"""Small adapters for public, official company recruiting endpoints."""

import json
import os
import ssl
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from radar.config import BYTEDANCE_CATEGORY_IDS, TENCENT_POSITION_FAMILY_IDS

JsonObject = dict[str, Any]
USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
)


def _ssl_context() -> ssl.SSLContext:
    """Use an explicit system CA bundle on macOS Python installations that miss it."""
    candidates = [os.environ.get("SSL_CERT_FILE", ""), "/etc/ssl/cert.pem"]
    ca_file = next((path for path in candidates if path and Path(path).is_file()), None)
    return ssl.create_default_context(cafile=ca_file)


def _post_json(url: str, payload: JsonObject, headers: dict[str, str]) -> JsonObject:
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={"User-Agent": USER_AGENT, "Content-Type": "application/json", **headers},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=30, context=_ssl_context()) as response:
            return json.load(response)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
        raise RuntimeError(f"请求失败 {url}: {error}") from error


def _iso_from_milliseconds(value: Any) -> str:
    if not isinstance(value, (int, float)) or value <= 0:
        return ""
    return datetime.fromtimestamp(value / 1000, UTC).isoformat(timespec="seconds")


def fetch_bytedance(max_pages: int = 50, page_size: int = 100) -> list[JsonObject]:
    """Fetch campus and internship non-engineering roles from ByteDance."""
    url = "https://jobs.bytedance.com/api/v1/search/job/posts"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "portal-channel": "campus",
        "portal-platform": "pc",
        "website-path": "campus",
        "Origin": "https://jobs.bytedance.com",
        "Referer": "https://jobs.bytedance.com/campus/position",
    }
    jobs: list[JsonObject] = []

    for page in range(max_pages):
        payload = {
            "keyword": "",
            "limit": page_size,
            "offset": page * page_size,
            "portal_type": 3,
            "portal_entrance": 1,
            "language": "zh",
            "recruitment_id_list": ["201", "202"],
            "job_category_id_list": BYTEDANCE_CATEGORY_IDS,
        }
        response = _post_json(url, payload, headers)
        if response.get("code") != 0:
            raise RuntimeError(f"字节跳动接口返回错误: {response.get('message', 'unknown error')}")
        data = response.get("data") or {}
        rows = data.get("job_post_list") or []
        for row in rows:
            upstream_id = str(row.get("id") or "")
            if not upstream_id:
                continue
            cities = row.get("city_list") or ([row.get("city_info")] if row.get("city_info") else [])
            locations = [city.get("name", "") for city in cities if city and city.get("name")]
            recruit_type = (row.get("recruit_type") or {}).get("name", "")
            jobs.append(
                {
                    "id": f"bytedance:{upstream_id}",
                    "company": "字节跳动",
                    "title": row.get("title", "").strip(),
                    "raw_category": (row.get("job_category") or {}).get("name", ""),
                    "locations": locations,
                    "stage": "实习" if "实习" in recruit_type else "校招",
                    "published_at": _iso_from_milliseconds(row.get("publish_time")),
                    "url": f"https://jobs.bytedance.com/campus/position/{upstream_id}/detail",
                    "source": "字节跳动招聘",
                }
            )
        total = int(data.get("count") or len(rows))
        if not rows or len(jobs) >= total or len(rows) < page_size:
            break
    return jobs


def fetch_tencent(max_pages: int = 50, page_size: int = 100) -> list[JsonObject]:
    """Fetch campus and internship non-engineering roles from Tencent."""
    jobs: list[JsonObject] = []
    url = f"https://join.qq.com/api/v1/position/searchPosition?timestamp={int(time.time() * 1000)}"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://join.qq.com",
        "Referer": "https://join.qq.com/post.html",
    }

    for page in range(1, max_pages + 1):
        payload = {
            "projectIdList": [],
            "projectMappingIdList": [],
            "keyword": "",
            "bgList": [],
            "workCountryType": 1,
            "workCityList": [],
            "recruitCityList": [],
            "positionFidList": TENCENT_POSITION_FAMILY_IDS,
            "pageIndex": page,
            "pageSize": page_size,
        }
        response = _post_json(url, payload, headers)
        if response.get("status") != 0:
            raise RuntimeError(f"腾讯接口返回错误: {response.get('message', 'unknown error')}")
        data = response.get("data") or {}
        rows = data.get("positionList") or []
        for row in rows:
            upstream_id = str(row.get("postId") or "")
            if not upstream_id:
                continue
            recruit_label = str(row.get("recruitLabelName") or "")
            locations = [part.strip() for part in str(row.get("workCities") or "").replace("/", ",").split(",")]
            jobs.append(
                {
                    "id": f"tencent:{upstream_id}",
                    "company": "腾讯",
                    "title": str(row.get("positionTitle") or "").strip(),
                    "raw_category": str(row.get("projectName") or "").strip(),
                    "locations": [location for location in locations if location],
                    "stage": "实习" if "实习" in recruit_label else "校招",
                    "published_at": "",
                    "url": f"https://join.qq.com/post_detail.html?postid={upstream_id}",
                    "source": "腾讯校招",
                }
            )
        total = int(data.get("count") or len(rows))
        if not rows or len(jobs) >= total or len(rows) < page_size:
            break
    return jobs


def _fetch_feishu_campus(
    *,
    host: str,
    channel: str,
    company: str,
    source: str,
    id_prefix: str,
    max_pages: int,
    page_size: int = 100,
) -> list[JsonObject]:
    url = f"https://{host}/api/v1/search/job/posts"
    headers = {
        "Accept": "application/json, text/plain, */*",
        "portal-channel": channel,
        "portal-platform": "pc",
        "website-path": channel,
        "Origin": f"https://{host}",
        "Referer": f"https://{host}/{channel}/",
    }
    jobs: list[JsonObject] = []
    for page in range(max_pages):
        response = _post_json(
            url,
            {
                "keyword": "",
                "limit": page_size,
                "offset": page * page_size,
                "portal_type": 3,
                "portal_entrance": 1,
                "language": "zh",
            },
            headers,
        )
        if response.get("code") != 0:
            raise RuntimeError(f"{company}接口返回错误: {response.get('message', 'unknown error')}")
        data = response.get("data") or {}
        rows = data.get("job_post_list") or []
        for row in rows:
            upstream_id = str(row.get("id") or "")
            if not upstream_id:
                continue
            cities = row.get("city_list") or ([row.get("city_info")] if row.get("city_info") else [])
            locations = [city.get("name", "") for city in cities if city and city.get("name")]
            recruit_type = (row.get("recruit_type") or {}).get("name", "")
            raw_category = (row.get("job_category") or {}).get("name") or (row.get("job_function") or {}).get(
                "name", ""
            )
            jobs.append(
                {
                    "id": f"{id_prefix}:{upstream_id}",
                    "company": company,
                    "title": str(row.get("title") or "").strip(),
                    "raw_category": raw_category,
                    "locations": locations,
                    "stage": "实习" if "实习" in f"{recruit_type} {row.get('title', '')}" else "校招",
                    "published_at": _iso_from_milliseconds(row.get("publish_time")),
                    "url": f"https://{host}/{channel}/position/{upstream_id}/detail",
                    "source": source,
                }
            )
        total = int(data.get("count") or len(rows))
        if not rows or len(jobs) >= total or len(rows) < page_size:
            break
    return jobs


def fetch_momenta(max_pages: int = 50) -> list[JsonObject]:
    return _fetch_feishu_campus(
        host="momenta.jobs.feishu.cn",
        channel="campus",
        company="Momenta",
        source="Momenta招聘",
        id_prefix="momenta",
        max_pages=max_pages,
    )


def fetch_sensetime(max_pages: int = 50) -> list[JsonObject]:
    return _fetch_feishu_campus(
        host="hr-jobs.sensetime.com",
        channel="edu",
        company="商汤",
        source="商汤招聘",
        id_prefix="sensetime",
        max_pages=max_pages,
    )


def fetch_lilith(max_pages: int = 50) -> list[JsonObject]:
    return _fetch_feishu_campus(
        host="lilithgames.jobs.feishu.cn",
        channel="campus",
        company="莉莉丝",
        source="莉莉丝招聘",
        id_prefix="lilith",
        max_pages=max_pages,
    )


def fetch_papegames(max_pages: int = 50) -> list[JsonObject]:
    return _fetch_feishu_campus(
        host="career.papegames.com",
        channel="campus",
        company="叠纸游戏",
        source="叠纸游戏招聘",
        id_prefix="papegames",
        max_pages=max_pages,
    )


def fetch_moonton(max_pages: int = 50) -> list[JsonObject]:
    return _fetch_feishu_campus(
        host="moonton.jobs.feishu.cn",
        channel="campus",
        company="沐瞳科技",
        source="沐瞳科技招聘",
        id_prefix="moonton",
        max_pages=max_pages,
    )
