from uuid import uuid4


ROLES = {
    "lin_yue": ("林悦", "招聘专员", "你好，我是林悦。我们在招 Python 后端开发实习生。你想先了解岗位的哪一部分？"),
    "chen_hao": ("陈浩", "招聘顾问", "你好！我是陈浩，校园招聘这边有一个 Python 后端实习机会，可以先聊聊岗位。"),
    "wang_yu": ("王宇", "大学朋友", "最近找实习怎么样？我在校园群里见过类似的招聘消息。"),
}


def message(role: str, sender: str, content: str) -> dict:
    return {"id": uuid4().hex, "role_id": role, "sender": sender, "content": content}


def opening_state(create_key: str, notice_version: str) -> dict:
    return {
        "stage": "S0",
        "status": "active",
        "notice_version": notice_version,
        "chats": {role: [message(role, "assistant", opening)] for role, (_, _, opening) in ROLES.items()},
        "events": [{"name": "SESSION_CREATED", "operation": create_key}],
    }
