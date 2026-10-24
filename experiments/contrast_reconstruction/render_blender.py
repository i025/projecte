"""Trusted observation helper; never saves the temporary observation camera."""
import json
import math
from pathlib import Path
import runpy
import sys
import time

import bpy
from mathutils import Vector

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
bpy.ops.wm.open_mainfile(filepath=job["blend"], use_scripts=False)
helpers = runpy.run_path(job["settings_helper"])
helpers["render_settings"](job)
scene = bpy.context.scene
scene.cycles.use_denoising = job.get("diagnostic_denoising", False)
scene.cycles.denoising_use_gpu = False
if job.get("gpu_uuid"):
    preferences = bpy.context.preferences.addons["cycles"].preferences
    preferences.compute_device_type = "CUDA"
    preferences.get_devices()
    devices = [device for device in preferences.devices if device.type == "CUDA"]
    if len(devices) != 1:
        raise ValueError("Exactly one CUDA-visible device is required")
    for device in preferences.devices:
        device.use = device.type == "CUDA"
    scene.cycles.device = "GPU"
if job.get("view", "input") == "custom":
    bpy.ops.object.camera_add(location=job["camera_position"])
    scene.camera = bpy.context.object
    direction = Vector(job["look_at"]) - scene.camera.location
    if not direction.length:
        raise ValueError("Camera position and look_at must differ")
    scene.camera.rotation_euler = direction.to_track_quat("-Z", "Y").to_euler()
    scene.camera.data.angle = math.radians(job.get("fov", 50))
if scene.camera is None:
    raise ValueError("No active reconstruction camera")
scene.render.filepath = job["image"]
started = time.monotonic()
bpy.ops.render.render(write_still=True)
Path(job["result"]).write_text(json.dumps({"engine": "CYCLES", "device": scene.cycles.device,
    "render_seconds": time.monotonic() - started, "camera": helpers["camera_info"](scene.camera),
    "samples": scene.cycles.samples, "resolution": job["resolution"],
    "source_blend_saved": False, "autoexec": False}, indent=2))
