import re
from dataclasses import dataclass

from .scenario import message

PRIVATE_DATA = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|\d{15,19}[Xx]?)(?!\d)|[\w.+-]+@[\w.-]+\.\w+|(?:sk-|ghp_|gho_)[\w-]{12,}")


@dataclass(frozen=True)
class Reply:
    text: str
    event: str | None = None
    clue: str | None = None
    job_question: bool = False


def reply_to(role: str, text: str, history: list[dict]) -> Reply:
    question = text.strip().rstrip("。！？?!")
    if question in {"我上次问了什么", "我刚才问了什么"}:
        previous = next((m["content"] for m in reversed(history) if m["sender"] == "user"), None)
        return Reply(f"你上次在这里说的是「{previous}」。" if previous else "这是你在这段对话里问我的第一个问题。")
    if role == "wang_yu":
        if re.fullmatch(r"(?:你(?:自己|本人)?(?:有|有没有)?亲自核实过(?:这个岗位|这个机会)?(?:没|没有|吗)?|(?:你[的这条]*|这条)?消息(?:是)?从哪[里儿]来[的了]?|你的消息来源是什么)", question):
            return Reply("我在校园群里见过类似的消息。这个机会我没有亲自核实过。", "USER_CHECKS_FRIEND_SOURCE", "K05")
        return Reply("我在校园群里见过类似的岗位。你想问我消息的出处，还是想聊聊找实习的事？")
    if re.search(r"薪资|薪水|工资|待遇", question):
        salary = "8k–10k" if role == "lin_yue" else "9k–12k"
        return Reply(f"这个 Python 后端实习岗位的薪资是 {salary}/月。实习周期是三个月以上。", job_question=True)
    if re.search(r"岗位|工作内容|技术栈|技术要求|实习周期|项目经验", question):
        return Reply("这个岗位参与 API 开发、数据库维护和自动化脚本。需要 Python、MySQL 和 HTTP 基础，课程项目或个人项目都可以。", job_question=True)
    return Reply("你想了解实习岗位的工作内容、技术要求，还是待遇？")


def take_turn(state: dict, role: str, text: str) -> dict:
    history = state["chats"][role]
    reply = reply_to(role, text, history)
    user = message(role, "user", text)
    assistant = message(role, "assistant", reply.text)
    history.extend((user, assistant))
    if reply.event:
        state["events"].append({"name": reply.event, "message_id": user["id"], "role_id": role})
    if reply.clue:
        state.setdefault("disclosures", []).append({
            "clue": reply.clue, "message_id": assistant["id"], "role_id": role, "excerpt": reply.text,
        })
    if state["stage"] == "S0" and reply.job_question:
        state["stage"] = "S1"
    return {"role_id": role, "user_id": user["id"], "reply_id": assistant["id"]}
