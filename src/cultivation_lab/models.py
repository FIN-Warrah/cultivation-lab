from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from math import isfinite
from typing import Any
from uuid import uuid4

from .config import EVENT_TYPES


class ValidationError(ValueError):
    """Raised when an incoming event payload cannot be accepted."""


def utc_now_ts() -> int:
    return int(datetime.now(tz=timezone.utc).timestamp())


@dataclass(frozen=True)
class Event:
    type: str
    duration: float
    timestamp: int
    metadata: dict[str, Any] = field(default_factory=dict)
    id: str = field(default_factory=lambda: uuid4().hex)

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "Event":
        if not isinstance(payload, dict):
            raise ValidationError("Event payload must be a JSON object.")

        event_type = payload.get("type")
        if event_type not in EVENT_TYPES:
            allowed = ", ".join(EVENT_TYPES)
            raise ValidationError(f"Unknown event type {event_type!r}. Allowed: {allowed}.")

        duration = _coerce_float(payload.get("duration"), "duration")
        if duration < 0:
            raise ValidationError("duration must be non-negative seconds.")

        raw_timestamp = payload.get("timestamp", utc_now_ts())
        timestamp = int(_coerce_float(raw_timestamp, "timestamp"))
        if timestamp <= 0:
            raise ValidationError("timestamp must be a positive Unix timestamp.")

        metadata = payload.get("metadata", {})
        if metadata is None:
            metadata = {}
        if not isinstance(metadata, dict):
            raise ValidationError("metadata must be an object when provided.")

        event_id = payload.get("id") or uuid4().hex
        if not isinstance(event_id, str):
            raise ValidationError("id must be a string when provided.")

        return cls(
            type=event_type,
            duration=duration,
            timestamp=timestamp,
            metadata=metadata,
            id=event_id,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "duration": self.duration,
            "timestamp": self.timestamp,
            "metadata": self.metadata,
        }


@dataclass(frozen=True)
class RealmProgress:
    realm: str
    lower_bound: float
    upper_bound: float | None
    next_realm: str | None
    progress: float

    def to_dict(self) -> dict[str, Any]:
        return {
            "realm": self.realm,
            "lower_bound": self.lower_bound,
            "upper_bound": self.upper_bound,
            "next_realm": self.next_realm,
            "progress": self.progress,
        }


@dataclass(frozen=True)
class CultivationState:
    cultivation_power: float
    realm: str
    daily_delta: float
    heart_demon_risk: float
    realm_progress: RealmProgress
    total_events: int
    last_event_timestamp: int | None
    warnings: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "cultivation_power": self.cultivation_power,
            "realm": self.realm,
            "daily_delta": self.daily_delta,
            "heart_demon_risk": self.heart_demon_risk,
            "realm_progress": self.realm_progress.to_dict(),
            "total_events": self.total_events,
            "last_event_timestamp": self.last_event_timestamp,
            "warnings": list(self.warnings),
        }


def _coerce_float(value: Any, field_name: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{field_name} must be a number.")
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{field_name} must be a number.") from exc
    if not isfinite(result):
        raise ValidationError(f"{field_name} must be finite.")
    return result
