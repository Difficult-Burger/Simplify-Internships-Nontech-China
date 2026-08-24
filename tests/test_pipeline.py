import unittest

from radar.pipeline import classify_job, normalize_locations


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


if __name__ == "__main__":
    unittest.main()
