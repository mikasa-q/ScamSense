import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import UTC, datetime
from typing import Annotated, Literal
from uuid import UUID, uuid4

import sqlalchemy as sa
from fastapi import Depends, FastAPI, Header, HTTPException
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict, Field

from .scenario import ROLES, opening_state
from .store import database_url, sessions
from .actions import apply_action
from .dialogue import PRIVATE_DATA, take_turn
from .recap import close_chat, complete_report
from .model import settings as model_settings

app = FastAPI(title="拆招 · ScamSense", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=json.loads(os.getenv("CORS_ALLOWED_ORIGINS", '["http://localhost:5173","http://127.0.0.1:5173"]')),
    allow_methods=["GET", "POST"], allow_headers=["Authorization", "Content-Type", "Idempotency-Key"],
)
engine = sa.create_engine(database_url())
prefix = "/api/v1/sessions"
bearer = HTTPBearer(auto_error=False)
RequestKey = Annotated[UUID, Header(alias="Idempotency-Key")]


class CreateSession(BaseModel):
    model_config = ConfigDict(extra="forbid")
    scenario_id: Literal["internship_v1"]
    privacy_notice_version: Literal["local-demo-v1", "model-demo-v1"]


@app.exception_handler(RequestValidationError)
async def invalid_input(request, exc):
    return JSONResponse({"detail": "请求格式无效，请检查输入。"}, status_code=422)


@app.middleware("http")
async def no_cache(request, call_next):
    response = await call_next(request)
    response.headers["Cache-Control"] = "no-store"
    return response


def snapshot(row) -> dict:
    return {
        "id": row["id"], "stage": row["state"]["stage"], "status": row["state"]["status"],
        "state_version": row["version"],
        "expires_at": datetime.fromtimestamp(row["expires_at"], UTC).isoformat(),
        "roles": [{"id": role, "name": name, "public_title": title} for role, (name, title, _) in ROLES.items()],
    }


def authorized(session_id: str, auth: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
    if auth is None:
        raise HTTPException(401, "需要训练凭证", headers={"WWW-Authenticate": "Bearer"})
    with engine.connect() as conn:
        row = conn.execute(sa.select(sessions).where(sessions.c.id == session_id)).mappings().one_or_none()
    if row is None or not hmac.compare_digest(hashlib.sha256(auth.credentials.encode()).digest(), row["token_hash"]):
        raise HTTPException(404, "找不到这次训练")
    if row["expires_at"] <= time.time():
        raise HTTPException(410, "训练已过期")
    return row


@app.get("/api/v1/training-options")
def training_options():
    return {"model_available": model_settings() is not None}


@app.post(prefix, status_code=201)
def create_session(body: CreateSession, key: RequestKey):
    if body.privacy_notice_version == "model-demo-v1" and model_settings() is None:
        raise HTTPException(503, "当前没有可用的模型配置，可另开本地剧情训练。")
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    row = {
        "id": uuid4().hex, "create_key": str(key), "token_hash": hashlib.sha256(token.encode()).digest(),
        "expires_at": now + 86400, "version": 0,
        "state": opening_state(str(key), body.privacy_notice_version),
    }
    with engine.begin() as conn:
        conn.execute(sa.delete(sessions).where(sessions.c.expires_at <= now))
        try:
            conn.execute(sessions.insert().values(**row))
        except sa.exc.IntegrityError:
            raise HTTPException(409, "这次创建已完成，凭证仅在首次响应返回。") from None
    return {"session": snapshot(row), "session_token": token}


@app.get(prefix + "/{session_id}")
def get_session(row=Depends(authorized)):
    return snapshot(row)


@app.get(prefix + "/{session_id}/messages")
def get_messages(role_id: Literal["lin_yue", "chen_hao", "wang_yu"], row=Depends(authorized)):
    return {"items": row["state"]["chats"][role_id]}


class ChatInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    role_id: Literal["lin_yue", "chen_hao", "wang_yu"]
    content: str = Field(min_length=1, max_length=2000)
    expected_version: int = Field(ge=0)
    reply_to: str | None = Field(default=None, pattern="^[a-f0-9]{32}$")


@app.post(prefix + "/{session_id}/messages")
def post_message(body: ChatInput, key: RequestKey, row=Depends(authorized)):
    if PRIVATE_DATA.search(body.content):
        raise HTTPException(422, "请将联系方式、证件或密钥替换为虚构占位内容。")
    state, sent = apply_action(engine, row, key, body, "chat", lambda state: take_turn(state, body.role_id, body.content, body.reply_to))
    chat = state["chats"][body.role_id]
    by_id = {m["id"]: m for m in chat}
    user, reply = by_id[sent["user_id"]], by_id[sent["reply_id"]]

    def frames():
        def frame(kind, data):
            return f"event: {kind}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"
        yield frame("start", {"user": user, "reply_id": reply["id"]})
        for start in range(0, len(reply["content"]), 16):
            yield frame("delta", {"text": reply["content"][start:start + 16]})
        yield frame("complete", {"reply_id": reply["id"]})

    return StreamingResponse(frames(), media_type="text/event-stream", headers={"X-Accel-Buffering": "no"})


class EndInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    expected_version: int = Field(ge=0)


class DecisionInput(EndInput):
    choice: Literal["continue", "necessary_only", "verify_first", "decline"]
    reason: str = Field(default="", max_length=2000)
    reason_message_id: str | None = Field(default=None, pattern="^[a-f0-9]{32}$")


def change_pause(command, body, key, row):
    def change(state):
        state["status"] = "paused" if command == "pause" else "active"
        return {"status": state["status"], "stage": state["stage"]}

    _, receipt = apply_action(engine, row, key, body, command, change)
    return {"session": snapshot({**row, "state": receipt, "version": body.expected_version + 1})}


@app.post(prefix + "/{session_id}/pause")
def pause_training(body: EndInput, key: RequestKey, row=Depends(authorized)):
    return change_pause("pause", body, key, row)


@app.post(prefix + "/{session_id}/resume")
def resume_training(body: EndInput, key: RequestKey, row=Depends(authorized)):
    return change_pause("resume", body, key, row)


@app.post(prefix + "/{session_id}/decisions")
def decide(body: DecisionInput, key: RequestKey, row=Depends(authorized)):
    if PRIVATE_DATA.search(body.reason):
        raise HTTPException(422, "理由中请使用虚构资料。")
    apply_action(engine, row, key, body, "decision",
                 lambda s: close_chat(s, str(key), body.choice, body.reason, body.reason_message_id))
    return complete_report(engine, row["id"])


@app.post(prefix + "/{session_id}/end")
def end_training(body: EndInput, key: RequestKey, row=Depends(authorized)):
    apply_action(engine, row, key, body, "end", lambda s: close_chat(s, str(key), "undecided", ""))
    return complete_report(engine, row["id"])


@app.get(prefix + "/{session_id}/report")
def get_report(row=Depends(authorized)):
    if row["state"]["status"] != "completed":
        raise HTTPException(409, "复盘还未生成。")
    return row["state"]["report"]


@app.post(prefix + "/{session_id}/report/retry")
def retry_report(key: RequestKey, row=Depends(authorized)):
    return complete_report(engine, row["id"])
