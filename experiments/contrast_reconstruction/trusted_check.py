"""One bounded trusted fixture for the supervised adapter, with an optional idle GPU probe."""
import fcntl
import json
from pathlib import Path
import subprocess
import tempfile
import time

from run import BATCH, ROOT, write
from supervised_runtime import SupervisedRuntime, cpu

CODE = """import bpy
from mathutils import Vector
bpy.ops.mesh.primitive_cube_add(size=1, location=(0,0,0.5))
bpy.context.object.name = 'TrustedCube'
bpy.ops.mesh.primitive_plane_add(size=5)
bpy.ops.object.camera_add(location=(3,-4,3))
scene = bpy.context.scene
scene.camera = bpy.context.object
scene.camera.rotation_euler = (Vector((0,0,0.5))-scene.camera.location).to_track_quat('-Z','Y').to_euler()
bpy.ops.object.light_add(type='AREA', location=(0,-2,4))
bpy.context.object.data.energy = 300
"""


def main():
    root = Path(tempfile.mkdtemp(prefix="trusted_runtime_check_", dir=BATCH))
    runtime = SupervisedRuntime(root / "runtime", approved_source=CODE.encode())
    results = {}
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        results["execute"] = runtime.execute(CODE, 120)
        if not results["execute"]["success"]:
            write(root / "summary.json", results)
            return
        before = (runtime.current / "scene.blend").read_bytes()
        results["input"] = runtime.render("input", 120)
        results["custom"] = runtime.render("custom", 120, camera_position=[-3, -4, 3], look_at=[0, 0, 0.5])
        results["inspect"] = runtime.inspect(120)
        results["source_blend_unchanged"] = before == (runtime.current / "scene.blend").read_bytes()
        results["success"] = all(results[name]["success"] for name in ("execute", "input", "custom", "inspect")) and results["source_blend_unchanged"]
        write(root / "summary.json", results)
        if not results["success"]:
            return
        listing = subprocess.run(["nvidia-smi", "--query-gpu=uuid,utilization.gpu,memory.used", "--format=csv,noheader,nounits"],
                                 capture_output=True, text=True, timeout=10, check=True)
        idle = [parts[0] for line in listing.stdout.splitlines()
                if len(parts := [part.strip() for part in line.split(",")]) == 3 and parts[1:] == ["0", "0"]]
        if not idle:
            results["gpu_probe"] = {"status": "no_idle_gpu"}
        else:
            folder = root / "gpu_probe"
            folder.mkdir()
            uuid = idle[0]
            job = {"blend": str(runtime.current / "scene.blend"), "gpu_uuid": uuid,
                "settings_helper": str(ROOT / "e_harness/runtime/blender_entry.py"), "resolution": [256, 256],
                "samples": 8, "image": str(folder / "render.png"), "result": str(folder / "result.json")}
            write(folder / "job.json", job)
            env = cpu.environment(folder)
            env["CUDA_VISIBLE_DEVICES"] = uuid
            command = cpu.namespace_command([str(cpu.BLENDER), "--background", "--factory-startup", "--disable-autoexec",
                "--threads", "2", "--python-exit-code", "1", "--python", str(Path(__file__).with_name("render_blender.py")), "--", str(folder / "job.json")])
            probe = cpu.monitored_process(command, folder, folder, None, time.monotonic() + 120, "gpu_probe",
                thread_details=True, extra_env=env, sample_seconds=0.02, process_limit=4)
            results["gpu_probe"] = {"device_uuid": uuid, "limits_unchanged": True, **probe}
        write(root / "summary.json", results)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
