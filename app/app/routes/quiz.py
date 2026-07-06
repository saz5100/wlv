"""Routes: quiz submit, exam page, exam submit, exam history"""
import json
from datetime import datetime
import random

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse

from helpers import render, get_device_user, _check_rate_limit, _check_answer, _update_review_schedule, _grade_from_percentage
from log import log
from database import query_async, query_one_async, execute_async

from pydantic import BaseModel, Field

class QuizSubmitRequest(BaseModel):
    lesson_id: int = Field(gt=0)
    answers: dict = Field(default_factory=dict)

class ExamSubmitRequest(BaseModel):
    answers: dict = Field(default_factory=dict)
    question_ids: list[int] = Field(default_factory=list)
    time_taken: int = Field(default=0, ge=0)
    question_times: dict = Field(default_factory=dict)
    timestamps: dict = Field(default_factory=dict)


router = APIRouter()


def _calculate_grade(correct, total):
    pct = round(correct / total * 100) if total > 0 else 0
    return _grade_from_percentage(pct), pct


@router.post("/quiz/submit")
async def quiz_submit(data: QuizSubmitRequest, request: Request):
    user = get_device_user(request)
    if not user:
        raise HTTPException(400, "No user found")

    user_id = user["id"]
    lesson_id = data.lesson_id
    answers = data.answers

    questions = await query_async("SELECT * FROM quiz_questions WHERE lesson_id = %s", (lesson_id,))

    results = []
    correct_count = 0
    for q in questions:
        qid = q["id"]
        qid_str = str(qid)
        if qid_str in answers:
            user_answer = answers[qid_str]
            correct = _check_answer(q, user_answer)
        else:
            user_answer = None
            correct = False

        if correct:
            correct_count += 1

        await execute_async(
            "INSERT INTO quiz_attempts (user_id, question_id, correct) VALUES (%s, %s, %s)",
            (user_id, qid, correct)
        )
        was_correct = 1 if correct else 0
        await execute_async(
            "INSERT INTO question_mastery (user_id, question_id, consecutive_correct, total_correct, total_attempts, last_correct, updated_at) "
            "VALUES (%s, %s, %s, %s, %s, %s, CURRENT_TIMESTAMP) "
            "ON CONFLICT(user_id, question_id) DO UPDATE SET "
            "consecutive_correct = CASE WHEN question_mastery.last_correct = 1 AND %s = 1 THEN question_mastery.consecutive_correct + 1 "
            "WHEN %s = 1 THEN 1 ELSE 0 END, "
            "total_correct = question_mastery.total_correct + %s, "
            "total_attempts = question_mastery.total_attempts + 1, "
            "last_correct = %s, "
            "updated_at = CURRENT_TIMESTAMP",
            (user_id, qid, was_correct, was_correct, was_correct, was_correct,
             was_correct, was_correct, was_correct, was_correct))

        results.append({
            "question_id": qid,
            "question": q["question"],
            "question_type": q.get("question_type", "mcq") or "mcq",
            "user_answer": user_answer if user_answer is not None else "unanswered",
            "correct_index": q["correct_index"],
            "options": json.loads(q["options"]) if isinstance(q["options"], str) else q["options"],
            "correct": correct,
            "explanation": q.get("explanation", ""),
            "command_word": q.get("command_word"),
            "common_mistake": q.get("common_mistake"),
        })

    total = len(questions)
    score_pct = round(correct_count / total * 100) if total > 0 else 0

    _update_review_schedule(user_id, lesson_id, score_pct)

    log("quiz_submit", device=request.state.device_id, lesson_id=lesson_id, score=f"{correct_count}/{total}", pct=score_pct)

    return JSONResponse({
        "results": results,
        "score": {"correct": correct_count, "total": total, "percentage": score_pct}
    })


@router.get("/exam", response_class=HTMLResponse)
async def exam_page(request: Request):
    mode = request.query_params.get("mode", "landing")
    review_id = request.query_params.get("review")
    topics = await query_async("SELECT * FROM topics ORDER BY sort_order")
    user = get_device_user(request)

    if review_id and user:
        row = await query_one_async(
            "SELECT * FROM exam_results WHERE id = %s AND user_id = %s",
            (int(review_id), user["id"])
        )
        if row:
            row = dict(row)
            if isinstance(row.get("taken_at"), str):
                row["taken_at"] = datetime.fromisoformat(row["taken_at"].replace("Z", ""))
            
            # Parse fields
            for field in ["topic_breakdown", "type_breakdown", "difficulty_breakdown", "results", "question_times"]:
                if isinstance(row.get(field), str):
                    try:
                        row[field] = json.loads(row[field])
                    except (json.JSONDecodeError, TypeError):
                        pass

            # Load comparison result (previous exam)
            last_exam_compare = await query_one_async("""
                SELECT percentage FROM exam_results
                WHERE user_id = %s AND id < %s AND percentage > 0
                ORDER BY taken_at DESC LIMIT 1
            """, (user["id"], int(review_id)))

            return render("exam.html",
                active="exam",
                mode="results",
                last_exam=row,
                review_id=review_id,
                last_exam_compare=last_exam_compare,
                grade=_grade_from_percentage(row.get("percentage", 0))
            )

    # Optional filters (used by quickfire)
    topic_filter = request.query_params.get("topic", "")
    diff_filter = request.query_params.get("diff", "")
    try:
        diff_val = int(diff_filter) if diff_filter else 0
    except (ValueError, TypeError):
        diff_val = 0

    # No mode -> show landing page
    if not mode or mode == "landing":
        last_5 = []
        if user:
            rows = await query_async(
                "SELECT score, total, percentage, taken_at FROM exam_results WHERE user_id = %s AND percentage > 0 ORDER BY taken_at DESC LIMIT 5",
                (user["id"],)
            )
            for r in reversed(rows):
                last_5.append(r)
        return render("exam.html", active="exam", mode="landing", last_5=last_5, topics=topics)

    # Parse mode parameters
    if mode == "quickfire":
        count = 20
        timed = False
        duration_seconds = None
        display_label = "⚡ Quick Fire 20"
        if topic_filter:
            topic_name_q = await query_one_async("SELECT title FROM topics WHERE code = %s", (topic_filter,))
            tname = topic_name_q["title"] if topic_name_q else topic_filter
            display_label = f"⚡ Quick Fire — {tname}"
        if diff_val in (1, 2, 3):
            diff_names = {1: "Easy", 2: "Medium", 3: "Hard"}
            dname = diff_names[diff_val]
            display_label += f" ({dname})"
    elif mode == "custom":
        try:
            count = max(5, min(50, int(request.query_params.get("count", 20))))
        except (ValueError, TypeError):
            count = 20
        paper = request.query_params.get("paper", "0")
        try:
            paper_val = int(paper)
        except (ValueError, TypeError):
            paper_val = 0
        timed = request.query_params.get("timed", "0") == "1"
        try:
            duration_seconds = int(request.query_params.get("duration", 0)) * 60 if timed else None
        except (ValueError, TypeError):
            duration_seconds = None
        paper_label = f" · Paper {paper_val}" if paper_val in (1, 2) else ""
        display_label = f"🎯 Custom ({count} Q{paper_label}{' · ' + str(int(duration_seconds/60)) + 'min' if duration_seconds else ''})"
    elif mode == "mock":
        try:
            paper_val = int(request.query_params.get("paper", "1"))
        except (ValueError, TypeError):
            paper_val = 1
        if paper_val not in (1, 2):
            paper_val = 1
        count = 40
        timed = True
        duration_seconds = 45 * 60  # 45 mins for mock
        display_label = f"📝 Mock Exam — Paper {paper_val}"
    elif mode == "tf_rapidfire":
        count = 30
        timed = True
        duration_seconds = 90
        display_label = "⚡ True/False Rapid Fire"
        if topic_filter:
            topic_name_q = await query_one_async("SELECT title FROM topics WHERE code = %s", (topic_filter,))
            tname = topic_name_q["title"] if topic_name_q else topic_filter
            display_label = f"⚡ T/F Rapid Fire — {tname}"
    elif mode == "balanced":
        count = 20
        timed = False
        duration_seconds = None
        display_label = "🎯 Balanced Topic Quiz"
    elif mode == "cross_mock":
        count = 40
        timed = True
        duration_seconds = 45 * 60
        display_label = "📝 Cross-Paper Mock Exam"
    else:
        raise HTTPException(400, "Invalid exam mode")

    # Fetch questions
    query_sql = """
        SELECT q.id, q.question, q.options, q.correct_index, q.explanation, q.difficulty, q.question_type,
               l.title as lesson_title, l.topic_code, t.title as topic_title
        FROM quiz_questions q
        JOIN lessons l ON l.id = q.lesson_id
        JOIN topics t ON t.code = l.topic_code
        WHERE q.is_exam = 1
    """
    params_list = []

    if mode == "quickfire":
        if topic_filter:
            query_sql += " AND l.topic_code = %s"
            params_list.append(topic_filter)
        if diff_val in (1, 2, 3):
            query_sql += " AND q.difficulty = %s"
            params_list.append(diff_val)
    elif mode == "custom":
        if paper_val in (1, 2):
            query_sql += " AND l.paper = %s"
            params_list.append(paper_val)
    elif mode == "mock":
        query_sql += " AND l.paper = %s"
        params_list.append(paper_val)
    elif mode == "tf_rapidfire":
        query_sql += " AND q.question_type = 'true_false'"
        if topic_filter:
            query_sql += " AND l.topic_code = %s"
            params_list.append(topic_filter)
    elif mode == "balanced":
        pass  # handled below with per-topic selection
    elif mode == "cross_mock":
        pass  # no paper filter — mix both papers

    if mode == "balanced":
        query_sql = query_sql.replace("WHERE q.is_exam = 1", "WHERE q.is_exam = 1")
        questions_list = []
        topics = await query_async("SELECT code FROM topics ORDER BY sort_order")
        for t in topics:
            rows = await query_async(
                query_sql + " AND l.topic_code = %s ORDER BY RANDOM() LIMIT 2",
                tuple(params_list + [t["code"]])
            )
            for r in rows:
                qd = dict(r)
                if isinstance(qd.get("options"), str):
                    try:
                        qd["options"] = json.loads(qd["options"])
                    except (json.JSONDecodeError, TypeError):
                        pass
                questions_list.append(qd)
        random.shuffle(questions_list)
    else:
        query_sql += " ORDER BY RANDOM() LIMIT %s"
        params_list.append(count)
        questions = await query_async(query_sql, tuple(params_list))
        if not questions:
            raise HTTPException(400, "No questions found matching criteria")
        questions_list = []
        for q in questions:
            qd = dict(q)
            if isinstance(qd.get("options"), str):
                try:
                    qd["options"] = json.loads(qd["options"])
                except (json.JSONDecodeError, TypeError):
                    pass
            questions_list.append(qd)

    # Shuffle MCQ options to prevent position bias
    for q in questions_list:
        if q.get("question_type") == "mcq" and len(q["options"]) >= 2:
            opts = list(enumerate(q["options"]))
            correct_idx = q["correct_index"]
            random.shuffle(opts)
            q["options"] = [o[1] for o in opts]
            for new_idx, old_opt in enumerate(opts):
                if old_opt[0] == correct_idx:
                    q["correct_index"] = new_idx
                    break

    return render("exam.html",
        active="exam",
        mode="exam",
        questions=questions_list,
        total=len(questions_list),
        display_label=display_label,
        timed=timed,
        duration_seconds=duration_seconds
    )


@router.post("/exam/submit")
async def exam_submit(data: ExamSubmitRequest, request: Request):
    device_id = request.state.device_id
    allowed, wait = _check_rate_limit(device_id)
    if not allowed:
        return JSONResponse({"error": f"Please wait {wait}s", "retry_after": wait}, status_code=429)

    user = get_device_user(request)
    if not user:
        raise HTTPException(400, "No user found")

    answers = data.answers
    question_ids = data.question_ids
    time_taken = data.time_taken
    q_times = data.timestamps or data.question_times
    if not time_taken and q_times:
        try:
            time_taken = sum(int(v) for v in q_times.values() if str(v).isdigit())
        except Exception:
            time_taken = 0
    if not question_ids:
        raise HTTPException(400, "No questions to submit")

    # Fetch details
    placeholders = ",".join("%s" for _ in question_ids)
    questions = await query_async(
        f"SELECT q.id, q.question, q.options, q.correct_index, q.explanation, q.difficulty, q.question_type, "
        f"l.title as lesson_title, l.topic_code, t.title as topic_title "
        f"FROM quiz_questions q "
        f"JOIN lessons l ON l.id = q.lesson_id "
        f"JOIN topics t ON t.code = l.topic_code "
        f"WHERE q.id IN ({placeholders})",
        tuple(question_ids)
    )

    q_map = {q["id"]: q for q in questions}

    results = []
    correct_count = 0
    topic_scores = {}  # topic_code -> {correct, total, title}
    type_scores = {}   # type -> {correct, total}
    diff_scores = {}   # diff -> {correct, total}

    for qid in question_ids:
        q = q_map.get(int(qid))
        if not q:
            continue
        user_val = answers.get(str(qid))
        correct = _check_answer(q, user_val) if user_val is not None else False
        if correct:
            correct_count += 1

        opts = json.loads(q["options"]) if isinstance(q["options"], str) else q["options"]

        def _fmt_ans(val):
            if val is None:
                return "--- (unanswered)"
            qtype = q.get("question_type", "mcq") or "mcq"
            if qtype in ("mcq", "true_false"):
                try:
                    idx = int(val)
                    return opts[idx] if opts and 0 <= idx < len(opts) else str(val)
                except (ValueError, IndexError):
                    return str(val)
            elif qtype == "multiple_select":
                try:
                    idxs = [int(x.strip()) for x in val.split(",") if x.strip()]
                    return ", ".join(opts[i] for i in idxs if 0 <= i < len(opts))
                except:
                    return str(val)
            elif qtype == "ordering":
                try:
                    idxs = [int(x.strip()) for x in val.split(",") if x.strip()]
                    return " → ".join(opts[i] for i in idxs if 0 <= i < len(opts))
                except:
                    return str(val)
            return str(val)

        t_spent = q_times.get(str(qid)) or q_times.get(int(qid))
        time_spent = int(t_spent) if t_spent is not None else None

        results.append({
            "question_id": q["id"],
            "question": q["question"],
            "question_type": q.get("question_type", "mcq") or "mcq",
            "user_answer": _fmt_ans(user_val),
            "correct_index": q["correct_index"],
            "options": opts,
            "correct": correct,
            "explanation": q.get("explanation", ""),
            "topic_code": q["topic_code"],
            "topic_title": q["topic_title"],
            "lesson_title": q["lesson_title"],
            "difficulty": q.get("difficulty", 1),
            "command_word": q.get("command_word"),
            "common_mistake": q.get("common_mistake"),
            "time_spent": time_spent,
        })

        # Topic aggregation
        tc = q["topic_code"]
        if tc not in topic_scores:
            topic_scores[tc] = {"correct": 0, "total": 0, "title": q["topic_title"], "code": tc}
        topic_scores[tc]["total"] += 1
        if correct:
            topic_scores[tc]["correct"] += 1

        # Type aggregation
        qt = q.get("question_type", "mcq") or "mcq"
        if qt not in type_scores:
            type_scores[qt] = {"correct": 0, "total": 0}
        type_scores[qt]["total"] += 1
        if correct:
            type_scores[qt]["correct"] += 1

        # Difficulty aggregation
        diff_map = {1: "easy", 2: "medium", 3: "hard"}
        qd_lbl = diff_map.get(q.get("difficulty", 1), "easy")
        if qd_lbl not in diff_scores:
            diff_scores[qd_lbl] = {"correct": 0, "total": 0}
        diff_scores[qd_lbl]["total"] += 1
        if correct:
            diff_scores[qd_lbl]["correct"] += 1

    total = len(question_ids)
    grade, pct = _calculate_grade(correct_count, total)

    # Format aggregations for storage
    topic_breakdown = []
    for tc, v in topic_scores.items():
        v["pct"] = round(v["correct"] / v["total"] * 100)
        topic_breakdown.append(v)
    topic_breakdown.sort(key=lambda x: x["code"])

    type_breakdown = []
    type_labels = {"mcq": "MCQ", "true_false": "True/False", "ordering": "Ordering", "cloze": "Cloze", "multiple_select": "Multi-Select"}
    for qt, v in type_scores.items():
        label = type_labels.get(qt, qt)
        v["type"] = label
        v["label"] = label
        v["pct"] = round(v["correct"] / v["total"] * 100)
        type_breakdown.append(v)

    difficulty_breakdown = []
    for dlbl, v in diff_scores.items():
        v["difficulty"] = dlbl
        v["label"] = dlbl.capitalize()
        v["pct"] = round(v["correct"] / v["total"] * 100)
        difficulty_breakdown.append(v)

    # Fetch last exam before inserting the new one
    last_exam = await query_one_async(
        "SELECT score, total, percentage FROM exam_results WHERE user_id = %s ORDER BY id DESC LIMIT 1",
        (user["id"],)
    )
    last_exam_compare = {
        "score": last_exam["score"],
        "total": last_exam["total"],
        "percentage": last_exam["percentage"]
    } if last_exam else None

    # Insert attempt logs into quiz_attempts for spacing calculations
    for r in results:
        await execute_async(
            "INSERT INTO quiz_attempts (user_id, question_id, correct) VALUES (%s, %s, %s)",
            (user["id"], r["question_id"], 1 if r["correct"] else 0)
        )

    # Save exam result
    row_id = await execute_async("""
        INSERT INTO exam_results (user_id, score, total, percentage, results, topic_breakdown, type_breakdown, difficulty_breakdown, question_times, duration_seconds)
        VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """, (
        user["id"], correct_count, total, pct,
        json.dumps(results), json.dumps(topic_breakdown),
        json.dumps(type_breakdown), json.dumps(difficulty_breakdown),
        json.dumps(q_times), int(time_taken)
    ))

    log("exam_submit", device=request.state.device_id, score=f"{correct_count}/{total}", pct=pct, grade=grade)

    return {
        "exam_id": row_id,
        "results": results,
        "score": {
            "percentage": pct,
            "correct": correct_count,
            "total": total,
            "grade": grade,
        },
        "topic_breakdown": topic_breakdown,
        "type_breakdown": type_breakdown,
        "difficulty_breakdown": difficulty_breakdown,
        "last_exam_compare": last_exam_compare
    }


@router.get("/exam-history", response_class=HTMLResponse)
async def exam_history(request: Request):
    user = get_device_user(request)
    if not user:
        return render("exam_history.html", active="exam-history", exams=[], weak_spots=[], topic_trends={})

    rows = await query_async(
        "SELECT id, score, total, percentage, topic_breakdown, results, taken_at "
        "FROM exam_results WHERE user_id = %s AND percentage > 0 ORDER BY taken_at DESC",
        (user["id"],)
    )

    # ─── Written exam-style history ───
    written_rows = await query_async(
        "SELECT id, topic, marks, score, question, answer, feedback, taken_at "
        "FROM exam_style_results WHERE user_id = %s ORDER BY taken_at DESC LIMIT 50",
        (user["id"],)
    )
    written_exams = []
    for wr in written_rows:
        taken_at = wr["taken_at"]
        if isinstance(taken_at, str):
            taken_at = datetime.fromisoformat(taken_at.replace("Z", ""))
        written_exams.append({
            "id": wr["id"],
            "topic": wr["topic"],
            "marks": wr["marks"],
            "score": wr["score"],
            "question": wr["question"],
            "answer": wr["answer"],
            "feedback": wr["feedback"],
            "taken_at": taken_at,
        })
    if not rows:
        return render("exam_history.html", active="exam-history", exams=[], weak_spots=[], topic_trends={})

    exams = []
    wrong_map = {}  # question_text -> {count, topic, lesson, options, correct_index, explanation}
    topic_over_time = {}  # topic_code -> [{date, pct}]

    for row in rows:
        taken_at = row["taken_at"]
        if isinstance(taken_at, str):
            taken_at = datetime.fromisoformat(taken_at.replace("Z", ""))
        
        tb = row.get("topic_breakdown")
        if isinstance(tb, str):
            tb = json.loads(tb)
        
        res = row.get("results")
        if isinstance(res, str):
            res = json.loads(res)
        
        exam = {
            "id": row["id"],
            "score": row["score"],
            "total": row["total"],
            "percentage": row["percentage"],
            "taken_at": taken_at,
            "topic_breakdown": tb or [],
            "results": res or [],
        }
        exams.append(exam)

        # Aggregate wrong questions
        for q in (res or []):
            if not q.get("correct"):
                key = q.get("question", "")
                if key not in wrong_map:
                    wrong_map[key] = {
                        "question": key,
                        "count": 0,
                        "topic_code": q.get("topic_code", ""),
                        "topic_title": q.get("topic_title", ""),
                        "lesson": q.get("lesson", ""),
                        "correct_index": q.get("correct_index"),
                        "options": q.get("options", []),
                        "explanation": q.get("explanation", ""),
                    }
                wrong_map[key]["count"] += 1

        # Topic trends
        for t in (tb or []):
            code = t.get("code", "")
            if code not in topic_over_time:
                topic_over_time[code] = {"title": t.get("title", code), "history": []}
            topic_over_time[code]["history"].append({
                "date": taken_at,
                "pct": t.get("pct", 0),
                "correct": t.get("correct", 0),
                "total": t.get("total", 0),
            })

    # Aggregate topic stats across ALL exams
    agg_topics = {}
    for exam in exams:
        for t in (exam.get("topic_breakdown") or []):
            code = t.get("code", "")
            if code not in agg_topics:
                agg_topics[code] = {"code": code, "title": t.get("title", code), "correct": 0, "total": 0}
            agg_topics[code]["correct"] += t.get("correct", 0)
            agg_topics[code]["total"] += t.get("total", 0)
    for v in agg_topics.values():
        v["pct"] = round(v["correct"] / v["total"] * 100) if v["total"] else 0
    agg_topic_list = sorted(agg_topics.values(), key=lambda x: x["code"])

    # Sort weak spots by frequency (most wrong first)
    weak_spots = sorted(wrong_map.values(), key=lambda x: -x["count"])

    # Calculate overall trend (last exam vs first exam percentage)
    trend = None
    if len(exams) >= 2:
        first = exams[-1]
        last = exams[0]
        diff = last["percentage"] - first["percentage"]
        trend = {"diff": diff, "direction": "up" if diff > 0 else ("down" if diff < 0 else "flat")}

    return render("exam_history.html",
        active="exam-history",
        exams=exams,
        weak_spots=weak_spots[:10],
        topic_trends=topic_over_time,
        trend=trend,
        agg_topics=agg_topic_list,
        written_exams=written_exams,
    )
