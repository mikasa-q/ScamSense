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
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, ConfigDict

from .scenario import ROLES, opening_state
from .store import database_url, sessions

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
    privacy_notice_version: Literal["local-demo-v1"]


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


@app.post(prefix, status_code=201)
def create_session(body: CreateSession, key: RequestKey):
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
