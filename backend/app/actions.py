import hashlib
import time

import sqlalchemy as sa
from fastapi import HTTPException

from .store import sessions


def apply_action(engine, row, key, body, action, change):
    """Commit the result and its retry receipt together, after checking the session version."""
    signature = hashlib.sha256((action + body.model_dump_json(exclude_none=True)).encode()).hexdigest()

    def replay(current):
        receipt = current["state"].get("operations", {}).get(str(key))
        if receipt and receipt["signature"] != signature:
            raise HTTPException(409, "请求标识已用于另一项操作。")
        return receipt

    receipt = replay(row)
    if receipt:
        return row["state"], receipt["result"]
    if row["state"]["status"] != "active" or body.expected_version != row["version"]:
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
