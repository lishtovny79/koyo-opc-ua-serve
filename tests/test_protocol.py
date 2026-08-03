from koyo_opc_ua_server.plc import KoyoPLC, crc16_ccitt


def test_crc16_ccitt_empty_payload():
    assert crc16_ccitt(b"") == 0


def test_maps_v_memory_and_control_bit_addresses():
    plc = KoyoPLC("127.0.0.1", 28784, 0.1)
    try:
        packet, sequence = plc.make_write_packet(10, [0x1234, 0xABCD])
        assert packet[3] == sequence
        assert packet[9:17] == bytes([0x19, 0, 1, 0x20, 4, 11, 0, 0x31])
        assert packet[17:] == bytes([0x34, 0x12, 0xCD, 0xAB])
    finally:
        plc.close()
