import json
import threading
import time
import uuid
from concurrent.futures import FIRST_COMPLETED, ProcessPoolExecutor, wait
from contextlib import contextmanager
from itertools import product

import numpy as np

from .engine import ENGINE_VERSION, initial, intervene, metrics, step
from .models import Branch, CreateRun, ExperimentSpec, WorldConfig
from .store import Store, new_id

_LOCKS = {}
_LOCK_GUARD = threading.Lock()
_POOL = None
_POOL_LOCK = threading.Lock()
_ACTIVE = set()
_ACTIVE_LOCK = threading.Lock()


def get_pool():
    global _POOL
    with _POOL_LOCK:
        if _POOL is None:
            _POOL = ProcessPoolExecutor(max_workers=2)
    return _POOL


@contextmanager
def run_lock(id):
    with _LOCK_GUARD:
        lock = _LOCKS.setdefault(id, threading.Lock())
    with lock:
        yield


def create_run(store, request: CreateRun):
    world, state = initial(request.config)
    id = new_id()
    store.create_run(id, request.name, request.config.model_dump(), world, state)
    return store.run(id)


def advance(store, id, days):
    with run_lock(id):
        r = store.run(id)
        if r["engine_version"] != ENGINE_VERSION:
            raise ValueError("Engine version mismatch; this run is replay-only")
        c = WorldConfig(**r["config"])
        s = store.snapshot(id)
        states = []
        if r["experiment"]:
            raise ValueError("Experiment runs are immutable; branch to intervene")
        for _ in range(min(days, c.duration - s["day"])):
            s = step(c, r["world"], s)
            states.append(s)
        store.save_states(
            id, states, "complete" if s["day"] == c.duration else "ready", metrics(c, s)
        )
        return s


def branch(store, id, request: Branch):
    r = store.run(id)
    if r["engine_version"] != ENGINE_VERSION:
        raise ValueError("Engine version mismatch; this run is replay-only")
    if request.day > r["day"]:
        raise ValueError("Cannot branch beyond the saved history")
    old = WorldConfig(**store.effective_config(id, request.day))
    config = old.model_copy(
        update={
            k: v
            for k, v in {"policy": request.policy, "reserve": request.reserve}.items()
            if v is not None
        }
    )
    state = intervene(store.snapshot(id, request.day), old, config, request.food_grant)
    new = new_id()
    store.create_run(
        new, request.name, config.model_dump(), r["world"], state, id, request.day
    )
    return store.run(new)


def grid(spec: ExperimentSpec):
    for condition, policy in product(spec.conditions, spec.policies):
        for reserve in spec.reserves if policy == "surplus" else [spec.base.reserve]:
            for seed in range(spec.seed_start, spec.seed_start + spec.seeds):
                yield spec.base.model_copy(
                    update={
                        "condition": condition,
                        "policy": policy,
                        "reserve": reserve,
                        "seed": seed,
                    }
                )


def worker(path, job_id, config, id, deadline):
    store = Store(path)
    c = WorldConfig(**config)
    try:
        r = store.run(id)
        if r["engine_version"] != ENGINE_VERSION:
            raise ValueError("Engine version mismatch; cannot resume")
        if r["status"] == "complete":
            return id
        world = r["world"]
        state = store.snapshot(id)
    except KeyError:
        world, state = initial(c)
        store.create_run(
            id,
            f"{c.condition} · {c.policy} · seed {c.seed}",
            config,
            world,
            state,
            experiment=job_id,
        )
    chunk = []
    while state["day"] < c.duration:
        if state["day"] % 16 == 0:
            status = store.job(job_id)["status"]
            if status not in ("running", "queued") or (
                deadline and time.time() >= deadline
            ):
                store.save_states(id, chunk, "interrupted", metrics(c, state))
                return None
        state = step(c, world, state)
        chunk.append(state)
        if len(chunk) >= 32:
            store.save_states(id, chunk, "running", metrics(c, state))
            chunk = []
    store.save_states(id, chunk or [state], "complete", metrics(c, state))
    return id


def new_experiment(store, spec):
    return store.create_job(
        "experiment",
        spec.model_dump(),
        {
            "total": spec.total,
            "completed": 0,
            "engine_version": ENGINE_VERSION,
            "elapsed_seconds": 0,
        },
    )


def execute_experiment(store, id, deadline=None, parent=None, on_event=None):
    def notify(kind, message, **data):
        if on_event:
            on_event(kind, message, experiment_id=id, **data)

    with _ACTIVE_LOCK:
        if id in _ACTIVE:
            return
        _ACTIVE.add(id)
    try:
        job = store.job(id)
        if job["kind"] != "experiment":
            raise ValueError("Not an experiment batch")
        if job["status"] == "complete":
            return
        if job["status"] == "cancelling":
            store.update_job(id, "cancelled")
            return
        spec = ExperimentSpec(**job["spec"])
        started = time.perf_counter()
        previous = job["data"].get("elapsed_seconds", 0)
        store.update_job(id, "running", error=None)
        configs = []
        for c in grid(spec):
            rid = uuid.uuid5(
                uuid.NAMESPACE_URL, id + json.dumps(c.model_dump(), sort_keys=True)
            ).hex[:16]
            try:
                if store.run(rid)["status"] == "complete":
                    continue
            except KeyError:
                pass
            configs.append((rid, c.model_dump()))
        completed = spec.total - len(configs)
        store.update_job(id, completed=completed)
        notify(
            "experiment.started",
            "Running simulation batch",
            completed=completed,
            total=spec.total,
        )
        pending = {}
        iterator = iter(configs)
        pool = get_pool()
        exhausted = False
        while pending or not exhausted:
            stopping = (
                store.job(id)["status"] != "running"
                or bool(deadline and time.time() >= deadline)
                or bool(parent and store.job(parent)["status"] != "running")
            )
            if stopping and store.job(id)["status"] == "running":
                store.update_job(id, "cancelling")
            while not stopping and not exhausted and len(pending) < 2:
                try:
                    rid, config = next(iterator)
                except StopIteration:
                    exhausted = True
                    break
                f = pool.submit(worker, store.path, id, config, rid, deadline)
                pending[f] = rid
                notify(
                    "world.started",
                    "Simulating a colony",
                    run_id=rid,
                    configuration=config,
                )
            if stopping:
                exhausted = True
            if not pending:
                break
            done, _ = wait(pending, timeout=0.25, return_when=FIRST_COMPLETED)
            for f in done:
                rid = pending.pop(f)
                success = f.result()
                if success:
                    completed += 1
                notify(
                    "world.finished",
                    "Colony simulation complete"
                    if success
                    else "Colony simulation stopped",
                    run_id=rid,
                    completed=completed,
                    total=spec.total,
                )
                store.update_job(
                    id,
                    completed=completed,
                    elapsed_seconds=previous + time.perf_counter() - started,
                )
        status = "complete" if completed == spec.total else "cancelled"
        notify(
            "experiment.finished",
            "Simulation batch " + status,
            status=status,
            completed=completed,
            total=spec.total,
        )
        store.update_job(
            id,
            status,
            completed=completed,
            elapsed_seconds=previous + time.perf_counter() - started,
        )
    except Exception as e:  # noqa: BLE001 -- a worker failure must leave a recoverable job record
        store.update_job(id, "failed", error=str(e))
    finally:
        with _ACTIVE_LOCK:
            _ACTIVE.discard(id)


def launch_experiment(store, id, deadline=None):
    thread = threading.Thread(
        target=execute_experiment, args=(store, id, deadline), daemon=True
    )
    thread.start()
    return thread


def cancel_job(store, id):
    job = store.job(id)
    if job["status"] in ("queued", "running"):
        store.update_job(id, "cancelling")
        if job["kind"] == "research":
            store.append_event(
                id,
                "session.stop_requested",
                "Stop requested; preserving completed work",
            )
    return store.job(id)


def summarize(store, id):
    job = store.job(id)
    if job["kind"] != "experiment":
        raise ValueError("Not an experiment batch")
    runs = [r for r in store.list_runs(1000, id) if r["status"] == "complete"]
    groups = {}
    for r in runs:
        c = r["config"]
        label = f"{c['condition']} / {c['policy']}" + (
            f" / reserve {c['reserve']:g}" if c["policy"] == "surplus" else ""
        )
        groups.setdefault(label, []).append(r)
    summaries = []
    for label, rows in sorted(
        groups.items(),
        key=lambda item: (
            item[1][0]["config"]["condition"],
            item[1][0]["config"]["policy"],
            item[1][0]["config"]["reserve"],
        ),
    ):

        def mean(key, rows=rows):
            return float(np.mean([r["metrics"][key] for r in rows]))

        recoveries = [
            r["metrics"]["recovery_days"]
            for r in rows
            if r["metrics"]["recovery_days"] is not None
        ]
        summaries.append(
            {
                "label": label,
                "condition": rows[0]["config"]["condition"],
                "policy": rows[0]["config"]["policy"],
                "reserve": rows[0]["config"]["reserve"],
                "n": len(rows),
                "survival": mean("survival"),
                "hungry_days": mean("hungry_days"),
                "spoiled": mean("spoiled"),
                "recovered": len(recoveries),
                "recovery_applicable": sum(
                    r["metrics"]["recovery_status"] != "not applicable" for r in rows
                ),
                "recovery_days": float(np.mean(recoveries)) if recoveries else None,
                "replay": sorted(rows, key=lambda r: r["metrics"]["survival"])[
                    len(rows) // 2
                ]["id"],
            }
        )
    paired = []
    rng = np.random.default_rng(2026)
    for i, a in enumerate(summaries):
        for b in summaries[i + 1 :]:
            if a["condition"] != b["condition"]:
                continue
            ar = {r["config"]["seed"]: r for r in groups[a["label"]]}
            br = {r["config"]["seed"]: r for r in groups[b["label"]]}
            seeds = sorted(ar.keys() & br.keys())
            for metric in ["survival", "hungry_days", "spoiled"]:
                diffs = np.array(
                    [br[s]["metrics"][metric] - ar[s]["metrics"][metric] for s in seeds]
                )
                if not len(diffs):
                    continue
                boot = np.mean(
                    rng.choice(diffs, size=(1000, len(diffs)), replace=True), axis=1
                )
                lo, hi = np.quantile(boot, [0.025, 0.975])
                paired.append(
                    {
                        "a": a["label"],
                        "b": b["label"],
                        "metric": metric,
                        "n": len(seeds),
                        "difference": float(diffs.mean()),
                        "low": float(lo) if len(seeds) > 1 else None,
                        "high": float(hi) if len(seeds) > 1 else None,
                    }
                )
    return {
        "job": job,
        "groups": summaries,
        "paired": paired,
        "runs": runs,
        "caveat": "Results describe this version of the simulated world. Paired intervals are descriptive, not adjusted for multiple comparisons. Recovery averages include recovered colonies only.",
    }


def report(store, id):
    s = summarize(store, id)
    job = s["job"]
    lines = [
        f"# {job['spec']['name']}",
        "",
        f"Experiment `{id}` · engine {job['data'].get('engine_version', ENGINE_VERSION)}",
        f"Status: {job['status']}. Completed {len(s['runs'])}/{job['data']['total']} runs in {job['data'].get('elapsed_seconds', 0):.2f} seconds.",
        "",
        "| Condition / policy | Seeds | Mean survival | Hungry inhabitant-days | Spoilage | Recovered | Recovery days (recovered only) |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ]
    for g in s["groups"]:
        lines.append(
            f"| {g['label']} | {g['n']} | {g['survival']:.3f} | {g['hungry_days']:.1f} | {g['spoiled']:.1f} | {g['recovered']} | {g['recovery_days'] if g['recovery_days'] is not None else 'N/A'} |"
        )
    lines += [
        "",
        "## Paired differences (B minus A)",
        "",
        "| A | B | Metric | Paired seeds | Difference | 95% bootstrap interval |",
        "|---|---|---|---:|---:|---|",
    ]
    for p in s["paired"]:
        interval = (
            f"{p['low']:.4f} to {p['high']:.4f}"
            if p["low"] is not None
            else "Insufficient seeds"
        )
        lines.append(
            f"| {p['a']} | {p['b']} | {p['metric']} | {p['n']} | {p['difference']:.4f} | {interval} |"
        )
    lines += [
        "",
        "## Assumptions",
        "",
        s["caveat"],
        "Sharing is instantaneous at the settlement. Rules and gathering behavior are explicit; inhabitants do not use AI. No causal claim about real societies is established.",
        "",
        "## Configuration",
        "",
        "```json",
        json.dumps(job["spec"], indent=2),
        "```",
    ]
    return "\n".join(lines)
