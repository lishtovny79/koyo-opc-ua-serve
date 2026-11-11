import asyncio
import struct
import unittest
from types import SimpleNamespace

from koyo_opc_ua_server.opc_server import OpcServerManager
from koyo_opc_ua_server.plc import READ_TRIGGER, KoyoPLC, crc16_ccitt


def frame(handle, command, words=()):
    payload = bytes([command, 0x19, 0, 0]) + struct.pack("<" + "H" * len(words), *words)
    if command == 0x20:
        payload += b"\0\0"
    return (
        b"HAP"
        + handle
        + struct.pack("<HH", crc16_ccitt(payload), len(payload))
        + payload
    )


class Validation(unittest.TestCase):
    def setUp(self):
        self.c = KoyoPLC("127.0.0.1", 28784, 0.1)

    def tearDown(self):
        self.c.close()

    def test_rejected_packet_reasons(self):
        h = b"\x12\x34"
        good = frame(h, 0x22, [0x1234, 0x5678])
        def check(d, peer=("127.0.0.1", 28784)):
            return self.c._invalid_response(d, peer, h, 0x22, 17)
        self.assertIsNone(check(good))
        self.assertIn("sender", check(good, ("127.0.0.2", 28784)))
        self.assertIn("header", check(b"bad"))
        bad = bytearray(good)
        bad[4] ^= 1
        self.assertIn("transaction", check(bad))
        bad = bytearray(good)
        bad[7] ^= 1
        self.assertIn("length", check(bad))
        bad = bytearray(good)
        bad[-1] ^= 1
        self.assertIn("CRC", check(bad))
        self.assertIn("phase", check(frame(h, 0x20)))
        self.assertIn("length", check(frame(h, 0x22, [0x1234])))


class UDPTests(unittest.IsolatedAsyncioTestCase):
    async def test_delayed_wrong_phase_and_duplicate_packets(self):
        loop = asyncio.get_running_loop()
        seen = []

        class PLC(asyncio.DatagramProtocol):
            def connection_made(s, t):
                s.transport = t
                s.previous = None

            def datagram_received(s, data, addr):
                h = data[3:5]
                if len(data) == 17:
                    seen.append(h)
                    if s.previous:
                        s.transport.sendto(frame(s.previous, 0x20), addr)
                    s.transport.sendto(frame(h, 0x22, [0x9999, 0x8888]), addr)
                    s.transport.sendto(frame(h, 0x20), addr)
                else:
                    bad = bytearray(frame(h, 0x22, [0x9999, 0x8888]))
                    bad[-1] ^= 1
                    s.transport.sendto(bytes(bad), addr)
                    s.transport.sendto(frame(h, 0x22, [1]), addr)
                    s.transport.sendto(frame(h, 0x20), addr)
                    s.transport.sendto(frame(h, 0x22, [0x12, 0x34]), addr)
                    s.previous = h

        transport, _ = await loop.create_datagram_endpoint(
            PLC, local_addr=("127.0.0.1", 0)
        )
        c = KoyoPLC("127.0.0.1", transport.get_extra_info("sockname")[1], 0.2)
        try:
            template = c.make_read_packet(45, 2)
            for _ in range(2):
                self.assertEqual(
                    await c.exchange(template, 0x48, READ_TRIGGER),
                    struct.pack("<HH", 0x12, 0x34),
                )
            self.assertNotEqual(seen[0], seen[1])
            self.assertTrue(c.is_online)
            self.assertIn("late or unrelated transaction", c.rejected_packets)
            self.assertIn("CRC mismatch", c.rejected_packets)
            self.assertIn("unexpected read block length", c.rejected_packets)
        finally:
            c.close()
            transport.close()

    async def test_timeout_discards_socket(self):
        transport, _ = await asyncio.get_running_loop().create_datagram_endpoint(
            asyncio.DatagramProtocol, local_addr=("127.0.0.1", 0)
        )
        c = KoyoPLC("127.0.0.1", transport.get_extra_info("sockname")[1], 0.03)
        old = c.sock
        try:
            self.assertIsNone(
                await c.exchange(c.make_read_packet(45, 2), 0x48, READ_TRIGGER)
            )
            self.assertFalse(c.is_online)
            self.assertIsNot(c.sock, old)
            self.assertEqual(old.fileno(), -1)
        finally:
            c.close()
            transport.close()

    async def test_cache_commit_requires_all_blocks(self):
        class Fake:
            def __init__(s):
                s.results = [struct.pack("<HH", 10, 20), b"\x01"]
                s.is_online = True

            async def exchange(s, *args):
                return s.results.pop(0)

        fake = Fake()
        a = bytearray(17)
        a[13] = 4
        obj = SimpleNamespace(
            word_cache={45: 1, 46: 2},
            read_requests=[(45, bytes(a)), (50, bytes(a))],
            plc=fake,
        )

        async def status():
            pass

        obj.update_online_status = status
        self.assertFalse(await OpcServerManager.sync_plc(obj))
        self.assertEqual(obj.word_cache, {45: 1, 46: 2})
        fake.results = [struct.pack("<HH", 10, 20), struct.pack("<HH", 30, 40)]
        self.assertTrue(await OpcServerManager.sync_plc(obj))
        self.assertEqual(obj.word_cache, {45: 10, 46: 20, 50: 30, 51: 40})


if __name__ == "__main__":
    unittest.main()
