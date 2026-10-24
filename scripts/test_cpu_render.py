"""One bounded trusted fixture render; never accepts model code or a blend input."""
import argparse
import fcntl
import json
import os
from pathlib import Path
import signal
import time

from manual_reviewed_replay import BLENDER, LIMITS, ROOT, monitored_process, namespace_command, write_json


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--oiio-threads", type=int, choices=(1, 2))
    args = parser.parse_args()
    root = args.output.resolve()
    fixture = ROOT / "tests/fixtures/cpu_render.py"
    extra = {} if args.oiio_threads is None else {"OPENIMAGEIO_THREADS": str(args.oiio_threads)}
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root.mkdir(parents=True, exist_ok=False, mode=0o700)
        (root / "fixture.py").write_bytes(fixture.read_bytes())
        write_json(root / "config.json", {"experiment": "trusted_cpu_thread_diagnosis",
            "limits": LIMITS, "sample_seconds": 0.05, "extra_env": extra,
            "allowed_cpus": sorted(os.sched_getaffinity(0))[:2], "fixture": str(fixture),
            "api_calls": 0, "model_scene_loaded": False, "unattended_runtime": "blocked"})
        command = namespace_command([str(BLENDER), "--background", "--factory-startup",
            "--disable-autoexec", "--threads", "2", "--python-exit-code", "1",
            "--python", str(root / "fixture.py")])
        result = monitored_process(command, root, root, None,
            time.monotonic() + 120, "render", thread_details=True,
            extra_env=extra, sample_seconds=0.05)
        write_json(root / "summary.json", result)
        print(json.dumps(result, indent=2))
        return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
