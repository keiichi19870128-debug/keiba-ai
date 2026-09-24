from __future__ import annotations

import base64
import copy
import mimetypes
import os
from pathlib import Path


class Provider:
    name = "base"
    env_keys: tuple[str, ...] = ()
    max_prompt_chars = 2000

    def __init__(self, cfg: dict):
        self.cfg = cfg

    # ---- 認証情報 ----
    def env(self, key: str) -> str | None:
        v = os.environ.get(key)
        if v:
            return v.strip()
        # .env ファイル（リポジトリ直下, git 管理外）にも対応
        envf = Path(__file__).resolve().parents[2] / ".env"
        if envf.exists():
            for line in envf.read_text().splitlines():
                if line.strip().startswith(key + "="):
                    return line.split("=", 1)[1].strip().strip('"').strip("'")
        return None

    def available(self) -> tuple[bool, str]:
        missing = [k for k in self.env_keys if not self.env(k)]
        if missing:
            return False, f"環境変数 {', '.join(missing)} が未設定です"
        return True, "ok"

    # ---- 画像 ----
    @staticmethod
    def data_uri(path: Path) -> str:
        mime = mimetypes.guess_type(str(path))[0] or "image/png"
        return f"data:{mime};base64," + base64.b64encode(Path(path).read_bytes()).decode()

    @staticmethod
    def raw_b64(path: Path) -> str:
        return base64.b64encode(Path(path).read_bytes()).decode()

    # ---- API ----
    def build_request(self, *, prompt: str, negative_prompt: str, image: Path, end_image: Path | None,
                      duration: float) -> dict:
        raise NotImplementedError

    def submit(self, req: dict) -> str:
        raise NotImplementedError

    def poll(self, task_id: str) -> tuple[str, str | None, str | None]:
        """戻り値: (status in {"running","succeeded","failed"}, video_url, error)."""
        raise NotImplementedError

    # ドライラン表示用に巨大な base64 を省略
    @staticmethod
    def redact(req: dict) -> dict:
        def walk(x):
            if isinstance(x, dict):
                return {k: walk(v) for k, v in x.items()}
            if isinstance(x, list):
                return [walk(v) for v in x]
            if isinstance(x, str) and len(x) > 500 and (x.startswith("data:") or " " not in x[:200]):
                return f"<base64 {len(x)} chars>"
            return x
        return walk(copy.deepcopy(req))

    @staticmethod
    def check(resp) -> dict:
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:500]}")
        return resp.json()
