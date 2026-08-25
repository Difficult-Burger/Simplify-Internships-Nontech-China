"""Fetch approved market-sector companies through a pinned MIT job-pro CLI."""

import json
import re
import subprocess
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from radar.company_pool import APPROVED_COMPANIES, JOB_PRO_VERSION, JobProCompany

JsonObject = dict[str, Any]
EARLY_CAREER_PATTERN = re.compile(r"实习|校招|应届|管培生|培训生|intern|graduate|trainee", re.IGNORECASE)


def _run_job_pro(company: JobProCompany, scope: str, max_pages: int) -> list[JsonObject]:
    command = [
        "npx",
        "-y",
        f"@ha7ch/job-pro@{JOB_PRO_VERSION}",
        company.key,
        "all",
        "--scope",
        scope,
        "--page-size",
        "100",
        "--max-pages",
        str(max_pages),
        "--compact",
    ]
    result = subprocess.run(command, capture_output=True, text=True, timeout=240, check=False)
    lines = [line for line in result.stdout.splitlines() if line.strip().startswith("{")]
    if not lines:
        detail = (result.stderr or result.stdout).strip().splitlines()[-1:] or ["no JSON output"]
        raise RuntimeError(f"{company.company} {scope}: {detail[0]}")
    payload = json.loads(lines[-1])
    if not payload.get("ok"):
        raise RuntimeError(f"{company.company} {scope}: {payload.get('message', 'upstream error')}")
    if payload.get("truncated"):
        raise RuntimeError(f"{company.company} {scope}: truncated at {payload.get('fetched')} / {payload.get('total')}")
    return payload.get("positions") or []


def _stage(position: JsonObject) -> str:
    text = f"{position.get('recruit_label', '')} {position.get('title', '')}".casefold()
    return "实习" if "实习" in text or "intern" in text else "校招"


def _normalize(company: JobProCompany, position: JsonObject) -> JsonObject | None:
    title = str(position.get("title") or "").strip()
    recruit_label = str(position.get("recruit_label") or "")
    if company.early_only and not EARLY_CAREER_PATTERN.search(f"{title} {recruit_label}"):
        return None
    post_id = str(position.get("post_id") or "").strip()
    apply_url = str(position.get("apply_url") or "").strip()
    if not post_id or not title or not apply_url:
        return None
    raw_category = " / ".join(
        value for value in [str(position.get("project") or "").strip(), str(position.get("bgs") or "").strip()] if value
    )
    locations = re.split(r"\s*(?:/|,|，|、)\s*", str(position.get("work_cities") or "").strip())
    return {
        "id": f"{company.key}:{post_id}",
        "company": company.company,
        "title": title,
        "raw_category": raw_category,
        "locations": [location for location in locations if location],
        "stage": _stage(position),
        "published_at": "",
        "url": apply_url,
        "source": company.source,
    }


def _fetch_company(company: JobProCompany, max_pages: int) -> list[JsonObject]:
    positions: dict[str, JsonObject] = {}
    errors: list[str] = []
    for scope in company.scopes:
        try:
            for position in _run_job_pro(company, scope, max_pages):
                normalized = _normalize(company, position)
                if normalized:
                    positions[normalized["id"]] = normalized
        except (RuntimeError, subprocess.TimeoutExpired, json.JSONDecodeError) as error:
            errors.append(str(error))
    if not positions and errors:
        raise RuntimeError("; ".join(errors))
    return list(positions.values())


def fetch_approved_companies(max_pages: int = 50) -> tuple[dict[str, list[JsonObject]], list[str]]:
    """Return jobs grouped by source label plus per-company failures."""
    grouped: dict[str, list[JsonObject]] = {}
    failures: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {pool.submit(_fetch_company, company, max_pages): company for company in APPROVED_COMPANIES}
        for future in as_completed(futures):
            company = futures[future]
            try:
                grouped[company.source] = future.result()
            except Exception as error:
                failures.append(f"{company.company}: {error}")
    return grouped, failures
