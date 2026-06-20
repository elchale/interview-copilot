"""FastAPI web server with SSE streaming for the dashboard."""

from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path
from typing import Any

import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from sse_starlette.sse import EventSourceResponse

from .dashboard import DASHBOARD_HTML
from .settings import SESSIONS_DIR

logger = logging.getLogger(__name__)

app = FastAPI(title="Interview Copilot", docs_url=None, redoc_url=None)


class SSEBus:
    """Pub/sub bus for server-sent events."""

    def __init__(self) -> None:
        self._subscribers: dict[str, list[asyncio.Queue[dict[str, Any]]]] = {}
        self._lock = threading.Lock()

    def subscribe(self, session_id: str) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue()
        with self._lock:
            self._subscribers.setdefault(session_id, []).append(q)
        return q

    def unsubscribe(self, session_id: str, q: asyncio.Queue[dict[str, Any]]) -> None:
        with self._lock:
            subs = self._subscribers.get(session_id, [])
            if q in subs:
                subs.remove(q)

    def publish(self, session_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            for q in self._subscribers.get(session_id, []):
                try:
                    q.put_nowait(event)
                except asyncio.QueueFull:
                    pass

    def publish_global(self, event: dict[str, Any]) -> None:
        with self._lock:
            for subs in self._subscribers.values():
                for q in subs:
                    try:
                        q.put_nowait(event)
                    except asyncio.QueueFull:
                        pass


bus = SSEBus()

# In-memory state for the current session
_state: dict[str, Any] = {
    "current_session_id": None,
    "status": {"recording": False, "analyzing": False, "listening": False, "call_active": False},
    "transcript": [],
    "answers": [],
    "context": [],
}


def update_status(**kwargs: Any) -> None:
    _state["status"].update(kwargs)
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {"type": "status", **_state["status"]})


def new_session() -> str:
    sid = str(uuid.uuid4())[:8]
    _state["current_session_id"] = sid
    _state["transcript"] = []
    _state["answers"] = []
    _state["context"] = []
    logger.info("New session: %s", sid)
    return sid


def get_current_session_id() -> str | None:
    return _state.get("current_session_id")


def add_transcript(text: str, source: str = "system") -> None:
    entry = {"text": text, "source": source, "ts": time.time()}
    _state["transcript"].append(entry)
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {"type": "transcript", "text": text, "source": source})


def add_context(text: str = "", kind: str = "source", url: str = "", answer_id: str | None = None) -> None:
    entry = {"kind": kind, "text": text, "url": url, "answerId": answer_id, "ts": time.time()}
    _state.setdefault("context", []).append(entry)
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {"type": "context", "kind": kind, "text": text, "url": url, "answerId": answer_id})


def start_answer(answer_id: str, question: str = "") -> None:
    _state["answers"].append({"id": answer_id, "text": "", "status": "STREAMING", "question": question})
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {"type": "answer.start", "answerId": answer_id, "question": question})
    update_status(analyzing=True)


def stream_answer_delta(answer_id: str, delta: str) -> None:
    for a in _state["answers"]:
        if a["id"] == answer_id:
            a["text"] += delta
            break
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {"type": "answer.delta", "answerId": answer_id, "text": delta})


def finish_answer(answer_id: str, latency_ms: int | None = None) -> None:
    for a in _state["answers"]:
        if a["id"] == answer_id:
            a["status"] = "DONE"
            a["latencyMs"] = latency_ms
            break
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {
            "type": "answer.done",
            "answerId": answer_id,
            "latencyMs": latency_ms,
        })
    update_status(analyzing=False)
    _save_session()


def error_answer(answer_id: str, error: str = "") -> None:
    for a in _state["answers"]:
        if a["id"] == answer_id:
            a["status"] = "ERROR"
            break
    sid = _state.get("current_session_id")
    if sid:
        bus.publish(sid, {"type": "answer.error", "answerId": answer_id, "error": error})
    update_status(analyzing=False)


def _save_session() -> None:
    """Persist current session to disk."""
    sid = _state.get("current_session_id")
    if not sid:
        return
    SESSIONS_DIR.mkdir(parents=True, exist_ok=True)
    path = SESSIONS_DIR / f"session_{sid}.json"
    data = {
        "id": sid,
        "savedAt": datetime.now().isoformat(),
        "transcript": _state["transcript"],
        "answers": _state["answers"],
    }
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


# --- Routes ---

@app.get("/", response_class=HTMLResponse)
async def dashboard() -> HTMLResponse:
    return HTMLResponse(content=DASHBOARD_HTML)


@app.get("/api/status")
async def status() -> JSONResponse:
    return JSONResponse({
        "sessionId": _state.get("current_session_id"),
        **_state["status"],
    })


@app.get("/api/state")
async def state() -> JSONResponse:
    return JSONResponse({
        "sessionId": _state.get("current_session_id"),
        "transcript": _state["transcript"],
        "answers": _state["answers"],
    })


@app.get("/api/sessions")
async def list_sessions() -> JSONResponse:
    sessions: list[dict[str, Any]] = []
    if SESSIONS_DIR.exists():
        for p in sorted(SESSIONS_DIR.glob("session_*.json"), reverse=True):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                sessions.append({
                    "id": data["id"],
                    "savedAt": data.get("savedAt"),
                    "transcriptLines": len(data.get("transcript", [])),
                    "answers": len(data.get("answers", [])),
                })
            except Exception:
                continue
    return JSONResponse(sessions)


@app.get("/api/sessions/{session_id}")
async def get_session(session_id: str) -> JSONResponse:
    path = SESSIONS_DIR / f"session_{session_id}.json"
    if not path.exists():
        return JSONResponse({"error": "not found"}, status_code=404)
    data = json.loads(path.read_text(encoding="utf-8"))
    return JSONResponse(data)


@app.get("/api/stream")
async def stream(request: Request) -> EventSourceResponse:
    sid = _state.get("current_session_id")
    if not sid:
        sid = new_session()

    q = bus.subscribe(sid)

    async def event_generator():
        try:
            # Send current state on connect
            yield {"event": "init", "data": json.dumps({
                "sessionId": sid,
                "status": _state["status"],
                "transcript": _state["transcript"],
                "answers": _state["answers"],
            })}

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield {"event": "message", "data": json.dumps(event)}
                except asyncio.TimeoutError:
                    yield {"event": "ping", "data": ""}
        finally:
            bus.unsubscribe(sid, q)

    return EventSourceResponse(event_generator())


def start_server(host: str = "127.0.0.1", port: int = 7123) -> threading.Thread:
    """Start uvicorn in a background thread. Returns the thread."""
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="warning",
        access_log=False,
        # Skip uvicorn's dictConfig: its ColourizedFormatter calls
        # sys.stdout.isatty(), which is None under PyInstaller --noconsole.
        log_config=None,
    )
    server = uvicorn.Server(config)

    thread = threading.Thread(target=server.run, daemon=True, name="web-server")
    thread.start()
    logger.info("Web server started at http://%s:%d", host, port)
    return thread
