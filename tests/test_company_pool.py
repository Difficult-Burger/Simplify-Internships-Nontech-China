import unittest

from radar.company_pool import APPROVED_COMPANIES, EXCLUDED_COMPANIES, PENDING_COMPANIES, JobProCompany
from radar.job_pro_sources import _normalize


class CompanyPoolTest(unittest.TestCase):
    def test_approved_and_excluded_company_names_do_not_overlap(self) -> None:
        approved = {company.company for company in APPROVED_COMPANIES} | set(PENDING_COMPANIES)
        excluded = {name for names in EXCLUDED_COMPANIES.values() for name in names}
        self.assertFalse(approved & excluded)

    def test_pending_company_names_are_unique(self) -> None:
        self.assertEqual(len(PENDING_COMPANIES), len(set(PENDING_COMPANIES)))

    def test_social_source_keeps_only_explicit_early_career_roles(self) -> None:
        company = JobProCompany("example", "示例公司", "示例招聘", ("example.com",), ("all",), True)
        senior = {
            "post_id": "1",
            "title": "高级产品经理",
            "recruit_label": "全职",
            "apply_url": "https://example.com/1",
        }
        intern = {
            "post_id": "2",
            "title": "产品实习生",
            "recruit_label": "实习",
            "apply_url": "https://example.com/2",
        }
        self.assertIsNone(_normalize(company, senior))
        self.assertEqual(_normalize(company, intern)["stage"], "实习")


if __name__ == "__main__":
    unittest.main()
