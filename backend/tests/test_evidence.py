from uuid import uuid4

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
