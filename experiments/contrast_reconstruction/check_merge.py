"""Trusted multi-part fixture: preserve transforms and a separate second object."""
import fcntl
from pathlib import Path
import tempfile

from run import BATCH, ROOT, read, write
from supervised_runtime import SupervisedRuntime, cpu
import gpu_profile

CODE = """import bpy
bpy.ops.object.empty_add(location=(1,2,.4))
parent=bpy.context.object
parent.name='UnitRoot'
parent.rotation_euler.z=.4
for name,local in [('PartA',(0,0,0)),('PartB',(1,0,.5))]:
 bpy.ops.mesh.primitive_cube_add(size=1)
 obj=bpy.context.object
 obj.name=name
 obj.parent=parent
 obj.location=local
bpy.ops.mesh.primitive_cube_add(size=.5,location=(-2,0,0))
bpy.context.object.name='SeparateObject'
"""


def main():
    root = Path(tempfile.mkdtemp(prefix="trusted_merge_", dir=BATCH))
    runtime = SupervisedRuntime(root / "runtime", approved_source=CODE.encode())
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        built = runtime.execute(CODE, 600)
        if not built["success"]:
            write(root / "summary.json", built)
            return
        original = Path(built["blend_path"]).read_bytes()
        write(root / "groups.json", {"JoinedUnit": ["UnitRoot"]})
        job = {"blend": built["blend_path"], "output_blend": str(root / "merged.blend"),
            "groups": str(root / "groups.json"), "settings_helper": str(ROOT / "e_harness/runtime/blender_entry.py"),
            "result": str(root / "merge_report.json")}
        write(root / "job.json", job)
        process = gpu_profile.launch(root, Path(__file__).with_name("merge_blender.py"), root / "job.json", label="merge")
        result = {"process": process, "success": False}
        if process["success"]:
            report = read(root / "merge_report.json")
            group = report["groups"][0]
            error = max(abs(a-b) for before,after in zip(group["bounds_before"], group["bounds_after"]) for a,b in zip(before,after))
            names = {obj["name"] for obj in report["scene_state"]["objects"]}
            result.update(success=error < 1e-5 and {"JoinedUnit", "SeparateObject"} <= names and "PartB" not in names
                and Path(built["blend_path"]).read_bytes() == original,
                max_bounds_difference=error, source_blend_unchanged=Path(built["blend_path"]).read_bytes() == original)
        write(root / "summary.json", result)
        print(result)


if __name__ == "__main__":
    main()
