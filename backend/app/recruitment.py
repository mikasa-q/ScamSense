import re
from dataclasses import dataclass


@dataclass(frozen=True)
class Reply:
    text: str
    event: str | None = None
    clue: str | None = None
    job_question: bool = False
    flexible: bool = False


FIRST_LAYER = ("姓名", "学校", "专业", "毕业时间", "简历", "项目经历")
INTEREST = re.compile(r"(?:我对(?:你(?:介绍)?的|这个|这份)(?:实习)?(?:岗位|机会|工作)(?:很|挺)?感兴趣|我想申请(?:这个|你介绍的)(?:实习)?岗位)")
STOP = re.compile(r"(?:整个登记|所有资料|其余资料|剩下的资料|登记资料).{0,6}(?:先不|暂缓|都不|不再)|(?:暂缓|暂停|先不|不再)(?:整个)?(?:登记|提供资料)")
REQUEST = re.compile(
    r"[?？]|谁|哪|多久|多长|多少|什么|几个月|是否|能否|能不能|可不可以|怎么|怎样|如何|吗|"
    r"请(?:问|提供|说明|介绍|给|告知)|给我.{0,16}(?:渠道|依据)|(?:我想|我希望)(?:了解|问|知道)|介绍一下|讲讲|说说"
)
DEFERRED = re.compile(
    r"^(?:我(?:们)?(?:会)?(?:自己)?)?(?:以后|打算|准备|稍后|回头|改天|已经知道|已经了解|知道了)|"
    r"^(?:我)?(?:不是问|不想问|不用介绍|不打算问)"
)
PLAN = re.compile(
    r"^(?:(?:我(?:们)?)?(?:打算|准备|计划|回头|稍后|以后|改天)|我(?:们)?(?:会|要))"
    r"(?:(?:通过|从|到|上|去|在)(?:学校官网|公司官网|官网|官方渠道)|"
    r"(?:找|向|跟)(?:王宇|林悦|陈浩|朋友|招聘方|对方)|会|再|先|自己|自行|亲自|去){0,6}"
    r"(?:核实|核对|验证|确认|查证|查|询问|问)"
)
CHECK_TARGET = re.compile(
    r"招聘(?:主体|方|公司)|收集(?:主体|方)|谁.{0,6}(?:招|收)|资料的?用途|必要性|保存期限|第三方|"
    r"官方渠道|消息(?:来源|出处)|(?:朋友|王宇).{0,6}亲自核实"
)


def clauses(text: str) -> list[str]:
    return [part.strip() for part in re.split(r"(?<=[。！？?!；;])|[，,\n]", text) if part.strip()]


def is_check_plan(clause: str) -> bool:
    return bool(PLAN.match(clause) and CHECK_TARGET.search(clause) and not re.search(r"[?？“”「」]", clause))


def current_questions(text: str) -> str:
    return " ".join(clause for clause in clauses(text)
                    if REQUEST.search(clause) and not DEFERRED.match(clause) and not PLAN.match(clause))


def field_answers(text: str) -> dict:
    answers = {}
    for clause in re.split(r"[，,。；;\n]|但是|不过|但", text):
        mentioned = [name for name in FIRST_LAYER if name in clause]
        if not mentioned or re.search(r"[?？]|怎么|为什么|用途|做什么|不确定|可不可以|是否|能不能", clause):
            continue
        if re.search(r"暂缓|先不|稍后|以后再", clause):
            status = "暂缓"
        elif re.search(r"拒绝|不(?:愿意|想|交|填|提供|给|谈)|跳过", clause):
            status = "拒绝"
        elif re.search(r"(?:同意|可以|愿意)(?:谈|聊|填|提供|讨论|给)?", clause):
            status = "同意"
        elif len(mentioned) == 1 and re.fullmatch(re.escape(mentioned[0]) + r"\s*[：:]\s*\S.+", clause.strip()):
            status = "已提供"
        else:
            continue
        answers.update(dict.fromkeys(mentioned, status))
    return answers


def registration(state: dict, user: dict) -> list[Reply]:
    text = user["content"]
    reg = state.get("registration")
    interested = any(INTEREST.fullmatch(clause.strip()) for clause in re.split(r"[，,。；;！!\n]", text))
    stop = STOP.search(text) is not None
    offers = []
    if interested:
        state["events"].append({"name": "USER_EXPRESSES_INTEREST", "message_id": user["id"], "role_id": "chen_hao"})
        if state["stage"] in {"S0", "S1"}:
            state["stage"] = "S2"
        if reg is None and not stop:
            state["registration"] = {"answers": {}, "stopped": False}
            offers.append(Reply("可以先做候选人预登记。第一层涉及姓名、学校、专业、毕业时间、简历和项目经历。你愿意谈哪些虚构资料？", "REGISTRATION_REQUESTED"))
    if reg is None:
        return offers
    answers = field_answers(text)
    if not answers and not stop:
        return offers
    reg["stopped"] = reg["stopped"] or stop
    reg["answers"].update(answers)
    state["events"].append({"name": "USER_RESPONDS_TO_INFO_REQUEST", "message_id": user["id"],
                             "role_id": "chen_hao", "fields": answers, "stopped": reg["stopped"]})
    if reg["stopped"]:
        offers.append(Reply("好的，登记就先到这里。你还可以继续问岗位或招聘流程。"))
    else:
        summary = "、".join(f"{name}（{status}）" for name, status in answers.items())
        offers.append(Reply(f"收到，你对这些项目的回应是：{summary}。我们按你愿意谈的范围继续。"))
    return offers


def verify_hr(role: str, text: str, questions: str, registration_requested: bool) -> list[Reply]:
    chen = role == "chen_hao"
    answers = []
    if re.search(r"招聘主体|收集主体|谁.{0,5}(?:招聘|收取|收集|收资料)|顾问.{0,12}关系|(?:招聘|收集)方是谁", questions):
        answers.append(Reply(
            "我负责对接候选人登记，实际收集资料的主体和顾问之间的关系，我这里没有可供核对的说明。" if chen else "我是本公司的招聘专员，只能介绍我们自己的岗位与招聘流程。",
            "USER_ASKS_RECRUITMENT_IDENTITY", "K01" if chen else None))
    if re.search(r"用途|必要|用(?:来|于|在)|(?:有|做)什么用|收.{0,8}做什么|为什么.{0,12}(?:收|要|填|交)", questions):
        requested_item = any(name in text for name in FIRST_LAYER) or bool(
            re.search(r"(?:这些|这项|这份)(?:登记)?资料|(?:收|要)它|^(?:请问)?(?:登记资料|资料|用途)", questions)
        )
        if chen and registration_requested and requested_item:
            answers.append(Reply("这些是候选人预登记资料。具体在哪一步需要，我手边没有更详细的说明。",
                                 "USER_ASKS_DATA_USAGE", "K02"))
        else:
            answers.append(Reply("你想了解哪一项？我们可以按具体登记项目逐项讨论用途。" if chen else
                                 "就我负责的岗位，简历和项目经历主要用于了解岗位相关的技能和经验。", "USER_ASKS_DATA_USAGE"))
    for pattern, topic in [(r"保存|保留|期限", "资料的保存期限"), (r"第三方|转交|接收方|给谁", "资料的第三方处理情况")]:
        if re.search(pattern, questions):
            answers.append(Reply(
                f"关于{topic}，我目前没有能给你核对的具体说明。" if chen else f"关于{topic}，我需要先核对自己这边的流程。",
                "USER_ASKS_DATA_USAGE", "K03" if chen else None))
    if re.search(r"官方.{0,7}(?:渠道|核实|核对|验证)|独立.{0,6}(?:核对|核实|验证|依据)|从官网", questions):
        answers.append(Reply(
            "我现在能提供的是我作为顾问的说明，手上没有可供你独立核对的官方依据。" if chen else "当前模拟材料里没有可展示的官方渠道。",
            "USER_REQUESTS_VERIFICATION", "K04" if chen else None))
    return answers
