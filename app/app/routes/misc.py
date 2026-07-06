"""Routes: flashcards, resources, revision, reset-mastery, reset-lessons, reset-exams, health, debug/dbpath"""
from json import loads as json_loads, JSONDecodeError
import os
import re
import httpx
from pathlib import Path
import json
import base64

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from pydantic import BaseModel, Field
from log import log
from helpers import render, get_device_user, _get_grade_summary, _grade_from_percentage
from database import execute_async, query_async, query_one_async, init_db, get_embedding

router = APIRouter()

# ─── PostgreSQL connection for KB ───
PG_DSN = os.environ.get("WLV_PG_DSN", "dbname=wlv_kb user=wlv_app password=wlv_kb_2026 host=localhost port=5432 client_encoding=utf8")

def get_pg_conn():
    import psycopg2
    return psycopg2.connect(PG_DSN)

# ─── Wiki ───

@router.get("/wiki", response_class=HTMLResponse)
async def wiki_page(request: Request):
    """Model answer wiki — browse/search grade 9 answers by topic."""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("""
            SELECT ms.id, ms.topic, ms.marks, ms.question, ms.mark_scheme, ms.model_answer, ms.key_terms
            FROM mark_schemes ms
            ORDER BY ms.topic, ms.marks DESC
        """)
        rows = c.fetchall()
        conn.close()

        pages = []
        topics = set()
        for r in rows:
            pages.append({
                "id": r[0], "topic": r[1], "marks": r[2],
                "question": r[3], "mark_scheme": r[4],
                "model_answer": r[5], "key_terms": r[6],
                "title": f"{'Evaluate' if r[2]==8 else 'Explain'} — {r[3][:80]}..."
            })
            topics.add(r[1])

        return render("wiki.html", pages=pages, topics=sorted(topics))
    except Exception as e:
        log("wiki_error", error=str(e))
        return HTMLResponse(f"<h1>Wiki unavailable</h1><p>{e}</p>", status_code=500)

class CodeLabCompleteRequest(BaseModel):
    challenge_id: int = Field(gt=0, le=10)

class BossBattleSubmitRequest(BaseModel):
    question_id: int = Field(gt=0)
    answer: str

class FlashcardStatusRequest(BaseModel):
    question_id: int = Field(gt=0)
    status: str = Field(pattern="^(known|review)$")


# ─── Boss Battle ───

@router.get("/api/boss/{lesson_id}")
async def boss_get(lesson_id: int, request: Request):
    """Check mastery and return a boss battle question if eligible."""
    user = get_device_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user["id"]

    # Check full mastery: all questions in lesson must have consecutive_correct >= 3
    mastery = await query_one_async("""
        SELECT COUNT(DISTINCT q.id) as total,
               COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) as mastered
        FROM quiz_questions q
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        WHERE q.lesson_id = %s
    """, (user_id, lesson_id))

    total = mastery["total"] if mastery else 0
    mastered = mastery["mastered"] if mastery else 0

    if total == 0 or mastered < total:
        return {"eligible": False, "mastered": mastered, "total": total}

    # Check if already beaten this boss
    existing = await query_one_async(
        "SELECT passed FROM boss_battle_results WHERE user_id = %s AND lesson_id = %s",
        (user_id, lesson_id)
    )
    if existing and existing["passed"]:
        return {"eligible": True, "already_passed": True, "mastered": mastered, "total": total}

    # Fetch a hard question (difficulty=3) for this lesson not yet used as a boss question
    used_qid = existing["question_id"] if existing else None
    boss_q = await query_one_async("""
        SELECT id, question, options, correct_index, explanation, command_word
        FROM quiz_questions
        WHERE lesson_id = %s AND difficulty = 3
        AND (%s IS NULL OR id != %s)
        ORDER BY RANDOM() LIMIT 1
    """, (lesson_id, used_qid, used_qid))

    # Fallback to any question if no difficulty=3 exists
    if not boss_q:
        boss_q = await query_one_async("""
            SELECT id, question, options, correct_index, explanation, command_word
            FROM quiz_questions
            WHERE lesson_id = %s
            AND (%s IS NULL OR id != %s)
            ORDER BY difficulty DESC, RANDOM() LIMIT 1
        """, (lesson_id, used_qid, used_qid))

    if not boss_q:
        return {"eligible": False, "mastered": mastered, "total": total}

    boss_q = dict(boss_q)
    if isinstance(boss_q.get("options"), str):
        boss_q["options"] = json_loads(boss_q["options"])

    return {
        "eligible": True,
        "already_passed": False,
        "mastered": mastered,
        "total": total,
        "question": boss_q
    }


@router.post("/api/boss/{lesson_id}/submit")
async def boss_submit(lesson_id: int, data: BossBattleSubmitRequest, request: Request):
    """Validate boss battle answer and record the result."""
    user = get_device_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")

    user_id = user["id"]

    q = await query_one_async(
        "SELECT correct_index, explanation FROM quiz_questions WHERE id = %s AND lesson_id = %s",
        (data.question_id, lesson_id)
    )
    if not q:
        raise HTTPException(status_code=404, detail="Question not found")

    correct_index = q["correct_index"]
    try:
        ci = int(correct_index)
        passed = str(data.answer).strip() == str(ci)
    except (ValueError, TypeError):
        passed = str(data.answer).strip() == str(correct_index).strip()

    passed_int = 1 if passed else 0
    await execute_async("""
        INSERT INTO boss_battle_results (user_id, lesson_id, passed, question_id, completed_at)
        VALUES (%s, %s, %s, %s, CURRENT_TIMESTAMP)
        ON CONFLICT(user_id, lesson_id) DO UPDATE SET
            passed = CASE WHEN excluded.passed = 1 THEN 1 ELSE boss_battle_results.passed END,
            question_id = excluded.question_id,
            completed_at = excluded.completed_at
    """, (user_id, lesson_id, passed_int, data.question_id))

    log("boss_battle", device=request.state.device_id, lesson_id=lesson_id, passed=passed)
    return {"passed": passed, "explanation": q.get("explanation", "")}


@router.get("/codelab", response_class=HTMLResponse)
async def codelab_page():
    return render("codelab.html", active="codelab")

@router.get("/section-b", response_class=HTMLResponse)
async def section_b_page():
    return render("section_b.html", active="section-b")

@router.get("/trace-tables", response_class=HTMLResponse)
async def trace_tables_page():
    return render("trace_tables.html", active="trace-tables")

@router.get("/test-data", response_class=HTMLResponse)
async def test_data_page():
    return render("test_data.html", active="test-data")

@router.get("/reference", response_class=HTMLResponse)
async def reference_page():
    return render("reference.html", active="reference")

@router.get("/languages", response_class=HTMLResponse)
async def languages_page():
    return render("languages.html", active="languages")

@router.get("/print-revision", response_class=HTMLResponse)
async def print_revision(request: Request):
    """Personalised printable revision sheet — filter by topic codes."""
    topics_param = request.query_params.get("topics", "")
    selected = set(t.strip() for t in topics_param.split(",") if t.strip()) if topics_param else set()
    return render("revision.html", active="revision", print_mode=True, selected_topics=selected)

@router.get("/settings", response_class=HTMLResponse)
async def settings_page():
    return render("settings.html", active="settings")

@router.post("/api/codelab/complete")
async def codelab_complete(data: CodeLabCompleteRequest, request: Request):
    user = get_device_user(request)
    if not user:
        raise HTTPException(400, "No user found")
    log("codelab_complete", device=request.state.device_id, challenge_id=data.challenge_id)
    return {"status": "ok"}


@router.get("/api/lessons")
async def api_lessons():
    """Return all lessons as [{id, title, topic_code}, ...] for the flashcard selector."""
    rows = await query_async("SELECT id, topic_code, title FROM lessons ORDER BY topic_code, sort_order")
    return [dict(r) for r in rows]


@router.get("/api/flashcards/{lesson_id}")
async def api_flashcards(lesson_id: int):
    """Return quiz questions for a lesson as [{question, options, answer}, ...]."""
    rows = await query_async(
        "SELECT id, question, options, correct_index FROM quiz_questions WHERE lesson_id = %s ORDER BY id",
        (lesson_id,)
    )
    result = []
    for r in rows:
        opts = r["options"]
        if isinstance(opts, str):
            opts = json_loads(opts)
        ci = r["correct_index"]
        if isinstance(ci, str):
            try:
                ci = json_loads(ci)
                ci = ci[0] if isinstance(ci, list) else int(ci)
            except (JSONDecodeError, ValueError, IndexError):
                ci = 0
        result.append({
            "id": r["id"],
            "question": r["question"],
            "options": opts,
            "answer": int(ci)
        })
    return result


@router.post("/api/flashcard-status")
async def api_flashcard_set_status(data: FlashcardStatusRequest, request: Request):
    """Persist a Know/Review status for a flashcard question."""
    user = get_device_user(request)
    if not user:
        raise HTTPException(status_code=401, detail="Not authenticated")
    user_id = user["id"]
    await execute_async(
        "INSERT INTO flashcard_status (user_id, question_id, status, updated_at) "
        "VALUES (%s, %s, %s, CURRENT_TIMESTAMP) "
        "ON CONFLICT(user_id, question_id) DO UPDATE SET status = excluded.status, updated_at = excluded.updated_at",
        (user_id, data.question_id, data.status)
    )
    return {"status": "ok"}


@router.get("/api/flashcard-status/{lesson_id}")
async def api_flashcard_get_status(lesson_id: int, request: Request):
    """Return all flashcard statuses for a lesson's questions."""
    user = get_device_user(request)
    if not user:
        return {}
    user_id = user["id"]
    rows = await query_async(
        "SELECT fs.question_id, fs.status FROM flashcard_status fs "
        "JOIN quiz_questions q ON q.id = fs.question_id "
        "WHERE fs.user_id = %s AND q.lesson_id = %s",
        (user_id, lesson_id)
    )
    return {r["question_id"]: r["status"] for r in rows}


@router.get("/api/flashcard-progress")
async def api_flashcard_progress(request: Request):
    """Return per-lesson progress: total questions, known count, review count."""
    user = get_device_user(request)
    if not user:
        # Return totals without user-specific data
        rows = await query_async(
            "SELECT l.id, l.topic_code, l.title, COUNT(q.id) as total "
            "FROM lessons l LEFT JOIN quiz_questions q ON q.lesson_id = l.id "
            "GROUP BY l.id, l.topic_code, l.title, l.sort_order ORDER BY l.topic_code, l.sort_order"
        )
        return [{"id": r["id"], "topic_code": r["topic_code"], "title": r["title"],
                 "total": r["total"], "known": 0, "review": 0} for r in rows]

    user_id = user["id"]
    rows = await query_async(
        "SELECT l.id, l.topic_code, l.title, COUNT(q.id) as total "
        "FROM lessons l LEFT JOIN quiz_questions q ON q.lesson_id = l.id "
        "GROUP BY l.id, l.topic_code, l.title, l.sort_order ORDER BY l.topic_code, l.sort_order"
    )
    result = []
    for r in rows:
        lid = r["id"]
        # Known: flashcard_status = 'known'
        known = await query_one_async(
            "SELECT COUNT(*) as c FROM flashcard_status fs "
            "JOIN quiz_questions q ON q.id = fs.question_id "
            "WHERE fs.user_id = %s AND q.lesson_id = %s AND fs.status = 'known'",
            (user_id, lid)
        )
        # Review: flashcard_status = 'review'
        review = await query_one_async(
            "SELECT COUNT(*) as c FROM flashcard_status fs "
            "JOIN quiz_questions q ON q.id = fs.question_id "
            "WHERE fs.user_id = %s AND q.lesson_id = %s AND fs.status = 'review'",
            (user_id, lid)
        )
        result.append({
            "id": lid,
            "topic_code": r["topic_code"],
            "title": r["title"],
            "total": r["total"],
            "known": known["c"] if known else 0,
            "review": review["c"] if review else 0
        })
    return result


@router.get("/flashcards", response_class=HTMLResponse)
async def flashcards_page():
    return render("flashcards.html", active="flashcards")

@router.get("/flashcard-sample", response_class=HTMLResponse)
async def flashcard_sample():
    """Serve the flashcard sample HTML."""
    path = Path(__file__).resolve().parent.parent / "static" / "flashcard-sample.html"
    if path.exists():
        return HTMLResponse(content=path.read_text())
    return HTMLResponse(content="<h1>Sample not found</h1>", status_code=404)


@router.get("/resources", response_class=HTMLResponse)
async def resources_page():
    return render("resources.html", active="resources")


@router.get("/revision", response_class=HTMLResponse)
async def revision_page():
    return render("revision.html", active="revision")


@router.post("/reset-mastery")
async def reset_mastery(request: Request):
    user = get_device_user(request)
    if user:
        await execute_async("DELETE FROM question_mastery WHERE user_id = %s", (user["id"],))
    return {"status": "ok"}


@router.post("/reset-lessons")
async def reset_lessons(request: Request):
    user = get_device_user(request)
    if not user:
        return {"status": "error", "error": "No user found"}
    await execute_async("DELETE FROM question_mastery WHERE user_id = %s", (user["id"],))
    await execute_async("DELETE FROM quiz_attempts WHERE user_id = %s", (user["id"],))
    await execute_async("DELETE FROM review_schedule WHERE user_id = %s", (user["id"],))
    return {"status": "ok"}


@router.post("/reset-exams")
async def reset_exams(request: Request):
    user = get_device_user(request)
    if not user:
        return {"status": "error", "error": "No user found"}
    await execute_async("DELETE FROM exam_results WHERE user_id = %s", (user["id"],))
    return {"status": "ok"}


@router.get("/admin", response_class=HTMLResponse)
async def admin_dashboard(request: Request):
    import os
    import shutil
    from datetime import date, timedelta

    # ── DB Stats ──
    total_lessons = (await query_one_async("SELECT COUNT(*) as c FROM lessons"))["c"]
    total_questions = (await query_one_async("SELECT COUNT(*) as c FROM quiz_questions"))["c"]
    total_users = (await query_one_async("SELECT COUNT(*) as c FROM users"))["c"]
    total_attempts = (await query_one_async("SELECT COUNT(*) as c FROM quiz_attempts"))["c"]
    mastered = (await query_one_async("SELECT COUNT(DISTINCT question_id) as c FROM question_mastery WHERE consecutive_correct >= 3"))["c"]
    review_entries = (await query_one_async("SELECT COUNT(*) as c FROM review_schedule"))["c"]
    review_due = (await query_one_async("SELECT COUNT(*) as c FROM review_schedule WHERE next_review::date <= CURRENT_DATE"))["c"]
    exam_results = (await query_one_async("SELECT COUNT(*) as c FROM exam_results"))["c"]

    mcq = (await query_one_async("SELECT COUNT(*) as c FROM quiz_questions WHERE question_type='mcq'"))["c"]
    tf = (await query_one_async("SELECT COUNT(*) as c FROM quiz_questions WHERE question_type='true_false'"))["c"]
    fill = (await query_one_async("SELECT COUNT(*) as c FROM quiz_questions WHERE question_type IN ('fill','cloze')"))["c"]

    today_str = date.today().isoformat()
    week_ago = (date.today() - timedelta(days=7)).isoformat()
    active_today = (await query_one_async("SELECT COUNT(DISTINCT user_id) as c FROM quiz_attempts WHERE DATE(answered_at) = %s", (today_str,)))["c"]
    active_week = (await query_one_async("SELECT COUNT(DISTINCT user_id) as c FROM quiz_attempts WHERE DATE(answered_at) >= %s", (week_ago,)))["c"]

    mastery_pct = 0
    attempted_questions = (await query_one_async("SELECT COUNT(DISTINCT question_id) as c FROM question_mastery WHERE total_attempts > 0"))["c"]
    if attempted_questions > 0:
        mastery_pct = round(mastered / attempted_questions * 100)

    # ── Topic Stats ──
    topic_rows = await query_async("""
        SELECT t.code, t.title, t.sort_order,
               COUNT(DISTINCT l.id) as lesson_count,
               COUNT(DISTINCT q.id) as q_count,
               SUM(CASE WHEN q.difficulty = 1 THEN 1 ELSE 0 END) as easy_count,
               SUM(CASE WHEN q.difficulty = 2 THEN 1 ELSE 0 END) as med_count,
               SUM(CASE WHEN q.difficulty = 3 THEN 1 ELSE 0 END) as hard_count
        FROM topics t
        LEFT JOIN lessons l ON l.topic_code = t.code
        LEFT JOIN quiz_questions q ON q.lesson_id = l.id
        GROUP BY t.code, t.title, t.sort_order
        ORDER BY t.sort_order
    """)
    topic_stats = []
    for r in topic_rows:
        topic_stats.append(dict(r))

    # ── Users ──
    user_rows = await query_async("""
        SELECT u.id, u.username, u.display_name, u.last_ip, u.created_at,
               (SELECT COUNT(*) FROM quiz_attempts qa WHERE qa.user_id = u.id) as attempt_count,
               (SELECT COUNT(DISTINCT qm.question_id) FROM question_mastery qm WHERE qm.user_id = u.id AND qm.consecutive_correct >= 3) as mastered_count
        FROM users u
        ORDER BY u.created_at DESC
        LIMIT 50
    """)
    users = [dict(r) for r in user_rows]

    # ── System (Docker-compatible) ──
    db_size_mb = 0
    db_ok = True
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        c.execute("SELECT pg_database_size('wlv_kb')")
        db_size_bytes = c.fetchone()[0]
        db_size_mb = round(db_size_bytes / (1024 * 1024), 1)
        conn.close()
    except:
        db_ok = False

    mem_total = 0
    mem_used = 0
    mem_pct = 0
    try:
        meminfo = open("/proc/meminfo").read()
        for line in meminfo.split("\n"):
            if line.startswith("MemTotal:"):
                mem_total = int(line.split()[1]) // 1024
            elif line.startswith("MemAvailable:"):
                avail = int(line.split()[1]) // 1024
                mem_used = mem_total - avail
        if mem_total > 0:
            mem_pct = round(mem_used / mem_total * 100)
    except:
        pass

    disk_total = 0
    disk_used = 0
    disk_pct = 0
    try:
        usage = shutil.disk_usage("/app")
        disk_total = round(usage.total / (1024**3), 1)
        disk_used = round(usage.used / (1024**3), 1)
        disk_pct = round(usage.used / usage.total * 100)
    except:
        pass

    uptime = "N/A"
    try:
        with open("/proc/uptime") as f:
            up_secs = float(f.read().split()[0])
            days = int(up_secs // 86400)
            hours = int((up_secs % 86400) // 3600)
            mins = int((up_secs % 3600) // 60)
            uptime = f"{days}d {hours}h {mins}m"
    except:
        pass

    system = {
        "db_size_mb": db_size_mb,
        "db_ok": db_ok,
        "db_type": "PostgreSQL 16",
        "memory_used_mb": mem_used,
        "memory_total_mb": mem_total,
        "memory_pct": mem_pct,
        "disk_used_gb": disk_used,
        "disk_total_gb": disk_total,
        "disk_pct": disk_pct,
        "uptime": uptime,
        "service_status": "Running"
    }

    lessons_per_topic = round(total_lessons / max(len(topic_stats), 1), 1)

    return render("admin.html",
        active="admin",
        stats={
            "total_lessons": total_lessons,
            "total_questions": total_questions,
            "total_users": total_users,
            "total_attempts": total_attempts,
            "mastered_questions": mastered,
            "mastery_pct": mastery_pct,
            "review_entries": review_entries,
            "review_due": review_due,
            "exam_results": exam_results,
            "mcq_count": mcq,
            "tf_count": tf,
            "fill_count": fill,
            "active_today": active_today,
            "active_week": active_week,
            "lessons_per_topic": lessons_per_topic,
            "error_feedback_count": (await query_one_async("SELECT COUNT(*) as cnt FROM error_feedback"))["cnt"] or 0
        },
        topic_stats=topic_stats,
        users=users,
        system=system
    )


@router.get("/health")
async def health():
    try:
        init_db()
        return {"status": "ok", "db": "connected"}
    except Exception as e:
        return {"status": "error", "db": f"{type(e).__name__}: {e}"}


@router.get("/debug/dbpath")
async def debug_dbpath():
    return {"db_path": "PostgreSQL (no local DB_PATH)", "exists": True}


@router.post("/admin/rename")
async def admin_rename(request: Request):
    """Rename a user/device from the admin page. Updates both users table
    and activity dashboard device names."""
    form = await request.form()
    user_id = form.get("user_id", "").strip()
    new_name = form.get("name", "").strip()
    if not user_id or not new_name:
        return RedirectResponse(url="/admin", status_code=303)

    # 1. Update users table
    await execute_async(
        "UPDATE users SET display_name = %s WHERE id = %s",
        (new_name, int(user_id))
    )

    # 2. Update activity dashboard device names
    try:
        from activity_dashboard import set_device_name
        # Get the username for this user to use as device_id
        row = await query_one_async(
            "SELECT username FROM users WHERE id = %s", (int(user_id),)
        )
        if row and row.get("username"):
            set_device_name(row["username"], new_name)
    except ImportError:
        pass

    return RedirectResponse(url="/admin", status_code=303)


# ─── Exam-Style Written Questions ───



@router.get("/exam-style", response_class=HTMLResponse)
async def exam_style_page(request: Request, marks: int = 6, topic: str = "", skip_id: int = 0):
    """Show exam-style written question landing page or question."""
    if marks not in (6, 8):
        marks = 6

    # ── LANDING PAGE: no topic selected, show topic/marks picker ──
    if not topic:
        # Get topics that have questions for the selected mark value
        try:
            conn = get_pg_conn()
            c = conn.cursor()
            c.execute("SELECT DISTINCT t.code, t.title FROM topics t JOIN exam_questions eq ON eq.topic = t.code WHERE eq.marks = %s ORDER BY t.sort_order", (marks,))
            topic_rows = c.fetchall()
            conn.close()
            topics_with_marks = [{'code': r[0], 'title': r[1]} for r in topic_rows]
        except Exception:
            topics_with_marks = await query_async("SELECT code, title FROM topics ORDER BY sort_order")
        html = render("exam-style.html",
            landing=True, topics=topics_with_marks, marks=marks,
            result=None, question=None, error=None, active="exam-style")
        return html

    # ── QUESTION PAGE: topic selected, show a question ──
    try:
        conn = get_pg_conn()
        c = conn.cursor()

        if skip_id:
            c.execute("""
                SELECT id, question, command_word, topic, marks
                FROM exam_questions
                WHERE topic = %s AND marks = %s AND id != %s
                ORDER BY RANDOM() LIMIT 1
            """, (topic, marks, skip_id))
        else:
            c.execute("""
                SELECT id, question, command_word, topic, marks
                FROM exam_questions
                WHERE topic = %s AND marks = %s
                ORDER BY RANDOM() LIMIT 1
            """, (topic, marks))

        row = c.fetchone()
        conn.close()

        if row:
            q_id, question, command_word, db_topic, db_marks = row
            topic_name = f"Topic {db_topic}"
        else:
            # No question found in DB for this topic/marks combination
            html = render("exam-style.html",
                error="No " + str(marks) + "-mark question available for Topic " + topic + ". Try a different mark value or topic.",
                landing=False, topics=[], marks=marks, topic=topic,
                topic_name="Topic " + topic, command_word="Explain",
                question="", question_id=0, result=None, active="exam-style")
            return html

        html = render("exam-style.html",
            landing=False, topics=[], marks=marks, topic=topic,
            topic_name=topic_name, command_word=command_word,
            question=question, question_id=q_id, result=None, error=None, active="exam-style")
        return html
    except Exception as e:
        log("exam_style_page_error", error=str(e))
        html = render("exam-style.html",
            error="Could not load question. Database error: " + str(e),
            landing=False, topics=[], marks=marks, topic=topic,
            topic_name="Topic " + topic, command_word="Explain",
            question="", question_id=0, result=None, active="exam-style")
        return html


@router.post("/exam-style/submit")
async def exam_style_submit(request: Request):
    """Submit an exam-style answer for AI marking."""
    form = await request.form()
    question = form.get("question", "")
    question_id = form.get("question_id", "0")
    try:
        question_id = int(question_id)
    except (ValueError, TypeError):
        question_id = 0
    marks = int(form.get("marks", 6))
    topic = form.get("topic", "1.1")
    command_word = form.get("command_word", "Explain")
    topic_name = form.get("topic_name", "")
    answer = form.get("answer", "").strip()

    if not answer:
        return {"error": "Please write an answer before submitting."}
    if len(answer.split()) < 10:
        return {"error": "Your answer is too short. Please write at least a few sentences."}

    # Retrieve relevant mark scheme from PostgreSQL (pgvector semantic search)
    rag_context = ""
    try:
        conn = get_pg_conn()
        c = conn.cursor()
        # Get embedding for the question
        emb = get_embedding(question)
        if emb:
            emb_str = "[" + ",".join(str(x) for x in emb) + "]"
            c.execute(f"""
                SELECT ms.mark_scheme, ms.model_answer, ms.key_terms, ms.marks
                FROM mark_schemes ms
                ORDER BY ms.embedding <=> '{emb_str}'::vector
                LIMIT 1
            """)
        else:
            # Fallback: keyword match
            keywords = [w for w in question.split() if len(w) > 3][:5]
            like_clauses = " AND ".join([f"(ms.question LIKE '%{w}%' OR ms.mark_scheme LIKE '%{w}%')" for w in keywords])
            c.execute(f"""
                SELECT ms.mark_scheme, ms.model_answer, ms.key_terms, ms.marks
                FROM mark_schemes ms
                WHERE {like_clauses}
                ORDER BY ms.marks DESC
                LIMIT 1
            """)
        row = c.fetchone()
        if row:
            rag_context = f"""
{row[0]}

MODEL ANSWER (grade 9):
{row[1]}

KEY TERMINOLOGY REQUIRED:
{row[2]}
"""
        conn.close()
    except Exception as e:
        log("rag_retrieval_error", error=str(e))
        rag_context = ""

    # Call AI for marking
    try:
        api_key = os.environ.get("OLLAMA_CLOUD_API_KEY") or os.environ.get("DEEPSEEK_API_KEY")
        base_url = os.environ.get("OLLAMA_CLOUD_BASE_URL", "https://ollama.com/v1")
        model = os.environ.get("OLLAMA_CLOUD_MODEL", "deepseek-v4-flash")

        prompt = f"""You are a WLV Computer Science examiner marking a {marks}-mark {command_word} question.

QUESTION:
{question}

STUDENT ANSWER:
{answer}

{rag_context}

Mark the answer out of {marks}. Use the real mark scheme above as your primary reference. Return your response as JSON with these fields:
- "score": integer (0-{marks})
- "feedback": string (2-3 sentences of overall feedback)
- "strengths": list of strings (what the student did well)
- "weaknesses": list of strings (what could be improved)
- "key_terms_missed": list of strings (important WLV Computer Science terminology the student should have included in their answer but did not. CRITICAL: every question has at least 3-5 key terms that should appear. List the specific terms missing. If the student used all relevant terms, still list 2-3 terms they could have added for a grade 9 answer.)
- "model_answer": string (a grade 9 model answer for this question)
- "ao_breakdown": object with "ao1" (knowledge), "ao2" (explanation), "ao3" (evaluation) scores out of the marks available for each AO. For a {marks}-mark {command_word} question: if {command_word} == "Explain" use AO1=~40%, AO2=~60%, AO3=0%. If {command_word} == "Evaluate" use AO1=~25%, AO2=~35%, AO3=~40%. Estimate the student's marks per AO.

Be fair but thorough. A grade 9 answer would use precise technical language, be well-structured, and address all parts of the question."""

        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                f"{base_url}/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 2000
                }
            )
            data = resp.json()
            content = data["choices"][0]["message"]["content"]

        # Parse JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            result = json_loads(json_match.group())
        else:
            result = {"score": 0, "feedback": "Could not parse AI response.", "strengths": [], "weaknesses": [], "key_terms_missed": [], "model_answer": ""}

        # Fallback: if AI returned empty/weak key_terms_missed, extract from RAG context
        if not result.get("key_terms_missed") and rag_context:
            import re as re2
            # Extract KEY TERMINOLOGY REQUIRED section
            kt_match = re2.search(r'KEY TERMINOLOGY REQUIRED:\n(.+)', rag_context)
            if kt_match:
                raw_terms = kt_match.group(1)
                # Parse comma-separated terms
                terms = [t.strip() for t in raw_terms.split(",") if t.strip()]
                # Filter to terms NOT found in the student's answer
                answer_lower = answer.lower() if answer else ""
                missed = [t for t in terms if t.lower() not in answer_lower]
                if missed:
                    result["key_terms_missed"] = missed[:8]  # max 8 terms


        # Save to exam_style_results
        try:
            user = get_device_user(request)
            if user:
                from database import execute_async
                await execute_async("""
                    INSERT INTO exam_style_results (user_id, topic, marks, score, question, answer, feedback, strengths, weaknesses, key_terms_missed, model_answer, taken_at)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                """, (
                    user["id"], topic, marks, result.get("score", 0),
                    question, answer, result.get("feedback", ""),
                    json.dumps(result.get("strengths", [])),
                    json.dumps(result.get("weaknesses", [])),
                    json.dumps(result.get("key_terms_missed", [])),
                    result.get("model_answer", "")
                ))
        except Exception as e:
            log("exam_style_save_error", error=str(e))

        # Build context_b64 for AI Tutor links
        try:
            ctx = {
                "t": topic_name or "",
                "q": question or "",
                "a": answer or "",
                "s": result.get("score", 0),
                "m": marks,
                "f": result.get("feedback", ""),
                "ma": result.get("model_answer", ""),
                "ms": rag_context[:2000] if rag_context else ""
            }
            ctx_json = json.dumps(ctx)
            context_b64 = base64.urlsafe_b64encode(ctx_json.encode()).decode().rstrip("=")
        except Exception:
            context_b64 = ""

        # Render results HTML
        html_resp = render("exam-style.html",
            result=result, marks=marks, topic=topic, question_id=question_id,
            topic_name=topic_name, command_word=command_word,
            question=question, error=None, active="exam-style",
            context_b64=context_b64, mark_scheme_text=rag_context[:3000] if rag_context else None)
        return {"html": html_resp.body.decode() if hasattr(html_resp, "body") else str(html_resp), "score": result.get("score", 0), "marks": marks, "question_id": question_id}

    except Exception as e:
        log("exam_style_error", error=str(e))
        return {"error": f"Sorry, marking failed: {str(e)}"}



# --- Grade API ---

@router.get("/api/grade-summary")
async def api_grade_summary(request: Request):
    """Get current working grade summary."""
    user = get_device_user(request)
    if not user:
        return {"overall_grade": None, "overall_pct": 0, "total_attempts": 0, "topics": []}
    return _get_grade_summary(user["id"]) or {"overall_grade": None, "overall_pct": 0, "total_attempts": 0, "topics": []}


@router.get("/grade", response_class=HTMLResponse)
async def grade_dashboard(request: Request):
    """Working grade dashboard — per-topic and overall WLV 9-1 grades."""
    user = get_device_user(request)
    if not user:
        return render("grade.html", active="grade", has_data=False)

    grade_data = _get_grade_summary(user["id"])

    # Also get exam_results (quiz-based exams) for a more complete picture
    exam_rows = await query_async(
        "SELECT percentage, taken_at FROM exam_results WHERE user_id = %s AND percentage > 0 ORDER BY taken_at DESC LIMIT 20",
        (user["id"],)
    )

    # Grade history over time
    grade_history = []
    for r in reversed(exam_rows):
        taken = r["taken_at"]
        if isinstance(taken, str):
            try:
                from datetime import datetime
                taken = datetime.fromisoformat(taken.replace("Z", ""))
            except:
                taken = None
        grade_history.append({
            "pct": r["percentage"],
            "grade": _grade_from_percentage(r["percentage"]),
            "date": taken.strftime("%d/%m/%Y") if taken else "?"
        })

    return render("grade.html",
        active="grade",
        has_data=bool(grade_data),
        grade=grade_data,
        grade_history=grade_history,
        GRADE_BOUNDARIES={9: 85, 8: 75, 7: 65, 6: 55, 5: 45, 4: 35, 3: 25, 2: 15, 1: 0}
    )


# ─── Error Feedback ──────────────────────────────────────────────────

class ErrorFeedbackRequest(BaseModel):
    page_url: str
    description: str = Field(min_length=1, max_length=2000)
    console_errors: str = ""
    browser_info: str = ""


@router.post("/api/error-feedback")
async def submit_error_feedback(data: ErrorFeedbackRequest, request: Request):
    user = get_device_user(request)
    user_id = user["id"] if user else None
    await execute_async(
        "INSERT INTO error_feedback (user_id, page_url, description, console_errors, browser_info) "
        "VALUES (%s, %s, %s, %s, %s)",
        (user_id, data.page_url, data.description, data.console_errors, data.browser_info)
    )
    return {"status": "ok"}


@router.get("/admin/error-feedback", response_class=HTMLResponse)
async def admin_error_feedback(request: Request):
    rows = await query_async(
        "SELECT ef.*, u.display_name, u.username "
        "FROM error_feedback ef "
        "LEFT JOIN users u ON u.id = ef.user_id "
        "ORDER BY ef.created_at DESC LIMIT 100"
    )
    return render("error_feedback_admin.html", request=request, active="admin", feedbacks=rows)
