import sys
import unittest
from pathlib import Path

sys.path[:0] = [str(Path(__file__).resolve().parents[1] / "router")]
from companion import cpu_percent, remaining_time


class TelemetryTests(unittest.TestCase):
    def test_cpu_excludes_guest_and_counts_iowait_as_idle(self):
        before = [100, 0, 100, 500, 100, 0, 0, 0, 80, 0]
        after = [120, 0, 110, 550, 120, 0, 0, 0, 90, 0]
        self.assertEqual(cpu_percent(before, after), 30)

    def test_cpu_first_sample_reset_and_no_elapsed_ticks(self):
        self.assertIsNone(cpu_percent(None, [1, 2, 3, 4]))
        self.assertIsNone(cpu_percent([1, 2, 3, 4], [1, 2, 3, 4]))
        self.assertIsNone(cpu_percent([10, 20, 30, 40], [1, 2, 3, 4]))

    def test_remaining_time_preserves_less_than_and_rejects_placeholders(self):
        self.assertEqual(remaining_time("8:10"), "8:10")
        self.assertEqual(remaining_time("< 0:10"), "< 0:10")
        for value in [None, "", "--", "3:99", 8]:
            self.assertIsNone(remaining_time(value))
