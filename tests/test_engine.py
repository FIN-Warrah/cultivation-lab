from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cultivation_lab.engine import CultivationEngine, realm
from cultivation_lab.models import Event, ValidationError


class CultivationEngineTest(unittest.TestCase):
    def setUp(self) -> None:
        self.engine = CultivationEngine(decay_rate_per_day=0)
        self.now = int(datetime(2026, 6, 14, 12, 0).timestamp())

    def test_duration_is_seconds_and_scored_by_hour(self) -> None:
        event = Event.from_payload(
            {
                "type": "coding",
                "duration": 3600,
                "timestamp": self.now,
            }
        )

        self.assertEqual(self.engine.event_delta(event), 10)

    def test_realm_mapping(self) -> None:
        self.assertEqual(realm(99), "炼气期")
        self.assertEqual(realm(100), "筑基期")
        self.assertEqual(realm(800), "元婴期")
        self.assertEqual(realm(5000), "飞升期")

    def test_snapshot_and_daily_report(self) -> None:
        events = [
            Event.from_payload({"type": "coding", "duration": 7200, "timestamp": self.now - 3600}),
            Event.from_payload({"type": "writing", "duration": 3600, "timestamp": self.now - 1800}),
            Event.from_payload({"type": "browsing", "duration": 1800, "timestamp": self.now - 900}),
        ]

        snapshot = self.engine.snapshot(events, now=self.now)
        report = self.engine.daily_report(events, now=self.now)

        self.assertEqual(snapshot.cultivation_power, 31.0)
        self.assertEqual(snapshot.daily_delta, 31.0)
        self.assertEqual(report["total_delta"], 31.0)
        self.assertEqual(report["event_count"], 3)

    def test_validation_rejects_unknown_type(self) -> None:
        with self.assertRaises(ValidationError):
            Event.from_payload({"type": "sleeping", "duration": 10, "timestamp": self.now})


if __name__ == "__main__":
    unittest.main()
