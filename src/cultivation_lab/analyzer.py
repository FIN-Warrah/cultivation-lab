from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any

from .config import EVENT_LABELS, WEIGHTS


DEFAULT_MINUTES = {
    "coding": 75,
    "paper_reading": 60,
    "experiment_run": 90,
    "writing": 70,
    "debugging": 50,
    "meeting": 45,
    "browsing": 30,
    "idle": 25,
}

POSITIVE_HINTS = {
    "完成": 0.18,
    "写完": 0.18,
    "跑通": 0.20,
    "复现": 0.18,
    "baseline": 0.18,
    "收敛": 0.18,
    "优化": 0.12,
    "修复": 0.12,
    "定位": 0.10,
    "总结": 0.10,
    "投稿": 0.22,
    "实验记录": 0.12,
    "读完": 0.12,
    "笔记": 0.10,
    "figure": 0.12,
    "表格": 0.10,
    "ablation": 0.18,
}

FRICTION_HINTS = {
    "卡住": -0.10,
    "没进展": -0.18,
    "刷": -0.12,
    "乱看": -0.16,
    "分心": -0.14,
    "拖延": -0.18,
    "失败": -0.08,
}

CHINESE_NUMBERS = {
    "零": 0,
    "一": 1,
    "二": 2,
    "两": 2,
    "三": 3,
    "四": 4,
    "五": 5,
    "六": 6,
    "七": 7,
    "八": 8,
    "九": 9,
    "十": 10,
    "半": 0.5,
}


@dataclass(frozen=True)
class ActivityAnalysis:
    event_type: str
    label: str
    duration_minutes: int
    quality: float
    estimated_delta: float
    achievement_score: int
    confidence: float
    tags: tuple[str, ...]
    feedback: str
    source: str = "local_ai"

    def to_dict(self) -> dict:
        return {
            "event_type": self.event_type,
            "label": self.label,
            "duration_minutes": self.duration_minutes,
            "quality": self.quality,
            "estimated_delta": self.estimated_delta,
            "achievement_score": self.achievement_score,
            "confidence": self.confidence,
            "tags": list(self.tags),
            "feedback": self.feedback,
            "source": self.source,
        }


class ActivityAnalyzer:
    def __init__(self, remote: "OpenAIActivityAnalyzer | None" = None, use_remote: bool = True) -> None:
        if not use_remote:
            self.remote = None
        else:
            self.remote = remote if remote is not None else OpenAIActivityAnalyzer.from_env()
        self.local = LocalActivityAnalyzer()

    def analyze(self, event_type: str, note: str) -> ActivityAnalysis:
        if self.remote is not None:
            try:
                return self.remote.analyze(event_type=event_type, note=note)
            except AnalysisProviderError:
                pass
        return self.local.analyze(event_type=event_type, note=note)


class LocalActivityAnalyzer:
    def analyze(self, event_type: str, note: str) -> ActivityAnalysis:
        clean_note = " ".join((note or "").strip().split())
        duration_minutes, duration_confidence = infer_duration_minutes(clean_note, event_type)
        quality, tags = infer_quality(clean_note, event_type)
        weight = WEIGHTS.get(event_type, 0.0)
        estimated_delta = round(weight * (duration_minutes / 60.0) * quality, 2)
        achievement_score = round(max(-100, min(100, estimated_delta * 4)))
        confidence = round(min(0.96, 0.48 + duration_confidence + min(0.24, len(clean_note) / 180)), 2)
        feedback = relaxed_feedback(
            event_type=event_type,
            duration_minutes=duration_minutes,
            quality=quality,
            estimated_delta=estimated_delta,
            tags=tags,
            note=clean_note,
        )

        return ActivityAnalysis(
            event_type=event_type,
            label=EVENT_LABELS.get(event_type, event_type),
            duration_minutes=duration_minutes,
            quality=quality,
            estimated_delta=estimated_delta,
            achievement_score=achievement_score,
            confidence=confidence,
            tags=tuple(tags),
            feedback=feedback,
        )


class AnalysisProviderError(RuntimeError):
    """Raised when an external AI provider cannot produce a usable analysis."""


class OpenAIActivityAnalyzer:
    def __init__(
        self,
        api_key: str,
        model: str = "gpt-5.5",
        base_url: str = "https://api.openai.com/v1",
        timeout_seconds: float = 20.0,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    @classmethod
    def from_env(cls) -> "OpenAIActivityAnalyzer | None":
        api_key = os.getenv("OPENAI_API_KEY") or os.getenv("CULTIVATION_AI_API_KEY")
        if not api_key:
            return None
        return cls(
            api_key=api_key,
            model=os.getenv("CULTIVATION_AI_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-5.5",
            base_url=os.getenv("CULTIVATION_AI_BASE_URL")
            or os.getenv("OPENAI_BASE_URL")
            or "https://api.openai.com/v1",
            timeout_seconds=_env_float("CULTIVATION_AI_TIMEOUT", 20.0),
        )

    def analyze(self, event_type: str, note: str) -> ActivityAnalysis:
        label = EVENT_LABELS.get(event_type, event_type)
        payload = {
            "model": self.model,
            "input": [
                {
                    "role": "system",
                    "content": (
                        "你是 Cultivation Lab 的科研修炼评估器。"
                        "根据用户对一次科研行为的自然语言描述，估算投入时长、质量、成果标签和修仙风格评语。"
                        "只输出 JSON，不要输出 Markdown。"
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"行为类别: {event_type} / {label}\n"
                        f"类别权重: {WEIGHTS.get(event_type, 0.0)}\n"
                        f"用户描述: {note}\n\n"
                        "请返回字段: duration_minutes(int,1-720), quality(number,0.25-1.85), "
                        "achievement_score(int,-100到100), confidence(number,0-1), "
                        "tags(array of short strings,最多5个), feedback(string,中文,修仙风格,不超过90字)。"
                        "不要让负面类别 browsing/idle 得到正向质量奖励。"
                    ),
                },
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": "cultivation_activity_analysis",
                    "schema": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "duration_minutes": {"type": "integer", "minimum": 1, "maximum": 720},
                            "quality": {"type": "number", "minimum": 0.25, "maximum": 1.85},
                            "achievement_score": {"type": "integer", "minimum": -100, "maximum": 100},
                            "confidence": {"type": "number", "minimum": 0, "maximum": 1},
                            "tags": {
                                "type": "array",
                                "items": {"type": "string"},
                                "maxItems": 5,
                            },
                            "feedback": {"type": "string", "maxLength": 120},
                        },
                        "required": [
                            "duration_minutes",
                            "quality",
                            "achievement_score",
                            "confidence",
                            "tags",
                            "feedback",
                        ],
                    },
                    "strict": True,
                }
            },
            "max_output_tokens": 500,
        }

        response = self._post_json("/responses", payload)
        raw_text = _extract_response_text(response)
        if not raw_text:
            raise AnalysisProviderError("AI provider returned no text.")
        try:
            parsed = json.loads(_strip_json_fence(raw_text))
        except json.JSONDecodeError as exc:
            raise AnalysisProviderError("AI provider returned invalid JSON.") from exc

        duration_minutes = _clamp_int(parsed.get("duration_minutes"), 1, 720, DEFAULT_MINUTES.get(event_type, 45))
        quality = _clamp_float(parsed.get("quality"), 0.25, 1.85, 1.0)
        if event_type in {"browsing", "idle"}:
            quality = min(quality, 1.0)
        estimated_delta = round(WEIGHTS.get(event_type, 0.0) * (duration_minutes / 60.0) * quality, 2)
        tags = _normalize_tags(parsed.get("tags"))
        feedback = str(parsed.get("feedback") or "").strip()
        if not feedback:
            feedback = relaxed_feedback(event_type, duration_minutes, quality, estimated_delta, tags, note)

        return ActivityAnalysis(
            event_type=event_type,
            label=label,
            duration_minutes=duration_minutes,
            quality=round(quality, 2),
            estimated_delta=estimated_delta,
            achievement_score=_clamp_int(
                parsed.get("achievement_score"),
                -100,
                100,
                round(max(-100, min(100, estimated_delta * 4))),
            ),
            confidence=round(_clamp_float(parsed.get("confidence"), 0.0, 1.0, 0.72), 2),
            tags=tuple(tags),
            feedback=feedback,
            source=f"openai:{self.model}",
        )

    def _post_json(self, path: str, payload: dict[str, Any]) -> dict[str, Any]:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"{self.base_url}{path}",
            data=body,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout_seconds) as response:
                return json.loads(response.read().decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, urllib.error.HTTPError, json.JSONDecodeError) as exc:
            raise AnalysisProviderError("AI provider request failed.") from exc


def infer_duration_minutes(note: str, event_type: str) -> tuple[int, float]:
    explicit = _duration_from_text(note)
    if explicit is not None:
        return max(1, min(12 * 60, round(explicit))), 0.24
    return DEFAULT_MINUTES.get(event_type, 45), 0.06


def infer_quality(note: str, event_type: str) -> tuple[float, list[str]]:
    lower = note.lower()
    quality = 1.0
    tags: list[str] = []

    if len(note) >= 16:
        quality += 0.08
        tags.append("描述清楚")
    if len(note) >= 48:
        quality += 0.08
        tags.append("细节充足")

    for word, delta in POSITIVE_HINTS.items():
        if word.lower() in lower:
            quality += delta
            tags.append(word)

    for word, delta in FRICTION_HINTS.items():
        if word in note:
            quality += delta
            tags.append(word)

    if event_type in {"browsing", "idle"}:
        quality = min(1.0, quality)
    elif event_type in {"experiment_run", "writing"}:
        quality += 0.04

    quality = round(max(0.25, min(1.85, quality)), 2)
    return quality, _dedupe(tags)[:4]


def relaxed_feedback(
    event_type: str,
    duration_minutes: int,
    quality: float,
    estimated_delta: float,
    tags: list[str],
    note: str,
) -> str:
    label = EVENT_LABELS.get(event_type, event_type)
    hours = duration_minutes / 60.0
    duration_text = f"{duration_minutes} 分钟" if duration_minutes < 90 else f"{hours:.1f} 小时"
    tag_text = "、".join(tags[:2]) if tags else "稳稳推进"

    if event_type in {"browsing", "idle"} or estimated_delta < 0:
        return f"{label}记下来了，约 {duration_text}。这段更像是心神散了一下，先不苛责，收回来就还能继续涨修为。"
    if estimated_delta >= 28:
        return f"{label}这一段很顶，约 {duration_text}，关键词是{tag_text}。今天不是假装努力，是真的往前拱了一截。"
    if quality >= 1.35:
        return f"{label}质量不错，约 {duration_text}。有产出感，不用端着，给自己倒杯水也算合理庆祝。"
    if len(note) < 8:
        return f"{label}已记录，先按 {duration_text} 估算。下次多说一句成果，AI 就能更准地给你算修为。"
    return f"{label}稳定入账，约 {duration_text}。节奏不必太燃，今天这点推进已经算数。"


def _duration_from_text(note: str) -> float | None:
    patterns = (
        (r"(\d+(?:\.\d+)?)\s*(?:小时|个小时|h|hour|hours)", 60.0),
        (r"(\d+(?:\.\d+)?)\s*(?:分钟|分|min|mins|minute|minutes)", 1.0),
    )
    for pattern, multiplier in patterns:
        match = re.search(pattern, note, flags=re.IGNORECASE)
        if match:
            return float(match.group(1)) * multiplier

    chinese_match = re.search(r"([零一二两三四五六七八九十半]+)\s*(?:个)?小时", note)
    if chinese_match:
        return _parse_chinese_number(chinese_match.group(1)) * 60.0

    minute_match = re.search(r"([零一二两三四五六七八九十]+)\s*(?:分钟|分)", note)
    if minute_match:
        return _parse_chinese_number(minute_match.group(1))

    if "半小时" in note:
        return 30.0
    return None


def _parse_chinese_number(text: str) -> float:
    if text == "半":
        return 0.5
    if "十" not in text:
        return float(sum(CHINESE_NUMBERS.get(char, 0) for char in text))

    before, _, after = text.partition("十")
    tens = CHINESE_NUMBERS.get(before, 1) if before else 1
    ones = CHINESE_NUMBERS.get(after, 0) if after else 0
    return float(tens * 10 + ones)


def _dedupe(values: list[str]) -> list[str]:
    seen = set()
    result = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


def _extract_response_text(response: dict[str, Any]) -> str:
    direct = response.get("output_text")
    if isinstance(direct, str):
        return direct.strip()

    parts: list[str] = []
    for item in response.get("output", []):
        if not isinstance(item, dict):
            continue
        for content in item.get("content", []):
            if not isinstance(content, dict):
                continue
            text = content.get("text")
            if isinstance(text, str):
                parts.append(text)
    return "\n".join(parts).strip()


def _strip_json_fence(text: str) -> str:
    clean = text.strip()
    if clean.startswith("```"):
        clean = re.sub(r"^```(?:json)?\s*", "", clean)
        clean = re.sub(r"\s*```$", "", clean)
    return clean.strip()


def _clamp_int(value: Any, lower: int, upper: int, default: int) -> int:
    try:
        parsed = int(round(float(value)))
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(upper, parsed))


def _clamp_float(value: Any, lower: float, upper: float, default: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(lower, min(upper, parsed))


def _normalize_tags(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    tags = []
    for item in value:
        tag = str(item).strip()
        if tag:
            tags.append(tag[:18])
    return _dedupe(tags)[:5]


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, ""))
    except ValueError:
        return default


def analysis_metadata(analysis: ActivityAnalysis, note: str) -> dict:
    return {
        "quality": analysis.quality,
        "note": note,
        "ai_feedback": analysis.feedback,
        "achievement_score": analysis.achievement_score,
        "confidence": analysis.confidence,
        "tags": list(analysis.tags),
        "analysis_source": analysis.source,
    }
