"""
FastAPI application core. Middlewares, startup configuration, and modular routing.
"""
import re
import os
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from database import init_db, ensure_default_user, check_schema, execute_async, query_one_async
from routes import lessons, quiz, tutor, activity, misc, mark_my_paper

BASE_DIR = Path(__file__).resolve().parent
DEBUG = os.getenv("WLV_DEBUG", "").lower() in ("true", "1", "yes")

app = FastAPI(title="WLV CS Revision")

app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


# ─── MIDDLEWARES ──────────────────────────────────────────────────────────

@app.middleware("http")
async def debug_no_cache_middleware(request: Request, call_next):
    """When WLV_DEBUG=true, disable all caching for instant CSS/JS updates."""
    response = await call_next(request)
    if DEBUG:
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


@app.middleware("http")
async def device_id_middleware(request: Request, call_next):
    """Ensure every visitor has a device cookie.

    Priority: JS-set cookie -> existing user by IP -> random UUID device ID.
    First-time visitors get a cookie set on the response.
    """
    device_id = request.cookies.get("wlv_device") or ""
    # Validate device_id format -- reject malformed values
    if device_id.strip() and not re.match(
        r"^device_[a-zA-Z0-9_-]+$",
        device_id.strip()
    ):
        device_id = ""
    if not device_id.strip():
        # Try to find an existing user for this IP to avoid duplicates
        client_ip = request.client.host if request.client else None
        if client_ip:
            existing = await query_one_async(
                "SELECT username FROM users WHERE last_ip = %s ORDER BY id DESC LIMIT 1",
                (client_ip,)
            )
            if existing:
                device_id = existing["username"]
        if not device_id.strip():
            import uuid
            device_id = "device_" + uuid.uuid4().hex[:12]

    request.state.device_id = device_id

    # Capture client IP
    client_ip = request.client.host if request.client else None

    # Ensure user exists in DB -- device_id is guaranteed non-empty here
    await execute_async(
        "INSERT INTO users (username, display_name, last_ip) VALUES (%s, %s, %s) ON CONFLICT(username) DO UPDATE SET last_ip = EXCLUDED.last_ip",
        (device_id, f"Device {device_id}", client_ip)
    )

    response = await call_next(request)

    # Set the cookie if it was missing -- catches first-time visitors
    if not request.cookies.get("wlv_device"):
        response.set_cookie(key="wlv_device", value=device_id, max_age=31536000, path="/")

    return response




@app.on_event("startup")
async def startup():
    init_db()
    check_schema()
    ensure_default_user()
    print("🚀 WLV CS platform ready")


# ─── ROUTER INTEGRATION ───────────────────────────────────────────────────

app.include_router(lessons.router)
app.include_router(quiz.router)
app.include_router(tutor.router)
app.include_router(activity.router)
app.include_router(misc.router)
app.include_router(mark_my_paper.router)


# ─── CUSTOM ERROR HANDLERS ──────────────────────────────────────────────

from fastapi.responses import HTMLResponse
from helpers import render


@app.exception_handler(404)
async def not_found_handler(request: Request, exc):
    return HTMLResponse(
        content=render("404.html", request=request, active="").body,
        status_code=404,
    )


@app.exception_handler(500)
async def server_error_handler(request: Request, exc):
    return HTMLResponse(
        content=render("500.html", request=request, active="").body,
        status_code=500,
    )
