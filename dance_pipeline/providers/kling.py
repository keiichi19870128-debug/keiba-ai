"""Kling AI 公式 API (image2video).

認証: AccessKey / SecretKey から HS256 の JWT を生成し `Authorization: Bearer <jwt>`。
環境変数: KLING_ACCESS_KEY, KLING_SECRET_KEY（任意: KLING_API_BASE）
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time

import requests

from .base import Provider

DEFAULT_BASE = "https://api-singapore.klingai.com"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode()


def make_jwt(ak: str, sk: str, ttl: int = 1800) -> str:
    header = {"alg": "HS256", "typ": "JWT"}
    now = int(time.time())
    payload = {"iss": ak, "exp": now + ttl, "nbf": now - 5}
    msg = _b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + \
        _b64url(json.dumps(payload, separators=(",", ":")).encode())
    sig = hmac.new(sk.encode(), msg.encode(), hashlib.sha256).digest()
    return msg + "." + _b64url(sig)


class KlingProvider(Provider):
    name = "kling"
    env_keys = ("KLING_ACCESS_KEY", "KLING_SECRET_KEY")
    max_prompt_chars = 2500

    @property
    def base(self) -> str:
        return (self.env("KLING_API_BASE") or self.cfg.get("base_url") or DEFAULT_BASE).rstrip("/")

    def headers(self) -> dict:
        return {"Authorization": "Bearer " + make_jwt(self.env("KLING_ACCESS_KEY"), self.env("KLING_SECRET_KEY")),
                "Content-Type": "application/json"}

    def build_request(self, *, prompt, negative_prompt, image, end_image, duration):
        body = {
            "model_name": self.cfg.get("model", "kling-v2-1"),
            "mode": self.cfg.get("mode", "pro"),
            "image": self.raw_b64(image),  # Kling は data: プレフィックス無しの Base64 か URL
            "prompt": prompt[: self.max_prompt_chars],
            "negative_prompt": negative_prompt[:2500],
            "cfg_scale": self.cfg.get("cfg_scale", 0.5),
            "duration": str(int(duration)),
        }
        if end_image is not None and self.cfg.get("supports_image_tail", True):
            body["image_tail"] = self.raw_b64(end_image)
        return body

    def submit(self, req):
        r = requests.post(f"{self.base}/v1/videos/image2video", headers=self.headers(), json=req, timeout=120)
        js = self.check(r)
        if js.get("code") not in (0, None):
            raise RuntimeError(f"Kling error {js.get('code')}: {js.get('message')}")
        return js["data"]["task_id"]

    def poll(self, task_id):
        r = requests.get(f"{self.base}/v1/videos/image2video/{task_id}", headers=self.headers(), timeout=60)
        js = self.check(r)
        d = js.get("data") or {}
        st = d.get("task_status")
        if st == "succeed":
            vids = (d.get("task_result") or {}).get("videos") or []
            return "succeeded", vids[0]["url"] if vids else None, None
        if st == "failed":
            return "failed", None, d.get("task_status_msg") or js.get("message")
        return "running", None, None
