import { useEffect, useState } from "react";
import { api, policyNames, type Run } from "./api";
export default function SavedWorlds({
  onOpen,
}: {
  onOpen: (id: string) => void;
}) {
  const [page, setPage] = useState(0),
    [rows, setRows] = useState<Omit<Run, "world">[]>([]),
    [loading, setLoading] = useState(false),
    [error, setError] = useState("");
  useEffect(() => {
    let current = true;
    setLoading(true);
    api<Omit<Run, "world">[]>(`/runs?limit=25&offset=${page * 25}`)
      .then((r) => {
        if (current) setRows(r);
      })
      .catch((e) => {
        if (current) setError(String(e));
      })
      .finally(() => {
        if (current) setLoading(false);
      });
    return () => {
      current = false;
    };
  }, [page]);
  return (
    <>
      <p className="microcopy">
        Every colony and every experiment world keeps its saved history.
      </p>
      {error && <p role="alert">{error}</p>}
      <div className="saved-worlds">
        {rows.map((r) => (
          <button key={r.id} onClick={() => onOpen(r.id)}>
            <span>
              <b>{r.name}</b>
              <small>
                Seed {r.config.seed} · {policyNames[r.config.policy]}
                {r.experiment ? " · experiment" : ""}
              </small>
            </span>
            <span>Day {r.day} ↗</span>
          </button>
        ))}
      </div>
      <div className="saved-pagination">
        <button
          className="button secondary"
          disabled={loading || page === 0}
          onClick={() => setPage(page - 1)}
        >
          Previous
        </button>
        <span>{loading ? "Loading…" : `Page ${page + 1}`}</span>
        <button
          className="button secondary"
          disabled={loading || rows.length < 25}
          onClick={() => setPage(page + 1)}
        >
          Next
        </button>
      </div>
    </>
  );
}
