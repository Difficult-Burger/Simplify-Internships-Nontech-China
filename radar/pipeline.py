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
    TECHNICAL_TITLE_PATTERNS,
)
from radar.job_pro_sources import fetch_approved_companies
from radar.sources import (
    fetch_bytedance,
    fetch_horizon,
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
JOB_HISTORY_JSON = ROOT / "data" / "job_history.json"
SOURCE_HEALTH_JSON = ROOT / "data" / "source_health.json"
SITE_SOURCE_HEALTH_JSON = ROOT / "docs" / "source_health.json"
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
    "missing_runs",
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
    "地平线招聘": {"company": "地平线", "hosts": ("wecruit.hotjob.cn",)},
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
    {"company": "地平线", "source": "地平线招聘"},
    *[{"company": company.company, "source": company.source} for company in APPROVED_COMPANIES],
]
VALID_STAGES = {"实习", "校招"}
VALID_FRESHNESS_BASES = {"official", "discovered", "baseline"}
MISSING_RUNS_BEFORE_REMOVAL = 3


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
    if any(re.search(pattern, title_text, re.IGNORECASE) for pattern in TECHNICAL_TITLE_PATTERNS):
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


def _load_jobs() -> list[dict[str, Any]]:
    if not JOBS_JSON.exists():
        return []
    with JOBS_JSON.open(encoding="utf-8") as file:
        data = json.load(file)
    if not isinstance(data, list):
        raise ValueError("data/jobs.json 顶层必须是数组")
    return data


def _load_job_history(existing: list[dict[str, Any]]) -> dict[str, dict[str, str]]:
    if JOB_HISTORY_JSON.exists():
        with JOB_HISTORY_JSON.open(encoding="utf-8") as file:
            data = json.load(file)
        if isinstance(data, dict):
            return data
    return {
        job["id"]: {
            "first_seen_at": str(job["first_seen_at"]),
            "freshness_basis": str(job["freshness_basis"]),
            "url": str(job.get("url") or ""),
        }
        for job in existing
        if job.get("id") and job.get("first_seen_at") and job.get("freshness_basis")
    }


def _load_source_health() -> dict[str, Any]:
    if not SOURCE_HEALTH_JSON.exists():
        return {}
    with SOURCE_HEALTH_JSON.open(encoding="utf-8") as file:
        data = json.load(file)
    return data if isinstance(data, dict) else {}


def _normalize(
    raw_jobs: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    history: dict[str, dict[str, str]] | None = None,
) -> list[dict[str, Any]]:
    now = _now()
    old_by_id = {job["id"]: job for job in existing if job.get("id")}
    old_by_url = {job["url"]: job for job in existing if job.get("url")}
    history_by_url = {
        str(item.get("url")): {**item, "id": job_id}
        for job_id, item in (history or {}).items()
        if item.get("url")
    }
    normalized: dict[str, dict[str, Any]] = {}
    for raw in raw_jobs:
        title = str(raw.get("title", ""))
        raw_category = str(raw.get("raw_category", ""))
        details = classify_job_details(title, raw_category)
        if not details:
            continue
        category, subcategory = details
        raw_job_id = str(raw["id"])
        url = str(raw.get("url") or "")
        previous = (
            old_by_id.get(raw_job_id)
            or old_by_url.get(url)
            or (history or {}).get(raw_job_id)
            or history_by_url.get(url)
            or {}
        )
        job_id = str(previous.get("id") or raw_job_id)
        freshness_basis = "official" if raw.get("published_at") else previous.get("freshness_basis", "discovered")
        normalized[job_id] = {
            **raw,
            "id": job_id,
            "category": category,
            "subcategory": subcategory,
            "program": classify_program(title, str(raw.get("stage", ""))),
            "tags": classify_tags(title, raw_category),
            "locations": normalize_locations(raw.get("locations") or []),
            "freshness_basis": freshness_basis,
            "first_seen_at": previous.get("first_seen_at", now),
            "last_seen_at": now,
            "missing_runs": 0,
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


def _reconcile_jobs(
    current: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    successful_sources: set[str],
) -> list[dict[str, Any]]:
    """Keep transiently missing jobs and remove only after three complete successful absences."""
    reconciled = {job["id"]: job for job in current}
    current_urls = {job.get("url") for job in current if job.get("url")}
    for old in existing:
        job_id = str(old.get("id") or "")
        source = str(old.get("source") or "")
        if not job_id or job_id in reconciled or old.get("url") in current_urls or source not in SOURCE_RULES:
            continue
        if not classify_job_details(str(old.get("title", "")), str(old.get("raw_category", ""))):
            continue
        if source not in successful_sources:
            reconciled[job_id] = old
            continue
        missing_runs = int(old.get("missing_runs") or 0) + 1
        if missing_runs < MISSING_RUNS_BEFORE_REMOVAL:
            reconciled[job_id] = {**old, "missing_runs": missing_runs}
    return sorted(
        reconciled.values(),
        key=lambda job: (_freshness_timestamp(job), job["company"], job["title"]),
        reverse=True,
    )


def _write_job_history(history: dict[str, dict[str, str]], jobs: list[dict[str, Any]]) -> None:
    for job in jobs:
        entry = history.setdefault(
            job["id"],
            {
                "first_seen_at": str(job["first_seen_at"]),
                "freshness_basis": str(job["freshness_basis"]),
                "url": str(job.get("url") or ""),
            },
        )
        entry["url"] = str(job.get("url") or "")
        if job.get("freshness_basis") == "official":
            entry["freshness_basis"] = "official"
    JOB_HISTORY_JSON.write_text(json.dumps(history, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


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


def _source_health_by_name(health: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(item.get("source")): item
        for item in health.get("sources", [])
        if isinstance(item, dict) and item.get("source")
    }


def _source_drop_error(
    source: str,
    observed_count: int,
    previous_health: dict[str, Any],
) -> tuple[str | None, int]:
    previous = _source_health_by_name(previous_health).get(source, {})
    previous_count = int(previous.get("raw_count") or 0)
    if previous_count < 20 or observed_count >= previous_count * 0.5:
        return None, 0
    anomaly_runs = int(previous.get("anomaly_runs") or 0) + 1
    if anomaly_runs >= MISSING_RUNS_BEFORE_REMOVAL:
        return None, 0
    return f"原始岗位量异常下降：上一完整快照 {previous_count}，本轮 {observed_count}", anomaly_runs


def _write_source_health(
    successful_sources: set[str],
    source_errors: dict[str, str],
    raw_counts: dict[str, int],
    observed_counts: dict[str, int],
    anomaly_runs: dict[str, int],
    jobs: list[dict[str, Any]],
    previous_health: dict[str, Any],
) -> None:
    previous = _source_health_by_name(previous_health)
    active_counts = {source: sum(job.get("source") == source for job in jobs) for source in SOURCE_RULES}
    sources: list[dict[str, Any]] = []
    for company in MONITORED_COMPANIES:
        source = company["source"]
        prior = previous.get(source, {})
        success = source in successful_sources
        sources.append(
            {
                **company,
                "status": "ok" if success else "failed",
                "error": source_errors.get(source, ""),
                "raw_count": raw_counts.get(source, int(prior.get("raw_count") or 0)),
                "observed_raw_count": observed_counts.get(source, 0),
                "active_count": active_counts.get(source, 0),
                "anomaly_runs": anomaly_runs.get(source, 0),
            }
        )
    payload = {
        "checked_at": _now(),
        "ok": not source_errors,
        "failed_sources": sorted(source_errors),
        "sources": sources,
    }
    _write_json(SOURCE_HEALTH_JSON, payload)
    _write_json(SITE_SOURCE_HEALTH_JSON, payload)


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
        return "未知"
    value = job.get("published_at") if basis == "official" else job.get("first_seen_at")
    if not value:
        return "未知"
    reference = now or datetime.now(UTC)
    hours = max(0, int((reference - datetime.fromisoformat(str(value))).total_seconds() // 3600))
    days = hours // 24
    if hours == 0:
        age = "<1h"
    elif hours < 24:
        age = f"{hours}h"
    else:
        age = ">14d" if days > 14 else f"{days}d"
    return age


def _location_label(locations: list[str], limit: int = 3) -> str:
    if len(locations) <= limit:
        return " / ".join(locations)
    return f"{'、'.join(locations[:limit])}等 {len(locations)} 个城市"


def _readme_table(jobs: list[dict[str, Any]]) -> str:
    rows = ["| 公司 | 岗位 | 城市 | 招聘类型 | 新鲜度 | 投递链接 |", "|---|---|---|---|---|---|"]
    for job in jobs:
        values = [
            job["company"],
            job["title"],
            _location_label(job["locations"]),
            job["stage"],
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
        "> 新鲜度使用企业官方发布时间；官网未提供时使用本项目首次发现时间，首批批量导入显示为`未知`。\n\n"
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
        if not isinstance(job.get("missing_runs"), int) or int(job.get("missing_runs") or 0) < 0:
            errors.append(f"第 {index + 1} 条连续缺失次数无效: {job.get('missing_runs')}")
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


def build_outputs(
    jobs: list[dict[str, Any]] | None = None,
    successful_sources: set[str] | None = None,
    source_errors: dict[str, str] | None = None,
    raw_counts: dict[str, int] | None = None,
    observed_counts: dict[str, int] | None = None,
    anomaly_runs: dict[str, int] | None = None,
    previous_health: dict[str, Any] | None = None,
    history: dict[str, dict[str, str]] | None = None,
) -> None:
    jobs = _load_jobs() if jobs is None else jobs
    history = history or _load_job_history(jobs)
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
                "missing_runs": int(job.get("missing_runs") or 0),
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
    _write_job_history(history, jobs)
    if successful_sources is not None:
        _write_source_health(
            successful_sources,
            source_errors or {},
            raw_counts or {},
            observed_counts or {},
            anomaly_runs or {},
            jobs,
            previous_health or {},
        )
    _update_readme(jobs)
    print(f"已生成 README、JSON、CSV 和静态站点数据：{len(jobs)} 个岗位。")


def fetch_and_build(max_pages: int = 50) -> None:
    existing = _load_jobs()
    history = _load_job_history(existing)
    previous_health = _load_source_health()
    raw_jobs: list[dict[str, Any]] = []
    source_errors: dict[str, str] = {}
    raw_counts: dict[str, int] = {}
    observed_counts: dict[str, int] = {}
    anomaly_runs: dict[str, int] = {}
    successful_sources: set[str] = set()
    sources = (
        ("字节跳动", "字节跳动招聘", fetch_bytedance),
        ("腾讯", "腾讯校招", fetch_tencent),
        ("Momenta", "Momenta招聘", fetch_momenta),
        ("商汤", "商汤招聘", fetch_sensetime),
        ("莉莉丝", "莉莉丝招聘", fetch_lilith),
        ("叠纸游戏", "叠纸游戏招聘", fetch_papegames),
        ("沐瞳科技", "沐瞳科技招聘", fetch_moonton),
        ("地平线", "地平线招聘", fetch_horizon),
    )
    for name, source_label, fetcher in sources:
        try:
            source_jobs = fetcher(max_pages=max_pages)
            observed_counts[source_label] = len(source_jobs)
            drop_error, anomaly_count = _source_drop_error(source_label, len(source_jobs), previous_health)
            if drop_error:
                anomaly_runs[source_label] = anomaly_count
                raise RuntimeError(drop_error)
            raw_jobs.extend(source_jobs)
            raw_counts[source_label] = len(source_jobs)
            successful_sources.add(source_label)
            print(f"{name}：抓取 {len(source_jobs)} 个非技术岗")
        except RuntimeError as error:
            source_errors[source_label] = str(error)
            print(f"{name}：抓取失败，{error}")

    job_pro_groups, job_pro_failures = fetch_approved_companies(max_pages=max(max_pages, 100))
    source_errors.update(job_pro_failures)
    for source_label, source_jobs in job_pro_groups.items():
        observed_counts[source_label] = len(source_jobs)
        drop_error, anomaly_count = _source_drop_error(source_label, len(source_jobs), previous_health)
        if drop_error:
            anomaly_runs[source_label] = anomaly_count
            source_errors[source_label] = drop_error
            continue
        raw_jobs.extend(source_jobs)
        raw_counts[source_label] = len(source_jobs)
        successful_sources.add(source_label)
        print(f"{source_label}：抓取 {len(source_jobs)} 个早期职业岗位")
    for failure in job_pro_failures.values():
        print(f"扩展公司抓取失败：{failure}")
    if not raw_jobs:
        raise RuntimeError("所有官方数据源均抓取失败；保留已有数据，未覆盖输出。")
    jobs = _normalize(raw_jobs, existing, history)
    jobs = _reconcile_jobs(jobs, existing, successful_sources)
    build_outputs(
        jobs,
        successful_sources,
        source_errors,
        raw_counts,
        observed_counts,
        anomaly_runs,
        previous_health,
        history,
    )
    if source_errors:
        print("部分数据源失败；成功来源已更新，失败来源不会被伪装为最新数据。")
