"""DirectLOGIC DL205 UDP transport and packet construction."""

from __future__ import annotations

import asyncio
import logging
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

    async def _receive(self, expected_seq: int) -> bytes | None:
        if self.sock is None:
            return None
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.receive_timeout
        while (remaining := deadline - loop.time()) > 0:
            try:
                data, _ = await asyncio.wait_for(loop.sock_recvfrom(self.sock, 2048), remaining)
            except asyncio.TimeoutError:
                return None
            except OSError as exc:
                logger.warning("UDP receive error: %s", exc)
                return None
            if len(data) > 3 and data[3] == expected_seq:
                return data
        return None

    async def exchange(self, setup: bytes, sequence: int, trigger: bytes | None = None) -> bytes | bool | None:
        """Run one serialized PLC transaction; only a matching response is accepted."""
        async with self.lock:
            if self.sock is None:
                self._connect_socket()
            assert self.sock is not None
            loop = asyncio.get_running_loop()
            try:
                await loop.sock_sendto(self.sock, setup, (self.host, self.port))
                if await self._receive(sequence) is None:
                    self.is_online = False
                    return None
                if trigger is None:
                    self.is_online = True
                    return True
                await asyncio.sleep(0.01)  # Required by the DL205 two-phase read exchange.
                await loop.sock_sendto(self.sock, trigger, (self.host, self.port))
                response = await self._receive(sequence)
                if response is None or len(response) < 14 or response[9] != 0x22:
                    self.is_online = False
                    return None
                self.is_online = True
                return response[13:]
            except OSError as exc:
                logger.warning("PLC exchange error: %s", exc)
                self.is_online = False
                self._connect_socket()
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
