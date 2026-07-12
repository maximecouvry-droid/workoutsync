from flask import Flask, jsonify, request
from api.common import compile_payload

app = Flask(__name__)

@app.post("/")
@app.post("/api/compile")
def handler():
    try:
        return jsonify(compile_payload(request.get_json(force=True) or {}))
    except Exception as exc:
        return jsonify({"error": str(exc)}), 400
