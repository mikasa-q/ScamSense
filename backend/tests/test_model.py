import json
import threading
from concurrent.futures import ThreadPoolExecutor
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from uuid import uuid4

from test_entry import client, start
from app import dialogue


def test_provider_is_opt_in_scoped_and_constrained(client, monkeypatch):
    requests = []

    class Provider(BaseHTTPRequestHandler):
        def do_POST(self):
            assert self.path == "/v1/chat/completions"
            body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
            packet = json.loads(body["messages"][1]["content"])
            requests.append(packet)
            selected = packet["required_sentences"] or packet["allowed_sentences"][:1]
            if packet["question"] == "越界测试":
                selected = ["model-only unapproved claim"]
            content = json.dumps({"sentences": selected})
            data = json.dumps({"choices": [{"message": {"content": content}}]}).encode()
            self.send_response(200)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def log_message(self, *args):
            pass

    with ThreadingHTTPServer(("127.0.0.1", 0), Provider) as server:
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            monkeypatch.setenv("MODEL_BASE_URL", f"http://127.0.0.1:{server.server_port}/v1")
            monkeypatch.setenv("MODEL_NAME", "test-model")
            monkeypatch.setenv("MODEL_API_KEY", "test-only")
            assert client.get("/api/v1/training-options").json()["model_available"]
            def ask(created, role, text, version, key=None):
                path = "/api/v1/sessions/" + created["session"]["id"] + "/messages"
                headers = {"Authorization": "Bearer " + created["session_token"], "Idempotency-Key": str(key or uuid4())}
                response = client.post(path, headers=headers, json={"role_id":role,"content":text,"expected_version":version})
                assert response.status_code == 200
                return client.get(path, headers=headers, params={"role_id":role}).json()["items"][-1]

            local = start(client).json()
            assert ask(local, "lin_yue", "薪资多少？", 0)["reply_mode"] == "preset"
            assert not requests
            consenting = client.post("/api/v1/sessions", headers={"Idempotency-Key": str(uuid4())},
                                     json={"scenario_id":"internship_v1","privacy_notice_version":"model-demo-v1"}).json()
            ask(consenting, "lin_yue", "林悦专属测试原话", 0)
            key = uuid4()
            reply = ask(consenting, "wang_yu", "你亲自核实过吗？", 1, key)
            assert reply["reply_mode"] == "model" and "没有亲自核实" in reply["content"]
            assert ask(consenting, "wang_yu", "你亲自核实过吗？", 1, key) == reply
            assert len(requests) == 2
            assert "林悦专属" not in json.dumps(requests[-1], ensure_ascii=False)
            assert all(name not in requests[-1] for name in ("events", "score", "disclosures"))
            refused = ask(consenting, "wang_yu", "越界测试", 2)
            assert refused["reply_mode"] == "fallback" and "unapproved" not in refused["content"]
        finally:
            server.shutdown()
            thread.join()


def test_slow_reply_finishes_before_exit(client, monkeypatch):
    entered, release = threading.Event(), threading.Event()
    original = dialogue.compose
    def slow(*args):
        entered.set()
        assert release.wait(4)
        return original(*args)
    monkeypatch.setattr(dialogue, "compose", slow)
    created = start(client).json()
    path = "/api/v1/sessions/" + created["session"]["id"]
    auth = {"Authorization": "Bearer " + created["session_token"]}
    with ThreadPoolExecutor(1) as worker:
        turn = worker.submit(client.post, path + "/messages",
                             headers={**auth, "Idempotency-Key": str(uuid4())},
                             json={"expected_version": 0, "role_id": "lin_yue", "content": "岗位做什么？"})
        assert entered.wait(3)
        try:
            end = client.post(path + "/end", headers={**auth, "Idempotency-Key": str(uuid4())}, json={"expected_version": 0})
            assert end.status_code == 409
        finally:
            release.set()
        assert turn.result().status_code == 200
    assert client.post(path + "/end", headers={**auth, "Idempotency-Key": str(uuid4())},
                       json={"expected_version": 1}).status_code == 200
