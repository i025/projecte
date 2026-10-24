"""Runs inside Blender. No reference image or hidden evidence is passed here."""
import json
import math
from pathlib import Path
import sys
import time

import bpy
from mathutils import Vector


def render_settings(job):
    scene = bpy.context.scene
    scene.render.engine = "CYCLES"
    scene.cycles.device = "CPU"
    scene.cycles.samples = job["samples"]
    scene.render.threads_mode = "FIXED"
    scene.render.threads = 2
    scene.render.resolution_x, scene.render.resolution_y = job["resolution"]
    scene.render.resolution_percentage = 100
    scene.render.image_settings.file_format = "PNG"
    scene.render.image_settings.color_mode = "RGB"


def save_scene(path):
    for material in bpy.data.materials:
        if material.users == 0:
            material.use_fake_user = True
    bpy.context.preferences.filepaths.save_version = 0
    bpy.ops.wm.save_as_mainfile(filepath=path)


def camera_info(camera):
    if camera is None:
        return None
    return {"name": camera.name, "location": list(camera.matrix_world.translation),
            "rotation": list(camera.matrix_world.to_euler()), "type": camera.data.type,
            "lens_mm": camera.data.lens, "fov_degrees": math.degrees(camera.data.angle),
            "ortho_scale": camera.data.ortho_scale,
            "matrix_world": [list(row) for row in camera.matrix_world],
            "sensor_fit": camera.data.sensor_fit, "sensor_width_mm": camera.data.sensor_width,
            "sensor_height_mm": camera.data.sensor_height,
            "shift_x": camera.data.shift_x, "shift_y": camera.data.shift_y}


def inspect(limit):
    scene = bpy.context.scene
    bpy.context.view_layer.update()
    objects = []
    for obj in sorted(scene.objects, key=lambda obj: obj.name)[:limit]:
        corners = [obj.matrix_world @ Vector(v) for v in obj.bound_box]
        dimensions = [max(p[i] for p in corners) - min(p[i] for p in corners) for i in range(3)]
        objects.append({"name": obj.name, "type": obj.type,
            "location": list(obj.matrix_world.translation), "dimensions": dimensions,
            "rotation": list(obj.matrix_world.to_euler()),
            "materials": [slot.material.name for slot in obj.material_slots if slot.material],
            "parent": obj.parent.name if obj.parent else None,
            "collections": sorted(c.name for c in obj.users_collection)})
        if obj.type == "LIGHT":
            objects[-1]["light"] = {"type": obj.data.type, "energy": obj.data.energy, "color": list(obj.data.color)}
    materials = {}
    for name in sorted(bpy.data.materials.keys()):
        mat = bpy.data.materials[name]
        data = {"diffuse_color": list(mat.diffuse_color), "use_nodes": mat.use_nodes}
        if mat.use_nodes:
            node = next((n for n in mat.node_tree.nodes if n.type == "BSDF_PRINCIPLED"), None)
            if node:
                data.update(base_color=list(node.inputs["Base Color"].default_value),
                            metallic=node.inputs["Metallic"].default_value, roughness=node.inputs["Roughness"].default_value)
        materials[name] = data
    return {"objects": objects, "object_count": len(scene.objects),
            "truncated": limit is not None and len(scene.objects) > limit, "camera": camera_info(scene.camera),
            "materials": materials, "omitted_fields": ["mesh_topology", "shader_graphs", "textures", "modifiers", "animation"],
            "render_resolution": [scene.render.resolution_x, scene.render.resolution_y],
            "coordinate_system": "world", "dimensions_definition": "world-axis-aligned bounds",
            "rotation_units": "radians", "blender_version": bpy.app.version_string}


def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
    operation = job["operation"]
    if job.get('benchmark_camera'):
        sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
        from e_harness.runtime.benchmark_blender import benchmark_camera, configure
    if operation == "execute":
        if job["mode"] == "update":
            bpy.ops.wm.open_mainfile(filepath=job["base_blend"], use_scripts=False)
        else:
            bpy.ops.wm.read_factory_settings(use_empty=True)
            if job.get('benchmark_camera'):
                benchmark_camera(bpy.context.scene, job['benchmark_camera'], {'type':'PERSP','lens':50.})
        # Execute the caller's byte snapshot, never reread the editable code artifact.
        code = sys.stdin.buffer.read().decode("utf-8")
        exec(compile(code, job["code"], "exec"), {"__name__": "__main__"})
        if job.get('benchmark_camera'):
            benchmark_camera(bpy.context.scene, job['benchmark_camera'])
            configure(bpy.context.scene, job['benchmark_camera'])
        if not bpy.context.scene.objects:
            raise ValueError("The generated scene is empty")
        render_settings(job)
        save_scene(job["blend"])
        bpy.ops.wm.open_mainfile(filepath=job["blend"], use_scripts=False)
        result = {"object_count": len(bpy.context.scene.objects), "blender_version": bpy.app.version_string}
        started = time.monotonic()
        result["scene_state"] = inspect(None)
        result["snapshot_seconds"] = time.monotonic() - started
    else:
        bpy.ops.wm.open_mainfile(filepath=job["blend"], use_scripts=False)
        if operation == "inspect":
            result = inspect(job["object_limit"])
        elif operation == "render":
            scene = bpy.context.scene
            if job["view"] == "custom":
                bpy.ops.object.camera_add(location=job["camera_position"])
                camera = bpy.context.object
                direction = Vector(job["look_at"]) - camera.location
                if direction.length == 0:
                    raise ValueError("Camera position and look_at must differ")
                camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
                camera.data.angle = math.radians(job.get("fov", 50))
                scene.camera = camera
            if scene.camera is None:
                raise ValueError("No active reconstruction camera; create one in your code")
            render_settings(job)
            if job.get('benchmark_camera') and job['view']=='input':
                benchmark_camera(scene, job['benchmark_camera'])
                configure(scene, job['benchmark_camera'])
            scene.render.filepath = job["image"]
            bpy.context.view_layer.update()
            result = {"camera": camera_info(scene.camera), "engine": scene.render.engine,
                      "resolution": job["resolution"], "samples": job["samples"]}
            bpy.ops.render.render(write_still=True)
            # No save: the observation camera never changes the source blend.
        else:
            raise ValueError(f"Unknown operation: {operation}")
    Path(job["result"]).write_text(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
