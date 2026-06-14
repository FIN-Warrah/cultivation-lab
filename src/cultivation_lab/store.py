from __future__ import annotations

import json
from pathlib import Path
from threading import RLock
from typing import Iterable

from .config import DEFAULT_EVENTS_PATH
from .models import Event


class JsonEventStore:
    def __init__(self, path: Path | str = DEFAULT_EVENTS_PATH) -> None:
        self.path = Path(path)
        self._lock = RLock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self.path.exists():
            self._write_raw([])

    def load_events(self) -> list[Event]:
        with self._lock:
            raw_events = self._read_raw()
            return [Event.from_payload(item) for item in raw_events]

    def append_event(self, event: Event) -> Event:
        with self._lock:
            raw_events = self._read_raw()
            raw_events.append(event.to_dict())
            self._write_raw(raw_events)
        return event

    def append_events(self, events: Iterable[Event]) -> list[Event]:
        accepted = list(events)
        with self._lock:
            raw_events = self._read_raw()
            raw_events.extend(event.to_dict() for event in accepted)
            self._write_raw(raw_events)
        return accepted

    def clear(self) -> None:
        with self._lock:
            self._write_raw([])

    def _read_raw(self) -> list[dict]:
        if not self.path.exists():
            return []
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Event store is not valid JSON: {self.path}") from exc
        if not isinstance(data, list):
            raise RuntimeError(f"Event store must contain a JSON list: {self.path}")
        return data

    def _write_raw(self, raw_events: list[dict]) -> None:
        tmp_path = self.path.with_suffix(".tmp")
        tmp_path.write_text(
            json.dumps(raw_events, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        tmp_path.replace(self.path)
