"""Explicit, per-step supervised replay. NOT an isolated/unattended runtime."""
import argparse
import ast
import ctypes
import fcntl
from functools import partial
import json
import os
from pathlib import Path
import resource
import shutil
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from e_harness.approval import terminal_decision

SOURCE = ROOT / "runs/scene_064_incremental_api_incremental_v1"
BLENDER = ROOT.parent / "bvb-repro/runtime/blender-4.2.0-linux-x64/blender"
WORLD_PREFLIGHT = ROOT / "runtime_evidence/world_initialization.json"
ROUNDS = (0, 2, 3)
LIMITS = {"resolution": [256, 256], "samples": 8, "threads": 2,
          "step_seconds": 120, "approval_seconds": 300, "cpu_seconds": 60,
          "address_space_bytes": 8 * 1024**3, "rss_stop_bytes": 1024**3,
          "single_file_bytes": 256 * 1024**2, "output_stop_bytes": 512 * 1024**2,
          "log_stop_bytes": 8 * 1024**2, "threads_stop": 128,
          "processes_stop": 2, "files_stop": 256, "sample_seconds": 0.2}
REVIEWS = {
    0: "Room/camera/light creation; read_homefile(use_empty=True) reads startup state. No explicit network, subprocess, external assets, dynamic execution or handlers. World may be None; no repair permitted.",
    2: "Second room replacement, not layering over the first. Same startup read and World risk. No explicit external side effects beyond Blender scene/material changes.",
    3: "Adds furniture using bpy/math and a locally defined chair function. No reset, external assets, filesystem calls or callbacks; depends on saved round_02 scene, not previous Python variables. Geometry/support issues remain unchanged."
}


def write_json(path, data):
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n")


def event(root, kind, **data):
    with (root / "trajectory.jsonl").open("a") as stream:
        stream.write(json.dumps({"event": kind, "time": time.time(), **data}) + "\n")


def save_step_result(root, folder, result):
    write_json(folder / "result.json", result)
    path = root / "summary.json"
    summary = json.loads(path.read_text()) if path.exists() else {}
    approvals = [json.loads(p.read_text()) for p in root.glob("round_*/approval.json")]
    attempts = list(root.glob("round_*/*_process.json"))
    summary.update(status="step_succeeded" if result["success"] else "stopped",
                   last_step_result=result, human_approvals=sum(a["approved"] for a in approvals),
                   blender_launch_attempts=len(attempts), unattended_runtime="blocked",
                   final_blend=str(root / "final.blend") if (root / "final.blend").exists() else None,
                   final_png=str(root / "final.png") if (root / "final.png").exists() else None)
    if attempts:
        # A failed unshare launch need not have reached Blender or the generated code.
        summary["blender_processes"] = None
        summary["model_python_executed"] = True if list(root.glob("round_*/execute_data.json")) else None
    write_json(path, summary)


def original_code(source, number):
    folder = source / f"round_{number:02d}"
    code = (folder / "generated_code.py").read_bytes()
    response = json.loads((folder / "model_response.json").read_text())
    # Stored API response files contain the original provider response.
    calls = response["choices"][0]["message"]["tool_calls"]
    if len(calls) != 1 or calls[0]["function"]["name"] != "execute_blender":
        raise ValueError("Expected exactly one original execute_blender call")
    args = json.loads(calls[0]["function"]["arguments"])
    mode = "update" if number == 3 else "replace"
    if args.get("mode") != mode or args["code"].encode("utf-8") != code:
        raise ValueError("Original code/mode does not match provider response")
    matched = False
    for line in (source / "trajectory.jsonl").read_text().splitlines():
        item = json.loads(line)
        if item.get("event") == "model_response" and item.get("round") == number:
            if item["response"]["choices"][0]["message"]["tool_calls"] != calls:
                raise ValueError("Provider response differs from trajectory")
            matched = True
    if not matched:
        raise ValueError("Original response missing from trajectory")
    ast.parse(code, filename=str(folder / "generated_code.py"))
    return code


def prepare(root, source=SOURCE, normalize_world=False):
    preflight = WORLD_PREFLIGHT
    if normalize_world:
        evidence = json.loads(preflight.read_text())
        if (not evidence["success"] or {c["name"] for c in evidence["cases"]} != {"default", "world_initialized"}
                or not all(c["success"] and c["cleanup_complete"] for c in evidence["cases"])):
            raise ValueError("World wrapper trusted preflight has not passed")
    codes = {n: original_code(source, n) for n in ROUNDS}
    root.mkdir(parents=True, exist_ok=False, mode=0o700)
    for n, code in codes.items():
        folder = root / f"round_{n:02d}"
        folder.mkdir()
        (folder / "code.py").write_bytes(code)
    # Preserve the trusted execution helper too; changes require a new review.
    shutil.copyfile(ROOT / "e_harness/runtime/blender_entry.py", root / "blender_entry.py")
    write_json(root / "config.json", {"source": str(source.resolve()), "blender": str(BLENDER),
        "limits": LIMITS, "mode": "manual_reviewed_local_replay", "unattended_runtime": "blocked",
        "filesystem_isolation": False, "task_resource_quota": False,
        "namespace_policy": "required user/net/pid/mount+private proc; no local fallback",
        "namespace_integration": "pending_trusted_preflight", "gpu_device_isolation": False})
    write_json(root / "review.json", {str(n): {"reviewer": "assistant_static_review",
        "review": REVIEWS[n], "bytes": len(codes[n]), "lines": len(codes[n].splitlines()),
        "matches_original_response_and_trajectory": True, "human_approval": "pending",
        "safety_guarantee": False} for n in ROUNDS})
    if normalize_world:
        shutil.copyfile(ROOT / "scripts/world_initialized_blender.py", root / "world_initialized_blender.py")
        config = json.loads((root / "config.json").read_text())
        config.update(experiment="environment_normalized_replay", normalize_world=True,
                      allowed_rounds=[0], world_preflight=str(preflight),
                      namespace_integration="verified_trusted_preflight")
        write_json(root / "config.json", config)
    event(root, "prepared", blender_started=False, api_calls=0)


def child_environment(folder):
    private = folder / "private"
    for name in ("home", "tmp", "config", "cache"):
        (private / name).mkdir(parents=True, exist_ok=True)
    return {"PATH": "/usr/bin:/bin", "LANG": "C.UTF-8", "HOME": str(private / "home"),
            "TMPDIR": str(private / "tmp"), "XDG_CONFIG_HOME": str(private / "config"),
            "XDG_CACHE_HOME": str(private / "cache"), "BLENDER_USER_CONFIG": str(private / "config"),
            "CUDA_VISIBLE_DEVICES": "", "HIP_VISIBLE_DEVICES": "", "OMP_NUM_THREADS": "2",
            "OPENBLAS_NUM_THREADS": "2", "MKL_NUM_THREADS": "2"}


def child_limits(limits=None):
    limits = LIMITS if limits is None else limits
    for kind, value in ((resource.RLIMIT_AS, limits["address_space_bytes"]),
                        (resource.RLIMIT_CPU, limits["cpu_seconds"]),
                        (resource.RLIMIT_FSIZE, limits["single_file_bytes"]),
                        (resource.RLIMIT_CORE, 0), (resource.RLIMIT_NOFILE, 256)):
        resource.setrlimit(kind, (value, value))
    os.sched_setaffinity(0, sorted(os.sched_getaffinity(0))[:2])
    os.nice(10)


def namespace_command(command):
    return ["/usr/bin/unshare", "--user", "--map-root-user", "--net", "--mount",
            "--propagation", "private", "--pid", "--fork", "--kill-child=SIGKILL",
            "--mount-proc", "--", *command]


def pidfd_call(number, *args):
    # This server's Python lacks pidfd wrappers; use the x86-64 Linux ABI.
    if os.uname().machine != "x86_64":
        raise RuntimeError("This reviewed launcher supports x86-64 Linux only")
    libc = ctypes.CDLL(None, use_errno=True)
    libc.syscall.restype = ctypes.c_long
    result = libc.syscall(ctypes.c_long(number), *args)
    if result < 0:
        code = ctypes.get_errno()
        raise OSError(code, os.strerror(code))
    return result


def open_pidfd(pid):
    return pidfd_call(434, ctypes.c_int(pid), ctypes.c_uint(0))


def kill_pidfd(fd):
    pidfd_call(424, ctypes.c_int(fd), ctypes.c_int(signal.SIGKILL), ctypes.c_void_p(), ctypes.c_uint(0))


def process_snapshot(pid, thread_details=False, process_limit=None):
    """Observe only this launch's descendants, including children of worker threads."""
    queue, seen, rows = [pid], set(), []
    process_limit = LIMITS["processes_stop"] if process_limit is None else process_limit
    while queue:
        current = queue.pop()
        if current in seen:
            continue
        seen.add(current)
        if len(seen) > process_limit + 1:
            break  # Return the over-limit sample before stopping the task.
        base = Path(f"/proc/{current}")
        try:
            fields = (base / "stat").read_text().rsplit(")", 1)[1].split()
            rows.append({"pid": current, "ppid": int(fields[1]), "state": fields[0], "start_ticks": int(fields[19]),
                         "rss": int(fields[21]) * os.sysconf("SC_PAGE_SIZE"),
                         "threads": int(fields[17]),
                         "cpu_seconds": (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK")})
            tasks = list((base / "task").iterdir())
            rows[-1]["threads"] = max(rows[-1]["threads"], len(tasks))
            if thread_details:
                rows[-1]["command"] = (base / "cmdline").read_bytes()[:4096].replace(b"\0", b" ").decode(errors="replace")
                details = []
                for task in tasks[:LIMITS["threads_stop"] + 1]:
                    try:
                        stat = (task / "stat").read_text()
                        fields = stat.rsplit(")", 1)[1].split()
                        details.append({"tid": int(task.name), "name": stat.split("(", 1)[1].rsplit(")", 1)[0],
                            "state": fields[0], "cpu_seconds": (int(fields[11]) + int(fields[12])) / os.sysconf("SC_CLK_TCK"),
                            "last_cpu": int(fields[36]), "allowed_cpus": sorted(os.sched_getaffinity(int(task.name))),
                            "wchan": (task / "wchan").read_text().strip()})
                    except (FileNotFoundError, ProcessLookupError):
                        pass
                rows[-1]["thread_details"] = details
                rows[-1]["thread_details_truncated"] = len(tasks) > len(details)
            if len(tasks) > LIMITS["threads_stop"]:
                return rows
            for task in tasks:
                try:
                    queue.extend(map(int, (task / "children").read_text().split()))
                except FileNotFoundError:
                    pass
        except FileNotFoundError:
            pass
    return rows


def output_usage(root):
    total, count = 0, 0
    for path in root.rglob("*"):
        count += 1
        if count > LIMITS["files_stop"]:
            raise RuntimeError("Output entry count exceeded")
        if not path.is_symlink() and path.is_file():
            total += path.stat().st_size
    return total


def monitored_process(command, folder, root, source, deadline, label, *,
                      thread_details=False, extra_env=None, sample_seconds=None, process_limit=None,
                      limits=None, observer=None):
    """Bounded monitoring for reviewed code only; not aggregate kernel quotas."""
    limits = LIMITS if limits is None else limits
    started = time.monotonic()
    handles, proc, error, peak_rss, cleanup_complete = {}, None, None, 0, True
    log_path = folder / f"{label}.log"
    last_sample = None
    stop_processes = limits["processes_stop"] if process_limit is None else process_limit
    try:
        os.close(open_pidfd(os.getpid()))  # Fail before launch if pidfds are unavailable.
        with tempfile.TemporaryFile(dir=folder) as snapshot, log_path.open("wb") as log:
            snapshot.write(source or b"")
            snapshot.seek(0)
            proc = subprocess.Popen(command, stdin=snapshot, stdout=log, stderr=subprocess.STDOUT,
                cwd=folder, env={**child_environment(folder), **(extra_env or {})}, close_fds=True,
                start_new_session=True, preexec_fn=partial(child_limits, limits))
            handles[proc.pid] = open_pidfd(proc.pid)
            with (folder / "resources.jsonl").open("a") as records:
                while True:
                    if process_limit is not None:
                        rows = process_snapshot(proc.pid, thread_details, process_limit)
                    else:
                        rows = process_snapshot(proc.pid, True) if thread_details else process_snapshot(proc.pid)
                    for row in rows:
                        if row["pid"] not in handles:
                            try:
                                handles[row["pid"]] = open_pidfd(row["pid"])
                            except ProcessLookupError:
                                pass
                    rss = sum(r["rss"] for r in rows)
                    cpu = sum(r["cpu_seconds"] for r in rows)
                    size = output_usage(root)
                    peak_rss = max(peak_rss, rss)
                    last_sample = {"operation": label, "seconds": round(time.monotonic()-started, 3),
                        "processes": rows, "rss_bytes": rss, "cpu_seconds": cpu, "output_bytes": size}
                    if observer is not None:
                        last_sample.update(observer(rows))
                    if thread_details:
                        phase = folder / "phase.json"
                        last_sample["phase"] = json.loads(phase.read_text())["phase"] if phase.exists() else "startup"
                    records.write(json.dumps(last_sample) + "\n")
                    records.flush()
                    if time.monotonic() >= deadline:
                        raise TimeoutError("Whole step deadline exceeded")
                    if sum(r["threads"] for r in rows) > limits["threads_stop"]:
                        raise RuntimeError("Unexpected thread growth")
                    if last_sample.get("resource_stop"):
                        raise RuntimeError(last_sample["resource_stop"])
                    if (rss > limits["rss_stop_bytes"] or cpu > limits["cpu_seconds"] or
                        len(rows) > stop_processes or
                        sum(r["threads"] for r in rows) > limits["threads_stop"] or
                        size > limits["output_stop_bytes"] or log_path.stat().st_size > limits["log_stop_bytes"]):
                        raise RuntimeError("Resource monitoring stop threshold exceeded")
                    if proc.poll() is not None:
                        break
                    time.sleep(limits["sample_seconds"] if sample_seconds is None else sample_seconds)
            if proc.returncode:
                error = f"Process exit {proc.returncode}; see {log_path.name}"
    except (Exception, KeyboardInterrupt) as exc:
        error = f"{type(exc).__name__}: {exc}"
    finally:
        # Kill the tracked namespace init before its launcher. pidfds avoid PID reuse.
        for fd in reversed(list(handles.values())):
            try:
                kill_pidfd(fd)
            except ProcessLookupError:
                pass
        if proc is not None:
            if proc.poll() is None:
                proc.kill()  # Also covers failure to open the launcher's pidfd.
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                error = "Cleanup incomplete: launcher did not exit"
                cleanup_complete = False
        import select
        for fd in handles.values():
            if not select.select([fd], [], [], 2)[0]:
                error = "Cleanup incomplete: tracked task still alive"
                cleanup_complete = False
            os.close(fd)
    result = {"success": error is None, "error": error, "returncode": proc.returncode if proc else None,
              "seconds": round(time.monotonic()-started, 3), "peak_rss_bytes": peak_rss,
              "log": str(log_path), "command": command, "task_quota": False,
              "cleanup_complete": cleanup_complete, "tracked_pids": list(handles)}
    result["process_limit"] = stop_processes
    if error and last_sample is not None:
        write_json(folder / f"{label}_stop_snapshot.json", last_sample)
    write_json(folder / f"{label}_process.json", result)
    return result


def execute_step(root, number):
    config = json.loads((root / "config.json").read_text())
    normalize_world = config.get("normalize_world", False)
    if normalize_world and number != 0:
        raise ValueError("This normalized replay is limited to round_00")
    if config["limits"] != LIMITS:
        raise ValueError("Prepared limits changed; prepare a separate experiment")
    if config["blender"] != str(BLENDER):
        raise ValueError("Prepared Blender executable changed")
    if config["namespace_integration"] != "verified_trusted_preflight":
        raise ValueError("Trusted launcher preflight has not passed")
    folder = root / f"round_{number:02d}"
    if (folder / "approval.json").exists():
        raise ValueError("This step already has a decision; no automatic retries or overwrite")
    index = ROUNDS.index(number)
    for previous in ROUNDS[:index]:
        result = json.loads((root / f"round_{previous:02d}/result.json").read_text())
        if not result["success"]:
            raise ValueError("Previous step failed; stop the replay")
    snapshot = (folder / "code.py").read_bytes()
    if snapshot != original_code(Path(config["source"]), number):
        raise ValueError("Review copy differs from original API code")
    helper = root / "blender_entry.py"
    if helper.read_bytes() != (ROOT / "e_harness/runtime/blender_entry.py").read_bytes():
        raise ValueError("Execution helper changed; a new review is required")
    wrapper = ROOT / "scripts/world_initialized_blender.py"
    if normalize_world and (root / wrapper.name).read_bytes() != wrapper.read_bytes():
        raise ValueError("World wrapper changed; a new review is required")
    mode = "update" if number == 3 else "replace"
    review_id = f"round_{number:02d}"
    if normalize_world:
        print("environment_normalized_replay: World initialization ON, including empty-scene resets.\n"
              "Original code unchanged; this is an explicit environment change, not code repair.", flush=True)
    print(f"Review full code: {folder / 'code.py'}\n{REVIEWS[number]}\n"
          f"Mode={mode}; CPU Cycles 256x256, 8 samples, 2 threads; execute+render <=120s.\n"
          "WARNING: local supervised replay, no filesystem sandbox or task quota.\n"
          "Approval also accepts documented remaining risks; ensure server policy permits this run.", flush=True)
    event(root, "approval_requested", round=number, code_path=str(folder / "code.py"), bytes=len(snapshot))
    requested = time.monotonic()
    decision = terminal_decision(review_id, LIMITS["approval_seconds"])
    if time.monotonic() - requested >= LIMITS["approval_seconds"]:
        decision = "timeout"
    if decision == "approved":
        try:
            if (folder / "code.py").read_bytes() != snapshot:
                decision = "code_changed"
        except OSError:
            decision = "code_unavailable"
    approval = {"round": number, "decision": decision, "approved": decision == "approved",
                "code_path": str(folder / "code.py"), "bytes": len(snapshot), "time": time.time(),
                "scope": "one step including save/reopen and CPU render", "is_sandbox": False}
    approval["normalize_world"] = normalize_world
    write_json(folder / "approval.json", approval)
    event(root, "approval_decision", **approval)
    if decision != "approved":
        result = {"success": False, "error": f"Approval {decision}", "executed": False}
        save_step_result(root, folder, result)
        return result
    (folder / "execution_code.py").write_bytes(snapshot)
    deadline = time.monotonic() + LIMITS["step_seconds"]
    blend = folder / "scene.blend"
    job = {"operation": "execute", "mode": mode, "code": str(folder / "execution_code.py"),
           "blend": str(blend), "resolution": [256, 256], "samples": 8}
    if normalize_world:
        job.update(normalize_world=True, normalization_report=str(folder / "normalization.json"))
    if mode == "update":
        shutil.copyfile(root / "round_02/scene.blend", folder / "base.blend")
        job["base_blend"] = str(folder / "base.blend")
    result = {"success": False, "round": number, "mode": mode, "version": index + 1}
    for operation in ("execute", "render"):
        if time.monotonic() >= deadline:
            result["error"] = "Whole step deadline exhausted"
            break
        if operation == "render":
            job = {"operation": "render", "blend": str(blend), "view": "input",
                   "image": str(folder / "render.png"), "resolution": [256, 256], "samples": 8}
        data_path = folder / f"{operation}_data.json"
        job["result"] = str(data_path)
        job_path = folder / f"{operation}_job.json"
        write_json(job_path, job)
        command = namespace_command([config["blender"], "--background", "--factory-startup",
            "--disable-autoexec", "--threads", "2", "--python-exit-code", "1",
            "--python", str(wrapper if normalize_world else helper), "--", str(job_path)])
        process = monitored_process(command, folder, root, snapshot if operation == "execute" else None,
                                    deadline, operation)
        artifact = blend if operation == "execute" else folder / "render.png"
        if not process["success"] or not data_path.exists() or not artifact.exists():
            result["error"] = process["error"] or "Missing expected artifact/result"
            break
    else:
        result["success"] = True
    event(root, "step_finished", **result)
    if result["success"]:
        shutil.copyfile(blend, root / f"scene_v{index+1:03d}.blend")
        shutil.copyfile(folder / "render.png", root / f"scene_v{index+1:03d}.png")
        if number == 3:
            shutil.copyfile(blend, root / "final.blend")
            shutil.copyfile(folder / "render.png", root / "final.png")
    save_step_result(root, folder, result)
    return result


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    action = parser.add_mutually_exclusive_group(required=True)
    action.add_argument("--prepare", action="store_true", help="Copy/review artifacts; never starts Blender")
    action.add_argument("--execute", action="store_true", help="Request terminal approval for ONE step")
    parser.add_argument("--round", type=int, choices=ROUNDS)
    parser.add_argument("--normalize-world", action="store_true", help="Prepare an opt-in World-normalized round_00 experiment")
    parser.add_argument("--output", type=Path, default=ROOT / "runs/scene_064_manual_replay")
    args = parser.parse_args(argv)
    if args.execute and args.round is None:
        parser.error("--execute requires --round")
    if args.normalize_world and not args.prepare:
        parser.error("--normalize-world is set during --prepare, then read from saved config")
    root = args.output.resolve()
    def interrupted(signum, frame):
        raise KeyboardInterrupt(f"Signal {signum}")
    signal.signal(signal.SIGTERM, interrupted)
    # One supervised replay at a time, even across output directories.
    with (ROOT / "runs/.manual_reviewed_replay.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            if args.prepare:
                prepare(root, normalize_world=args.normalize_world)
                print(f"Prepared only: {root}; no Blender started; approvals pending.")
                return 0
            result = execute_step(root, args.round)
            print(json.dumps(result, ensure_ascii=False))
            return 0 if result["success"] else 1
        except (OSError, ValueError, KeyError) as exc:
            if args.execute:
                folder = root / f"round_{args.round:02d}"
                if (folder / "approval.json").exists() and not (folder / "result.json").exists():
                    save_step_result(root, folder, {"success": False, "error": str(exc)})
                    event(root, "step_failed", round=args.round, error=str(exc))
            print(f"Stopped: {exc}", file=sys.stderr)
            return 1


if __name__ == "__main__":
    raise SystemExit(main())
