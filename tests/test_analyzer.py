from __future__ import annotations

from pathlib import Path
import sys
import unittest


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from cultivation_lab.analyzer import ActivityAnalyzer


class ActivityAnalyzerTest(unittest.TestCase):
    def test_analyzes_chinese_research_note(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze(
            "experiment_run",
            "跑了两个小时 diffusion baseline，定位了 loss 不收敛的问题并写了实验记录",
        )

        self.assertEqual(result.duration_minutes, 120)
        self.assertGreater(result.quality, 1.2)
        self.assertGreater(result.estimated_delta, 30)
        self.assertIn("炉基已成", result.tags)
        self.assertIn("丹炉试炼", result.feedback)
        self.assertNotIn("baseline", result.feedback)
        self.assertNotIn("实验", result.feedback)

    def test_defaults_when_duration_is_missing(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("paper_reading", "读完一篇 arxiv 论文并整理了笔记")

        self.assertEqual(result.duration_minutes, 60)
        self.assertGreater(result.estimated_delta, 8)
        self.assertGreater(result.confidence, 0.5)
        self.assertIn("玉简开悟", result.tags)


if __name__ == "__main__":
    unittest.main()
