"""Reviewed offline fixture; not a real model reconstruction."""
import bpy
from mathutils import Vector

sphere_color = (0.85, 0.55, 0.04)


def material(name, color):
    obj = bpy.context.object
    obj.name = name
    mat = bpy.data.materials.new(name)
    mat.diffuse_color = (*color, 1)
    mat.use_nodes = True
    mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (*color, 1)
    obj.data.materials.append(mat)


bpy.ops.mesh.primitive_plane_add(size=10)
material("Ground", (0.55, 0.55, 0.55))
bpy.ops.mesh.primitive_cube_add(size=1, location=(-1.4, 0, 0.5))
material("Cube", (0.7, 0.12, 0.08))
bpy.ops.object.empty_add(location=(0.25, 0, 0))
parent = bpy.context.object
parent.name = "Assembly"
bpy.ops.mesh.primitive_uv_sphere_add(segments=24, ring_count=12, radius=0.6, location=(-0.25, 0, 0.6))
bpy.context.object.parent = parent
material("Sphere", sphere_color)
bpy.ops.mesh.primitive_cylinder_add(vertices=24, radius=0.45, depth=1.4, location=(1.4, 0, 0.7))
material("Cylinder", (0.15, 0.6, 0.18))
bpy.ops.object.camera_add(location=(4, -7, 4))
camera = bpy.context.object
camera.rotation_euler = (Vector((0, 0, 0.5)) - camera.location).to_track_quat("-Z", "Y").to_euler()
camera.data.lens = 48
bpy.context.scene.camera = camera
bpy.ops.object.light_add(type="AREA", location=(0, -3, 6))
bpy.context.object.data.energy = 900
bpy.context.object.data.size = 5
bpy.context.scene.world = bpy.data.worlds.new("World")
bpy.context.scene.world.color = (0.15, 0.15, 0.15)
