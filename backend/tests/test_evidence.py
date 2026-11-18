from uuid import uuid4

import pytest

from test_entry import client, start


def test_judgment_cites_real_private_message(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}
    def ask(role, text, version, source=None):
        return client.post(path + "/messages", headers={**auth, "Idempotency-Key": str(uuid4())},
                           json={"expected_version": version, "role_id": role, "content": text, "reply_to": source})

    assert ask("wang_yu", "你的消息从哪里来的？", 0).status_code == 200
    source = client.get(path + "/messages", headers=auth, params={"role_id": "wang_yu"}).json()["items"][-1]
    judgment = "你没有亲自核实，所以群消息不足以证明岗位可靠。"
    assert ask("chen_hao", judgment, 1, source["id"]).status_code == 422
    assert ask("wang_yu", "你没有亲自核实吗？", 1, source["id"]).status_code == 200
    assert ask("wang_yu", judgment, 2, source["id"]).status_code == 200
    result = client.post(path + "/end", headers={**auth, "Idempotency-Key": str(uuid4())},
                         json={"expected_version": 3}).json()
    for index in (0, 3):
        refs = result["dimensions"][index]["evidence"]
        assert len(refs) == 1 and refs[0]["content"] == judgment
        assert refs[0]["source"] == source and refs[0]["id"] != source["id"]
        assert result["dimensions"][index]["score"] is None


@pytest.mark.parametrize(("cite", "note"), [(False, ""), (True, ""), (True, "repeat"), (True, "我还需要独立依据。")])
def test_decision_can_use_own_earlier_message_as_reason(client, cite, note):
    def conversation():
        created = start(client).json()
        path = "/api/v1/sessions/" + created["session"]["id"]
        auth = {"Authorization": "Bearer " + created["session_token"]}
        chat = {"expected_version": 0, "role_id": "wang_yu", "content": "我想先核实，群里的消息还不足以证明岗位可靠。"}
        assert client.post(path + "/messages", headers={**auth, "Idempotency-Key": str(uuid4())}, json=chat).status_code == 200
        messages = client.get(path + "/messages?role_id=wang_yu", headers=auth).json()["items"]
        return path, auth, messages

    path, auth, own = conversation()
    _, _, other = conversation()
    operation = str(uuid4())
    headers = {**auth, "Idempotency-Key": operation}
    body = {"expected_version": 1, "choice": "verify_first"}
    for invalid in (own[2]["id"], other[1]["id"]):
        response = client.post(path + "/decisions", headers=headers, json={**body, "reason_message_id": invalid})
        assert response.status_code == 422
    assert client.get(path, headers=auth).json()["status"] == "active"
    if cite:
        body["reason_message_id"] = own[1]["id"]
    if note:
        body["reason"] = own[1]["content"] if note == "repeat" else note
    result = client.post(path + "/decisions", headers=headers, json=body)
    assert result.status_code == 200
    report = result.json()
    decision = next(d for d in report["dimensions"] if d["name"] == "决策合理性")
    assert decision["score"] is None
    if cite:
        expected = [{**own[1], "operation": operation}]
        if note and note != "repeat":
            expected.append({"operation": operation, "content": note})
        assert decision["evidence"] == expected
        assert report["reason"] == body.get("reason", own[1]["content"])
    else:
        assert not decision["evidence"] and not report["reason"]
        assert "缺少能归属于该选择的理由原话" in decision["explanation"]
    assert client.post(path + "/decisions", headers=headers, json=body).json() == report
