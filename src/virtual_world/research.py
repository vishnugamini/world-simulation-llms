"""A bounded local-model planner; models never execute code or control agents."""

import json
import threading
import time

import httpx

from .activity import ResearchStopped, Trace, current_trace, emit
from .models import ExperimentSpec, Interpretation, Proposal, ResearchSpec
from .service import execute_experiment, new_experiment, summarize
from .store import new_id

OLLAMA = "http://127.0.0.1:11434"


def grammar_schema(model):
    """Keep structural constraints in Ollama; enforce every bound with Pydantic.

    Some local Ollama grammars cannot compile bounded-number schemas. Resolve
    references and omit those grammar-only bounds without weakening validation.
    """
    schema = model.model_json_schema()
    definitions = schema.get("$defs", {})
    omitted = {
        "$defs",
        "title",
        "default",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "minLength",
        "maxLength",
        "minItems",
        "maxItems",
    }

    def simplify(value):
        if isinstance(value, list):
            return [simplify(v) for v in value]
        if not isinstance(value, dict):
            return value
        if "$ref" in value:
            return simplify(definitions[value["$ref"].split("/")[-1]])
        return {k: simplify(v) for k, v in value.items() if k not in omitted}

    return simplify(schema)


def local_models():
    try:
        with httpx.Client(timeout=3, trust_env=False) as client:
            r = client.get(OLLAMA + "/api/tags")
            r.raise_for_status()
        models = [
            m["name"]
            for m in r.json().get("models", [])
            if not m.get("remote_host") and ":cloud" not in m["name"]
        ]
        return {"available": True, "models": models, "error": None}
    except (httpx.HTTPError, ValueError, KeyError, TypeError):
        return {
            "available": False,
            "models": [],
            "error": "Ollama is not available at localhost:11434. Start it and install a local model to enable research. The World and Lab do not require it.",
        }


def ask(model, schema, messages, deadline, constraints=None):
    last = None
    wire_schema = grammar_schema(schema)
    if schema is Proposal and constraints is not None:
        wire_schema["properties"]["confirm_experiment_id"] = {
            "enum": [None, *constraints["result_ids"]]
        }
    if schema is Interpretation and constraints is not None:
        wire_schema["properties"]["result_ids"]["items"] = {
            "enum": constraints["result_ids"]
        }
    for attempt in range(2):
        remaining = deadline - time.time()
        if remaining <= 0:
            raise TimeoutError("Research wall-time budget exhausted")
        try:
            trace = current_trace.get()
            if trace:
                trace.check_stop()
            request_id = new_id()
            payload = {
                "model": model,
                "stream": True,
                "think": "low" if model.startswith("gpt-oss") else False,
                "messages": messages,
                "format": wire_schema,
                "options": {"temperature": 0, "num_predict": 2200, "num_ctx": 8192},
                "keep_alive": "5m",
            }
            stage = "proposal" if schema is Proposal else "interpretation"
            emit(
                "model.request",
                "Asking the model for an experiment proposal"
                if stage == "proposal"
                else "Asking the model to interpret measured results",
                request_id=request_id,
                stage=stage,
                attempt=attempt + 1,
                request=payload,
            )
            text_parts = []
            buffers = {"content": [], "thinking": []}
            last_flush = time.monotonic()
            done = False
            completion = {}
            call_deadline = min(deadline, time.time() + 60)

            def flush(
                buffers=buffers, request_id=request_id, stage=stage, attempt=attempt
            ):
                nonlocal last_flush
                for channel, parts in buffers.items():
                    if parts:
                        emit(
                            "model.delta",
                            "Model output"
                            if channel == "content"
                            else "Local model reasoning output",
                            request_id=request_id,
                            stage=stage,
                            attempt=attempt + 1,
                            channel=channel,
                            text="".join(parts),
                        )
                        parts.clear()
                last_flush = time.monotonic()

            try:
                with (
                    httpx.Client(timeout=min(60, remaining), trust_env=False) as client,
                    client.stream(
                        "POST", OLLAMA + "/api/chat", json=payload
                    ) as response,
                ):
                    if response.is_error:
                        response.read()
                        raise RuntimeError(
                            f"Local model request failed ({response.status_code}): {response.text[:500]}"
                        )
                    emit(
                        "model.connected",
                        "Connected to Ollama; waiting for generated text",
                        request_id=request_id,
                        stage=stage,
                    )
                    for line in response.iter_lines():
                        if time.time() >= deadline:
                            raise TimeoutError("Research wall-time budget exhausted")
                        if time.time() >= call_deadline:
                            raise httpx.ReadTimeout(
                                "Local model exceeded its 60-second response limit"
                            )
                        if trace:
                            trace.check_stop()
                        if not line:
                            continue
                        packet = json.loads(line)
                        if packet.get("error"):
                            raise RuntimeError(str(packet["error"]))
                        message = packet.get("message", {})
                        for channel, parts in buffers.items():
                            delta = message.get(channel, "")
                            if delta:
                                parts.append(delta)
                                if channel == "content":
                                    text_parts.append(delta)
                        if message.get("tool_calls"):
                            emit(
                                "model.tool_calls",
                                "Model emitted tool calls; none are executed",
                                request_id=request_id,
                                tool_calls=message["tool_calls"],
                            )
                        if time.monotonic() - last_flush >= 0.15:
                            flush()
                        if packet.get("done"):
                            done = True
                            completion = {
                                k: v for k, v in packet.items() if k != "message"
                            }
                            break
            finally:
                flush()
            if not done:
                raise ValueError(
                    "Model stream ended before a completion marker; partial output retained"
                )
            emit(
                "model.completed",
                "Model response complete; validating structured output",
                request_id=request_id,
                stage=stage,
                **completion,
            )
            result = schema.model_validate_json("".join(text_parts))
            if (
                isinstance(result, Proposal)
                and constraints is not None
                and not result.stop
            ):
                if result.confirm_experiment_id:
                    if result.confirm_experiment_id not in constraints["result_ids"]:
                        raise ValueError(
                            "Confirmation must reference an existing result ID, otherwise use null"
                        )
                    if result.experiment is not None:
                        raise ValueError(
                            "A confirmation must omit experiment and reuse its source configuration"
                        )
                elif result.experiment.total > constraints["remaining_runs"]:
                    raise ValueError(
                        "Experiment exceeds remaining run budget; reduce seeds or conditions"
                    )
            emit(
                "validation.accepted",
                "Model response passed validation",
                request_id=request_id,
                stage=stage,
                value=result.model_dump(),
            )
            return result
        except (ValueError, KeyError) as e:
            last = e
            emit(
                "validation.rejected",
                "Invalid model output; retrying once"
                if attempt == 0
                else "Invalid model output; retry limit reached",
                attempt=attempt + 1,
                error=str(e),
                will_retry=attempt == 0,
            )
            messages = messages + [
                {
                    "role": "user",
                    "content": f"Your proposal did not validate: {str(e)[:500]}. Return only valid JSON matching the schema.",
                }
            ]
    raise ValueError(f"Invalid model output after one retry: {last}")


def new_research(store, spec: ResearchSpec):
    available = local_models()
    if spec.model not in available["models"]:
        raise ValueError(available["error"] or "Select an installed local model")
    job = store.create_job(
        "research",
        spec.model_dump(),
        {"rounds": [], "used_runs": 0, "elapsed_seconds": 0},
    )
    store.append_event(
        job["id"],
        "session.queued",
        "Research session queued",
        {"spec": spec.model_dump()},
    )
    return job


def execute_research(store, id):
    if store.job(id)["status"] == "cancelling":
        store.update_job(id, "cancelled", stop_reason="Stopped before starting")
        store.append_event(
            id, "session.finished", "Stopped before starting", {"status": "cancelled"}
        )
        return
    started = time.time()
    spec = ResearchSpec(**store.job(id)["spec"])
    deadline = started + spec.minutes * 60
    store.update_job(id, "running", started_at=started, deadline_at=deadline)
    trace = Trace(store, id)
    token = current_trace.set(trace)
    trace.emit(
        "session.started",
        "Research started",
        model=spec.model,
        budget=spec.model_dump(),
        deadline_at=deadline,
    )
    history = []
    used = 0
    try:
        for number in range(spec.rounds):
            trace.round = number + 1
            trace.emit(
                "round.started",
                f"Starting round {number + 1}",
                remaining_runs=spec.max_runs - used,
                remaining_seconds=max(0, deadline - time.time()),
            )
            if store.job(id)["status"] != "running":
                break
            if time.time() >= deadline or used >= spec.max_runs:
                break
            context = {
                "question": spec.question,
                "remaining_runs": spec.max_runs - used,
                "round": number + 1,
                "prior_results": history,
            }
            messages = [
                {
                    "role": "system",
                    "content": "You are a researcher studying a rule-based food-sharing simulation, not real societies. Propose one small controlled experiment within the remaining run budget. Allowed policies: private,pool,surplus. Conditions: individual,drought,baseline. Prefer paired comparisons. For confirmation, supply confirm_experiment_id from prior results AND set experiment to null: the engine will reuse its configuration with fresh seeds. Otherwise supply a valid experiment and set confirm_experiment_id to null. When there are no prior results, you MUST use null for confirm_experiment_id. Omit optional config fields to keep defaults. Run count = seeds times conditions times policy variants. You cannot edit the engine. Stop when evidence is sufficient. Never invent results or IDs.",
                },
                {
                    "role": "user",
                    "content": json.dumps(context)
                    + "\nReturn a proposal matching this schema: "
                    + json.dumps(Proposal.model_json_schema()),
                },
            ]
            proposal = ask(
                spec.model,
                Proposal,
                messages,
                deadline,
                {
                    "result_ids": [r["experiment_id"] for r in history],
                    "remaining_runs": spec.max_runs - used,
                },
            )
            if store.job(id)["status"] != "running":
                break
            if proposal.stop:
                store.update_job(id, stop_reason=proposal.rationale)
                break
            if proposal.confirm_experiment_id:
                prior = next(
                    (
                        r
                        for r in history
                        if r["experiment_id"] == proposal.confirm_experiment_id
                    ),
                    None,
                )
                if not prior:
                    raise ValueError(
                        "Confirmation must reference a result from this research session"
                    )
                exp = ExperimentSpec(
                    **store.job(proposal.confirm_experiment_id)["spec"]
                )
            else:
                exp = proposal.experiment
            # Disjoint, engine-assigned seed windows prevent exploratory/confirmation reuse.
            exp = exp.model_copy(update={"seed_start": 100000 + number * 1000})
            if exp.total > spec.max_runs - used:
                raise ValueError("Proposal exceeds remaining run budget")
            trace.emit(
                "experiment.configured",
                "Validated experiment configured with engine-assigned seeds",
                configuration=exp.model_dump(),
                total=exp.total,
                confirmation_of=proposal.confirm_experiment_id,
            )
            job = new_experiment(store, exp)
            used += exp.total
            record = {
                "round": number + 1,
                "hypothesis": proposal.hypothesis,
                "rationale": proposal.rationale,
                "experiment_id": job["id"],
                "confirmation_of": proposal.confirm_experiment_id,
                "interpretation": None,
                "groups": [],
            }
            history.append(record)
            store.update_job(
                id, rounds=history, used_runs=used, active_experiment=job["id"]
            )
            execute_experiment(
                store, job["id"], deadline, parent=id, on_event=trace.emit
            )
            results = summarize(store, job["id"])
            record["groups"] = results["groups"]
            record["paired"] = results["paired"]
            trace.emit(
                "experiment.results",
                "Measured simulation results are ready",
                experiment_id=job["id"],
                status=results["job"]["status"],
                groups=results["groups"],
                paired=results["paired"],
            )
            store.update_job(id, rounds=history, elapsed_seconds=time.time() - started)
            if store.job(id)["status"] != "running" or time.time() >= deadline:
                break
            if results["job"]["status"] != "complete":
                raise RuntimeError(
                    "Experiment did not complete: "
                    + str(results["job"]["data"].get("error", results["job"]["status"]))
                )
            interpretation = ask(
                spec.model,
                Interpretation,
                [
                    {
                        "role": "system",
                        "content": "Interpret these measured simulation results cautiously. Your text is an unverified model interpretation, not a factual report. Reference only the supplied experiment ID. n means number of matched simulation seeds, NOT number of inhabitants. Survival is a fraction; hungry_days is mean cumulative hungry inhabitant-days per run; spoiled is mean food units lost to spoilage. Recovery is measured among surviving inhabitants. Distinguish group means from totals. Use the supplied population and duration. Do not extrapolate to real societies.",
                    },
                    {
                        "role": "user",
                        "content": json.dumps(
                            {
                                "experiment_id": job["id"],
                                "population_per_world": exp.base.population,
                                "days_per_world": exp.base.duration,
                                "groups": results["groups"],
                                "paired": results["paired"],
                                "caveat": results["caveat"],
                            }
                        ),
                    },
                ],
                deadline,
                {"result_ids": [job["id"]]},
            )
            if any(x != job["id"] for x in interpretation.result_ids):
                raise ValueError("Interpretation references an unknown result")
            record["interpretation"] = interpretation.model_dump()
            trace.emit(
                "round.completed",
                f"Round {number + 1} complete",
                experiment_id=job["id"],
            )
            store.update_job(id, rounds=history, elapsed_seconds=time.time() - started)
        status = "cancelled" if store.job(id)["status"] == "cancelling" else "complete"
        store.update_job(
            id,
            status,
            rounds=history,
            used_runs=used,
            elapsed_seconds=time.time() - started,
            active_experiment=None,
            stop_reason=store.job(id)["data"].get("stop_reason")
            or (
                "Budget reached"
                if time.time() >= deadline or used >= spec.max_runs
                else "Round limit reached"
                if len(history) == spec.rounds
                else "Stopped"
            ),
        )
    except ResearchStopped:
        store.update_job(
            id,
            "cancelled",
            rounds=history,
            used_runs=used,
            elapsed_seconds=time.time() - started,
            active_experiment=None,
            stop_reason="Stopped by user",
        )
    except TimeoutError:
        cancelled = store.job(id)["status"] == "cancelling"
        store.update_job(
            id,
            "cancelled" if cancelled else "complete",
            rounds=history,
            used_runs=used,
            elapsed_seconds=time.time() - started,
            active_experiment=None,
            stop_reason="Stopped" if cancelled else "Wall-time budget reached",
        )
    except Exception as e:  # noqa: BLE001 -- persist failures at the background-job boundary
        status = "cancelled" if store.job(id)["status"] == "cancelling" else "failed"
        store.update_job(
            id,
            status,
            rounds=history,
            error=str(e),
            elapsed_seconds=time.time() - started,
            active_experiment=None,
        )
    finally:
        final = store.job(id)
        trace.emit(
            "session.finished",
            final["data"].get("error")
            or final["data"].get("stop_reason")
            or final["status"],
            status=final["status"],
            elapsed_seconds=time.time() - started,
            used_runs=used,
        )
        current_trace.reset(token)


def launch_research(store, id):
    t = threading.Thread(target=execute_research, args=(store, id), daemon=True)
    t.start()
    return t
