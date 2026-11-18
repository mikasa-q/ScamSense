import re
from .scenario import message
from .recruitment import Reply, registration, verify_hr
from .evidence import record_observation
from .model import compose

PRIVATE_DATA = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|\d{15,19}[Xx]?)(?!\d)|[\w.+-]+@[\w.-]+\.\w+|(?:sk-|ghp_|gho_)[\w-]{12,}")


def reply_to(role: str, text: str, history: list[dict]) -> Reply:
    question = text.strip().rstrip("。！？?!")
    if question in {"我上次问了什么", "我刚才问了什么"}:
        previous = next((m["content"] for m in reversed(history) if m["sender"] == "user"), None)
        return Reply(f"你上次在这里说的是「{previous}」。" if previous else "这是你在这段对话里问我的第一个问题。")
    if role == "wang_yu":
        if re.fullmatch(r"(?:你(?:自己|本人)?(?:有|有没有)?亲自核实过(?:这个岗位|这个机会)?(?:没|没有|吗)?|(?:你[的这条]*|这条)?消息(?:是)?从哪[里儿]来[的了]?|你的消息来源是什么)", question):
            return Reply("我在校园群里见过类似的消息。这个机会我没有亲自核实过。", "USER_CHECKS_FRIEND_SOURCE", "K05")
        return Reply("我在校园群里见过类似的岗位。你想问我消息的出处，还是想聊聊找实习的事？", flexible=True)
    if re.search(r"薪资|薪水|工资|待遇", question):
        salary = "8k–10k" if role == "lin_yue" else "9k–12k"
        return Reply(f"这个 Python 后端实习岗位的薪资是 {salary}/月。实习周期是三个月以上。", job_question=True)
    if re.search(r"岗位|工作内容|技术栈|技术要求|实习周期|项目经验", question):
        return Reply("这个岗位参与 API 开发、数据库维护和自动化脚本。需要 Python、MySQL 和 HTTP 基础，课程项目或个人项目都可以。", job_question=True)
    return Reply("你想了解实习岗位的工作内容、技术要求，还是待遇？", flexible=True)


def take_turn(state: dict, role: str, text: str, source_id: str | None = None) -> dict:
    history = state["chats"][role]
    initial_stage = state["stage"]
    user = message(role, "user", text)
    record_observation(state, user, history, source_id)
    replies = registration(state, user) if role == "chen_hao" else []
    if role != "wang_yu":
        replies.extend(verify_hr(role, text))
    if not replies:
        replies = [reply_to(role, text, history)]
    content, mode = compose(role, history, text, [r.text for r in replies], all(r.flexible for r in replies),
                            state.get("notice_version") == "model-demo-v1")
    assistant = {**message(role, "assistant", content), "reply_mode": mode}
    history.extend((user, assistant))
    for event in dict.fromkeys(r.event for r in replies if r.event):
        source = assistant if event == "REGISTRATION_REQUESTED" else user
        state["events"].append({"name": event, "message_id": source["id"], "role_id": role})
    for reply in replies:
        if reply.clue:
            state.setdefault("disclosures", []).append({
                "clue": reply.clue, "message_id": assistant["id"], "role_id": role, "excerpt": reply.text,
            })
    if initial_stage == "S3" and any(r.event and r.event != "REGISTRATION_REQUESTED" for r in replies):
        state["stage"] = "S4"
    elif initial_stage == "S2" and any(r.clue for r in replies):
        state["stage"] = "S3"
    elif state["stage"] == "S0" and any(r.job_question for r in replies):
        state["stage"] = "S1"
    return {"role_id": role, "user_id": user["id"], "reply_id": assistant["id"]}
