from uuid import uuid4

import sqlalchemy as sa

from app import main
from app.dialogue import take_turn
from app.recap import build_report, close_chat
from app.scenario import opening_state
from app.speech import split_relay
from app.store import sessions
from test_entry import client, start


def test_relay_and_own_question_remain_distinct(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}

    def post(action, **body):
        version = client.get(path, headers=auth).json()["state_version"]
        response = client.post(path + "/" + action, headers={**auth, "Idempotency-Key": str(uuid4())},
                               json={"expected_version": version, **body})
        assert response.status_code == 200
        return response

    post("messages", role_id="wang_yu", content="模拟贴纸叫蓝桦。")
    post("messages", role_id="chen_hao", content="我转述王宇的话：“我对这个岗位感兴趣，简历可以交。”")
    post("messages", role_id="chen_hao", content="王宇问我谁在收资料。")
    history = client.get(path + "/messages?role_id=chen_hao", headers=auth).json()["items"]
    assert all("蓝桦" not in m["content"] for m in history)
    assert "转述" in history[-1]["content"]
    with main.engine.connect() as conn:
        state = conn.execute(sa.select(sessions.c.state)).scalar_one()
    assert state["stage"] == "S0" and "registration" not in state and not state.get("disclosures")
    assert [e["name"] for e in state["events"]] == ["SESSION_CREATED"]

    question = "我想问的是保存多久？"
    mixed = "王宇问我：“谁在收资料，资料会交给谁？”" + question
    post("messages", role_id="chen_hao", content=mixed)
    report = post("end").json()
    [entry] = report["dimensions"][1]["evidence"]
    assert entry["own_statement"] == question and entry["content"] == mixed
    assert "保存期限" in entry["source"]["content"] and "第三方" not in entry["source"]["content"]
    assert [d["clue"] for d in report["disclosures"]] == ["K03"]
    assert client.get(path + "/report", headers=auth).json() == report


def test_old_relay_is_not_credited_but_delivered_disclosure_remains(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}
    headers = lambda: {**auth, "Idempotency-Key": str(uuid4())}
    assert client.post(path + "/messages", headers=headers(),
                       json={"expected_version": 0, "role_id": "chen_hao", "content": "谁在收资料？"}).status_code == 200
    report = client.post(path + "/end", headers=headers(), json={"expected_version": 1}).json()
    [old_entry] = report["dimensions"][1]["evidence"]
    # Before the attribution fix the same event and reply were saved for a relayed question.
    mixed = "王宇问我谁在收资料，我想问工资是多少？"
    with main.engine.begin() as conn:
        state = conn.execute(sa.select(sessions.c.state)).scalar_one()
        state["chats"]["chen_hao"][1]["content"] = mixed
        state["report"]["dimensions"][1]["evidence"][0]["content"] = mixed
        conn.execute(sessions.update().where(sessions.c.id == created["session"]["id"]).values(state=state))
    fixed = client.get(path + "/report", headers=auth).json()
    assert fixed["dimensions"][1]["evidence"] == [] and fixed["disclosures"] == report["disclosures"]
    assert fixed["disclosures"][0]["message_id"] == old_entry["source"]["id"]
    assert client.post(path + "/report/retry", headers=headers()).json() == fixed


def test_relay_cannot_grant_consent_or_supply_the_users_judgment():
    interrupted = "我想问资料用途，王宇问我谁在收资料，我还想问保存多久？"
    words, relayed = split_relay(interrupted)
    assert relayed and words.splitlines() == ["我想问资料用途", "我还想问保存多久？"]
    state = opening_state(str(uuid4()), "local-demo-v1")
    take_turn(state, "chen_hao", "我对这个岗位感兴趣")
    take_turn(state, "chen_hao", "王宇说：“简历可以交。”")
    assert not state["registration"]["answers"]
    assert not any(e["name"] == "USER_RESPONDS_TO_INFO_REQUEST" for e in state["events"])
    verified = take_turn(state, "wang_yu", "你亲自核实过吗？")
    text = "你没有亲自核实，所以群消息不足以证明岗位可靠。"
    take_turn(state, "wang_yu", "我转述林悦的看法：“" + text + "”", verified["reply_id"])
    assert not state.get("observations")
    own = "我自己的判断是" + text
    take_turn(state, "wang_yu", "陈浩说可以相信群里的说法，" + own, verified["reply_id"])
    close_chat(state, str(uuid4()), "undecided", "")
    dimensions = build_report(state)["dimensions"]
    for index in (0, 3):
        [evidence] = dimensions[index]["evidence"]
        assert evidence["own_statement"] == own and evidence["source"]["id"] == verified["reply_id"]
