"""Routes: activity dashboard, device profile, rename device, clear log, activity log HTML & raw plain text"""
from pathlib import Path
import json

from fastapi import APIRouter, Request, HTTPException
from fastapi.responses import HTMLResponse, RedirectResponse, PlainTextResponse

from helpers import render, _grade_from_percentage, templates
from database import query_async, execute_async

router = APIRouter()


# ─── DASHBOARD RENDER HELPERS ────────────────────────────────────────────

def _render_device_stats(device_stats, all_names, entries=None):
    """Build device table with quiz averages and grades."""
    if not device_stats:
        return '<p class="empty">No devices yet</p>'

    dev_quiz_pcts = {}
    if entries:
        for e in entries:
            if e["event_type"] == "quiz_submit":
                dev = e["fields"].get("device", "unknown")
                score_str = e["fields"].get("score", "")
                try:
                    parts = score_str.replace("%", "").split("/")
                    if len(parts) == 2:
                        c, t = int(parts[0]), int(parts[1])
                        pct = round(c / t * 100, 1) if t else 0
                        if dev not in dev_quiz_pcts:
                            dev_quiz_pcts[dev] = []
                        dev_quiz_pcts[dev].append(pct)
                except (ValueError, IndexError):
                    pass

    rows = ""
    for dev, stats in sorted(device_stats.items()):
        name = all_names.get(dev, dev[:16] + "..." if len(dev) > 16 else dev)
        last = stats.get("last_seen", "")
        if hasattr(last, "strftime"):
            last_str = last.strftime("%d/%m %H:%M")
        else:
            last_str = str(last)[:16] if last else "-"

        total = stats["lessons"] + stats["quizzes"] + stats["exams"] + stats["tutor"]
        
        q_pcts = dev_quiz_pcts.get(dev, [])
        if q_pcts:
            avg_q = sum(q_pcts) / len(q_pcts)
            grade = _grade_from_percentage(avg_q)
            grade_cell = f'Grade {grade}'
        else:
            grade_cell = '-'

        ips_set = stats.get("ips", set())
        ips_str = ", ".join(sorted(ips_set))[:35] if ips_set else "-"

        rows += (
            f'<tr>'
            f'<td><a href="/activity/device/{dev}" class="dev">{name}</a></td>'
            f'<td>{total}</td>'
            f'<td>{stats["lessons"]}</td>'
            f'<td>{stats["quizzes"]}</td>'
            f'<td>{stats["exams"]}</td>'
            f'<td>{grade_cell}</td>'
            f'<td class="last">{last_str}</td>'
            f'<td class="ip-cell">{ips_str}</td>'
            f'<td><button class="rename-inline" onclick="renameDevice(\'{dev}\',\'{name}\')" title="Rename">✏️</button></td>'
            f'</tr>'
        )
    
    return (
        '<table class="dev-table">'
        '<tr><th>Device</th><th>Total</th><th>📖 Lessons</th><th>🧪 Quizzes</th><th>📋 Exams</th><th>🎓 Grade</th><th>Last seen</th><th>IP</th><th></th></tr>'
        f'{rows}'
        '</table>'
        '<script>'
        'function renameDevice(id,n){var p=prompt("Rename device:",n);if(p&&p.trim()){var f=new FormData();f.append("name",p.trim());fetch("/activity/device/"+id+"/rename",{method:"POST",body:f}).then(function(r){if(r.ok)location.reload()})}}'
        '</script>'
    )


# ─── Endpoints ───────────────────────────────────────────────────────────

@router.get("/log/raw", response_class=PlainTextResponse)
async def raw_log():
    """Raw unfiltered log as plain text."""
    log_path = Path("/var/log/activity/wlv.log")
    if not log_path.exists():
        return PlainTextResponse("No log entries yet.")
    lines = log_path.read_text().strip().splitlines()
    return PlainTextResponse("\n".join(reversed(lines[-500:])))


@router.get("/activity", response_class=HTMLResponse)
async def activity_dashboard(request: Request):
    """Study dashboard — device list with grades, IPs, rename."""
    from activity_dashboard import parse_entries_db, build_dashboard_data, get_device_name, get_all_device_names

    filter_dev = request.query_params.get("device", "").strip() or None

    entries = parse_entries_db(filter_device=filter_dev)
    data = build_dashboard_data(entries)
    all_names = get_all_device_names()

    # Device filter dropdown
    device_ids = sorted(data.get("device_stats", {}).keys())
    filter_opts = '<option value="" ' + ("" if not filter_dev else "selected") + '>All Devices</option>'
    for d in device_ids:
        name = all_names.get(d, d[:16] + "..." if len(d) > 16 else d)
        sel = ' selected' if d == filter_dev else ''
        filter_opts += f'<option value="{d}"{sel}>{name}</option>'

    title = f"📊 {get_device_name(filter_dev)}" if filter_dev else "📊 Study Dashboard"

    device_table = _render_device_stats(data["device_stats"], all_names, entries)

    tmpl = templates.get_template("dashboard.html")
    return HTMLResponse(tmpl.render(
        title=title,
        active="activity",
        filter_opts=filter_opts,
        total_devices=len(device_ids),
        device_table=device_table,
    ))


@router.get("/activity/device/{device_id}", response_class=HTMLResponse)
async def device_profile(request: Request, device_id: str):
    """Per-device profile with trends, weak topics, repeated mistakes, grades."""
    from activity_dashboard import build_device_profile, get_device_name, get_question_history

    profile = build_device_profile(device_id)
    if profile is None:
        return HTMLResponse("<html><body><h1>Device not found</h1><p>No activity for device: %s</p></body></html>" % device_id)

    total_events = profile.get("total_events", 0)
    mistake_count = len(profile.get("repeated_mistakes", []))
    topic_count = len(profile.get("topic_breakdown", []))
    days_active = profile.get("days_active", 1)
    ips = profile.get("ips", [])
    trend = profile.get("trend", "flat")
    trend_icon = {"up": "📈 Improving", "down": "📉 Declining", "flat": "➡️ Stable"}.get(trend, "")
    trend_badge = {"up": "badge-up", "down": "badge-down", "flat": "badge-flat"}.get(trend, "badge-flat")
    first = profile.get("first_seen", "")
    last = profile.get("last_seen", "")
    if hasattr(first, "strftime"):
        first = first.strftime("%d/%m/%Y %H:%M")
    if hasattr(last, "strftime"):
        last = last.strftime("%d/%m/%Y %H:%M")
    friendly = profile.get("friendly_name", device_id[:16] + "..." if len(device_id) > 16 else device_id)

    score_timeline = profile.get("score_timeline", [])
    score_rows = ""
    for s in score_timeline:
        is_quiz = s.get("type", "") == "quiz_submit"
        icon = "🧪" if is_quiz else "📋"
        cls = "tag-quiz" if is_quiz else "tag-exam"
        bc = "#818cf8" if is_quiz else "#facc15"
        ds = s.get("date", "")
        if hasattr(ds, "strftime"):
            ds = ds.strftime("%d/%m %H:%M")
        bar_w = max(s.get("pct", 0), 5)
        bar_c = "#34d399" if s.get("pct", 0) >= 70 else ("#facc15" if s.get("pct", 0) >= 40 else "#f87171")
        g = s.get("grade")
        grade_str = "-"
        if g is not None:
            if isinstance(g, int):
                grade_str = "Grade %d" % g
            else:
                grade_str = str(g)
        score_rows += '<tr style="border-left:3px solid %s"><td class="time">%s</td><td><span class="tag %s">%s</span></td><td>%s</td><td class="pct">%s</td><td><div class="bar" style="width:%d%%;background:%s"></div></td><td class="pct">%d%%</td></tr>' % (bc, ds, cls, icon, s.get("score", ""), grade_str, int(bar_w), bar_c, int(s.get("pct", 0)))
    if not score_rows:
        score_rows = '<tr><td colspan="6" class="empty">No quiz or exam scores yet</td></tr>'

    all_pcts = [s.get("pct", 0) for s in score_timeline if s.get("pct") is not None]
    quiz_pcts = [s.get("pct", 0) for s in score_timeline if s.get("pct") is not None and s.get("type") == "quiz_submit"]
    exam_pcts = [s.get("pct", 0) for s in score_timeline if s.get("pct") is not None and s.get("type") == "exam_submit"]
    avg_str = "%.1f%%" % (sum(all_pcts)/len(all_pcts)) if all_pcts else "-"
    avg_quiz_str = "%.1f%%" % (sum(quiz_pcts)/len(quiz_pcts)) if quiz_pcts else "-"
    avg_exam_str = "%.1f%%" % (sum(exam_pcts)/len(exam_pcts)) if exam_pcts else "-"
    avg_grade_str = "Grade %d" % _grade_from_percentage(sum(all_pcts)/len(all_pcts)) if all_pcts else "-"
    avg_quiz_grade_str = "Grade %d" % _grade_from_percentage(sum(quiz_pcts)/len(quiz_pcts)) if quiz_pcts else "-"
    avg_exam_grade_str = "Grade %d" % _grade_from_percentage(sum(exam_pcts)/len(exam_pcts)) if exam_pcts else "-"

    scores = [s.get("pct", 0) for s in score_timeline if s.get("pct") is not None]
    svg_graph = ""
    if len(scores) >= 2:
        svg_w, svg_h = 600, 120
        max_s = max(scores)
        min_s = min(scores)
        span = max_s - min_s if max_s != min_s else 1
        n = len(scores)
        pts = ["%d,%d" % (round(i * (svg_w - 40) / (n - 1)) + 20, round(svg_h - 20 - (s_val - min_s) * (svg_h - 40) / span)) for i, s_val in enumerate(scores)]
        pts_str = " ".join(pts)
        svg_graph = '<svg width="100%%" viewBox="0 0 %d %d" style="display:block;margin:0 0 8px 0;width:100%%"><polyline points="%s" fill="none" stroke="#22d3ee" stroke-width="1.5" opacity="0.7"/><text x="20" y="12" fill="#94a3b8" font-size="10">%d%%</text><text x="20" y="%d" fill="#94a3b8" font-size="10">%d%%</text></svg>' % (svg_w, svg_h, pts_str, max_s, svg_h - 8, min_s)

    topic_breakdown = profile.get("topic_breakdown", [])
    topic_rows = ""
    for t in topic_breakdown:
        acc = t.get("accuracy")
        acc_str = "%.1f%%" % acc if acc is not None else "-"
        bar_w = acc or 0
        bar_c = "#34d399" if bar_w >= 70 else ("#facc15" if bar_w >= 40 else "#f87171")
        last_s = t.get("last_seen", "")
        if hasattr(last_s, "strftime"):
            last_s = last_s.strftime("%d/%m")
        topic_rows += '<tr><td>%s</td><td>%d</td><td>%d</td><td><div class="bar-sm" style="width:%d%%;background:%s"></div></td><td class="pct">%s</td><td class="time">%s</td></tr>' % (t.get("title", "?"), t.get("lessons", 0), t.get("total", 0), int(bar_w), bar_c, acc_str, last_s)
    if not topic_rows:
        topic_rows = '<tr><td colspan="6" class="empty">No topic data yet</td></tr>'

    lesson_timeline = profile.get("lesson_timeline", [])
    lesson_rows = ""
    for le in lesson_timeline[-10:]:
        ts = le.get("timestamp", "")
        if hasattr(ts, "strftime"):
            ts = ts.strftime("%H:%M")
        lesson_rows += '<tr><td class="time">%s</td><td>%s</td><td>%s</td></tr>' % (ts, le.get("topic_title", "Unknown"), le.get("lesson_title", ""))
    if not lesson_rows:
        lesson_rows = '<tr><td colspan="3" class="empty">No lessons viewed yet</td></tr>'

    repeated = profile.get("repeated_mistakes", [])
    mistake_rows = ""
    for m in repeated:
        qtext = m.get("question", "")[:80]
        cnt = m.get("count", 0)
        correct = m.get("correct", "")[:60]
        wrong = m.get("student_answer", "")[:30]
        topic = m.get("topic", "")
        qsafe = qtext.replace("'", "\\'")
        mistake_rows += '<tr onclick="loadQuestionHistory(this, \'%s\')" style="cursor:pointer"><td class="q-cell">%s</td><td class="wrong-ans">%s</td><td class="ans-cell">%s</td><td class="count-cell">%dX</td><td class="time">%s</td></tr>' % (qsafe, qtext, wrong, correct, cnt, topic or "-")
    if not mistake_rows:
        repeated = []
        mistake_rows = '<tr><td colspan="5" class="empty">No repeated mistakes</td></tr>'

    day_activity = profile.get("day_activity", [])
    day_grid = ""
    for d in day_activity:
        active = d.get("active", False)
        label = d.get("label", "")
        bg = "rgba(34,211,238,0.5)" if active else "rgba(255,255,255,0.04)"
        parts = label.split(" ")
        day_grid += '<div style="display:inline-flex;flex-direction:column;align-items:center;margin:0 2px"><div style="width:14px;height:14px;border-radius:3px;background:%s;margin-bottom:2px"></div><span style="font-size:9px;color:#64748b">%s</span><span style="font-size:8px;color:#94a3b8">%s</span></div>' % (bg, parts[0] if parts else "", parts[1] if len(parts) > 1 else "")

    this_w = profile.get("this_week_stats", profile.get("this_week", {}))
    last_w = profile.get("last_week_stats", profile.get("last_week", {}))
    week_compare = ""
    if this_w.get("events", 0) or last_w.get("events", 0):
        ev_diff = this_w.get("events", 0) - last_w.get("events", 0)
        arrow = "📈" if ev_diff > 0 else ("📉" if ev_diff < 0 else "➡️")
        week_compare = '<p class="sub">%s This week: %d events vs last week %d</p>' % (arrow, this_w.get("events", 0), last_w.get("events", 0))

    qhistory = get_question_history(device_id)
    qhistory_json = json.dumps(qhistory)

    tmpl = templates.get_template("device_profile.html")
    return HTMLResponse(tmpl.render(
        title="📊 " + get_device_name(device_id), active="activity",
        device_id=device_id, device_name=get_device_name(device_id),
        friendly=friendly, trend_icon=trend_icon, trend_badge=trend_badge,
        first=first, last=last, days_active=days_active, ips=ips,
        total_events=total_events, avg_str=avg_str, avg_grade_str=avg_grade_str,
        avg_quiz_str=avg_quiz_str, avg_quiz_grade_str=avg_quiz_grade_str,
        avg_exam_str=avg_exam_str, avg_exam_grade_str=avg_exam_grade_str,
        mistake_count=mistake_count, topic_count=topic_count,
        svg_graph=svg_graph, score_rows=score_rows, topic_rows=topic_rows,
        lesson_rows=lesson_rows, mistake_rows=mistake_rows,
        qhistory_json=qhistory_json,
        week_compare=week_compare, day_grid=day_grid,
    ))


@router.post("/activity/device/{device_id}/rename")
async def device_rename(device_id: str, request: Request):
    """Set a friendly name for a device."""
    from activity_dashboard import set_device_name
    form = await request.form()
    name = form.get("name", "").strip()
    if name:
        set_device_name(device_id, name)
    return RedirectResponse(url=f"/activity/device/{device_id}", status_code=303)


@router.post("/activity/clear")
async def clear_activity_log():
    """Truncate the activity log file and SQLite DB. Device names are preserved."""
    from activity_dashboard import _load_device_names, _save_device_names
    names = _load_device_names()
    log_path = Path("/var/log/activity/wlv.log")
    db_path = Path("/var/log/activity/wlv.db")
    if log_path.exists():
        log_path.write_text("")
    if db_path.exists():
        import sqlite3
        conn = sqlite3.connect(str(db_path))
        conn.execute("DELETE FROM activity_log")
        conn.commit()
        conn.close()
    _save_device_names(names)
    return RedirectResponse(url="/log", status_code=303)


@router.get("/log", response_class=HTMLResponse)
async def activity_log_page():
    """Colourised log viewer - event types highlighted."""
    log_path = Path("/var/log/activity/wlv.log")
    if not log_path.exists():
        return HTMLResponse("<html><body><h1>Activity Log</h1><p>No log entries yet.</p></body></html>")
    lines = log_path.read_text().strip().splitlines()
    html_rows = ""
    for line in reversed(lines[-500:]):
        css = ""
        if "lesson_view" in line: css = "tag-lesson"
        elif "quiz_submit" in line: css = "tag-quiz"
        elif "exam_submit" in line: css = "tag-exam"
        elif "tutor_chat" in line: css = "tag-tutor"
        elif "codelab_complete" in line: css = "tag-codelab"
        html_rows += f'<div class="line {css}">{line}</div>\n'
    return HTMLResponse(f"""<html><head><link href="/static/css/style.css" rel="stylesheet"></head><body style="padding:20px;font-family:monospace;font-size:13px;background:var(--c-bg);color:var(--c-text)"><h1>Activity Log</h1><form method="post" action="/activity/clear" style="margin-bottom:16px"><button class="btn">Clear log</button></form>{html_rows}</body></html>""")
