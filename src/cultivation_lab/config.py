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
    (5000.0, "飞升期"),
)

DECAY_RATE_PER_DAY = 0.03
HEART_DEMON_BROWSING_HOURS = 2.0
HEART_DEMON_FRAGMENTATION = 12.0
