"""One supervised experiment step at a time; never an unattended runtime."""
import argparse
import ast
from decimal import Decimal
import fcntl
import json
import os
from pathlib import Path
import shutil
import signal
import sys
import time

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT.parent / "BlenderWorld/scripts"))
from ofox_tunnel import OfoxTunnel
from e_harness.context import build_model_context
from e_harness.model_client import token_counts
from e_harness.prompts import get_system_prompt
from e_harness.storage import Storage
from e_harness.tools import TOOLS
from jsonschema import validate
from accounting import balance, charge

BATCH = ROOT / "runs/contrast24_gpt6_sol_20261017"


def read(path):
    return json.loads(path.read_text())


def write(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def problem(folder, kind, origin, **details):
    event = {"event": "problem", "time": time.time(), "round": folder.name,
             "kind": kind, "origin": origin, **details}
    for path in (folder / "trajectory.jsonl", folder.parent / "issues.jsonl"):
        with path.open("a") as stream:
            stream.write(json.dumps(event, ensure_ascii=False) + "\n")


def records():
    return [read(path) for path in sorted(BATCH.glob("*/round_*/summary.json"))]


def report():
    rows = records()
    known = [Decimal(row["account_charge_difference_usd"]) for row in rows
             if row.get("account_charge_difference_usd") is not None]
    balances = [read(path) for path in BATCH.glob("*/round_*/balance_*.json")]
    initial = read(BATCH / "balance_initial.json") if (BATCH / "balance_initial.json").exists() else None
    settled = max((charge(initial, item) for item in balances), default=Decimal(0)) if initial else Decimal(0)
    summary = {"status": "supervised_experiment", "api_calls": sum(row.get("api_calls", 0) for row in rows),
        "account_charge_difference_usd": str(settled),
        "sum_immediate_request_deltas_usd": str(sum(known, Decimal(0))),
        "sdk_confirmed_cost_usd": None,
        "settlement_status": "Latest charge may not yet be reflected; later requests can reveal prior settlements",
        "unknown_charge_calls": sum(row.get("api_calls", 0) for row in rows if row.get("account_charge_difference_usd") is None),
        "input_tokens": sum(row.get("input_tokens") or 0 for row in rows),
        "output_tokens": sum(row.get("output_tokens") or 0 for row in rows),
        "total_tokens": sum(row.get("total_tokens") or 0 for row in rows),
        "calls_missing_usage": sum(row.get("api_calls", 0) for row in rows if row.get("total_tokens") is None),
        "api_latency_seconds": round(sum(row.get("api_latency_seconds", 0) for row in rows), 3),
        "estimated_uncached_cost_usd": str(sum((Decimal(str(row.get("input_tokens") or 0)) * Decimal("0.000002")
            + Decimal(str(row.get("output_tokens") or 0)) * Decimal("0.00001") for row in rows), Decimal(0))),
        "completed_exports": sum(read(path).get("success", False) for path in BATCH.glob("*/export/summary.json")),
        "formal_runtime_status": "blocked",
        "cost_note": "Account-level difference, not SDK cost; concurrent use and delayed settlement can affect it."}
    write(BATCH / "summary.json", summary)
    return summary


def history(store, image_root):
    messages = [{"role": "system", "content": get_system_prompt("incremental_v1")},
                {"role": "user", "content": [store.image(store.root / "input.png")]}]
    for folder in sorted(image_root.glob("round_*")):
        if folder == store.root:
            continue
        previous = read(folder / "summary.json")
        if previous["status"] != "valid_tool_call" or not (folder / "tool_result.json").exists():
            raise ValueError("Previous step is unresolved or stopped; do not issue another request")
        message = read(folder / "model_response.json")["choices"][0]["message"]
        call = message["tool_calls"][0]
        result = read(folder / "tool_result.json")
        if call["function"]["name"] == "finish" and result.get("success"):
            raise ValueError("Agent already finished")
        messages.extend([message, {"role": "tool", "tool_call_id": call["id"],
            "name": call["function"]["name"], "content": json.dumps(result)}])
        if result.get("success") and result.get("render_path"):
            target = store.root / (folder.name + "_feedback.png")
            shutil.copyfile(result["render_path"], target)
            messages.append({"role": "user", "content": [
                {"type": "text", "text": f"Your scene {result['scene_version']}, {call['function']['name']} image:"},
                store.image(target)]})
    return messages


def request(image_id):
    import requests
    config = read(BATCH / "config.json")
    image_root = BATCH / image_id
    previous = sorted(image_root.glob("round_*"))
    number = len(previous)
    if (BATCH / "SAFETY_STOP.json").exists():
        raise ValueError("Safety stop active")
    if number >= config["max_api_calls_per_image"]:
        print(f"{image_id}: per-image request budget exhausted")
        return
    if previous:
        last = read(previous[-1] / "summary.json")
        if last["status"] != "valid_tool_call":
            print(f"{image_id}: stopped at {last['status']}; no automatic retry")
            return
        if not (previous[-1] / "tool_result.json").exists():
            raise ValueError("Saved submission is awaiting review/execution")
        if last["tool_name"] == "finish" and read(previous[-1] / "tool_result.json").get("success"):
            print(f"{image_id}: agent already finished")
            return
    ledger = report()
    if ledger["unknown_charge_calls"] or ledger["api_calls"] >= config["max_api_calls_batch"]:
        raise ValueError("Batch limit reached or a previous charge is unknown")
    # Reserve 1 USD per request, well above the cached-route price for this short experiment.
    # This is a conservative estimate, not a guarantee of future provider billing.
    observed_or_estimated = max(Decimal(ledger["account_charge_difference_usd"]),
                                Decimal(ledger["estimated_uncached_cost_usd"]) * 2)
    if observed_or_estimated + Decimal("1") > Decimal(config["budget_usd"]):
        raise ValueError("Insufficient remaining batch budget including a 1 USD request reserve")
    manifest = read(ROOT / config["dataset_manifest"])
    item = next(row for row in manifest["images"] if row["id"] == image_id)
    source = (ROOT / config["dataset_manifest"]).parent / item["image"]
    store = Storage(image_root / f"round_{number:02d}", source, config)
    messages, stats = build_model_context(history(store, image_root), "full")
    store.save_system_prompt(messages[0]["content"])
    payload = {"model": config["model"], "messages": messages, "tools": TOOLS,
               "tool_choice": "auto", "max_tokens": config["max_output_tokens"]}
    store.event("model_request", messages=messages, tools=TOOLS, context=stats,
                model=payload["model"], transport="requests.Session.post through OfoxTunnel", retries=0)
    summary = {"api_calls": 0, "status": "prepared", "model": config["model"],
        "account_charge_difference_usd": None, "cost_note": "Immediate account delta; zero does not imply free inference",
        **token_counts(None)}
    store.write("summary.json", summary)
    key = os.environ.get("OFOX_API_KEY") or os.environ.get("VLM_API_KEY")
    if not key:
        raise ValueError("Set OFOX_API_KEY or VLM_API_KEY")
    try:
        with OfoxTunnel(ip="47.83.144.71") as tunnel, requests.Session() as session:
            tunnel.configure_session(session)
            before = balance(session, config["api_base_url"], key)
            store.write("balance_before.json", before)
            if not (BATCH / "balance_initial.json").exists():
                write(BATCH / "balance_initial.json", before)
            cumulative = charge(read(BATCH / "balance_initial.json"), before)
            if cumulative + Decimal("1") > Decimal(config["budget_usd"]):
                raise ValueError("Account-level budget guard stopped before inference")
            if "overall_budget_usd" in config:
                overall = Decimal(config["prior_cost_usd"]) + cumulative
                if overall + Decimal("1") > Decimal(config["overall_budget_usd"]):
                    raise ValueError("Combined experiment budget guard stopped before inference")
            print(f"[OFox] {image_id} turn {number}: before {before['balance']} USD", flush=True)
            summary.update(api_calls=1, status="request_started")
            store.write("summary.json", summary)
            started = time.monotonic()
            try:
                response = session.post(config["api_base_url"].rstrip("/") + "/chat/completions",
                    headers={"Authorization": "Bearer " + key}, json=payload,
                    timeout=(10, config["api_timeout_seconds"]), allow_redirects=False)
                summary.update(api_latency_seconds=round(time.monotonic() - started, 3), http_status=response.status_code)
                response.raise_for_status()
                reply = response.json()
                store.write("model_response.json", reply)
                summary.update(**token_counts(reply.get("usage")), usage=reply.get("usage"))
                choice = reply["choices"][0]
                summary["finish_reason"] = choice.get("finish_reason")
                calls = choice["message"].get("tool_calls") or []
                store.write("tool_calls.json", calls)
                store.event("model_response", response=reply, latency=summary["api_latency_seconds"])
                if summary["finish_reason"] in ("length", "content_filter"):
                    summary["status"] = "incomplete_response"
                elif len(calls) != 1:
                    summary["status"] = "no_single_tool_call"
                else:
                    call = calls[0]
                    arguments = json.loads(call["function"]["arguments"])
                    schema = next(tool["function"]["parameters"] for tool in TOOLS if tool["function"]["name"] == call["function"]["name"])
                    validate(arguments, schema)
                    summary.update(status="valid_tool_call", tool_name=call["function"]["name"])
                    if call["function"]["name"] == "execute_blender":
                        code = arguments["code"].encode("utf-8")
                        (store.root / "code.py").write_bytes(code)
                        summary.update(mode=arguments.get("mode", "replace"), code_bytes=len(code), code_lines=len(code.splitlines()))
                        try:
                            ast.parse(code, filename="code.py")
                            summary["syntax_status"] = "valid"
                        except SyntaxError as exc:
                            summary.update(syntax_status="invalid", error=str(exc))
                            result = {"success": False, "executed": False,
                                "scene_version": len(list((image_root / "runtime").glob("scene_v*"))),
                                "error_type": "SyntaxError", "error": f"SyntaxError at line {exc.lineno}: {exc.msg}",
                                "source_line": (exc.text or "").strip()}
                            store.write("tool_result.json", result)
                            store.event("tool_result", name="execute_blender", tool_call_id=call["id"], result=result)
                            problem(store.root, "python_syntax_error", "model_output",
                                    tool_call_id=call["id"], line=exc.lineno,
                                    scene_version=result["scene_version"], detail_file="tool_result.json")
            except Exception as exc:
                summary.update(status="request_or_protocol_error", error=type(exc).__name__ + ": " + str(exc))
                summary.setdefault("api_latency_seconds", round(time.monotonic() - started, 3))
            finally:
                try:
                    after = balance(session, config["api_base_url"], key)
                    store.write("balance_after.json", after)
                    summary["account_charge_difference_usd"] = str(charge(before, after))
                    print(f"[OFox] after {after['balance']} USD; delta {summary['account_charge_difference_usd']} USD", flush=True)
                except Exception as exc:
                    summary["balance_after_error"] = str(exc)
    except Exception as exc:
        summary.update(status="stopped_before_inference" if not summary["api_calls"] else summary["status"], error=str(exc))
    store.write("summary.json", summary)
    if summary["status"] != "valid_tool_call":
        kind = summary.get("finish_reason") if summary.get("finish_reason") in ("length", "content_filter") else summary["status"]
        problem(store.root, kind, "api_or_protocol", detail_file="summary.json")
    store.event("request_stopped", **summary)
    report()
    print(json.dumps(summary, ensure_ascii=False, indent=2))


def apply(image_id, review_note):
    from supervised_runtime import SupervisedRuntime, cpu
    folder = sorted((BATCH / image_id).glob("round_*"))[-1]
    if (folder / "approval.json").exists() or (folder / "tool_result.json").exists() or (BATCH / "SAFETY_STOP.json").exists():
        raise ValueError("Already processed or safety stop active; no automatic rerun")
    if read(folder / "summary.json")["status"] != "valid_tool_call":
        raise ValueError("Only a complete, schema-valid single tool call can be processed")
    call = read(folder / "model_response.json")["choices"][0]["message"]["tool_calls"][0]
    name = call["function"]["name"]
    arguments = json.loads(call["function"]["arguments"])
    source = arguments["code"].encode("utf-8") if name == "execute_blender" else None
    if source is not None and (folder / "code.py").read_bytes() != source:
        raise ValueError("Review copy differs from the original response")
    if source is not None and not review_note:
        raise ValueError("An explicit per-submission assistant review note is required")
    write(folder / "approval.json", {"reviewer": "assistant", "authorization": "user_delegated_supervised_review",
        "approved": True, "note": review_note or "Trusted observation/finish operation on the approved saved scene",
        "code_bytes": len(source) if source is not None else None, "is_sandbox": False, "time": time.time()})
    runtime = SupervisedRuntime(BATCH / image_id / "runtime", approved_source=source)
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if name == "execute_blender":
            result = runtime.execute(arguments["code"], 600, mode=arguments.get("mode", "replace"))
        elif name == "render_scene":
            result = runtime.render(timeout=600, **arguments)
        elif name == "inspect_scene":
            result = runtime.inspect(600)
        elif name == "finish":
            result = {"success": False, "error": "No successful scene"}
            if runtime.current:
                result = runtime.render("input", 600) if not runtime.input_render else {"success": True}
                if result["success"]:
                    runtime.export()
                    result.update(scene_version=runtime.version, blend_path=str(runtime.root / "final.blend"),
                                  render_path=str(runtime.root / "final.png"))
        else:
            raise ValueError("Unknown tool")
    write(folder / "tool_result.json", result)
    with (folder / "trajectory.jsonl").open("a") as stream:
        stream.write(json.dumps({"event": "tool_result", "name": name, "tool_call_id": call["id"], "result": result}) + "\n")
    if not result["success"]:
        problem(folder, "tool_failure", "tool_execution", tool_name=name,
                tool_call_id=call["id"], scene_version=runtime.version, detail_file="tool_result.json")
    display = {key: result[key] for key in ("success", "scene_version", "execution_status", "render_path", "blend_path", "error", "resources") if key in result}
    display["object_count"] = result.get("data", {}).get("object_count")
    display["render_device"] = result.get("data", {}).get("device")
    print(json.dumps(display, ensure_ascii=False, indent=2))


def export(image_id, groups):
    from supervised_runtime import SupervisedRuntime, cpu
    import gpu_profile
    root = BATCH / image_id
    if (BATCH / "SAFETY_STOP.json").exists() or (root / "final.blend").exists():
        raise ValueError("Safety stop or an export already exists")
    runtime = SupervisedRuntime(root / "runtime")
    if not runtime.current:
        raise ValueError("No successful model scene to export")
    folder = root / "export"
    folder.mkdir(exist_ok=False)
    shutil.copyfile(groups, folder / "groups.json")
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        if not runtime.input_render:
            rendered = runtime.render("input", 600)
            if not rendered["success"]:
                write(folder / "summary.json", rendered)
                return
        shutil.copyfile(runtime.current / "scene.blend", root / "final_parts.blend")
        shutil.copyfile(runtime.input_render, root / "final_parts.png")
        job = {"blend": str(root / "final_parts.blend"), "output_blend": str(root / "final.blend"),
            "groups": str(folder / "groups.json"), "result": str(folder / "merge_report.json"),
            "settings_helper": str(ROOT / "e_harness/runtime/blender_entry.py")}
        write(folder / "merge_job.json", job)
        merged = gpu_profile.launch(folder, Path(__file__).with_name("merge_blender.py"), folder / "merge_job.json", label="merge")
        write(folder / "summary.json", {"merge": merged, "postprocessing_not_agent_revision": True})
        if not merged["success"] or not merged["cleanup_complete"]:
            return
        render_folder = folder / "render"
        rendered = runtime.process({"operation": "render", "blend": str(root / "final.blend"), "view": "input",
            "image": str(root / "final.png"), "samples": 8, "resolution": [256, 256]}, render_folder, 600)
        result = {"success": rendered["success"], "merge": merged, "render": rendered,
                  "source_scene_version": runtime.version, "postprocessing_not_agent_revision": True}
        write(folder / "summary.json", result)
    report()
    print(json.dumps({"image": image_id, "success": result["success"], "final": str(root / "final.blend")}, indent=2))


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--request", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--export", action="store_true")
    parser.add_argument("--review-note")
    parser.add_argument("--groups", type=Path)
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    if args.request:
        if not args.live:
            parser.error("A real request requires --live")
        with (BATCH / ".api.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            request(args.image)
    elif args.apply:
        apply(args.image, args.review_note)
    else:
        if args.groups is None:
            parser.error("--export requires --groups (generated-object grouping only)")
        export(args.image, args.groups)


if __name__ == "__main__":
    main()
