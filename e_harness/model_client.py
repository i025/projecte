"""Provider-neutral messages via LiteLLM; deterministic replay for offline tests."""
import copy
import json
import os


class ModelClient:
    is_mock = False

    def __init__(self, model, api_base_url=None):
        self.model, self.api_base_url = model, api_base_url

    def complete(self, messages, tools, timeout, tool_choice="auto", *, max_tokens=None):
        os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
        import litellm
        # Unknown custom routes are left to the provider; never substitute a text parser.
        try:
            metadata = litellm.get_model_info(self.model)
        except Exception:
            metadata = {}
        for feature in ("supports_function_calling", "supports_vision"):
            if metadata.get(feature) is False:
                raise ValueError(f"Incompatible model: {feature}=False")
        observed = {}

        def observe(details):
            if details.get("log_event_type") != "post_api_call":
                return
            raw = details.get("original_response")
            if isinstance(raw, str):
                try:
                    raw = json.loads(raw)
                except ValueError:
                    return
            if isinstance(raw, dict):
                observed["usage"] = raw.get("usage", raw.get("usageMetadata"))

        response = litellm.completion(model=self.model, messages=messages, tools=tools,
            tool_choice=tool_choice, api_base=self.api_base_url, timeout=timeout,
            num_retries=0, max_retries=0, logger_fn=observe,
            **({"max_tokens": max_tokens} if max_tokens is not None else {}))
        result = response.model_dump()
        # LiteLLM can synthesize usage. Record only observed provider usage here.
        result["usage"] = observed.get("usage")
        return result


def token_counts(usage):
    """Normalize reported counters only; never infer missing usage."""
    usage = usage or {}
    def field(*names):
        return next((usage[n] for n in names if usage.get(n) is not None), None)
    return {"input_tokens": field("prompt_tokens", "input_tokens", "promptTokenCount"),
            "output_tokens": field("completion_tokens", "output_tokens", "candidatesTokenCount"),
            "total_tokens": field("total_tokens", "totalTokenCount")}


def response(name, arguments, index=0):
    return {"id": f"mock_{index}", "model": "mock", "usage": None,
        "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
            "tool_calls": [{"id": f"tool_{index}", "type": "function", "function": {
                "name": name, "arguments": json.dumps(arguments)}}]}}]}


class MockModel:
    is_mock = True
    model = "mock"

    def __init__(self, calls):
        self.calls = iter(calls)
        self.requests = []

    def complete(self, messages, tools, timeout, tool_choice="auto", *, max_tokens=None):
        # A real JSON serialization boundary: tests decode images from these bytes.
        wire = json.dumps({"model": self.model, "messages": messages, "tools": tools,
                           "tool_choice": tool_choice, "max_tokens": max_tokens}).encode()
        self.requests.append(wire)
        call = next(self.calls)
        if isinstance(call, Exception):
            raise call
        if isinstance(call, dict):
            return copy.deepcopy(call)
        return response(*call, index=len(self.requests))
