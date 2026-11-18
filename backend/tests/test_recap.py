from uuid import uuid4

import pytest
import sqlalchemy as sa

from app import main, recap
from app.store import sessions
from test_entry import client, start


@pytest.mark.parametrize("early", [True, False])
def test_exit_and_evidence_are_independent(client, early):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}
    key = lambda: {**auth, "Idempotency-Key": str(uuid4())}
    text = "你亲自核实过吗？"
    chat = {"expected_version": 0, "role_id": "wang_yu", "content": text}
    assert client.post(path + "/messages", headers=key(), json=chat).status_code == 200
    assert client.get(path + "/report", headers=auth).status_code == 409
    terminal = path + ("/end" if early else "/decisions")
    body = {"expected_version": 1}
    if not early:
        body.update(choice="decline", reason="对方没有给出我需要的依据。")
    headers = key()
    response = client.post(terminal, headers=headers, json=body)
    assert response.status_code == 200
    report = response.json()
    assert report["choice"] == ("undecided" if early else "decline")
    assert report["ended_early"] is early
    assert report["total_score"] is None
    risk, verify, decision, analysis = report["dimensions"]
    assert not risk["evidence"] and not analysis["evidence"]
    assert verify["evidence"][0]["content"] == text
    assert bool(decision["evidence"]) == (not early)
    assert report["disclosures"][0]["message_id"] != verify["evidence"][0]["id"]
    assert client.post(terminal, headers=headers, json=body).json() == report
    assert client.get(path + "/report", headers=auth).json() == report
    session = client.get(path, headers=auth).json()
    assert session["stage"] == "S6"
    assert client.post(path + "/messages", headers=key(), json={**chat, "expected_version": session["state_version"]}).status_code == 409
    with main.engine.connect() as conn:
        state = conn.execute(sa.select(sessions.c.state)).scalar_one()
    events = [e["name"] for e in state["events"]]
    assert events.count("USER_MAKES_DECISION") == (0 if early else 1)
    assert events.count("SESSION_COMPLETED") == 1


def test_report_can_retry_fixed_exit(client, monkeypatch):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    headers = {"Authorization": "Bearer " + created["session_token"], "Idempotency-Key": str(uuid4())}
    def fail(state):
        raise ValueError("test")
    with monkeypatch.context() as patch:
        patch.setattr(recap, "build_report", fail)
        assert client.post(path + "/end", headers=headers, json={"expected_version": 0}).status_code == 503
    assert client.get(path, headers=headers).json()["stage"] == "S5"
    retry = client.post(path + "/report/retry", headers=headers)
    assert retry.status_code == 200 and retry.json()["ended_early"]
    assert client.get(path, headers=headers).json()["stage"] == "S6"
