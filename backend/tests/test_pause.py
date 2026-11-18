from uuid import uuid4

from test_entry import client, start


def test_pause_resume_preserves_conversation_and_stage(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}

    def send(action, version, key=None, **fields):
        headers = {**auth, "Idempotency-Key": str(key or uuid4())}
        return client.post(path + "/" + action, headers=headers, json={"expected_version": version, **fields})

    assert send("messages", 0, role_id="lin_yue", content="薪资多少？").status_code == 200
    history_path = path + "/messages?role_id=lin_yue"
    before = client.get(history_path, headers=auth).json()
    pause_key = uuid4()
    paused = send("pause", 1, pause_key)
    assert paused.status_code == 200
    snapshot = paused.json()["session"]
    assert (snapshot["status"], snapshot["stage"], snapshot["state_version"]) == ("paused", "S1", 2)
    assert client.get(path, headers=auth).json() == snapshot
    assert send("messages", 2, role_id="lin_yue", content="谁招聘？").status_code == 409
    assert send("decisions", 2, choice="decline").status_code == 409
    assert send("end", 2).status_code == 409
    assert send("resume", 1).status_code == 409
    assert client.get(history_path, headers=auth).json() == before

    resume_key = uuid4()
    resumed = send("resume", 2, resume_key)
    assert resumed.status_code == 200
    active = resumed.json()["session"]
    assert (active["status"], active["stage"], active["state_version"]) == ("active", "S1", 3)
    assert send("pause", 1, pause_key).json() == paused.json()
    assert send("resume", 2, resume_key).json() == resumed.json()
    assert client.get(path, headers=auth).json() == active
    assert client.get(history_path, headers=auth).json() == before
    assert send("messages", 3, role_id="lin_yue", content="请介绍一下学历要求。").status_code == 200
