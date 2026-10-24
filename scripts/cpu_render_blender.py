"""Trusted render-only helper; never executes text stored inside a blend."""
import json
from pathlib import Path
import runpy
import sys
import time

import bpy

job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
bpy.ops.wm.open_mainfile(filepath=job["blend"], use_scripts=False)
helpers = runpy.run_path(job["settings_helper"])
helpers["render_settings"](job)
scene = bpy.context.scene
scene.cycles.use_denoising = False
scene.cycles.denoising_use_gpu = False
scene.render.filepath = job["image"]
started = time.monotonic()
bpy.ops.render.render(write_still=True)
Path(job["result"]).write_text(json.dumps({
    "engine": scene.render.engine, "device": scene.cycles.device,
    "threads": scene.render.threads, "samples": scene.cycles.samples,
    "render_seconds": time.monotonic() - started,
    "camera": helpers["camera_info"](scene.camera),
    "resolution": [scene.render.resolution_x, scene.render.resolution_y],
    "autoexec": False, "denoising": False, "source_blend_saved": False
}, indent=2))
