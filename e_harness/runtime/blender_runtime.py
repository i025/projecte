"""Local runtime for reviewed mock fixtures ONLY, not a security sandbox."""
import json
import os
from pathlib import Path
import shutil
import signal
import subprocess
import time

from ..context import scene_diff


class BlenderRuntime:
    isolated = False

    def __init__(self, root, blender, *, trusted_mock=False, resolution=(320, 240), samples=16, object_limit=100, benchmark_camera=None):
        self.root, self.blender = Path(root), str(blender)
        self.trusted_mock = trusted_mock
        self.resolution, self.samples, self.object_limit = resolution, samples, object_limit
        self.version = 0
        self.attempt = 0
        self.render_count = 0
        self.inspect_count = 0
        self.input_render = None
        self.scene_state = None
        self.benchmark_camera = benchmark_camera

    @property
    def current(self):
        return self.root / f"scene_v{self.version:03d}" if self.version else None

    def process(self, job, directory, timeout, source=None):
        if not self.trusted_mock:
            raise PermissionError("Local runtime accepts reviewed mock fixtures only; an isolated runtime is required")
        directory.mkdir(parents=True, exist_ok=True)
        result_path = directory / "result.json"
        job = dict(job, result=str(result_path))
        if self.benchmark_camera:
            job['benchmark_camera'] = dict(self.benchmark_camera, resolution=list(self.resolution), samples=self.samples)
        job_path = directory / "job.json"
        job_path.write_text(json.dumps(job, indent=2))
        command = [self.blender, "--background", "--factory-startup", "--disable-autoexec", "--threads", "2",
                   "--python-exit-code", "1", "--python", str(Path(__file__).with_name("blender_entry.py")),
                   "--", str(job_path)]
        env = {"PATH": os.defpath, "LANG": "C.UTF-8", "CUDA_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2"}
        start = time.monotonic()
        try:
            proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    env=env, cwd=directory, start_new_session=True)
            try:
                stdout, stderr = proc.communicate(input=source, timeout=timeout)
                code = proc.returncode
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, stderr = proc.communicate()
                stderr += f"\nTimed out after {timeout:.3f}s".encode()
                code = 124
            stdout, stderr = stdout.decode("utf-8", errors="replace"), stderr.decode("utf-8", errors="replace")
        except OSError as exc:
            code, stdout, stderr = -1, "", str(exc)
        elapsed = time.monotonic() - start
        log = directory / "process.log"
        log.write_text(json.dumps(command) + f"\nexit={code}\nSTDOUT\n{stdout}\nSTDERR\n{stderr}")
        success = code == 0 and result_path.exists()
        result = {"success": success, "seconds": round(elapsed, 3), "log_path": str(log),
                  "returncode": code, "error": None if success else (stderr + stdout)[-4000:] or "Missing execution result"}
        if success:
            result["data"] = json.loads(result_path.read_text())
        return result

    def execute(self, code, timeout, mode="replace"):
        self.attempt += 1
        directory = self.root / "attempts" / f"execute_{self.attempt:03d}"
        directory.mkdir(parents=True)
        source = code.encode("utf-8")
        (directory / "scene.py").write_bytes(source)
        blend = directory / "scene.blend"
        base_version = self.version if mode == "update" and self.current else None
        job = {"operation": "execute", "mode": mode, "code": str(directory / "scene.py"),
               "blend": str(blend), "samples": self.samples, "resolution": self.resolution}
        if mode == "update" and not self.current:
            log = directory / "process.log"
            log.write_text("NO_ACTIVE_SCENE: update requires a successful scene; no process started.\n")
            result = {"success": False, "error": "NO_ACTIVE_SCENE", "seconds": 0,
                      "log_path": str(log), "returncode": None}
        else:
            if mode == "update":
                # Work on a copy so even save_mainfile cannot overwrite the committed base.
                base = directory / "base.blend"
                shutil.copyfile(self.current / "scene.blend", base)
                job["base_blend"] = str(base)
            result = self.process(job, directory, timeout, source=source)
        (directory / "scene.py").write_bytes(source)
        if result["success"]:
            target = self.root / f"scene_v{self.version + 1:03d}"
            target.mkdir()
            (target / "scene.py").write_bytes(source)
            shutil.copyfile(blend, target / "scene.blend")
            shutil.copyfile(directory / "process.log", target / "execute.log")
            state = result["data"].pop("scene_state")
            state.update(scene_version=self.version + 1, source="saved_blend")
            state["diff"] = scene_diff(self.scene_state, state)
            (target / "state.json").write_text(json.dumps(state, indent=2))
            self.scene_state = state
            self.version += 1
            self.input_render = None
        record = {"mode": mode, "base_scene_version": base_version,
                  "new_scene_version": self.version if result["success"] else None,
                  "execution_status": "success" if result["success"] else "failed",
                  "execution_time": result["seconds"], "error": result["error"]}
        (directory / "mode.json").write_text(json.dumps(record, indent=2))
        if result["success"]:
            shutil.copyfile(directory / "mode.json", self.current / "mode.json")
        result.update(record)
        return dict(result, scene_version=self.version, execution_time=result["seconds"],
                    blend_path=str(self.current / "scene.blend") if self.current else None)

    def render(self, view, timeout, **camera):
        if not self.current:
            return {"success": False, "error": "No successful scene", "scene_version": 0}
        if view not in ("input", "custom"):
            return {"success": False, "error": "view must be input or custom"}
        if view == "custom" and not all(k in camera for k in ("camera_position", "look_at")):
            return {"success": False, "error": "custom requires camera_position and look_at"}
        number = self.render_count
        self.render_count += 1
        renders = self.current / "renders"
        image = renders / f"{view}_{number:03d}.png"
        result = self.process({"operation": "render", "blend": str(self.current / "scene.blend"),
            "view": view, "image": str(image), "samples": self.samples,
            "resolution": self.resolution, **camera}, renders / f"{view}_{number:03d}", timeout)
        if result["success"] and not image.exists():
            result.update(success=False, error="Render did not produce an image")
        if result["success"] and view == "input":
            self.input_render = image
        result.update(scene_version=self.version, view=view, render_time=result["seconds"],
                      render_path=str(image) if result["success"] else None)
        return result

    def inspect(self, timeout):
        if not self.current:
            return {"success": False, "error": "No successful scene", "scene_version": 0}
        self.inspect_count += 1
        result = self.process({"operation": "inspect", "blend": str(self.current / "scene.blend"),
            "object_limit": self.object_limit}, self.current / f"inspection_{self.inspect_count:03d}", timeout)
        if result["success"]:
            (self.current / "inspect.json").write_text(json.dumps(result["data"], indent=2))
        return dict(result, scene_version=self.version)

    def export(self):
        if self.current:
            shutil.copyfile(self.current / "scene.blend", self.root / "final.blend")
            if self.input_render:
                shutil.copyfile(self.input_render, self.root / "final.png")
