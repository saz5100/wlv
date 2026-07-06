"""
WLV CS Revision — Shared Helper Functions
Extracted from main.py for route-split refactoring.
Uses actual DB schema: question_mastery, review_schedule, quiz_attempts.
"""
import re, json, os, time
from pathlib import Path
from datetime import date, datetime, timedelta

from fastapi import Request, HTTPException
from fastapi.responses import HTMLResponse
from jinja2 import Environment, FileSystemLoader

from database import get_db, query, query_one, execute, query_async, query_one_async, execute_async

# ─── Config ───
BASE_DIR = Path(__file__).resolve().parent
templates = Environment(loader=FileSystemLoader(BASE_DIR / "templates"))
OWUI_KEY = os.environ.get("OWUI_API_KEY")
OWUI_MODEL = os.environ.get("OWUI_MODEL", "wlv-computer-science--v3")
FALLBACK_SYSTEM_PROMPT = (
    "You are an enthusiastic, technically precise AI tutor for "
    "and terminology. Provide clear, logical explanations suitable "
    "for WLV students (ages 14-16). When creating mermaid diagrams: keep node labels SHORT (max 3-4 words per line, 1-2 lines per node). Use chained nodes instead of one node with long text. Put detailed explanations in surrounding text, not inside diagram nodes."
)
OWUI_BASE = os.environ.get("OWUI_BASE", "http://chat.lan")
MAX_TOKENS = 2048

ICON_MAP = {
    "1.1": "\U0001f527", "1.2": "\U0001f9e0", "1.3": "\U0001f310", "1.4": "\U0001f512",
    "1.5": "\u2699\ufe0f", "1.6": "\u2696\ufe0f", "2.1": "\U0001f50d", "2.2": "\U0001f4dd",
    "2.3": "\U0001f6e1\ufe0f", "2.4": "\U0001f532", "2.5": "\U0001f4df"
}

def get_icon(code):
    return ICON_MAP.get(code, "\U0001f4d6")


def render(template_name, **context):
    template = templates.get_template(template_name)
    context.setdefault('active', '')
    context['ICON_MAP'] = ICON_MAP
    return HTMLResponse(content=template.render(**context))


def get_device_user(request: Request):
    return query_one("SELECT id, username FROM users WHERE username = %s", (request.state.device_id,))


# ─── Rate Limiting ───
def _check_rate_limit(device_id: str) -> tuple[bool, float]:
    """Check if device can submit. Uses DB for cross-worker safety."""
    from database import execute, query_one
    execute("CREATE TABLE IF NOT EXISTS rate_limits (device_id TEXT PRIMARY KEY, last_submit REAL)")
    now = time.time()
    row = query_one("SELECT last_submit FROM rate_limits WHERE device_id = %s", (device_id,))
    if row:
        elapsed = now - row["last_submit"]
        if elapsed < 2.0:
            return False, round(2.0 - elapsed, 1)
    execute("INSERT OR REPLACE INTO rate_limits (device_id, last_submit) VALUES (%s, %s)", (device_id, now))
    return True, 0


# ─── Grading ───
def _grade_from_percentage(pct):
    if pct >= 85: return 9
    if pct >= 75: return 8
    if pct >= 65: return 7
    if pct >= 55: return 6
    if pct >= 45: return 5
    if pct >= 35: return 4
    if pct >= 25: return 3
    if pct >= 15: return 2
    return 1


# ─── Answer Checking ───
def _check_answer(q, user_answer):
    """Check answer for any question type."""
    import json
    qtype = q.get("question_type", "mcq") or "mcq"
    correct = q["correct_index"]
    
    if qtype in ("mcq",):
        return str(user_answer) == str(correct)
    
    elif qtype == "true_false":
        return str(user_answer) == str(correct)
    
    elif qtype == "multiple_select":
        # user_answer is a comma-separated list "0,2,3"
        # correct is JSON array "[0,2,3]"
        try:
            correct_list = sorted(json.loads(correct) if isinstance(correct, str) else correct)
        except (json.JSONDecodeError, TypeError):
            return str(user_answer) == str(correct)
        if isinstance(user_answer, str):
            try:
                user_list = sorted([int(x.strip()) for x in user_answer.split(",") if x.strip()])
            except ValueError:
                return False
        elif isinstance(user_answer, list):
            user_list = sorted(user_answer)
        else:
            return False
        return user_list == correct_list
    
    elif qtype == "ordering":
        # user_answer is comma-separated "0,1,2,3"
        try:
            correct_list = json.loads(correct) if isinstance(correct, str) else correct
        except (json.JSONDecodeError, TypeError):
            return str(user_answer) == str(correct)
        if isinstance(user_answer, str):
            try:
                user_list = [int(x.strip()) for x in user_answer.split(",") if x.strip()]
            except ValueError:
                return False
        elif isinstance(user_answer, list):
            user_list = user_answer
        else:
            return False
        return user_list == correct_list
    
    elif qtype == "cloze":
        # user_answer is text, correct is the index in options array of the acceptable answer
        try:
            options = json.loads(q["options"]) if isinstance(q["options"], str) else q["options"]
            correct_idx = int(correct)
            acceptable = options[correct_idx].strip().lower() if correct_idx < len(options) else ""
        except (json.JSONDecodeError, TypeError, IndexError, ValueError):
            # Fallback: check if user_answer matches correct as a string
            return str(user_answer).strip().lower() == str(correct).strip().lower()
        user_text = str(user_answer).strip().lower() if user_answer else ""
        return user_text == acceptable
    
    # Default fallback
    return str(user_answer) == str(correct)


# ─── Question stats ───
def _get_question_stats(lesson_id, topic_code):
    conn = get_db()
    cur = conn.execute("SELECT COUNT(*) FROM quiz_questions WHERE lesson_id = ?", (lesson_id,))
    cnt = cur.fetchone()[0]
    conn.close()
    return cnt


# ─── SM-2 Review Schedule (lesson-level) ───
def _update_review_schedule(user_id, lesson_id, score_pct):
    """SM-2 spaced repetition algorithm update."""
    # Get existing schedule
    schedule = query_one(
        "SELECT * FROM review_schedule WHERE user_id = %s AND lesson_id = %s",
        (user_id, lesson_id)
    )
    
    # SM-2 quality rating (0-5 scale mapped from percentage)
    if score_pct >= 90:
        q = 5  # Perfect response
    elif score_pct >= 70:
        q = 4  # Correct after hesitation
    elif score_pct >= 50:
        q = 3  # Correct with serious difficulty
    elif score_pct >= 30:
        q = 2  # Incorrect, easy to recall
    else:
        q = 1  # Incorrect, remembered after review
    
    # SM-2 algorithm
    # Advance schedule only at 70%+ (was 50%)
    if q < 4:
        # Reset repetitions
        reps = 0
        interval = 0
    else:
        if schedule:
            reps = schedule["repetitions"] + 1
        else:
            reps = 1
        
        if reps == 1:
            interval = 1
        elif reps == 2:
            interval = 6
        else:
            if schedule:
                interval = int(schedule["interval_days"] * schedule["easiness"])
            else:
                interval = 6
    
    # Calculate new easiness factor
    ef = schedule["easiness"] if schedule else 2.5
    ef = ef + (0.1 - (5 - q) * (0.08 + (5 - q) * 0.02))
    if ef < 1.3:
        ef = 1.3
    
    next_review = date.today() + timedelta(days=interval)
    
    if schedule:
        execute(
            "UPDATE review_schedule SET easiness = %s, interval_days = %s, "
            "repetitions = %s, next_review = %s, last_reviewed = CURRENT_TIMESTAMP "
            "WHERE user_id = %s AND lesson_id = %s",
            (ef, interval, reps, next_review, user_id, lesson_id)
        )
    else:
        execute(
            "INSERT INTO review_schedule (user_id, lesson_id, easiness, "
            "interval_days, repetitions, next_review, last_reviewed) "
            "VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)",
            (user_id, lesson_id, ef, interval, reps, next_review)
        )


# ─── Question mastery update (inline in quiz submit) ───
# This is called directly by the quiz route, not as a helper function.
# Included here for shared access.


# ─── XP / Gamification System ───

LEVEL_THRESHOLDS = [
    (1, 0),       # Level 1: 0 XP
    (2, 100),     # Level 2: 100 XP
    (3, 300),     # Level 3: 300 XP
    (4, 600),     # Level 4: 600 XP
    (5, 1000),    # Level 5: 1000 XP
    (6, 1500),    # Level 6: 1500 XP
    (7, 2200),    # Level 7: 2200 XP
    (8, 3000),    # Level 8: 3000 XP
    (9, 4000),    # Level 9: 4000 XP
    (10, 5500),   # Level 10: 5500 XP
]

LEVEL_NAMES = {
    1: "Beginner",
    2: "Apprentice",
    3: "Coder",
    4: "Debugger",
    5: "Builder",
    6: "Analyst",
    7: "Architect",
    8: "Expert",
    9: "Master",
    10: "Grandmaster"
}

XP_REWARDS = {
    "quiz_correct": 10,       # Correct MCQ/TF answer
    "quiz_correct_hard": 20,  # Correct difficulty=3 answer
    "quiz_perfect": 50,       # 100% on a quiz
    "flashcard_known": 5,     # Marked a card as known
    "flashcard_review": 2,    # Marked a card for review
    "streak_bonus": 15,       # Daily streak bonus
    "boss_defeated": 100,     # Beat a boss battle
    "exam_completed": 30,     # Completed an exam
}

def _calculate_level(xp):
    """Determine level from total XP."""
    level = 1
    for lvl, threshold in LEVEL_THRESHOLDS:
        if xp >= threshold:
            level = lvl
    return level

def _get_level_name(level):
    return LEVEL_NAMES.get(level, "Grandmaster")

def _get_level_progress(xp):
    """Return (current_level, next_level_xp, progress_pct) for the progress bar."""
    level = _calculate_level(xp)
    current_threshold = 0
    next_threshold = LEVEL_THRESHOLDS[-1][1]
    for lvl, threshold in LEVEL_THRESHOLDS:
        if lvl == level:
            current_threshold = threshold
        if lvl == level + 1:
            next_threshold = threshold
    if next_threshold <= current_threshold:
        return level, 0, 100
    progress = ((xp - current_threshold) / (next_threshold - current_threshold)) * 100
    return level, next_threshold - xp, min(100, round(progress))

def _award_xp(user_id, amount, reason):
    """Award XP to a user, update level, and log the transaction."""
    from database import execute, query_one
    execute(
        "INSERT INTO user_xp (user_id, xp, level, updated_at) VALUES (%s, %s, 1, CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id) DO UPDATE SET xp = xp + %s, updated_at = CURRENT_TIMESTAMP",
        (user_id, amount, amount)
    )
    # Recalculate level
    row = query_one("SELECT xp FROM user_xp WHERE user_id = %s", (user_id,))
    if row:
        new_level = _calculate_level(row["xp"])
        execute("UPDATE user_xp SET level = %s WHERE user_id = %s", (new_level, user_id))
    # Log transaction
    execute(
        "INSERT INTO xp_transactions (user_id, amount, reason) VALUES (%s, %s, %s)",
        (user_id, amount, reason)
    )

def _get_user_xp(user_id):
    """Get XP info for a user."""
    from database import query_one
    row = query_one("SELECT xp, level FROM user_xp WHERE user_id = %s", (user_id,))
    if not row:
        return {"xp": 0, "level": 1, "level_name": "Beginner", "next_level_xp": 100, "progress_pct": 0}
    xp = row["xp"]
    level = row["level"]
    _, next_xp, pct = _get_level_progress(xp)
    return {
        "xp": xp,
        "level": level,
        "level_name": _get_level_name(level),
        "next_level_xp": next_xp,
        "progress_pct": pct
    }

def _get_leaderboard(limit=20):
    """Get top users by XP."""
    from database import query
    rows = query(
        "SELECT u.id, u.username, u.display_name, COALESCE(ux.xp, 0) as xp, COALESCE(ux.level, 1) as level "
        "FROM users u LEFT JOIN user_xp ux ON ux.user_id = u.id "
        "ORDER BY ux.xp DESC NULLS LAST LIMIT %s",
        (limit,)
    )
    result = []
    for i, r in enumerate(rows):
        result.append({
            "rank": i + 1,
            "username": r["username"],
            "display_name": r["display_name"] or r["username"],
            "xp": r["xp"],
            "level": r["level"],
            "level_name": _get_level_name(r["level"])
        })
    return result


import httpx

async def _call_owui(messages: list[dict], stream: bool = False) -> httpx.Response:
    headers = {"Authorization": f"Bearer {OWUI_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": OWUI_MODEL,
        "messages": [{"role": "system", "content": FALLBACK_SYSTEM_PROMPT}] + messages,
        "max_tokens": MAX_TOKENS,
        "stream": stream,
        "thinking": {"type": "enabled"},
        "reasoning_effort": "high",
        "temperature": 0.7,
    }
    async with httpx.AsyncClient(timeout=60.0) as client:
        resp = await client.post(f"{OWUI_BASE}/api/chat/completions", headers=headers, json=payload)
        resp.raise_for_status()
        return resp
