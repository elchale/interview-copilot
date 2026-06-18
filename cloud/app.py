"""FastAPI cloud backend: landing/download, Google OAuth, device pairing,
per-user live feed (SSE) and agent audio ingest (WebSocket)."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets

from fastapi import FastAPI, Form, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from sse_starlette.sse import EventSourceResponse
from starlette.middleware.sessions import SessionMiddleware

from . import auth, pages
from .config import load_config
from .crypto import decrypt, encrypt
from .db import PairCode, User, get_session, init_engine
from .publisher import CloudSettings, HubRegistry

logger = logging.getLogger(__name__)

config = load_config()
init_engine(config.database_url)
oauth = auth.create_oauth(config)
registry = HubRegistry()

app = FastAPI(title="Interview Copilot", docs_url=None, redoc_url=None)
app.add_middleware(SessionMiddleware, secret_key=config.secret_key, https_only=config.base_url.startswith("https"))

import os
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# --- helpers ---

def _current_user(request: Request) -> User | None:
    uid = request.session.get("uid")
    if not uid:
        return None
    with get_session() as s:
        return s.get(User, uid)


def _cloud_settings_for(user: User) -> CloudSettings:
    return CloudSettings(
        deepgram_key=decrypt(config.secret_key, user.enc_deepgram_key),
        anthropic_key=decrypt(config.secret_key, user.enc_anthropic_key),
        answer_mode=user.answer_mode,
        persona=user.persona,
        enable_web_search=user.enable_web_search,
    )


# --- public pages ---

@app.get("/", response_class=HTMLResponse)
async def landing(request: Request) -> HTMLResponse:
    return HTMLResponse(pages.landing_page(
        exe_url=config.download_exe_url,
        installer_url=config.download_installer_url,
        logged_in=bool(request.session.get("uid")),
    ))


# --- auth ---

@app.get("/login")
async def login(request: Request, next: str = "/app"):
    request.session["next"] = next
    return await oauth.google.authorize_redirect(request, config.oauth_redirect_uri)


@app.get("/auth/callback")
async def auth_callback(request: Request):
    try:
        token = await oauth.google.authorize_access_token(request)
    except Exception:
        logger.exception("OAuth callback failed")
        return RedirectResponse("/?error=auth")
    userinfo = token.get("userinfo") or {}
    with get_session() as s:
        user = auth.upsert_user(s, userinfo)
        request.session["uid"] = user.id
    return RedirectResponse(request.session.pop("next", "/app"))


@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse("/")


# --- settings (BYO keys) ---

@app.get("/settings", response_class=HTMLResponse)
async def settings_get(request: Request):
    user = _current_user(request)
    if user is None:
        return RedirectResponse("/login?next=/settings")
    return HTMLResponse(pages.settings_page(
        email=user.email,
        has_deepgram=bool(user.enc_deepgram_key),
        has_anthropic=bool(user.enc_anthropic_key),
        answer_mode=user.answer_mode,
        persona=user.persona,
        web_search=user.enable_web_search,
        saved=request.query_params.get("saved") == "1",
    ))


@app.post("/settings")
async def settings_post(
    request: Request,
    deepgram_key: str = Form(""),
    anthropic_key: str = Form(""),
    answer_mode: str = Form("GENERAL"),
    persona: str = Form(""),
    enable_web_search: str = Form(""),
):
    user = _current_user(request)
    if user is None:
        return RedirectResponse("/login?next=/settings")
    with get_session() as s:
        u = s.get(User, user.id)
        if deepgram_key.strip():
            u.enc_deepgram_key = encrypt(config.secret_key, deepgram_key.strip())
        if anthropic_key.strip():
            u.enc_anthropic_key = encrypt(config.secret_key, anthropic_key.strip())
        u.answer_mode = answer_mode
        u.persona = persona
        u.enable_web_search = bool(enable_web_search)
        s.commit()
    return RedirectResponse("/settings?saved=1", status_code=303)


# --- live feed ---

@app.get("/app", response_class=HTMLResponse)
async def feed(request: Request):
    if not request.session.get("uid"):
        return RedirectResponse("/login?next=/app")
    return HTMLResponse(pages.FEED_HTML)


@app.get("/api/stream")
async def stream(request: Request) -> EventSourceResponse:
    user = _current_user(request)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)

    hub = registry.get_or_create(user.id, _cloud_settings_for(user), asyncio.get_event_loop())
    pub = hub.publisher
    q = pub.subscribe()

    async def gen():
        try:
            yield {"event": "init", "data": json.dumps({"sessionId": str(user.id), **pub.snapshot()})}
            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"event": "message", "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            pub.unsubscribe(q)

    return EventSourceResponse(gen())


@app.post("/api/force")
async def force_answer(request: Request):
    user = _current_user(request)
    if user is None:
        return JSONResponse({"error": "unauthorized"}, status_code=401)
    hub = registry.get(user.id)
    if hub:
        hub.force_answer()
    return JSONResponse({"ok": True})


# --- device pairing (agent <-> browser login) ---

@app.post("/pair/start")
async def pair_start():
    device_code = secrets.token_urlsafe(24)
    with get_session() as s:
        s.add(PairCode(device_code=device_code, status="pending"))
        s.commit()
    return JSONResponse({
        "device_code": device_code,
        "verify_url": f"{config.base_url.rstrip('/')}/pair?code={device_code}",
        "poll_url": f"{config.base_url.rstrip('/')}/pair/poll?code={device_code}",
    })


@app.get("/pair", response_class=HTMLResponse)
async def pair(request: Request, code: str = ""):
    if not request.session.get("uid"):
        return RedirectResponse(f"/login?next=/pair?code={code}")
    uid = request.session["uid"]
    try:
        with get_session() as s:
            auth.claim_pair_code(s, code, uid)
    except ValueError:
        return HTMLResponse(pages._shell(  # noqa: SLF001 - simple inline error page
            "Pairing failed",
            '<div class="card">That pairing link is invalid or expired. '
            'Restart the app to try again.</div>',
        ), status_code=400)
    return HTMLResponse(pages.pair_success_page())


@app.get("/pair/poll")
async def pair_poll(code: str = ""):
    with get_session() as s:
        pc = s.query(PairCode).filter_by(device_code=code).one_or_none()
        if pc is None or pc.is_expired():
            return JSONResponse({"status": "expired"}, status_code=404)
        if pc.status == "claimed":
            return JSONResponse({
                "status": "claimed",
                "token": pc.agent_token,
                "ws_url": f"{config.ws_base.rstrip('/')}/ws/agent",
            })
        return JSONResponse({"status": "pending"})


# --- agent audio ingest ---

@app.websocket("/ws/agent")
async def ws_agent(ws: WebSocket):
    token = ws.query_params.get("token", "")
    with get_session() as s:
        device = auth.device_for_token(s, token)
        user = s.get(User, device.user_id) if device else None
    if user is None:
        await ws.close(code=4401)
        return

    await ws.accept()
    hub = registry.get_or_create(user.id, _cloud_settings_for(user), asyncio.get_event_loop())
    # Pick up the latest BYO keys / prefs before starting.
    settings = _cloud_settings_for(user)
    hub.refresh(
        deepgram_key=settings.deepgram_key,
        anthropic_key=settings.anthropic_key,
        answer_mode=settings.answer_mode,
        persona=settings.persona,
        enable_web_search=settings.enable_web_search,
    )
    await hub.agent_connected()
    logger.info("Agent connected for user %s", user.id)
    try:
        while True:
            msg = await ws.receive()
            if msg["type"] == "websocket.disconnect":
                break
            data = msg.get("bytes")
            if data:
                hub.feed(data)
    except WebSocketDisconnect:
        pass
    finally:
        await hub.agent_disconnected()
        logger.info("Agent disconnected for user %s", user.id)


@app.get("/healthz")
async def healthz():
    return {"ok": True}
