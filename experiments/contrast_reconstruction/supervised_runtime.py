"""Explicit assistant-reviewed adapter; isolated=False and no unattended entry."""
import json
from pathlib import Path
import shutil
import sys

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import manual_cpu_render as cpu
from e_harness.runtime.blender_runtime import BlenderRuntime


class SupervisedRuntime(BlenderRuntime):
    def __init__(self, root, approved_source=None):
        evidence = json.loads(cpu.CALIBRATION.read_text())
        if not evidence["success"] or len(evidence["cases"]) != 3:
            raise PermissionError("Trusted CPU calibration is required")
        root.mkdir(parents=True, exist_ok=True)
        super().__init__(root, cpu.BLENDER, resolution=(256, 256), samples=8, object_limit=100)
        self.approved_source = approved_source
        self.version = len(list(root.glob("scene_v*")))
        self.attempt = len(list(root.glob("attempts/execute_*")))
        self.render_count = len(list(root.glob("scene_v*/renders/*/job.json")))
        self.inspect_count = len(list(root.glob("scene_v*/inspection_*/job.json")))
        if self.current:
            self.scene_state = json.loads((self.current / "state.json").read_text())
            inputs = sorted(self.current.glob("renders/input_*.png"))
            self.input_render = inputs[-1] if inputs else None

    def process(self, job, directory, timeout, source=None):
        import gpu_profile
        directory.mkdir(parents=True, exist_ok=True)
        operation = job["operation"]
        uuid = None
        helper = ROOT / "e_harness/runtime/blender_entry.py"
        if operation == "execute":
            if self.approved_source is None or source != self.approved_source:
                raise PermissionError("No byte-identical assistant-reviewed submission")
            helper = ROOT / "scripts/world_initialized_blender.py"
            evidence = json.loads((ROOT / "runtime_evidence/world_initialization.json").read_text())
            if job["mode"] == "replace" and not evidence["success"]:
                raise PermissionError("World normalization trusted test has not passed")
            job.update(normalize_world=job["mode"] == "replace",
                       normalization_report=str(directory / "normalization.json"))
        elif operation == "render":
            helper = Path(__file__).with_name("render_blender.py")
            job["settings_helper"] = str(ROOT / "e_harness/runtime/blender_entry.py")
            ready = self.root.parent.parent / "gpu_ready.json"
            if ready.exists():
                evidence = json.loads(ready.read_text())
                if evidence["limits"] == gpu_profile.LIMITS:
                    candidate = gpu_profile.idle_device()
                    if candidate == evidence["gpu_uuid"]:
                        uuid = candidate
                        job["gpu_uuid"] = uuid
        result_path = directory / "result.json"
        job = dict(job, result=str(result_path))
        job_path = directory / "job.json"
        job_path.write_text(json.dumps(job, indent=2))
        process = gpu_profile.launch(directory, helper, job_path, uuid, source=source, label=operation)
        stats = cpu.statistics(directory)
        success = process["success"] and process["cleanup_complete"] and result_path.exists()
        log = Path(process["log"])
        shutil.copyfile(log, directory / "process.log")
        result = {"success": success, "seconds": process["seconds"], "returncode": process["returncode"],
            "log_path": str(log), "error": None if success else (process["error"] or "Missing result") + "\n" + log.read_text(errors="replace")[-4000:],
            "resources": {**stats, "peak_rss_bytes": process["peak_rss_bytes"], "cleanup_complete": process["cleanup_complete"]}}
        if success:
            result["data"] = json.loads(result_path.read_text())
        if not process["cleanup_complete"] or (process["error"] and any(word in process["error"] for word in ("Resource", "thread growth", "deadline", "Cleanup", "Output entry"))):
            batch = self.root.parent.parent
            (batch / "SAFETY_STOP.json").write_text(json.dumps(process, indent=2))
        return result
