"""Runway API (image_to_video).

認証: `Authorization: Bearer $RUNWAYML_API_SECRET` + `X-Runway-Version` ヘッダー。
promptText は 1000 文字上限 → 短縮版プロンプトを使用。
"""
from __future__ import annotations

import requests

from .base import Provider

BASE = "https://api.dev.runwayml.com"


class RunwayProvider(Provider):
    name = "runway"
    env_keys = ("RUNWAYML_API_SECRET",)
    max_prompt_chars = 1000

    def headers(self):
        return {"Authorization": f"Bearer {self.env('RUNWAYML_API_SECRET')}",
                "X-Runway-Version": self.cfg.get("api_version", "2024-11-06"),
                "Content-Type": "application/json"}

    def build_request(self, *, prompt, negative_prompt, image, end_image, duration):
        img = self.cfg.get("image_url") or self.data_uri(image)
        if end_image is not None and self.cfg.get("supports_last_frame", False):
            prompt_image = [{"uri": img, "position": "first"},
                            {"uri": self.cfg.get("image_url") or self.data_uri(end_image), "position": "last"}]
        else:
            prompt_image = img
        return {
            "model": self.cfg.get("model", "gen4_turbo"),
            "promptImage": prompt_image,
            "promptText": prompt[: self.max_prompt_chars],
            "ratio": self.cfg.get("ratio", "720:1280"),
            "duration": int(duration),
        }

    def submit(self, req):
        js = self.check(requests.post(f"{BASE}/v1/image_to_video", headers=self.headers(), json=req, timeout=120))
        return js["id"]

    def poll(self, task_id):
        js = self.check(requests.get(f"{BASE}/v1/tasks/{task_id}", headers=self.headers(), timeout=60))
        st = js.get("status")
        if st == "SUCCEEDED":
            out = js.get("output") or []
            return "succeeded", out[0] if out else None, None
        if st in ("FAILED", "CANCELLED"):
            return "failed", None, js.get("failure") or js.get("failureCode") or st
        return "running", None, None
