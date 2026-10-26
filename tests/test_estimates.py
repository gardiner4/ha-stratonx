"""Schedule interpolation, boundary, and override regression tests."""
import importlib.util
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "estimates", ROOT / "custom_components/ati_straton_x/estimates.py")
e = importlib.util.module_from_spec(spec)
spec.loader.exec_module(e)


def sample(clock="2026-10-26 12:00:00", remaining=0):
    return {
        "local_time": clock,
        "live_remaining": remaining,
        "schedule": {"nodes": [
            {"timestamp": 28800, "channelValues": [0] * 6},
            {"timestamp": 36000, "channelValues": [313, 798, 798, 437, 443, 187]},
            {"timestamp": 72000, "channelValues": [313, 798, 798, 437, 443, 187]},
            {"timestamp": 79200, "channelValues": [0] * 6},
        ]},
    }


class EstimateTests(unittest.TestCase):
    def test_observed_daytime_plateau(self):
        self.assertEqual(e.estimate_channels(sample()),
                         ([30.6, 78.0, 78.0, 42.7, 43.3, 18.3], "schedule_estimate"))

    def test_rising_and_falling_ramps(self):
        for clock in ("2026-10-26 09:00:00", "2026-10-26 21:00:00"):
            self.assertEqual(e.estimate_channels(sample(clock))[0],
                             [15.3, 39.0, 39.0, 21.4, 21.7, 9.1])

    def test_exact_node(self):
        self.assertEqual(e.estimate_channels(sample("2026-10-26 10:00:00"))[0],
                         e.estimate_channels(sample())[0])

    def test_dark_boundaries_and_midnight(self):
        for hour in ("00", "07", "08", "22", "23"):
            self.assertEqual(e.estimate_channels(sample(f"2026-10-26 {hour}:00:00"))[0], [0] * 6)

    def test_unknown_nonzero_wraparound(self):
        data = sample("2026-10-26 00:00:00")
        data["schedule"]["nodes"][-1]["channelValues"][0] = 30
        self.assertEqual(e.estimate_channels(data), (None, "outside_schedule"))

    def test_live_override_and_resume(self):
        data = sample(remaining=60)
        self.assertEqual(e.estimate_channels(data), (None, "live_mode_active"))
        data["live_remaining"] = 0
        self.assertIsNotNone(e.estimate_channels(data)[0])

    def test_unknown_timer_never_claims_scheduled_output(self):
        for remaining in (None, True, -1, "0"):
            self.assertEqual(e.estimate_channels(sample(remaining=remaining)),
                             (None, "live_mode_unknown"))

    def test_invalid_clock(self):
        for clock in (None, "", "bad", "2000-00-00 00:00:00"):
            self.assertEqual(e.estimate_channels(sample(clock)), (None, "clock_unknown"))

    def test_invalid_schedule(self):
        for nodes in (None, [], [{}], [{"timestamp": 1, "channelValues": [0]*6}]*2):
            data = sample()
            data["schedule"] = {"nodes": nodes}
            self.assertEqual(e.estimate_channels(data), (None, "schedule_invalid"))

    def test_invalid_channels_and_times(self):
        for value in (-1, 1024, True, float("nan")):
            data = sample()
            data["schedule"]["nodes"][1]["channelValues"][0] = value
            self.assertEqual(e.estimate_channels(data)[0], None)
        for stamp in (-1, 86400, True, 0):
            data = sample()
            data["schedule"]["nodes"][1]["timestamp"] = stamp
            self.assertEqual(e.estimate_channels(data)[0], None)

    def test_full_scale_and_independent_fixtures(self):
        first, second = sample(), sample()
        first["schedule"]["nodes"][1]["channelValues"] = [1023]*6
        first["local_time"] = "2026-10-26 10:00:00"
        self.assertEqual(e.estimate_channels(first)[0], [100]*6)
        self.assertEqual(e.estimate_channels(second)[0][0], 30.6)


if __name__ == "__main__":
    unittest.main()
