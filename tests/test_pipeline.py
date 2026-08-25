import unittest
from datetime import UTC, datetime

from radar.pipeline import (
    _age_label,
    _company_manifest,
    _is_suspicious_source_drop,
    classify_job,
    classify_job_details,
    classify_program,
    classify_tags,
    normalize_locations,
    validate_data,
)


class ClassifyJobTest(unittest.TestCase):
    def test_title_keyword_has_priority(self) -> None:
        self.assertEqual(classify_job_details("国际化增长产品经理实习生", "产品"), ("产品", "产品经理"))
        self.assertEqual(classify_tags("国际化增长产品经理实习生", "产品"), ["增长", "国际化"])

    def test_raw_category_fallback(self) -> None:
        self.assertEqual(classify_job("创作者生态实习生", "运营"), "内容")

    def test_ascii_short_keyword_uses_boundaries(self) -> None:
        self.assertEqual(classify_job("BD Intern", "销售"), "商务拓展")
        self.assertNotEqual(classify_job("Brand Intern", "市场"), "商务拓展")

    def test_unknown_role_is_rejected(self) -> None:
        self.assertIsNone(classify_job("后端开发工程师", "研发"))

    def test_technical_role_in_nontech_parent_is_rejected(self) -> None:
        self.assertIsNone(classify_job("电商运营数据科学实习生", "运营"))
        self.assertEqual(classify_job("开发者社区运营实习生", "运营"), "运营")

    def test_multi_city_source_text_is_split(self) -> None:
        self.assertEqual(normalize_locations(["深圳总部 北京 / 上海、广州"]), ["深圳", "北京", "上海", "广州"])

    def test_province_city_district_formats_are_normalized(self) -> None:
        self.assertEqual(
            normalize_locations(["北京市-北京市-房山区 / 广东省-深圳市 / 香港特别行政区"]),
            ["北京", "深圳", "中国香港"],
        )

    def test_legitimate_nontech_edge_cases_are_kept(self) -> None:
        cases = {
            "PR实习生": "市场",
            "国际电商数据分析实习生": "数据分析",
            "游戏系统策划实习生": "游戏",
            "产业研究": "战略投资",
            "资质合规管理": "法务合规",
            "动画": "设计",
            "项目实习生-产品": "产品",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify_job(title, ""), expected)

    def test_previously_combined_categories_are_distinct(self) -> None:
        cases = {
            "品牌市场实习生": "市场",
            "用户增长运营实习生": "运营",
            "战略研究实习生": "战略投资",
            "经营分析实习生": "数据分析",
            "渠道销售实习生": "销售",
            "商务拓展实习生": "商务拓展",
            "交互设计实习生": "设计",
            "用户研究实习生": "用户研究",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify_job(title, ""), expected)

    def test_hr_and_trainee_are_separate_dimensions(self) -> None:
        cases = {
            "腾讯营销管培生": "市场",
            "游戏发行运营培训生": "运营",
            "AI-HR培训生（分析方向）": "HR",
        }
        for title, expected in cases.items():
            with self.subTest(title=title):
                self.assertEqual(classify_job(title, ""), expected)
                self.assertEqual(classify_program(title, "校招"), "管培生")

    def test_technical_edge_cases_are_rejected(self) -> None:
        self.assertIsNone(classify_job("UI开发", "设计"))
        self.assertIsNone(classify_job("计算语言学实习生（ASR方向）", "运营"))
        self.assertIsNone(classify_job("资深开发工程师（骑手运营方向）", "运营"))
        self.assertIsNone(classify_job("AI芯片Linux平台软件工程师", "产品"))

    def test_senior_social_roles_are_rejected(self) -> None:
        self.assertIsNone(classify_job("高级产品经理", "产品"))
        self.assertIsNone(classify_job("策略运营专家", "运营"))
        self.assertEqual(classify_job("商务合作主管实习生", "市场"), "商务拓展")

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
            "subcategory": "产品经理",
            "raw_category": "产品",
            "locations": ["北京"],
            "stage": "实习",
            "program": "实习招聘",
            "tags": [],
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

    def test_age_label_collapses_old_official_dates(self) -> None:
        job = {"published_at": "2026-07-01T00:00:00+00:00", "first_seen_at": "2026-07-01T00:00:00+00:00"}
        self.assertEqual(_age_label(job, datetime(2026, 8, 24, tzinfo=UTC)), ">14 天前")

    def test_age_label_does_not_present_discovery_as_publish_time(self) -> None:
        job = {"published_at": "", "first_seen_at": "2026-08-24T00:00:00+00:00"}
        self.assertEqual(_age_label(job), "未知")

    def test_company_manifest_distinguishes_source_states(self) -> None:
        jobs = [{"source": "字节跳动招聘"}]
        manifest = _company_manifest(jobs, {"字节跳动招聘", "腾讯校招"})
        by_source = {row["source"]: row for row in manifest if row["source"] != "待接入官方招聘源"}
        self.assertEqual(by_source["字节跳动招聘"]["status"], "已更新")
        self.assertEqual(by_source["腾讯校招"]["status"], "暂无匹配岗位")
        self.assertEqual(by_source["Momenta招聘"]["status"], "抓取失败")


if __name__ == "__main__":
    unittest.main()
