from uuid import uuid4

import sqlalchemy as sa

from app import main
from app.store import sessions
from test_entry import client, start


def test_full_scenario_and_field_scope(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}

    def ask(role, text):
        version = client.get(path, headers=auth).json()["state_version"]
        response = client.post(path + "/messages", headers={**auth, "Idempotency-Key": str(uuid4())},
                               json={"role_id": role, "content": text, "expected_version": version})
        assert response.status_code == 200
        return client.get(path, headers=auth).json()["stage"]

    assert ask("lin_yue", "薪资多少？") == "S1"
    assert ask("lin_yue", "我对这个岗位感兴趣") == "S1"
    assert ask("chen_hao", "我对这个岗位感兴趣") == "S2"
    assert ask("chen_hao", "简历不交但项目经历可以聊") == "S2"
    ask("chen_hao", "简历先不交，你们收它做什么？")
    assert ask("chen_hao", "谁在收资料？") == "S4"
    ask("chen_hao", "保存多久？")
    ask("chen_hao", "能提供独立核对的官方渠道吗？")
    ask("wang_yu", "你亲自核实过吗？")
    version = client.get(path, headers=auth).json()["state_version"]
    done = client.post(path + "/decisions", headers={**auth, "Idempotency-Key": str(uuid4())},
                       json={"expected_version": version, "choice": "verify_first"})
    assert done.status_code == 200
    with main.engine.connect() as conn:
        state = conn.execute(sa.select(sessions.c.state)).scalar_one()
    assert set(e["name"] for e in state["events"]) == {
        "SESSION_CREATED", "USER_EXPRESSES_INTEREST", "REGISTRATION_REQUESTED",
        "USER_RESPONDS_TO_INFO_REQUEST", "USER_ASKS_RECRUITMENT_IDENTITY", "USER_ASKS_DATA_USAGE",
        "USER_REQUESTS_VERIFICATION", "USER_CHECKS_FRIEND_SOURCE", "USER_MAKES_DECISION", "SESSION_COMPLETED",
    }
    first = next(e for e in state["events"] if e["name"] == "USER_RESPONDS_TO_INFO_REQUEST")
    assert first["fields"] == {"简历": "拒绝", "项目经历": "同意"}
    clues = done.json()["disclosures"]
    assert {c["clue"] for c in clues} == {"K01", "K02", "K03", "K04", "K05"}
    assert all("第三方" not in c["excerpt"] for c in clues if c["clue"] == "K03")
