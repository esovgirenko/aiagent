import asyncio
import json
import re
import time
from pathlib import Path
from typing import AsyncIterator, Literal

from fastapi import Depends, FastAPI, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from starlette.middleware.sessions import SessionMiddleware

from .config import settings
from .llm_clients import get_client
from .storage import (
    create_goal_task,
    create_user,
    enqueue_autonomy_goal,
    ensure_default_user,
    fetch_next_queued_goal,
    get_or_create_active_goal,
    get_feedback_summary,
    get_recent_memories,
    get_user,
    init_db,
    list_autonomous_runs,
    list_audit_logs,
    list_goal_tasks,
    list_queue_items,
    list_users,
    mark_queue_item_done,
    mark_queue_item_failed,
    mark_task_done,
    save_audit_log,
    save_autonomous_run,
    save_conversation,
    save_feedback,
    set_user_active,
    verify_password,
)


class ChatRequest(BaseModel):
    provider: Literal["openai", "ollama", "gigachat"]
    message: str = Field(min_length=1, max_length=8000)


class FeedbackRequest(BaseModel):
    conversation_id: int
    score: int = Field(ge=-1, le=1)
    comment: str = ""


class AdminCreateUserRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=8, max_length=128)
    role: Literal["admin", "user"] = "user"


class AdminSetUserStatusRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    is_active: bool


class AgentRunRequest(BaseModel):
    goal: str = Field(min_length=5, max_length=500)
    provider: Literal["openai", "ollama", "gigachat"] = "gigachat"
    priority: int = Field(default=1, ge=1, le=5)


class AgentWorkerRequest(BaseModel):
    enabled: bool


_RATE_BUCKETS: dict[str, list[float]] = {}
_AUTONOMY_WORKER_ENABLED = False
_AUTONOMY_WORKER_TASK: asyncio.Task | None = None
_AUTONOMY_ITERATIONS = 0
_AUTONOMY_FAIL_STREAK = 0


BASE_DIR = Path(__file__).resolve().parent.parent
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

app = FastAPI(title=settings.app_title)
app.add_middleware(SessionMiddleware, secret_key=settings.session_secret)
app.mount("/static", StaticFiles(directory=str(BASE_DIR / "static")), name="static")


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    default_password = settings.default_password or settings.auth_password
    ensure_default_user(settings.default_username, default_password)


@app.on_event("shutdown")
async def on_shutdown() -> None:
    global _AUTONOMY_WORKER_ENABLED, _AUTONOMY_WORKER_TASK
    _AUTONOMY_WORKER_ENABLED = False
    if _AUTONOMY_WORKER_TASK:
        _AUTONOMY_WORKER_TASK.cancel()
        try:
            await _AUTONOMY_WORKER_TASK
        except BaseException:
            pass
        _AUTONOMY_WORKER_TASK = None


def build_system_prompt() -> str:
    memories = get_recent_memories(limit=8)
    feedback_hint = get_feedback_summary(limit=30)
    compact_memory = "\n".join(
        [f"- [{p}] user: {u[:120]} | assistant: {a[:120]}" for p, u, a in memories]
    )
    return (
        "You are a safe and practical assistant. Use prior local memory to improve answer quality.\n"
        f"Feedback guidance: {feedback_hint}\n"
        f"Recent memory:\n{compact_memory if compact_memory else '- none'}"
    )


def _is_authorized(request: Request) -> bool:
    if not _auth_enabled():
        return True
    return bool(request.session.get("username"))


def _auth_enabled() -> bool:
    return bool(settings.default_password or settings.auth_password or get_user(settings.default_username))


def require_auth(request: Request) -> None:
    if not _is_authorized(request):
        raise HTTPException(status_code=401, detail="Unauthorized")


def _rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    now = time.time()
    bucket = _RATE_BUCKETS.setdefault(ip, [])
    window_start = now - 60
    while bucket and bucket[0] < window_start:
        bucket.pop(0)
    if len(bucket) >= settings.rate_limit_per_minute:
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    bucket.append(now)


def _username(request: Request) -> str:
    return str(request.session.get("username", "anonymous"))


def _is_admin(request: Request) -> bool:
    username = _username(request)
    user = get_user(username)
    return bool(user and user[3] == "admin")


def require_admin(request: Request) -> None:
    require_auth(request)
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required")


async def run_autonomous_cycle(goal: str, provider: str) -> dict:
    client = get_client(provider)
    result_text = await client.chat(
        [
            {
                "role": "user",
                "content": (
                    "Отвечай строго на русском языке.\n"
                    "Дай ИТОГОВЫЙ ответ на цель одной короткой фразой.\n"
                    "Если данных недостаточно, ответь ровно: НЕТ ДАННЫХ.\n"
                    f"Цель: {goal}"
                ),
            }
        ]
    )
    plan_text = await client.chat(
        [
            {
                "role": "user",
                "content": (
                    "Отвечай строго на русском языке.\n"
                    "Составь краткий план из 3 шагов для этой цели:\n"
                    f"{goal}\n"
                    "Формат: маркированный список."
                ),
            }
        ]
    )
    action_text = await client.chat(
        [
            {
                "role": "user",
                "content": (
                    "Отвечай строго на русском языке.\n"
                    "По этому плану дай следующее конкретное действие для выполнения прямо сейчас.\n"
                    f"{plan_text}"
                ),
            }
        ]
    )
    verify_text = await client.chat(
        [
            {
                "role": "user",
                "content": (
                    "Отвечай строго на русском языке.\n"
                    "Оцени, насколько действие конкретно и проверяемо. "
                    "Ответ только в формате: PASS: <короткая причина> или FAIL: <короткая причина>.\n"
                    f"{action_text}"
                ),
            }
        ]
    )
    verify_status = "PASS" if "PASS" in verify_text.upper() else "FAIL"
    if "верси" in goal.lower():
        if not re.search(r"\b\d+\.\d+(?:\.\d+)?\b", result_text):
            verify_status = "FAIL"
    reflection_text = await client.chat(
        [
            {
                "role": "user",
                "content": (
                    "Отвечай строго на русском языке.\n"
                    "Напиши ретроспективу в 2 пунктах:\n"
                    "1) Что сработало\n"
                    "2) Что улучшить в следующем цикле\n"
                    f"Цель: {goal}\n"
                    f"План: {plan_text}\n"
                    f"Действие: {action_text}\n"
                    f"Проверка: {verify_text}"
                ),
            }
        ]
    )
    return {
        "result_text": result_text,
        "plan_text": plan_text,
        "action_text": action_text,
        "verify_status": verify_status,
        "reflection_text": reflection_text,
    }


async def _autonomy_worker_loop() -> None:
    global _AUTONOMY_ITERATIONS, _AUTONOMY_FAIL_STREAK, _AUTONOMY_WORKER_ENABLED
    while _AUTONOMY_WORKER_ENABLED and _AUTONOMY_ITERATIONS < settings.autonomy_max_iterations:
        item = fetch_next_queued_goal()
        if not item:
            await asyncio.sleep(settings.autonomy_interval_sec)
            continue
        queue_id, goal, provider, created_by = item
        try:
            goal_id = get_or_create_active_goal(goal, created_by)
            task_id = create_goal_task(goal_id, f"Auto cycle action for: {goal}", priority=1)
            result = await run_autonomous_cycle(goal, provider)
            if result["verify_status"] == "PASS":
                mark_task_done(task_id)
            run_id = save_autonomous_run(
                goal_id=goal_id,
                provider=provider,
                result_text=result["result_text"],
                plan_text=result["plan_text"],
                action_text=result["action_text"],
                verify_status=result["verify_status"],
                reflection_text=result["reflection_text"],
                created_by=created_by,
            )
            mark_queue_item_done(queue_id)
            _AUTONOMY_ITERATIONS += 1
            _AUTONOMY_FAIL_STREAK = 0
            save_audit_log(created_by, "autonomy_worker_cycle", "worker", f"queue_id={queue_id},run_id={run_id}")
        except Exception as exc:
            mark_queue_item_failed(queue_id, str(exc))
            _AUTONOMY_FAIL_STREAK += 1
            save_audit_log(created_by, "autonomy_worker_failed", "worker", f"queue_id={queue_id}:{exc}")
            if _AUTONOMY_FAIL_STREAK >= settings.autonomy_fail_streak_limit:
                _AUTONOMY_WORKER_ENABLED = False
                save_audit_log(
                    created_by,
                    "autonomy_worker_auto_stop",
                    "worker",
                    f"fail_streak={_AUTONOMY_FAIL_STREAK}",
                )
                break
            await asyncio.sleep(1)


@app.get("/", response_class=HTMLResponse)
async def index(request: Request) -> HTMLResponse:
    if not _is_authorized(request):
        return RedirectResponse(url="/login", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        context={"title": settings.app_title},
    )


@app.get("/admin", response_class=HTMLResponse)
async def admin_page(request: Request) -> HTMLResponse:
    if not _is_authorized(request):
        return RedirectResponse(url="/login", status_code=302)
    if not _is_admin(request):
        raise HTTPException(status_code=403, detail="Admin access required")
    return templates.TemplateResponse(
        request=request,
        name="admin.html",
        context={"title": settings.app_title},
    )


@app.post("/api/chat")
async def chat(payload: ChatRequest, request: Request, _: None = Depends(require_auth)) -> JSONResponse:
    try:
        _rate_limit(request)
        client = get_client(payload.provider)
        messages = [
            {"role": "system", "content": build_system_prompt()},
            {"role": "user", "content": payload.message},
        ]
        reply = await client.chat(messages)
        conversation_id = save_conversation(payload.provider, payload.message, reply)
        save_audit_log(_username(request), "chat", request.client.host if request.client else "unknown", payload.provider)
        return JSONResponse({"conversation_id": conversation_id, "reply": reply})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/api/feedback")
async def feedback(payload: FeedbackRequest, request: Request, _: None = Depends(require_auth)) -> JSONResponse:
    try:
        _rate_limit(request)
        save_feedback(payload.conversation_id, payload.score, payload.comment)
        save_audit_log(_username(request), "feedback", request.client.host if request.client else "unknown", str(payload.score))
        return JSONResponse({"ok": True})
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc


@app.post("/chat", response_class=HTMLResponse)
async def chat_form(request: Request, provider: str = Form(...), message: str = Form(...)) -> HTMLResponse:
    payload = ChatRequest(provider=provider, message=message)
    data = await chat(payload, request)
    return HTMLResponse(data.body.decode("utf-8"))


@app.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    if _is_authorized(request):
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse(
        request=request,
        name="login.html",
        context={"title": settings.app_title, "error": request.query_params.get("error")},
    )


@app.post("/login")
async def login(request: Request, username: str = Form(...), password: str = Form(...)) -> RedirectResponse:
    if not _auth_enabled():
        return RedirectResponse(url="/", status_code=302)
    user = get_user(username)
    if not user or not verify_password(password, user[2]) or int(user[4]) == 0:
        save_audit_log(username, "login_failed", request.client.host if request.client else "unknown")
        return RedirectResponse(url="/login?error=1", status_code=302)
    request.session["username"] = user[1]
    save_audit_log(user[1], "login_success", request.client.host if request.client else "unknown")
    return RedirectResponse(url="/", status_code=302)


@app.post("/logout")
async def logout(request: Request) -> RedirectResponse:
    save_audit_log(_username(request), "logout", request.client.host if request.client else "unknown")
    request.session.clear()
    return RedirectResponse(url="/login", status_code=302)


@app.post("/api/chat/stream")
async def chat_stream(payload: ChatRequest, request: Request, _: None = Depends(require_auth)) -> StreamingResponse:
    async def event_stream() -> AsyncIterator[str]:
        try:
            _rate_limit(request)
            client = get_client(payload.provider)
            messages = [
                {"role": "system", "content": build_system_prompt()},
                {"role": "user", "content": payload.message},
            ]
            chunks: list[str] = []
            async for token in client.stream_chat(messages):
                chunks.append(token)
                yield f"data: {json.dumps({'type': 'chunk', 'text': token})}\n\n"
            reply = "".join(chunks)
            conversation_id = save_conversation(payload.provider, payload.message, reply)
            save_audit_log(_username(request), "chat_stream", request.client.host if request.client else "unknown", payload.provider)
            yield f"data: {json.dumps({'type': 'done', 'conversation_id': conversation_id})}\n\n"
        except Exception as exc:
            yield f"data: {json.dumps({'type': 'error', 'detail': str(exc)})}\n\n"

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@app.get("/api/admin/users")
async def admin_users(request: Request, _: None = Depends(require_admin)) -> JSONResponse:
    data = [
        {
            "id": uid,
            "username": username,
            "role": role,
            "is_active": bool(is_active),
            "created_at": created_at,
        }
        for uid, username, role, is_active, created_at in list_users()
    ]
    return JSONResponse({"items": data})


@app.post("/api/admin/users")
async def admin_create_user(
    payload: AdminCreateUserRequest, request: Request, _: None = Depends(require_admin)
) -> JSONResponse:
    if get_user(payload.username):
        raise HTTPException(status_code=409, detail="User already exists")
    user_id = create_user(payload.username, payload.password, role=payload.role)
    save_audit_log(
        _username(request),
        "admin_create_user",
        request.client.host if request.client else "unknown",
        payload.username,
    )
    return JSONResponse({"id": user_id, "ok": True})


@app.post("/api/admin/users/status")
async def admin_set_user_status(
    payload: AdminSetUserStatusRequest, request: Request, _: None = Depends(require_admin)
) -> JSONResponse:
    if payload.username == _username(request) and not payload.is_active:
        raise HTTPException(status_code=400, detail="Cannot deactivate yourself")
    if not get_user(payload.username):
        raise HTTPException(status_code=404, detail="User not found")
    set_user_active(payload.username, 1 if payload.is_active else 0)
    save_audit_log(
        _username(request),
        "admin_set_user_status",
        request.client.host if request.client else "unknown",
        f"{payload.username}:{payload.is_active}",
    )
    return JSONResponse({"ok": True})


@app.get("/api/admin/audit")
async def admin_audit_logs(request: Request, _: None = Depends(require_admin)) -> JSONResponse:
    items = [
        {
            "username": username,
            "action": action,
            "ip": ip,
            "details": details,
            "created_at": created_at,
        }
        for username, action, ip, details, created_at in list_audit_logs(limit=200)
    ]
    return JSONResponse({"items": items})


@app.post("/api/admin/agent/run-cycle")
async def admin_run_cycle(
    payload: AgentRunRequest, request: Request, _: None = Depends(require_admin)
) -> JSONResponse:
    _rate_limit(request)
    goal_id = get_or_create_active_goal(payload.goal, _username(request))
    task_id = create_goal_task(goal_id, f"Cycle action for: {payload.goal}", priority=1)
    result = await run_autonomous_cycle(payload.goal, payload.provider)
    if result["verify_status"] == "PASS":
        mark_task_done(task_id)
    run_id = save_autonomous_run(
        goal_id=goal_id,
        provider=payload.provider,
        result_text=result["result_text"],
        plan_text=result["plan_text"],
        action_text=result["action_text"],
        verify_status=result["verify_status"],
        reflection_text=result["reflection_text"],
        created_by=_username(request),
    )
    save_audit_log(
        _username(request),
        "admin_agent_run_cycle",
        request.client.host if request.client else "unknown",
        f"goal_id={goal_id},run_id={run_id}",
    )
    return JSONResponse({"ok": True, "run_id": run_id, "goal_id": goal_id, **result})


@app.post("/api/admin/agent/queue")
async def admin_queue_goal(
    payload: AgentRunRequest, request: Request, _: None = Depends(require_admin)
) -> JSONResponse:
    queue_id = enqueue_autonomy_goal(payload.goal, payload.provider, _username(request), payload.priority)
    save_audit_log(
        _username(request),
        "admin_agent_queue_goal",
        request.client.host if request.client else "unknown",
        f"queue_id={queue_id}",
    )
    return JSONResponse({"ok": True, "queue_id": queue_id})


@app.get("/api/admin/agent/runs")
async def admin_agent_runs(request: Request, _: None = Depends(require_admin)) -> JSONResponse:
    items = [
        {
            "id": run_id,
            "goal_id": goal_id,
            "provider": provider,
            "result_text": result_text,
            "plan_text": plan_text,
            "action_text": action_text,
            "verify_status": verify_status,
            "reflection_text": reflection_text,
            "created_at": created_at,
        }
        for run_id, goal_id, provider, result_text, plan_text, action_text, verify_status, reflection_text, created_at in list_autonomous_runs(30)
    ]
    return JSONResponse({"items": items})


@app.get("/api/admin/agent/queue")
async def admin_agent_queue(request: Request, _: None = Depends(require_admin)) -> JSONResponse:
    items = [
        {
            "id": qid,
            "goal": goal,
            "provider": provider,
            "status": status,
            "priority": priority,
            "attempts": attempts,
            "created_by": created_by,
            "last_error": last_error,
            "created_at": created_at,
        }
        for qid, goal, provider, status, priority, attempts, created_by, last_error, created_at in list_queue_items(100)
    ]
    return JSONResponse({"items": items})


@app.post("/api/admin/agent/worker")
async def admin_agent_worker(
    payload: AgentWorkerRequest, request: Request, _: None = Depends(require_admin)
) -> JSONResponse:
    global _AUTONOMY_WORKER_ENABLED, _AUTONOMY_WORKER_TASK, _AUTONOMY_ITERATIONS, _AUTONOMY_FAIL_STREAK
    if payload.enabled:
        _AUTONOMY_WORKER_ENABLED = True
        _AUTONOMY_ITERATIONS = 0
        _AUTONOMY_FAIL_STREAK = 0
        if not _AUTONOMY_WORKER_TASK or _AUTONOMY_WORKER_TASK.done():
            _AUTONOMY_WORKER_TASK = asyncio.create_task(_autonomy_worker_loop())
        save_audit_log(_username(request), "admin_agent_worker_start", request.client.host if request.client else "unknown")
    else:
        _AUTONOMY_WORKER_ENABLED = False
        if _AUTONOMY_WORKER_TASK and not _AUTONOMY_WORKER_TASK.done():
            _AUTONOMY_WORKER_TASK.cancel()
        save_audit_log(_username(request), "admin_agent_worker_stop", request.client.host if request.client else "unknown")
    return JSONResponse(
        {
            "ok": True,
            "enabled": _AUTONOMY_WORKER_ENABLED,
            "iterations": _AUTONOMY_ITERATIONS,
            "fail_streak": _AUTONOMY_FAIL_STREAK,
            "max_iterations": settings.autonomy_max_iterations,
        }
    )


@app.get("/api/admin/agent/worker")
async def admin_agent_worker_status(request: Request, _: None = Depends(require_admin)) -> JSONResponse:
    running = bool(_AUTONOMY_WORKER_TASK and not _AUTONOMY_WORKER_TASK.done() and _AUTONOMY_WORKER_ENABLED)
    return JSONResponse(
        {
            "enabled": _AUTONOMY_WORKER_ENABLED,
            "running": running,
            "iterations": _AUTONOMY_ITERATIONS,
            "fail_streak": _AUTONOMY_FAIL_STREAK,
            "fail_streak_limit": settings.autonomy_fail_streak_limit,
            "max_iterations": settings.autonomy_max_iterations,
            "interval_sec": settings.autonomy_interval_sec,
        }
    )


@app.get("/api/admin/agent/goals/{goal_id}/tasks")
async def admin_goal_tasks(goal_id: int, request: Request, _: None = Depends(require_admin)) -> JSONResponse:
    items = [
        {"id": tid, "content": content, "status": status, "priority": priority}
        for tid, content, status, priority in list_goal_tasks(goal_id)
    ]
    return JSONResponse({"items": items})
