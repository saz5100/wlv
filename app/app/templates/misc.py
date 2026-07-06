"""Routes: flashcards, resources, revision, reset-mastery, reset-lessons, reset-exams, health, debug/dbpath"""
import json
import os
from pathlib import Path

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse

from pydantic import BaseModel, Field
from log import log
from helpers import render, get_device_user, _get_user_xp, _get_leaderboard, _award_xp, XP_REWARDS
from database import execute_async, query_async, query_one_async, init_db

router = APIRouter()

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
        boss_q["options"] = json.loads(boss_q["options"])

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
    """Return quiz questions for a lesson as [{question, options, answer, explanation}, ...]."""
    rows = await query_async(
        "SELECT id, question, options, correct_index, explanation FROM quiz_questions WHERE lesson_id = %s ORDER BY id",
        (lesson_id,)
    )
    result = []
    for r in rows:
        opts = r["options"]
        if isinstance(opts, str):
            opts = json.loads(opts)
        
        ci = r["correct_index"]
        try:
            ci = int(ci)
        except (ValueError, TypeError):
            ci = 0

        # Get actual correct option text
        ans_text = ""
        if isinstance(opts, list) and 0 <= ci < len(opts):
            ans_text = opts[ci]
        else:
            ans_text = str(ci)

        result.append({
            "id": r["id"],
            "question": r["question"],
            "options": opts,
            "answer": ans_text,
            "explanation": r["explanation"] or ""
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
            "GROUP BY l.id ORDER BY l.topic_code, l.sort_order"
        )
        return [{"id": r["id"], "topic_code": r["topic_code"], "title": r["title"],
                 "total": r["total"], "known": 0, "review": 0} for r in rows]

    user_id = user["id"]
    rows = await query_async(
        "SELECT l.id, l.topic_code, l.title, COUNT(q.id) as total "
        "FROM lessons l LEFT JOIN quiz_questions q ON q.lesson_id = l.id "
        "GROUP BY l.id ORDER BY l.topic_code, l.sort_order"
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

    # ── System ──
    db_path = "/opt/wlvcs/app/data/wlvcs.db"
    db_size_mb = 0
    db_ok = os.path.exists(db_path)
    if db_ok:
        db_size_mb = round(os.path.getsize(db_path) / (1024 * 1024), 1)

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
        usage = shutil.disk_usage("/opt/wlvcs")
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
            "lessons_per_topic": lessons_per_topic
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
    return {"db_type": "PostgreSQL", "database": "wlv_kb", "host": "localhost"}
@router.post("/admin/rename")
async def admin_rename(request: Request):
    """Rename a user/device from the admin page. Updates both users table
    and activity dashboard device names."""
    form = await request.form()
    user_id = form.get("user_id", "").strip()
    new_name = form.get("name", "").strip()
    if not user_id or not new_name:
        return RedirectResponse(url="/admin", status_code=303)


# ─── XP / Gamification API ───

@router.get("/api/xp")
async def api_get_xp(request: Request):
    """Get current user's XP and level info."""
    user = get_device_user(request)
    if not user:
        return {"xp": 0, "level": 1, "level_name": "Beginner", "next_level_xp": 100, "progress_pct": 0}
    return _get_user_xp(user["id"])


@router.get("/api/leaderboard")
async def api_leaderboard():
    """Get top users by XP."""
    return _get_leaderboard(20)


@router.get("/leaderboard", response_class=HTMLResponse)
async def leaderboard_page(request: Request):
    """Leaderboard page."""
    user = get_device_user(request)
    user_xp = _get_user_xp(user["id"]) if user else None
    leaderboard = _get_leaderboard(20)
    return render("leaderboard.html", active="leaderboard",
                  leaderboard=leaderboard, user_xp=user_xp)


# ─── Admin rename ───

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
