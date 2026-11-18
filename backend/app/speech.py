import re


ATTRIBUTION = re.compile(
    r"^(?:我(?:只是|来)?(?:转述|转告|转发)|"
    r"(?:据|听|我听)?(?:王宇|陈浩|林悦|朋友|同学|对方|他|她|另一(?:位|个)(?:招聘)?(?:顾问|HR))"
    r"(?:刚才|之前|刚|曾)?(?:说|问|提到|告诉我|表示|让我|没(?:有)?(?:解释|说明|说清)))"
)
OWN_VOICE = re.compile(
    r"^(?:但(?:是)?|不过|那么?)?(?:我(?:自己|个人)|我(?:也|还|现在)?(?:想|希望)(?:请)?(?:问|知道|了解)|"
    r"我的问题|我的判断|我觉得|我认为|请问|请你)"
)
DELIMITER = re.compile(r'''“[^”]*(?:”|$)|「[^」]*(?:」|$)|『[^』]*(?:』|$)|‘[^’]*(?:’|$)|"[^"]*(?:"|$)|[，,。；;！？?!\n]+''')


def _phrases(text):
    start = 0
    for token in DELIMITER.finditer(text):
        if token.group().startswith(("“", "「", "『", "‘", '"')) and not OWN_VOICE.match(text[token.end():].lstrip()):
            continue
        yield text[start:token.end()]
        start = token.end()
    if start < len(text):
        yield text[start:]


def split_relay(text: str) -> tuple[str, bool]:
    segments = [[]]
    reporting = found = False
    for part in _phrases(text):
        clause = part.strip().rstrip("，,。；;！？?!")
        if ATTRIBUTION.match(clause):
            reporting = found = True
        elif OWN_VOICE.match(clause):
            reporting = False
        if not reporting:
            segments[-1].append(part)
        elif segments[-1]:
            segments.append([])
        if re.search(r"[。；;！？?!\n]\s*$", part) or clause.endswith(("”", "」", "』", "’", '"')):
            reporting = False
    if not found:
        return text, False
    excerpts = ["".join(segment).strip(" ，,\n") for segment in segments if segment]
    return "\n".join(excerpts), True


def own_words(message: dict) -> str:
    if "own_statement" in message:
        return message["own_statement"]
    return split_relay(message["content"])[0]
