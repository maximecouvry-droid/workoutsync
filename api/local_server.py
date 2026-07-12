from flask import Flask, jsonify, request
from api.common import compile_payload, intervals_events_payload, notion_query_payload, notion_status_payload

app = Flask(__name__)

@app.get("/api/health")
def health():
    return jsonify({"ok": True, "service": "workout-sync-local"})

@app.post("/api/compile")
def compile_route():
    try:
        return jsonify(compile_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/notion/query")
def notion_query_route():
    try:
        return jsonify(notion_query_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/notion/status")
def notion_status_route():
    try:
        return jsonify(notion_status_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

@app.post("/api/intervals/events")
def intervals_events_route():
    try:
        return jsonify(intervals_events_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400

if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=False)
