"""Pure deterministic daily simulation. No wall clock, network, or model calls."""

import math
from collections import deque
from copy import deepcopy

from .models import WorldConfig

ENGINE_VERSION = "1.0.0"
MASK = (1 << 64) - 1
NAMES = [
    "Ada",
    "Milo",
    "Luna",
    "Theo",
    "Iris",
    "Finn",
    "Nora",
    "Arlo",
    "Esme",
    "Kai",
    "Cleo",
    "Jude",
    "Alma",
    "Otis",
    "Vera",
    "Remy",
    "Maya",
    "Leo",
    "Wren",
    "Hugo",
    "Thea",
    "Ezra",
    "Isla",
    "Noel",
    "Sage",
    "Oren",
    "Lyra",
    "Eli",
    "June",
    "Asa",
    "Rhea",
    "Ivo",
    "Zoe",
    "Sol",
    "Nell",
    "Kit",
    "Faye",
    "Ravi",
    "Eden",
    "Bo",
]


def random_at(seed: int, day: int, entity: int, kind: int) -> float:
    x = (
        seed
        + day * 0x9E3779B97F4A7C15
        + entity * 0xBF58476D1CE4E5B9
        + kind * 0x94D049BB133111EB
    ) & MASK
    x = ((x ^ (x >> 30)) * 0xBF58476D1CE4E5B9) & MASK
    x = ((x ^ (x >> 27)) * 0x94D049BB133111EB) & MASK
    return ((x ^ (x >> 31)) & MASK) / (1 << 64)


def make_world(c: WorldConfig) -> dict:
    land = set()
    for y in range(48):
        for x in range(48):
            a = math.atan2(y - 24, x - 24)
            radius = (
                17 + 2 * math.sin(a * 3 + c.seed) + 1.3 * math.cos(a * 5 + c.seed * 0.3)
            )
            if math.hypot(x - 24, y - 24) < radius:
                land.add((x, y))
    # BFS guarantees all usable tiles belong to the central connected component.
    root = (24, 24)
    parents = {root: None}
    queue = deque([root])
    while queue:
        x, y = queue.popleft()
        for p in [(x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)]:
            if p in land and p not in parents:
                parents[p] = (x, y)
                queue.append(p)
    patches = []
    for i in range(6):
        a = i * math.pi / 3 + 0.2
        r = 9 + random_at(c.seed, 0, i, 11) * 4
        target = (round(24 + math.cos(a) * r), round(24 + math.sin(a) * r))
        target = min(
            parents, key=lambda p: (p[0] - target[0]) ** 2 + (p[1] - target[1]) ** 2
        )
        path = []
        p = target
        while p is not None:
            path.append(list(p))
            p = parents[p]
        path.reverse()
        patches.append(
            {
                "id": i,
                "x": target[0],
                "y": target[1],
                "path": path,
                "distance": len(path) - 1,
                "capacity": 70.0,
            }
        )
    homes = [
        {
            "x": 24 + round(math.cos(i * 2 * math.pi / 10) * 4),
            "y": 24 + round(math.sin(i * 2 * math.pi / 10) * 4),
        }
        for i in range(10)
    ]
    return {
        "size": 48,
        "land": [list(p) for p in sorted(parents)],
        "settlement": [24, 24],
        "homes": homes,
        "patches": patches,
    }


def initial(c: WorldConfig):
    world = make_world(c)
    agents = []
    for i in range(c.population):
        agents.append(
            {
                "id": i,
                "name": NAMES[i % len(NAMES)] + (f" {i // 40 + 1}" if i >= 40 else ""),
                "alive": True,
                "ability": 0.65 + 0.7 * random_at(c.seed, 0, i, 1),
                "food": 0.0 if c.policy == "pool" else c.initial_food,
                "hunger": 0,
                "patch": None,
                "gathered": 0.0,
                "eaten": 0.0,
                "received": 0.0,
                "donated": 0.0,
                "incapacitated": False,
                "home": i % 10,
            }
        )
    state = {
        "day": 0,
        "agents": agents,
        "pool": c.initial_food * c.population if c.policy == "pool" else 0.0,
        "patch_food": [45.0] * 6,
        "weather": "Clear",
        "rain": 1.0,
        "events": [],
        "ledger": {},
        "totals": {
            "gathered": 0.0,
            "consumed": 0.0,
            "spoiled": 0.0,
            "lost": 0.0,
            "hungry_days": 0,
            "grants": 0.0,
        },
        "ration_history": [],
        "shock_recovery": None,
    }
    return world, state


def stored(s):
    return s["pool"] + sum(a["food"] for a in s["agents"])


def distribute(s, c):
    """Transfers only: consumption happens afterward. Return transfer event records."""
    alive = [a for a in s["agents"] if a["alive"]]
    events = []
    if not alive:
        return events
    if c.policy == "pool":
        per = min(c.ration, s["pool"] / len(alive))
        for a in alive:
            a["food"] += per
            a["received"] += per
        s["pool"] -= per * len(alive)
        events.append(
            {
                "kind": "sharing",
                "text": f"Common store allocated {per:.2f} food per survivor.",
                "amount": per * len(alive),
            }
        )
    elif c.policy == "surplus":
        # Reserve includes today's ration: a zero reserve may give away today's meal.
        donors = [(a, max(0.0, a["food"] - c.reserve * c.ration)) for a in alive]
        needs = [(a, max(0.0, c.ration - a["food"])) for a in alive]
        total_need = sum(n for _, n in needs)
        surplus = sum(n for _, n in donors)
        moved = min(total_need, surplus)
        if moved > 0:
            for a, extra in donors:
                amount = moved * extra / surplus
                if amount:
                    a["food"] -= amount
                    a["donated"] += amount
                    events.append(
                        {
                            "kind": "sharing",
                            "agent": a["id"],
                            "amount": amount,
                            "text": f"{a['name']} donated {amount:.2f} food.",
                        }
                    )
            for a, need in needs:
                amount = moved * need / total_need
                if amount:
                    a["food"] += amount
                    a["received"] += amount
                    events.append(
                        {
                            "kind": "sharing",
                            "agent": a["id"],
                            "amount": amount,
                            "text": f"{a['name']} received {amount:.2f} food.",
                        }
                    )
    return events


def step(c: WorldConfig, world: dict, state: dict) -> dict:
    s = deepcopy(state)
    day = s["day"] + 1
    s["day"] = day
    events = []
    opening = stored(s)
    drought = (
        c.condition == "drought"
        and c.drought_start <= day < c.drought_start + c.drought_length
    )
    rain = 0.8 + 0.4 * random_at(c.seed, day, 0, 2)
    factor = (1 - c.drought_severity) if drought else 1.0
    s["weather"] = "Drought" if drought else ("Rain" if rain > 1.1 else "Clear")
    s["rain"] = rain
    if drought and day == c.drought_start:
        events.append({"kind": "weather", "text": "A colony-wide drought began."})
    if (
        c.condition == "drought"
        and c.drought_length
        and day == c.drought_start + c.drought_length
    ):
        events.append(
            {
                "kind": "weather",
                "text": "The drought ended. Recovery monitoring continues.",
            }
        )
    for p in world["patches"]:
        i = p["id"]
        s["patch_food"][i] = min(
            p["capacity"], s["patch_food"][i] + c.patch_regrowth * rain * factor
        )
    demands = [[] for _ in world["patches"]]
    alive = [a for a in s["agents"] if a["alive"]]
    for a in s["agents"]:
        a.update(
            patch=None,
            gathered=0.0,
            eaten=0.0,
            received=0.0,
            donated=0.0,
            incapacitated=False,
        )
        if not a["alive"]:
            continue
        fail = c.failure_chance if c.condition == "individual" else 0.03
        a["incapacitated"] = random_at(c.seed, day, a["id"], 3) < fail
        if a["incapacitated"]:
            events.append(
                {
                    "kind": "misfortune",
                    "agent": a["id"],
                    "text": f"{a['name']} was unable to gather today.",
                }
            )
            continue
        # Stable heterogeneous preferences spread demand; identical strategy for every policy.
        p = max(
            world["patches"],
            key=lambda p: (
                (s["patch_food"][p["id"]] / (1 + len(demands[p["id"]])))
                * (0.65 + 0.7 * random_at(c.seed, day, a["id"] * 6 + p["id"], 4))
                / (1 + p["distance"] * 0.035)
            ),
        )
        a["patch"] = p["id"]
        request = (
            c.daily_yield * a["ability"] * max(0.1, 1 - p["distance"] * 0.018) * factor
        )
        demands[p["id"]].append((a, request))
    gathered = 0.0
    for i, entries in enumerate(demands):
        requested = sum(v for _, v in entries)
        ratio = min(1.0, s["patch_food"][i] / requested) if requested else 0.0
        for a, request in entries:
            amount = request * ratio
            a["gathered"] = amount
            gathered += amount
            if c.policy == "pool":
                s["pool"] += amount
                a["donated"] += amount
            else:
                a["food"] += amount
            events.append(
                {
                    "kind": "gathering",
                    "agent": a["id"],
                    "patch": i,
                    "amount": amount,
                    "text": f"{a['name']} gathered {amount:.2f} food at patch {i + 1}.",
                }
            )
        s["patch_food"][i] = max(0.0, s["patch_food"][i] - requested * ratio)
    events.extend(distribute(s, c))
    consumed = 0.0
    hungry = 0
    lost = 0.0
    for a in alive:
        eaten = min(c.ration, max(0.0, a["food"]))
        a["food"] -= eaten
        a["eaten"] = eaten
        consumed += eaten
        if eaten < c.ration - 1e-9:
            a["hunger"] += 1
            hungry += 1
        else:
            a["hunger"] = 0
    spoiled = stored(s) * c.spoilage
    s["pool"] *= 1 - c.spoilage
    for a in s["agents"]:
        a["food"] *= 1 - c.spoilage
    for a in alive:
        if a["hunger"] >= c.starvation_days:
            a["alive"] = False
            lost += a["food"]
            a["food"] = 0.0
            events.append(
                {
                    "kind": "death",
                    "agent": a["id"],
                    "text": f"{a['name']} died after {a['hunger']} consecutive days of insufficient food.",
                }
            )
    fulfillment = consumed / (len(alive) * c.ration) if alive else 0.0
    s["ration_history"].append(fulfillment)
    for k, v in [
        ("gathered", gathered),
        ("consumed", consumed),
        ("spoiled", spoiled),
        ("lost", lost),
        ("hungry_days", hungry),
    ]:
        s["totals"][k] += v
    s["ledger"] = {
        "opening": opening,
        "gathered": gathered,
        "consumed": consumed,
        "spoiled": spoiled,
        "lost": lost,
        "closing": stored(s),
        "grants": 0.0,
    }
    residual = opening + gathered - consumed - spoiled - lost - stored(s)
    if abs(residual) > 1e-7:
        raise ArithmeticError(f"Food ledger imbalance: {residual}")
    s["events"] = events
    if (
        c.condition == "drought"
        and c.drought_length > 0
        and day >= c.drought_start + c.drought_length + 6
        and s["shock_recovery"] is None
    ):
        before = s["ration_history"][c.drought_start - 8 : c.drought_start - 1]
        if (
            len(before) == 7
            and sum(before) > 0
            and all(v >= 0.9 * sum(before) / 7 for v in s["ration_history"][-7:])
        ):
            s["shock_recovery"] = day - 6 - (c.drought_start + c.drought_length)
    return s


def intervene(s, old: WorldConfig, new: WorldConfig, grant=0.0):
    s = deepcopy(s)
    alive = [a for a in s["agents"] if a["alive"]]
    opening = stored(s)
    if grant and not alive:
        raise ValueError("Cannot grant food to an extinct colony")
    events = []
    if old.policy != new.policy:
        if new.policy == "pool":
            s["pool"] += sum(a["food"] for a in alive)
            for a in alive:
                a["food"] = 0.0
        elif old.policy == "pool" and alive:
            per = s["pool"] / len(alive)
            for a in alive:
                a["food"] += per
            s["pool"] = 0.0
        events.append(
            {
                "kind": "intervention",
                "text": f"Policy changed from {old.policy} to {new.policy}; existing food conserved.",
            }
        )
    if old.reserve != new.reserve:
        events.append(
            {
                "kind": "intervention",
                "text": f"Reserve changed to {new.reserve:g} days.",
            }
        )
    if grant:
        if new.policy == "pool":
            s["pool"] += grant
        else:
            for a in alive:
                a["food"] += grant / len(alive)
        s["totals"]["grants"] += grant
        events.append(
            {
                "kind": "intervention",
                "amount": grant,
                "text": f"External food grant: {grant:g} units.",
            }
        )
    s["events"] = s["events"] + events
    if events:
        s["intervention_ledger"] = {
            "opening": opening,
            "grants": grant,
            "closing": stored(s),
        }
    return s


def metrics(c, s):
    alive = sum(a["alive"] for a in s["agents"])
    recovery_applicable = (
        c.condition == "drought"
        and c.drought_length > 0
        and s["day"] >= c.drought_start
    )
    return {
        "survival": alive / c.population,
        "survivors": alive,
        "hungry_days": s["totals"]["hungry_days"],
        "spoiled": s["totals"]["spoiled"],
        "recovery_days": s["shock_recovery"],
        "recovery_status": (
            "recovered" if s["shock_recovery"] is not None else "not recovered"
        )
        if recovery_applicable
        else "not applicable",
        "stored": stored(s),
        "day": s["day"],
    }
