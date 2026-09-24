from __future__ import annotations

import filecmp
import json
import shutil
import time
from pathlib import Path

_STAMP = time.strftime("%Y%m%d-%H%M%S")


def safe_write(path: Path, content: str | bytes, history_root: Path | None = None) -> Path:
    """既存ファイルは削除せず output/_history/<時刻>/ に退避してから書き込む（内容が同じなら何もしない）."""
    path.parent.mkdir(parents=True, exist_ok=True)
    data = content.encode() if isinstance(content, str) else content
    if path.exists():
        if path.read_bytes() == data:
            return path
        backup_existing(path, history_root)
    path.write_bytes(data)
    return path


def backup_existing(path: Path, history_root: Path | None = None) -> Path | None:
    if not path.exists():
        return None
    root = history_root or (path.parent / "_history")
    dst = root / _STAMP / path.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dst))
    return dst


def write_json(path: Path, obj, history_root: Path | None = None) -> Path:
    return safe_write(path, json.dumps(obj, ensure_ascii=False, indent=2) + "\n", history_root)
