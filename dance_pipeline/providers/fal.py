"""fal.ai キュー API（Kling / Pika / Hailuo などを 1 つのキーで利用できるアグリゲーター）.

認証: `Authorization: Key $FAL_KEY`
config.json の providers.fal.model にモデル ID（例: fal-ai/kling-video/v2.1/pro/image-to-video,
fal-ai/pika/v2.2/image-to-video）を指定。
"""
from __future__ import annotations

import requests

from .base import Provider

QUEUE = "https://queue.fal.run"


class FalProvider(Provider):
    name = "fal"
    env_keys = ("FAL_KEY",)
    max_prompt_chars = 2000

    def headers(self):
        return {"Authorization": f"Key {self.env('FAL_KEY')}", "Content-Type": "application/json"}

    @property
    def model(self) -> str:
        return self.cfg.get("model", "fal-ai/kling-video/v2.1/pro/image-to-video")

    def build_request(self, *, prompt, negative_prompt, image, end_image, duration):
        body = {
            "prompt": prompt[: self.max_prompt_chars],
            "image_url": self.cfg.get("image_url") or self.data_uri(image),
            "duration": str(int(duration)),
            "negative_prompt": negative_prompt,
        }
        if "pika" in self.model:
            body.pop("negative_prompt")
            body["aspect_ratio"] = "9:16"
            body["resolution"] = self.cfg.get("resolution", "720p")
            body["duration"] = int(duration)
        if end_image is not None and "kling" in self.model and self.cfg.get("supports_tail", True):
            body["tail_image_url"] = self.cfg.get("image_url") or self.data_uri(end_image)
        return {"_model": self.model, **body}

    def submit(self, req):
        body = {k: v for k, v in req.items() if k != "_model"}
        js = self.check(requests.post(f"{QUEUE}/{req['_model']}", headers=self.headers(), json=body, timeout=120))
        return js["status_url"] + "|" + js["response_url"]

    def poll(self, task_id):
        status_url, response_url = task_id.split("|", 1)
        js = self.check(requests.get(status_url, headers=self.headers(), timeout=60))
        st = js.get("status")
        if st == "COMPLETED":
            res = self.check(requests.get(response_url, headers=self.headers(), timeout=60))
            if res.get("detail"):
                return "failed", None, str(res["detail"])[:500]
            return "succeeded", (res.get("video") or {}).get("url"), None
        if st in ("FAILED", "ERROR"):
            return "failed", None, str(js)[:500]
        return "running", None, None
