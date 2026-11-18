import re
from .scenario import message
from .recruitment import Reply, current_questions, registration, verify_hr
from .evidence import record_observation
from .model import compose
from .speech import own_words, split_relay

PRIVATE_DATA = re.compile(r"(?<!\d)(?:1[3-9]\d{9}|\d{15,19}[Xx]?)(?!\d)|[\w.+-]+@[\w.-]+\.\w+|(?:sk-|ghp_|gho_)[\w-]{12,}")
RELAY_ACK = {
    "lin_yue": "你提到的是另一段交流。我可以向你解释我负责的岗位和招聘流程。",
    "chen_hao": "收到你转述的说法了。你自己想向我核实哪件事？",
    "wang_yu": "听你这么说，我也会重新想想自己的印象。你转述的情况，我手头没有别的依据。",
}


def reply_to(role: str, text: str, history: list[dict], questions: str) -> Reply:
    question = text.strip().rstrip("。！？?!")
    if question in {"不想继续了", "我不想继续了", "不想再继续了", "我不想再继续了"}:
        return Reply("你想先停下这个话题，还是暂停训练？页面上的按钮可以暂停训练、确认招聘选择或提前结束。")
    if question in {"我上次问了什么", "我刚才问了什么"}:
        previous = next((m["content"] for m in reversed(history) if m["sender"] == "user"), None)
        return Reply(f"你上次在这里说的是「{previous}」。" if previous else "这是你在这段对话里问我的第一个问题。")
    if role == "wang_yu":
        if re.fullmatch(r"(?:你(?:自己|本人)?(?:有|有没有)?亲自核实过(?:这个岗位|这个机会)?(?:没|没有|吗)?|(?:你[的这条]*|这条)?消息(?:是)?从哪[里儿]来[的了]?|你的消息来源是什么)", question):
            return Reply("我在校园群里见过类似的消息。这个机会我没有亲自核实过。", "USER_CHECKS_FRIEND_SOURCE", "K05")
        return Reply("我在校园群里见过类似的岗位。你想问我消息的出处，还是想聊聊找实习的事？", flexible=True)
    if re.search(r"薪资|薪水|工资|待遇", questions):
        salary = "8k–10k" if role == "lin_yue" else "9k–12k"
        return Reply(f"这个 Python 后端实习岗位的薪资是 {salary}/月。实习周期是三个月以上。", job_question=True)
    if re.search(r"学历|专业要求", questions):
        return Reply("学历要求是本科及以上，计算机相关专业优先。", job_question=True)
    if re.search(r"实习(?:周期|多久|多长|时间)|几个月", questions):
        return Reply("实习周期是三个月以上。", job_question=True)
    if re.search(r"招聘流程|招聘步骤|怎么申请", questions):
        process = ("我这边会通过简历和项目经历了解与岗位相关的技能和经验。" if role == "lin_yue"
                   else "可以先了解岗位，感兴趣后再聊候选人预登记。")
        return Reply(process, job_question=True)
    if re.search(r"公司名|公司叫|哪家(?:公司|企业)|工作地[点址]|在哪(?:儿|里)?(?:工作|办公)", questions):
        return Reply("目前的岗位介绍中没有可供核对的具体公司名称或办公地点。", job_question=True)
    if re.search(r"岗位|工作内容|职责|技术栈|技术要求|项目经验|课程项目|个人项目", questions):
        return Reply("这个岗位参与 API 开发、数据库维护和自动化脚本。需要 Python、MySQL 和 HTTP 基础，课程项目或个人项目都可以。", job_question=True)
    return Reply("你想了解实习岗位的工作内容、技术要求，还是待遇？", flexible=True)


def take_turn(state: dict, role: str, text: str, source_id: str | None = None) -> dict:
    history = state["chats"][role]
    initial_stage = state["stage"]
    user = message(role, "user", text)
    direct, relayed = split_relay(text)
    if relayed:
        user["own_statement"] = direct
    record_observation(state, user, history, source_id)
    questions = current_questions(direct)
    replies = registration(state, user) if role == "chen_hao" else []
    if role != "wang_yu":
        previously_requested = any(e["name"] == "REGISTRATION_REQUESTED" and e.get("role_id") == role
                                   for e in state["events"])
        replies.extend(verify_hr(role, direct, questions, previously_requested))
    if not replies:
        replies = [Reply(RELAY_ACK[role]) if relayed and not direct else reply_to(role, direct, history, questions)]
    content, mode = compose(role, history, text, [r.text for r in replies], all(r.flexible for r in replies),
                            state.get("notice_version") == "model-demo-v1")
    assistant = {**message(role, "assistant", content), "reply_mode": mode}
    normalized = direct.strip().rstrip("。！？?!")
    repeated = any(m["sender"] == "user" and own_words(m).strip().rstrip("。！？?!") == normalized
                   for m in history)
    history.extend((user, assistant))
    for event in dict.fromkeys(r.event for r in replies if r.event):
        source = assistant if event == "REGISTRATION_REQUESTED" else user
        state["events"].append({"name": event, "message_id": source["id"], "role_id": role})
    for reply in replies:
        if reply.clue:
            state.setdefault("disclosures", []).append({
                "clue": reply.clue, "message_id": assistant["id"], "role_id": role, "excerpt": reply.text,
            })
    if initial_stage == "S3" and not repeated and any(r.event and r.event != "REGISTRATION_REQUESTED" for r in replies):
        state["stage"] = "S4"
    elif initial_stage == "S2" and any(r.clue for r in replies):
        state["stage"] = "S3"
    elif state["stage"] == "S0" and any(r.job_question for r in replies):
        state["stage"] = "S1"
    return {"role_id": role, "user_id": user["id"], "reply_id": assistant["id"]}
