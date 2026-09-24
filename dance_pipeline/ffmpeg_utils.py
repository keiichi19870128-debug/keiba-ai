"""ffmpeg の場所解決と小さなヘルパー."""
from __future__ import annotations

import re
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg

        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception as exc:  # pragma: no cover
        raise RuntimeError(
            "ffmpeg が見つかりません。`pip install imageio-ffmpeg` か OS の ffmpeg を入れてください。"
        ) from exc


def run(args: list[str], quiet: bool = True) -> subprocess.CompletedProcess:
    cmd = [ffmpeg_exe(), "-hide_banner", "-y"] + args
    if not quiet:
        print("  $ ffmpeg " + " ".join(args))
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg failed ({proc.returncode}):\n{proc.stderr[-3000:]}")
    return proc


def probe(path: str | Path) -> dict:
    """ffprobe 無しで duration / 解像度 / fps を取得する（ffmpeg -i の出力を解析）."""
    proc = subprocess.run(
        [ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True, text=True
    )
    err = proc.stderr
    info: dict = {"duration": None, "width": None, "height": None, "fps": None, "has_audio": False}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    m = re.search(r"Video:.*?(\d{2,5})x(\d{2,5})", err)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
    if m:
        info["fps"] = float(m.group(1))
    info["has_audio"] = "Audio:" in err
    return info


def extract_last_frame(video: str | Path, out_png: str | Path) -> Path:
    run(["-sseof", "-0.1", "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out_png)])
    return Path(out_png)
