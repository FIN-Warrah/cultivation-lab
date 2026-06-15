from __future__ import annotations

from pathlib import Path


PACKAGE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = PACKAGE_DIR.parents[1]
DATA_DIR = PROJECT_ROOT / "data"
STATIC_DIR = PROJECT_ROOT / "static"
DEFAULT_EVENTS_PATH = DATA_DIR / "events.json"

EVENT_TYPES = (
    "coding",
    "paper_reading",
    "experiment_run",
    "writing",
    "meeting",
    "debugging",
    "browsing",
    "idle",
)

EVENT_LABELS = {
    "coding": "符阵炼器",
    "paper_reading": "玉简参悟",
    "experiment_run": "丹炉试炼",
    "writing": "道卷成章",
    "meeting": "同门论道",
    "debugging": "破阵除障",
    "browsing": "心猿游荡",
    "idle": "神游太虚",
}

ACADEMIC_TRACKS = (
    "master",
    "phd",
    "direct_phd",
    "master_phd",
)

DEFAULT_ACADEMIC_TRACK = "master"

ACADEMIC_TRACK_LABELS = {
    "master": "硕士一程",
    "phd": "博士一程",
    "direct_phd": "直博玄门",
    "master_phd": "硕博连修",
}

DEFAULT_TRACK_YEARS = {
    "master": 3.0,
    "phd": 4.0,
    "direct_phd": 5.0,
    "master_phd": 6.0,
}

ACADEMIC_TRACK_ALIASES = {
    "master_only": "master",
    "masters": "master",
    "硕士": "master",
    "读研": "master",
    "只读研": "master",
    "phd_only": "phd",
    "doctoral": "phd",
    "博士": "phd",
    "只读博": "phd",
    "direct": "direct_phd",
    "directphd": "direct_phd",
    "直博": "direct_phd",
    "combined": "master_phd",
    "master_to_phd": "master_phd",
    "硕博连读": "master_phd",
    "硕博连修": "master_phd",
}

WEIGHTS = {
    "coding": 10.0,
    "paper_reading": 8.0,
    "experiment_run": 15.0,
    "writing": 12.0,
    "debugging": 9.0,
    "meeting": 5.0,
    "browsing": -2.0,
    "idle": -5.0,
}

REALM_THRESHOLDS = (
    (0.0, "炼气期"),
    (100.0, "筑基期"),
    (300.0, "金丹期"),
    (800.0, "元婴期"),
    (1500.0, "化神期"),
    (3000.0, "渡劫期"),
    (5000.0, "大乘期"),
    (8000.0, "飞升期"),
)

DECAY_RATE_PER_DAY = 0.03
HEART_DEMON_BROWSING_HOURS = 2.0
HEART_DEMON_FRAGMENTATION = 12.0


def normalize_academic_track(value: object) -> str:
    raw = str(value or DEFAULT_ACADEMIC_TRACK).strip()
    if raw in ACADEMIC_TRACKS:
        return raw
    compact = raw.lower().replace("-", "_").replace(" ", "_")
    return ACADEMIC_TRACK_ALIASES.get(compact, DEFAULT_ACADEMIC_TRACK)


def academic_track_label(track: object) -> str:
    normalized = normalize_academic_track(track)
    return ACADEMIC_TRACK_LABELS[normalized]


def normalize_track_years(track: object, value: object = None) -> float:
    normalized_track = normalize_academic_track(track)
    default = DEFAULT_TRACK_YEARS[normalized_track]
    if value is None or value == "":
        return default
    try:
        years = float(value)
    except (TypeError, ValueError):
        return default
    years = max(1.0, min(10.0, years))
    return round(years, 1)


def track_year_factor(track: object, value: object = None) -> float:
    normalized_track = normalize_academic_track(track)
    years = normalize_track_years(normalized_track, value)
    factor = DEFAULT_TRACK_YEARS[normalized_track] / years
    return round(max(0.85, min(1.15, factor)), 3)
