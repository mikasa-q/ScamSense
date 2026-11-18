from uuid import uuid4

import sqlalchemy as sa

from app import main
from app.store import sessions
from test_entry import client, start


def test_private_verification_and_replay(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"] + "/messages"
    headers = {"Authorization": "Bearer " + created["session_token"], "Idempotency-Key": str(uuid4())}
    body = {"role_id": "wang_yu", "content": "你亲自核实过吗？", "expected_version": 0}
    stream = client.post(path, headers=headers, json=body)
    assert stream.status_code == 200 and stream.headers["content-type"].startswith("text/event-stream")
    assert stream.text.count("event: delta") >= 2 and "event: complete" in stream.text
    assert client.post(path, headers=headers, json=body).text == stream.text
    assert client.post(path, headers=headers, json=dict(body, content="另一个问题")).status_code == 409
    history = client.get(path, headers=headers, params={"role_id": "wang_yu"}).json()["items"]
    assert len(history) == 3 and history[1]["content"] == body["content"]
    assert "没有亲自核实" in history[2]["content"]
    assert len(client.get(path, headers=headers, params={"role_id": "chen_hao"}).json()["items"]) == 1
    with main.engine.connect() as conn:
        state = conn.execute(sa.select(sessions.c.state)).scalar_one()
    assert state["events"][-1]["message_id"] == history[1]["id"]
    assert state["disclosures"][0]["message_id"] == history[2]["id"]
    assert state["disclosures"][0]["clue"] == "K05"
    headers["Idempotency-Key"] = str(uuid4())
    assert client.post(path, headers=headers, json=body).status_code == 409


def test_input_and_role_partition(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"] + "/messages"
    auth = {"Authorization": "Bearer " + created["session_token"]}

    def ask(role, text, version):
        return client.post(path, headers={**auth, "Idempotency-Key": str(uuid4())},
                           json={"role_id": role, "content": text, "expected_version": version})

    assert ask("lin_yue", "person@example.invalid", 0).status_code == 422
    assert ask("lin_yue", "薪资多少？", 0).status_code == 200
    assert ask("chen_hao", "我刚才问了什么？", 1).status_code == 200
    last = client.get(path, headers=auth, params={"role_id": "chen_hao"}).json()["items"][-1]
    assert "第一个问题" in last["content"]
    assert "薪资多少" not in last["content"]
