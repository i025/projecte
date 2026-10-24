"""Read-only diagnostic image; not an Agent observation or scene revision."""
import argparse
import fcntl
from pathlib import Path
import tempfile

from PIL import Image

from run import BATCH, ROOT, write
from supervised_runtime import SupervisedRuntime


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", required=True)
    args = parser.parse_args()
    if (BATCH / "SAFETY_STOP.json").exists():
        raise PermissionError("Safety stop active")
    runtime = SupervisedRuntime(BATCH / args.image / "runtime")
    if not runtime.current:
        raise ValueError("No saved scene")
    source = runtime.current / "scene.blend"
    before = source.read_bytes()
    reference = BATCH / args.image / "round_00/input.png"
    with Image.open(reference) as image:
        width, height = image.size
    resolution = [round(width * 512 / max(width, height)), round(height * 512 / max(width, height))]
    folder = Path(tempfile.mkdtemp(prefix="diagnostic_", dir=BATCH / args.image))
    job = {"operation": "render", "blend": str(source), "view": "input",
           "image": str(folder / "render.png"), "resolution": resolution,
           "samples": 64, "diagnostic_denoising": True}
    write(folder / "config.json", {**job, "source_scene_version": runtime.version,
          "reference_resolution": [width, height], "source_bytes": len(before),
          "agent_feedback": False, "api_calls": 0, "model_code_executed": False,
          "formal_runtime_status": "blocked"})
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        result = runtime.process(job, folder, 600)
    unchanged = before == source.read_bytes()
    write(folder / "summary.json", {**result, "source_unchanged": unchanged,
          "agent_feedback": False, "api_calls": 0, "model_code_executed": False})
    print(folder, "success:", result["success"], "source unchanged:", unchanged)
    if not result["success"] or not unchanged:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
