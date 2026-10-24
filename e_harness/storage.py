import base64
import json
import os
from pathlib import Path
import time

from PIL import Image


class Storage:
    def __init__(self, output, image, config):
        self.root = Path(output).resolve()
        self.root.mkdir(parents=True, exist_ok=False)
        self.images = {}
        self.secrets = [v for k, v in os.environ.items() if len(v) >= 8 and
                        any(word in k.upper() for word in ("API_KEY", "TOKEN", "SECRET", "PASSWORD"))]
        with Image.open(image) as source:
            source.convert("RGB").save(self.root / "input.png")
        self.write("config.json", {"prompt_version": "baseline", **config})

    def save_system_prompt(self, prompt):
        (self.root / "system_prompt.txt").write_bytes(prompt.encode("utf-8"))

    def clean(self, value):
        if isinstance(value, str):
            if value in self.images:
                return {"image_file": self.images[value]}
            for secret in self.secrets:
                value = value.replace(secret, "[REDACTED]")
            return value
        if isinstance(value, dict):
            return {k: self.clean(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.clean(v) for v in value]
        return value

    def write(self, name, value):
        (self.root / name).write_text(json.dumps(self.clean(value), indent=2, ensure_ascii=False) + "\n")

    def event(self, kind, **data):
        with (self.root / "trajectory.jsonl").open("a") as stream:
            stream.write(json.dumps(self.clean({"event": kind, "time": time.time(), **data}), ensure_ascii=False) + "\n")

    def image(self, path):
        path = Path(path).resolve()
        url = "data:image/png;base64," + base64.b64encode(path.read_bytes()).decode()
        self.images[url] = str(path.relative_to(self.root))
        return {"type": "image_url", "image_url": {"url": url}}
