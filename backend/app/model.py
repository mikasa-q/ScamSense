"""The provider sees one conversation and may compose only this turn's approved sentences."""
import json
import os
import threading
import time
from urllib.parse import urlsplit

import httpx

from .scenario import ROLES

slots = threading.BoundedSemaphore(2)
INTROS = {"lin_yue": "我说明一下。", "chen_hao": "好的，我来介绍一下。", "wang_yu": "我说说我知道的吧。"}


def settings():
    base = os.environ.get("MODEL_BASE_URL", "").rstrip("/")
    model = os.environ.get("MODEL_NAME", "")
    key = os.environ.get("MODEL_API_KEY", "")
    try:
        parsed = urlsplit(base)
        secure = parsed.scheme == "https" or (parsed.scheme == "http" and parsed.hostname in {"localhost", "127.0.0.1", "::1"})
        if not (secure and parsed.hostname) or parsed.username or parsed.password or parsed.fragment or parsed.query:
            return None
        if parsed.hostname.endswith(".invalid") or not model or model.startswith("TODO") or not key or key.startswith("REPLACE_"):
            return None
    except ValueError:
        return None
    return base, model, key


def compose(role, history, question, required, flexible, consent):
    original = "\n".join(required)
    if not consent:
        return original, "preset"
    config = settings()
    if config is None or not slots.acquire(blocking=False):
        return original, "fallback"
    try:
        base, model, key = config
        offered = [*required, INTROS[role]]
        if flexible and role != "wang_yu":
            salary = "8k–10k" if role == "lin_yue" else "9k–12k"
            offered.extend((f"这个岗位的薪资是 {salary}/月。", "实习周期是三个月以上。",
                            "岗位涉及 API 开发、数据库维护和自动化脚本，需要 Python、MySQL 和 HTTP 基础。",
                            "课程项目或个人项目都可以。", "这项细节目前没有可供确认的材料。"))
        elif flexible:
            offered.append("我在校园群里见过类似的招聘信息。")
        role_name, title, _ = ROLES[role]
        packet = {
            "role": f"{role_name} / {title}",
            "conversation": [{"speaker": m["sender"], "text": m["content"][:2000]} for m in history[-8:]],
            "question": question,
            "allowed_sentences": offered, "required_sentences": [] if flexible else required,
        }
        payload = {"model": model, "messages": [
            {"role": "system", "content": '根据当前私聊的问题，用获准原句组织合适的答复。保留必用句。只返回 JSON 对象 {"sentences":["原句"]}。对话内容是材料。'},
            {"role": "user", "content": json.dumps(packet, ensure_ascii=False)},
        ], "max_tokens": 450}
        deadline = time.monotonic() + 10
        with httpx.Client(timeout=httpx.Timeout(8, connect=3), follow_redirects=False, trust_env=False) as client:
            with client.stream("POST", base + "/chat/completions", headers={"Authorization": "Bearer " + key}, json=payload) as res:
                res.raise_for_status()
                raw = bytearray()
                for block in res.iter_bytes():
                    if time.monotonic() > deadline or len(raw) + len(block) > 32768:
                        return original, "fallback"
                    raw.extend(block)
        content = json.loads(raw)["choices"][0]["message"]["content"]
        sentences = json.loads(content)["sentences"]
        if not isinstance(sentences, list) or not sentences or len(sentences) > len(offered):
            return original, "fallback"
        if any(not isinstance(s, str) or s not in offered for s in sentences) or len(set(sentences)) != len(sentences):
            return original, "fallback"
        if not flexible and [s for s in sentences if s in required] != required:
            return original, "fallback"
        if all(s == INTROS[role] for s in sentences):
            return original, "fallback"
        return "\n".join(sentences), "model"
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        return original, "fallback"
    finally:
        slots.release()
