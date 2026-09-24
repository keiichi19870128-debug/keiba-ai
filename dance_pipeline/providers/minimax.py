"""MiniMax (Hailuo) 動画生成 API.

認証: `Authorization: Bearer $MINIMAX_API_KEY`（中国本土版は MINIMAX_API_BASE=https://api.minimaxi.com）
"""
from __future__ import annotations

import requests

from .base import Provider

DEFAULT_BASE = "https://api.minimax.io"


class MiniMaxProvider(Provider):
    name = "minimax"
    env_keys = ("MINIMAX_API_KEY",)
    max_prompt_chars = 2000

    @property
    def base(self):
        return (self.env("MINIMAX_API_BASE") or self.cfg.get("base_url") or DEFAULT_BASE).rstrip("/")

    def headers(self):
        return {"Authorization": f"Bearer {self.env('MINIMAX_API_KEY')}", "Content-Type": "application/json"}

    def build_request(self, *, prompt, negative_prompt, image, end_image, duration):
        body = {
            "model": self.cfg.get("model", "MiniMax-Hailuo-02"),
            "prompt": prompt[: self.max_prompt_chars],
            "first_frame_image": self.cfg.get("image_url") or self.data_uri(image),
            "duration": int(duration),
            "resolution": self.cfg.get("resolution", "768P"),
            "prompt_optimizer": self.cfg.get("prompt_optimizer", False),
        }
        if end_image is not None and self.cfg.get("supports_last_frame", False):
            body["last_frame_image"] = self.data_uri(end_image)
        return body

    def submit(self, req):
        js = self.check(requests.post(f"{self.base}/v1/video_generation", headers=self.headers(), json=req, timeout=120))
        br = js.get("base_resp") or {}
        if br.get("status_code", 0) != 0:
            raise RuntimeError(f"MiniMax error {br.get('status_code')}: {br.get('status_msg')}")
        return js["task_id"]

    def poll(self, task_id):
        js = self.check(requests.get(f"{self.base}/v1/query/video_generation", params={"task_id": task_id},
                                     headers=self.headers(), timeout=60))
        st = js.get("status")
        if st == "Success":
            fr = self.check(requests.get(f"{self.base}/v1/files/retrieve", params={"file_id": js["file_id"]},
                                         headers=self.headers(), timeout=60))
            return "succeeded", fr["file"]["download_url"], None
        if st == "Fail":
            return "failed", None, (js.get("base_resp") or {}).get("status_msg") or "Fail"
        return "running", None, None
