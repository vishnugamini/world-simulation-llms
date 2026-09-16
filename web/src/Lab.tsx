import { useEffect, useState } from "react";
import {
  ArrowDownToLine,
  ArrowUpRight,
  Beaker,
  Check,
  ChevronRight,
  GitCompareArrows,
  Play,
  RotateCcw,
  Square,
} from "lucide-react";
import {
  api,
  fmt,
  policyNames,
  type Job,
  type Policy,
  type Config,
} from "./api";

type Group = {
  label: string;
  condition: string;
  policy: Policy;
  reserve: number;
  n: number;
  survival: number;
  hungry_days: number;
  spoiled: number;
  recovered: number;
  recovery_applicable: number;
  recovery_days: number | null;
  replay: string;
};
type Paired = {
  a: string;
  b: string;
  metric: string;
  n: number;
  difference: number;
  low: number | null;
  high: number | null;
};
type Result = {
  job: Job;
  groups: Group[];
  paired: Paired[];
  caveat: string;
  runs: unknown[];
};
const COLORS: Record<Policy, string> = {
  private: "#c99379",
  pool: "#739c88",
  surplus: "#dfb65e",
};
export default function Lab({
  onReplay,
  onError,
}: {
  onReplay: (id: string) => void;
  onError: (s: string) => void;
}) {
  const [jobs, setJobs] = useState<Job[]>([]),
    [current, setCurrent] = useState(""),
    [result, setResult] = useState<Result | null>(null),
    [seeds, setSeeds] = useState(50),
    [days, setDays] = useState(365),
    [policies, setPolicies] = useState<Policy[]>([
      "private",
      "pool",
      "surplus",
    ]),
    [conditions, setConditions] = useState(["individual", "drought"]),
    [reserve, setReserve] = useState("3"),
    [failure, setFailure] = useState(0.2),
    [severity, setSeverity] = useState(0.7),
    [droughtStart, setDroughtStart] = useState(90),
    [droughtLength, setDroughtLength] = useState(20),
    [seedStart, setSeedStart] = useState(1000),
    [busy, setBusy] = useState(false),
    [metric, setMetric] = useState<"survival" | "hungry_days" | "spoiled">(
      "survival",
    );
  async function refresh() {
    const j = await api<Job[]>("/experiments");
    setJobs(j);
    if (!current && j.length) setCurrent(j[0].id);
    if (current) setResult(await api<Result>("/experiments/" + current));
  }
  useEffect(() => {
    refresh().catch((e) => onError(String(e)));
    const t = setInterval(
      () => refresh().catch((e) => onError(String(e))),
      2000,
    );
    return () => clearInterval(t);
  }, [current]);
  const reserves = reserve.split(",").map((s) => Number(s.trim()));
  const total =
    seeds *
    conditions.length *
    policies.reduce(
      (sum, p) => sum + (p === "surplus" ? reserves.length : 1),
      0,
    );
  async function submit() {
    setBusy(true);
    try {
      const job = await api<Job>("/experiments", {
        name: "Sharing & survival",
        policies,
        conditions,
        reserves,
        seeds,
        seed_start: seedStart,
        base: {
          duration: days,
          failure_chance: failure,
          drought_severity: severity,
          drought_start: droughtStart,
          drought_length: droughtLength,
        },
      });
      setResult(null);
      setCurrent(job.id);
      setJobs(await api<Job[]>("/experiments"));
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  async function control(action: string) {
    try {
      await api(`/experiments/${current}/${action}`, {});
      await refresh();
    } catch (e) {
      onError(String(e));
    }
  }
  const data = result?.job.data as
    | {
        total?: number;
        completed?: number;
        elapsed_seconds?: number;
        error?: string;
      }
    | undefined;
  const active =
    result && ["queued", "running", "cancelling"].includes(result.job.status);
  const max = Math.max(
    metric === "survival" ? 1 : 0,
    ...(result?.groups.map((g) => g[metric]) || [1]),
  );
  return (
    <>
      <section className="page-heading">
        <div>
          <div className="eyebrow">CONTROLLED CURIOSITY</div>
          <h1>One question. Many worlds.</h1>
          <p>Change the rules. Keep the weather. Compare what happens.</p>
        </div>
        <span className="outline-tag">
          <Beaker size={15} /> PAIRED EXPERIMENTS
        </span>
      </section>
      <div className="lab-layout">
        <section className="experiment-form panel">
          <div className="panel-heading">
            <h2>Design an experiment</h2>
            <span className="pill">01</span>
          </div>
          <div className="form-body">
            <div className="section-label">SHARING RULES</div>
            <div className="checks">
              {Object.entries(policyNames).map(([k, v]) => (
                <label key={k}>
                  <input
                    type="checkbox"
                    checked={policies.includes(k as Policy)}
                    onChange={() =>
                      setPolicies(
                        policies.includes(k as Policy)
                          ? policies.filter((p) => p !== k)
                          : [...policies, k as Policy],
                      )
                    }
                  />
                  <span
                    className="legend-dot"
                    style={{ background: COLORS[k as Policy] }}
                  />
                  {v}
                </label>
              ))}
            </div>
            <div className="section-label">ENVIRONMENT</div>
            <div className="checks">
              {[
                ["individual", "Individual misfortune"],
                ["drought", "Shared drought"],
                ["baseline", "Baseline"],
              ].map(([k, v]) => (
                <label key={k}>
                  <input
                    type="checkbox"
                    checked={conditions.includes(k)}
                    onChange={() =>
                      setConditions(
                        conditions.includes(k)
                          ? conditions.filter((c) => c !== k)
                          : [...conditions, k],
                      )
                    }
                  />
                  {v}
                </label>
              ))}
            </div>
            <div className="form-grid">
              <label>
                Matched seeds
                <input
                  type="number"
                  min="1"
                  max="100"
                  value={seeds}
                  onChange={(e) => setSeeds(+e.target.value)}
                />
              </label>
              <label>
                Days per world
                <input
                  type="number"
                  min="1"
                  max="730"
                  value={days}
                  onChange={(e) => setDays(+e.target.value)}
                />
              </label>
            </div>
            <label>
              Surplus reserves (days, comma-separated)
              <input
                value={reserve}
                onChange={(e) => setReserve(e.target.value)}
                placeholder="0, 1, 3, 5, 10"
              />
            </label>
            <details>
              <summary>Environmental parameters</summary>
              <div className="form-grid">
                <label>
                  Failure probability
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step=".05"
                    value={failure}
                    onChange={(e) => setFailure(+e.target.value)}
                  />
                </label>
                <label>
                  Drought severity
                  <input
                    type="number"
                    min="0"
                    max="1"
                    step=".05"
                    value={severity}
                    onChange={(e) => setSeverity(+e.target.value)}
                  />
                </label>
                <label>
                  Drought begins
                  <input
                    type="number"
                    min="8"
                    max="700"
                    value={droughtStart}
                    onChange={(e) => setDroughtStart(+e.target.value)}
                  />
                </label>
                <label>
                  Drought lasts
                  <input
                    type="number"
                    min="0"
                    max="100"
                    value={droughtLength}
                    onChange={(e) => setDroughtLength(+e.target.value)}
                  />
                </label>
                <label>
                  First seed
                  <input
                    type="number"
                    min="0"
                    value={seedStart}
                    onChange={(e) => setSeedStart(+e.target.value)}
                  />
                </label>
              </div>
            </details>
            <div className="batch-estimate">
              <b>{fmt(total)} worlds</b>
              <span>Up to two simulation processes</span>
            </div>
            <button
              className="button primary full"
              onClick={submit}
              disabled={
                busy ||
                !policies.length ||
                !conditions.length ||
                total > 1000 ||
                total < 1
              }
            >
              <Play size={15} />
              {busy ? "Starting…" : "Run experiment"}
            </button>
            <p className="microcopy">
              Each policy sees the same seeded conditions. Every world keeps its
              complete daily history.
            </p>
          </div>
        </section>
        <div className="lab-results">
          <section className="panel">
            <div className="panel-heading">
              <h2>Experiment notebook</h2>
              <select
                aria-label="Saved experiment"
                value={current}
                onChange={(e) => {
                  setCurrent(e.target.value);
                  setResult(null);
                }}
              >
                <option value="">Choose a batch…</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {String(j.spec.name)} · {j.id.slice(0, 6)} · {j.status}
                  </option>
                ))}
              </select>
            </div>
            {result ? (
              <>
                <div className="batch-status">
                  <div>
                    <span
                      className={
                        "pill " +
                        (result.job.status === "complete" ? "success" : "")
                      }
                    >
                      {result.job.status.toUpperCase()}
                    </span>
                    <h3>
                      {fmt(data?.completed)}{" "}
                      <span>/ {fmt(data?.total)} worlds explored</span>
                    </h3>
                    <p>
                      {fmt(data?.elapsed_seconds, 1)} seconds of measured batch
                      time
                    </p>
                  </div>
                  {active ? (
                    <button
                      className="button secondary"
                      onClick={() => control("cancel")}
                      disabled={result.job.status === "cancelling"}
                    >
                      <Square size={13} />
                      Stop batch
                    </button>
                  ) : ["cancelled", "interrupted", "failed"].includes(
                      result.job.status,
                    ) ? (
                    <button
                      className="button secondary"
                      onClick={() => control("resume")}
                    >
                      <RotateCcw size={14} />
                      Resume
                    </button>
                  ) : (
                    <Check size={25} className="green" />
                  )}
                </div>
                <div className="progress-track">
                  <span
                    style={{
                      width: `${(100 * (data?.completed || 0)) / (data?.total || 1)}%`,
                    }}
                  />
                </div>
                {data?.error && <p className="inline-error">{data.error}</p>}
                <div className="results-heading">
                  <div>
                    <div className="section-label">WHAT THE WORLDS TELL US</div>
                    <h3>
                      {metric === "survival"
                        ? "Survival across conditions"
                        : metric === "hungry_days"
                          ? "Days without enough food"
                          : "Food lost to spoilage"}
                    </h3>
                  </div>
                  <select
                    aria-label="Chart metric"
                    value={metric}
                    onChange={(e) => setMetric(e.target.value as typeof metric)}
                  >
                    <option value="survival">Survival fraction</option>
                    <option value="hungry_days">Hungry days</option>
                    <option value="spoiled">Spoilage</option>
                  </select>
                </div>
                <div className="bar-chart">
                  {result.groups.length ? (
                    result.groups.map((g) => (
                      <div className="bar-row" key={g.label}>
                        <div>
                          <span>
                            {policyNames[g.policy]}
                            {g.policy === "surplus" ? ` · ${g.reserve}d` : ""}
                          </span>
                          <small>
                            {g.condition} · {g.n} seeds
                          </small>
                        </div>
                        <div className="bar-track">
                          <div
                            style={{
                              width: `${(100 * g[metric]) / max}%`,
                              background: COLORS[g.policy],
                            }}
                          />
                        </div>
                        <b>
                          {metric === "survival"
                            ? `${(g.survival * 100).toFixed(1)}%`
                            : fmt(g[metric], 1)}
                        </b>
                        <button
                          className="icon-button"
                          title="Open representative replay"
                          aria-label={`Replay ${g.label}`}
                          onClick={() => onReplay(g.replay)}
                        >
                          <ArrowUpRight size={16} />
                        </button>
                      </div>
                    ))
                  ) : (
                    <div className="empty-small">
                      Completed worlds will appear here as the batch runs.
                    </div>
                  )}
                </div>
                <div className="export-row">
                  <span>Take the evidence with you</span>
                  {[
                    ["zip", "All results"],
                    ["csv", "CSV"],
                    ["json", "JSON"],
                    ["md", "Report"],
                  ].map(([format, label]) => (
                    <a
                      key={format}
                      className="button secondary compact-button"
                      href={`/api/experiments/${current}/export?format=${format}`}
                    >
                      <ArrowDownToLine size={13} />
                      {label}
                    </a>
                  ))}
                </div>
              </>
            ) : (
              <div className="empty">
                <GitCompareArrows size={40} />
                <h3>The interesting part is the comparison.</h3>
                <p>
                  Run your first batch to see how different sharing rules
                  respond to the same challenges.
                </p>
              </div>
            )}
          </section>
          {result && result.groups.length > 0 && (
            <>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Recovery after drought</h2>
                  <span className="pill">CONDITIONAL MEAN</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Rule / condition</th>
                        <th>Recovered</th>
                        <th>Days to recovery</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.groups.map((g) => (
                        <tr key={g.label}>
                          <td>{g.label}</td>
                          <td>
                            {g.recovery_applicable
                              ? `${g.recovered} / ${g.recovery_applicable}`
                              : "Not applicable"}
                          </td>
                          <td>
                            {g.recovery_days === null
                              ? g.recovery_applicable
                                ? "Not recovered"
                                : "—"
                              : fmt(g.recovery_days, 1)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="table-note">
                  Recovery begins with seven consecutive days at ≥90% of the
                  pre-shock average ration fulfillment. Means exclude colonies
                  that did not recover.
                </p>
              </section>
              <section className="panel">
                <div className="panel-heading">
                  <h2>Paired differences</h2>
                  <span className="pill">B − A</span>
                </div>
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th>Comparison</th>
                        <th>Metric</th>
                        <th>Seeds</th>
                        <th>Difference</th>
                        <th>95% interval</th>
                      </tr>
                    </thead>
                    <tbody>
                      {result.paired.map((p, i) => (
                        <tr key={i}>
                          <td>
                            <small>
                              A: {p.a}
                              <br />
                              B: {p.b}
                            </small>
                          </td>
                          <td>{p.metric.replaceAll("_", " ")}</td>
                          <td>{p.n}</td>
                          <td>{p.difference.toFixed(3)}</td>
                          <td>
                            {p.low === null
                              ? "More seeds needed"
                              : `${p.low.toFixed(3)} to ${p.high!.toFixed(3)}`}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
                <p className="table-note">{result.caveat}</p>
              </section>
            </>
          )}
        </div>
      </div>
      <footer className="page-footer">
        This is a model of a world, not a conclusion about real societies.
        Inspect assumptions and individual histories before interpreting
        aggregates.
      </footer>
    </>
  );
}
