from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cultivation_lab.models import Event
from cultivation_lab.store import JsonEventStore


def main() -> None:
    now = datetime.now()
    entries = [
        ("paper_reading", 90, now.replace(hour=9, minute=0, second=0, microsecond=0), "精读相关工作"),
        ("coding", 120, now.replace(hour=11, minute=0, second=0, microsecond=0), "实现事件 API"),
        ("experiment_run", 75, now.replace(hour=14, minute=30, second=0, microsecond=0), "跑通 baseline"),
        ("debugging", 45, now.replace(hour=16, minute=10, second=0, microsecond=0), "修复数据落盘问题"),
        ("browsing", 35, now.replace(hour=17, minute=15, second=0, microsecond=0), "无效信息流"),
        ("writing", 60, now.replace(hour=20, minute=0, second=0, microsecond=0), "整理实验记录"),
    ]
    store = JsonEventStore()
    store.clear()
    events = [
        Event.from_payload(
            {
                "type": event_type,
                "duration": minutes * 60,
                "timestamp": int(moment.timestamp()),
                "metadata": {"note": note, "quality": 1.0},
            }
        )
        for event_type, minutes, moment, note in entries
    ]

    yesterday = now - timedelta(days=1)
    events.append(
        Event.from_payload(
            {
                "type": "coding",
                "duration": 150 * 60,
                "timestamp": int(yesterday.replace(hour=15, minute=0, second=0, microsecond=0).timestamp()),
                "metadata": {"note": "昨日代码推进", "quality": 1.1},
            }
        )
    )
    store.append_events(events)
    print(f"Seeded {len(events)} events into {store.path}")


if __name__ == "__main__":
    main()
