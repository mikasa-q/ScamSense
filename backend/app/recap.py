from datetime import UTC, datetime

import sqlalchemy as sa
from fastapi import HTTPException

from .evidence import identified_clues, supported_analysis
from .recruitment import clauses, current_questions, is_check_plan, verify_hr
from .speech import own_words
from .store import sessions

CHOICES = {"continue": "继续提交", "necessary_only": "仅提交必要资料",
           "verify_first": "先核实再决定", "decline": "退出招聘流程"}
VERIFY = {"USER_ASKS_RECRUITMENT_IDENTITY", "USER_ASKS_DATA_USAGE",
          "USER_REQUESTS_VERIFICATION", "USER_CHECKS_FRIEND_SOURCE"}
WEIGHTS = {"风险识别": 25, "主动核实": 30, "决策合理性": 25, "证据分析": 20}


def close_chat(state: dict, operation: str, choice: str, reason: str, reason_message_id: str | None = None) -> dict:
    if reason_message_id:
        user_message = any(m["id"] == reason_message_id and m["sender"] == "user"
                           for chat in state["chats"].values() for m in chat)
        if choice == "undecided" or not user_message:
            raise HTTPException(422, "只能引用本次训练中自己发送的消息作为决定理由。")
    state.update(stage="S5", status="evaluating")
    state["decision"] = {
        "operation": operation, "choice": choice, "reason": reason,
        "confirmed_at": datetime.now(UTC).isoformat(),
    }
    if reason_message_id:
        state["decision"]["reason_message_id"] = reason_message_id
    if choice != "undecided":
        state["events"].append({"name": "USER_MAKES_DECISION", "operation": operation})
    return {"operation": operation}


def verification_evidence(state: dict, messages: dict) -> list:
    requests = {}
    for event in state["events"]:
        if event["name"] in VERIFY:
            requests.setdefault((event["message_id"], event["role_id"]), set()).add(event["name"])
    # A committed chat operation identifies both messages, including in older sessions.
    replies = {}
    for operation in state.get("operations", {}).values():
        turn = operation["result"]
        if "user_id" in turn:
            replies[turn["user_id"]] = turn["reply_id"]
    for message in messages.values():
        if message["sender"] == "user":
            replies.setdefault(message["id"], None)

    evidence = []
    for user_id, reply_id in replies.items():
        user = messages.get(user_id)
        if not user or user["sender"] != "user":
            continue
        words = own_words(user)
        if not words:
            continue
        plans = [part for part in clauses(words) if is_check_plan(part)]
        events = requests.get((user_id, user["role_id"]), set())
        asked = bool(events)
        if asked and words != user["content"] and "own_statement" not in user:
            own_replies = verify_hr(user["role_id"], words, current_questions(words), False) if user["role_id"] != "wang_yu" else []
            asked = any(reply.event in events for reply in own_replies)
        if not (plans or asked):
            continue
        item = {**user, "verification": "request" if asked else "plan", "plans": plans}
        if words != user["content"]:
            item["own_statement"] = words
        reply = messages.get(reply_id)
        if asked and reply and reply["sender"] == "assistant" and reply["role_id"] == user["role_id"]:
            item["source"] = reply
        evidence.append(item)
    return evidence


def evidence_explanation(name, items, choice):
    if name == "决策合理性" and not items:
        if choice == "undecided":
            return "你提前结束了训练，本次没有确认招聘选择。"
        return "已确认招聘选择，本次缺少能归属于该选择的理由原话。"
    if not items:
        return "本次没有足以评估这一维度的证据。"
    if name != "主动核实":
        return "已有行为证据，数字量表待确认。"
    if any(item["verification"] == "request" for item in items):
        return "已记录实际核实请求。独立核实的结果还需另有材料支持，数字量表待确认。"
    return "已记录核实计划，本次尚未记录实际核实请求。数字量表待确认。"


def build_report(state: dict) -> dict:
    messages = {m["id"]: m for chat in state["chats"].values() for m in chat}
    decision = state["decision"]
    evidence = {dimension: [] for dimension in WEIGHTS}
    evidence["主动核实"] = verification_evidence(state, messages)
    for obs in state.get("observations", []):
        user, source = messages[obs["message_id"]], messages[obs["source_id"]]
        if user["sender"] != "user" or source["sender"] != "assistant" or user["role_id"] != source["role_id"]:
            continue
        cited = {**user, "source": source}
        words = own_words(user)
        if words != user["content"]:
            cited["own_statement"] = words
        if obs["clues"] and set(obs["clues"]).intersection(identified_clues(state, source, words)):
            evidence["风险识别"].append(cited)
        if obs["analyzes"] and supported_analysis(user, source):
            evidence["证据分析"].append(cited)
    reason = decision["reason"]
    if decision["choice"] != "undecided":
        selected = messages.get(decision.get("reason_message_id"))
        if selected and selected["sender"] == "user":
            evidence["决策合理性"].append({**selected, "operation": decision["operation"]})
            reason = reason or selected["content"]
        if decision["reason"] and not any(e["content"] == reason for e in evidence["决策合理性"]):
            evidence["决策合理性"].append({"operation": decision["operation"], "content": reason})
    dimensions = [
        {"name": name, "weight": weight, "score": None, "evidence": evidence[name],
         "explanation": evidence_explanation(name, evidence[name], decision["choice"])}
        for name, weight in WEIGHTS.items()
    ]
    return {
        "choice": decision["choice"], "choice_label": CHOICES.get(decision["choice"], "未决定"),
        "ended_early": decision["choice"] == "undecided", "reason": reason,
        "dimensions": dimensions, "total_score": None, "disclosures": [
            {**d, "visibility": "可查看，展示情况未知"} for d in state.get("disclosures", [])
            if d["excerpt"] in messages[d["message_id"]]["content"]
        ],
    }


def checked_report(state: dict) -> dict:
    report = state["report"]
    affected = {d["name"] for d in report["dimensions"] if d["name"] != "决策合理性"
                and any("own_statement" not in e and own_words(e) != e["content"] for e in d["evidence"])}
    if affected:
        corrected = {d["name"]: d for d in build_report(state)["dimensions"]}
        report = {**report, "total_score": None, "dimensions": [
            corrected[d["name"]] if d["name"] in affected else d for d in report["dimensions"]
        ]}
    analysis = next((d for d in report["dimensions"] if d["name"] == "证据分析"), None)
    if not analysis or not analysis["evidence"]:
        return report
    messages = {m["id"]: m for chat in state["chats"].values() for m in chat}
    verified = []
    for item in analysis["evidence"]:
        user = messages.get(item.get("id"))
        cited = item.get("source") or {}
        source = messages.get(cited.get("id"))
        if supported_analysis(user, source):
            if user["content"] == item["content"] and source["content"] == cited.get("content"):
                verified.append(item)
    if len(verified) == len(analysis["evidence"]):
        return report
    updated = {**analysis, "evidence": verified, "score": None,
               "explanation": evidence_explanation("证据分析", verified, report["choice"])}
    return {**report, "dimensions": [updated if d is analysis else d for d in report["dimensions"]], "total_score": None}


def complete_report(engine, session_id: str):
    # The S5 commit already closed the conversation. Retrying uses that same evidence.
    with engine.begin() as conn:
        row = conn.execute(sa.select(sessions).where(sessions.c.id == session_id)).mappings().one_or_none()
        if not row or row["expires_at"] <= datetime.now(UTC).timestamp():
            raise HTTPException(410, "训练已过期")
        state = row["state"]
        if state["status"] == "completed":
            return checked_report(state)
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
            return checked_report(other)
        return report
