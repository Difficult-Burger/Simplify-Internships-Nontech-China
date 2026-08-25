"""Classification, persistence and static artifact generation."""

import csv
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from radar.company_pool import APPROVED_COMPANIES
from radar.config import CATEGORIES, CATEGORY_KEYWORDS, TECHNICAL_TITLE_KEYWORDS
from radar.job_pro_sources import fetch_approved_companies
from radar.sources import fetch_bytedance, fetch_momenta, fetch_sensetime, fetch_tencent

ROOT = Path(__file__).resolve().parent.parent
JOBS_JSON = ROOT / "data" / "jobs.json"
JOBS_CSV = ROOT / "data" / "jobs.csv"
SITE_JSON = ROOT / "docs" / "jobs.json"
SITE_CSV = ROOT / "docs" / "jobs.csv"
COMPANIES_JSON = ROOT / "data" / "companies.json"
SITE_COMPANIES_JSON = ROOT / "docs" / "companies.json"
README = ROOT / "README.md"
REQUIRED_FIELDS = {
    "id",
    "company",
    "title",
    "category",
    "raw_category",
    "locations",
    "stage",
    "published_at",
    "first_seen_at",
    "last_seen_at",
    "url",
    "source",
}
SOURCE_RULES = {
    "字节跳动招聘": {"company": "字节跳动", "hosts": ("jobs.bytedance.com",)},
    "腾讯校招": {"company": "腾讯", "hosts": ("join.qq.com",)},
    "Momenta招聘": {"company": "Momenta", "hosts": ("momenta.jobs.feishu.cn",)},
    "商汤招聘": {"company": "商汤", "hosts": ("hr-jobs.sensetime.com",)},
    **{company.source: {"company": company.company, "hosts": company.hosts} for company in APPROVED_COMPANIES},
}
MONITORED_COMPANIES = [
    {"company": "字节跳动", "source": "字节跳动招聘"},
    {"company": "腾讯", "source": "腾讯校招"},
    {"company": "Momenta", "source": "Momenta招聘"},
    {"company": "商汤", "source": "商汤招聘"},
    *[{"company": company.company, "source": company.source} for company in APPROVED_COMPANIES],
]
VALID_STAGES = {"实习", "校招"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _contains(text: str, keyword: str) -> bool:
    if keyword.isascii() and len(keyword) <= 3:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text))
    return keyword in text


def classify_job(title: str, raw_category: str) -> str | None:
    """Map an official title/category to one of the public non-tech categories."""
    title_text = title.casefold()
    raw_text = raw_category.casefold()
    if any(keyword in title_text for keyword in TECHNICAL_TITLE_KEYWORDS):
        return None
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(_contains(title_text, keyword.casefold()) for keyword in keywords):
            return category
    for category, keywords in CATEGORY_KEYWORDS.items():
        if any(_contains(raw_text, keyword.casefold()) for keyword in keywords):
            return category

    raw_defaults = {
        "产品": "产品",
        "运营": "运营",
        "数据分析": "商业分析",
        "市场": "市场",
        "PR": "市场",
        "销售": "销售",
        "设计": "设计",
        "策划": "产品",
        "人力": "HR",
        "职能": "职能",
        "内审": "职能",
        "IT支持": "职能",
    }
    return next((category for token, category in raw_defaults.items() if token in raw_category), None)


def normalize_locations(locations: list[str]) -> list[str]:
    """Split source-specific multi-city strings into stable city filters."""
    pieces = [piece for location in locations for piece in re.split(r"[\s/,，、|]+", location) if piece]
    normalized = [_normalize_location_piece(piece) for piece in pieces]
    return list(dict.fromkeys(normalized)) or ["地点未注明"]


def _normalize_location_piece(location: str) -> str:
    location = location.strip()
    aliases = {
        "深圳总部": "深圳",
        "香港": "中国香港",
        "香港特别行政区": "中国香港",
        "中国-香港特别行政区": "中国香港",
        "海淀区": "北京",
        "拱墅区": "杭州",
        "其他": "地点未注明",
        "其它": "地点未注明",
    }
    if location in aliases:
        return aliases[location]
    parts = [part for part in re.split(r"[-·]", location) if part]
    city_parts = [part for part in parts if part.endswith("市")]
    if city_parts:
        location = city_parts[-1]
    elif len(parts) > 1:
        location = parts[-1]
    for municipality in ("北京", "上海", "天津", "重庆"):
        if municipality in location:
            return municipality
    if location.endswith("市"):
        location = location[:-1]
    if location.endswith("特别行政区"):
        location = location.removesuffix("特别行政区")
    if location == "香港":
        return "中国香港"
    if location.endswith("省"):
        location = location[:-1]
    return location or "地点未注明"


def _is_suspicious_source_drop(previous_count: int, current_count: int) -> bool:
    """Protect the published dataset from a likely partial upstream response."""
    return previous_count >= 20 and current_count < previous_count * 0.5


def _load_jobs() -> list[dict[str, Any]]:
    if not JOBS_JSON.exists():
        return []
    with JOBS_JSON.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("data/jobs.json 顶层必须是数组")
    return data


def _normalize(raw_jobs: list[dict[str, Any]], existing: list[dict[str, Any]]) -> list[dict[str, Any]]:
    now = _now()
    old_by_id = {job["id"]: job for job in existing if job.get("id")}
    normalized: dict[str, dict[str, Any]] = {}
    for raw in raw_jobs:
        category = classify_job(str(raw.get("title", "")), str(raw.get("raw_category", "")))
        if not category:
            continue
        job_id = str(raw["id"])
        normalized[job_id] = {
            **raw,
            "category": category,
            "locations": normalize_locations(raw.get("locations") or []),
            "first_seen_at": old_by_id.get(job_id, {}).get("first_seen_at", now),
            "last_seen_at": now,
        }
    return sorted(
        normalized.values(),
        key=lambda job: (job.get("published_at") or job["first_seen_at"], job["company"], job["title"]),
        reverse=True,
    )


def _write_json(path: Path, jobs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_csv_file(path: Path, jobs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(REQUIRED_FIELDS - {"locations"}) + ["locations"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for job in jobs:
            writer.writerow({**job, "locations": " | ".join(job["locations"])})


def _age_label(job: dict[str, Any], now: datetime | None = None) -> str:
    if not job.get("published_at"):
        return "未知"
    reference = now or datetime.now(UTC)
    posted = datetime.fromisoformat(str(job["published_at"]))
    days = max(0, (reference - posted).days)
    return "今天" if days == 0 else f"{days} 天前"


def _readme_table(jobs: list[dict[str, Any]]) -> str:
    rows = ["| 公司 | 岗位 | 城市 | 发布于 | 投递链接 |", "|---|---|---|---|---|"]
    for job in jobs:
        values = [job["company"], f"{job['title']} · {job['stage']}", " / ".join(job["locations"]), _age_label(job)]
        safe = [html.escape(str(value)).replace("|", "\\|").replace("\n", " ") for value in values]
        safe_url = html.escape(str(job["url"]), quote=True)
        rows.append(f"| {' | '.join(safe)} | [投递]({safe_url}) |")
    return "\n".join(rows)


def _readme_sections(jobs: list[dict[str, Any]], per_category: int = 60) -> str:
    sections: list[str] = []
    for index, (category, emoji) in enumerate(CATEGORIES.items(), start=1):
        category_jobs = [job for job in jobs if job["category"] == category][:per_category]
        if not category_jobs:
            continue
        sections.append(
            f'<a id="category-{index}"></a>\n\n## {emoji} 岗位类别：{category}\n\n'
            f"最新展示 {len(category_jobs)} 条。\n\n{_readme_table(category_jobs)}"
        )
    return "\n\n---\n\n".join(sections)


def _update_readme(jobs: list[dict[str, Any]]) -> None:
    content = README.read_text(encoding="utf-8")
    start = "<!-- JOBS_START -->"
    end = "<!-- JOBS_END -->"
    if start not in content or end not in content:
        raise ValueError("README 缺少岗位表更新标记")
    category_counts = {category: sum(job["category"] == category for job in jobs) for category in CATEGORIES}
    links = "\n\n".join(
        f"{emoji} **[{category}](#category-{index})**（{category_counts[category]}）"
        for index, (category, emoji) in enumerate(CATEGORIES.items(), start=1)
    )
    generated = (
        f"\n\n当前收录 **{len(jobs)}** 条在招岗位。\n\n"
        f"### 按岗位类别浏览\n\n{links}\n\n---\n\n"
        f"{_readme_sections(jobs)}\n\n"
        "> `发布于` 使用企业官方发布时间；来源未提供该字段时显示“未知”。\n\n"
    )
    before, remainder = content.split(start, 1)
    _, after = remainder.split(end, 1)
    README.write_text(before + start + generated + end + after, encoding="utf-8")


def validate_data(jobs: list[dict[str, Any]] | None = None) -> None:
    jobs = _load_jobs() if jobs is None else jobs
    seen_ids: set[str] = set()
    seen_urls: set[str] = set()
    errors: list[str] = []
    for index, job in enumerate(jobs):
        missing = REQUIRED_FIELDS - job.keys()
        if missing:
            errors.append(f"第 {index + 1} 条缺少字段: {sorted(missing)}")
        if job.get("category") not in CATEGORIES:
            errors.append(f"第 {index + 1} 条分类无效: {job.get('category')}")
        if job.get("stage") not in VALID_STAGES:
            errors.append(f"第 {index + 1} 条招聘类型无效: {job.get('stage')}")
        source = str(job.get("source", ""))
        source_rule = SOURCE_RULES.get(source)
        if source_rule is None:
            errors.append(f"第 {index + 1} 条来源无效: {source}")
        else:
            if job.get("company") != source_rule["company"]:
                errors.append(f"第 {index + 1} 条公司与来源不匹配: {job.get('company')} / {source}")
            if urlparse(str(job.get("url", ""))).netloc not in source_rule["hosts"]:
                errors.append(f"第 {index + 1} 条申请域名与来源不匹配: {job.get('url')}")
        if not isinstance(job.get("locations"), list) or not all(job.get("locations", [])):
            errors.append(f"第 {index + 1} 条城市格式无效: {job.get('locations')}")
        try:
            first_seen = datetime.fromisoformat(str(job.get("first_seen_at", "")))
            last_seen = datetime.fromisoformat(str(job.get("last_seen_at", "")))
            if first_seen > last_seen:
                errors.append(f"第 {index + 1} 条首次发现晚于最后确认")
            if job.get("published_at"):
                datetime.fromisoformat(str(job["published_at"]))
        except ValueError:
            errors.append(f"第 {index + 1} 条时间格式无效")
        for field, seen in (("id", seen_ids), ("url", seen_urls)):
            value = str(job.get(field, ""))
            if not value:
                errors.append(f"第 {index + 1} 条 {field} 为空")
            elif value in seen:
                errors.append(f"第 {index + 1} 条 {field} 重复: {value}")
            seen.add(value)
    if errors:
        raise ValueError("\n".join(errors))
    print(f"校验通过：{len(jobs)} 个岗位，ID 和官方链接均唯一。")


def build_outputs(jobs: list[dict[str, Any]] | None = None) -> None:
    jobs = _load_jobs() if jobs is None else jobs
    jobs = [
        {**job, "category": category, "locations": normalize_locations(job.get("locations") or [])}
        for job in jobs
        if (category := classify_job(str(job.get("title", "")), str(job.get("raw_category", ""))))
    ]
    validate_data(jobs)
    _write_json(JOBS_JSON, jobs)
    _write_json(SITE_JSON, jobs)
    _write_json(COMPANIES_JSON, MONITORED_COMPANIES)
    _write_json(SITE_COMPANIES_JSON, MONITORED_COMPANIES)
    _write_csv_file(JOBS_CSV, jobs)
    _write_csv_file(SITE_CSV, jobs)
    _update_readme(jobs)
    print(f"已生成 README、JSON、CSV 和静态站点数据：{len(jobs)} 个岗位。")


def fetch_and_build(max_pages: int = 50) -> None:
    existing = _load_jobs()
    raw_jobs: list[dict[str, Any]] = []
    failures: list[str] = []
    successful_sources: set[str] = set()
    sources = (
        ("字节跳动", "字节跳动招聘", fetch_bytedance),
        ("腾讯", "腾讯校招", fetch_tencent),
        ("Momenta", "Momenta招聘", fetch_momenta),
        ("商汤", "商汤招聘", fetch_sensetime),
    )
    for name, source_label, fetcher in sources:
        try:
            source_jobs = fetcher(max_pages=max_pages)
            previous_count = sum(job.get("source") == source_label for job in existing)
            if _is_suspicious_source_drop(previous_count, len(source_jobs)):
                raise RuntimeError(
                    f"{name} 返回量异常下降：上一版 {previous_count} 条，本次 {len(source_jobs)} 条；保留上一版数据"
                )
            raw_jobs.extend(source_jobs)
            successful_sources.add(source_label)
            print(f"{name}：抓取 {len(source_jobs)} 个非技术岗")
        except RuntimeError as error:
            failures.append(str(error))
            print(f"{name}：抓取失败，{error}")

    job_pro_groups, job_pro_failures = fetch_approved_companies(max_pages=max(max_pages, 100))
    failures.extend(job_pro_failures)
    for source_label, source_jobs in job_pro_groups.items():
        previous_count = sum(job.get("source") == source_label for job in existing)
        if _is_suspicious_source_drop(previous_count, len(source_jobs)):
            failures.append(f"{source_label} 返回量异常下降：上一版 {previous_count} 条，本次 {len(source_jobs)} 条")
            continue
        raw_jobs.extend(source_jobs)
        successful_sources.add(source_label)
        print(f"{source_label}：抓取 {len(source_jobs)} 个早期职业岗位")
    for failure in job_pro_failures:
        print(f"扩展公司抓取失败：{failure}")
    if not raw_jobs:
        raise RuntimeError("所有官方数据源均抓取失败；保留已有数据，未覆盖输出。")
    jobs = _normalize(raw_jobs, existing)
    if failures:
        preserved = [
            job for job in existing if job.get("source") not in successful_sources and job.get("source") in SOURCE_RULES
        ]
        jobs = sorted(
            {job["id"]: job for job in [*jobs, *preserved]}.values(),
            key=lambda job: (job.get("published_at") or job["first_seen_at"], job["company"], job["title"]),
            reverse=True,
        )
    build_outputs(jobs)
    if failures:
        print("部分数据源失败；成功来源已更新，失败来源不会被伪装为最新数据。")
