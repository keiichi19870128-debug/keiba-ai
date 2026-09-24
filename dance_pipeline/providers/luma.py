"""Luma Dream Machine API.

認証: `Authorization: Bearer $LUMAAI_API_KEY`
注意: キーフレーム画像は公開 URL のみ（Base64 不可）。config.json の providers.luma.image_url に
      基準画像の公開 URL を設定してください。
"""
from __future__ import annotations

import requests

from .base import Provider

BASE = "https://api.lumalabs.ai/dream-machine/v1"


class LumaProvider(Provider):
    name = "luma"
    env_keys = ("LUMAAI_API_KEY",)
    max_prompt_chars = 2000

    def available(self):
        ok, why = super().available()
        if ok and not self.cfg.get("image_url"):
            return False, "Luma は画像の公開 URL が必要です（config.json の providers.luma.image_url）"
        return ok, why

    def headers(self):
        return {"Authorization": f"Bearer {self.env('LUMAAI_API_KEY')}", "Content-Type": "application/json"}

    def build_request(self, *, prompt, negative_prompt, image, end_image, duration):
        url = self.cfg.get("image_url") or f"<PUBLIC URL OF {image.name}>"
        kf = {"frame0": {"type": "image", "url": url}}
        if end_image is not None:
            kf["frame1"] = {"type": "image", "url": url}
        return {
            "model": self.cfg.get("model", "ray-2"),
            "prompt": prompt[: self.max_prompt_chars],
            "aspect_ratio": "9:16",
            "resolution": self.cfg.get("resolution", "720p"),
            "duration": f"{int(duration)}s",
            "keyframes": kf,
        }

    def submit(self, req):
        js = self.check(requests.post(f"{BASE}/generations", headers=self.headers(), json=req, timeout=120))
        return js["id"]

    def poll(self, task_id):
        js = self.check(requests.get(f"{BASE}/generations/{task_id}", headers=self.headers(), timeout=60))
        st = js.get("state")
        if st == "completed":
            return "succeeded", (js.get("assets") or {}).get("video"), None
        if st == "failed":
            return "failed", None, js.get("failure_reason") or "failed"
        return "running", None, None
