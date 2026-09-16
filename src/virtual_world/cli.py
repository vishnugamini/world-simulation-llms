import argparse
import json
from pathlib import Path

from . import research, service
from .models import Branch, CreateRun, ExperimentSpec, ResearchSpec, WorldConfig
from .store import Store


def main():
    parser = argparse.ArgumentParser(
        description="World Simulation LLMs — local simulation and bounded research"
    )
    parser.add_argument("--db", help="SQLite path (default .data/world.sqlite3)")
    sub = parser.add_subparsers(dest="command", required=True)
    r = sub.add_parser("run")
    r.add_argument("--config")
    r.add_argument("--days", type=int, default=30)
    r.add_argument("--name", default="CLI colony")
    e = sub.add_parser("experiment")
    e.add_argument("--config")
    e.add_argument("--resume")
    e.add_argument("--seeds", type=int, default=50)
    e.add_argument("--days", type=int, default=365)
    i = sub.add_parser("inspect")
    i.add_argument("id")
    i.add_argument("--day", type=int)
    b = sub.add_parser("branch")
    b.add_argument("id")
    b.add_argument("--day", type=int, required=True)
    b.add_argument("--policy", choices=["private", "pool", "surplus"])
    b.add_argument("--reserve", type=float)
    b.add_argument("--food-grant", type=float, default=0)
    r = sub.add_parser("report")
    r.add_argument("id")
    r.add_argument("--output")
    r = sub.add_parser("research")
    r.add_argument("--model")
    r.add_argument("--question")
    r.add_argument("--rounds", type=int, default=5)
    r.add_argument("--max-runs", type=int, default=500)
    r.add_argument("--minutes", type=float, default=30)
    r.add_argument("--inspect")
    r.add_argument("--stop")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8765)
    args = parser.parse_args()
    store = Store(args.db)

    def read(path):
        return json.loads(Path(path).read_text()) if path else {}

    if args.command == "run":
        c = WorldConfig(**read(args.config))
        run = service.create_run(store, CreateRun(name=args.name, config=c))
        service.advance(store, run["id"], max(0, min(args.days, c.duration)))
        result = store.run(run["id"])
        result.pop("world")
    elif args.command == "experiment":
        if args.resume:
            id = args.resume
        else:
            spec = (
                ExperimentSpec(**read(args.config))
                if args.config
                else ExperimentSpec(
                    seeds=args.seeds, base=WorldConfig(duration=args.days)
                )
            )
            id = service.new_experiment(store, spec)["id"]
        print(f"Experiment {id}", flush=True)
        service.execute_experiment(store, id)
        result = store.job(id)
    elif args.command == "inspect":
        try:
            result = store.snapshot(args.id, args.day)
        except KeyError:
            result = store.job(args.id)
    elif args.command == "branch":
        result = service.branch(
            store,
            args.id,
            Branch(
                day=args.day,
                policy=args.policy,
                reserve=args.reserve,
                food_grant=args.food_grant,
            ),
        )
    elif args.command == "report":
        result = service.report(store, args.id)
        if args.output:
            Path(args.output).write_text(result)
            print(args.output)
            return
        print(result)
        return
    elif args.command == "research":
        if args.inspect:
            result = store.job(args.inspect)
        elif args.stop:
            result = service.cancel_job(store, args.stop)
        else:
            if not args.model or not args.question:
                parser.error(
                    "research requires --model and --question, or --inspect/--stop"
                )
            spec = ResearchSpec(
                question=args.question,
                model=args.model,
                rounds=args.rounds,
                max_runs=args.max_runs,
                minutes=args.minutes,
            )
            job = research.new_research(store, spec)
            print(f"Research {job['id']}", flush=True)
            research.execute_research(store, job["id"])
            result = store.job(job["id"])
    elif args.command == "serve":
        import uvicorn

        from .api import create_app

        uvicorn.run(create_app(args.db), host="127.0.0.1", port=args.port)
        return
    print(json.dumps(result, indent=2))
    if isinstance(result, dict) and result.get("status") == "failed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
