import hashlib
import threading
import time

import sqlalchemy as sa
from fastapi import HTTPException

from .store import sessions

_active_sessions: set[str] = set()
_guard = threading.Lock()


def apply_action(engine, row, key, body, action, change):
    """Commit the result and its retry receipt together, after checking the session version."""
    # Single-worker demo: keep an in-flight model turn from being overtaken by an exit.
    with _guard:
        if row["id"] in _active_sessions:
            raise HTTPException(409, "上一项操作还在处理，请稍后重试。")
        _active_sessions.add(row["id"])
    try:
        return _commit_action(engine, row, key, body, action, change)
    finally:
        with _guard:
            _active_sessions.remove(row["id"])


def _commit_action(engine, row, key, body, action, change):
    signature = hashlib.sha256((action + body.model_dump_json(exclude_none=True)).encode()).hexdigest()

    def replay(current):
        receipt = current["state"].get("operations", {}).get(str(key))
        if receipt and receipt["signature"] != signature:
            raise HTTPException(409, "请求标识已用于另一项操作。")
        return receipt

    receipt = replay(row)
    if receipt:
        return row["state"], receipt["result"]
    required_status = "paused" if action == "resume" else "active"
    if row["state"]["status"] != required_status or body.expected_version != row["version"]:
        raise HTTPException(409, "训练已更新，请刷新后重试。")
    state = row["state"]
    result = change(state)
    state.setdefault("operations", {})[str(key)] = {"signature": signature, "result": result}
    with engine.begin() as conn:
        written = conn.execute(sessions.update().where(
            sessions.c.id == row["id"], sessions.c.version == row["version"], sessions.c.expires_at > time.time(),
        ).values(state=state, version=row["version"] + 1))
        if written.rowcount:
            return state, result
        current = conn.execute(sa.select(sessions).where(sessions.c.id == row["id"])).mappings().one_or_none()
        if current is None or current["expires_at"] <= time.time():
            raise HTTPException(410, "训练已过期")
        receipt = replay(current)
        if receipt:
            return current["state"], receipt["result"]
        raise HTTPException(409, "训练已更新，请刷新后重试。")
