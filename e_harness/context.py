"""Deterministic scene memory and paired-history selection; no model summarizer."""
import json
import math

from .model_client import token_counts


def equivalent(a, b):
    if isinstance(a, (int, float)) and isinstance(b, (int, float)):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-5)
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(equivalent(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(equivalent(x, y) for x, y in zip(a, b))
    return a == b


def scene_diff(previous, current):
    previous = previous or {"objects": []}
    before = {o["name"]: o for o in previous["objects"]}
    after = {o["name"]: o for o in current["objects"]}
    modified = []
    for name in sorted(before.keys() & after.keys()):
        materials = after[name]["materials"]
        if (not equivalent(before[name], after[name]) or any(
                not equivalent(previous.get("materials", {}).get(m), current.get("materials", {}).get(m))
                for m in materials)):
            modified.append(name)
    return {"added": sorted(after.keys() - before.keys()), "removed": sorted(before.keys() - after.keys()),
            "modified": modified}


def compact(value):
    if isinstance(value, float):
        return round(value, 5)
    if isinstance(value, dict):
        return {k: compact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [compact(v) for v in value]
    return value


def recent_context(messages, state):
    # The controller issues one call per response. Unknown/pending shapes fall back intact.
    groups = []
    i = 2
    while i < len(messages):
        start = i
        calls = messages[i].get("tool_calls") or []
        if len(calls) != 1 or i + 1 >= len(messages):
            return messages, "incomplete_or_unsupported_history"
        call, reply = calls[0], messages[i + 1]
        if reply.get("role") != "tool" or reply.get("tool_call_id") != call.get("id"):
            return messages, "incomplete_or_unsupported_history"
        result = json.loads(reply["content"])
        i += 2
        while i < len(messages) and messages[i]["role"] == "user":
            i += 1
        groups.append((messages[start:i], call["function"]["name"], result))
    committed = [i for i, (_, name, r) in enumerate(groups) if name == "execute_blender"
                 and r.get("success") and not r.get("simulated") and r.get("scene_version") == state["scene_version"]]
    if not committed:
        return messages, "snapshot_has_no_matching_commit"
    cutoff = committed[-1]
    renders = [i for i, (group, _, r) in enumerate(groups) if r.get("success")
               and r.get("render_path") and any(m["role"] == "user" for m in group)]
    latest_render = renders[-1] if renders else None
    unresolved = {}
    for index, (_, name, result) in enumerate(groups):
        if result.get("success"):
            unresolved.pop(name, None)
        else:
            unresolved[name] = index
    fields = ["name", "type", "location", "rotation", "dimensions", "materials", "parent", "collections", "light"]
    memory_state = dict(state, object_fields=fields, objects=[[obj.get(k) for k in fields] for obj in state["objects"]])
    memory = "CURRENT SCENE MEMORY (from saved Blender data)\n" + json.dumps(compact(memory_state),
        ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    memory += "\nPython local variables/functions do not persist. Render feedback keeps its original scene version."
    selected = messages[:2] + [{"role": "user", "content": memory}]
    for index, (group, _, _) in enumerate(groups):
        if index == latest_render or index in unresolved.values() or (index > cutoff and index not in renders):
            selected.extend(group)
    return selected, None


def build_model_context(messages, policy="full", state=None, scene_version=0):
    selected, reason = messages, None
    effective = "full"
    if policy == "scene_state_recent":
        if not state or state.get("source") != "saved_blend" or state.get("scene_version") != scene_version:
            reason = "no_current_scene_snapshot"
        else:
            selected, reason = recent_context(messages, state)
            if reason is None:
                effective = policy
    code_bytes = 0
    for message in selected:
        for call in message.get("tool_calls") or []:
            if call["function"]["name"] == "execute_blender":
                raw = call["function"]["arguments"]
                try:
                    code = json.loads(raw).get("code", "")
                except (ValueError, AttributeError):
                    code = raw
                if isinstance(code, str):
                    code_bytes += len(code.encode("utf-8"))
    memory_bytes = len(selected[2]["content"].encode("utf-8")) if effective == "scene_state_recent" else 0
    text_view = [{**m, "content": [p if p.get("type") != "image_url" else {"type": "image_url"}
                                  for p in m["content"]]} if isinstance(m.get("content"), list) else m for m in selected]
    stats = {"context_policy": policy, "effective_context_policy": effective, "fallback_reason": reason,
             "message_count": len(selected), "historical_code_bytes": code_bytes,
             "scene_memory_bytes": memory_bytes, "scene_version": scene_version,
             "text_bytes": len(json.dumps(text_view, ensure_ascii=False).encode("utf-8")),
             "message_bytes": len(json.dumps(selected, ensure_ascii=False).encode("utf-8"))}
    return selected, stats


def record_context_stats(store, stats, usage, latency):
    record = {**stats, **token_counts(usage), "api_latency_seconds": latency}
    with (store.root / "context_stats.jsonl").open("a") as stream:
        stream.write(json.dumps(store.clean(record), ensure_ascii=False) + "\n")
