"""
Activity logging for SEND study platform.

SQLite -> system reads from here for the dashboard (source of truth).
Text log -> human-readable append only, for debugging/tail -f. System never reads it.

Usage:
    from log import log
    log("lesson_view", lesson_id=5, topic="1.1", title="CPU Architecture")
    log("exam_submit", mode="quickfire", score="14/20", grade=7)
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

LOG_DIR = Path("/var/log/activity")
LOG_FILE = LOG_DIR / "send.log"
LOG_DB = LOG_DIR / "gcse-cs.db"
MAX_BYTES = 128 * 1024  # 128KB trim for text log only

# ─── SQLite schema ───────────────────────────────────────────────────────

_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS activity_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    site TEXT NOT NULL DEFAULT 'gcse-cs',
    event_type TEXT NOT NULL,
    device TEXT,
    ip TEXT,
    fields TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_al_timestamp ON activity_log(timestamp);
CREATE INDEX IF NOT EXISTS idx_al_event_type ON activity_log(event_type);
CREATE INDEX IF NOT EXISTS idx_al_device ON activity_log(device);
CREATE INDEX IF NOT EXISTS idx_al_ip ON activity_log(ip);
"""


def _ensure_dir():
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def _init_db():
    """Create schema if DB doesn't exist yet."""
    _ensure_dir()
    try:
        conn = sqlite3.connect(str(LOG_DB))
        for stmt in _SCHEMA_SQL.split(";"):
            s = stmt.strip()
            if s:
                conn.execute(s)
        conn.commit()
    finally:
        conn.close()


def _trim_if_needed():
    """Trim text log to MAX_BYTES if oversized. SQLite is never trimmed."""
    if LOG_FILE.stat().st_size > MAX_BYTES:
        with open(LOG_FILE, "r") as f:
            lines = f.readlines()
        # Keep last ~75% of max bytes
        keep = []
        size = 0
        for line in reversed(lines):
            keep.append(line)
            size += len(line)
            if size > MAX_BYTES * 0.75:
                break
        with open(LOG_FILE, "w") as f:
            f.writelines(reversed(keep))


def _write_text_log(event_type: str, **extra):
    """Append a human-readable line to the text log. System never reads this."""
    now = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
    parts = []
    for k, v in extra.items():
        if v is None:
            continue
        val = str(v)
        if len(val) > 2000:
            val = val[:1997] + "..."
        val = val.replace("|", "/")
        parts.append(f"{k}={val}")
    line = f"[{now}] [gcse-cs] {event_type} | {' | '.join(parts)}\n"
    _ensure_dir()
    with open(LOG_FILE, "a") as f:
        f.write(line)
    _trim_if_needed()


def _write_db(event_type: str, device: str = None, ip: str = None, **extra):
    """Append a structured row to SQLite. Source of truth for the dashboard."""
    try:
        conn = sqlite3.connect(str(LOG_DB))
        known = {"device", "ip"}
        fields = {k: v for k, v in extra.items() if k not in known}
        if device is None:
            device = extra.get("device")
        if ip is None:
            ip = extra.get("ip")
        conn.execute(
            "INSERT INTO activity_log (timestamp, site, event_type, device, ip, fields) VALUES (?, ?, ?, ?, ?, ?)",
            (
                datetime.now().isoformat(),
                "gcse-cs",
                event_type,
                str(device) if device else None,
                str(ip) if ip else None,
                json.dumps(fields, default=str),
            ),
        )
        conn.commit()
    except Exception:
        pass  # DB write failure shouldn't crash the app
    finally:
        conn.close()


def log(event_type: str, **extra):
    """
    Log an event to BOTH SQLite (system reads this) and text file (human debugging).

    Args:
        event_type: Short event name (lesson_view, quiz_submit, exam_submit, tutor_chat)
        **extra: Key-value pairs describing the event.
    """
    _init_db()
    _write_db(event_type, **extra)
    _write_text_log(event_type, **extra)
