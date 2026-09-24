"""動画生成サービスのクライアント（すべて requests のみで実装、SDK 不要）."""
from __future__ import annotations

from .base import Provider


def get_provider(name: str, cfg: dict) -> Provider:
    name = name.lower()
    if name == "kling":
        from .kling import KlingProvider as P
    elif name == "runway":
        from .runway import RunwayProvider as P
    elif name in ("minimax", "hailuo"):
        from .minimax import MiniMaxProvider as P
    elif name == "luma":
        from .luma import LumaProvider as P
    elif name in ("fal", "pika"):
        from .fal import FalProvider as P
    else:
        raise ValueError(f"unknown provider: {name}")
    return P(cfg)
