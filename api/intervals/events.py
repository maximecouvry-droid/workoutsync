from flask import Flask, jsonify, request
from api.common import intervals_events_payload

app = Flask(__name__)

@app.post("/")
@app.post("/api/intervals/events")
def handler():
    try:
        return jsonify(intervals_events_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
