import unittest
from datetime import UTC, datetime

from radar.pipeline import _age_label, _is_suspicious_source_drop, classify_job, normalize_locations, validate_data


class ClassifyJobTest(unittest.TestCase):
    def test_title_keyword_has_priority(self) -> None:
        self.assertEqual(classify_job("国际化增长产品经理实习生", "产品"), "市场/增长")

    def test_raw_category_fallback(self) -> None:
        self.assertEqual(classify_job("创作者生态实习生", "运营"), "运营")

    def test_ascii_short_keyword_uses_boundaries(self) -> None:
        self.assertEqual(classify_job("BD Intern", "销售"), "销售/商务")
        self.assertNotEqual(classify_job("Brand Intern", "市场"), "销售/商务")

    def test_unknown_role_is_rejected(self) -> None:
        self.assertIsNone(classify_job("后端开发工程师", "研发"))

    def test_technical_role_in_nontech_parent_is_rejected(self) -> None:
        self.assertIsNone(classify_job("电商运营数据科学实习生", "运营"))
        self.assertEqual(classify_job("开发者社区运营实习生", "运营"), "运营")

    def test_multi_city_source_text_is_split(self) -> None:
        self.assertEqual(normalize_locations(["深圳总部 北京 / 上海、广州"]), ["深圳", "北京", "上海", "广州"])

    def test_legitimate_nontech_edge_cases_are_kept(self) -> None:
        cases = {
            "PR实习生": "市场/增长",
            "国际电商数据分析实习生": "战略/商业分析",
            "游戏系统策划实习生": "产品",
            "产业研究": "战略/商业分析",
            "资质合规管理": "职能",
            "动画": "设计/用户研究",
            "项目实习生-产品": "产品",
            "项目实习生-职能": "职能",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify_job(title, ""), expected)

    def test_technical_edge_cases_are_rejected(self) -> None:
        self.assertIsNone(classify_job("UI开发", "设计"))
        self.assertIsNone(classify_job("计算语言学实习生（ASR方向）", "运营"))

    def test_large_source_drop_is_rejected(self) -> None:
        self.assertTrue(_is_suspicious_source_drop(100, 49))
        self.assertFalse(_is_suspicious_source_drop(100, 50))
        self.assertFalse(_is_suspicious_source_drop(10, 0))

    def test_validation_rejects_wrong_official_domain(self) -> None:
        job = {
            "id": "bytedance:1",
            "company": "字节跳动",
            "title": "产品经理实习生",
            "category": "产品",
            "raw_category": "产品",
            "locations": ["北京"],
            "stage": "实习",
            "published_at": "",
            "first_seen_at": "2026-08-24T00:00:00+00:00",
            "last_seen_at": "2026-08-24T01:00:00+00:00",
            "url": "https://example.com/job/1",
            "source": "字节跳动招聘",
        }
        with self.assertRaisesRegex(ValueError, "申请域名与来源不匹配"):
            validate_data([job])

    def test_age_label_prefers_official_publish_time(self) -> None:
        job = {
            "published_at": "2026-08-20T00:00:00+00:00",
            "first_seen_at": "2026-08-24T00:00:00+00:00",
        }
        now = datetime(2026, 8, 24, tzinfo=UTC)
        self.assertEqual(_age_label(job, now), "4 天前")

    def test_age_label_does_not_present_discovery_as_publish_time(self) -> None:
        job = {"published_at": "", "first_seen_at": "2026-08-24T00:00:00+00:00"}
        self.assertEqual(_age_label(job), "时间未公开")


if __name__ == "__main__":
    unittest.main()
