"""Per-execution human consent, not a security sandbox or code safety checker."""
import select
import sys
import time


def terminal_decision(review_id, timeout):
    print(f"Type APPROVE {review_id} to approve; anything else rejects "
          f"(timeout {timeout:.0f}s, default reject): ", end="", flush=True)
    if not sys.stdin.isatty():
        return "no_terminal"
    try:
        if not select.select([sys.stdin], [], [], timeout)[0]:
            return "timeout"
        answer = sys.stdin.readline()
        if not answer:
            return "eof"
        return "approved" if answer.strip() == f"APPROVE {review_id}" else "denied"
    except (KeyboardInterrupt, OSError):
        return "interrupted"


class ManualApproval:
    def __init__(self, store):
        self.store = store
        self.number = 0

    def request(self, code, *, timeout, tool_call_id, scene_version, execution):
        self.number += 1
        review_id = f"execute_{self.number:03d}"
        directory = self.store.root / "approvals" / review_id
        directory.mkdir(parents=True)
        path = directory / "code.py"
        snapshot = code.encode("utf-8")
        path.write_bytes(snapshot)
        record = {"review_id": review_id, "code_path": str(path), "encoding": "utf-8",
                  "bytes": len(snapshot), "tool_call_id": tool_call_id,
                  "scene_version": scene_version, "execution": execution}
        self.store.event("approval_requested", **record)
        print(f"\nManual review: {path}\n"
              f"Python: {len(snapshot)} bytes. "
              f"Runtime={execution['runtime']}, isolated={execution['isolated']}.\n"
              f"Mode={execution['mode']}, current scene={scene_version}, "
              f"Blender timeout <= {execution['blender_timeout']}s.\n"
              f"Scene mode={execution['scene_mode']}: "
              f"{'load the current scene' if execution['scene_mode'] == 'update' else 'start an empty scene'}, then save/reopen the blend; "
              "single-shot also renders after success.\n"
              "Read the entire file. Do not edit it. Approval is NOT isolation.", flush=True)
        started = time.monotonic()
        decision = terminal_decision(review_id, timeout)
        if time.monotonic() - started >= timeout:
            decision = "timeout"
        if decision == "approved":
            try:
                if path.read_bytes() != snapshot:
                    decision = "code_changed"
            except OSError:
                decision = "code_unavailable"
        result = {**record, "approved": decision == "approved", "decision": decision,
                  "wait_seconds": round(time.monotonic() - started, 3)}
        self.store.write(str(directory.relative_to(self.store.root) / "decision.json"), result)
        self.store.event("approval_decision", **result)
        return result
