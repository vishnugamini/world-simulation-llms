from virtual_world import service
from virtual_world.models import ExperimentSpec, WorldConfig
from virtual_world.store import Store


def test_experiment_resume_and_pairs(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    spec = ExperimentSpec(
        seeds=2, conditions=["individual"], base=WorldConfig(duration=15)
    )
    job = service.new_experiment(store, spec)
    service.execute_experiment(store, job["id"])
    first = store.list_runs(100, job["id"])
    assert len(first) == 6
    assert store.job(job["id"])["status"] == "complete"
    result = service.summarize(store, job["id"])
    assert len(result["groups"]) == 3
    assert len(result["paired"]) == 9
    assert all(p["n"] == 2 for p in result["paired"])
    store.update_job(job["id"], "interrupted")
    service.execute_experiment(store, job["id"])
    assert {r["id"] for r in first} == {
        r["id"] for r in store.list_runs(100, job["id"])
    }
    assert "Paired differences" in service.report(store, job["id"])


def test_cancellation_worker_and_restart(tmp_path):
    store = Store(tmp_path / "test.sqlite3")
    c = WorldConfig(duration=30)
    job = service.new_experiment(store, ExperimentSpec(seeds=1, base=c))
    store.update_job(job["id"], "cancelling")
    assert (
        service.worker(store.path, job["id"], c.model_dump(), "cancelled-run", None)
        is None
    )
    assert store.run("cancelled-run")["day"] == 0
    store.update_job(job["id"], "running")
    store.interrupt()
    assert store.job(job["id"])["status"] == "interrupted"


def test_stop_before_start_and_deadline(tmp_path):
    import time

    store = Store(tmp_path / "stop.sqlite3")
    job = service.new_experiment(store, ExperimentSpec(seeds=1))
    service.cancel_job(store, job["id"])
    service.execute_experiment(store, job["id"])
    assert store.job(job["id"])["status"] == "cancelled"
    assert not store.list_runs(100, job["id"])
    expired = service.new_experiment(store, ExperimentSpec(seeds=1))
    service.execute_experiment(store, expired["id"], deadline=time.time() - 1)
    assert store.job(expired["id"])["status"] == "cancelled"
    assert not store.list_runs(100, expired["id"])


def test_running_cancellation_then_resume(tmp_path):
    import time

    store = Store(tmp_path / "cancel-live.sqlite3")
    job = service.new_experiment(
        store, ExperimentSpec(seeds=3, base=WorldConfig(duration=100))
    )
    thread = service.launch_experiment(store, job["id"])
    deadline = time.time() + 5
    while time.time() < deadline and not store.list_runs(10, job["id"]):
        time.sleep(0.01)
    service.cancel_job(store, job["id"])
    thread.join(timeout=5)
    assert not thread.is_alive()
    assert store.job(job["id"])["status"] == "cancelled"
    before = {r["id"] for r in store.list_runs(100, job["id"])}
    service.execute_experiment(store, job["id"])
    assert store.job(job["id"])["status"] == "complete"
    assert len(store.list_runs(100, job["id"])) == 18
    assert before <= {r["id"] for r in store.list_runs(100, job["id"])}
