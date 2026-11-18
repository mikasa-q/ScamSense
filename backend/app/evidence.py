import re

from fastapi import HTTPException

from .scenario import ROLES

GAPS = {
    "K01": ("收集方|收集主体|招聘主体|顾问.{0,5}关系", "不明|不清楚|没.{0,3}说清|没有说明|无法确认"),
    "K02": ("用途|必要性|岗位需要", "不明|不清楚|没.{0,3}说明|不足|没有解释"),
    "K03": ("保存期限|保存多久|第三方|接收方", "不明|不清楚|没.{0,3}说明|没有说|无法确认"),
    "K04": ("独立.{0,4}(?:依据|证据)|官方.{0,4}(?:依据|渠道)", "缺乏|没有|不足|无法|缺少"),
    "K05": ("核实|群消息|转述", "没有(?:亲自)?核实|没(?:有)?查证|未经核实|没(?:亲自)?核实|未核实"),
}

MATERIAL_TOPICS = tuple(re.compile(pattern) for pattern in (
    r"校园群|群里|群消息", r"亲自核实|未经核实",
    r"收集(?:方|主体|资料的主体)|招聘主体", r"用途|必要性|哪一步需要",
    r"保存期限|保存多久", r"第三方|接收方", r"(?:官方|独立).{0,6}(?:渠道|依据)",
    r"薪资|月薪|工资|待遇", r"简历", r"项目经历",
))
ATTRIBUTED_SPEAKER = re.compile(r"(林悦|陈浩|王宇)(?:自己|还|也|并)?(?:说|承认|表示|(?:没(?:有)?|未|已经)?(?:亲自)?核实)")


def supported_analysis(user, source):
    if not user or not source or user["sender"] != "user" or source["sender"] != "assistant":
        return False
    if user["role_id"] != source["role_id"]:
        return False
    text, original = user["content"], source["content"]
    if not re.search(r"不能证明|不足以证明|无法证明|只能说明|因此.{1,20}无法", text):
        return False
    speaker = ROLES[source["role_id"]][0]
    if any(name != speaker and name not in original for name in ATTRIBUTED_SPEAKER.findall(text)):
        return False
    if re.search(r"(?:你|他|王宇)(?:自己|也|并)?(?:没(?:有)?|未)(?:亲自)?核实", text):
        if not re.search(r"(?:没(?:有)?|未)(?:亲自)?核实", original):
            return False
    quotations = re.findall(r'[“「‘"]([^”」’"\n]+)[”」’"]', text)
    if quotations:
        return all(part in original for part in quotations) and bool(re.search(r"\w", "".join(quotations)))
    discusses_source = re.search(r"转述|群消息|口头|自述|来源|核实|独立依据", text)
    return bool(discusses_source and any(topic.search(text) and topic.search(original) for topic in MATERIAL_TOPICS))


def record_observation(state, user, history, reply_to):
    source = next((m for m in reversed(history) if m["sender"] == "assistant" and
                   (reply_to is None or m["id"] == reply_to)), None)
    if reply_to and not source:
        raise HTTPException(422, "只能引用当前私聊里可查看的角色消息。")
    if not source:
        return
    text = user["content"]
    if reply_to:
        user["reply_to"] = source["id"]
    if re.search(r"[?？]|请问|是否|并非|不是(?:说|没有|没)|不能说|不认为", text):
        return
    clues = []
    for d in state.get("disclosures", []):
        if d["message_id"] != source["id"] or d["excerpt"] not in source["content"]:
            continue
        topic, gap = GAPS[d["clue"]]
        if d["clue"] == "K03":
            topic = "期限|保存多久" if "期限" in d["excerpt"] else "第三方|接收方"
        if re.search(topic, text) and re.search(gap, text):
            clues.append(d["clue"])
    analyzes = supported_analysis(user, source)
    if clues or (reply_to and analyzes):
        state.setdefault("observations", []).append({
            "message_id": user["id"], "source_id": source["id"], "role_id": user["role_id"],
            "clues": list(dict.fromkeys(clues)), "analyzes": analyzes,
        })
