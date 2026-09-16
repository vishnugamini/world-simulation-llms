from copy import deepcopy

import pytest

from virtual_world.engine import distribute, initial, intervene, metrics, step, stored
from virtual_world.models import Branch, CreateRun, ExperimentSpec, WorldConfig
from virtual_world.service import advance, branch, create_run
from virtual_world.store import Store


@pytest.mark.parametrize("policy", ["private", "pool", "surplus"])
def test_determinism_and_conservation(policy):
    c = WorldConfig(
        policy=policy, condition="drought", drought_start=12, drought_length=25
    )
    w, s = initial(c)
    _, t = initial(c)
    for _ in range(65):
        s = step(c, w, s)
        t = step(c, w, t)
        assert s == t
        l = s["ledger"]
        assert l["opening"] + l["gathered"] == pytest.approx(
            l["closing"] + l["consumed"] + l["spoiled"] + l["lost"]
        )
        assert s["pool"] >= -1e-9
        assert all(a["food"] >= -1e-9 for a in s["agents"])
    assert s["day"] == 65


def test_matched_environment_and_connected_land():
    c = WorldConfig()
    w, s = initial(c)
    p = c.model_copy(update={"policy": "pool"})
    w2, t = initial(p)
    assert w == w2
    land = {tuple(x) for x in w["land"]}
    visited = {(24, 24)}
    frontier = list(visited)
    while frontier:
        x, y = frontier.pop()
        for n in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
            if n in land and n not in visited:
                visited.add(n)
                frontier.append(n)
    assert visited == land
    for _ in range(30):
        s = step(c, w, s)
        t = step(p, w, t)
        assert (s["rain"], s["weather"]) == (t["rain"], t["weather"])
        assert [a["incapacitated"] for a in s["agents"]] == [
            a["incapacitated"] for a in t["agents"]
        ]


def test_hand_calculable_sharing():
    c = WorldConfig(population=3, policy="surplus", reserve=2)
    _, s = initial(c)
    for a, v in zip(s["agents"], [5.0, 0.0, 0.5]):
        a["food"] = v
    distribute(s, c)
    assert [a["food"] for a in s["agents"]] == pytest.approx([3.5, 1.0, 1.0])
    assert stored(s) == 5.5
    c = WorldConfig(population=3, policy="pool")
    _, s = initial(c)
    s["pool"] = 1.5
    distribute(s, c)
    assert [a["food"] for a in s["agents"]] == pytest.approx([0.5, 0.5, 0.5])
    assert s["pool"] == pytest.approx(0)


def test_policy_conversion_and_grant():
    c = WorldConfig(population=3, policy="private")
    _, s = initial(c)
    before = deepcopy(s)
    pool = c.model_copy(update={"policy": "pool"})
    p = intervene(s, c, pool, 3)
    assert stored(p) == stored(s) + 3
    assert p["pool"] == 15
    p = intervene(p, pool, c)
    assert [a["food"] for a in p["agents"]] == [5.0, 5.0, 5.0]
    assert s == before


def test_saved_branch_continuation(tmp_path):
    db = Store(tmp_path / "test.sqlite3")
    r = create_run(db, CreateRun())
    advance(db, r["id"], 30)
    original = db.snapshot(r["id"], 30)
    b = branch(db, r["id"], Branch(day=12))
    advance(db, b["id"], 18)
    assert db.snapshot(b["id"]) == original
    assert db.snapshot(b["id"], 3) == db.snapshot(r["id"], 3)
    changed = branch(db, r["id"], Branch(day=12, policy="pool", food_grant=4))
    assert db.snapshot(changed["id"])["intervention_ledger"]["grants"] == 4
    assert db.snapshot(r["id"], 30) == original
    with pytest.raises(ValueError):
        branch(db, r["id"], Branch(day=31))


def test_recovery_and_extinction():
    c = WorldConfig(
        population=1,
        condition="drought",
        drought_start=8,
        drought_length=1,
        drought_severity=0,
    )
    w, s = initial(c)
    for _ in range(16):
        s = step(c, w, s)
    assert s["shock_recovery"] == 0
    c = WorldConfig(population=1, initial_food=0, daily_yield=0, starvation_days=2)
    w, s = initial(c)
    s = step(c, w, step(c, w, s))
    assert not s["agents"][0]["alive"]
    assert metrics(c, s)["survival"] == 0
    assert step(c, w, s)["day"] == 3


def test_validation():
    with pytest.raises(ValueError):
        WorldConfig(reserve=11)
    with pytest.raises(ValueError):
        ExperimentSpec(policies=["pool", "pool"])
    with pytest.raises(ValueError):
        ExperimentSpec(reserves=[float("nan")])


def test_branch_before_an_earlier_policy_change(tmp_path):
    db = Store(tmp_path / "nested.sqlite3")
    original = create_run(db, CreateRun(config=WorldConfig(policy="private")))
    advance(db, original["id"], 20)
    first = branch(db, original["id"], Branch(day=15, policy="pool"))
    earlier = branch(db, first["id"], Branch(day=10))
    assert earlier["config"]["policy"] == "private"
    assert db.effective_config(first["id"], 10)["policy"] == "private"
    advance(db, earlier["id"], 10)
    assert db.snapshot(earlier["id"]) == db.snapshot(original["id"])
