from __future__ import annotations

import base64
import json
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from flask import Flask, jsonify, request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from parser.core import (  # noqa: E402
    DEFAULT_PROFILE,
    SPORT_MAP,
    compile_details_v6,
    estimate_duration_seconds,
)

app = Flask(__name__)

def _json_request(url: str, method: str = "GET", headers: dict | None = None, payload=None):
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
        raise RuntimeError(f"Erreur réseau: {exc}") from exc

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "workout-sync"})

@app.post("/api/compile")
def compile_workout():
    data = request.get_json(force=True) or {}
    details = str(data.get("details", "")).strip()
    sport = str(data.get("sport", "Course")).strip()
    profile = DEFAULT_PROFILE.copy()
    profile.update(data.get("profile") or {})
    intervals_type = SPORT_MAP.get(sport, SPORT_MAP.get(sport.capitalize()))
    if intervals_type == "Swim":
        return jsonify({"error": "La natation est volontairement exclue."}), 400
    if intervals_type not in {"Run", "Ride"}:
        return jsonify({"error": f"Sport non reconnu: {sport}"}), 400
    if not details:
        return jsonify({"error": "Détails séance manquants."}), 400
    try:
        script, warnings, records = compile_details_v6(details, intervals_type, profile)
        return jsonify({
            "script": script,
            "warnings": warnings,
            "records": records,
            "moving_time": estimate_duration_seconds(script),
        })
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/notion/query")
def notion_query():
    data = request.get_json(force=True) or {}
    token = data.get("token")
    database_id = data.get("database_id")
    if not token or not database_id:
        return jsonify({"error": "Token ou Database ID manquant."}), 400
    payload = {
        "filter": {
            "and": [
                {"property": "Sync Intervals", "checkbox": {"equals": True}},
                {"property": "Status", "status": {"equals": "To do"}},
            ]
        },
        "page_size": 100,
    }
    try:
        _, result = _json_request(
            f"https://api.notion.com/v1/databases/{database_id}/query",
            "POST",
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            payload,
        )
        return jsonify(result)
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/intervals/events")
def intervals_events():
    data = request.get_json(force=True) or {}
    api_key = data.get("api_key")
    events = data.get("events")
    if not api_key or not isinstance(events, list) or not events:
        return jsonify({"error": "Clé Intervals ou événements manquants."}), 400
    auth = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
    try:
        status, result = _json_request(
            "https://intervals.icu/api/v1/athlete/0/events/bulk?upsert=true",
            "POST",
            {
                "Authorization": f"Basic {auth}",
                "Content-Type": "application/json",
                "User-Agent": "WorkoutSyncPWA/0.1",
            },
            events,
        )
        return jsonify({"status": status, "result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/notion/status")
def notion_status():
    data = request.get_json(force=True) or {}
    token, page_id = data.get("token"), data.get("page_id")
    if not token or not page_id:
        return jsonify({"error": "Token ou page_id manquant."}), 400
    try:
        status, result = _json_request(
            f"https://api.notion.com/v1/pages/{page_id}",
            "PATCH",
            {
                "Authorization": f"Bearer {token}",
                "Notion-Version": "2022-06-28",
                "Content-Type": "application/json",
            },
            {"properties": {"Status": {"status": {"name": "Sync"}}}},
        )
        return jsonify({"status": status, "result": result})
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
