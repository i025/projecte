"""Optional empty-scene World policy; used only by explicit normalized experiments."""
from contextlib import contextmanager
import json
from pathlib import Path
import runpy
import sys

import bpy


@contextmanager
def world_initialization(enabled=False):
    record = {"enabled": enabled, "created_worlds": [], "handlers_removed": True}
    if not enabled:
        yield record
        return

    @bpy.app.handlers.persistent
    def initialize(*_):
        scene = bpy.context.scene
        # Only normalize empty scenes, never replace an existing World or repair loaded geometry.
        if scene is not None and not scene.objects and scene.world is None:
            world = bpy.data.worlds.new("World")
            world.use_nodes = True
            scene.world = world
            record["created_worlds"].append({"scene": scene.name, "world": world.name})

    handlers = (bpy.app.handlers.load_post, bpy.app.handlers.load_factory_startup_post)
    for callbacks in handlers:
        callbacks.append(initialize)
    try:
        initialize()
        yield record
    finally:
        for callbacks in handlers:
            if initialize in callbacks:
                callbacks.remove(initialize)
        record["handlers_removed"] = all(initialize not in callbacks for callbacks in handlers)


def main():
    job = json.loads(Path(sys.argv[sys.argv.index("--") + 1]).read_text())
    enabled = bool(job.get("normalize_world", False))
    if enabled and (job["operation"] != "execute" or job["mode"] != "replace"):
        raise ValueError("World initialization is only supported for explicit replace execution")
    entry = Path(__file__).resolve().parents[1] / "e_harness/runtime/blender_entry.py"
    record = {}
    try:
        with world_initialization(enabled) as record:
            runpy.run_path(str(entry), run_name="__main__")
    finally:
        if job.get("normalization_report"):
            Path(job["normalization_report"]).write_text(json.dumps(record, indent=2) + "\n")


if __name__ == "__main__":
    main()
