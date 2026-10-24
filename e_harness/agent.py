import json
import time

from jsonschema import validate, ValidationError

from .prompts import get_system_prompt
from .tools import TOOLS
from .approval import ManualApproval
from .context import build_model_context, record_context_stats


class BudgetExhausted(Exception):
    pass


class Agent:
    def __init__(self, model, runtime, store, config):
        self.model, self.runtime, self.store, self.config = model, runtime, store, config
        self.started = time.monotonic()
        self.counts = dict.fromkeys(("model_turns", "api_calls", "tool_calls", "blender_executions",
                                    "render_calls", "successful_renders", "inspect_calls"), 0)
        self.limits = {"model_turns": config["max_model_turns"], "tool_calls": config["max_total_tool_calls"],
                      "blender_executions": config["max_executions"], "render_calls": config["max_renders"],
                      "inspect_calls": config["max_inspects"]}
        self.messages = [{"role": "system", "content": get_system_prompt(config.get("prompt_version", "baseline"), config["mode"], config.get('benchmark_camera'))},
                         {"role": "user", "content": [store.image(store.root / "input.png")]}]
        if config["mode"] == "single_shot":
            self.messages[0]["content"] += "\nSingle-shot: submit exactly one complete program via execute_blender with mode=replace. No revision."
        store.save_system_prompt(self.messages[0]["content"])
        self.status = None
        self.reason = None
        self.usages = []
        self.approval = ManualApproval(store) if config.get("manual_approval") else None

    def remaining(self):
        remaining = self.config["max_wall_time"] - (time.monotonic() - self.started)
        if remaining <= 0:
            raise BudgetExhausted("max_wall_time")
        return remaining

    def take(self, counter):
        self.remaining()
        if self.counts[counter] >= self.limits[counter]:
            raise BudgetExhausted(counter)
        self.counts[counter] += 1

    def request(self):
        self.take("model_turns")
        tools = TOOLS[:1] if self.config["mode"] == "single_shot" else TOOLS
        choice = {"type": "function", "function": {"name": "execute_blender"}} if len(tools) == 1 else "auto"
        messages, stats = build_model_context(self.messages, self.config.get("context_policy", "full"),
                                             getattr(self.runtime, "scene_state", None), self.runtime.version)
        for attempt in range(self.config["api_retries"] + 1):
            timeout = min(self.config["api_timeout"], self.remaining())
            self.counts["api_calls"] += 1
            self.store.event("model_request", model=self.model.model, attempt=attempt,
                             messages=messages, tools=tools, tool_choice=choice, timeout=timeout, context=stats)
            start = time.monotonic()
            try:
                reply = self.model.complete(messages, tools, timeout, choice)
            except Exception as exc:
                record_context_stats(self.store, dict(stats, api_call=self.counts["api_calls"]), None, time.monotonic() - start)
                self.store.event("api_error", error=str(exc), latency=time.monotonic() - start)
                if attempt == self.config["api_retries"]:
                    raise
                continue
            self.usages.append(reply.get("usage"))
            record_context_stats(self.store, dict(stats, api_call=self.counts["api_calls"]), reply.get("usage"), time.monotonic() - start)
            self.store.event("model_response", response=reply, latency=time.monotonic() - start)
            self.remaining()
            return reply

    def render(self, arguments, origin="agent"):
        self.take("render_calls")
        result = self.runtime.render(timeout=min(self.config["render_timeout"], self.remaining()), **arguments)
        if result["success"]:
            self.counts["successful_renders"] += 1
        self.store.event("render", origin=origin, result=result)
        return result

    def finish(self, origin="agent"):
        if not self.runtime.current:
            return {"success": False, "error": "Cannot finish without a successful scene"}
        if not self.runtime.input_render:
            result = self.render({"view": "input"}, origin=origin)
            if not result["success"]:
                return result
        self.remaining()
        self.runtime.export()
        self.status, self.reason = "completed", "agent_finish" if origin == "agent" else "single_shot_complete"
        return {"success": True, "scene_version": self.runtime.version,
                "blend_path": str(self.store.root / "final.blend"), "render_path": str(self.store.root / "final.png")}

    def dispatch(self, name, arguments, tool_call_id=None):
        schema = next((t["function"] for t in TOOLS if t["function"]["name"] == name), None)
        if schema is None:
            return {"success": False, "error": f"Unknown tool: {name}"}
        try:
            validate(arguments, schema["parameters"])
        except ValidationError as exc:
            return {"success": False, "error": exc.message}
        if name == "execute_blender":
            mode = arguments.get("mode", "replace")
            if self.config["mode"] == "single_shot" and mode != "replace":
                return {"success": False, "error": "single_shot requires mode=replace"}
            if self.approval:
                self.remaining()
                if self.counts["blender_executions"] >= self.limits["blender_executions"]:
                    raise BudgetExhausted("blender_executions")
                decision = self.approval.request(arguments["code"],
                    timeout=min(self.config["approval_timeout"], self.remaining()),
                    tool_call_id=tool_call_id, scene_version=self.runtime.version,
                    execution={"runtime": type(self.runtime).__name__, "isolated": self.runtime.isolated,
                               "blender_timeout": self.config["blender_timeout"], "mode": self.config["mode"],
                               "scene_mode": mode})
                if not decision["approved"]:
                    self.status, self.reason = "rejected", "manual_approval_" + decision["decision"]
                    return {"success": False, "executed": False, "approval": decision}
            self.take("blender_executions")
            return self.runtime.execute(arguments["code"], min(self.config["blender_timeout"], self.remaining()), mode=mode)
        if name == "render_scene":
            return self.render(arguments)
        if name == "inspect_scene":
            self.take("inspect_calls")
            return self.runtime.inspect(min(self.config["blender_timeout"], self.remaining()))
        return self.finish()

    def run(self):
        try:
            if not self.model.is_mock and not self.runtime.isolated:
                self.status = "blocked"
                raise PermissionError("Real model execution requires a verified isolated runtime; no API call was made")
            if not self.model.is_mock and self.approval is None:
                self.status = "blocked"
                raise PermissionError("Real model execution requires manual approval; no API call was made")
            while self.status is None:
                reply = self.request()
                message = reply["choices"][0]["message"]
                calls = message.get("tool_calls") or []
                if len(calls) != 1:
                    self.status, self.reason = "protocol_error", "Expected exactly one native tool call; no text fallback"
                    break
                call = calls[0]
                name = call["function"]["name"]
                if self.config["mode"] == "single_shot" and name != "execute_blender":
                    self.status, self.reason = "protocol_error", "single_shot requires execute_blender"
                    break
                self.messages.append(message)
                self.store.event("tool_call", name=name, arguments=call["function"]["arguments"],
                                 scene_version=self.runtime.version)
                self.take("tool_calls")
                try:
                    arguments = json.loads(call["function"]["arguments"])
                    result = self.dispatch(name, arguments, tool_call_id=call["id"])
                except (json.JSONDecodeError, TypeError) as exc:
                    result = {"success": False, "error": str(exc)}
                self.store.event("tool_result", name=name, result=result, scene_version=self.runtime.version)
                self.messages.append({"role": "tool", "tool_call_id": call["id"], "name": name,
                                      "content": json.dumps(result)})
                if result.get("success") and result.get("render_path"):
                    self.messages.append({"role": "user", "content": [
                        {"type": "text", "text": f"Your scene {self.runtime.version}, {name} image:"},
                        self.store.image(result["render_path"])]})
                    self.store.event("image_feedback", scene_version=self.runtime.version, image=result["render_path"])
                if self.status is not None:
                    break
                self.remaining()
                if self.config["mode"] == "single_shot":
                    if result["success"]:
                        final = self.finish(origin="single_shot")
                        self.store.event("finalize", result=final)
                        if not final["success"]:
                            self.status, self.reason = "failed", "single_shot_final_render_failed"
                    else:
                        self.status, self.reason = "failed", "single_shot_execution_failed"
        except BudgetExhausted as exc:
            self.status, self.reason = "budget_exhausted", str(exc)
            self.store.event("budget_exhausted", reason=self.reason)
        except Exception as exc:
            self.status = self.status or "failed"
            self.reason = f"{type(exc).__name__}: {exc}"
            self.store.event("error", error=self.reason)
        finally:
            # No extra execution or render after stopping; preserve only the current state.
            self.runtime.export()
            summary = {"status": self.status, "termination_reason": self.reason,
                "model": self.model.model, "mode": self.config["mode"], "mock": self.model.is_mock,
                "context_policy": self.config.get("context_policy", "full"),
                "prompt_version": self.config.get("prompt_version", "baseline"),
                "effective_prompt_version": self.config.get("prompt_version", "baseline") if self.config["mode"] == "tool_agent" else "baseline",
                "counts": self.counts, "scene_version": self.runtime.version,
                "wall_seconds": round(time.monotonic() - self.started, 3), "usage": self.usages,
                "cost_usd": 0 if self.model.is_mock else None,
                "final_blend": "final.blend" if self.runtime.current else None,
                "final_render": "final.png" if self.runtime.input_render else None,
                "isolated_runtime": self.runtime.isolated, "manual_approval": self.approval is not None}
            self.store.event("termination", **summary)
            self.store.write("summary.json", summary)
        return self.store.clean(summary)
