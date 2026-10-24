"""Opt-in supervised CPU profile: three trusted tests or one approved blend render."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import time

from manual_reviewed_replay import (BLENDER, LIMITS, ROOT, child_environment, event,
    monitored_process, namespace_command, terminal_decision, write_json)

PROCESS_LIMIT = 4
CALIBRATION = ROOT / "runtime_evidence/cpu_calibration.json"


def environment(folder):
    env = child_environment(folder)
    config = Path(env["XDG_CONFIG_HOME"]) / "user-dirs.dirs"
    config.write_text('XDG_DOCUMENTS_DIR="$HOME"\nXDG_DESKTOP_DIR="$HOME"\n'
                      'XDG_DOWNLOAD_DIR="$HOME"\nXDG_MUSIC_DIR="$HOME"\n'
                      'XDG_PICTURES_DIR="$HOME"\nXDG_PUBLICSHARE_DIR="$HOME"\n'
                      'XDG_TEMPLATES_DIR="$HOME"\nXDG_VIDEOS_DIR="$HOME"\n')
    env["OPENIMAGEIO_THREADS"] = "2"
    return env


def launch(folder, root, script, job=None, *, source=None, deadline=None, label="render"):
    command = namespace_command([str(BLENDER), "--background", "--factory-startup",
        "--disable-autoexec", "--threads", "2", "--python-exit-code", "1", "--python", str(script)])
    if job is not None:
        command += ["--", str(job)]
    return monitored_process(command, folder, root, source,
        time.monotonic() + 120 if deadline is None else deadline,
        label, thread_details=True, extra_env=environment(folder), sample_seconds=0.02,
        process_limit=PROCESS_LIMIT)


def statistics(folder):
    rows = [json.loads(s) for s in (folder / "resources.jsonl").read_text().splitlines()]
    return {"sampled_peak_processes": max((len(r["processes"]) for r in rows), default=0),
        "sampled_peak_threads": max((sum(p["threads"] for p in r["processes"]) for r in rows), default=0),
        "sampled_max_cpu_seconds": max((r["cpu_seconds"] for r in rows), default=0),
        "all_sampled_threads_within_affinity": all(set(t["allowed_cpus"]) <= set(sorted(os.sched_getaffinity(0))[:2])
            for r in rows for p in r["processes"] for t in p.get("thread_details", []))}


def prepare(root, blend=None):
    if blend is not None:
        evidence = json.loads(CALIBRATION.read_text())
        if not evidence["success"] or len(evidence["cases"]) != 3:
            raise ValueError("Three consecutive trusted renders must pass first")
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    write_json(root / "config.json", {"profile": "manual_supervised_cpu",
        "limits": {**LIMITS, "processes_stop": PROCESS_LIMIT, "sample_seconds": 0.02},
        "environment": {"OPENIMAGEIO_THREADS": "2", "isolated_xdg_config": True},
        "affinity": sorted(os.sched_getaffinity(0))[:2], "api_calls": 0,
        "unattended_runtime": "blocked", "task_quota": False, "filesystem_isolation": False,
        "source_blend": str(blend) if blend else None, "calibration": str(CALIBRATION) if blend else None})
    if blend is not None:
        (root / "input.blend").write_bytes(blend.read_bytes())
        (root / "render_helper.py").write_bytes((ROOT / "scripts/cpu_render_blender.py").read_bytes())
        (root / "settings_helper.py").write_bytes((ROOT / "e_harness/runtime/blender_entry.py").read_bytes())
        write_json(root / "job.json", {"blend": str(root / "input.blend"), "resolution": [256, 256],
            "samples": 8, "image": str(root / "render.png"), "result": str(root / "render_data.json"),
            "settings_helper": str(root / "settings_helper.py")})
        event(root, "prepared", blend_loaded=False, approval="pending")


def calibrate(root):
    prepare(root)
    summary = {"success": False, "cases": [], "unattended_runtime": "blocked", "api_calls": 0}
    for number in range(1, 4):
        folder = root / f"test_{number:02d}"
        folder.mkdir()
        script = folder / "fixture.py"
        script.write_bytes((ROOT / "tests/fixtures/cpu_render.py").read_bytes())
        result = launch(folder, root, script)
        result.update(statistics(folder))
        if result["success"]:
            fixture = json.loads((folder / "fixture_result.json").read_text())
            result["render_seconds"] = fixture["render_seconds"]
            result["success"] = (folder / "render.png").is_file() and result["all_sampled_threads_within_affinity"]
        summary["cases"].append(result)
        write_json(root / "summary.json", summary)
        if not result["success"] or not result["cleanup_complete"]:
            return summary
    summary["success"] = True
    write_json(root / "summary.json", summary)
    return summary


def execute(root):
    if (root / "approval.json").exists():
        raise ValueError("An approval decision already exists; no retries or overwrite")
    config = json.loads((root / "config.json").read_text())
    if config["limits"] != {**LIMITS, "processes_stop": PROCESS_LIMIT, "sample_seconds": 0.02}:
        raise ValueError("Prepared limits changed")
    artifacts = {name: (root / name).read_bytes()
                 for name in ("input.blend", "render_helper.py", "settings_helper.py", "job.json")}
    if artifacts["input.blend"] != Path(config["source_blend"]).read_bytes():
        raise ValueError("Prepared scene differs from the source")
    print(f"Review {root / 'input.blend'} and {root / 'render_helper.py'}\n"
          "One CPU render only: 256x256, 8 samples, 2 cores/threads, 120s, process limit 4.\n"
          "No model Python rerun. Autoexec disabled; native parsing/external references remain risks.\n"
          "No filesystem sandbox or task quota; formal Runtime stays blocked.", flush=True)
    event(root, "approval_requested", scope="one independent CPU render")
    decision = terminal_decision("render_round_00", LIMITS["approval_seconds"])
    if decision == "approved" and any((root / name).read_bytes() != value for name, value in artifacts.items()):
        decision = "artifact_changed"
    record = {"approved": decision == "approved", "decision": decision, "time": time.time()}
    write_json(root / "approval.json", record)
    event(root, "approval_decision", **record)
    if not record["approved"]:
        return {"success": False, "executed": False, "decision": decision}
    result = launch(root, root, root / "render_helper.py", root / "job.json")
    result.update(statistics(root))
    write_json(root / "summary.json", result)
    event(root, "render_finished", **result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--test-three", action="store_true")
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--blend", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    if args.prepare != (args.blend is not None):
        parser.error("--blend is required only with --prepare")
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = args.output.resolve()
        if args.prepare:
            prepare(root, args.blend.resolve())
            print(f"Prepared only: {root}; no Blender started; approval pending.")
            return 0
        result = calibrate(root) if args.test_three else execute(root)
        print(json.dumps(result, indent=2))
        return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
