import ResearchActivity from "./ResearchActivity";
import { useEffect, useState } from "react";
import {
  ArrowUpRight,
  BookOpen,
  CheckCircle2,
  FlaskConical,
  Play,
  RefreshCw,
  Square,
  Terminal,
} from "lucide-react";
import { api, fmt, type Job } from "./api";
type Models = { available: boolean; models: string[]; error: string | null };
type Round = {
  round: number;
  hypothesis: string;
  rationale: string;
  experiment_id: string;
  confirmation_of: string | null;
  interpretation: { text: string; result_ids: string[] } | null;
  groups: { label: string; n: number; survival: number; hungry_days: number }[];
};
export default function Research({
  onError,
}: {
  onError: (s: string) => void;
}) {
  const [models, setModels] = useState<Models | null>(null),
    [model, setModel] = useState(""),
    [question, setQuestion] = useState(
      "When does surplus sharing improve survival compared with private stores, and does the answer change during a drought?",
    ),
    [rounds, setRounds] = useState(5),
    [budget, setBudget] = useState(500),
    [minutes, setMinutes] = useState(30),
    [jobs, setJobs] = useState<Job[]>([]),
    [selected, setSelected] = useState(""),
    [busy, setBusy] = useState(false);
  async function refresh() {
    setJobs(await api<Job[]>("/research"));
  }
  async function loadModels() {
    setModels(await api<Models>("/models"));
  }
  useEffect(() => {
    loadModels().catch((e) => onError(String(e)));
    refresh().catch((e) => onError(String(e)));
    const t = setInterval(
      () => refresh().catch((e) => onError(String(e))),
      2000,
    );
    return () => clearInterval(t);
  }, []);
  async function start() {
    setBusy(true);
    try {
      const j = await api<Job>("/research", {
        question,
        model,
        rounds,
        max_runs: budget,
        minutes,
      });
      setSelected(j.id);
      await refresh();
    } catch (e) {
      onError(String(e));
    } finally {
      setBusy(false);
    }
  }
  const job = jobs.find((j) => j.id === selected) || jobs[0];
  const data = job?.data as
    | {
        rounds?: Round[];
        used_runs?: number;
        elapsed_seconds?: number;
        error?: string;
        stop_reason?: string;
      }
    | undefined;
  return (
    <>
      <section className="page-heading">
        <div>
          <div className="eyebrow">A NOTEBOOK THAT KEEPS ASKING</div>
          <h1>Let curiosity take a turn.</h1>
          <p>
            A local research partner. Bounded experiments. Evidence you can
            inspect.
          </p>
        </div>
        <span className="outline-tag">
          <BookOpen size={16} /> RESEARCH JOURNAL
        </span>
      </section>
      <div className="research-intro">
        <div>
          <span className="step-number">01</span>
          <b>Ask a question</b>
          <p>The model proposes a testable hypothesis.</p>
        </div>
        <Chevron />
        <div>
          <span className="step-number">02</span>
          <b>Run real experiments</b>
          <p>The same validated simulator does the work.</p>
        </div>
        <Chevron />
        <div>
          <span className="step-number">03</span>
          <b>Inspect & follow up</b>
          <p>Results guide the next bounded experiment.</p>
        </div>
      </div>
      <div className="lab-layout">
        <section className="panel experiment-form">
          <div className="panel-heading">
            <h2>Your research question</h2>
            <FlaskConical size={17} />
          </div>
          <div className="form-body">
            <label>
              What would you like to investigate?
              <textarea
                rows={5}
                value={question}
                onChange={(e) => setQuestion(e.target.value)}
              />
            </label>
            <div className="model-status">
              <span
                className={
                  "status-dot " + (!models?.available ? "warning" : "")
                }
              />
              <span>
                {models?.available
                  ? "Local Ollama connected"
                  : "Local model not connected"}
              </span>
              <button
                className="icon-button"
                aria-label="Refresh local models"
                onClick={() => loadModels().catch((e) => onError(String(e)))}
              >
                <RefreshCw size={14} />
              </button>
            </div>
            <label>
              Local model
              <select value={model} onChange={(e) => setModel(e.target.value)}>
                <option value="">Select an installed model…</option>
                {models?.models.map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
            </label>
            {models?.error && <p className="microcopy">{models.error}</p>}
            {models?.available && !models.models.length && (
              <p className="microcopy">
                No local models are installed. Install one through Ollama, then
                refresh this list. No model is downloaded automatically.
              </p>
            )}
            <div className="form-grid">
              <label>
                Maximum rounds
                <input
                  type="number"
                  min="1"
                  max="5"
                  value={rounds}
                  onChange={(e) => setRounds(+e.target.value)}
                />
              </label>
              <label>
                Maximum worlds
                <input
                  type="number"
                  min="1"
                  max="500"
                  value={budget}
                  onChange={(e) => setBudget(+e.target.value)}
                />
              </label>
              <label>
                Minutes of wall time
                <input
                  type="number"
                  min=".1"
                  max="30"
                  step=".1"
                  value={minutes}
                  onChange={(e) => setMinutes(+e.target.value)}
                />
              </label>
            </div>
            <button
              className="button primary full"
              disabled={busy || !model || question.length < 5}
              onClick={start}
            >
              <Play size={15} />
              {busy ? "Starting…" : "Begin research"}
            </button>
            <p className="microcopy">
              Stops when any limit is reached. The model can propose parameters,
              never rewrite the engine or control inhabitants.
            </p>
          </div>
        </section>
        <div className="lab-results">
          <section className="panel">
            <div className="panel-heading">
              <h2>Field notes</h2>
              <select
                aria-label="Research session"
                value={job?.id || ""}
                onChange={(e) => setSelected(e.target.value)}
              >
                <option value="">Choose a session…</option>
                {jobs.map((j) => (
                  <option key={j.id} value={j.id}>
                    {j.id.slice(0, 8)} · {j.status}
                  </option>
                ))}
              </select>
            </div>
            {job ? (
              <>
                <div className="batch-status">
                  <div>
                    <span className="pill">{job.status.toUpperCase()}</span>
                    <h3>
                      {data?.rounds?.length || 0} rounds{" "}
                      <span>· {data?.used_runs || 0} worlds budgeted</span>
                    </h3>
                    <p>
                      {["running", "queued", "cancelling"].includes(job.status)
                        ? "Live activity below"
                        : fmt(data?.elapsed_seconds, 1) + " seconds"}{" "}
                      · {data?.stop_reason || "Research in progress"}
                    </p>
                  </div>
                  {["running", "queued"].includes(job.status) && (
                    <button
                      className="button secondary"
                      onClick={async () => {
                        try {
                          await api(`/research/${job.id}/stop`, {});
                          await refresh();
                        } catch (e) {
                          onError(String(e));
                        }
                      }}
                    >
                      <Square size={14} />
                      Stop
                    </button>
                  )}
                </div>
                <div className="journal-question">
                  {String(job.spec.question)}
                </div>
                {data?.error && (
                  <div className="inline-error">{data.error}</div>
                )}
                <ResearchActivity key={job.id} job={job} />
                {data?.rounds?.map((r) => (
                  <article className="journal-entry" key={r.round}>
                    <div className="eyebrow">
                      ROUND {String(r.round).padStart(2, "0")}{" "}
                      {r.confirmation_of
                        ? "· FRESH-SEED CONFIRMATION"
                        : "· EXPLORATION"}
                    </div>
                    <h3>{r.hypothesis}</h3>
                    <p>{r.rationale}</p>
                    {r.groups.length > 0 && (
                      <div className="table-wrap">
                        <table>
                          <thead>
                            <tr>
                              <th>Measured result</th>
                              <th>Seeds</th>
                              <th>Survival</th>
                              <th>Hungry days</th>
                            </tr>
                          </thead>
                          <tbody>
                            {r.groups.map((g) => (
                              <tr key={g.label}>
                                <td>{g.label}</td>
                                <td>{g.n}</td>
                                <td>{(g.survival * 100).toFixed(1)}%</td>
                                <td>{fmt(g.hungry_days, 1)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                    {r.interpretation && (
                      <div className="model-interpretation">
                        <div className="section-label">
                          MODEL INTERPRETATION · NOT INDEPENDENTLY VERIFIED
                        </div>
                        <p>{r.interpretation.text}</p>
                      </div>
                    )}
                    <a
                      className="text-button"
                      href={`/api/experiments/${r.experiment_id}/export?format=md`}
                    >
                      Download factual report <ArrowUpRight size={14} />
                    </a>
                    <small className="result-id">
                      Evidence: {r.experiment_id}
                    </small>
                  </article>
                ))}
              </>
            ) : (
              <div className="empty journal-empty">
                <BookOpen size={42} />
                <h3>
                  Your next discovery starts
                  <br />
                  with a good question.
                </h3>
                <p>
                  Research sessions preserve their hypotheses, experiment IDs,
                  measured results, and clearly labeled model interpretations.
                </p>
              </div>
            )}
          </section>
          <section className="codex-card">
            <Terminal size={21} />
            <div>
              <h3>Work with Codex instead</h3>
              <p>
                Ask Codex to design a bounded experiment and use the project
                CLI. No model API is required in this app.
              </p>
              <code>uv run virtual-world experiment --seeds 5 --days 365</code>
              <p className="microcopy">
                The CLI and interface use the same engine and local database.
                See AGENTS.md for the research workflow.
              </p>
            </div>
          </section>
        </div>
      </div>
    </>
  );
}
function Chevron() {
  return <span className="research-arrow">→</span>;
}
