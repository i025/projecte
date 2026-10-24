"""Opt-in supervised GPU profile; not a cgroup quota or an unattended sandbox."""
from pathlib import Path
import subprocess
import time

from supervised_runtime import cpu

LIMITS = {**cpu.LIMITS, "rss_stop_bytes": 32 * 1024**3, "address_space_bytes": 64 * 1024**3,
          "cpu_seconds": 1200, "step_seconds": 600, "processes_stop": 4}
CACHE = cpu.ROOT / "runs/contrast24_gpt6_sol_20261017/cuda_cache"


def available_memory():
    return int(next(line.split()[1] for line in Path("/proc/meminfo").read_text().splitlines()
                    if line.startswith("MemAvailable:"))) * 1024


def query(arguments):
    result = subprocess.run(["nvidia-smi", *arguments, "--format=csv,noheader,nounits"],
                            capture_output=True, text=True, timeout=5, check=True)
    return [[field.strip() for field in line.split(",")] for line in result.stdout.splitlines() if line.strip()]


def idle_device():
    if available_memory() < 64 * 1024**3:
        return None
    active = {row[0] for row in query(["--query-compute-apps=gpu_uuid,pid,used_memory"])}
    devices = query(["--query-gpu=uuid,memory.total,memory.used,utilization.gpu"])
    return next((row[0] for row in devices if row[0] not in active and row[2:] == ["0", "0"]), None)


def observer(uuid):
    previous = {}
    sampled = 0.0

    def sample(rows):
        nonlocal sampled, previous
        if time.monotonic() - sampled < 1:
            return previous
        sampled = time.monotonic()
        devices = query(["--query-gpu=uuid,memory.total,memory.used,utilization.gpu"])
        total, used, utilization = next(row[1:] for row in devices if row[0] == uuid)
        processes = [row for row in query(["--query-compute-apps=gpu_uuid,pid,used_memory"]) if row[0] == uuid]
        own_pids = {row["pid"] for row in rows}
        foreign = [int(row[1]) for row in processes if int(row[1]) not in own_pids]
        previous = {"gpu": {"uuid": uuid, "total_MiB": int(total), "used_MiB": int(used),
            "utilization_percent": int(utilization), "foreign_pids": foreign}}
        if foreign:
            previous["resource_stop"] = "Resource stop: another process appeared on the selected GPU"
        elif int(used) > int(total) - 1024:
            previous["resource_stop"] = "Resource stop: GPU memory headroom below 1 GiB"
        elif available_memory() < 32 * 1024**3:
            previous["resource_stop"] = "Resource stop: shared host available memory below 32 GiB"
        return previous

    return sample


def launch(folder, helper, job_path, uuid=None, *, source=None, label="render"):
    if available_memory() < 64 * 1024**3:
        raise RuntimeError("Insufficient shared host memory headroom")
    env = cpu.environment(folder)
    if uuid:
        env["CUDA_VISIBLE_DEVICES"] = uuid
        env["CUDA_CACHE_PATH"] = str(CACHE)
        CACHE.mkdir(exist_ok=True)
    command = cpu.namespace_command([str(cpu.BLENDER), "--background", "--factory-startup", "--disable-autoexec",
        "--threads", "2", "--python-exit-code", "1", "--python", str(helper), "--", str(job_path)])
    return cpu.monitored_process(command, folder, folder, source, time.monotonic() + LIMITS["step_seconds"], label,
        thread_details=True, extra_env=env, sample_seconds=0.02, process_limit=4,
        limits=LIMITS, observer=observer(uuid) if uuid else None)
