import argparse
import json
from pathlib import Path

from .model_client import MockModel, ModelClient
from .storage import Storage
from .prompts import PROMPT_VERSIONS

ROOT = Path(__file__).resolve().parents[1]
BLENDER = ROOT.parent / "bvb-repro/runtime/blender-4.2.0-linux-x64/blender"


def mock_calls():
    code = Path(__file__).with_name("mock_scene.py").read_text()
    revised = "import bpy\nbpy.data.materials['Sphere'].node_tree.nodes['Principled BSDF'].inputs['Base Color'].default_value = (0.08, 0.3, 0.75, 1)\n"
    return [("execute_blender", {"code": code, "mode": "replace"}), ("render_scene", {"view": "input"}),
            ("inspect_scene", {}), ("render_scene", {"view": "custom", "camera_position": [-4, -4, 3], "look_at": [0, 0, 0.5]}),
            ("execute_blender", {"code": revised, "mode": "update"}), ("render_scene", {"view": "input"}), ("finish", {})]


def parser():
    p = argparse.ArgumentParser(description="Single-image scene reconstruction; local execution is mock-only.")
    p.add_argument("--image", type=Path, required=True)
    p.add_argument("--output", type=Path, required=True)
    p.add_argument("--model", default="openai/gpt-5.1")
    p.add_argument("--mock", action="store_true")
    p.add_argument('--fixed-camera', action='store_true', help='Benchmark preset T0; Agent chooses intrinsics; local real execution remains blocked')
    p.add_argument("--generation-only", action="store_true", help="Save one response as code; never construct a runtime")
    p.add_argument("--live", action="store_true", help="Authorize the generation-only API request")
    p.add_argument("--max-output-tokens", type=int, default=4096, help="Generation-only output token limit")
    p.add_argument("--manual-approval", action="store_true",
                   help="Require terminal approval for every execute_blender; does not bypass runtime isolation")
    p.add_argument("--mode", choices=["single_shot", "tool_agent"], default="tool_agent")
    p.add_argument("--context-policy", choices=["full", "scene_state_recent"], default="full")
    p.add_argument("--prompt-version", choices=PROMPT_VERSIONS, default="baseline")
    p.add_argument("--blender", type=Path, default=BLENDER)
    p.add_argument("--api-base-url")
    for name, default in [("max-model-turns", 8), ("max-executions", 3), ("max-renders", 6),
                          ("max-inspects", 6), ("max-total-tool-calls", 16), ("api-retries", 1),
                          ("width", 320), ("height", 240), ("samples", 16), ("object-limit", 100)]:
        p.add_argument("--" + name, type=int, default=default)
    for name, default in [("max-wall-time", 600), ("blender-timeout", 120), ("render-timeout", 120),
                          ("api-timeout", 120), ("approval-timeout", 300)]:
        p.add_argument("--" + name, type=float, default=default)
    return p


def main():
    p = parser()
    args = p.parse_args()
    if args.generation_only and (args.mode != "single_shot" or args.manual_approval):
        p.error("--generation-only requires --mode single_shot and cannot use --manual-approval")
    if args.live and (not args.generation_only or args.mock):
        p.error("--live is only for non-Mock --generation-only")
    if args.max_output_tokens <= 0:
        p.error("--max-output-tokens must be positive")
    config = {k: str(v.resolve()) if isinstance(v, Path) else v for k, v in vars(args).items()}
    config["effective_prompt_version"] = args.prompt_version if args.mode == "tool_agent" else "baseline"
    if args.fixed_camera:
        from .benchmark_config import RENDER
        config['benchmark_camera'] = dict(RENDER, resolution=[args.width,args.height], samples=args.samples)
    if any(value < 0 for value in config.values() if isinstance(value, (int, float))) or min(args.width, args.height, args.samples) < 1:
        p.error("Budgets must be nonnegative; render dimensions and samples must be positive")
    try:
        store = Storage(args.output, args.image, config)
    except FileExistsError:
        p.error("Output already exists; choose a new experiment directory")
    model = MockModel(mock_calls()) if args.mock else ModelClient(args.model, args.api_base_url)
    if args.generation_only:
        from .generation import generate_only
        summary = generate_only(model, store, config)
    else:
        from .agent import Agent
        from .runtime.blender_runtime import BlenderRuntime
        runtime = BlenderRuntime(store.root, args.blender.resolve(), trusted_mock=args.mock,
            resolution=(args.width, args.height), samples=args.samples, object_limit=args.object_limit,
            benchmark_camera=config.get('benchmark_camera'))
        summary = Agent(model, runtime, store, config).run()
    print(json.dumps(summary, indent=2))
    return 0 if summary["status"] in ("completed", "generated", "dry_run") else 1


if __name__ == "__main__":
    raise SystemExit(main())
