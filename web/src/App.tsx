import SavedWorlds from "./SavedWorlds";
import { useEffect, useRef, useState } from "react";
import {
  ArrowUpRight,
  Beaker,
  BookOpen,
  ChevronRight,
  GitBranch,
  Leaf,
  Map,
  Pause,
  Play,
  Plus,
  Settings2,
  SkipForward,
  Sprout,
  Users,
  Wind,
  X,
  CloudRain,
  Sun,
  Download,
  RefreshCw,
} from "lucide-react";
import {
  api,
  fmt,
  policyNames,
  type Run,
  type Snapshot,
  type Policy,
  type Config,
} from "./api";
import Island from "./Island";
import Lab from "./Lab";
import Research from "./Research";

type RunRow = Omit<Run, "world">;
const DEFAULT = {
  policy: "surplus",
  reserve: 3,
  seed: 42,
  condition: "individual",
  population: 40,
  duration: 365,
} as Config;
function Spark({
  values,
  color = "#658d73",
}: {
  values: number[];
  color?: string;
}) {
  if (!values.length) return <div className="spark-empty" />;
  const max = Math.max(1, ...values);
  return (
    <svg
      className="spark"
      viewBox="0 0 240 50"
      preserveAspectRatio="none"
      aria-label="Ration fulfillment over time"
    >
      <path
        d={
          "M " +
          values
            .map(
              (v, i) =>
                `${(i / Math.max(1, values.length - 1)) * 240},${47 - (v / max) * 40}`,
            )
            .join(" L ")
        }
        stroke={color}
        fill="none"
        strokeWidth="2"
      />
    </svg>
  );
}
export default function App() {
  const [tab, setTab] = useState("world"),
    [run, setRun] = useState<Run | null>(null),
    [state, setState] = useState<Snapshot | null>(null),
    [runs, setRuns] = useState<RunRow[]>([]),
    [selected, setSelected] = useState<number | null>(0),
    [error, setError] = useState(""),
    [busy, setBusy] = useState(false),
    [playing, setPlaying] = useState(false),
    [speed, setSpeed] = useState(1),
    [filter, setFilter] = useState("all"),
    [modal, setModal] = useState<
      "new" | "branch" | "config" | "library" | null
    >(null),
    [form, setForm] = useState<Partial<Config>>(DEFAULT),
    [grant, setGrant] = useState(0),
    [name, setName] = useState("A new beginning"),
    [compare, setCompare] = useState<Run | null>(null),
    [compareState, setCompareState] = useState<Snapshot | null>(null),
    [compareId, setCompareId] = useState("");
  const gate = useRef(false),
    sequence = useRef(0);
  const refreshRuns = () => api<RunRow[]>("/runs").then(setRuns);
  async function openRun(id: string, navigate = true) {
    const seq = ++sequence.current;
    setPlaying(false);
    setCompare(null);
    setCompareState(null);
    setCompareId("");
    setBusy(true);
    try {
      const r = await api<Run>("/runs/" + id);
      const s = await api<Snapshot>("/runs/" + id + "/state");
      if (seq !== sequence.current) return;
      setRun(r);
      setState(s);
      setSelected(0);
      if (navigate) setTab("world");
      await refreshRuns();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    (async () => {
      try {
        const list = await api<RunRow[]>("/runs");
        setRuns(list);
        const interactive = list.find((r) => !r.experiment);
        if (interactive) await openRun(interactive.id, false);
        else {
          const r = await api<Run>("/runs", {
            name: "The first colony",
            config: { seed: 42 },
          });
          await api("/runs/" + r.id + "/advance", { days: 1 });
          await openRun(r.id, false);
        }
      } catch (e) {
        setError(String(e));
      }
    })();
  }, []);
  async function seek(day: number) {
    if (!run) return;
    setPlaying(false);
    const seq = ++sequence.current;
    try {
      const s = await api<Snapshot>(`/runs/${run.id}/state?day=${day}`);
      const cs = compare
        ? await api<Snapshot>(`/runs/${compare.id}/state?day=${day}`)
        : null;
      if (seq === sequence.current) {
        setState(s);
        setCompareState(cs);
      }
    } catch (e) {
      setError(String(e));
    }
  }
  async function next() {
    if (!run || !state || gate.current) return;
    gate.current = true;
    const seq = ++sequence.current;
    try {
      const max = compare
        ? Math.min(run.day, compare.day)
        : run.config.duration;
      if (state.day >= max) {
        setPlaying(false);
        return;
      }
      const day = state.day + 1;
      const s = await api<Snapshot>(
        day <= run.day
          ? `/runs/${run.id}/state?day=${day}`
          : `/runs/${run.id}/advance`,
        day <= run.day ? undefined : { days: 1 },
      );
      const cs = compare
        ? await api<Snapshot>(`/runs/${compare.id}/state?day=${day}`)
        : null;
      if (seq === sequence.current) {
        setState(s);
        setRun((previous) =>
          previous?.id === run.id
            ? { ...previous, day: Math.max(previous.day, s.day) }
            : previous,
        );
        setCompareState(cs);
      }
    } catch (e) {
      setError(String(e));
      setPlaying(false);
    } finally {
      gate.current = false;
    }
  }
  useEffect(() => {
    if (!playing || tab !== "world") return;
    const timer = setTimeout(next, Math.max(180, 2400 / speed));
    return () => clearTimeout(timer);
  }, [playing, state, tab, speed, run, compare]);
  async function simulate() {
    if (!run) return;
    setPlaying(false);
    setBusy(true);
    try {
      if (run.experiment)
        throw new Error(
          "Experiment histories are already saved. Branch to change a rule.",
        );
      const s = await api<Snapshot>(`/runs/${run.id}/advance`, {
        days: Math.min(30, run.config.duration - run.day),
      });
      setState(s);
      setRun({ ...run, day: s.day });
      await refreshRuns();
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function changeCompare(id: string) {
    const seq = ++sequence.current;
    setCompareId(id);
    setPlaying(false);
    if (!id) {
      setCompare(null);
      setCompareState(null);
      return;
    }
    try {
      const other = await api<Run>("/runs/" + id);
      const day = Math.min(state?.day || 0, run?.day || 0, other.day);
      const [a, b] = await Promise.all([
        api<Snapshot>(`/runs/${run!.id}/state?day=${day}`),
        api<Snapshot>(`/runs/${id}/state?day=${day}`),
      ]);
      if (seq !== sequence.current) return;
      setCompare(other);
      setState(a);
      setCompareState(b);
    } catch (e) {
      setError(String(e));
    }
  }
  async function submit() {
    setBusy(true);
    try {
      if (modal === "new") {
        const r = await api<Run>("/runs", { name, config: form });
        await openRun(r.id);
      } else if (modal === "branch" && run && state) {
        const r = await api<Run>(`/runs/${run.id}/branch`, {
          day: state.day,
          name,
          policy: form.policy,
          reserve: form.reserve,
          food_grant: grant,
        });
        await openRun(r.id);
      }
      setModal(null);
    } catch (e) {
      setError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const recordedPolicy =
    state?.recorded_policy || run?.config.policy || "surplus";
  const recordedReserve = state?.recorded_reserve ?? run?.config.reserve ?? 3;
  const living = state?.agents.filter((a) => a.alive) || [];
  const inhabitant = state?.agents.find((a) => a.id === selected);
  const hungry = living.filter((a) => a.hunger > 0).length;
  const food =
    (state?.pool || 0) + (state?.agents.reduce((s, a) => s + a.food, 0) || 0);
  const events =
    state?.events.filter(
      (e) =>
        filter === "all" ||
        (filter === "selected" ? e.agent === selected : e.kind === filter),
    ) || [];
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <a
          className="brand"
          href="#"
          onClick={(e) => {
            e.preventDefault();
            setTab("world");
          }}
        >
          <span className="brand-symbol">
            <Sprout size={25} />
          </span>
          <span>
            world
            <br />
            <b>simulation.</b>
          </span>
        </a>
        <div className="nav-label">A LIVING EXPERIMENT</div>
        <nav>
          {[
            ["world", "The island", Map],
            ["lab", "Experiment lab", Beaker],
            ["research", "Research journal", BookOpen],
          ].map(([id, label, Icon]) => (
            <button
              key={String(id)}
              aria-label={String(label)}
              className={tab === id ? "nav-item active" : "nav-item"}
              onClick={() => {
                setTab(String(id));
                setPlaying(false);
              }}
            >
              <Icon size={18} />
              <span>{String(label)}</span>
              {tab === id && <span className="nav-dot" />}
            </button>
          ))}
        </nav>
        <div className="sidebar-rule" />
        <div className="section-label">
          YOUR COLONIES{" "}
          <button
            aria-label="Create colony"
            className="icon-button"
            onClick={() => {
              setName("A new beginning");
              setForm(DEFAULT);
              setModal("new");
            }}
          >
            <Plus size={15} />
          </button>
        </div>
        <div className="colony-list">
          {runs
            .filter((r) => !r.experiment)
            .slice(0, 8)
            .map((r) => (
              <button
                key={r.id}
                className={"colony-link " + (run?.id === r.id ? "chosen" : "")}
                onClick={() => openRun(r.id)}
              >
                <span className="colony-dot" />
                <span>
                  {r.name}
                  <small>
                    Day {r.day} · {policyNames[r.config.policy]}
                  </small>
                </span>
              </button>
            ))}
        </div>
        <div className="sidebar-bottom">
          <span className="status-dot" /> Local & reproducible
          <small>One island. Many possible futures.</small>
          <div className="build-tag">
            LLM RESEARCH <span>v1.0</span>
          </div>
        </div>
      </aside>
      <main>
        <header className="topbar">
          <div>
            <span className="breadcrumb">Workspace</span>
            <ChevronRight size={13} />
            <span>
              {tab === "world"
                ? "The island"
                : tab === "lab"
                  ? "Experiment lab"
                  : "Research journal"}
            </span>
          </div>
          <button
            className="button secondary compact-button"
            onClick={() => setModal("library")}
          >
            <BookOpen size={13} />
            Saved worlds
          </button>
          <span className="local-tag">
            <span className="status-dot" /> LOCAL SIMULATION
          </span>
        </header>
        {error && (
          <div className="error-banner" role="alert">
            {error}
            <button
              className="icon-button"
              aria-label="Dismiss error"
              onClick={() => setError("")}
            >
              <X size={16} />
            </button>
          </div>
        )}
        {tab === "lab" ? (
          <Lab onReplay={openRun} onError={setError} />
        ) : tab === "research" ? (
          <Research onError={setError} />
        ) : (
          <>
            <section className="page-heading">
              <div>
                <div className="eyebrow">WORLD SIMULATION / LLMS</div>
                <h1>
                  A small world.
                  <br className="mobile-break" /> A bigger question.
                </h1>
                <p>When does sharing help a colony survive? Let's find out.</p>
              </div>
              <button
                className="button secondary"
                onClick={() => {
                  setName("A new beginning");
                  setForm(DEFAULT);
                  setModal("new");
                }}
              >
                <Plus size={16} />
                New colony
              </button>
            </section>
            {!run || !state ? (
              <div className="empty loading">
                <Sprout size={40} />
                <h2>Preparing your island</h2>
                <p>Creating its first reproducible moment…</p>
              </div>
            ) : (
              <>
                <div className="stats-grid">
                  <div className="stat">
                    <span>
                      <Users size={15} /> POPULATION
                    </span>
                    <strong>
                      {living.length}
                      <small> / {run.config.population}</small>
                    </strong>
                    <p>
                      {living.length === run.config.population
                        ? "Everyone is still here"
                        : `${run.config.population - living.length} inhabitants lost`}
                    </p>
                  </div>
                  <div className="stat">
                    <span>
                      <Sprout size={15} /> FOOD IN STORE
                    </span>
                    <strong>
                      {fmt(food, 1)}
                      <small> units</small>
                    </strong>
                    <p>
                      {living.length
                        ? `${(food / (living.length * run.config.ration)).toFixed(1)} days of colony reserves`
                        : "Colony is extinct"}
                    </p>
                  </div>
                  <div className="stat">
                    <span>
                      <Wind size={15} /> GOING HUNGRY
                    </span>
                    <strong>
                      {hungry}
                      <small> inhabitants</small>
                    </strong>
                    <p>
                      <i
                        className={hungry ? "status-dot warning" : "status-dot"}
                      />
                      {hungry
                        ? "Some rations are incomplete"
                        : "All surviving inhabitants are fed"}
                    </p>
                  </div>
                  <div className="stat">
                    <span>
                      <GitBranch size={15} /> SHARING RULE
                    </span>
                    <strong className="text-stat">
                      {policyNames[recordedPolicy]}
                    </strong>
                    <p>
                      {recordedPolicy === "surplus"
                        ? `Keep ${recordedReserve} days, then help others`
                        : recordedPolicy === "pool"
                          ? "One store, equal daily rations"
                          : "Each inhabitant keeps their harvest"}
                    </p>
                  </div>
                </div>
                <div className={"world-layout " + (compare ? "comparing" : "")}>
                  <section className="world-panel">
                    <div className="panel-heading">
                      <div>
                        <span className="live-dot" />
                        <h2>{run.name}</h2>
                        <span className="pill">SEED {run.config.seed}</span>
                      </div>
                      <button
                        className="icon-button"
                        aria-label="World configuration"
                        onClick={() => setModal("config")}
                      >
                        <Settings2 size={17} />
                      </button>
                    </div>
                    <div className="map-wrap">
                      <div className="map-badges">
                        <span className="weather-badge">
                          {state.weather === "Rain" ? (
                            <CloudRain size={15} />
                          ) : state.weather === "Drought" ? (
                            <Wind size={15} />
                          ) : (
                            <Sun size={15} />
                          )}{" "}
                          {state.weather}
                        </span>
                        <span className="day-badge">
                          DAY <b>{String(state.day).padStart(3, "0")}</b>
                        </span>
                      </div>
                      <Island
                        run={run}
                        state={state}
                        selected={selected}
                        onSelect={setSelected}
                      />
                      <div className="map-note">
                        <span className="legend-dot" /> Inhabitants{" "}
                        <span className="legend-dot food" /> Food patches{" "}
                        <span className="north">↑ N</span>
                      </div>
                    </div>
                    <div className="transport">
                      <button
                        className="play-button"
                        aria-label={
                          playing ? "Pause simulation" : "Play simulation"
                        }
                        onClick={() => setPlaying(!playing)}
                        disabled={busy}
                      >
                        {playing ? (
                          <Pause size={16} fill="currentColor" />
                        ) : (
                          <Play size={16} fill="currentColor" />
                        )}
                      </button>
                      <button
                        className="icon-button"
                        aria-label="Step one day"
                        onClick={next}
                        disabled={busy}
                      >
                        <SkipForward size={18} />
                      </button>
                      <select
                        aria-label="Playback speed"
                        value={speed}
                        onChange={(e) => setSpeed(+e.target.value)}
                      >
                        {[1, 2, 5, 10].map((n) => (
                          <option key={n} value={n}>
                            {n}×
                          </option>
                        ))}
                      </select>
                      <div className="timeline">
                        <input
                          aria-label="Replay day"
                          type="range"
                          min="0"
                          max={
                            compare ? Math.min(run.day, compare.day) : run.day
                          }
                          value={state.day}
                          onChange={(e) => seek(+e.target.value)}
                        />
                        <div>
                          <span>Day 0</span>
                          <span>
                            Day{" "}
                            {compare ? Math.min(run.day, compare.day) : run.day}{" "}
                            saved
                          </span>
                        </div>
                      </div>
                      <button
                        className="button compact-button secondary"
                        disabled={
                          busy ||
                          !!compare ||
                          !!run.experiment ||
                          run.day >= run.config.duration
                        }
                        onClick={simulate}
                      >
                        {busy ? "Working…" : "+30 days"}
                      </button>
                    </div>
                  </section>
                  {compare && compareState ? (
                    <section className="world-panel">
                      <div className="panel-heading">
                        <div>
                          <h2>{compare.name}</h2>
                          <span className="pill">COMPARISON</span>
                        </div>
                        <button
                          className="icon-button"
                          onClick={() => changeCompare("")}
                          aria-label="Close comparison"
                        >
                          <X size={16} />
                        </button>
                      </div>
                      <Island
                        run={compare}
                        state={compareState}
                        selected={selected}
                        onSelect={setSelected}
                      />
                      <div className="compare-summary">
                        <strong>
                          {compareState.agents.filter((a) => a.alive).length}{" "}
                          survivors
                        </strong>
                        <span>
                          Day {compareState.day} ·{" "}
                          {policyNames[compare.config.policy]}
                        </span>
                        <small>
                          Both views use the same saved day. Playback stops at
                          their shared horizon.
                        </small>
                      </div>
                    </section>
                  ) : (
                    <aside className="inspector">
                      <div className="panel-heading">
                        <h2>A closer look</h2>
                        <span className="pill">INHABITANT</span>
                      </div>
                      {inhabitant && (
                        <>
                          <div className="person-card">
                            <div
                              className={
                                "avatar " +
                                (!inhabitant.alive ? "deceased" : "")
                              }
                            >
                              <span />
                              <i />
                            </div>
                            <h3>{inhabitant.name}</h3>
                            <span
                              className={
                                "person-status " +
                                (inhabitant.hunger ? "hungry" : "")
                              }
                            >
                              {!inhabitant.alive
                                ? "No longer living"
                                : inhabitant.incapacitated
                                  ? "Resting today"
                                  : inhabitant.hunger
                                    ? "Needs a little help"
                                    : "Doing well"}
                            </span>
                          </div>
                          <div className="person-numbers">
                            <div>
                              <span>Food stored</span>
                              <strong>
                                {fmt(inhabitant.food, 2)} <small>units</small>
                              </strong>
                            </div>
                            <div>
                              <span>Gathering ability</span>
                              <strong>
                                {inhabitant.ability.toFixed(2)}
                                <small>×</small>
                              </strong>
                            </div>
                            <div>
                              <span>Days underfed</span>
                              <strong>{inhabitant.hunger}</strong>
                            </div>
                          </div>
                          <div className="inspector-section">
                            <div className="section-label">
                              TODAY'S EXCHANGE
                            </div>
                            <div className="exchange">
                              <span>Gathered</span>
                              <b>+{fmt(inhabitant.gathered, 2)}</b>
                            </div>
                            <div className="exchange">
                              <span>Received</span>
                              <b>+{fmt(inhabitant.received, 2)}</b>
                            </div>
                            <div className="exchange">
                              <span>Donated</span>
                              <b>−{fmt(inhabitant.donated, 2)}</b>
                            </div>
                            <div className="exchange">
                              <span>Ate</span>
                              <b>
                                {fmt(inhabitant.eaten, 2)} / {run.config.ration}
                              </b>
                            </div>
                          </div>
                          <div className="inspector-section">
                            <label
                              className="section-label"
                              htmlFor="inhabitant"
                            >
                              EXPLORE THE COLONY
                            </label>
                            <select
                              id="inhabitant"
                              value={selected ?? 0}
                              onChange={(e) => setSelected(+e.target.value)}
                            >
                              {state.agents.map((a) => (
                                <option key={a.id} value={a.id}>
                                  {a.name}
                                  {!a.alive ? " · deceased" : ""}
                                </option>
                              ))}
                            </select>
                            <p className="microcopy">
                              Click a person on the island or choose a name.
                            </p>
                          </div>
                        </>
                      )}
                    </aside>
                  )}
                </div>
                <div className="below-map">
                  <div>
                    <GitBranch size={17} />
                    <span>Every choice opens another possible future.</span>
                  </div>
                  <div className="branch-actions">
                    <select
                      aria-label="Compare saved colony"
                      value={compareId}
                      onChange={(e) => changeCompare(e.target.value)}
                    >
                      <option value="">Compare saved histories…</option>
                      {runs
                        .filter((r) => r.id !== run.id)
                        .map((r) => (
                          <option key={r.id} value={r.id}>
                            {r.name} · day {r.day}
                          </option>
                        ))}
                    </select>
                    <button
                      className="button secondary"
                      onClick={() => {
                        setPlaying(false);
                        setName(run.name + " · branch");
                        setForm(run.config);
                        setGrant(0);
                        setModal("branch");
                      }}
                    >
                      <GitBranch size={15} />
                      Branch here
                    </button>
                  </div>
                </div>
                <div className="bottom-grid">
                  <section className="events-panel">
                    <div className="panel-heading">
                      <div>
                        <h2>Life on the island</h2>
                        <span className="muted">Day {state.day}</span>
                      </div>
                      <select
                        aria-label="Filter events"
                        value={filter}
                        onChange={(e) => setFilter(e.target.value)}
                      >
                        <option value="all">All events</option>
                        <option value="selected">Selected inhabitant</option>
                        {[
                          "sharing",
                          "gathering",
                          "misfortune",
                          "death",
                          "weather",
                          "intervention",
                        ].map((k) => (
                          <option key={k} value={k}>
                            {k}
                          </option>
                        ))}
                      </select>
                    </div>
                    <div className="event-list">
                      {events.length ? (
                        events.map((e, i) => (
                          <div className={"event " + e.kind} key={i}>
                            <span className="event-icon">
                              {e.kind === "sharing" ? (
                                <Users size={13} />
                              ) : e.kind === "gathering" ? (
                                <Leaf size={13} />
                              ) : (
                                <Wind size={13} />
                              )}
                            </span>
                            <span>{e.text}</span>
                            <small>{e.kind}</small>
                          </div>
                        ))
                      ) : (
                        <div className="empty-small">
                          No events in this view.
                        </div>
                      )}
                    </div>
                  </section>
                  <section className="insight-panel">
                    <div className="section-label">THE COLONY'S PULSE</div>
                    <h3>Enough for everyone?</h3>
                    <p>Daily ration fulfillment among living inhabitants.</p>
                    <Spark values={state.ration_history} />
                    <div className="pulse-footer">
                      <b>
                        {((state.ration_history.at(-1) || 0) * 100).toFixed(0)}%{" "}
                        <small>today</small>
                      </b>
                      <span>
                        {fmt(state.totals.hungry_days)} hungry days so far
                      </span>
                    </div>
                    <button
                      className="text-button"
                      onClick={() => {
                        setPlaying(false);
                        setTab("lab");
                      }}
                    >
                      Explore the experiment lab <ArrowUpRight size={15} />
                    </button>
                  </section>
                </div>
                <footer className="page-footer">
                  <span>
                    Deterministic rules. Recorded actions. Reproducible futures.
                  </span>
                  <span>
                    Sharing is instantaneous at the settlement. Findings apply
                    to this simulated world.
                  </span>
                </footer>
              </>
            )}
          </>
        )}
      </main>
      {modal && (
        <div className="modal-backdrop" onClick={() => setModal(null)}>
          <section
            className="modal"
            role="dialog"
            aria-modal="true"
            aria-label={
              modal === "new"
                ? "Create colony"
                : modal === "branch"
                  ? "Branch colony"
                  : modal === "library"
                    ? "Saved worlds"
                    : "World configuration"
            }
            onClick={(e) => e.stopPropagation()}
          >
            <div className="panel-heading">
              <h2>
                {modal === "new"
                  ? "A new beginning"
                  : modal === "branch"
                    ? `Another future, from day ${state?.day}`
                    : modal === "library"
                      ? "All your possible worlds"
                      : "The rules of this world"}
              </h2>
              <button
                className="icon-button"
                aria-label="Close dialog"
                onClick={() => setModal(null)}
              >
                <X size={18} />
              </button>
            </div>
            {modal === "library" ? (
              <SavedWorlds
                onOpen={(id) => {
                  setModal(null);
                  openRun(id);
                }}
              />
            ) : modal === "config" ? (
              <>
                <p className="microcopy">
                  Versioned configuration. Gathering rules are identical across
                  policies. Changing a rule creates a separate history.
                </p>
                <div className="config-list">
                  {Object.entries(run!.config).map(([k, v]) => (
                    <div key={k}>
                      <span>{k.replaceAll("_", " ")}</span>
                      <code>{String(v)}</code>
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                <label>
                  Colony name
                  <input
                    value={name}
                    onChange={(e) => setName(e.target.value)}
                    maxLength={100}
                  />
                </label>
                <div className="form-grid">
                  <label>
                    Sharing rule
                    <select
                      value={form.policy}
                      onChange={(e) =>
                        setForm({ ...form, policy: e.target.value as Policy })
                      }
                    >
                      {Object.entries(policyNames).map(([k, v]) => (
                        <option value={k} key={k}>
                          {v}
                        </option>
                      ))}
                    </select>
                  </label>
                  <label>
                    Reserve (days)
                    <input
                      type="number"
                      min="0"
                      max="10"
                      step=".5"
                      value={form.reserve}
                      onChange={(e) =>
                        setForm({ ...form, reserve: +e.target.value })
                      }
                    />
                  </label>
                  {modal === "new" ? (
                    <>
                      <label>
                        Seed
                        <input
                          type="number"
                          min="0"
                          value={form.seed}
                          onChange={(e) =>
                            setForm({ ...form, seed: +e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Environment
                        <select
                          value={form.condition}
                          onChange={(e) =>
                            setForm({
                              ...form,
                              condition: e.target.value as Config["condition"],
                            })
                          }
                        >
                          <option value="individual">
                            Individual misfortune
                          </option>
                          <option value="drought">Shared drought</option>
                          <option value="baseline">Baseline</option>
                        </select>
                      </label>
                      <label>
                        Inhabitants
                        <input
                          type="number"
                          min="1"
                          max="100"
                          value={form.population}
                          onChange={(e) =>
                            setForm({ ...form, population: +e.target.value })
                          }
                        />
                      </label>
                      <label>
                        Duration (days)
                        <input
                          type="number"
                          min="1"
                          max="730"
                          value={form.duration}
                          onChange={(e) =>
                            setForm({ ...form, duration: +e.target.value })
                          }
                        />
                      </label>
                    </>
                  ) : (
                    <label>
                      External food grant
                      <input
                        type="number"
                        min="0"
                        max="10000"
                        value={grant}
                        onChange={(e) => setGrant(+e.target.value)}
                      />
                    </label>
                  )}
                </div>
                <p className="microcopy">
                  {modal === "branch"
                    ? "The original history stays intact. The branch keeps the same future weather and misfortune inputs."
                    : "One unit feeds one inhabitant for one day. All parameters can be inspected after creation."}
                </p>
                <button
                  className="button primary full"
                  disabled={busy || !name.trim()}
                  onClick={submit}
                >
                  {busy
                    ? "Preparing…"
                    : modal === "new"
                      ? "Create island"
                      : "Create this future"}
                  <ArrowUpRight size={16} />
                </button>
              </>
            )}
          </section>
        </div>
      )}
    </div>
  );
}
