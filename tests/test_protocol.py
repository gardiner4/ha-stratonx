"""Validate parsers against captured BLE packets and malformed responses."""
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("protocol", ROOT / "custom_components/ati_straton_x/protocol.py")
p = importlib.util.module_from_spec(spec)
spec.loader.exec_module(p)


class ProtocolTest(unittest.TestCase):
    def test_recorded_schedule(self):
        evidence = json.loads((ROOT / "tests/fixtures/schedule.json").read_text())
        packets = evidence["schedule_packets"]
        self.assertEqual(p.schedule_count(bytes.fromhex(packets[0]["response_hex"])), 8)
        nodes = [p.schedule_node(bytes.fromhex(item["response_hex"])) for item in packets[1:]]
        self.assertEqual(nodes, evidence["schedule"]["nodes"])

    def test_recorded_temperature(self):
        self.assertEqual(p.temperatures(bytes.fromhex("ff2c282f")), {"temperature_1": 44, "temperature_2": 40, "controller_temperature": 47})

    def test_recorded_clock_header(self):
        self.assertEqual(p.header(0xD1, 36809, 0, 0xB1, "112233445566").hex(), "d1b1c98f0000112233445566")

    def test_group_and_passcode_encoding(self):
        self.assertEqual(p.header(0xC3, 36809).hex(), "c300c98f0000000000000000")
        self.assertNotEqual(p.header(0xC3, 42), p.header(0xC3, 36809))
        self.assertEqual(p.header(0xC3, 42, 513)[4:6], b"\x01\x02")

    def test_reject_bad_values(self):
        for value in (b"", b"empty", b"\xcc\xff\xff"):
            with self.assertRaises(ValueError):
                p.schedule_count(value)
        for value in (b"", b"\xff\x2c", b"\x00\x2c\x28\x2f", b"\xff\xff\x28\x2f"):
            with self.assertRaises(ValueError):
                p.temperatures(value)
        for node in ({"timestamp": -1, "channelValues": [0]*6}, {"timestamp": 0, "channelValues": [1024]*6}, {"timestamp": True, "channelValues": [0]*6}, {"timestamp": 0, "channelValues": [0]*5}):
            with self.assertRaises(ValueError):
                p.schedule_node(b"\xbb" + json.dumps(node).encode())
        for serial in ("wrong", "206EF18C987", "206EF18C987Z"):
            with self.assertRaises(ValueError):
                p.serial_id(serial)


if __name__ == "__main__":
    unittest.main()
