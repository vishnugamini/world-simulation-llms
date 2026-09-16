import { useEffect, useRef, useState } from "react";
import { api, type Job } from "./api";
import type { components } from "./generated";
type Event = components["schemas"]["ResearchEvent"];
type Page = components["schemas"]["ResearchEvents"];
const pretty = (value: unknown) => JSON.stringify(value, null, 2);

export default function ResearchActivity({ job }: { job: Job }) {
  const [events, setEvents] = useState<Event[]>([]);
  const [error, setError] = useState("");
  const [loaded, setLoaded] = useState(false);
  const [follow, setFollow] = useState(true);
  const [filter, setFilter] = useState("all");
  const [now, setNow] = useState(Date.now());
  const viewport = useRef<HTMLDivElement>(null);
  useEffect(() => {
    let cancelled = false,
      cursor = 0;
    let timer: ReturnType<typeof setTimeout>;
    async function poll() {
      try {
        const page = await api<Page>(
          `/research/${job.id}/events?after=${cursor}`,
        );
        if (cancelled) return;
        cursor = page.next_cursor;
        setEvents((old) => [...old, ...page.events]);
        setError("");
        setLoaded(true);
        timer = setTimeout(poll, page.has_more ? 0 : 600);
      } catch (e) {
        if (cancelled) return;
        setError(String(e));
        timer = setTimeout(poll, 2000);
      }
    }
    poll();
    const clock = setInterval(() => setNow(Date.now()), 1000);
    return () => {
      cancelled = true;
      clearTimeout(timer);
      clearInterval(clock);
    };
  }, [job.id]);
  useEffect(() => {
    if (follow && viewport.current)
      viewport.current.scrollTop = viewport.current.scrollHeight;
  }, [events, follow, filter]);
  const active = ["queued", "running", "cancelling"].includes(job.status);
  const latest = [...events].reverse().find((e) => e.kind !== "model.delta");
  const progress = [...events]
    .reverse()
    .find((e) => e.data.total !== undefined && e.data.completed !== undefined);
  const elapsed =
    active && job.data.started_at
      ? Math.max(0, now / 1000 - Number(job.data.started_at))
      : Number(job.data.elapsed_seconds || 0);
  const visible = events.filter(
    (e) =>
      e.kind !== "model.delta" &&
      e.kind !== "model.connected" &&
      (filter === "all" ||
        (filter === "model"
          ? e.kind.startsWith("model.") || e.kind.startsWith("validation.")
          : !e.kind.startsWith("model.") && !e.kind.startsWith("validation."))),
  );
  const responses = new Map<
    string,
    { content: string; thinking: string; complete: boolean }
  >();
  for (const e of events) {
    const id = String(e.data.request_id || "");
    if (!id) continue;
    const value = responses.get(id) || {
      content: "",
      thinking: "",
      complete: false,
    };
    if (e.kind === "model.delta") {
      if (e.data.channel === "thinking")
        value.thinking += String(e.data.text || "");
      else value.content += String(e.data.text || "");
    }
    if (e.kind === "model.completed") value.complete = true;
    responses.set(id, value);
  }
  return (
    <section className="research-activity" aria-label="Live research activity">
      <div className="activity-heading">
        <div>
          <div className="eyebrow">LIVE ACTIVITY · SAVED AUTOMATICALLY</div>
          <h3>
            {(events.at(-1)?.kind === "model.delta" && active
              ? "Model is writing its " +
                String(events.at(-1)?.data.stage || "response") +
                "…"
              : latest?.message) ||
              (active ? "Waiting for the researcher…" : "Session activity")}
          </h3>
        </div>
        <span className="pill">
          {Math.floor(elapsed / 60)}m {Math.floor(elapsed % 60)}s
        </span>
      </div>
      <p className="microcopy">
        Model text streams below. Prompts, settings, validation, simulation
        results, and stop reasons stay in this record. Model explanations are
        interpretations, not verified conclusions.
      </p>
      {progress && (
        <div className="activity-progress">
          <progress
            value={Number(progress.data.completed)}
            max={Number(progress.data.total)}
          />
          <span>
            {String(progress.data.completed)} / {String(progress.data.total)}{" "}
            worlds completed in this batch
          </span>
        </div>
      )}
      <div className="activity-tools">
        <select
          aria-label="Activity filter"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
        >
          <option value="all">All activity</option>
          <option value="model">Model & validation</option>
          <option value="simulator">Simulator & session</option>
        </select>
        <label>
          <input
            type="checkbox"
            checked={follow}
            onChange={(e) => setFollow(e.target.checked)}
          />{" "}
          Follow output
        </label>
        <a
          className="text-button"
          href={`/api/research/${job.id}/activity/export`}
        >
          Download full log
        </a>
      </div>
      {error && (
        <p role="alert" className="inline-error">
          Activity connection interrupted. Retrying… {error}
        </p>
      )}
      <div
        ref={viewport}
        className="activity-feed"
        tabIndex={0}
        aria-label="Activity transcript"
      >
        {!loaded && !error && <p>Loading activity…</p>}
        {loaded && !events.length && (
          <p className="microcopy">
            {active
              ? "Waiting for the first recorded event…"
              : "Live traces were not recorded for this session. New sessions record their activity here."}
          </p>
        )}
        {visible.map((e) => {
          const response = responses.get(String(e.data.request_id));
          return (
            <article
              className={
                "activity-event " +
                (e.kind === "model.request" ? "model-event" : "")
              }
              key={e.seq}
            >
              <div className="activity-meta">
                <time>{new Date(e.created * 1000).toLocaleTimeString()}</time>
                <span>
                  {e.kind.startsWith("model.")
                    ? "LOCAL MODEL"
                    : e.kind.startsWith("validation.")
                      ? "VALIDATION"
                      : "SIMULATOR / SESSION"}
                  {e.data.round ? ` · ROUND ${e.data.round}` : ""}
                </span>
              </div>
              <strong>{e.message}</strong>
              {e.kind === "model.request" ? (
                <>
                  <details>
                    <summary>
                      Exact prompt, schema & model settings · attempt{" "}
                      {String(e.data.attempt)}
                    </summary>
                    <pre>{pretty(e.data.request)}</pre>
                  </details>
                  <div className="stream-label">
                    {response?.complete
                      ? "Model output · complete"
                      : active
                        ? "Model output · waiting / streaming"
                        : "Model output · stream ended"}
                  </div>
                  <pre className="model-output">
                    {response?.content || "Waiting for text from Ollama…"}
                  </pre>
                  {response?.thinking && (
                    <details open>
                      <summary>
                        Reasoning text returned by the local model
                      </summary>
                      <pre>{response.thinking}</pre>
                    </details>
                  )}
                </>
              ) : (
                Object.keys(e.data).filter((k) => k !== "round").length > 0 && (
                  <details>
                    <summary>Inspect recorded details</summary>
                    <pre>{pretty(e.data)}</pre>
                  </details>
                )
              )}
            </article>
          );
        })}
      </div>
    </section>
  );
}
