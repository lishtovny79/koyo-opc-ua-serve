"""DirectLOGIC DL205 UDP transport and packet construction."""

from __future__ import annotations

import asyncio
import logging
import secrets
import socket

logger = logging.getLogger(__name__)
READ_TRIGGER = bytes.fromhex("48415048582e990600201900000000")


def crc16_ccitt(data: bytes | bytearray) -> int:
    crc = 0
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) if crc & 0x8000 else crc << 1
            crc &= 0xFFFF
    return crc


class KoyoPLC:
    def __init__(self, host: str, port: int, receive_timeout: float) -> None:
        self.host = host
        self.port = port
        self.receive_timeout = receive_timeout
        self.sock: socket.socket | None = None
        self.lock = asyncio.Lock()
        self._read_handle = secrets.randbits(16)
        self._peer = (socket.gethostbyname(host), port)
        self.rejected_packets: dict[str, int] = {}
        self._seq = 0xC2
        self.is_online = False
        self._connect_socket()

    def _connect_socket(self) -> None:
        if self.sock is not None:
            self.sock.close()
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        logger.info("UDP socket initialized for %s:%s", self.host, self.port)

    def close(self) -> None:
        if self.sock is not None:
            self.sock.close()
            self.sock = None

    def _reject(self, reason: str) -> None:
        count = self.rejected_packets.get(reason, 0) + 1
        self.rejected_packets[reason] = count
        if count == 1 or count % 100 == 0:
            logger.warning("Rejected PLC UDP response: %s (count=%d)", reason, count)

    async def _receive(self, handle: bytes, command: int | None,
                       expected_length: int | None) -> bytes | None:
        if self.sock is None:
            return None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.receive_timeout
        while (remaining := deadline - loop.time()) > 0:
            try:
                data, peer = await asyncio.wait_for(
                    loop.sock_recvfrom(self.sock, 2048), remaining
                )
            except asyncio.TimeoutError:
                return None
            except OSError as exc:
                logger.warning("UDP receive error: %s", exc)
                return None
            reason = self._invalid_response(data, peer, handle, command, expected_length)
            if reason:
                self._reject(reason)
                continue
            return data
        return None

    def _invalid_response(self, data: bytes, peer: tuple,
                          handle: bytes, command: int | None, expected_length: int | None) -> str | None:
        if peer[:2] != self._peer:
            return "unexpected sender"
        if len(data) < 13 or data[:3] != b"HAP":
            return "invalid HAP header"
        if data[3:5] != handle:
            return "late or unrelated transaction"
        if int.from_bytes(data[7:9], "little") != len(data) - 9:
            return "invalid declared payload length"
        if int.from_bytes(data[5:7], "little") != crc16_ccitt(data[9:]):
            return "CRC mismatch"
        if command is not None and data[9] != command:
            return "unexpected transaction phase"
        if command is not None and data[10:13] != bytes([0x19, 0, 0]):
            return "PLC response status or function mismatch"
        if expected_length is not None and len(data) != expected_length:
            return "unexpected read block length"
        return None

    def _failed_exchange(self) -> None:
        self.is_online = False
        # A fresh source port prevents a timed-out response from reaching the next request.
        self._connect_socket()

    async def exchange(self, setup: bytes, sequence: int, trigger: bytes | None = None) -> bytes | bool | None:
        """Serialize exchanges and accept only an exact response to the current phase."""
        async with self.lock:
            if self.sock is None:
                self._connect_socket()
            assert self.sock is not None
            expected_bytes = None
            if trigger is not None:
                if len(setup) != 17 or setup[9:13] != bytes([0x19, 0, 1, 0x1E]):
                    raise ValueError("Invalid read setup packet")
                expected_bytes = setup[13]
                if expected_bytes == 0 or expected_bytes % 2:
                    raise ValueError("Invalid read block byte count")
                # Templates are cached, but each actual read needs a new two-byte handle.
                self._read_handle = (self._read_handle + 1) & 0xFFFF
                handle = self._read_handle.to_bytes(2, "little")
                setup = setup[:3] + handle + setup[5:]
                trigger = trigger[:3] + handle + trigger[5:]
            else:
                handle = setup[3:5]
                if not handle or setup[3] != sequence:
                    raise ValueError("Invalid write transaction handle")
            loop = asyncio.get_running_loop()
            try:
                await loop.sock_sendto(self.sock, setup, self._peer)
                if await self._receive(handle, 0x20 if trigger is not None else None, 15 if trigger is not None else None) is None:
                    self._failed_exchange()
                    return None
                if trigger is None:
                    self.is_online = True
                    return True
                await asyncio.sleep(0.01)
                await loop.sock_sendto(self.sock, trigger, self._peer)
                response = await self._receive(handle, 0x22, 13 + expected_bytes)
                if response is None:
                    self._failed_exchange()
                    return None
                self.is_online = True
                return response[13:]
            except OSError as exc:
                logger.warning("PLC exchange error: %s", exc)
                self._failed_exchange()
                return None

    def next_sequence(self) -> int:
        self._seq = (self._seq + 1) & 0xFF
        return self._seq

    def make_write_packet(self, address: int, values: list[int]) -> tuple[bytes, int]:
        if not 1 <= len(values) <= 127:
            raise ValueError("write request must contain 1 to 127 words")
        data = bytearray()
        for value in values:
            word = int(value) & 0xFFFF
            data.extend((word & 0xFF, word >> 8))
        plc_address = address + 1
        payload = bytearray([0x19, 0x00, 0x01, 0x20, len(data), plc_address & 0xFF,
                             (plc_address >> 8) & 0xFF, 0x31]) + data
        sequence = self.next_sequence()
        crc = crc16_ccitt(payload)
        packet = bytes([0x48, 0x41, 0x50, sequence, sequence ^ 0x10, crc & 0xFF,
                        (crc >> 8) & 0xFF, 0x0A, 0x00]) + bytes(payload)
        return packet, sequence

    def make_read_packet(self, address: int, length: int) -> bytes:
        if not 1 <= length <= 127:
            raise ValueError("read request must contain 1 to 127 words")
        plc_address = address + 1
        payload = bytearray([0x19, 0x00, 0x01, 0x1E, length * 2, plc_address & 0xFF,
                             (plc_address >> 8) & 0xFF, 0x31])
        crc = crc16_ccitt(payload)
        return bytes([0x48, 0x41, 0x50, 0x48, 0x58, crc & 0xFF, (crc >> 8) & 0xFF,
                      0x08, 0x00]) + bytes(payload)
