"""Read-only geometry audit of a separately joined export."""
import json
from pathlib import Path
import sys

import bpy
from mathutils.kdtree import KDTree


def vertices(objects):
    bpy.context.view_layer.update()
    graph = bpy.context.evaluated_depsgraph_get()
    points = []
    for obj in objects:
        evaluated = obj.evaluated_get(graph)
        mesh = evaluated.to_mesh()
        points.extend(tuple(evaluated.matrix_world @ vertex.co) for vertex in mesh.vertices)
        evaluated.to_mesh_clear()
    return points


def nearest_error(first, second):
    tree = KDTree(len(second))
    for index, point in enumerate(second):
        tree.insert(point, index)
    tree.balance()
    return max(tree.find(point)[2] for point in first)


job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
report = json.loads(Path(job["merge_report"]).read_text())
bpy.ops.wm.open_mainfile(filepath=job["source"], use_scripts=False)
before = {g["object"]: vertices([bpy.data.objects[name] for name in g["source_parts"]])
          for g in report["groups"]}
bpy.ops.wm.open_mainfile(filepath=job["merged"], use_scripts=False)
results = []
for name, original in before.items():
    joined = vertices([bpy.data.objects[name]])
    def bounds(points):
        return [[f(point[i] for point in points) for i in range(3)] for f in (min, max)]
    error = max(abs(a-b) for row1, row2 in zip(bounds(original), bounds(joined)) for a, b in zip(row1, row2))
    results.append({"object": name, "source_vertices": len(original), "merged_vertices": len(joined),
                    "max_vertex_bounds_difference": error,
                    "max_bidirectional_vertex_distance": max(nearest_error(original, joined), nearest_error(joined, original))})
Path(job["result"]).write_text(json.dumps({"groups": results, "source_saved": False}, indent=2))
