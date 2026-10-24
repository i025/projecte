"""Opt-in real tool-calling experiment with simulated results and no execution runtime."""
import argparse
import ast
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from jsonschema import validate, ValidationError

from e_harness.model_client import ModelClient, token_counts
from e_harness.prompts import PROMPT_VERSIONS, get_system_prompt
from e_harness.storage import Storage
from e_harness.tools import TOOLS
from e_harness.context import build_model_context, record_context_stats

MAX_OUTPUT_TOKENS = 4096
API_TIMEOUT = 180


def dispatch(name, arguments, version, directory):
    result = {"success": False, "simulated": True, "execution_status": "NOT_EXECUTED",
              "scene_version": version, "scene_version_is_virtual": True}
    metrics = {}
    if name == "execute_blender":
        code, mode = arguments["code"], arguments.get("mode", "replace")
        (directory / "generated_code.py").write_bytes(code.encode("utf-8"))
        metrics = {"mode": mode, "mode_explicit": "mode" in arguments,
                   "code_length_characters": len(code), "code_length_bytes": len(code.encode("utf-8")),
                   "code_lines": len(code.splitlines()), "base_scene_version": version if mode == "update" else None,
                   "python_syntax_status": "valid"}
        result.update(mode=mode, base_scene_version=metrics["base_scene_version"])
        try:
            ast.parse(code)
        except (SyntaxError, ValueError) as exc:
            metrics["python_syntax_status"] = "invalid"
            result.update(error="PYTHON_SYNTAX_ERROR", detail=str(exc))
        else:
            if mode == "update" and version == 0:
                result["error"] = "NO_ACTIVE_SCENE"
            else:
                result.update(success=True, scene_version=version + 1,
                              note="Syntax accepted only. Code was NOT executed; no Blender scene exists.")
    elif name == "render_scene":
        result["error"] = "RENDER_UNAVAILABLE_API_ONLY"
    elif name == "inspect_scene":
        result["error"] = "INSPECT_UNAVAILABLE_API_ONLY"
    else:
        result.update(success=True, agent_finished=True,
                      note="Agent stopped. No Blender scene was constructed or rendered.")
    return result, metrics


def run(model, store, *, live=False, max_model_calls=4, context_policy="full", prompt_version="baseline"):
    if not 1 <= max_model_calls <= 4:
        raise ValueError("max_model_calls must be between 1 and 4")
    messages = [{"role": "system", "content": get_system_prompt(prompt_version)},
                {"role": "user", "content": [store.image(store.root / "input.png")]}]
    store.save_system_prompt(messages[0]["content"])
    rounds = []
    summary = {"model": model.model, "mock_model": model.is_mock, "simulated_tools": True,
               "context_policy": context_policy,
               "prompt_version": prompt_version, "effective_prompt_version": prompt_version,
               "status": "dry_run", "termination_reason": "live_not_authorized",
               "model_calls": 0, "api_calls": 0, "virtual_scene_version": 0,
               "python_executed": False, "blender_processes": 0, "runtime_status": "blocked",
               "reconstruction_success": False, "agent_finished": False,
               "cost_usd": None, "rounds": rounds}
    store.event("experiment_prepared", messages=messages, tools=TOOLS, tool_choice="auto",
                live=live, max_model_calls=max_model_calls, max_output_tokens=MAX_OUTPUT_TOKENS,
                api_timeout=API_TIMEOUT, retries=0)
    history_characters = history_bytes = 0
    for number in range(max_model_calls if live else 0):
        # A virtual scene is not Blender evidence: always supply no snapshot.
        request_messages, context_stats = build_model_context(messages, context_policy)
        folder = f"round_{number:02d}"
        directory = store.root / folder
        directory.mkdir()
        store.write(f"{folder}/tool_call.json", [])
        store.write(f"{folder}/simulated_result.json", {
            "simulated": True, "execution_status": "NOT_EXECUTED", "dispatched": False,
            "scene_version": summary["virtual_scene_version"], "scene_version_is_virtual": True})
        record = {"round": number, "message_count": len(messages),
                  **context_stats, "virtual_scene_version": summary["virtual_scene_version"],
                  "historical_code_characters": history_characters, "historical_code_bytes": history_bytes,
                  "tool_call_name": None, "mode": None, "code_length_bytes": None,
                  "code_length_characters": None, "code_lines": None,
                  "tool_call_status": "not_received", "python_syntax_status": "not_checked",
                  **token_counts(None)}
        rounds.append(record)
        summary.update(status="running", termination_reason=None)
        summary["model_calls"] += 1
        summary["api_calls"] += int(not model.is_mock)
        store.event("model_request", round=number, messages=request_messages, tools=TOOLS, context=context_stats,
                    tool_choice="auto", max_tokens=MAX_OUTPUT_TOKENS, **{
                        k: record[k] for k in ("message_count", "historical_code_characters", "historical_code_bytes")})
        store.write("summary.json", summary)
        started = time.monotonic()
        try:
            reply = model.complete(request_messages, TOOLS, API_TIMEOUT, "auto", max_tokens=MAX_OUTPUT_TOKENS)
        except Exception as exc:
            error = str(exc)
            for url, filename in store.images.items():
                error = error.replace(url, f"[image_file:{filename}]")
            record.update(api_latency_seconds=round(time.monotonic() - started, 3), error=error)
            record_context_stats(store, dict(context_stats, round=number), None, record["api_latency_seconds"])
            store.write(f"{folder}/model_response.json", {"status": "api_error", "error": error})
            store.event("api_error", **record)
            summary.update(status="api_error", termination_reason="request_failed_no_retry")
            break
        record.update(api_latency_seconds=round(time.monotonic() - started, 3),
                      usage=reply.get("usage"), **token_counts(reply.get("usage")))
        record_context_stats(store, dict(context_stats, round=number), reply.get("usage"), record["api_latency_seconds"])
        store.write(f"{folder}/model_response.json", reply)
        store.event("model_response", round=number, response=reply, latency=record["api_latency_seconds"])
        try:
            choice = reply["choices"][0]
            message = choice["message"]
            calls = message.get("tool_calls") or []
            record["finish_reason"] = choice.get("finish_reason")
            store.write(f"{folder}/tool_call.json", calls)
            if len(calls) == 1:
                record["tool_call_name"] = calls[0].get("function", {}).get("name")
            if record["finish_reason"] in ("length", "content_filter"):
                record["tool_call_status"] = "incomplete_response"
                summary.update(status="incomplete_response", termination_reason=record["finish_reason"])
                break
            if len(calls) != 1:
                raise ValueError("Expected exactly one native tool call")
            call = calls[0]
            if call.get("type") != "function" or not isinstance(call.get("id"), str) or not call["id"]:
                raise ValueError("Native function call requires a tool call ID")
            name = call["function"]["name"]
            schema = next((t["function"]["parameters"] for t in TOOLS if t["function"]["name"] == name), None)
            if schema is None:
                raise ValueError(f"Unknown tool: {name}")
            arguments = json.loads(call["function"]["arguments"])
            validate(arguments, schema)
        except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
            record.update(tool_call_status="invalid", error=exc.message if isinstance(exc, ValidationError) else str(exc))
            summary.update(status="protocol_error", termination_reason="invalid_tool_call")
            break
        result, metrics = dispatch(name, arguments, summary["virtual_scene_version"], directory)
        record.update(tool_call_status="valid", tool_call_id=call["id"], **metrics)
        record["simulated_result"] = result
        summary["virtual_scene_version"] = result["scene_version"]
        store.write(f"{folder}/simulated_result.json", result)
        store.event("simulated_tool_result", round=number, name=name, result=result, **metrics)
        messages.extend([message, {"role": "tool", "tool_call_id": call["id"], "name": name,
                                    "content": json.dumps(result)}])
        if name == "execute_blender":
            history_characters += len(arguments["code"])
            history_bytes += len(arguments["code"].encode("utf-8"))
        if name == "finish":
            summary.update(status="agent_finished_simulated", termination_reason="agent_finish", agent_finished=True)
            break
        summary.update(status="budget_exhausted", termination_reason="max_model_calls")
    for field in ("input_tokens", "output_tokens", "total_tokens"):
        values = [record[field] for record in rounds]
        summary[field] = sum(values) if values and all(value is not None for value in values) else None
    summary["api_latency_seconds"] = round(sum(r.get("api_latency_seconds", 0) for r in rounds), 3)
    store.event("termination", **summary)
    store.write("summary.json", summary)
    return store.clean(summary)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--model", default=os.environ.get("VLM_MODEL"))
    parser.add_argument("--api-base-url", default=os.environ.get("VLM_BASE_URL"))
    parser.add_argument("--max-model-calls", type=int, choices=range(1, 5), default=4)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--context-policy", choices=["full", "scene_state_recent"], default="full")
    parser.add_argument("--prompt-version", choices=PROMPT_VERSIONS, default="baseline")
    args = parser.parse_args()
    if not args.model:
        parser.error("Set VLM_MODEL or --model")
    if "/" not in args.model:
        args.model = "openai/" + args.model
    if args.live and os.environ.get("VLM_API_KEY"):
        os.environ["OPENAI_API_KEY"] = os.environ["VLM_API_KEY"]
    if args.live and not os.environ.get("OPENAI_API_KEY"):
        parser.error("Set VLM_API_KEY or OPENAI_API_KEY")
    config = {key: str(value) if isinstance(value, Path) else value for key, value in vars(args).items()}
    config.update(max_output_tokens=MAX_OUTPUT_TOKENS, api_timeout=API_TIMEOUT, api_retries=0,
                  simulated_tools=True, runtime_status="blocked")
    store = Storage(args.output, args.image, config)
    summary = run(ModelClient(args.model, args.api_base_url), store,
                  live=args.live, max_model_calls=args.max_model_calls, context_policy=args.context_policy,
                  prompt_version=args.prompt_version)
    print(json.dumps({"output": str(store.root), **summary}, indent=2, ensure_ascii=False))
    return 0 if summary["status"] in ("dry_run", "budget_exhausted", "agent_finished_simulated") else 1


if __name__ == "__main__":
    raise SystemExit(main())
