"""Run only the fixed trusted World fixture, never a model response or model API."""
import argparse
import fcntl
import json
from pathlib import Path
import time

from manual_reviewed_replay import BLENDER, LIMITS, ROOT, monitored_process, namespace_command, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.output.resolve()
    fixture = ROOT / "tests/fixtures/world_initialization.py"
    wrapper = ROOT / "scripts/world_initialized_blender.py"
    source = fixture.read_bytes()
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        write_json(root / "config.json", {"experiment": "environment_normalized_replay",
            "stage": "trusted_mock_validation_only", "fixture": str(fixture), "wrapper": str(wrapper),
            "limits": LIMITS, "model_api_calls": 0, "model_python_executed": False,
            "unattended_runtime": "blocked", "filesystem_isolation": False, "task_resource_quota": False})
        summary = {"experiment": "environment_normalized_replay", "stage": "trusted_mock_validation_only",
                   "model_python_executed": False, "api_calls": 0, "cases": [], "success": False}
        for name, enabled in (("default", False), ("world_initialized", True)):
            folder = root / name
            folder.mkdir()
            (folder / "fixture.py").write_bytes(source)
            job = {"operation": "execute", "mode": "replace", "code": str(folder / "fixture.py"),
                   "blend": str(folder / "scene.blend"), "result": str(folder / "result.json"),
                   "fixture_result": str(folder / "fixture_result.json"),
                   "normalization_report": str(folder / "normalization.json"),
                   "resolution": [256, 256], "samples": 8}
            if enabled:
                job["normalize_world"] = True
            write_json(folder / "job.json", job)
            command = namespace_command([str(BLENDER), "--background", "--factory-startup",
                "--disable-autoexec", "--threads", "2", "--python-exit-code", "1", "--python",
                str(wrapper), "--", str(folder / "job.json")])
            result = monitored_process(command, folder, root, source,
                                       time.monotonic() + LIMITS["step_seconds"], "execute")
            summary["cases"].append({"name": name, **result})
            write_json(root / "summary.json", summary)
            if not result["success"]:
                return 1
            normalized = json.loads((folder / "normalization.json").read_text())
            if not normalized["handlers_removed"]:
                raise RuntimeError("Normalization handlers were not removed")
        summary["success"] = True
        write_json(root / "summary.json", summary)
        print(json.dumps(summary, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
