"""Join explicitly selected generated parts in a separate scene copy; no repair."""
from fnmatch import fnmatchcase
import json
from pathlib import Path
import runpy
import sys

import bpy
from mathutils import Vector


def bounds(objects):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        points.extend(evaluated.matrix_world @ vertex.co for vertex in mesh.vertices)
        evaluated.to_mesh_clear()
    return [[min(point[i] for point in points) for i in range(3)],
            [max(point[i] for point in points) for i in range(3)]]

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
bpy.ops.wm.open_mainfile(filepath=job["blend"], use_scripts=False)
scene = bpy.context.scene
groups = json.loads(Path(job["groups"]).read_text())
claimed = set()
selected = {}
for name, patterns in groups.items():
    roots = [obj for obj in scene.objects if any(fnmatchcase(obj.name, pattern) for pattern in patterns)]
    parts = {part for root in roots for part in (root, *root.children_recursive)
             if part.type in ("MESH", "CURVE", "SURFACE", "FONT", "META")}
    if not parts or parts & claimed:
        raise ValueError(f"Empty or overlapping merge group: {name}")
    claimed.update(parts)
    selected[name] = sorted(parts, key=lambda obj: obj.name)
report = {"source_blend": job["blend"], "source_object_count": len(scene.objects), "groups": []}
for name, parts in selected.items():
    original_names = [obj.name for obj in parts]
    before_bounds = bounds(parts)
    converted = []
    for obj in parts:
        matrix = obj.matrix_world.copy()
        obj.parent = None
        obj.matrix_world = matrix
        bpy.ops.object.select_all(action="DESELECT")
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        if obj.type != "MESH" or obj.modifiers:
            bpy.ops.object.convert(target="MESH")
        converted.append(bpy.context.object)
    bpy.ops.object.select_all(action="DESELECT")
    for obj in converted:
        obj.select_set(True)
    bpy.context.view_layer.objects.active = converted[0]
    if len(converted) > 1:
        bpy.ops.object.join()
    bpy.context.object.name = name
    bpy.context.view_layer.update()
    after_bounds = bounds([bpy.context.object])
    report["groups"].append({"object": name, "source_parts": original_names,
        "bounds_before": before_bounds, "bounds_after": after_bounds})
helpers = runpy.run_path(job["settings_helper"])
helpers["save_scene"](job["output_blend"])
bpy.ops.wm.open_mainfile(filepath=job["output_blend"], use_scripts=False)
report["object_count"] = len(bpy.context.scene.objects)
report["geometry_repair"] = False
report["note"] = "Join preserves disconnected surfaces. Procedural Generated/Object texture coordinates may change; original parts and render are retained."
report["scene_state"] = helpers["inspect"](None)
Path(job["result"]).write_text(json.dumps(report, indent=2))
