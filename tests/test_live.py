"""Failure-path tests for timer-first manual overrides, without Bluetooth."""
import importlib.util
from pathlib import Path
import sys
import types
import unittest

ROOT = Path(__file__).resolve().parents[1] / "custom_components/ati_straton_x"
package = types.ModuleType("straton_test")
package.__path__ = [str(ROOT)]
sys.modules[package.__name__] = package
from straton_test.live import apply_live


class LiveTest(unittest.IsolatedAsyncioTestCase):
    async def run_action(self, responses, seconds=600, channels=None, fail_output=False):
        writes = []

        async def write(packet):
            writes.append(packet)
            if fail_output and packet[0] == 0xA2:
                raise ConnectionError("Ambiguous output write")

        async def query(packet):
            self.assertEqual(packet[:2], b"\xc2\xb2")
            return responses.pop(0)

        self.writes = writes
        return await apply_live(write, query, 42, 0, seconds, channels if channels is not None else [0]*6)

    async def test_timer_before_output(self):
        self.assertEqual(await self.run_action([b"599", b"598"]), 598)
        self.assertEqual([p[0] for p in self.writes], [0xB2, 0xA2])

    async def test_resume_never_sets_channels(self):
        self.assertEqual(await self.run_action([b"0"], seconds=0), 0)
        self.assertEqual(len(self.writes), 1)
        self.assertEqual(self.writes[0][-2:], b"\x00\x00")

    async def test_unconfirmed_timer_never_sets_channels(self):
        with self.assertRaises(ValueError):
            await self.run_action([b"0"])
        self.assertEqual([p[0] for p in self.writes], [0xB2, 0xB2])
        self.assertEqual(self.writes[-1][-2:], b"\x00\x00")

    async def test_partial_write_attempts_resume(self):
        with self.assertRaises(ConnectionError):
            await self.run_action([b"599"], fail_output=True)
        self.assertEqual([p[0] for p in self.writes], [0xB2, 0xA2, 0xB2])
        self.assertEqual(self.writes[-1][-2:], b"\x00\x00")

    async def test_invalid_channels_make_no_writes(self):
        with self.assertRaises(ValueError):
            await self.run_action([], channels=[1024]*6)
        self.assertEqual(self.writes, [])

    async def test_expired_timer_after_channels_attempts_resume(self):
        with self.assertRaises(ValueError):
            await self.run_action([b"599", b"0"])
        self.assertEqual(self.writes[-1][-2:], b"\x00\x00")


if __name__ == "__main__":
    unittest.main()
