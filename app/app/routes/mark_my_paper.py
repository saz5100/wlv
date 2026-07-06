"""
Writing Practice — SEND Certificate L2 grading pipeline.
Upload PDFs, verify extracted text, get AI-marked reports against SEND mark schemes.
"""
import json, os, re, uuid, tempfile, traceback
from pathlib import Path
from fastapi import APIRouter, Request, Form, UploadFile, File, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from database import query_async, query_one_async, execute_async
from helpers import render
from question_bank import get_paper, get_paper_questions, ALL_PAPERS

router = APIRouter()
BASE_DIR = Path(__file__).resolve().parent.parent

# ─── Past paper definitions ────────────────────────────────────────────────
# Imported from question_bank.py: ALL_PAPERS
PAPERS = ALL_PAPERS

# ─── Helpers ───────────────────────────────────────────────────────────────

def extract_text_from_pdf(file_bytes: bytes) -> str:
    """Extract text from a digital PDF using pypdf."""
    try:
        from pypdf import PdfReader
        import io
        reader = PdfReader(io.BytesIO(file_bytes))
        pages = []
        for page in reader.pages:
            t = page.extract_text() or ""
            pages.append(t)
        return "\n\n".join(pages)
    except ImportError:
        return ""
    except Exception:
        return ""


def parse_questions_from_text(text: str) -> list:
    """Try to split extracted PDF text into question-answer blocks.
    Returns list of {number, text} dicts."""
    if not text.strip():
        return []
    questions = []
    # Look for numbered questions like "1.", "1)", "Q1."
    parts = re.split(r'(?:^|\n)\s*(?:Q(?:uestion)?\s*)?(\d+)[.)]\s*', text.strip(), flags=re.MULTILINE)
    # parts will be [before, num1, text1, num2, text2, ...]
    if len(parts) < 3:
        # No clear numbering — return as single blob
        return [{"number": 1, "text": text.strip()}]
    i = 1
    while i < len(parts) - 1:
        num = int(parts[i])
        txt = parts[i + 1].strip()
        questions.append({"number": num, "text": txt})
        i += 2
    if not questions:
        questions.append({"number": 1, "text": text.strip()})
    return questions


def get_mark_scheme_for_question(question_text: str) -> dict:
    """Retrieve the most relevant mark scheme from PostgreSQL for a question."""
    try:
        import psycopg2
        from database import get_db_cursor
        with get_db_cursor() as cur:
            # Try exact match first
            cur.execute(
                "SELECT id, topic, marks, question, mark_scheme, model_answer, key_terms "
                "FROM mark_schemes WHERE question ILIKE %s LIMIT 1",
                (f"%{question_text[:60]}%",)
            )
            row = cur.fetchone()
            if row:
                return dict(row)
            # Fallback: keyword match
            words = [w for w in re.findall(r'\w+', question_text.lower()) if len(w) > 3]
            if words:
                like_clauses = " OR ".join([f"question ILIKE '%{w}%'" for w in words[:5]])
                cur.execute(
                    f"SELECT id, topic, marks, question, mark_scheme, model_answer, key_terms "
                    f"FROM mark_schemes WHERE {like_clauses} LIMIT 1"
                )
                row = cur.fetchone()
                if row:
                    return dict(row)
    except Exception:
        pass
    return {}


async def call_ai_marker(question_text: str, student_answer: str, mark_scheme: dict) -> dict:
    """Call DeepSeek to mark a single question against its mark scheme."""
    import httpx

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key:
        return {"score": 0, "max_marks": mark_scheme.get("marks", 0),
                "feedback": "AI marking unavailable — no API key configured.",
                "strengths": [], "weaknesses": [], "key_terms_missed": []}

    max_marks = mark_scheme.get("marks", 0)
    scheme_text = mark_scheme.get("mark_scheme", "No mark scheme available.")
    model_ans = mark_scheme.get("model_answer", "")
    key_terms = mark_scheme.get("key_terms", "")

    prompt = f"""You are an expert SEND Certificate L2 examiner for SEND.

Question: {question_text}

Student's answer:
{student_answer}

Official mark scheme:
{scheme_text}

{"Model answer: " + model_ans if model_ans else ""}
{"Key terms expected: " + key_terms if key_terms else ""}

Mark this answer out of {max_marks} marks. Be fair but precise — award marks only where the student demonstrates the required knowledge.

Respond in this exact JSON format (no markdown, no code fences):
{{
  "score": <integer 0-{max_marks}>,
  "feedback": "<2-3 sentence explanation of the mark>",
  "strengths": ["<strength 1>", "<strength 2>"],
  "weaknesses": ["<weakness 1>", "<weakness 2>"],
  "key_terms_missed": ["<term 1>", "<term 2>"]
}}"""

    try:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                "https://api.deepseek.com/v1/chat/completions",
                headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
                json={
                    "model": "deepseek-chat",
                    "messages": [{"role": "user", "content": prompt}],
                    "temperature": 0.3,
                    "max_tokens": 1024
                }
            )
            if resp.status_code != 200:
                return {"score": 0, "max_marks": max_marks,
                        "feedback": f"AI API error: {resp.status_code}", "strengths": [], "weaknesses": [], "key_terms_missed": []}
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            # Strip markdown code fences if present
            content = re.sub(r'^```(?:json)?\s*', '', content.strip())
            content = re.sub(r'\s*```$', '', content)
            result = json.loads(content)
            result["max_marks"] = max_marks
            return result
    except Exception as e:
        return {"score": 0, "max_marks": max_marks,
                "feedback": f"AI marking error: {str(e)}", "strengths": [], "weaknesses": [], "key_terms_missed": []}



@router.get("/past-papers", response_class=HTMLResponse)
async def past_papers_list(request: Request):
    """List all past papers with download/mark/online options."""
    static_dir = BASE_DIR / "static" / "past-papers"
    # Build mapping: paper_id -> has_qp, has_ms
    # Filenames on disk: J277-01-2024-QP.pdf
    # Paper IDs: j277-01-jun2024
    # Map: paper_id -> {qp: filename, ms: filename}
    paper_files = {}
    if static_dir.exists():
        for f in static_dir.iterdir():
            if f.suffix == ".pdf" and f.stem.count("-") >= 2:
                parts = f.stem.split("-")
                if len(parts) >= 4:
                    paper_num = parts[1].lower()  # 01
                    year_str = parts[2]            # 2024
                    suffix = parts[-1]             # QP or MS
                    # Detect month from filename (e.g., "J277-01-2024-QP" = jun, "J277-01-2024-nov-QP" = nov)
                    filename_lower = f.stem.lower()
                    if "nov" in filename_lower.split("-") or "november" in filename_lower:
                        month_prefix = "nov"
                    else:
                        month_prefix = "jun"
                    try:
                        year = int(year_str)
                        paper_id = f"j277-{paper_num}-{month_prefix}{year_str}"
                        if paper_id not in paper_files:
                            paper_files[paper_id] = {"qp": None, "ms": None}
                        if suffix == "QP":
                            paper_files[paper_id]["qp"] = f.stem
                        elif suffix == "MS":
                            paper_files[paper_id]["ms"] = f.stem
                    except ValueError:
                        pass
    return render("past_papers.html", request=request, active="past-papers", papers=ALL_PAPERS, paper_files=paper_files)

# ─── Routes ────────────────────────────────────────────────────────────────
@router.get("/online-papers", response_class=HTMLResponse)
async def online_papers_list(request: Request):
    """List all papers available for filling online."""
    return render("online_papers.html", request=request, active="online-papers", papers=ALL_PAPERS)



@router.get("/online-paper/{paper_id}", response_class=HTMLResponse)
async def online_paper(request: Request, paper_id: str):
    """Render an online paper for the student to fill in."""
    paper = get_paper(paper_id)
    if not paper:
        return HTMLResponse("Paper not found", status_code=404)

    if not paper.get("active"):
        return render("online_paper.html", request=request, active="online-paper",
                      paper=paper, questions=[], total_marks=0, coming_soon=True)

    questions_data = get_paper_questions(paper_id)
    if not questions_data:
        return render("online_paper.html", request=request, active="online-paper",
                      paper=paper, questions=[], total_marks=0, coming_soon=True)

    questions = questions_data["questions"]
    total_marks = questions_data["total_marks"]

    return render("online_paper.html", request=request, active="online-paper",
                  paper=paper, questions=questions, total_marks=total_marks, coming_soon=False)


@router.get("/mark-my-paper", response_class=HTMLResponse)
async def mark_my_paper_landing(request: Request):
    """Landing page: list past papers, show previous attempts."""
    device_id = request.state.device_id
    # Get previous attempts
    attempts = await query_async(
        "SELECT id, paper_id, paper_label, total_marks, max_marks, "
        "ROUND((total_marks::float / NULLIF(max_marks, 0)) * 100) as percentage, "
        "grade, created_at "
        "FROM marked_papers WHERE device_id = %s ORDER BY created_at DESC LIMIT 20",
        (device_id,)
    )
    # Convert RealDictRow to plain dicts for Jinja2 compatibility
    attempts = [dict(a) for a in attempts]
    return render("mark_my_paper.html", request=request, active="mark-my-paper", papers=PAPERS, attempts=attempts)


@router.post("/mark-my-paper/upload")
async def mark_my_paper_upload(
    request: Request,
    paper_id: str = Form(...),
    file: UploadFile = File(None)
):
    """Upload a PDF, extract text, return question-by-question text for review."""
    device_id = request.state.device_id
    paper = next((p for p in PAPERS if p["id"] == paper_id), None)
    if not paper:
        return JSONResponse({"error": "Invalid paper selection"}, status_code=400)

    extracted_text = ""
    pdf_path = ""

    if file and file.filename:
        # Save PDF
        upload_dir = BASE_DIR / "data" / "uploads" / device_id
        upload_dir.mkdir(parents=True, exist_ok=True)
        safe_name = f"{paper_id}_{uuid.uuid4().hex[:8]}.pdf"
        pdf_path = str(upload_dir / safe_name)
        contents = await file.read()
        with open(pdf_path, "wb") as f:
            f.write(contents)
        # Extract text
        extracted_text = extract_text_from_pdf(contents)

    # Parse into questions
    questions = parse_questions_from_text(extracted_text)

    # If no questions from PDF, create blank ones from the mark scheme
    if not questions:
        # Create placeholder questions
        questions = [{"number": i + 1, "text": ""} for i in range(10)]

    return render("mark_my_paper.html", request=request, active="mark-my-paper", papers=PAPERS, paper=paper, pdf_path=pdf_path, questions=questions, mode="review")


@router.post("/mark-my-paper/submit")
async def mark_my_paper_submit(request: Request):
    """Submit answers for AI marking."""
    try:
        body = await request.json()
    except Exception:
        return JSONResponse({"error": "Invalid JSON body"}, status_code=400)

    device_id = request.state.device_id
    paper_id = body.get("paper_id", "")
    answers = body.get("answers", [])  # list of {number, text}

    paper = next((p for p in PAPERS if p["id"] == paper_id), None)
    if not paper:
        return JSONResponse({"error": "Invalid paper"}, status_code=400)

    # Mark each question
    results = []
    total_marks = 0
    max_marks = 0

    for ans in answers:
        q_text = ans.get("question_text", "")
        student_text = ans.get("text", "")
        ms = get_mark_scheme_for_question(q_text or student_text)
        marking = await call_ai_marker(q_text or f"Question {ans['number']}", student_text, ms)
        results.append({
            "number": ans["number"],
            "question_text": q_text or f"Question {ans['number']}",
            "student_answer": student_text,
            "score": marking.get("score", 0),
            "max_marks": marking.get("max_marks", ms.get("marks", 0)),
            "feedback": marking.get("feedback", ""),
            "strengths": marking.get("strengths", []),
            "weaknesses": marking.get("weaknesses", []),
            "key_terms_missed": marking.get("key_terms_missed", []),
        })
        total_marks += marking.get("score", 0)
        max_marks += marking.get("max_marks", ms.get("marks", 0))

    # Calculate grade
    pct = round((total_marks / max_marks * 100)) if max_marks > 0 else 0
    if pct >= 85:
        grade = "9"
    elif pct >= 75:
        grade = "8"
    elif pct >= 65:
        grade = "7"
    elif pct >= 55:
        grade = "6"
    elif pct >= 45:
        grade = "5"
    elif pct >= 35:
        grade = "4"
    elif pct >= 25:
        grade = "3"
    elif pct >= 15:
        grade = "2"
    else:
        grade = "1"

    # Save to DB
    attempt_id = uuid.uuid4().hex[:12]
    await execute_async(
        "INSERT INTO marked_papers (id, device_id, paper_id, paper_label, total_marks, max_marks, percentage, grade, results_json) "
        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (attempt_id, device_id, paper_id, paper["label"], total_marks, max_marks, pct, grade, json.dumps(results))
    )

    return JSONResponse({
        "attempt_id": attempt_id,
        "total_marks": total_marks,
        "max_marks": max_marks,
        "percentage": pct,
        "grade": grade,
        "results": results
    })


@router.get("/mark-my-paper/report/{attempt_id}", response_class=HTMLResponse)
async def mark_my_paper_report(request: Request, attempt_id: str):
    """Render the Seneca-style performance report."""
    row = await query_one_async(
        "SELECT * FROM marked_papers WHERE id = %s", (attempt_id,)
    )
    if not row:
        return HTMLResponse("Attempt not found", status_code=404)

    row = dict(row)
    results = json.loads(row["results_json"]) if isinstance(row["results_json"], str) else row["results_json"]

    return render("mark_my_paper_report.html", request=request, active="exam", attempt=row, results=results)


@router.get("/mark-my-paper/history", response_class=JSONResponse)
async def mark_my_paper_history(request: Request):
    """Return JSON history of attempts for the current device."""
    device_id = request.state.device_id
    rows = await query_async(
        "SELECT id, paper_label, total_marks, max_marks, percentage, grade, created_at "
        "FROM marked_papers WHERE device_id = %s ORDER BY created_at DESC LIMIT 50",
        (device_id,)
    )
    # Convert datetime to string for JSON serialization
    result = []
    for r in rows:
        d = dict(r)
        if "created_at" in d and d["created_at"] is not None:
            d["created_at"] = d["created_at"].isoformat()
        result.append(d)
    return JSONResponse(result)
