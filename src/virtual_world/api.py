import csv
import io
import json
import zipfile
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import research, service
from .models import (
    Advance,
    Branch,
    CreateRun,
    ExperimentSpec,
    JobView,
    ResearchEvents,
    ResearchSpec,
    RunView,
    Snapshot,
)
from .store import Store


def create_app(db_path=None):
    store = Store(db_path)

    @asynccontextmanager
    async def lifespan(app):
        store.interrupt()
        yield

    app = FastAPI(title="World Simulation LLMs", version="1.0.0", lifespan=lifespan)
    app.state.store = store

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=404, content={"detail": str(exc)})

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=400, content={"detail": str(exc)})

    @app.get("/api/health")
    def health():
        return {"ok": True, "engine": service.ENGINE_VERSION}

    @app.get("/api/runs")
    def runs(limit: int = Query(100, ge=1, le=1000), offset: int = Query(0, ge=0)):
        return store.list_runs(limit, offset=offset)

    @app.post("/api/runs", response_model=RunView)
    def create(request: CreateRun):
        return service.create_run(store, request)

    @app.get("/api/runs/{id}", response_model=RunView)
    def run(id: str):
        return store.run(id)

    @app.get("/api/runs/{id}/state", response_model=Snapshot)
    def state(id: str, day: int | None = Query(None, ge=0)):
        s = store.snapshot(id, day)
        c = store.effective_config(id, s["day"])
        return {**s, "recorded_policy": c["policy"], "recorded_reserve": c["reserve"]}

    @app.post("/api/runs/{id}/advance", response_model=Snapshot)
    def advance(id: str, request: Advance):
        return service.advance(store, id, request.days)

    @app.post("/api/runs/{id}/branch", response_model=RunView)
    def branch(id: str, request: Branch):
        return service.branch(store, id, request)

    @app.get("/api/experiments", response_model=list[JobView])
    def experiments():
        return store.jobs("experiment")

    @app.post("/api/experiments", response_model=JobView)
    def experiment(request: ExperimentSpec):
        job = service.new_experiment(store, request)
        service.launch_experiment(store, job["id"])
        return job

    @app.get("/api/experiments/{id}")
    def results(id: str):
        return service.summarize(store, id)

    @app.post("/api/experiments/{id}/cancel", response_model=JobView)
    def cancel(id: str):
        return service.cancel_job(store, id)

    @app.post("/api/experiments/{id}/resume", response_model=JobView)
    def resume(id: str):
        job = store.job(id)
        if job["kind"] != "experiment":
            raise ValueError("Not an experiment")
        if job["status"] not in ("interrupted", "cancelled", "failed"):
            raise ValueError(
                "Only interrupted, cancelled, or failed batches can resume"
            )
        store.update_job(id, "queued")
        service.launch_experiment(store, id)
        return store.job(id)

    @app.get("/api/experiments/{id}/export")
    def export(id: str, format: str = "zip"):
        if format == "md":
            return Response(
                service.report(store, id),
                media_type="text/markdown",
                headers={
                    "Content-Disposition": f'attachment; filename="experiment-{id}.md"'
                },
            )
        summary = service.summarize(store, id)
        if format == "json":
            return Response(
                json.dumps(summary, indent=2),
                media_type="application/json",
                headers={
                    "Content-Disposition": f'attachment; filename="experiment-{id}.json"'
                },
            )
        output = io.StringIO()
        fields = [
            "run_id",
            "seed",
            "condition",
            "policy",
            "reserve",
            "survival",
            "survivors",
            "hungry_days",
            "spoiled",
            "recovery_days",
            "recovery_status",
            "stored",
            "day",
        ]
        writer = csv.DictWriter(output, fieldnames=fields)
        writer.writeheader()
        for r in summary["runs"]:
            writer.writerow(
                {
                    "run_id": r["id"],
                    **{
                        k: r["config"][k]
                        for k in ["seed", "condition", "policy", "reserve"]
                    },
                    **r["metrics"],
                }
            )
        if format == "csv":
            return Response(
                output.getvalue(),
                media_type="text/csv",
                headers={
                    "Content-Disposition": f'attachment; filename="experiment-{id}.csv"'
                },
            )
        if format != "zip":
            raise ValueError("Formats: zip, json, csv, md")
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr(
                "configuration.json", json.dumps(summary["job"]["spec"], indent=2)
            )
            z.writestr("results.json", json.dumps(summary, indent=2))
            z.writestr("runs.csv", output.getvalue())
            z.writestr("report.md", service.report(store, id))
        return Response(
            buf.getvalue(),
            media_type="application/zip",
            headers={
                "Content-Disposition": f'attachment; filename="experiment-{id}.zip"'
            },
        )

    @app.get("/api/models")
    def models():
        return research.local_models()

    @app.get("/api/research", response_model=list[JobView])
    def sessions():
        return store.jobs("research")

    @app.post("/api/research", response_model=JobView)
    def start(request: ResearchSpec):
        job = research.new_research(store, request)
        research.launch_research(store, job["id"])
        return job

    @app.get("/api/research/{id}", response_model=JobView)
    def session(id: str):
        return store.job(id)

    @app.get("/api/research/{id}/events", response_model=ResearchEvents)
    def activity(
        id: str, after: int = Query(0, ge=0), limit: int = Query(500, ge=1, le=1000)
    ):
        if store.job(id)["kind"] != "research":
            raise ValueError("Not a research session")
        events = store.events(id, after, limit + 1)
        page = events[:limit]
        return {
            "events": page,
            "next_cursor": page[-1]["seq"] if page else after,
            "has_more": len(events) > limit,
        }

    @app.get("/api/research/{id}/activity/export")
    def activity_export(id: str):
        job = store.job(id)
        if job["kind"] != "research":
            raise ValueError("Not a research session")
        return Response(
            json.dumps(
                {"session": job, "events": store.events(id, limit=-1)}, indent=2
            ),
            media_type="application/json",
            headers={
                "Content-Disposition": f'attachment; filename="research-{id}-activity.json"'
            },
        )

    @app.post("/api/research/{id}/stop", response_model=JobView)
    def stop(id: str):
        job = service.cancel_job(store, id)
        if job["data"].get("active_experiment"):
            service.cancel_job(store, job["data"]["active_experiment"])
        return job

    dist = Path(__file__).resolve().parents[2] / "web" / "dist"
    if dist.exists():
        app.mount("/assets", StaticFiles(directory=dist / "assets"), name="assets")

        @app.get("/")
        def index():
            return FileResponse(dist / "index.html")

    return app
