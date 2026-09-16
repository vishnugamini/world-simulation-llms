import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

from virtual_world import research
from virtual_world.activity import Trace, current_trace
from virtual_world.api import create_app
from virtual_world.models import Proposal
from virtual_world.store import Store


def test_stream_persists_before_completion_and_keeps_partial_failure(
    tmp_path, monkeypatch
):
    store = Store(tmp_path / "events.db")
    job = store.create_job("research", {})
    store.update_job(job["id"], "running")
    trace = Trace(store, job["id"])
    token = current_trace.set(trace)
    real_client = httpx.Client

    class Stream(httpx.SyncByteStream):
        def __iter__(self):
            yield (
                json.dumps(
                    {
                        "message": {
                            "content": '{"stop":',
                            "thinking": "Considering a test",
                        }
                    }
                )
                + chr(10)
            ).encode()
            time.sleep(0.17)
            yield b'{"message":{"content":"true,"}}' + bytes([10])
            saved = store.events(job["id"])
            assert any(e["kind"] == "model.delta" for e in saved)
            assert not any(e["kind"] == "model.completed" for e in saved)
            yield b'{"message":{"content":"partial"}}' + bytes([10])
            raise httpx.ReadTimeout("test disconnect")

    monkeypatch.setattr(
        research.httpx,
        "Client",
        lambda **kw: real_client(
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, stream=Stream())
            )
        ),
    )
    try:
        with pytest.raises(httpx.ReadTimeout):
            research.ask("test", Proposal, [], time.time() + 30)
    finally:
        current_trace.reset(token)
    events = store.events(job["id"])
    output = "".join(
        e["data"]["text"]
        for e in events
        if e["kind"] == "model.delta" and e["data"]["channel"] == "content"
    )
    assert output == '{"stop":true,partial'
    assert any(e["data"].get("channel") == "thinking" for e in events)
    assert events[0]["data"]["request"]["stream"] is True


def test_event_pagination_export_and_restart(tmp_path):
    app = create_app(tmp_path / "api.db")
    with TestClient(app) as client:
        store = app.state.store
        a = store.create_job("research", {})
        b = store.create_job("research", {})
        store.append_event(a["id"], "model.delta", "Output", {"text": "hello"})
        store.append_event(b["id"], "model.delta", "Other", {"text": "private"})
        store.append_event(a["id"], "model.delta", "Output", {"text": " world"})
        url = f"/api/research/{a['id']}"
        first = client.get(url + "/events?limit=1").json()
        assert first["has_more"]
        second = client.get(url + f"/events?after={first['next_cursor']}").json()
        assert len(second["events"]) == 1
        assert second["events"][0]["data"]["text"] == " world"
        assert not second["has_more"]
        export = client.get(url + "/activity/export").json()
        assert len(export["events"]) == 2
        store.update_job(a["id"], "running")
        store.interrupt()
        assert store.events(a["id"])[-1]["kind"] == "session.interrupted"
        assert client.get("/api/research/missing/events").status_code == 404
