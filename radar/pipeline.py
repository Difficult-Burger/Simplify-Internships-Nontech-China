"""Classification, persistence and static artifact generation."""

import csv
import html
import json
import re
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from radar.company_pool import APPROVED_COMPANIES, PENDING_COMPANIES
from radar.config import (
    CATEGORIES,
    CLASSIFICATION_RULES,
    EARLY_CAREER_TITLE_KEYWORDS,
    JOB_TAG_KEYWORDS,
    RAW_CATEGORY_DEFAULTS,
    SENIOR_TITLE_KEYWORDS,
    TECHNICAL_RAW_CATEGORY_KEYWORDS,
    TECHNICAL_TITLE_KEYWORDS,
)
from radar.job_pro_sources import fetch_approved_companies
from radar.sources import (
    fetch_bytedance,
    fetch_lilith,
    fetch_momenta,
    fetch_moonton,
    fetch_papegames,
    fetch_sensetime,
    fetch_tencent,
)

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
    "subcategory",
    "raw_category",
    "locations",
    "stage",
    "program",
    "tags",
    "published_at",
    "freshness_basis",
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
    "莉莉丝招聘": {"company": "莉莉丝", "hosts": ("lilithgames.jobs.feishu.cn",)},
    "叠纸游戏招聘": {"company": "叠纸游戏", "hosts": ("career.papegames.com",)},
    "沐瞳科技招聘": {"company": "沐瞳科技", "hosts": ("moonton.jobs.feishu.cn",)},
    **{company.source: {"company": company.company, "hosts": company.hosts} for company in APPROVED_COMPANIES},
}
MONITORED_COMPANIES = [
    {"company": "字节跳动", "source": "字节跳动招聘"},
    {"company": "腾讯", "source": "腾讯校招"},
    {"company": "Momenta", "source": "Momenta招聘"},
    {"company": "商汤", "source": "商汤招聘"},
    {"company": "莉莉丝", "source": "莉莉丝招聘"},
    {"company": "叠纸游戏", "source": "叠纸游戏招聘"},
    {"company": "沐瞳科技", "source": "沐瞳科技招聘"},
    *[{"company": company.company, "source": company.source} for company in APPROVED_COMPANIES],
]
VALID_STAGES = {"实习", "校招"}
VALID_FRESHNESS_BASES = {"official", "discovered", "baseline"}


def _now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def _contains(text: str, keyword: str) -> bool:
    if keyword.isascii() and len(keyword) <= 3:
        return bool(re.search(rf"(?<![a-z0-9]){re.escape(keyword)}(?![a-z0-9])", text))
    return keyword in text


def classify_job(title: str, raw_category: str) -> str | None:
    """Map an official title/category to one public non-tech category."""
    details = classify_job_details(title, raw_category)
    return details[0] if details else None


def classify_job_details(title: str, raw_category: str) -> tuple[str, str] | None:
    """Return the public first-level category and second-level direction."""
    title_text = title.casefold()
    raw_text = raw_category.casefold()
    if any(keyword.casefold() in title_text for keyword in TECHNICAL_TITLE_KEYWORDS):
        return None
    if any(keyword.casefold() in raw_text for keyword in TECHNICAL_RAW_CATEGORY_KEYWORDS):
        return None
    has_senior_title = any(keyword.casefold() in title_text for keyword in SENIOR_TITLE_KEYWORDS)
    has_early_career_title = any(keyword.casefold() in title_text for keyword in EARLY_CAREER_TITLE_KEYWORDS) or bool(
        re.search(r"20\d{2}届", title_text)
    )
    if has_senior_title and not has_early_career_title:
        return None
    for category, subcategory, keywords in CLASSIFICATION_RULES:
        if any(_contains(title_text, keyword.casefold()) for keyword in keywords):
            return category, subcategory
    for category, subcategory, keywords in CLASSIFICATION_RULES:
        if any(_contains(raw_text, keyword.casefold()) for keyword in keywords):
            return category, subcategory
    return next(
        ((category, subcategory) for token, category, subcategory in RAW_CATEGORY_DEFAULTS if token in raw_category),
        None,
    )


def classify_program(title: str, stage: str) -> str:
    text = title.casefold()
    if any(keyword in text for keyword in ("管培生", "培训生", "management trainee", "graduate trainee")):
        return "管培生"
    if any(keyword in text for keyword in ("青云", "专项", "seed", "byteintern", "人才计划")):
        return "人才专项"
    return "实习招聘" if stage == "实习" else "校园招聘"


def classify_tags(title: str, raw_category: str) -> list[str]:
    text = f"{title} {raw_category}".casefold()
    return [
        tag
        for tag, keywords in JOB_TAG_KEYWORDS.items()
        if any(_contains(text, keyword.casefold()) for keyword in keywords)
    ]


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
        title = str(raw.get("title", ""))
        raw_category = str(raw.get("raw_category", ""))
        details = classify_job_details(title, raw_category)
        if not details:
            continue
        category, subcategory = details
        job_id = str(raw["id"])
        previous = old_by_id.get(job_id, {})
        freshness_basis = "official" if raw.get("published_at") else previous.get("freshness_basis", "discovered")
        normalized[job_id] = {
            **raw,
            "category": category,
            "subcategory": subcategory,
            "program": classify_program(title, str(raw.get("stage", ""))),
            "tags": classify_tags(title, raw_category),
            "locations": normalize_locations(raw.get("locations") or []),
            "freshness_basis": freshness_basis,
            "first_seen_at": previous.get("first_seen_at", now),
            "last_seen_at": now,
        }
    return sorted(
        normalized.values(),
        key=lambda job: (_freshness_timestamp(job), job["company"], job["title"]),
        reverse=True,
    )


def _freshness_timestamp(job: dict[str, Any]) -> str:
    if job.get("freshness_basis") == "baseline":
        return ""
    return str(job.get("published_at") or job.get("first_seen_at") or "")


def _write_json(path: Path, jobs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(jobs, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _company_manifest(jobs: list[dict[str, Any]], successful_sources: set[str] | None) -> list[dict[str, str]]:
    existing: dict[str, dict[str, str]] = {}
    if COMPANIES_JSON.exists():
        with COMPANIES_JSON.open(encoding="utf-8") as file:
            existing = {row["source"]: row for row in json.load(file) if row.get("source")}
    counts = {source: sum(job.get("source") == source for job in jobs) for source in SOURCE_RULES}
    checked_at = _now()
    manifest: list[dict[str, str]] = []
    for company in MONITORED_COMPANIES:
        source = company["source"]
        previous = existing.get(source, {})
        if successful_sources is None:
            status = previous.get("status") or ("已更新" if counts[source] else "暂无匹配岗位")
            updated_at = previous.get("updated_at", "")
        elif source in successful_sources:
            status = "已更新" if counts[source] else "暂无匹配岗位"
            updated_at = checked_at
        else:
            status = "抓取失败"
            updated_at = previous.get("updated_at", "")
        manifest.append({**company, "status": status, "updated_at": updated_at})
    manifest.extend(
        {
            "company": company,
            "source": "待接入官方招聘源",
            "status": "待接入",
            "updated_at": "",
        }
        for company in PENDING_COMPANIES
    )
    return manifest


def _write_csv_file(path: Path, jobs: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fields = sorted(REQUIRED_FIELDS - {"locations", "tags"}) + ["locations", "tags"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fields, lineterminator="\n")
        writer.writeheader()
        for job in jobs:
            writer.writerow({**job, "locations": " | ".join(job["locations"]), "tags": " | ".join(job["tags"])})


def _age_label(job: dict[str, Any], now: datetime | None = None) -> str:
    if not job.get("published_at"):
        return "未知"
    reference = now or datetime.now(UTC)
    posted = datetime.fromisoformat(str(job["published_at"]))
    days = max(0, (reference - posted).days)
    if days == 0:
        return "今天"
    return ">14 天前" if days > 14 else f"{days} 天前"


def _freshness_label(job: dict[str, Any], now: datetime | None = None) -> str:
    basis = job.get("freshness_basis")
    if basis == "baseline":
        return "存量岗位"
    value = job.get("published_at") if basis == "official" else job.get("first_seen_at")
    if not value:
        return "存量岗位"
    reference = now or datetime.now(UTC)
    days = max(0, (reference - datetime.fromisoformat(str(value))).days)
    age = "今天" if days == 0 else (">14 天前" if days > 14 else f"{days} 天前")
    return f"发布于 {age}" if basis == "official" else f"新收录 {age}"


def _readme_table(jobs: list[dict[str, Any]]) -> str:
    rows = ["| 公司 | 岗位 | 城市 | 新鲜度 | 投递链接 |", "|---|---|---|---|---|"]
    for job in jobs:
        values = [
            job["company"],
            f"{job['title']} · {job['stage']}",
            " / ".join(job["locations"]),
            _freshness_label(job),
        ]
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
        "> `发布于` 使用企业官方时间；`新收录` 是本项目首次发现时间；首批批量导入显示为`存量岗位`。\n\n"
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
        if not job.get("subcategory"):
            errors.append(f"第 {index + 1} 条岗位方向为空")
        if job.get("stage") not in VALID_STAGES:
            errors.append(f"第 {index + 1} 条招聘类型无效: {job.get('stage')}")
        if not isinstance(job.get("tags"), list):
            errors.append(f"第 {index + 1} 条岗位标签格式无效")
        if job.get("freshness_basis") not in VALID_FRESHNESS_BASES:
            errors.append(f"第 {index + 1} 条新鲜度依据无效: {job.get('freshness_basis')}")
        if job.get("published_at") and job.get("freshness_basis") != "official":
            errors.append(f"第 {index + 1} 条有官方时间但新鲜度依据不是 official")
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


def build_outputs(jobs: list[dict[str, Any]] | None = None, successful_sources: set[str] | None = None) -> None:
    jobs = _load_jobs() if jobs is None else jobs
    rebuilt: list[dict[str, Any]] = []
    for job in jobs:
        if job.get("source") not in SOURCE_RULES:
            continue
        title = str(job.get("title", ""))
        raw_category = str(job.get("raw_category", ""))
        details = classify_job_details(title, raw_category)
        if not details:
            continue
        category, subcategory = details
        freshness_basis = job.get("freshness_basis")
        if freshness_basis not in VALID_FRESHNESS_BASES:
            freshness_basis = "official" if job.get("published_at") else "baseline"
        rebuilt.append(
            {
                **job,
                "category": category,
                "subcategory": subcategory,
                "program": classify_program(title, str(job.get("stage", ""))),
                "tags": classify_tags(title, raw_category),
                "freshness_basis": freshness_basis,
                "locations": normalize_locations(job.get("locations") or []),
            }
        )
    jobs = sorted(
        rebuilt,
        key=lambda job: (_freshness_timestamp(job), job["company"], job["title"]),
        reverse=True,
    )
    validate_data(jobs)
    _write_json(JOBS_JSON, jobs)
    _write_json(SITE_JSON, jobs)
    companies = _company_manifest(jobs, successful_sources)
    _write_json(COMPANIES_JSON, companies)
    _write_json(SITE_COMPANIES_JSON, companies)
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
        ("莉莉丝", "莉莉丝招聘", fetch_lilith),
        ("叠纸游戏", "叠纸游戏招聘", fetch_papegames),
        ("沐瞳科技", "沐瞳科技招聘", fetch_moonton),
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
            key=lambda job: (_freshness_timestamp(job), job["company"], job["title"]),
            reverse=True,
        )
    build_outputs(jobs, successful_sources)
    if failures:
        print("部分数据源失败；成功来源已更新，失败来源不会被伪装为最新数据。")
