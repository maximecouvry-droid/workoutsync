from flask import Flask, jsonify, request
from api.common import notion_status_payload

app = Flask(__name__)

@app.post("/")
@app.post("/api/notion/status")
def handler():
    try:
        return jsonify(notion_status_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
