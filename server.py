import os
import threading
import logging
from datetime import datetime
from flask import Flask, jsonify, request, render_template
import db

app = Flask(__name__, template_folder="templates")
log = logging.getLogger("werkzeug")
log.setLevel(logging.ERROR)  # suppress Flask request logs in terminal


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ------------------------------------------------------------------
# History
# ------------------------------------------------------------------

@app.route("/api/history")
def history():
    page = int(request.args.get("page", 1))
    q = request.args.get("q", "").strip()
    rows, total = db.get_history(page=page, per_page=20, q=q)
    return jsonify({"items": rows, "total": total, "page": page})


@app.route("/api/history/<int:tid>", methods=["DELETE"])
def delete_history(tid):
    db.delete_transcription(tid)
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Usage
# ------------------------------------------------------------------

@app.route("/api/usage")
def usage():
    return jsonify(db.get_usage())


# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------

@app.route("/api/settings", methods=["GET"])
def get_settings():
    return jsonify(db.get_settings())


@app.route("/api/settings", methods=["POST"])
def update_settings():
    data = request.get_json(force=True)
    allowed = {"model", "language", "obsidian_vault", "obsidian_folder"}
    filtered = {k: v for k, v in data.items() if k in allowed}
    db.update_settings(filtered)
    return jsonify({"ok": True})


# ------------------------------------------------------------------
# Obsidian
# ------------------------------------------------------------------

@app.route("/api/obsidian/<int:tid>", methods=["POST"])
def save_to_obsidian(tid):
    row = db.get_transcription(tid)
    if not row:
        return jsonify({"error": "not found"}), 404

    settings = db.get_settings()
    vault = os.path.expanduser(settings.get("obsidian_vault", "~/Documents/Vault"))
    folder = settings.get("obsidian_folder", "Voice Notes")
    save_dir = os.path.join(vault, folder)
    os.makedirs(save_dir, exist_ok=True)

    created = row["created_at"][:16].replace(":", "-")  # "2026-05-11 14-32"
    filename = f"{created} voice-note.md"
    filepath = os.path.join(save_dir, filename)

    words = row.get("word_count") or len(row["text"].split())
    cost = row.get("cost_usd") or 0
    ts = row["created_at"][:16]

    content = f"# Voice Note — {ts}\n\n{row['text']}\n\n---\n*Transcribed by Wispr Local · {words} words · ${cost:.4f}*\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)

    return jsonify({"ok": True, "path": filepath})


# ------------------------------------------------------------------
# Start
# ------------------------------------------------------------------

def start_server(port=7842):
    db.init()
    t = threading.Thread(
        target=lambda: app.run(host="127.0.0.1", port=port, debug=False, use_reloader=False),
        daemon=True,
    )
    t.start()
