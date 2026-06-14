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

XIANXIA_TAGS = {
    "完成": "一诀功成",
    "写完": "道卷落笔",
    "跑通": "炉火贯通",
    "复现": "古法重现",
    "baseline": "炉基已成",
    "收敛": "灵息归元",
    "优化": "淬炼精进",
    "修复": "补全天机",
    "定位": "窥见阵眼",
    "总结": "凝练心得",
    "投稿": "投递仙门",
    "实验记录": "丹录成册",
    "读完": "玉简尽览",
    "笔记": "灵纹留痕",
    "figure": "灵图显影",
    "表格": "阵图归位",
    "ablation": "拆阵验法",
    "卡住": "关隘未破",
    "没进展": "灵机未显",
    "刷": "心猿扰动",
    "乱看": "杂念入海",
    "分心": "道心浮动",
    "拖延": "尘缘牵缠",
    "失败": "炉火失衡",
    "描述清楚": "脉络分明",
    "细节充足": "灵纹充盈",
}

EVENT_TAGS = {
    "coding": "符阵成形",
    "paper_reading": "玉简开悟",
    "experiment_run": "丹炉有应",
    "writing": "道卷添章",
    "debugging": "阵眼已现",
    "meeting": "同门印证",
    "browsing": "心猿外驰",
    "idle": "神游未归",
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
    milestone: dict[str, Any] | None = None
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
            "milestone": self.milestone,
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
        base_delta = round(weight * (duration_minutes / 60.0) * quality, 2)
        milestone = detect_milestone(clean_note, event_type)
        estimated_delta = apply_milestone_delta(base_delta, milestone)
        cultivation_tags = xianxia_tags(tags, event_type, estimated_delta)
        if milestone:
            cultivation_tags = _dedupe(list(milestone.get("tags", [])) + cultivation_tags)[:5]
        achievement_score = round(max(-100, min(100, estimated_delta * 4)))
        confidence = round(min(0.96, 0.48 + duration_confidence + min(0.24, len(clean_note) / 180)), 2)
        if milestone:
            feedback = str(milestone["feedback"])
            confidence = max(confidence, float(milestone.get("confidence", 0.88)))
        else:
            feedback = relaxed_feedback(
                event_type=event_type,
                duration_minutes=duration_minutes,
                quality=quality,
                estimated_delta=estimated_delta,
                tags=cultivation_tags,
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
            tags=tuple(cultivation_tags),
            feedback=feedback,
            milestone=milestone,
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
                        "你是 Cultivation Lab 的修仙判官。"
                        "根据用户对一次现实修炼行为的自然语言描述，估算投入时长、质量、成果标签和修仙评语。"
                        "所有可见文案必须完全是修仙语体。"
                        "feedback 和 tags 禁止出现论文、实验、代码、baseline、loss、debug、科研、读研等现实词。"
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
                        "tags 必须像“玉简开悟”“丹炉有应”“道心浮动”这样的修仙词。"
                        "feedback 要像宗门长老评点弟子修行，不要像导师点评研究生。"
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
        base_delta = round(WEIGHTS.get(event_type, 0.0) * (duration_minutes / 60.0) * quality, 2)
        milestone = detect_milestone(note, event_type)
        estimated_delta = apply_milestone_delta(base_delta, milestone)
        tags = xianxia_tags(_normalize_tags(parsed.get("tags")), event_type, estimated_delta)
        if milestone:
            tags = _dedupe(list(milestone.get("tags", [])) + tags)[:5]
        feedback = str(parsed.get("feedback") or "").strip()
        if milestone:
            feedback = str(milestone["feedback"])
        if not feedback:
            feedback = relaxed_feedback(event_type, duration_minutes, quality, estimated_delta, tags, note)
        achievement_score = _clamp_int(
            parsed.get("achievement_score"),
            -100,
            100,
            round(max(-100, min(100, estimated_delta * 4))),
        )
        confidence = round(_clamp_float(parsed.get("confidence"), 0.0, 1.0, 0.72), 2)
        if milestone:
            achievement_score = max(achievement_score, int(milestone.get("achievement_score", 100)))
            confidence = max(confidence, float(milestone.get("confidence", 0.9)))

        return ActivityAnalysis(
            event_type=event_type,
            label=label,
            duration_minutes=duration_minutes,
            quality=round(quality, 2),
            estimated_delta=estimated_delta,
            achievement_score=achievement_score,
            confidence=round(confidence, 2),
            tags=tuple(tags),
            feedback=feedback,
            milestone=milestone,
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


def detect_milestone(note: str, event_type: str) -> dict[str, Any] | None:
    clean = " ".join((note or "").strip().split())
    lower = clean.lower()
    if not clean:
        return None

    has_defense = _has_any(lower, ("答辩", "defense", "viva"))
    defense_passed = (
        has_defense
        and (
            _has_any(lower, ("通过", "过了", "passed"))
            or re.search(r"(答辩|defense|viva).{0,8}(完成|结束|顺利)", lower) is not None
        )
    )
    if defense_passed:
        return _milestone(
            key="defense_passed",
            title="雷劫已渡",
            description="劫云散尽，法身无损，已踏入大乘门槛。",
            bonus_power=2200,
            realm_target="大乘期",
            realm_floor_power=5000,
            tags=("雷劫已渡", "大乘初成", "天门近启"),
            feedback="劫雷既散，元神归位。此番关隘已破，法身入大乘之门，余下只待温养圆满。",
            confidence=0.94,
        )
    if has_defense:
        return _milestone(
            key="defense_started",
            title="雷劫将临",
            description="劫云已聚，道场将启，境界稳入渡劫门前。",
            bonus_power=1200,
            realm_target="渡劫期",
            realm_floor_power=3000,
            tags=("雷劫将临", "劫云压顶", "道心凝定"),
            feedback="雷劫之云已在天穹聚合，道场将开。此事非寻常功课，可直入渡劫之境，宜稳住道心备迎天雷。",
            confidence=0.92,
        )

    thesis_terms = (
        "提交学位论文",
        "毕业论文提交",
        "提交毕业论文",
        "学位论文提交",
        "thesis submitted",
        "dissertation submitted",
    )
    if _has_any(lower, thesis_terms):
        return _milestone(
            key="thesis_submitted",
            title="渡劫书成",
            description="本命道卷已呈宗门，天雷之期近在眼前。",
            bonus_power=1400,
            realm_target="渡劫期",
            realm_floor_power=3000,
            tags=("渡劫书成", "宗门验卷", "劫期将至"),
            feedback="本命道卷已呈宗门，千日灵纹汇作一章。此为渡劫前的大成节点，气海当有骤涨之象。",
            confidence=0.91,
        )

    paper_terms = ("论文", "paper", "稿件", "投稿", "会议", "期刊", "journal", "conference", "manuscript")
    accepted_terms = ("录用", "接收", "中稿", "命中", "accept", "accepted")
    if _has_any(lower, accepted_terms) and _has_any(lower, paper_terms):
        return _milestone(
            key="paper_accepted",
            title="仙门赐符",
            description="外门金榜有名，道法已得仙门印证。",
            bonus_power=1200,
            realm_target="化神期",
            realm_floor_power=1500,
            tags=("仙门赐符", "金榜有名", "道法印证"),
            feedback="仙门赐符，金榜留名。此番道法已得外界印证，神识暴涨，足以稳住化神门庭。",
            confidence=0.9,
        )

    submit_terms = ("投稿", "提交", "submit", "submitted", "arxiv", "openreview", "投出去")
    if _has_any(lower, submit_terms) and _has_any(lower, paper_terms):
        return _milestone(
            key="paper_submitted",
            title="叩问仙门",
            description="道卷已出洞府，向山门递上第一道符。",
            bonus_power=620,
            realm_target="元婴期",
            realm_floor_power=800,
            tags=("叩问仙门", "道卷出山", "灵符已递"),
            feedback="道卷已离洞府，叩问仙门。此举虽未定成败，却已跨过闭门独修之关，元婴灵机可由此凝实。",
            confidence=0.86,
        )

    proposal_passed = "开题" in clean and _has_any(lower, ("通过", "过了", "完成", "passed"))
    if proposal_passed:
        return _milestone(
            key="proposal_passed",
            title="筑坛立誓",
            description="道途初定，命灯已悬，金丹之基由此成形。",
            bonus_power=260,
            realm_target="金丹期",
            realm_floor_power=300,
            tags=("筑坛立誓", "金丹有影", "道途初定"),
            feedback="命灯已悬，道途初定。此关一过，散乱灵机开始结丹，往后可循此脉络稳步炼化。",
            confidence=0.86,
        )
    if "开题" in clean:
        return _milestone(
            key="proposal_started",
            title="立道基",
            description="初开山门，择定一条可长期温养的道脉。",
            bonus_power=120,
            realm_target="筑基期",
            realm_floor_power=100,
            tags=("立道基", "择脉开山", "根骨渐稳"),
            feedback="山门初开，道脉已有雏形。此非一日小功，而是筑基之始，宜把灵机收束成可久修之法。",
            confidence=0.8,
        )

    done_terms = ("定稿", "终稿", "camera-ready", "返修完成", "rebuttal完成", "rebuttal finished")
    if _has_any(lower, done_terms):
        return _milestone(
            key="manuscript_finalized",
            title="道卷定形",
            description="散乱灵纹归于一册，元婴之相更加稳固。",
            bonus_power=700,
            realm_target="元婴期",
            realm_floor_power=800,
            tags=("道卷定形", "灵纹归册", "元婴渐稳"),
            feedback="道卷定形，灵纹归册。此前零散火候今日并作一炉，气脉自然比寻常书写更为充沛。",
            confidence=0.84,
        )

    breakthrough_terms = (
        "突破",
        "顿悟",
        "想通",
        "解决关键",
        "关键问题",
        "瓶颈",
        "找到原因",
        "aha",
        "insight",
        "breakthrough",
    )
    if _has_any(lower, breakthrough_terms):
        return _milestone(
            key="breakthrough",
            title="有所悟",
            description="一线灵光贯穿关隘，瓶颈已有松动。",
            bonus_power=420,
            realm_target=None,
            realm_floor_power=None,
            tags=("有所悟", "瓶颈初破", "灵台大明"),
            feedback="一线灵光贯穿泥丸宫，旧日关隘已有裂纹。此乃真悟，不必拘泥时辰，灵力当按大功记入。",
            confidence=0.84,
        )

    insight_terms = ("有所感", "悟到", "明白了", "理解了", "理清", "思路清楚", "有点理解")
    if _has_any(lower, insight_terms):
        return _milestone(
            key="insight",
            title="有所感",
            description="心湖微明，已有可继续温养的灵机。",
            bonus_power=120,
            realm_target=None,
            realm_floor_power=None,
            tags=("有所感", "心湖微明", "灵机可养"),
            feedback="心湖微明，灵机初现。此类感应虽未成雷霆，却能滋养后续关窍，宜趁热写入玉简。",
            confidence=0.78,
        )

    return None


def apply_milestone_delta(base_delta: float, milestone: dict[str, Any] | None) -> float:
    if not milestone:
        return base_delta
    total = base_delta + float(milestone.get("bonus_power") or 0)
    floor = milestone.get("realm_floor_power")
    if floor is not None:
        total = max(total, float(floor))
    return round(total, 2)


def _milestone(
    *,
    key: str,
    title: str,
    description: str,
    bonus_power: float,
    realm_target: str | None,
    realm_floor_power: float | None,
    tags: tuple[str, ...],
    feedback: str,
    confidence: float,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "key": key,
        "title": title,
        "description": description,
        "bonus_power": float(bonus_power),
        "tags": list(tags),
        "feedback": feedback,
        "achievement_score": 100,
        "confidence": confidence,
    }
    if realm_target:
        payload["realm_target"] = realm_target
    if realm_floor_power is not None:
        payload["realm_floor_power"] = float(realm_floor_power)
    return payload


def _has_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(needle.lower() in text for needle in needles)


def relaxed_feedback(
    event_type: str,
    duration_minutes: int,
    quality: float,
    estimated_delta: float,
    tags: list[str],
    note: str,
) -> str:
    label = EVENT_LABELS.get(event_type, event_type)
    duration_text = cultivation_duration_text(duration_minutes)
    tag_text = "、".join(tags[:2]) if tags else EVENT_TAGS.get(event_type, "灵机微动")

    if event_type in {"browsing", "idle"} or estimated_delta < 0:
        return f"{label}约 {duration_text}，心猿离座，灵息外散。速归蒲团，闭目调息，莫让杂念侵蚀道基。"
    if estimated_delta >= 28:
        return f"{label}约 {duration_text}，{tag_text}，灵台大明。此番火候已至，可记入今日上乘功课。"
    if quality >= 1.35:
        return f"{label}约 {duration_text}，{tag_text}，气脉运行颇顺。若能趁热温养，破境之机可再添一线。"
    if len(note) < 8:
        return f"{label}约 {duration_text}，玉简所载尚略。此番先记小功一笔，来日当详述灵机所得。"
    return f"{label}约 {duration_text}，{tag_text}。虽非雷劫大成，亦是道基添砖，灵力缓缓归海。"


def cultivation_duration_text(duration_minutes: int) -> str:
    if duration_minutes == 15:
        return "一炷香"
    if duration_minutes < 120 and duration_minutes % 15 == 0:
        return f"{duration_minutes // 15} 刻"
    if duration_minutes >= 120:
        shichen = duration_minutes / 120.0
        if duration_minutes % 120 == 0:
            return f"{int(shichen)} 个时辰"
        return f"约 {shichen:.1f} 个时辰"
    return f"约 {duration_minutes} 分"


def _duration_from_text(note: str) -> float | None:
    patterns = (
        (r"(\d+(?:\.\d+)?)\s*(?:时辰)", 120.0),
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

    shichen_match = re.search(r"([零一二两三四五六七八九十半]+)\s*时辰", note)
    if shichen_match:
        return _parse_chinese_number(shichen_match.group(1)) * 120.0

    minute_match = re.search(r"([零一二两三四五六七八九十]+)\s*(?:分钟|分)", note)
    if minute_match:
        return _parse_chinese_number(minute_match.group(1))

    if "一炷香" in note:
        return 15.0
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


def xianxia_tags(tags: list[str], event_type: str, estimated_delta: float) -> list[str]:
    translated = [XIANXIA_TAGS.get(tag, tag) for tag in tags]
    translated.insert(0, EVENT_TAGS.get(event_type, "灵机微动"))
    if estimated_delta >= 28:
        translated.append("灵压大涨")
    elif estimated_delta > 0:
        translated.append("道基微增")
    elif estimated_delta < 0:
        translated.append("魔念侵心")
    return _dedupe(translated)[:5]


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
    metadata = {
        "quality": analysis.quality,
        "note": note,
        "ai_feedback": analysis.feedback,
        "achievement_score": analysis.achievement_score,
        "confidence": analysis.confidence,
        "tags": list(analysis.tags),
        "analysis_source": analysis.source,
    }
    if analysis.milestone:
        milestone = analysis.milestone
        metadata["milestone"] = milestone
        metadata["milestone_key"] = milestone.get("key")
        metadata["milestone_title"] = milestone.get("title")
        metadata["bonus_power"] = milestone.get("bonus_power", 0)
        if milestone.get("realm_target"):
            metadata["realm_target"] = milestone.get("realm_target")
        if milestone.get("realm_floor_power") is not None:
            metadata["realm_floor_power"] = milestone.get("realm_floor_power")
    return metadata
