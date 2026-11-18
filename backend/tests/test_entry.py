from uuid import uuid4

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

from app import main
from app.store import sessions


@pytest.fixture
def client(tmp_path, monkeypatch):
    url = f"sqlite:///{tmp_path}/test.db"
    monkeypatch.setenv("DATABASE_URL", url)
    command.upgrade(Config("alembic.ini"), "head")
    engine = sa.create_engine(url)
    monkeypatch.setattr(main, "engine", engine)
    with TestClient(main.app) as client:
        yield client
    engine.dispose()


def start(client, key=None):
    return client.post(
        "/api/v1/sessions", headers={"Idempotency-Key": str(key or uuid4())},
        json={"scenario_id": "internship_v1", "privacy_notice_version": "local-demo-v1"},
    )


def test_creation_replay(client):
    key = uuid4()
    first = start(client, key)
    assert first.status_code == 201
    assert first.json()["session"]["stage"] == "S0"
    replay = start(client, key)
    assert replay.status_code == 409
    assert "session_token" not in replay.json()
    with main.engine.connect() as conn:
        row = conn.execute(sa.select(sessions)).mappings().one()
        assert row["state"]["events"] == [{"name": "SESSION_CREATED", "operation": str(key)}]


def test_private_openings_survive_reload(client):
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}
    restored = client.get(path, headers=auth)
    assert restored.json() == created["session"]
    assert [r["name"] for r in restored.json()["roles"]] == ["林悦", "陈浩", "王宇"]
    for role in restored.json()["roles"]:
        messages = client.get(path + "/messages", params={"role_id": role["id"]}, headers=auth).json()["items"]
        assert len(messages) == 1 and messages[0]["role_id"] == role["id"]
        assert set(role) == {"id", "name", "public_title"}
    assert client.get(path).status_code == 401
    other = {"Authorization": "Bearer " + start(client).json()["session_token"]}
    assert client.get(path + "/messages?role_id=lin_yue", headers=other).status_code == 404
