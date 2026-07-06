"""Routes: tutor page, tutor suggestions, tutor chat (standard & stream), tutor profile, start session, advisor"""
import json
import os
from pathlib import Path
from datetime import date, datetime, timedelta

import httpx
from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse, JSONResponse

from helpers import render, get_device_user, _call_owui, _grade_from_percentage, query_async, query_one_async, FALLBACK_SYSTEM_PROMPT
from log import log
from pydantic import BaseModel, Field

class TutorChatMessage(BaseModel):
    role: str = Field(default="user", pattern="^(user|assistant|system)$")
    content: str = Field(default="", max_length=32768)

class TutorChatRequest(BaseModel):
    messages: list[TutorChatMessage] = Field(min_length=1, max_length=20)


router = APIRouter()

# --- Load Environment Config ---
BASE_DIR = Path(__file__).resolve().parent.parent
_env_path = BASE_DIR / ".env"
if _env_path.exists():
    for _line in _env_path.read_text().strip().splitlines():
        if "=" in _line and not _line.startswith("#"):
            _k, _v = _line.split("=", 1)
            os.environ.setdefault(_k.strip(), _v.strip())

DEEPSEEK_KEY = os.environ.get("DEEPSEEK_API_KEY")
DEEPSEEK_BASE = os.environ.get("DEEPSEEK_BASE", "https://api.deepseek.com/v1")
DEEPSEEK_MODEL = os.environ.get("DEEPSEEK_MODEL", "deepseek-chat")
OLLAMA_KEY = os.environ.get("OLLAMA_API_KEY")
OLLAMA_BASE = os.environ.get("OLLAMA_BASE", "https://ollama.com/v1")
OLLAMA_MODEL = os.environ.get("OLLAMA_MODEL", "deepseek-v4-flash")
LLM_MODEL = os.environ.get("LLM_MODEL", "deepseek-v4-flash")
OWUI_BASE = os.environ.get("OWUI_BASE", "http://chat.lan")
OWUI_MODEL = os.environ.get("OWUI_MODEL", "wlv--v1")
MAX_TOKENS = 4096

# --- LLM Tool Definitions ---
TOOL_DEFINITIONS = [
    {
        "type": "function",
        "function": {
            "name": "get_topic_breakdown",
            "description": "Get student's mastery percentage and score stats across all WLV topics",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_weak_questions",
            "description": "Get list of specific quiz questions the student has repeatedly failed",
            "parameters": {
                "type": "object",
                "properties": {
                    "topic": {"type": "string", "description": "Optional topic code (e.g. 1.1) to filter by"},
                    "limit": {"type": "integer", "description": "Max questions to return (default 5)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_lesson_content",
            "description": "Retrieve the exact study guide HTML text content of a specific lesson",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Lesson title or topic code keywords"}
                },
                "required": ["query"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_mistakes",
            "description": "Get details of the most recent wrong quiz answers the student submitted",
            "parameters": {
                "type": "object",
                "properties": {
                    "limit": {"type": "integer", "description": "Max mistakes to return (default 5)"}
                }
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_overdue_lessons",
            "description": "Get lessons that are due or overdue for review",
            "parameters": {"type": "object", "properties": {}}
        }
    },
    {
        "type": "function",
        "function": {
            "name": "get_knowledge_context",
            "description": "Search the WLV CS knowledge base for relevant concepts, definitions, and explanations. Automatically routes to curated OKF concepts (exact, high-stakes) or RAG vector search (exploratory, open-ended).",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "The topic or question to search for in the knowledge base"}
                },
                "required": ["query"]
            }
        }
    },
]


async def _call_llm(messages: list[dict], tools: list = None, stream: bool = False) -> httpx.Response:
    """Call the LLM via Ollama Cloud (primary) or DeepSeek native (fallback)."""
    errors = []

    # --- Attempt 1: Ollama Cloud ---
    payload = {
        "model": OLLAMA_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "stream": stream,
    }
    if tools:
        payload["tools"] = tools

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{OLLAMA_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {OLLAMA_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            if resp.status_code == 200:
                return resp
            errors.append(f"Ollama {resp.status_code}: {resp.text[:200]}")
        except Exception as e:
            errors.append(f"Ollama error: {e}")

    # --- Attempt 2: DeepSeek native (fallback) ---
    payload_ds = {
        "model": DEEPSEEK_MODEL,
        "messages": messages,
        "max_tokens": MAX_TOKENS,
        "stream": stream,
    }
    if tools:
        payload_ds["tools"] = tools

    async with httpx.AsyncClient(timeout=120) as client:
        try:
            resp = await client.post(
                f"{DEEPSEEK_BASE}/chat/completions",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload_ds,
            )
            if resp.status_code == 200:
                return resp
            if resp.status_code == 401:
                raise RuntimeError("AI Tutor unavailable - API key expired or invalid.")
            if resp.status_code == 402:
                raise RuntimeError("AI Tutor unavailable - insufficient credits or quota exceeded.")
            errors.append(f"DeepSeek {resp.status_code}: {resp.text[:200]}")
        except RuntimeError:
            raise
        except Exception as e:
            errors.append(f"DeepSeek error: {e}")

    # Both failed
    err_msg = "AI Tutor unavailable - " + "; ".join(errors)
    raise RuntimeError(err_msg)


async def _call_llm_with_tools(messages: list[dict], user_id: int) -> tuple[list[dict], str, str]:
    """Call LLM with tools, execute any tool calls, append results."""
    from tutor_tools import (
        get_topic_breakdown, get_weak_questions,
        get_lesson_content, get_recent_mistakes, get_overdue_lessons,
        get_knowledge_context
    )
    
    # Ensure system message is present
    if not any(m.get("role") == "system" for m in messages):
        messages.insert(0, {"role": "system", "content": FALLBACK_SYSTEM_PROMPT})


    TOOL_MAP = {
        "get_topic_breakdown": lambda a: get_topic_breakdown(user_id),
        "get_weak_questions": lambda a: get_weak_questions(user_id, a.get("topic"), a.get("limit", 5)),
        "get_lesson_content": lambda a: get_lesson_content(user_id, a["query"]),
        "get_recent_mistakes": lambda a: get_recent_mistakes(user_id, a.get("limit", 5)),
        "get_overdue_lessons": lambda a: get_overdue_lessons(user_id),
        "get_knowledge_context": lambda a: get_knowledge_context(a.get("query", "")),
    }

    for _ in range(5):
        resp = await _call_llm(messages, tools=TOOL_DEFINITIONS)
        data = resp.json()
        choice = data["choices"][0]

        if choice["finish_reason"] != "tool_calls":
            content = choice["message"].get("content", "")
            reasoning = choice["message"].get("reasoning_content", "")
            messages.append(choice["message"])
            return messages, content, reasoning

        messages.append(choice["message"])
        for tc in choice["message"]["tool_calls"]:
            fn_name = tc["function"]["name"]
            try:
                args = json.loads(tc["function"]["arguments"])
            except json.JSONDecodeError:
                args = {}
            fn = TOOL_MAP.get(fn_name)
            if fn:
                try:
                    result = fn(args)
                except Exception as e:
                    result = {"error": str(e)}
            else:
                result = {"error": f"Unknown tool: {fn_name}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tc["id"],
                "content": json.dumps(result)
            })

    return messages, "", ""


@router.get("/tutor", response_class=HTMLResponse)
async def tutor_page(request: Request, q: str = "", ctx: str = ""):
    return render("tutor.html", active="tutor", query=q, context_b64=ctx)


@router.get("/api/tutor/suggestions")
async def tutor_suggestions(request: Request, context: str = ""):
    user = get_device_user(request)
    if not user:
        return {"suggestions": []}
    
    user_id = user["id"]
    weak = await query_async("""
        SELECT q.id, q.question FROM quiz_questions q
        JOIN quiz_attempts r ON r.question_id = q.id
        WHERE r.user_id = %s AND r.correct = FALSE
        GROUP BY q.id ORDER BY COUNT(*) DESC LIMIT 5
    """, (user_id,))
    
    suggestions = []
    for w in weak:
        suggestions.append(f"Can you explain: {w['question']}")
    return {"suggestions": suggestions[:5]}


@router.get("/api/tutor/profile")
async def tutor_profile(request: Request):
    user = get_device_user(request)
    if not user:
        return {"has_data": False}

    user_id = user["id"]
    profile = {"has_data": True}

    total = await query_one_async("SELECT COUNT(*) as cnt FROM quiz_attempts WHERE user_id = %s", (user_id,))
    profile["total_attempts"] = total["cnt"] if total else 0

    best = await query_one_async("""
        SELECT t.title, (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / NULLIF(COUNT(DISTINCT q.id), 0) * 100) as pct
        FROM topics t JOIN lessons l ON l.topic_code = t.code
        JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.title
        ORDER BY pct DESC LIMIT 1
    """, (user_id,))
    if best and best["pct"]:
        profile["best_topic"] = best["title"]
        profile["best_pct"] = round(best["pct"])

    weak = await query_async("""
        SELECT t.title FROM topics t JOIN lessons l ON l.topic_code = t.code
        JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.title
        HAVING COUNT(DISTINCT q.id) > 0 AND (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) < 0.5
        ORDER BY (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) ASC
        LIMIT 5
    """, (user_id,))
    if weak:
        profile["weak_topics"] = [w["title"] for w in weak]

    mistakes = await query_one_async("""
        SELECT COUNT(*) as cnt FROM question_mastery WHERE user_id = %s AND total_attempts >= 2 AND (total_correct * 1.0 / total_attempts) < 0.4
    """, (user_id,))
    profile["total_mistakes"] = mistakes["cnt"] if mistakes else 0

    overdue = await query_one_async("""
        SELECT COUNT(*) as cnt FROM review_schedule WHERE user_id = %s AND next_review::date <= CURRENT_DATE
    """, (user_id,))
    profile["overdue_reviews"] = overdue["cnt"] if overdue else 0

    last = await query_one_async("SELECT MAX(answered_at) as la FROM quiz_attempts WHERE user_id = %s", (user_id,))
    if last and last["la"]:
        from datetime import datetime as _dt
        try:
            d = last["la"]
            if isinstance(d, str): d = _dt.fromisoformat(d)
            days = (_dt.now() - d).days
            profile["days_ago"] = days
            if days == 0: profile["days_ago_text"] = "today"
            elif days == 1: profile["days_ago_text"] = "yesterday"
            else: profile["days_ago_text"] = f"{days} days ago"
        except: pass

    return profile


@router.get("/api/tutor/start-session")
async def tutor_start_session(request: Request, theme: str = ""):
    user = get_device_user(request)
    if not user:
        return {"chat_id": None, "error": "no_user"}

    user_id = user["id"]
    profile_parts = ["You are a WLV tutor with access to this student's study data. Tailor your responses to their level."]

    total = await query_one_async("SELECT COUNT(*) as cnt FROM quiz_attempts WHERE user_id = %s", (user_id,))
    cnt = total["cnt"] if total else 0
    profile_parts.append(f"Student has answered {cnt} quiz questions total.")

    best = await query_one_async("""
        SELECT t.title, ROUND(COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 100.0 / NULLIF(COUNT(DISTINCT q.id), 0)) as pct
        FROM topics t JOIN lessons l ON l.topic_code = t.code
        JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.title HAVING COUNT(DISTINCT q.id) > 0
        ORDER BY pct DESC LIMIT 1
    """, (user_id,))
    if best and best["pct"] is not None:
        profile_parts.append(f"Strongest topic: {best['title']} ({best['pct']}% mastery).")
    else:
        profile_parts.append("No strong topics established yet - student is still building knowledge.")

    weak = await query_async("""
        SELECT t.title FROM topics t JOIN lessons l ON l.topic_code = t.code
        JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.title
        HAVING COUNT(DISTINCT q.id) > 0 AND (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) < 0.5
        ORDER BY (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) ASC
        LIMIT 5
    """, (user_id,))
    if weak:
        topics = ", ".join(w["title"] for w in weak)
        profile_parts.append(f"Weak topics needing attention: {topics}.")

    mistakes = await query_one_async("SELECT COUNT(*) as cnt FROM question_mastery WHERE user_id = %s AND total_attempts >= 2 AND (total_correct * 1.0 / total_attempts) < 0.4", (user_id,))
    mcnt = mistakes["cnt"] if mistakes else 0
    profile_parts.append(f"Repeated mistakes: {mcnt} questions.")

    overdue = await query_one_async("SELECT COUNT(*) as cnt FROM review_schedule WHERE user_id = %s AND next_review::date <= CURRENT_DATE", (user_id,))
    ocnt = overdue["cnt"] if overdue else 0
    profile_parts.append(f"Overdue reviews: {ocnt} lessons.")

    last = await query_one_async("SELECT MAX(answered_at) as la FROM quiz_attempts WHERE user_id = %s", (user_id,))
    if last and last["la"]:
        from datetime import datetime as _dt
        try:
            d = last["la"]
            if isinstance(d, str): d = _dt.fromisoformat(d)
            days = (_dt.now() - d).days
            if days == 0: profile_parts.append("Last studied today.")
            elif days == 1: profile_parts.append("Last studied yesterday.")
            else: profile_parts.append(f"Last studied {days} days ago.")
        except:
            profile_parts.append("Last studied: unknown.")
    else:
        profile_parts.append("No study activity recorded yet - this is a new or returning student.")

    system_content = "\n".join(profile_parts)

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{OWUI_BASE}/api/v1/chats/new",
                headers={
                    "Authorization": f"Bearer {DEEPSEEK_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "chat": {
                        "title": "WLV CS Tutor",
                        "model": OWUI_MODEL,
                        "messages": [
                            {"role": "system", "content": system_content},
                            {"role": "assistant", "content": "Hi! I can see your study data, so I'll tailor my help to where you're at. What would you like to work on?"}
                        ]
                    }
                }
            )
            resp.raise_for_status()
            data = resp.json()
            return {"chat_id": data.get("id"), "url": f"{OWUI_BASE}/c/{data.get('id')}?theme={theme}"}
    except Exception as e:
        return {"chat_id": None, "error": str(e)[:100]}


@router.post("/api/tutor/chat")
async def tutor_chat(data: TutorChatRequest, request: Request):
    user = get_device_user(request)
    if not user:
        raise HTTPException(400, "No user found")

    messages = [m.dict() for m in data.messages]
    try:
        # Resolve via tools
        messages, final_content, reasoning = await _call_llm_with_tools(messages, user["id"])
        
        q = messages[-2]["content"][:100] if len(messages) >= 2 else ""
        log("tutor_chat", device=request.state.device_id, q=q)

        return {"reply": final_content, "reasoning": reasoning}
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=f"LLM API Error: {e.response.text[:200]}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/api/tutor/chat/stream")
async def tutor_chat_stream(data: TutorChatRequest, request: Request):
    user = get_device_user(request)
    if not user:
        raise HTTPException(400, "No user found")

    messages = [m.dict() for m in data.messages]
    try:
        # Prepend the system prompt and call the LLM (DeepSeek) directly
        system_message = {"role": "system", "content": FALLBACK_SYSTEM_PROMPT}
        full_messages = [system_message] + messages
        resp = await _call_llm(full_messages, stream=True)

        async def generate():
            try:
                async for line in resp.aiter_lines():
                    if line.startswith("data: "):
                        payload = line[6:].strip()
                        if payload == "[DONE]":
                            break
                        if payload:
                            yield f"data: {payload}\n\n"
            except RuntimeError as e:
                error_msg = str(e).replace('"', "'").replace("'", "\\'")
                err_data = json.dumps({"choices": [{"delta": {"content": "⚠️ " + error_msg}}]})
                yield "data: " + err_data + "\n\n"
            except Exception as e:
                err = str(e)[:200].replace('"', "'").replace("'", "\\'")
                err_data = json.dumps({"choices": [{"delta": {"content": "⚠️ Unexpected error. (" + err + ")"}}]})
                yield "data: " + err_data + "\n\n"
            finally:
                yield "data: [DONE]\n\n"

        return StreamingResponse(
            generate(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "X-Accel-Buffering": "no",
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/advise-me", response_class=JSONResponse)
async def advise_me(request: Request):
    """Analyse user data and return personalised AI-generated study advice."""
    user = get_device_user(request)
    if not user:
        return {"advice": [], "summary": "Complete a lesson to get started!"}

    user_id = user["id"]

    # Gather data
    weak_topics = await query_async("""
        SELECT t.code, t.title,
               COUNT(DISTINCT q.id) as total_qs,
               COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) as mastered
        FROM topics t
        JOIN lessons l ON l.topic_code = t.code
        JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.code, t.title, t.sort_order
        HAVING COUNT(DISTINCT q.id) > 0 AND (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) < 0.5
        ORDER BY (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) ASC
        LIMIT 5
    """, (user_id,))

    mistake_qs = await query_async("""
        SELECT q.id, q.question, l.topic_code, l.title as lesson_title,
               qm.total_attempts, qm.total_correct
        FROM question_mastery qm
        JOIN quiz_questions q ON q.id = qm.question_id
        JOIN lessons l ON l.id = q.lesson_id
        WHERE qm.user_id = %s AND qm.total_attempts >= 2
          AND (qm.total_correct * 1.0 / qm.total_attempts) < 0.4
        ORDER BY (qm.total_correct * 1.0 / qm.total_attempts) ASC
        LIMIT 5
    """, (user_id,))

    overdue = await query_async("""
        SELECT rs.id, l.title, l.topic_code, rs.next_review
        FROM review_schedule rs
        JOIN lessons l ON l.id = rs.lesson_id
        WHERE rs.user_id = %s AND rs.next_review::date <= CURRENT_DATE
        ORDER BY rs.next_review ASC
        LIMIT 5
    """, (user_id,))

    days_ago = None
    last = await query_one_async("""
        SELECT MAX(answered_at) as last_activity FROM quiz_attempts WHERE user_id = %s
    """, (user_id,))
    if last and last["last_activity"]:
        try:
            from datetime import datetime as _dt
            last_dt = last["last_activity"]
            if isinstance(last_dt, str):
                last_dt = _dt.fromisoformat(last_dt)
            days_ago = (_dt.now() - last_dt).days
        except:
            pass

    best_topic = await query_one_async("""
        SELECT t.code, t.title,
               COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) as mastered,
               COUNT(DISTINCT q.id) as total_qs
        FROM topics t
        JOIN lessons l ON l.topic_code = t.code
        JOIN quiz_questions q ON q.lesson_id = l.id
        LEFT JOIN question_mastery qm ON qm.question_id = q.id AND qm.user_id = %s
        GROUP BY t.code, t.title, t.sort_order
        HAVING COUNT(DISTINCT q.id) > 0
        ORDER BY (COUNT(DISTINCT CASE WHEN qm.consecutive_correct >= 3 THEN q.id END) * 1.0 / COUNT(DISTINCT q.id)) DESC
        LIMIT 1
    """, (user_id,))

    total_attempts = await query_one_async("""
        SELECT COUNT(*) as cnt FROM quiz_attempts WHERE user_id = %s
    """, (user_id,))

    # Build data block
    data_lines = ["## Student Study Data"]
    if total_attempts and total_attempts["cnt"]:
        data_lines.append(f"Total quiz questions answered: {total_attempts['cnt']}")
    if best_topic and best_topic["total_qs"] > 0:
        bpct = round(best_topic["mastered"] / best_topic["total_qs"] * 100)
        data_lines.append(f"Best topic: {best_topic['code']} {best_topic['title']} ({bpct}% mastery)")
    if weak_topics:
        data_lines.append("")
        data_lines.append("Weak topics (low mastery):")
        for t in weak_topics:
            pct = round(t["mastered"] / t["total_qs"] * 100)
            data_lines.append(f"  - {t['code']} {t['title']}: {t['mastered']}/{t['total_qs']} mastered ({pct}%)")
    if mistake_qs:
        data_lines.append("")
        data_lines.append("Repeated mistakes:")
        for m in mistake_qs:
            pct = round(m["total_correct"] / m["total_attempts"] * 100) if m["total_attempts"] > 0 else 0
            qtext = m["question"][:100]
            data_lines.append(f"  - \"{qtext}\" in {m['lesson_title']}: correct {m['total_correct']}/{m['total_attempts']} ({pct}%)")
    if overdue:
        data_lines.append("")
        data_lines.append("Overdue review items:")
        for r in overdue:
            data_lines.append(f"  - {r['title']} (due: {r['next_review']})")
    if days_ago is not None and days_ago >= 0:
        data_lines.append("")
        if days_ago == 0:
            data_lines.append("Last activity: Today")
        elif days_ago == 1:
            data_lines.append("Last activity: Yesterday")
        else:
            data_lines.append(f"Last activity: {days_ago} days ago")
    data_text = "\n".join(data_lines)

    # Call AI
    system_msg = {
        "role": "system",
        "content": (
            "You are a supportive WLV tutor giving personalised study advice. "
            "You will receive a student's study data. Write 2-4 short, encouraging advice items. "
            "Each item must have: an emoji icon, a short bold title (under 50 chars), a friendly explanation in 1-2 sentences, "
            "and an action link path (like /topic/1.1). "
            "Respond ONLY with valid JSON in this exact format, no other text:\n"
            '{"advice": [{"icon": "...", "title": "...", "body": "...", "action": "/topic/1.1", "action_label": "Revise this topic \\u2192"}], "summary": "One sentence summary of the advice."}'
        )
    }

    user_msg = {
        "role": "user",
        "content": f"Here is the student's current study data:\n\n{data_text}\n\nWhat personalised advice should I give them?"
    }

    try:
        resp = await _call_llm([system_msg, user_msg], stream=False)
        body = resp.json()
        ai_text = body["choices"][0]["message"]["content"]
        try:
            return json.loads(ai_text)
        except json.JSONDecodeError:
            return {
                "advice": [{"icon": "\U0001f4ac", "title": "Study Check", "body": ai_text[:300], "action": "/topic/1.1", "action_label": "Start studying \u2192"}],
                "summary": "Here's what I found."
            }
    except Exception:
        advice = []
        for t in weak_topics:
            pct = round(t["mastered"] / t["total_qs"] * 100)
            advice.append({"icon": "\U0001f4a1", "title": f"{t['code']} — {t['title']}", "body": f"You've mastered {t['mastered']}/{t['total_qs']} questions ({pct}%). This topic needs attention.", "action": f"/topic/{t['code']}", "action_label": "Revise \u2192"})
        for m in mistake_qs:
            pct = round(m["total_correct"] / m["total_attempts"] * 100) if m["total_attempts"] > 0 else 0
            advice.append({"icon": "\u274c", "title": f"Repeated mistakes in {m['lesson_title']}", "body": f"Correct only {m['total_correct']}/{m['total_attempts']} ({pct}%).", "action": f"/topic/{m['topic_code']}", "action_label": "Practise \u2192"})
        for r in overdue:
            advice.append({"icon": "\U0001f504", "title": "Review due", "body": f"\"{r['title']}\" is overdue.", "action": f"/topic/{r['topic_code']}", "action_label": "Review \u2192"})
        if days_ago and days_ago >= 3:
            advice.append({"icon": "\U0001f4a4", "title": "Haven't studied in a while", "body": f"Last session {days_ago} days ago.", "action": "/topic/1.1", "action_label": "Start \u2192"})
        if not advice:
            advice.append({"icon": "\u2705", "title": "Looking good!", "body": "You're on top of everything. Try a practice test.", "action": "/exam", "action_label": "Practice test \u2192"})
        return {"advice": advice, "summary": f"Here are {len(advice)} things to focus on."}
