from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime
from math import exp
from typing import Iterable

from .config import (
    DECAY_RATE_PER_DAY,
    EVENT_LABELS,
    HEART_DEMON_BROWSING_HOURS,
    HEART_DEMON_FRAGMENTATION,
    REALM_THRESHOLDS,
    WEIGHTS,
)
from .models import CultivationState, Event, RealmProgress, utc_now_ts


SECONDS_PER_HOUR = 3600.0
SECONDS_PER_DAY = 86400.0


class CultivationEngine:
    def __init__(
        self,
        weights: dict[str, float] | None = None,
        decay_rate_per_day: float = DECAY_RATE_PER_DAY,
    ) -> None:
        self.weights = dict(weights or WEIGHTS)
        self.decay_rate_per_day = decay_rate_per_day

    def update(self, events: Iterable[Event]) -> float:
        return self.snapshot(events).cultivation_power

    def snapshot(self, events: Iterable[Event], now: int | None = None) -> CultivationState:
        now = now or utc_now_ts()
        ordered = sorted(events, key=lambda event: event.timestamp)
        power = 0.0
        last_ts: int | None = None

        for event in ordered:
            if last_ts is not None:
                power = self.apply_decay(power, event.timestamp - last_ts)
            power += self.event_delta(event)
            last_ts = event.timestamp

        if last_ts is not None:
            power = self.apply_decay(power, now - last_ts)

        progress = realm_progress(power)
        daily_delta = self.daily_delta(ordered, now=now)
        risk, warnings = self.heart_demon_risk(ordered, now=now)

        return CultivationState(
            cultivation_power=round(power, 2),
            realm=progress.realm,
            daily_delta=round(daily_delta, 2),
            heart_demon_risk=round(risk, 2),
            realm_progress=progress,
            total_events=len(ordered),
            last_event_timestamp=ordered[-1].timestamp if ordered else None,
            warnings=tuple(warnings),
        )

    def event_delta(self, event: Event) -> float:
        hours = event.duration / SECONDS_PER_HOUR
        weight = self.weights.get(event.type, 0.0)
        return weight * hours * self.estimate_quality(event)

    def estimate_quality(self, event: Event) -> float:
        raw_quality = event.metadata.get("quality", 1.0)
        try:
            quality = float(raw_quality)
        except (TypeError, ValueError):
            quality = 1.0
        return min(2.0, max(0.0, quality))

    def apply_decay(self, power: float, delta_seconds: float) -> float:
        if delta_seconds <= 0:
            return power
        delta_days = delta_seconds / SECONDS_PER_DAY
        return power * exp(-self.decay_rate_per_day * delta_days)

    def daily_delta(self, events: Iterable[Event], now: int | None = None) -> float:
        day = local_date(now or utc_now_ts())
        return sum(self.event_delta(event) for event in events if local_date(event.timestamp) == day)

    def daily_report(self, events: Iterable[Event], day: date | None = None, now: int | None = None) -> dict:
        now = now or utc_now_ts()
        report_day = day or local_date(now)
        selected = [event for event in events if local_date(event.timestamp) == report_day]
        selected.sort(key=lambda event: event.timestamp)

        by_type: dict[str, dict[str, float | int | str]] = defaultdict(
            lambda: {"type": "", "label": "", "duration": 0.0, "delta": 0.0, "count": 0}
        )
        log = []

        for event in selected:
            delta = self.event_delta(event)
            bucket = by_type[event.type]
            bucket["type"] = event.type
            bucket["label"] = EVENT_LABELS.get(event.type, event.type)
            bucket["duration"] = float(bucket["duration"]) + event.duration
            bucket["delta"] = float(bucket["delta"]) + delta
            bucket["count"] = int(bucket["count"]) + 1
            log.append(
                {
                    "id": event.id,
                    "time": datetime.fromtimestamp(event.timestamp).strftime("%H:%M"),
                    "type": event.type,
                    "label": EVENT_LABELS.get(event.type, event.type),
                    "duration": event.duration,
                    "duration_minutes": round(event.duration / 60.0, 1),
                    "delta": round(delta, 2),
                    "metadata": event.metadata,
                }
            )

        summary = []
        for item in by_type.values():
            summary.append(
                {
                    "type": item["type"],
                    "label": item["label"],
                    "duration": round(float(item["duration"]), 2),
                    "duration_hours": round(float(item["duration"]) / SECONDS_PER_HOUR, 2),
                    "delta": round(float(item["delta"]), 2),
                    "count": item["count"],
                }
            )
        summary.sort(key=lambda item: abs(float(item["delta"])), reverse=True)

        total_delta = round(sum(item["delta"] for item in log), 2)
        risk, warnings = self.heart_demon_risk(selected, now=now)
        narrative = self._daily_narrative(total_delta, risk, selected)

        return {
            "date": report_day.isoformat(),
            "total_delta": total_delta,
            "event_count": len(selected),
            "summary": summary,
            "log": log,
            "heart_demon_risk": round(risk, 2),
            "warnings": warnings,
            "narrative": narrative,
        }

    def heart_demon_risk(self, events: Iterable[Event], now: int | None = None) -> tuple[float, list[str]]:
        now = now or utc_now_ts()
        window_start = now - SECONDS_PER_DAY
        recent = [event for event in events if window_start <= event.timestamp <= now]
        browsing_hours = sum(event.duration for event in recent if event.type == "browsing") / SECONDS_PER_HOUR
        idle_hours = sum(event.duration for event in recent if event.type == "idle") / SECONDS_PER_HOUR
        total_hours = sum(event.duration for event in recent) / SECONDS_PER_HOUR
        tab_switches = sum(_numeric_metadata(event, "tab_switches") for event in recent)
        fragmentation = (len(recent) / max(total_hours, 0.25)) + (tab_switches / 40.0)

        risk = min(
            1.0,
            (browsing_hours / HEART_DEMON_BROWSING_HOURS) * 0.45
            + (idle_hours / 4.0) * 0.25
            + (fragmentation / HEART_DEMON_FRAGMENTATION) * 0.30,
        )

        warnings = []
        if browsing_hours > HEART_DEMON_BROWSING_HOURS:
            warnings.append("心魔预警：近 24 小时无效浏览偏高。")
        if fragmentation > HEART_DEMON_FRAGMENTATION:
            warnings.append("心魔预警：行为碎片化偏高，建议安排一段连续深度工作。")
        return risk, warnings

    def _daily_narrative(self, total_delta: float, risk: float, events: list[Event]) -> str:
        if not events:
            return "今日尚未记录修炼行为。"
        if risk >= 0.75:
            return "今日心魔扰动明显，建议先压低浏览和切换频率。"
        if total_delta >= 40:
            return "今日修炼势头强劲，有明显学术推进。"
        if total_delta >= 15:
            return "今日修炼稳定，适合在晚间补一段总结或论文笔记。"
        if total_delta >= 0:
            return "今日修为小幅增长，可以用一个低阻力任务收尾。"
        return "今日修为回落，优先减少无效浏览并恢复连续专注。"


def realm(power: float) -> str:
    return realm_progress(power).realm


def realm_progress(power: float) -> RealmProgress:
    thresholds = list(REALM_THRESHOLDS)
    current_index = 0
    for index, (threshold, _) in enumerate(thresholds):
        if power >= threshold:
            current_index = index
        else:
            break

    lower, current_realm = thresholds[current_index]
    next_index = current_index + 1
    if next_index >= len(thresholds):
        return RealmProgress(
            realm=current_realm,
            lower_bound=lower,
            upper_bound=None,
            next_realm=None,
            progress=1.0,
        )

    upper, next_realm = thresholds[next_index]
    progress = (power - lower) / (upper - lower)
    return RealmProgress(
        realm=current_realm,
        lower_bound=lower,
        upper_bound=upper,
        next_realm=next_realm,
        progress=round(min(1.0, max(0.0, progress)), 4),
    )


def local_date(timestamp: int | float) -> date:
    return datetime.fromtimestamp(timestamp).date()


def _numeric_metadata(event: Event, key: str) -> float:
    value = event.metadata.get(key, 0)
    if isinstance(value, bool):
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0
