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

    def test_defense_preparation_triggers_tribulation(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("writing", "开始筹备毕业答辩，整理答辩稿和问答材料")

        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "雷劫将临")
        self.assertEqual(result.milestone["realm_target"], "渡劫期")
        self.assertEqual(result.milestone["realm_floor_power"], 3000)
        self.assertGreaterEqual(result.estimated_delta, 3000)
        self.assertIn("雷劫将临", result.tags)
        self.assertIn("雷劫", result.feedback)

    def test_passed_defense_triggers_great_vehicle(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("meeting", "今天毕业答辩顺利通过")

        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "雷劫已渡")
        self.assertEqual(result.milestone["realm_target"], "大乘期")
        self.assertEqual(result.milestone["realm_floor_power"], 5000)
        self.assertGreaterEqual(result.estimated_delta, 5000)
        self.assertIn("大乘初成", result.tags)

    def test_phd_defense_passed_triggers_ascension(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("meeting", "今天博士毕业答辩顺利通过", track="phd")

        self.assertEqual(result.track, "phd")
        self.assertEqual(result.track_years, 4.0)
        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "天门大开")
        self.assertEqual(result.milestone["realm_target"], "飞升期")
        self.assertEqual(result.milestone["realm_floor_power"], 8000)
        self.assertGreaterEqual(result.estimated_delta, 8000)

    def test_direct_phd_defense_has_long_pathwording(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("meeting", "今天毕业答辩顺利通过", track="direct_phd")

        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "长阶飞升")
        self.assertEqual(result.milestone["realm_target"], "飞升期")
        self.assertEqual(result.milestone["realm_floor_power"], 8000)

    def test_master_phd_master_defense_is_front_tribulation(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("meeting", "硕士毕业答辩顺利通过", track="master_phd")

        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "前劫已渡")
        self.assertEqual(result.milestone["realm_target"], "渡劫期")
        self.assertEqual(result.milestone["realm_floor_power"], 3000)

    def test_master_phd_final_defense_triggers_ascension(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("meeting", "博士毕业答辩顺利通过", track="master_phd")

        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "双劫尽渡")
        self.assertEqual(result.milestone["realm_target"], "飞升期")
        self.assertEqual(result.milestone["realm_floor_power"], 8000)

    def test_breakthrough_gets_insight_bonus(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("debugging", "卡了很久的关键问题今天终于想通并突破", track_years=2)

        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "有所悟")
        self.assertGreaterEqual(result.milestone["bonus_power"], 420)
        self.assertEqual(result.milestone["bonus_power"], 420)
        self.assertEqual(result.milestone["year_factor"], 1.0)
        self.assertIn("有所悟", result.tags)

    def test_standard_years_scale_long_term_milestones(self) -> None:
        analyzer = ActivityAnalyzer(use_remote=False)

        result = analyzer.analyze("writing", "博士论文录用", track="phd", track_years=3)

        self.assertEqual(result.track_years, 3.0)
        self.assertIsNotNone(result.milestone)
        self.assertEqual(result.milestone["title"], "仙门赐符")
        self.assertEqual(result.milestone["base_bonus_power"], 1800)
        self.assertEqual(result.milestone["bonus_power"], 2070)
        self.assertEqual(result.milestone["year_factor"], 1.15)


if __name__ == "__main__":
    unittest.main()
