import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "wispr.db")

_CREATE_TRANSCRIPTIONS = """
CREATE TABLE IF NOT EXISTS transcriptions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    text        TEXT NOT NULL,
    duration_s  REAL,
    word_count  INTEGER,
    cost_usd    REAL
);
"""

_CREATE_SETTINGS = """
CREATE TABLE IF NOT EXISTS settings (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

_DEFAULTS = {
    "model":           "whisper-1",
    "language":        "en",
    "obsidian_vault":  os.path.expanduser("~/Documents/Vault"),
    "obsidian_folder": "Voice Notes",
}


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init():
    with _connect() as conn:
        conn.execute(_CREATE_TRANSCRIPTIONS)
        conn.execute(_CREATE_SETTINGS)
        for k, v in _DEFAULTS.items():
            conn.execute(
                "INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (k, v)
            )


# ------------------------------------------------------------------
# Transcriptions
# ------------------------------------------------------------------

def save_transcription(text, duration_s, word_count, cost_usd):
    with _connect() as conn:
        conn.execute(
            "INSERT INTO transcriptions (text, duration_s, word_count, cost_usd) VALUES (?, ?, ?, ?)",
            (text, duration_s, word_count, cost_usd),
        )


def get_history(page=1, per_page=20, q=""):
    offset = (page - 1) * per_page
    with _connect() as conn:
        if q:
            pattern = f"%{q}%"
            rows = conn.execute(
                "SELECT * FROM transcriptions WHERE text LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (pattern, per_page, offset),
            ).fetchall()
            total = conn.execute(
                "SELECT COUNT(*) FROM transcriptions WHERE text LIKE ?", (pattern,)
            ).fetchone()[0]
        else:
            rows = conn.execute(
                "SELECT * FROM transcriptions ORDER BY created_at DESC LIMIT ? OFFSET ?",
                (per_page, offset),
            ).fetchall()
            total = conn.execute("SELECT COUNT(*) FROM transcriptions").fetchone()[0]
    return [dict(r) for r in rows], total


def get_transcription(tid):
    with _connect() as conn:
        row = conn.execute(
            "SELECT * FROM transcriptions WHERE id = ?", (tid,)
        ).fetchone()
    return dict(row) if row else None


def delete_transcription(tid):
    with _connect() as conn:
        conn.execute("DELETE FROM transcriptions WHERE id = ?", (tid,))


# ------------------------------------------------------------------
# Usage stats
# ------------------------------------------------------------------

def get_usage():
    with _connect() as conn:
        total = conn.execute(
            "SELECT COUNT(*) as count, COALESCE(SUM(duration_s),0) as secs, COALESCE(SUM(cost_usd),0) as cost "
            "FROM transcriptions"
        ).fetchone()
        month = conn.execute(
            "SELECT COALESCE(SUM(cost_usd),0) as cost, COUNT(*) as count "
            "FROM transcriptions WHERE strftime('%Y-%m', created_at) = strftime('%Y-%m', 'now')"
        ).fetchone()
        daily = conn.execute(
            "SELECT date(created_at) as day, COUNT(*) as count, COALESCE(SUM(cost_usd),0) as cost "
            "FROM transcriptions WHERE created_at >= date('now', '-13 days') "
            "GROUP BY day ORDER BY day"
        ).fetchall()
    return {
        "total_count":      total["count"],
        "total_minutes":    round(total["secs"] / 60, 2),
        "total_cost":       round(total["cost"], 4),
        "month_count":      month["count"],
        "month_cost":       round(month["cost"], 4),
        "daily":            [dict(r) for r in daily],
    }


# ------------------------------------------------------------------
# Settings
# ------------------------------------------------------------------

def get_settings():
    with _connect() as conn:
        rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def update_settings(data: dict):
    with _connect() as conn:
        for k, v in data.items():
            conn.execute(
                "INSERT INTO settings (key, value) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (k, v),
            )
