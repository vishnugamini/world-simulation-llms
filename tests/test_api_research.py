import time

import httpx
import pytest
from fastapi.testclient import TestClient

from virtual_world import research
from virtual_world.api import create_app
from virtual_world.models import (
    ExperimentSpec,
    Interpretation,
    Proposal,
    ResearchSpec,
    WorldConfig,
)
from virtual_world.store import Store


def test_api_roundtrip(tmp_path):
    with TestClient(create_app(tmp_path / "api.sqlite3")) as client:
        r = client.post("/api/runs", json={"name": "Test", "config": {"population": 3}})
        assert r.status_code == 200
        id = r.json()["id"]
        assert (
            client.post(f"/api/runs/{id}/advance", json={"days": 3}).json()["day"] == 3
        )
        assert client.get(f"/api/runs/{id}/state?day=1").json()["day"] == 1
        assert (
            client.post(
                f"/api/runs/{id}/branch", json={"day": 2, "policy": "pool"}
            ).status_code
            == 200
        )
        assert (
            client.post("/api/runs", json={"config": {"reserve": 99}}).status_code
            == 422
        )
        assert client.get("/api/runs/missing").status_code == 404


def test_research_budget_rejection(tmp_path, monkeypatch):
    store = Store(tmp_path / "r.sqlite3")
    monkeypatch.setattr(
        research, "local_models", lambda: {"models": ["test"], "error": None}
    )
    job = research.new_research(
        store, ResearchSpec(model="test", question="Does sharing help?", max_runs=1)
    )
    monkeypatch.setattr(
        research,
        "ask",
        lambda *a: Proposal(hypothesis="x", rationale="x", experiment=ExperimentSpec()),
    )
    research.execute_research(store, job["id"])
    assert store.job(job["id"])["status"] == "failed"
    assert "budget" in store.job(job["id"])["data"]["error"]
    assert not store.jobs("experiment")


def test_research_confirmation_fresh_seeds(tmp_path, monkeypatch):
    store = Store(tmp_path / "r.sqlite3")
    monkeypatch.setattr(
        research, "local_models", lambda: {"models": ["test"], "error": None}
    )
    job = research.new_research(
        store,
        ResearchSpec(model="test", question="Does sharing help?", rounds=2, max_runs=4),
    )

    def ask(model, schema, messages, deadline, constraints=None):
        if schema is Interpretation:
            import json

            id = json.loads(messages[-1]["content"])["experiment_id"]
            return Interpretation(text="A test interpretation.", result_ids=[id])
        history = store.job(job["id"])["data"]["rounds"]
        if history:
            return Proposal(
                hypothesis="Confirm",
                rationale="Fresh seeds",
                confirm_experiment_id=history[0]["experiment_id"],
            )
        return Proposal(
            hypothesis="Sharing",
            rationale="Compare",
            experiment=ExperimentSpec(
                seeds=1,
                policies=["pool", "private"],
                conditions=["individual"],
                base=WorldConfig(duration=4),
            ),
        )

    monkeypatch.setattr(research, "ask", ask)
    research.execute_research(store, job["id"])
    j = store.job(job["id"])
    assert j["status"] == "complete"
    assert j["data"]["used_runs"] == 4
    a, b = [store.job(r["experiment_id"]) for r in j["data"]["rounds"]]
    assert a["spec"]["seed_start"] != b["spec"]["seed_start"]


def test_unavailable_and_timeout(tmp_path, monkeypatch):
    store = Store(tmp_path / "r.sqlite3")
    monkeypatch.setattr(
        research, "local_models", lambda: {"models": [], "error": "Unavailable"}
    )
    with pytest.raises(ValueError, match="Unavailable"):
        research.new_research(
            store, ResearchSpec(model="x", question="Does sharing help?")
        )
    with pytest.raises(TimeoutError):
        research.ask("x", Proposal, [], time.time() - 1)


def test_invalid_model_output_retry(monkeypatch):
    calls = []

    class Response:
        is_error = False

        def raise_for_status(self):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def iter_lines(self):
            yield '{"message":{"content":"not json"},"done":true}'

    class Client:
        def __init__(self, **kw):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            pass

        def stream(self, *a, **kw):
            calls.append(1)
            return Response()

    monkeypatch.setattr(research.httpx, "Client", Client)
    with pytest.raises(ValueError, match="one retry"):
        research.ask("x", Proposal, [], time.time() + 30)
    assert len(calls) == 2


def test_research_stop_before_start(tmp_path, monkeypatch):
    from virtual_world.service import cancel_job

    store = Store(tmp_path / "stop.sqlite3")
    job = store.create_job(
        "research",
        ResearchSpec(model="test", question="Can sharing help?").model_dump(),
    )
    cancel_job(store, job["id"])
    monkeypatch.setattr(
        research, "ask", lambda *a: pytest.fail("Stopped session called the model")
    )
    research.execute_research(store, job["id"])
    assert store.job(job["id"])["status"] == "cancelled"


def test_ollama_grammar_retains_structure_and_python_keeps_bounds():
    schema = research.grammar_schema(Proposal)
    assert "$defs" not in schema
    assert schema["additionalProperties"] is False
    assert "experiment" in schema["properties"]
    with pytest.raises(ValueError):
        Proposal.model_validate(
            {"hypothesis": "test", "rationale": "test", "experiment": {"seeds": 101}}
        )


def test_model_transport_timeout_is_recorded(tmp_path, monkeypatch):
    store = Store(tmp_path / "timeout.sqlite3")
    job = store.create_job(
        "research",
        ResearchSpec(model="test", question="Can sharing help?").model_dump(),
        {"rounds": []},
    )

    def timeout(*args):
        raise httpx.ReadTimeout("Local model did not respond in time")

    monkeypatch.setattr(research, "ask", timeout)
    research.execute_research(store, job["id"])
    assert store.job(job["id"])["status"] == "failed"
    assert "did not respond" in store.job(job["id"])["data"]["error"]


def test_research_wall_budget_stops_normally(tmp_path, monkeypatch):
    store = Store(tmp_path / "deadline.sqlite3")
    job = store.create_job(
        "research",
        ResearchSpec(model="test", question="Can sharing help?").model_dump(),
        {"rounds": []},
    )

    def expired(*args):
        raise TimeoutError("Research wall-time budget exhausted")

    monkeypatch.setattr(research, "ask", expired)
    research.execute_research(store, job["id"])
    result = store.job(job["id"])
    assert result["status"] == "complete"
    assert result["data"]["stop_reason"] == "Wall-time budget reached"
    assert result["data"]["used_runs"] == 0


def test_run_library_pagination(tmp_path):
    with TestClient(create_app(tmp_path / "pages.sqlite3")) as client:
        for n in range(3):
            client.post("/api/runs", json={"name": f"Colony {n}"})
        first = client.get("/api/runs?limit=2").json()
        second = client.get("/api/runs?limit=2&offset=2").json()
        assert len(first) == 2 and len(second) == 1
        assert {r["id"] for r in first}.isdisjoint({r["id"] for r in second})
