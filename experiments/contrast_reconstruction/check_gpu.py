"""One trusted Cube GPU render under the explicitly authorized memory profile."""
import fcntl
import json
from pathlib import Path
import signal
import tempfile

from run import BATCH, ROOT, read, write
import gpu_profile
from supervised_runtime import cpu


def main():
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    source = next(path for path in BATCH.glob("trusted_runtime_check_*/summary.json") if read(path).get("success"))
    scene = Path(read(source)["execute"]["blend_path"])
    folder = Path(tempfile.mkdtemp(prefix="trusted_gpu_", dir=BATCH))
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        uuid = gpu_profile.idle_device()
        if uuid is None:
            write(folder / "summary.json", {"success": False, "reason": "No idle permitted device or insufficient host memory"})
            return
        job = {"blend": str(scene), "gpu_uuid": uuid, "resolution": [256, 256], "samples": 8,
            "settings_helper": str(ROOT / "e_harness/runtime/blender_entry.py"),
            "image": str(folder / "render.png"), "result": str(folder / "result.json")}
        write(folder / "job.json", job)
        write(folder / "config.json", {"limits": gpu_profile.LIMITS, "gpu_uuid": uuid,
            "vram_headroom_MiB": 1024, "host_headroom_GiB": 32, "model_python": False, "api_calls": 0,
            "authorization": "User approved 32 GiB RSS, 1200 CPU seconds and 600 wall seconds; defaults unchanged"})
        result = gpu_profile.launch(folder, Path(__file__).with_name("render_blender.py"), folder / "job.json", uuid)
        result.update(cpu.statistics(folder), gpu_uuid=uuid)
        if result["success"]:
            result["render"] = read(folder / "result.json")
        write(folder / "summary.json", result)
        if result["success"] and result["cleanup_complete"]:
            write(BATCH / "gpu_ready.json", {"trusted_evidence": str(folder / "summary.json"), "gpu_uuid": uuid,
                                            "limits": gpu_profile.LIMITS, "formal_runtime_status": "blocked"})
        print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
