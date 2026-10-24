"""Offline transport and review tests; no API or Blender processes."""
import contextlib
import io
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from PIL import Image
import run
from supervised_runtime import SupervisedRuntime, cpu


class Reply:
    status_code = 200

    def __init__(self, data):
        self.data = data

    def raise_for_status(self):
        pass

    def json(self, **_):
        return self.data


class Session:
    def __init__(self):
        self.calls = []
        self.trust_env = True

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def get(self, *_, **__):
        return Reply({"balance": "100", "used": "0", "currency": "USD", "is_active": True})

    def post(self, url, **kwargs):
        if self.trust_env:
            raise AssertionError("Wrong session: tunnel was not configured")
        self.calls.append((url, kwargs))
        return Reply({"usage": {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30},
            "choices": [{"finish_reason": "tool_calls", "message": {"role": "assistant", "content": None,
                "tool_calls": [{"id": "mock_1", "type": "function", "function": {"name": "execute_blender",
                    "arguments": json.dumps({"mode": "replace", "code": "raise RuntimeError('never execute in request')"})}}]}}]})


class Tunnel:
    def __init__(self, **_):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *_):
        pass

    def configure_session(self, session):
        session.trust_env = False


class SupervisionTests(unittest.TestCase):
    def test_optional_limits_preserve_existing_defaults(self):
        import gpu_profile
        self.assertEqual(cpu.LIMITS["rss_stop_bytes"], 1024**3)
        self.assertEqual(cpu.LIMITS["cpu_seconds"], 60)
        self.assertEqual(cpu.LIMITS["step_seconds"], 120)
        self.assertEqual(gpu_profile.LIMITS["rss_stop_bytes"], 32 * 1024**3)
        self.assertEqual(gpu_profile.LIMITS["cpu_seconds"], 1200)
        self.assertEqual(gpu_profile.LIMITS["step_seconds"], 600)

    def test_request_uses_configured_session_and_only_saves_code(self):
        with tempfile.TemporaryDirectory() as temporary:
            folder = Path(temporary)
            Image.new("RGB", (4, 3)).save(folder / "source.png")
            run.write(folder / "manifest.json", {"images": [{"id": "sample", "image": "source.png"}]})
            config = run.read(run.BATCH / "config.json")
            config.update(dataset_manifest=str(folder / "manifest.json"), max_api_calls_per_image=1)
            run.write(folder / "config.json", config)
            session = Session()
            with patch.object(run, "BATCH", folder), patch.object(run, "OfoxTunnel", Tunnel), \
                 patch("requests.Session", return_value=session), patch.dict(os.environ, {"OFOX_API_KEY": "offline_fixture_key"}), \
                 patch("subprocess.Popen", side_effect=AssertionError("No process allowed")), contextlib.redirect_stdout(io.StringIO()):
                run.request("sample")
                run.request("sample")
            self.assertEqual(len(session.calls), 1)
            _, call = session.calls[0]
            self.assertFalse(call["allow_redirects"])
            self.assertEqual(call["json"]["tools"], run.TOOLS)
            self.assertEqual(call["json"]["model"], "openai/gpt-6-sol")
            self.assertTrue(call["json"]["messages"][1]["content"][0]["image_url"]["url"].startswith("data:image/png;base64,"))
            self.assertEqual((folder / "sample/round_00/code.py").read_text(), "raise RuntimeError('never execute in request')")
            self.assertNotIn("base64,", (folder / "sample/round_00/trajectory.jsonl").read_text())

    def test_without_exact_reviewed_bytes_runtime_cannot_start(self):
        with tempfile.TemporaryDirectory() as temporary, patch.object(cpu, "launch") as launch:
            runtime = SupervisedRuntime(Path(temporary), approved_source=b"approved")
            with self.assertRaises(PermissionError):
                runtime.process({"operation": "execute", "mode": "replace"}, Path(temporary), 120, b"changed")
            launch.assert_not_called()
            self.assertFalse(runtime.isolated)
            self.assertFalse(runtime.trusted_mock)


if __name__ == "__main__":
    unittest.main()
