"""Explicitly authorized continuation in a separate directory, with cumulative call limits."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil

import run as steps

SOURCE = steps.ROOT / "runs/contrast24_gpt6_sol_20261017"
OUTPUT = steps.ROOT / "runs/contrast_retry_20261018"
LIMITS = {"S3_01_B": (6, 2), "S3_02_B": (7, 1)}
local_history = steps.history


def prepare():
    for image_id, (previous_calls, allowance) in LIMITS.items():
        source = SOURCE / image_id
        target = OUTPUT / image_id
        runtime = target / "runtime"
        runtime.mkdir(parents=True, exist_ok=False)
        for scene in sorted((source / "runtime").glob("scene_v*")):
            shutil.copytree(scene, runtime / scene.name)
        shutil.copyfile(source / "merge_groups.json", target / "merge_groups.json")
        context = {"source": str(source.relative_to(steps.ROOT)), "previous_api_calls": previous_calls,
                   "max_new_api_calls": allowance, "previous_failure": steps.read(source / "termination.json")}
        if image_id == "S3_01_B":
            failed = source / "round_05"
            error = steps.read(failed / "summary.json")["error"]
            context["tool_result"] = {"success": False, "executed": False, "scene_version": 2,
                "error_type": "SyntaxError", "error": error,
                "source_line": (failed / "code.py").read_text().splitlines()[46]}
            context["feedback_source"] = "Original saved parser error; no code executed or repaired"
        else:
            context["feedback_source"] = "The timeout had no model response; resume only the preceding complete conversation"
        steps.write(target / "recovery_context.json", context)


def history(store, image_root):
    messages = local_history(store, image_root)
    inherited = []
    source = SOURCE / image_root.name
    context = steps.read(image_root / "recovery_context.json")
    for folder in sorted(source.glob("round_*")):
        summary = steps.read(folder / "summary.json")
        if summary["status"] == "syntax_error":
            result = context["tool_result"]
        elif summary["status"] == "valid_tool_call":
            result = steps.read(folder / "tool_result.json")
        else:
            break
        message = steps.read(folder / "model_response.json")["choices"][0]["message"]
        call = message["tool_calls"][0]
        inherited.extend([message, {"role": "tool", "tool_call_id": call["id"],
            "name": call["function"]["name"], "content": json.dumps(result)}])
        if result.get("success") and result.get("render_path"):
            original = Path(result["render_path"])
            target = store.root / ("source_" + folder.name + "_feedback.png")
            shutil.copyfile(original, target)
            inherited.append({"role": "user", "content": [
                {"type": "text", "text": f"Your scene {result['scene_version']}, {call['function']['name']} image:"},
                store.image(target)]})
    return messages[:2] + inherited + messages[2:]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare", action="store_true")
    parser.add_argument("--image", choices=LIMITS)
    action = parser.add_mutually_exclusive_group()
    action.add_argument("--request", action="store_true")
    action.add_argument("--apply", action="store_true")
    action.add_argument("--export", action="store_true")
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--review-note")
    args = parser.parse_args()
    steps.BATCH = OUTPUT
    if args.prepare:
        prepare()
        return
    if args.image is None:
        parser.error("--image is required")
    if args.request:
        if not args.live:
            parser.error("A real request requires --live")
        previous, allowance = LIMITS[args.image]
        rounds = list((OUTPUT / args.image).glob("round_*"))
        if len(rounds) >= allowance or previous + len(rounds) >= 8:
            raise ValueError("Cumulative per-image request allowance exhausted")
        steps.history = history
        with (OUTPUT / ".api.lock").open("a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            steps.request(args.image)
    elif args.apply:
        steps.apply(args.image, args.review_note)
    elif args.export:
        steps.export(args.image, OUTPUT / args.image / "merge_groups.json")
    else:
        parser.error("Choose --request, --apply or --export")


if __name__ == "__main__":
    main()
