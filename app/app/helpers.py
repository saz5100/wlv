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
    "for WLV students (ages 14-16).\n\n"
    "### MERMAID DIAGRAMS\n"
    "Use mermaid for diagrams. Wrap in ```mermaid ... ``` fences.\n"
    "Use graph TD. Define classDefs at TOP. Quotes on ALL labels.\n"
    "Keep node labels SHORT (max 3-4 words per line, 1-2 lines per node).\n"
    "Use chained nodes instead of one node with long text.\n"
    "Put detailed explanations in surrounding text, not inside diagram nodes.\n"
    "VERTICAL LAYOUT ONLY \u2014 diagrams expand top-to-bottom, never left-to-right.\n"
    "No subgraphs, no title boxes, no legend boxes inside the diagram.\n"
    "KEY/LEGEND: Always include a text key/legend AFTER the mermaid block.\n"
    "\n"
    "COLOUR PALETTE (define at bottom of each diagram):\n"
    "  classDef fetch fill:#1e40af,stroke:#3b82f6,color:#fff\n"
    "  classDef decode fill:#c2410c,stroke:#f97316,color:#fff\n"
    "  classDef execute fill:#b91c1c,stroke:#ef4444,color:#fff\n"
    "  classDef system fill:#6b21a8,stroke:#a855f7,color:#fff\n"
    "  classDef decision fill:#0e7490,stroke:#06b6d4,color:#fff\n"
    "  classDef blue fill:#2563eb,color:#fff\n"
    "  classDef green fill:#16a34a,color:#fff\n"
    "  classDef purple fill:#7c3aed,color:#fff\n"
    "  classDef amber fill:#d97706,color:#fff\n"
    "  classDef red fill:#dc2626,color:#fff\n"
    "  classDef teal fill:#0891b2,color:#fff\n"
    "\n"
    "SHAPES: Rectangle: A[\"Label\"] | Oval: A([\"Label\"]) | Diamond: A{\"Label\"} | Arrow: A --> B | Label: A -->|\"text\"| B\n"
    "\n"
    "### BUTTONS \u2014 Follow-up suggestions\n"
    "At the END of every response, include a ```buttons JSON block with 2-4 contextual follow-up suggestions.\n"
    "These appear as clickable chips above the input bar.\n"
    "\n"
    "Format:\n"
    "```buttons\n"
    '[{"label": "Button text", "text": "text sent when clicked"},'
    ' {"label": "Option 2", "text": "Option 2 text"}]'
    "```\n"
    "\n"
    "Examples:\n"
    "- After explaining the CPU: buttons for 'Tell me more about registers', 'Give me a practice question', 'Explain the fetch-execute cycle'\n"
    "- After a practice question: buttons for 'Check my answer', 'Give me a hint', 'Try another question'\n"
    "- After giving advice: buttons for 'What should I study next?', 'Show me my weak areas'\n"
    "\n"
    "Always include buttons when the student could reasonably want to continue the conversation.\n"
    "\n"
    "### FORMATTING RULES\n"
    "Use these HTML callout boxes to make your responses engaging and easy to scan:\n"
    "- <div class=\"exam-tip\">...</div> \u2014 for exam technique advice, what examiners look for, command word tips\n"
    "- <div class=\"exam-tip grade9\">...</div> \u2014 for grade 9 stretch content, what top students do\n"
    "- <div class=\"key-point\">...</div> \u2014 for the single most important takeaway from a section\n"
    "- <div class=\"definition\">...</div> \u2014 when introducing a new technical term with its definition\n"
    "- <div class=\"warning-box\">...</div> \u2014 for common misconceptions, mistakes students make, pitfalls\n"
    "- <div class=\"remember-box\">...</div> \u2014 for memory aids, mnemonics, things to memorise\n"
    "Use these sparingly \u2014 1-3 per response max. They should highlight, not overwhelm. "
    "Also use <strong> for key terms, <em> for emphasis, and <code> for code/technical names.\n"
    "Use pipe tables (| col1 | col2 |) for comparisons, specifications, and structured data.\n"
    "Use <span style=\"color:#...\">...</span> to colour-key important terms (e.g. fetch=blue, decode=orange, execute=red).\n"
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
    context['WLV_DEBUG'] = os.getenv("WLV_DEBUG", "").lower() in ("true", "1", "yes")
    # Server-side cache-buster: unique on every render, defeats ALL caches
    context['CACHE_BUST'] = str(int(time.time() * 1000))
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
    execute("""
        INSERT INTO rate_limits (device_id, last_submit)
        VALUES (%s, %s)
        ON CONFLICT (device_id) DO UPDATE SET last_submit = EXCLUDED.last_submit
    """, (device_id, now))
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


# ─── Grade Tracking ───

GRADE_BOUNDARIES = {
    9: 85, 8: 75, 7: 65, 6: 55, 5: 45, 4: 35, 3: 25, 2: 15, 1: 0
}

def _get_grade_summary(user_id):
    """Get current working grade per topic and overall from exam-style results."""
    from database import query
    rows = query(
        "SELECT topic, marks, score FROM exam_style_results WHERE user_id = %s ORDER BY id DESC",
        (user_id,)
    )
    if not rows:
        return None
    
    topic_scores = {}
    for r in rows:
        topic = r["topic"]
        if topic not in topic_scores:
            topic_scores[topic] = {"total": 0, "count": 0}
        topic_scores[topic]["total"] += r["score"]
        topic_scores[topic]["count"] += 1
    
    topic_grades = []
    overall_total = 0
    overall_count = 0
    for topic, data in sorted(topic_scores.items()):
        avg_pct = round((data["total"] / (data["count"] * 6)) * 100)
        grade = _grade_from_percentage(avg_pct)
        topic_grades.append({
            "topic": topic,
            "avg_pct": avg_pct,
            "grade": grade,
            "attempts": data["count"]
        })
        overall_total += data["total"]
        overall_count += data["count"]
    
    overall_pct = round((overall_total / (overall_count * 6)) * 100) if overall_count > 0 else 0
    overall_grade = _grade_from_percentage(overall_pct)
    
    next_grade = overall_grade + 1
    if next_grade <= 9:
        next_boundary = GRADE_BOUNDARIES[next_grade]
        marks_needed = max(0, next_boundary - overall_pct)
    else:
        marks_needed = 0
    
    return {
        "overall_grade": overall_grade,
        "overall_pct": overall_pct,
        "next_grade": next_grade if next_grade <= 9 else None,
        "marks_to_next": marks_needed,
        "total_attempts": overall_count,
        "topics": topic_grades
    }

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
