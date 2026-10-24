"""One model response saved as data. No runtime, approval or execution dependency."""
import ast
import json
import time

from jsonschema import validate, ValidationError

from .model_client import token_counts
from .prompts import get_system_prompt
from .tools import TOOLS
from .context import build_model_context, record_context_stats


def generate_only(model, store, config):
    if config["mode"] != "single_shot" or not config.get("generation_only"):
        raise ValueError("Generation-only requires --generation-only --mode single_shot")
    summary = {"model": model.model, "mock": model.is_mock, "generation_only": True,
               "status": "dry_run", "termination_reason": "live_not_authorized",
               "model_calls": 0, "api_calls": 0, "api_latency_seconds": None,
               "usage": None, **token_counts(None), "tool_call_status": "not_requested",
               "python_syntax_status": "not_checked", "code_length_bytes": None,
               "code_length_characters": None, "cost_usd": None,
               "python_executed": False, "blender_processes": 0, "runtime_ready": False,
               "runtime_status": "blocked", "max_api_calls": 1, "retries": 0}
    messages = [{"role": "system", "content": get_system_prompt(config.get("prompt_version", "baseline"), "single_shot", config.get('benchmark_camera')) +
                 "\nSingle-shot generation only: submit one complete bpy program via execute_blender with mode=replace. "
                 "It will be saved, not executed. No revision."},
                {"role": "user", "content": [store.image(store.root / "input.png")]}]
    store.save_system_prompt(messages[0]["content"])
    summary.update(prompt_version=config.get("prompt_version", "baseline"), effective_prompt_version="baseline")
    choice = {"type": "function", "function": {"name": "execute_blender"}}
    messages, stats = build_model_context(messages, config.get("context_policy", "full"))
    summary["context_policy"] = stats["context_policy"]
    store.write("model_response.json", {"status": "not_requested"})
    store.event("generation_request_prepared", messages=messages, tools=TOOLS[:1], tool_choice=choice,
                max_tokens=config["max_output_tokens"], live=bool(config.get("live")))
    if model.is_mock or config.get("live"):
        timeout = min(config["api_timeout"], config["max_wall_time"])
        if timeout <= 0 or config["max_model_turns"] <= 0:
            summary.update(status="budget_exhausted", termination_reason="generation_request_budget")
        else:
            summary.update(model_calls=1, api_calls=0 if model.is_mock else 1)
            started = time.monotonic()
            try:
                reply = model.complete(messages, TOOLS[:1], timeout, choice, max_tokens=config["max_output_tokens"])
            except Exception as exc:
                summary["api_latency_seconds"] = round(time.monotonic() - started, 3)
                record_context_stats(store, stats, None, summary["api_latency_seconds"])
                error = str(exc)
                for url, filename in store.images.items():
                    error = error.replace(url, f"[image_file:{filename}]")
                summary.update(status="api_error", termination_reason="model_request_failed",
                               error=f"{type(exc).__name__}: {error}")
                store.write("model_response.json", {"status": "error", "error": summary["error"]})
            else:
                summary["api_latency_seconds"] = round(time.monotonic() - started, 3)
                record_context_stats(store, stats, reply.get("usage"), summary["api_latency_seconds"])
                store.write("model_response.json", reply)
                summary.update(usage=reply.get("usage"), response_model=reply.get("model"),
                               **token_counts(reply.get("usage")))
                try:
                    selected = reply["choices"][0]
                    summary["finish_reason"] = selected.get("finish_reason")
                    calls = selected["message"].get("tool_calls") or []
                    if len(calls) != 1:
                        raise ValueError("Expected exactly one execute_blender tool call")
                    call = calls[0]
                    if (call.get("type") != "function" or not isinstance(call.get("id"), str) or not call["id"]
                            or call["function"]["name"] != "execute_blender"):
                        raise ValueError("Expected a native execute_blender call with an ID")
                    arguments = json.loads(call["function"]["arguments"])
                    validate(arguments, TOOLS[0]["function"]["parameters"])
                    if arguments.get("mode", "replace") != "replace":
                        raise ValueError("Single-shot generation requires mode=replace")
                    code = arguments["code"]
                    source = code.encode("utf-8")
                    (store.root / "generated_scene.py").write_bytes(source)
                    summary.update(status="generated", termination_reason="code_saved_no_execution",
                                   tool_call_status="valid", tool_call_id=call["id"],
                                   code_length_bytes=len(source), code_length_characters=len(code))
                    try:
                        ast.parse(code)
                        summary["python_syntax_status"] = "valid"
                    except (SyntaxError, ValueError) as exc:
                        summary.update(status="syntax_error", termination_reason="saved_with_syntax_error",
                                       python_syntax_status="invalid", syntax_error=str(exc))
                except (KeyError, IndexError, TypeError, ValueError, ValidationError) as exc:
                    summary.update(status="protocol_error", termination_reason="invalid_tool_call",
                                   tool_call_status="invalid", error=str(exc))
                if summary.get("finish_reason") in ("length", "content_filter"):
                    summary.update(status="incomplete_response", termination_reason=summary["finish_reason"])
    store.event("generation_termination", **summary)
    store.write("summary.json", summary)
    return store.clean(summary)
