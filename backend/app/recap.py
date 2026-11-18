from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException

from .store import sessions

CHOICES = {"continue": "继续提交", "necessary_only": "仅提交必要资料",
           "verify_first": "先核实再决定", "decline": "退出招聘流程"}
VERIFY = {"USER_ASKS_RECRUITMENT_IDENTITY", "USER_ASKS_DATA_USAGE",
          "USER_REQUESTS_VERIFICATION", "USER_CHECKS_FRIEND_SOURCE"}
WEIGHTS = {"风险识别": 25, "主动核实": 30, "决策合理性": 25, "证据分析": 20}


def close_chat(state: dict, operation: str, choice: str, reason: str) -> dict:
    state.update(stage="S5", status="evaluating")
    state["decision"] = {
        "operation": operation, "choice": choice, "reason": reason,
        "confirmed_at": datetime.now(UTC).isoformat(),
    }
    if choice != "undecided":
        state["events"].append({"name": "USER_MAKES_DECISION", "operation": operation})
    return {"operation": operation}


def build_report(state: dict) -> dict:
    messages = {m["id"]: m for chat in state["chats"].values() for m in chat}
    decision = state["decision"]
    evidence = {dimension: [] for dimension in WEIGHTS}
    request_ids = dict.fromkeys(e["message_id"] for e in state["events"] if e["name"] in VERIFY)
    evidence["主动核实"] = [messages[mid] for mid in request_ids if messages[mid]["sender"] == "user"]
    for obs in state.get("observations", []):
        user, source = messages[obs["message_id"]], messages[obs["source_id"]]
        if user["sender"] != "user" or source["sender"] != "assistant" or user["role_id"] != source["role_id"]:
            continue
        cited = {**user, "source": source}
        if obs["clues"]:
            evidence["风险识别"].append(cited)
        if obs["analyzes"]:
            evidence["证据分析"].append(cited)
    if decision["reason"] and decision["choice"] != "undecided":
        evidence["决策合理性"].append({"operation": decision["operation"], "content": decision["reason"]})
    dimensions = [
        {"name": name, "weight": weight, "score": None, "evidence": evidence[name],
         "explanation": "已有行为证据，数字量表待确认。" if evidence[name] else "本次没有足以评估这一维度的证据。"}
        for name, weight in WEIGHTS.items()
    ]
    return {
        "choice": decision["choice"], "choice_label": CHOICES.get(decision["choice"], "未决定"),
        "ended_early": decision["choice"] == "undecided", "reason": decision["reason"],
        "dimensions": dimensions, "total_score": None, "disclosures": [
            {**d, "visibility": "可查看，展示情况未知"} for d in state.get("disclosures", [])
            if d["excerpt"] in messages[d["message_id"]]["content"]
        ],
    }


def complete_report(engine, session_id: str):
    # The S5 commit already closed the conversation. Retrying uses that same evidence.
    with engine.begin() as conn:
        row = conn.execute(sa.select(sessions).where(sessions.c.id == session_id)).mappings().one_or_none()
        if not row or row["expires_at"] <= datetime.now(UTC).timestamp():
            raise HTTPException(410, "训练已过期")
        state = row["state"]
        if state["status"] == "completed":
            return state["report"]
        if state["status"] != "evaluating":
            raise HTTPException(409, "请先确认招聘选择或提前结束训练。")
        try:
            report = build_report(state)
        except (ValueError, KeyError, TypeError) as exc:
            raise HTTPException(503, "已固定对话证据，复盘暂时无法生成。") from exc
        state.update(report=report, stage="S6", status="completed")
        state["events"].append({"name": "SESSION_COMPLETED", "operation": state["decision"]["operation"]})
        changed = conn.execute(sessions.update().where(
            sessions.c.id == session_id, sessions.c.version == row["version"],
        ).values(state=state, version=row["version"] + 1))
        if not changed.rowcount:
            other = conn.execute(sa.select(sessions.c.state).where(sessions.c.id == session_id)).scalar_one()
            if other["status"] != "completed":
                raise HTTPException(409, "训练状态已更新，请重试。")
            return other["report"]
        return report
