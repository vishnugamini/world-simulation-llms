from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

Policy = Literal["private", "pool", "surplus"]
Condition = Literal["individual", "drought", "baseline"]


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)


class WorldConfig(StrictModel):
    version: Literal["1"] = "1"
    seed: int = Field(42, ge=0, le=2147483647)
    population: int = Field(40, ge=1, le=100)
    duration: int = Field(365, ge=1, le=730)
    policy: Policy = "surplus"
    reserve: float = Field(3, ge=0, le=10)
    ration: float = Field(1, gt=0, le=5)
    initial_food: float = Field(4, ge=0, le=20)
    daily_yield: float = Field(2.4, ge=0, le=10)
    patch_regrowth: float = Field(13, ge=0, le=100)
    spoilage: float = Field(0.035, ge=0, le=0.5)
    starvation_days: int = Field(7, ge=1, le=60)
    failure_chance: float = Field(0.2, ge=0, le=1)
    drought_start: int = Field(90, ge=8, le=700)
    drought_length: int = Field(20, ge=0, le=100)
    drought_severity: float = Field(0.7, ge=0, le=1)
    condition: Condition = "individual"


class CreateRun(StrictModel):
    name: str = Field("New colony", min_length=1, max_length=100)
    config: WorldConfig = Field(default_factory=WorldConfig)


class Advance(StrictModel):
    days: int = Field(1, ge=1, le=365)


class Branch(StrictModel):
    day: int = Field(ge=0)
    name: str = Field("Alternate history", min_length=1, max_length=100)
    policy: Policy | None = None
    reserve: float | None = Field(None, ge=0, le=10)
    food_grant: float = Field(0, ge=0, le=10000)


class ExperimentSpec(StrictModel):
    name: str = Field("Sharing & survival", min_length=1, max_length=100)
    base: WorldConfig = Field(default_factory=WorldConfig)
    policies: list[Policy] = Field(
        default_factory=lambda: ["private", "pool", "surplus"],
        min_length=1,
        max_length=3,
    )
    conditions: list[Condition] = Field(
        default_factory=lambda: ["individual", "drought"], min_length=1, max_length=3
    )
    reserves: list[float] = Field(
        default_factory=lambda: [3], min_length=1, max_length=11
    )
    seeds: int = Field(50, ge=1, le=100)
    seed_start: int = Field(1000, ge=0, le=2147483000)

    @model_validator(mode="after")
    def validate_grid(self):
        if len(set(self.policies)) != len(self.policies) or len(
            set(self.conditions)
        ) != len(self.conditions):
            raise ValueError("Policies and conditions must be unique")
        if len(set(self.reserves)) != len(self.reserves) or any(
            not 0 <= r <= 10 for r in self.reserves
        ):
            raise ValueError("Reserves must be unique values between 0 and 10")
        if self.total > 1000:
            raise ValueError("A batch is limited to 1000 runs")
        return self

    @property
    def total(self):
        return (
            self.seeds
            * len(self.conditions)
            * sum(len(self.reserves) if p == "surplus" else 1 for p in self.policies)
        )


class ResearchSpec(StrictModel):
    question: str = Field(min_length=5, max_length=2000)
    model: str = Field(min_length=1, max_length=200)
    rounds: int = Field(5, ge=1, le=5)
    max_runs: int = Field(500, ge=1, le=500)
    minutes: float = Field(30, gt=0, le=30)


class Proposal(StrictModel):
    hypothesis: str = Field(min_length=1, max_length=2000)
    rationale: str = Field(min_length=1, max_length=3000)
    stop: bool = False
    experiment: ExperimentSpec | None = None
    confirm_experiment_id: str | None = None

    @model_validator(mode="after")
    def actionable(self):
        if (
            not self.stop
            and self.experiment is None
            and self.confirm_experiment_id is None
        ):
            raise ValueError("Supply an experiment or a previous experiment to confirm")
        return self


class Interpretation(StrictModel):
    text: str = Field(max_length=6000)
    result_ids: list[str] = Field(min_length=1, max_length=20)


class AgentState(BaseModel):
    id: int
    name: str
    alive: bool
    ability: float
    food: float
    hunger: int
    patch: int | None
    gathered: float
    eaten: float
    received: float
    donated: float
    incapacitated: bool
    home: int


class Event(BaseModel):
    kind: str
    text: str
    agent: int | None = None
    patch: int | None = None
    amount: float | None = None


class Snapshot(BaseModel):
    recorded_policy: Policy | None = None
    recorded_reserve: float | None = None
    day: int
    agents: list[AgentState]
    pool: float
    patch_food: list[float]
    weather: str
    rain: float
    events: list[Event]
    ledger: dict[str, float]
    totals: dict[str, float]
    ration_history: list[float]
    shock_recovery: int | None
    intervention_ledger: dict[str, float] | None = None


class Patch(BaseModel):
    id: int
    x: int
    y: int
    path: list[list[int]]
    distance: int
    capacity: float


class WorldMap(BaseModel):
    size: int
    land: list[list[int]]
    settlement: list[int]
    homes: list[dict[str, int]]
    patches: list[Patch]


class RunView(BaseModel):
    engine_version: str
    id: str
    name: str
    created: float
    config: WorldConfig
    world: WorldMap
    day: int
    status: str
    parent: str | None
    branch_day: int | None
    experiment: str | None
    metrics: dict | None


class JobView(BaseModel):
    id: str
    kind: str
    created: float
    status: str
    spec: dict
    data: dict


class ResearchEvent(BaseModel):
    seq: int
    job: str
    created: float
    kind: str
    message: str
    data: dict


class ResearchEvents(BaseModel):
    events: list[ResearchEvent]
    next_cursor: int
    has_more: bool
