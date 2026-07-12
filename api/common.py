from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.core import DEFAULT_PROFILE, SPORT_MAP, compile_details_v6, estimate_duration_seconds


def json_request(url: str, method: str = "GET", headers: dict | None = None, payload=None):
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    req = Request(url, data=body, method=method, headers=headers or {})
    try:
        with urlopen(req, timeout=45) as response:
            raw = response.read().decode("utf-8", errors="replace")
            return response.status, json.loads(raw) if raw else None
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Erreur réseau : {exc}") from exc


def compile_payload(data: dict):
    details = str(data.get("details", "")).strip()
    sport = str(data.get("sport", "Course")).strip()
    profile = DEFAULT_PROFILE.copy()
    profile.update(data.get("profile") or {})

    intervals_type = SPORT_MAP.get(sport, SPORT_MAP.get(sport.capitalize()))
    if intervals_type == "Swim":
        raise ValueError("La natation est volontairement exclue.")
    if intervals_type not in {"Run", "Ride"}:
        raise ValueError(f"Sport non reconnu : {sport}")
    if not details:
        raise ValueError("Détails séance manquants.")

    script, warnings, records = compile_details_v6(details, intervals_type, profile)
    return {
        "script": script,
        "warnings": warnings,
        "records": records,
        "moving_time": estimate_duration_seconds(script),
    }


def notion_query_payload(data: dict):
    token = data.get("token")
    database_id = data.get("database_id")
    if not token or not database_id:
        raise ValueError("Token ou Database ID manquant.")

    payload = {
        "filter": {
            "and": [
                {"property": "Sync Intervals", "checkbox": {"equals": True}},
                {"property": "Status", "status": {"equals": "To do"}},
            ]
        },
        "page_size": 100,
    }

    _, result = json_request(
        f"https://api.notion.com/v1/databases/{database_id}/query",
        "POST",
        {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        payload,
    )
    return result


def notion_status_payload(data: dict):
    token = data.get("token")
    page_id = data.get("page_id")
    if not token or not page_id:
        raise ValueError("Token ou page_id manquant.")

    status, result = json_request(
        f"https://api.notion.com/v1/pages/{page_id}",
        "PATCH",
        {
            "Authorization": f"Bearer {token}",
            "Notion-Version": "2022-06-28",
            "Content-Type": "application/json",
        },
        {"properties": {"Status": {"status": {"name": "Sync"}}}},
    )
    return {"status": status, "result": result}


def intervals_events_payload(data: dict):
    api_key = data.get("api_key")
    events = data.get("events")
    if not api_key or not isinstance(events, list) or not events:
        raise ValueError("Clé Intervals ou événements manquants.")

    auth = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    status, result = json_request(
        "https://intervals.icu/api/v1/athlete/0/events/bulk?upsert=true",
        "POST",
        {
            "Authorization": f"Basic {auth}",
            "Content-Type": "application/json",
            "User-Agent": "WorkoutSyncPWA/0.3",
        },
        events,
    )
    return {"status": status, "result": result}
