"""One approved scene replacement or update using the supervised CPU profile."""
import argparse
import fcntl
import json
from pathlib import Path
import shutil
import signal
import time

import manual_cpu_render as cpu
from manual_reviewed_replay import ROOT, SOURCE, original_code, terminal_decision, event, write_json

HELPERS = {"world_initialized_blender.py": ROOT / "scripts/world_initialized_blender.py",
           "settings_helper.py": ROOT / "e_harness/runtime/blender_entry.py",
           "render_helper.py": ROOT / "scripts/cpu_render_blender.py"}


def prepare(root, source=SOURCE, number=2):
    if number == 3:
        previous = json.loads((root / "round_02/result.json").read_text())
        if not previous["success"]:
            raise ValueError("round_02 must succeed before preparing update")
        source = Path(json.loads((root / "config.json").read_text())["source"])
    code = original_code(source, number)
    evidence = json.loads(cpu.CALIBRATION.read_text())
    if not evidence["success"] or len(evidence["cases"]) != 3:
        raise ValueError("Three successful trusted renders required")
    if number == 2:
        cpu.prepare(root)
        config = json.loads((root / "config.json").read_text())
        config.update(experiment="environment_normalized_replay", source=str(source.resolve()),
                      allowed_rounds=[2], mode="replace", normalize_world=True,
                      calibration=str(cpu.CALIBRATION), code_bytes=len(code))
        write_json(root / "config.json", config)
    mode = "replace" if number == 2 else "update"
    folder = root / f"round_{number:02d}"
    folder.mkdir()
    (folder / "code.py").write_bytes(code)
    for name, path in HELPERS.items():
        if number == 2:
            (root / name).write_bytes(path.read_bytes())
        elif (root / name).read_bytes() != path.read_bytes():
            raise ValueError(f"Reviewed helper changed: {name}")
    job = {"operation": "execute", "mode": mode,
        "code": str(folder / "execution_code.py"), "blend": str(folder / "scene.blend"),
        "result": str(folder / "execute_data.json"), "resolution": [256, 256], "samples": 8,
        "normalize_world": number == 2, "normalization_report": str(folder / "normalization.json")}
    if number == 3:
        shutil.copyfile(root / "round_02/scene.blend", folder / "base.blend")
        job["base_blend"] = str(folder / "base.blend")
        write_json(folder / "preparation.json", {"round": 3, "mode": mode,
            "source_blend": str(root / "round_02/scene.blend"), "code_bytes": len(code),
            "approval": "pending", "normalize_world": False})
        write_json(folder / "inspect_job.json", {"operation": "inspect", "object_limit": None,
            "blend": str(folder / "scene.blend"), "result": str(folder / "inspect_data.json")})
    write_json(folder / "execute_job.json", job)
    write_json(folder / "render_job.json", {"blend": str(folder / "scene.blend"),
        "image": str(folder / "render.png"), "result": str(folder / "render_data.json"),
        "settings_helper": str(root / "settings_helper.py"), "resolution": [256, 256], "samples": 8})
    event(root, "prepared", round=number, mode=mode, approval="pending", blender_started=False)
    if number == 3:
        with (root / "replay_report.md").open("a") as stream:
            stream.write("\n## round_03 准备\n\n原始 update 代码已保存，尚未执行或批准。"
                         "唯一输入是 round_02/scene.blend 的字节副本 base.blend。"
                         "不重置场景，不拼接或重跑历史代码，不启用 World 补建。\n")
        return
    (root / "replay_report.md").write_text(
        "# Environment-normalized replay\n\n"
        "round_02 已准备，尚未批准或执行。原始代码与 API 响应及轨迹一致。\n\n"
        "replace 从空场景开始，World Wrapper 处理空场景重置；不加载 round_00。\n"
        "沿用可信 CPU 配置：2 核、2 渲染线程、256×256、8 samples、4 进程阈值；"
        "执行与渲染共用 120 秒。禁用自动脚本，环境清理及网络命名空间保留。\n\n"
        "这是人工监督离线重放，不是完整沙箱或新的 Agent 闭环。正式 Runtime 仍 blocked。\n"
        "round_03 尚未准备；必须在 round_02 成功后另行准备、审核和批准，继承其 blend。\n"
        "final.blend/final.png 仅在后续 round_03 获批且成功后导出。\n")


def execute(root, number=2):
    folder = root / f"round_{number:02d}"
    mode = "replace" if number == 2 else "update"
    if (folder / "approval.json").exists():
        raise ValueError("This step already has a decision; no retries or overwrite")
    config = json.loads((root / "config.json").read_text())
    if config["limits"] != {**cpu.LIMITS, "processes_stop": cpu.PROCESS_LIMIT, "sample_seconds": 0.02}:
        raise ValueError("Prepared resource limits changed")
    snapshot = (folder / "code.py").read_bytes()
    if snapshot != original_code(Path(config["source"]), number):
        raise ValueError("Code differs from original model response")
    if number == 3:
        if not json.loads((root / "round_02/result.json").read_text())["success"]:
            raise ValueError("round_02 must succeed before update")
        if (folder / "base.blend").read_bytes() != (root / "round_02/scene.blend").read_bytes():
            raise ValueError("Update base differs from round_02 scene")
    for name, path in HELPERS.items():
        if (root / name).read_bytes() != path.read_bytes():
            raise ValueError(f"Reviewed helper changed: {name}")
    reviewed = {p: p.read_bytes() for p in [folder / "code.py", folder / "execute_job.json",
                folder / "render_job.json", *[root / name for name in HELPERS]]}
    if number == 3:
        reviewed.update({p: p.read_bytes() for p in (folder / "base.blend", folder / "inspect_job.json")})
    print(f"Review full code: {folder / 'code.py'}\n"
          f"round_{number:02d} {mode} ONLY; original model code unchanged.\n"
          f"Base scene: {folder / 'base.blend' if number == 3 else 'empty scene + World normalization'}\n"
          "CPU Cycles 256x256, 8 samples, 2 cores/threads, 4 processes; whole step <=120s.\n"
          "No filesystem sandbox/task quota. Formal Runtime blocked; no other round included.", flush=True)
    event(root, "approval_requested", round=number, mode=mode, bytes=len(snapshot))
    decision = terminal_decision(f"round_{number:02d}", cpu.LIMITS["approval_seconds"])
    if decision == "approved":
        try:
            if any(p.read_bytes() != data for p, data in reviewed.items()):
                decision = "artifact_changed"
        except OSError:
            decision = "artifact_unavailable"
    approval = {"approved": decision == "approved", "decision": decision, "round": number,
                "time": time.time(), "scope": f"round_{number:02d} {mode}, save/reopen, CPU render and inspection"}
    write_json(folder / "approval.json", approval)
    event(root, "approval_decision", **approval)
    result = {"success": False, "round": number, "mode": mode, "executed": False,
              "unattended_runtime": "blocked", "api_calls": 0}
    if not approval["approved"]:
        result["error"] = f"Approval {decision}"
    else:
        (folder / "execution_code.py").write_bytes(snapshot)
        deadline = time.monotonic() + cpu.LIMITS["step_seconds"]
        try:
            operations = [
                    ("execute", HELPERS["world_initialized_blender.py"], snapshot, "scene.blend"),
                    ("render", root / "render_helper.py", None, "render.png")]
            if number == 3:
                operations.append(("inspect", root / "settings_helper.py", None, "scene.blend"))
            for label, helper, code, artifact in operations:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Whole step deadline exhausted")
                if label == "execute":
                    result["executed"] = None  # A failed launch may have run part of the code.
                process = cpu.launch(folder, root, helper, folder / f"{label}_job.json",
                    source=code, deadline=deadline, label=label)
                result[f"{label}_process"] = process
                if not process["success"] or not process["cleanup_complete"]:
                    raise RuntimeError(process["error"] or "Cleanup failed")
                data = json.loads((folder / f"{label}_data.json").read_text())
                if not (folder / artifact).is_file():
                    raise RuntimeError(f"Missing {artifact}")
                if label == "execute":
                    result["executed"] = True
                    write_json(folder / "scene_inspection.json", data["scene_state"])
                    result["world_initialization"] = json.loads((folder / "normalization.json").read_text())
                elif label == "inspect":
                    write_json(folder / "scene_inspection.json", data)
            result.update(cpu.statistics(folder))
            result["success"] = result["all_sampled_threads_within_affinity"]
        except (Exception, KeyboardInterrupt) as exc:
            result["error"] = f"{type(exc).__name__}: {exc}"
    if result["success"] and number == 3:
        shutil.copyfile(folder / "scene.blend", root / "final.blend")
        shutil.copyfile(folder / "render.png", root / "final.png")
    write_json(folder / "result.json", result)
    write_json(root / "summary.json", result)
    event(root, "step_finished", **result)
    with (root / "replay_report.md").open("a") as stream:
        stream.write(f"\n## round_{number:02d} 运行记录\n\n```json\n" + json.dumps(result, ensure_ascii=False, indent=2) + "\n```\n")
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true")
    action.add_argument("--execute", action="store_true")
    parser.add_argument("--round", type=int, choices=(2, 3), required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args(argv)
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        root = args.output.resolve()
        if args.prepare:
            prepare(root, number=args.round)
            print(f"Prepared only: {root}; Blender not started; approval pending.")
            return 0
        result = execute(root, number=args.round)
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0 if result["success"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
