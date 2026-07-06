"""Routes: home, lessons, topic, lesson, review, progress, search, get_question"""
import json
from datetime import date, datetime, timedelta

from fastapi import APIRouter, Request, Query, HTTPException
from fastapi.responses import HTMLResponse

from helpers import render, get_icon, get_device_user, _get_user_xp
from log import log
from database import query_async, query_one_async

router = APIRouter()


@router.get("/", response_class=HTMLResponse)
async def home(request: Request):
    user = get_device_user(request)
    streak = 0
    due_reviews = []

    if user:
        # Study streak
        study_dates = await query_async(
            "SELECT DISTINCT DATE(answered_at) as d FROM quiz_attempts WHERE user_id = %s ORDER BY d DESC",
            (user["id"],)
        )
        study_date_set = {r["d"] for r in study_dates}
        check_date = date.today()
        while check_date.isoformat() in study_date_set:
            streak += 1
            check_date -= timedelta(days=1)

        # Due reviews
        due = await query_async("""
            SELECT rs.*, l.title as lesson_title, t.title as topic_title, t.code as topic_code
            FROM review_schedule rs
            JOIN lessons l ON l.id = rs.lesson_id
            JOIN topics t ON t.code = l.topic_code
            WHERE rs.user_id = %s AND (rs.next_review::date <= CURRENT_DATE OR rs.next_review IS NULL)
            ORDER BY rs.next_review ASC
            LIMIT 10
        """, (user["id"],))

        today = date.today()
        for r in due:
            r = dict(r)
            nr = r.get("next_review")
            r["overdue"] = nr is None or (isinstance(nr, str) and datetime.strptime(nr, "%Y-%m-%d").date() < today) or (
                hasattr(nr, 'date') and nr.date() < today)
            # Count questions needing review in this lesson
            mastery = await query_one_async("""
                SELECT COUNT(DISTINCT q.id) as total,
                       SUM(CASE WHEN qm.consecutive_correct >= 3 THEN 1 ELSE 0 END) as mastered,
                       SUM(CASE WHEN qm2.total_attempts > 0 AND COALESCE(qm3.consecutive_correct, 0) < 3 THEN 1 ELSE 0 END) as needs_review
                FROM quiz_questions q
                LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s AND qm.consecutive_correct >= 3
                LEFT JOIN question_mastery qm2 ON qm2.question_id = q.id AND qm2.user_id = %s AND qm2.total_attempts > 0
                LEFT JOIN question_mastery qm3 ON qm3.question_id = q.id AND qm3.user_id = %s AND qm3.consecutive_correct < 3
                WHERE q.lesson_id = %s
            """, (user["id"], user["id"], user["id"], r["lesson_id"]))
            r["needs_review"] = mastery["needs_review"] or 0 if mastery else 0
            due_reviews.append(r)

    return render("home.html",
        active="home",
        streak=streak,
        due_reviews=due_reviews,
        user_xp=_get_user_xp(user["id"]) if user else None
    )


@router.get("/lessons", response_class=HTMLResponse)
async def lessons_page(request: Request):
    topics = await query_async("SELECT * FROM topics ORDER BY sort_order")
    stats = await query_async("""
        SELECT t.code, t.title,
               COUNT(DISTINCT l.id) as lesson_count,
               COUNT(DISTINCT q.id) as question_count
        FROM topics t
        LEFT JOIN lessons l ON l.topic_code = t.code
        LEFT JOIN quiz_questions q ON q.lesson_id = l.id
        GROUP BY t.code, t.title, t.sort_order
        ORDER BY t.sort_order
    """)

    total_lessons = sum(s["lesson_count"] for s in stats)
    total_questions = sum(s["question_count"] for s in stats)

    mastery_data = {}
    user = get_device_user(request)
    if user:
        rows = await query_async("""
            SELECT l.topic_code, COUNT(DISTINCT qm.question_id) as mastered
            FROM question_mastery qm
            JOIN quiz_questions q ON q.id = qm.question_id
            JOIN lessons l ON l.id = q.lesson_id
            WHERE qm.user_id = %s AND qm.consecutive_correct >= 3
            GROUP BY l.topic_code
        """, (user["id"],))
        for r in rows:
            mastery_data[r["topic_code"]] = {"mastered": r["mastered"]}

    for s in stats:
        code = s["code"]
        if code in mastery_data:
            mastery_data[code]["total"] = s["question_count"]
        else:
            mastery_data[code] = {"mastered": 0, "total": s["question_count"]}

    all_lessons = await get_all_lessons_with_topics()

    return render("lessons.html",
        active="lessons",
        topics=topics,
        stats=stats,
        total_lessons=total_lessons,
        total_questions=total_questions,
        mastery_data=mastery_data,
        all_lessons=all_lessons
    )

async def get_all_lessons_with_topics():
    return await query_async("""
        SELECT l.id, l.topic_code, l.title, l.sort_order as lesson_sort,
               t.title as topic_title, t.component, t.sort_order as topic_sort
        FROM lessons l
        JOIN topics t ON t.code = l.topic_code
        ORDER BY t.sort_order, l.sort_order
    """)


@router.get("/topic/{code}", response_class=HTMLResponse)
async def topic_page(code: str, request: Request):
    topic = await query_one_async("SELECT * FROM topics WHERE code = %s", (code,))
    if not topic:
        raise HTTPException(404, "Topic not found")
    
    lessons = await query_async("""
        SELECT l.*,
               (SELECT COUNT(*) FROM quiz_questions q WHERE q.lesson_id = l.id) as question_count
        FROM lessons l
        WHERE l.topic_code = %s
        ORDER BY l.sort_order
    """, (code,))
    
    user = get_device_user(request)
    lesson_progress = {}
    if user:
        for l in lessons:
            row = await query_one_async("""
                SELECT COUNT(*) as attempted,
                       SUM(CASE WHEN qm.consecutive_correct >= 3 THEN 1 ELSE 0 END) as mastered
                FROM quiz_questions q
                LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
                WHERE q.lesson_id = %s
            """, (user["id"], l["id"]))
            lesson_progress[str(l["id"])] = {
                "attempted": row["attempted"] if row else 0,
                "mastered": row["mastered"] if row else 0,
                "total": l["question_count"]
            }
            
    icon = get_icon(code)
    return render("topic.html",
        active="topic",
        topic=topic,
        lessons=lessons,
        lesson_progress=lesson_progress,
        icon=icon
    )


@router.get("/lesson/{lesson_id}", response_class=HTMLResponse)
async def lesson_page(lesson_id: int, request: Request):
    lesson = await query_one_async("""
        SELECT l.*, t.code as topic_code, t.title as topic_title
        FROM lessons l
        JOIN topics t ON t.code = l.topic_code
        WHERE l.id = %s
    """, (lesson_id,))
    if not lesson:
        raise HTTPException(404, "Lesson not found")

    log("lesson_view", device=request.state.device_id, lesson_id=lesson_id, topic=lesson.get("topic_code", ""))

    questions = await query_async("SELECT * FROM quiz_questions WHERE lesson_id = %s ORDER BY id", (lesson_id,))
    questions_list = []
    for q in questions:
        qd = dict(q)
        if qd.get("options"):
            try:
                qd["options"] = json.loads(qd["options"])
            except (json.JSONDecodeError, TypeError):
                pass
        questions_list.append(qd)

    prev_lesson = await query_one_async("""
        SELECT id, title FROM lessons
        WHERE topic_code = %s AND sort_order < %s
        ORDER BY sort_order DESC LIMIT 1
    """, (lesson["topic_code"], lesson["sort_order"]))

    next_lesson = await query_one_async("""
        SELECT id, title FROM lessons
        WHERE topic_code = %s AND sort_order > %s
        ORDER BY sort_order ASC LIMIT 1
    """, (lesson["topic_code"], lesson["sort_order"]))

    icon = get_icon(lesson["topic_code"])

    # Previous/next section (topic-level navigation)
    prev_section = None
    next_section = None
    all_topics = await query_async(
        "SELECT code, title FROM topics ORDER BY code"
    )
    for i, t in enumerate(all_topics):
        if t["code"] == lesson["topic_code"]:
            if i > 0:
                prev_topic = all_topics[i-1]
                first_lesson = await query_one_async(
                    "SELECT id, title FROM lessons WHERE topic_code = %s ORDER BY sort_order LIMIT 1",
                    (prev_topic["code"],)
                )
                if first_lesson:
                    prev_section = {**first_lesson, "topic_title": prev_topic["title"]}
            if i < len(all_topics) - 1:
                next_topic = all_topics[i+1]
                first_lesson = await query_one_async(
                    "SELECT id, title FROM lessons WHERE topic_code = %s ORDER BY sort_order LIMIT 1",
                    (next_topic["code"],)
                )
                if first_lesson:
                    next_section = {**first_lesson, "topic_title": next_topic["title"]}
            break

    boss_unlocked = False
    boss_passed = False
    user = get_device_user(request)
    if user:
        mastery_row = await query_one_async("""
            SELECT COUNT(DISTINCT q.id) as total,
                   COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) as mastered
            FROM quiz_questions q
            LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
            WHERE q.lesson_id = %s
        """, (user["id"], lesson_id))
        total_q = mastery_row["total"] if mastery_row else 0
        mastered_q = mastery_row["mastered"] if mastery_row else 0
        if total_q > 0 and mastered_q >= total_q:
            boss_unlocked = True
            boss_result = await query_one_async(
                "SELECT passed FROM boss_battle_results WHERE user_id = %s AND lesson_id = %s",
                (user["id"], lesson_id)
            )
            boss_passed = bool(boss_result and boss_result["passed"])

    return render("lesson.html",
        active="lesson",
        lesson=lesson,
        questions=questions_list,
        prev_lesson=prev_lesson,
        next_lesson=next_lesson,
        icon=icon,
        boss_unlocked=boss_unlocked,
        boss_passed=boss_passed,
        prev_section=prev_section,
        next_section=next_section
    )


@router.get("/review", response_class=HTMLResponse)
async def review_page(request: Request):
    user = get_device_user(request)
    if not user:
        return render("review.html", reviews=[], overdue=[], due_today=[], upcoming=[], active="review")

    due = await query_async("""
        SELECT rs.*, l.title as lesson_title, t.title as topic_title, t.code as topic_code
        FROM review_schedule rs
        JOIN lessons l ON l.id = rs.lesson_id
        JOIN topics t ON t.code = l.topic_code
        WHERE rs.user_id = %s AND (rs.next_review::date <= CURRENT_DATE OR rs.next_review IS NULL)
        ORDER BY rs.next_review ASC
    """, (user["id"],))

    for r in due:
        nr = r.get("next_review")
        if nr and isinstance(nr, str):
            try:
                r["next_review"] = datetime.fromisoformat(nr)
            except ValueError:
                pass

        mastery = await query_one_async("""
            SELECT COUNT(DISTINCT q.id) as total_questions,
                   SUM(CASE WHEN qm.consecutive_correct >= 3 THEN 1 ELSE 0 END) as mastered,
                   SUM(CASE WHEN qm2.total_attempts > 0 THEN 1 ELSE 0 END) as attempted,
                   SUM(CASE WHEN qm3.consecutive_correct < 3 AND qm3.total_attempts > 0 THEN 1 ELSE 0 END) as needs_review
            FROM quiz_questions q
            LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s AND qm.consecutive_correct >= 3
            LEFT JOIN question_mastery qm2 ON qm2.question_id = q.id AND qm2.user_id = %s AND qm2.total_attempts > 0
            LEFT JOIN question_mastery qm3 ON qm3.question_id = q.id AND qm3.user_id = %s AND qm3.consecutive_correct < 3 AND qm3.total_attempts > 0
            WHERE q.lesson_id = %s
        """, (user["id"], user["id"], user["id"], r["lesson_id"]))

        r["total_questions"] = mastery["total_questions"] or 0 if mastery else 0
        r["mastered"] = mastery["mastered"] or 0 if mastery else 0
        r["attempted"] = mastery["attempted"] or 0 if mastery else 0
        r["needs_review"] = mastery["needs_review"] or 0 if mastery else 0

    today = date.today()
    overdue = [r for r in due if r.get("next_review") is None or (
        isinstance(r["next_review"], str) and datetime.strptime(r["next_review"], "%Y-%m-%d").date() < today
    ) or (
        isinstance(r["next_review"], datetime) and r["next_review"].date() < today
    )]
    due_today = [r for r in due if (
        isinstance(r.get("next_review"), str) and datetime.strptime(r["next_review"], "%Y-%m-%d").date() == today
    ) or (
        isinstance(r.get("next_review"), datetime) and r["next_review"].date() == today
    )]
    upcoming = [r for r in due if r not in overdue and r not in due_today]

    return render("review.html",
        active="review",
        reviews=due,
        overdue=overdue,
        due_today=due_today,
        upcoming=upcoming,
        now=date.today()
    )


@router.get("/progress", response_class=HTMLResponse)
async def progress_page(request: Request):
    user = get_device_user(request)
    if not user:
        return render("progress.html", active="progress", topics_data=[], overall=None, last_14_days=[], mastery_data={}, review_stats={}, weakest_lessons=[], type_breakdown=[])

    user_id = user["id"]

    topics_data = await query_async("""
        SELECT t.code, t.title, t.component,
               COUNT(DISTINCT l.id) as total_lessons,
               COUNT(DISTINCT q.id) as total_questions,
               COALESCE(COUNT(DISTINCT qm.question_id), 0) as attempted,
               COALESCE(COUNT(CASE WHEN qm.consecutive_correct >= 3 THEN 1 END), 0) as mastered,
               COALESCE(COUNT(CASE WHEN qm.total_attempts > 0 AND qm.consecutive_correct < 3 THEN 1 END), 0) as needs_work
        FROM topics t
        LEFT JOIN lessons l ON l.topic_code = t.code
        LEFT JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.code, t.title, t.component, t.sort_order
        ORDER BY t.sort_order
    """, (user_id,))

    overall = await query_one_async("""
        SELECT
            COUNT(DISTINCT question_id) as unique_questions,
            (SELECT COUNT(*) FROM question_mastery WHERE user_id = %s AND consecutive_correct >= 3) as mastered
        FROM quiz_attempts WHERE user_id = %s
    """, (user_id, user_id))

    if overall and overall["unique_questions"] and overall["unique_questions"] > 0:
        correct_latest_row = await query_one_async("""
            SELECT COUNT(*) as correct_count FROM quiz_attempts qa
            WHERE qa.user_id = %s AND qa.correct = TRUE
            AND qa.id IN (
                SELECT MAX(id) FROM quiz_attempts WHERE user_id = %s GROUP BY question_id
            )
        """, (user_id, user_id))
        overall["correct_latest"] = correct_latest_row["correct_count"] if correct_latest_row else 0
        overall["accuracy_pct"] = round(overall["correct_latest"] / overall["unique_questions"] * 100)
    else:
        overall["correct_latest"] = 0
        overall["accuracy_pct"] = 0

    study_rows = await query_async("""
        SELECT DISTINCT DATE(answered_at) as study_date
        FROM quiz_attempts WHERE user_id = %s
    """, (user_id,))
    study_dates_set = set()
    for r in study_rows:
        if r["study_date"]:
            sd = r["study_date"]
            if isinstance(sd, str):
                study_dates_set.add(sd)
            else:
                study_dates_set.add(sd.isoformat() if hasattr(sd, 'isoformat') else str(sd))

    last_14_days = []
    for i in range(13, -1, -1):
        d = date.today() - timedelta(days=i)
        d_str = d.isoformat()
        last_14_days.append({
            "date_str": d_str,
            "label": d.strftime("%a %d %b"),
            "studied": d_str in study_dates_set
        })

    mastery_rows = await query_async("""
        SELECT l.topic_code, COUNT(DISTINCT qm.question_id) as mastered
        FROM question_mastery qm
        JOIN quiz_questions q ON q.id = qm.question_id
        JOIN lessons l ON l.id = q.lesson_id
        WHERE qm.user_id = %s AND qm.consecutive_correct >= 3
        GROUP BY l.topic_code
    """, (user_id,))
    mastery_data = {}
    for r in mastery_rows:
        mastery_data[r["topic_code"]] = r["mastered"]

    stats = await query_async("""
        SELECT t.code, COUNT(DISTINCT q.id) as question_count
        FROM topics t
        LEFT JOIN lessons l ON l.topic_code = t.code
        LEFT JOIN quiz_questions q ON q.lesson_id = l.id
        GROUP BY t.code
    """)
    for s in stats:
        code = s["code"]
        if code in mastery_data:
            mastery_data[code] = {"mastered": mastery_data[code], "total": s["question_count"]}
        else:
            mastery_data[code] = {"mastered": 0, "total": s["question_count"]}

    today_str = date.today().isoformat()
    future_str = (date.today() + timedelta(days=7)).isoformat()
    review_stats = await query_one_async("""
        SELECT
            COUNT(CASE WHEN rs.next_review::date < %s THEN 1 END) as overdue,
            COUNT(CASE WHEN rs.next_review::date = %s THEN 1 END) as due_today,
            COUNT(CASE WHEN rs.next_review::date > %s AND rs.next_review::date <= %s THEN 1 END) as upcoming
        FROM review_schedule rs
        WHERE rs.user_id = %s
    """, (today_str, today_str, today_str, future_str, user_id))
    if not review_stats:
        review_stats = {"overdue": 0, "due_today": 0, "upcoming": 0}

    weakest = await query_async("""
        SELECT l.id, l.title, l.topic_code, t.title as topic_title,
               SUM(qm.total_correct) as total_correct,
               SUM(qm.total_attempts) as total_attempts
        FROM question_mastery qm
        JOIN quiz_questions q ON q.id = qm.question_id
        JOIN lessons l ON l.id = q.lesson_id
        JOIN topics t ON t.code = l.topic_code
        WHERE qm.user_id = %s
        GROUP BY l.id
        HAVING total_attempts > 0
        ORDER BY CAST(total_correct AS REAL) / total_attempts ASC
        LIMIT 5
    """, (user_id,))
    for w in weakest:
        w["accuracy"] = round(w["total_correct"] / w["total_attempts"] * 100) if w["total_attempts"] > 0 else 0

    type_breakdown = await query_async("""
        SELECT q.question_type,
               COUNT(DISTINCT qm.question_id) as attempted,
               SUM(qm.total_correct) as correct,
               SUM(qm.total_attempts) as attempts
        FROM question_mastery qm
        JOIN quiz_questions q ON q.id = qm.question_id
        WHERE qm.user_id = %s
        GROUP BY q.question_type
        ORDER BY attempted DESC
    """, (user_id,))
    type_labels = {
        "mcq": "Multiple Choice", "true_false": "True / False",
        "ordering": "Ordering", "cloze": "Fill in the Blank",
        "multiple_select": "Multi-Select"
    }
    for tb in type_breakdown:
        tb["accuracy"] = round(tb["correct"] / tb["attempts"] * 100) if tb["attempts"] > 0 else 0
        tb["label"] = type_labels.get(tb["question_type"], tb["question_type"])

    component_data = await query_async("""
        SELECT t.component,
               COUNT(DISTINCT q.id) as total_questions,
               COALESCE(COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END), 0) as mastered
        FROM topics t
        LEFT JOIN lessons l ON l.topic_code = t.code
        LEFT JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.component ORDER BY t.component
    """, (user_id,))

    study_dates = await query_async(
        "SELECT DISTINCT DATE(answered_at) as d FROM quiz_attempts WHERE user_id = %s ORDER BY d DESC",
        (user_id,)
    )
    streak = 0
    check_date = date.today()
    study_date_set = {r["d"] for r in study_dates}
    while check_date.isoformat() in study_date_set:
        streak += 1
        check_date -= timedelta(days=1)

    return render("progress.html",
        active="progress",
        topics_data=topics_data,
        overall=overall,
        last_14_days=last_14_days,
        mastery_data=mastery_data,
        review_stats=review_stats,
        weakest_lessons=weakest,
        type_breakdown=type_breakdown,
        component_data=component_data,
        streak=streak
    )


@router.get("/search", response_class=HTMLResponse)
async def search_page(q: str = Query("", max_length=100)):
    results = []
    query_text = q.strip()
    if query_text:
        like = f"%{query_text}%"
        rows = await query_async("""
            SELECT id, topic_code, title, substr(content, 1, 200) as content_preview
            FROM lessons WHERE title LIKE ? OR content LIKE ?
            ORDER BY sort_order LIMIT 30
        """, (like, like))
        for r in rows:
            rd = dict(r)
            raw = rd.get("content_preview", "")
            clean = __import__("re").sub(r"<[^>]+>", "", raw)
            clean = clean.replace("&nbsp;", " ").replace("&amp;", "&")
            clean = " ".join(clean.split())
            if len(clean) > 160:
                clean = clean[:157] + "..."
            rd["content_preview"] = clean
            rd["type"] = "lesson"
            rd["url"] = f"/lesson/{rd['id']}"
            results.append(rd)

        resources_list = [
            {"id": 0, "title": "Reading Section — Language Analysis Guide", "desc": "How to analyse language in fiction extracts: identifying techniques, explaining effects, and using subject terminology.", "url": "/static/reading-language-guide.html", "tags": "reading language analysis techniques"},
            {"id": 0, "title": "Writing Section — Creative Writing Guide", "desc": "Structure, vocabulary, and techniques for descriptive and narrative writing. Includes planning frameworks and model answers.", "url": "/static/writing-creative-guide.html", "tags": "writing creative descriptive narrative"},
            {"id": 0, "title": "Mnemonic Reference Sheet", "desc": "All key memory devices in one printable page. Language techniques, structural devices, SPaG rules, and writing frameworks.", "url": "/static/mnemonics.html", "tags": "mnemonics memory devices revision"},
            {"id": 0, "title": "Exam Command Word Guide", "desc": "What each exam word means — State, Describe, Explain, Compare, Evaluate. PEEL structure, mark allocation, common mistakes.", "url": "/static/command-words.html", "tags": "command words exam technique peel"},
            {"id": 0, "title": "Language Techniques Quick Reference", "desc": "One-page cards for each key language technique: simile, metaphor, personification, alliteration, onomatopoeia, and more.", "url": "/static/language-techniques.html", "tags": "quick reference cards language techniques"},
            {"id": 0, "title": "Structural Devices Quick Reference", "desc": "One-page cards for structural devices: foreshadowing, juxtaposition, cyclical structure, flashback, and more.", "url": "/static/structural-devices.html", "tags": "quick reference cards structural devices"},
            {"id": 0, "title": "SPaG Practice Worksheet", "desc": "21 questions covering spelling, punctuation, and grammar. Includes comma splices, apostrophes, and sentence types.", "url": "/static/practice-spag.pdf", "tags": "spag spelling punctuation grammar worksheet practice"},
        ]
        ql = query_text.lower()
        for res in resources_list:
            search_text = (res["title"] + " " + res["desc"] + " " + res["tags"]).lower()
            if ql in search_text:
                clean = res["desc"]
                if len(clean) > 160:
                    clean = clean[:157] + "..."
                results.append({
                    "id": 0,
                    "topic_code": "📦",
                    "title": res["title"],
                    "content_preview": clean,
                    "type": "resource",
                    "url": res["url"]
                })
    return render("search.html", active="search", query=query_text, results=results)


@router.get("/api/quiz/{question_id}")
async def get_question(question_id: int):
    q = await query_one_async("SELECT * FROM quiz_questions WHERE id = %s", (question_id,))
    if not q:
        raise HTTPException(404, "Question not found")
    qd = dict(q)
    if qd.get("options"):
        try:
            qd["options"] = json.loads(qd["options"])
        except (json.JSONDecodeError, TypeError):
            pass
    return qd
