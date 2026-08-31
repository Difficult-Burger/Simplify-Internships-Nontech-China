import unittest
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from radar.pipeline import (
    _age_label,
    _company_manifest,
    _freshness_label,
    _normalize,
    _reconcile_jobs,
    _source_drop_error,
    _write_job_history,
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
        self.assertIsNone(classify_job("游戏客户端工程师（Unity3D）【2027届】", "游戏"))
        self.assertIsNone(classify_job("游戏服务端工程师【2027届】", "游戏"))
        self.assertIsNone(classify_job("芯片设计工程师-总线方向", "设计类"))
        self.assertIsNone(classify_job("游戏服务器架构开发实习生", "游戏"))
        self.assertIsNone(classify_job("AI应用后端开发实习生 - AI 工具运营", "运营"))
        self.assertIsNone(classify_job("游戏测试实习生（蛋仔派对）", "游戏"))
        self.assertIsNone(classify_job("AI工具开发实习生-内容质量平台", "内容"))
        self.assertIsNone(classify_job("模型运维实习生", "运营"))
        self.assertIsNone(classify_job("嵌入式操作系统项目经理实习生", "项目管理"))
        self.assertEqual(classify_job("开发者社区运营实习生", "运营"), "运营")

    def test_senior_social_roles_are_rejected(self) -> None:
        self.assertIsNone(classify_job("高级产品经理", "产品"))
        self.assertIsNone(classify_job("策略运营专家", "运营"))
        self.assertEqual(classify_job("商务合作主管实习生", "市场"), "商务拓展")

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
            "freshness_basis": "baseline",
            "first_seen_at": "2026-08-24T00:00:00+00:00",
            "last_seen_at": "2026-08-24T01:00:00+00:00",
            "missing_runs": 0,
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

    def test_freshness_labels_distinguish_time_semantics(self) -> None:
        now = datetime(2026, 8, 24, tzinfo=UTC)
        official = {"freshness_basis": "official", "published_at": "2026-08-20T00:00:00+00:00"}
        discovered = {"freshness_basis": "discovered", "first_seen_at": "2026-08-23T00:00:00+00:00"}
        baseline = {"freshness_basis": "baseline", "first_seen_at": "2026-08-24T00:00:00+00:00"}
        self.assertEqual(_freshness_label(official, now), "4d")
        self.assertEqual(_freshness_label(discovered, now), "1d")
        self.assertEqual(_freshness_label(baseline, now), "未知")

    def test_freshness_label_uses_hours_across_midnight(self) -> None:
        job = {"freshness_basis": "official", "published_at": "2026-08-25T14:22:09+00:00"}
        now = datetime(2026, 8, 25, 20, 23, tzinfo=UTC)
        self.assertEqual(_freshness_label(job, now), "6h")

    def test_normalize_preserves_baseline_and_marks_new_discoveries(self) -> None:
        existing = [
            {
                "id": "old",
                "first_seen_at": "2026-08-24T00:00:00+00:00",
                "freshness_basis": "baseline",
            }
        ]
        common = {
            "company": "示例公司",
            "title": "产品经理实习生",
            "raw_category": "产品",
            "locations": ["北京"],
            "stage": "实习",
            "published_at": "",
            "url": "https://example.com/job",
            "source": "示例招聘",
        }
        jobs = _normalize([{**common, "id": "old"}, {**common, "id": "new"}], existing)
        by_id = {job["id"]: job for job in jobs}
        self.assertEqual(by_id["old"]["freshness_basis"], "baseline")
        self.assertEqual(by_id["old"]["first_seen_at"], "2026-08-24T00:00:00+00:00")
        self.assertEqual(by_id["new"]["freshness_basis"], "discovered")

    def test_reappearing_job_uses_permanent_history(self) -> None:
        raw = {
            "id": "restored",
            "company": "示例公司",
            "title": "产品经理实习生",
            "raw_category": "产品",
            "locations": ["北京"],
            "stage": "实习",
            "published_at": "",
            "url": "https://example.com/job",
            "source": "示例招聘",
        }
        history = {
            "restored": {
                "first_seen_at": "2026-08-24T00:00:00+00:00",
                "freshness_basis": "baseline",
            }
        }
        restored = _normalize([raw], [], history)[0]
        self.assertEqual(restored["first_seen_at"], "2026-08-24T00:00:00+00:00")
        self.assertEqual(restored["freshness_basis"], "baseline")

    def test_changed_upstream_id_keeps_url_identity(self) -> None:
        existing = [
            {
                "id": "old-id",
                "url": "https://example.com/stable-job",
                "first_seen_at": "2026-08-24T00:00:00+00:00",
                "freshness_basis": "baseline",
            }
        ]
        raw = {
            "id": "new-id",
            "company": "示例公司",
            "title": "产品经理实习生",
            "raw_category": "产品",
            "locations": ["北京"],
            "stage": "实习",
            "published_at": "",
            "url": "https://example.com/stable-job",
            "source": "示例招聘",
        }
        normalized = _normalize([raw], existing)[0]
        self.assertEqual(normalized["id"], "old-id")
        self.assertEqual(normalized["first_seen_at"], "2026-08-24T00:00:00+00:00")

    def test_missing_job_requires_three_successful_absences(self) -> None:
        job = {
            "id": "bytedance:missing",
            "company": "字节跳动",
            "title": "产品经理实习生",
            "raw_category": "产品",
            "source": "字节跳动招聘",
            "freshness_basis": "baseline",
            "first_seen_at": "2026-08-24T00:00:00+00:00",
            "missing_runs": 0,
        }
        first = _reconcile_jobs([], [job], {"字节跳动招聘"})
        second = _reconcile_jobs([], first, {"字节跳动招聘"})
        third = _reconcile_jobs([], second, {"字节跳动招聘"})
        self.assertEqual(first[0]["missing_runs"], 1)
        self.assertEqual(second[0]["missing_runs"], 2)
        self.assertEqual(third, [])
        failed_run = _reconcile_jobs([], [job], set())
        self.assertEqual(failed_run[0]["missing_runs"], 0)

    def test_source_drop_uses_raw_history_and_three_run_confirmation(self) -> None:
        previous = {"sources": [{"source": "示例招聘", "raw_count": 100, "anomaly_runs": 0}]}
        error, count = _source_drop_error("示例招聘", 40, previous)
        self.assertIsNotNone(error)
        self.assertEqual(count, 1)
        previous["sources"][0]["anomaly_runs"] = 2
        error, count = _source_drop_error("示例招聘", 40, previous)
        self.assertIsNone(error)
        self.assertEqual(count, 0)

    def test_official_time_upgrades_history_basis(self) -> None:
        history = {
            "job": {
                "first_seen_at": "2026-08-24T00:00:00+00:00",
                "freshness_basis": "baseline",
                "url": "https://example.com/job",
            }
        }
        job = {
            "id": "job",
            "first_seen_at": "2026-08-24T00:00:00+00:00",
            "freshness_basis": "official",
            "url": "https://example.com/job",
        }
        with TemporaryDirectory() as directory:
            target = Path(directory) / "history.json"
            with patch("radar.pipeline.JOB_HISTORY_JSON", target):
                _write_job_history(history, [job])
        self.assertEqual(history["job"]["freshness_basis"], "official")

    def test_company_manifest_distinguishes_source_states(self) -> None:
        jobs = [{"source": "字节跳动招聘"}]
        manifest = _company_manifest(jobs, {"字节跳动招聘", "腾讯校招"})
        by_source = {row["source"]: row for row in manifest if row["source"] != "待接入官方招聘源"}
        self.assertEqual(by_source["字节跳动招聘"]["status"], "已更新")
        self.assertEqual(by_source["腾讯校招"]["status"], "暂无匹配岗位")
        self.assertEqual(by_source["Momenta招聘"]["status"], "抓取失败")


if __name__ == "__main__":
    unittest.main()
