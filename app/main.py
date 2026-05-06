import json
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
    create_user,
    ensure_default_user,
    get_feedback_summary,
    get_recent_memories,
    get_user,
    init_db,
    list_audit_logs,
    list_users,
    save_audit_log,
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


_RATE_BUCKETS: dict[str, list[float]] = {}


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
