"""ログ・ffmpeg 呼び出し・設定読み込みなどの共通処理."""
from __future__ import annotations

import copy
import json
import logging
import re
import shutil
import subprocess
import sys
import tempfile
import time
from functools import lru_cache
from pathlib import Path

log = logging.getLogger("tiktok")

# ---------------------------------------------------------------------------
# 既定設定（config.json の "lyrics_video" で上書きされる。書かなかった項目はこの値）
# ---------------------------------------------------------------------------
DEFAULTS: dict = {
    "input_dir": "input",
    "output_dir": "output",
    "output_name": "final_tiktok.mp4",
    "keep_history": True,
    "files": {"audio": None, "lyrics": None, "background": None},
    "video": {
        "width": 1080,
        "height": 1920,
        "fps": 30,
        "crf": 18,
        "preset": "slow",
        "audio_bitrate": "320k",
        "audio_sample_rate": "source",
        "fade_in_sec": 0.4,
        "fade_out_sec": 1.2,
    },
    "background": {
        "brightness": 0.78,
        "saturation": 1.0,
        "contrast": 1.0,
        "blur": 0,
        "vignette": True,
        "text_scrim": 0.28,
        "fit": "cover",
        "video_start_sec": 0.0,
        "loop_crossfade_sec": 1.0,
        "image_motion": "auto",
        "image_zoom": 1.15,
        "image_crossfade_sec": 1.2,
        "motion_seed": 0,
    },
    "font": {"file": "auto", "name": "auto", "size": 92, "bold": True},
    "subtitle": {
        "position_y": 0.60,
        "margin_x": 90,
        "safe_top": 0.14,
        "safe_bottom": 0.24,
        "max_lines": 2,
        "max_chars_per_line": 0,
        "phrase_max_chars": 12,
        "line_spacing": 0.18,
        "letter_spacing": 1,
        "primary_color": "#FFFFFF",
        "outline_color": "#000000",
        "outline": 6,
        "outline_blur": 1.5,
        "shadow": 3,
        "shadow_color": "#000000",
        "shadow_alpha": 0.55,
        "animation": "slide_up",
        "fade_in_ms": 180,
        "fade_out_ms": 160,
        "lead_in_sec": 0.12,
        "hold_sec": 0.45,
        "min_duration": 0.8,
        "max_duration": 6.0,
        "gap_sec": 0.06,
        "beat_snap": True,
        "beat_snap_tolerance": 0.16,
    },
    "chorus": {
        "enabled": True,
        "detect": "auto",
        "scale": 1.15,
        "animation": "pop",
        "color": None,
    },
    "emphasis": {
        "enabled": True,
        "auto": True,
        "words": [],
        "scale": 1.28,
        "color": "#FFE45C",
        "max_auto_words": 6,
        "max_per_phrase": 1,
    },
    "timing": {
        "method": "auto",
        "whisper_model": "small",
        "language": "ja",
        "device": "auto",
        "compute_type": "auto",
        "vocal_separation": "auto",
        "use_lyrics_prompt": True,
        "min_match_ratio": 0.2,
        "offset_sec": 0.0,
    },
    "variants": 1,
}


def deep_merge(base: dict, over: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in (over or {}).items():
        if k.startswith("_"):
            continue  # "_説明" などのコメント用キー
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = deep_merge(out[k], v)
        else:
            out[k] = v
    return out


def load_config(path: Path) -> dict:
    """config.json の "lyrics_video" セクションを読み、既定値とマージする."""
    if not path.exists():
        print(f"[注意] 設定ファイル {path} が無いため既定値で実行します")
        return copy.deepcopy(DEFAULTS)
    try:
        raw = json.loads(path.read_text(encoding="utf-8-sig"))
    except json.JSONDecodeError as exc:
        raise SystemExit(
            f"config.json の書式エラー: {exc}\n"
            "  → カンマの付け忘れ/付けすぎ、\" の閉じ忘れを確認してください。"
        ) from exc
    section = raw.get("lyrics_video", {})
    return deep_merge(DEFAULTS, section)


# ---------------------------------------------------------------------------
# ログ
# ---------------------------------------------------------------------------
def setup_logging(log_dir: Path, verbose: bool = False) -> Path:
    """コンソール + output/logs/generate_<時刻>.log の両方に出す."""
    for stream in (sys.stdout, sys.stderr):
        try:  # Windows のコンソール (cp932) で表示できない文字があっても落ちないように
            stream.reconfigure(errors="replace")
        except Exception:
            pass
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"generate_{time.strftime('%Y%m%d_%H%M%S')}.log"
    log.setLevel(logging.DEBUG)
    log.handlers.clear()
    fh = logging.FileHandler(log_path, encoding="utf-8")
    fh.setLevel(logging.DEBUG)
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.DEBUG if verbose else logging.INFO)
    ch.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(fh)
    log.addHandler(ch)
    return log_path


class StepError(RuntimeError):
    """原因とヒント付きのエラー（最後に分かりやすく表示する）."""

    def __init__(self, message: str, hint: str = ""):
        super().__init__(message)
        self.hint = hint


# ---------------------------------------------------------------------------
# ffmpeg
# ---------------------------------------------------------------------------
@lru_cache(maxsize=1)
def ffmpeg_exe() -> str:
    """システムの ffmpeg（libass 入り）→ imageio-ffmpeg 同梱版の順に探す."""
    cands: list[str] = []
    sys_ff = shutil.which("ffmpeg")
    if sys_ff:
        cands.append(sys_ff)
    try:
        import imageio_ffmpeg

        cands.append(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:
        pass
    for exe in cands:
        if _has_filters(exe, ("ass", "zoompan", "xfade")):
            return exe
    if cands:
        raise StepError(
            f"ffmpeg は見つかりましたが字幕描画 (libass) に対応していません: {cands}",
            "`pip install -U imageio-ffmpeg` を実行するか、https://www.gyan.dev/ffmpeg/builds/ の "
            "full 版 ffmpeg を入れて PATH を通してください。",
        )
    raise StepError(
        "ffmpeg が見つかりません。",
        "`pip install imageio-ffmpeg` を実行するか、winget install Gyan.FFmpeg で ffmpeg を入れてください。",
    )


def _has_filters(exe: str, names: tuple[str, ...]) -> bool:
    try:
        out = subprocess.run([exe, "-hide_banner", "-filters"], capture_output=True, timeout=30,
                             encoding="utf-8", errors="replace").stdout
    except Exception:
        return False
    return all(re.search(rf"^\s*\S+\s+{n}\s", out, re.M) for n in names)


def run_ffmpeg(args: list[str], what: str, cwd: Path | None = None, total: float | None = None) -> None:
    """ffmpeg を実行。コマンドと出力は全てログファイルに残す. total（秒）を渡すと進捗 % を表示."""
    cmd = [ffmpeg_exe(), "-hide_banner", "-nostdin", "-y", "-loglevel", "warning", "-nostats"]
    if total:
        cmd += ["-progress", "pipe:1"]
    cmd += [str(a) for a in args]
    log.debug("[ffmpeg:%s] cwd=%s\n  %s", what, cwd, subprocess.list2cmdline(cmd))
    t0 = time.time()
    with tempfile.TemporaryFile() as errf:
        proc = subprocess.Popen(cmd, cwd=str(cwd) if cwd else None, stdout=subprocess.PIPE, stderr=errf)
        last = -1
        for raw in proc.stdout:  # -progress の出力: out_time_us=12345678
            if not total:
                continue
            line = raw.decode("ascii", "ignore").strip()
            if line.startswith("out_time_us=") and line[12:].isdigit():
                pct = min(100, int(int(line[12:]) / 1e6 / total * 100))
                if pct != last and sys.stdout.isatty():
                    sys.stdout.write(f"\r    {what}: {pct:3d}%  ({time.time() - t0:.0f}s)")
                    sys.stdout.flush()
                last = pct
        proc.wait()
        if total and sys.stdout.isatty():
            sys.stdout.write("\r" + " " * 60 + "\r")
        errf.seek(0)
        err = errf.read().decode("utf-8", "replace")
    log.debug("[ffmpeg:%s] exit=%s %.1fs\n%s", what, proc.returncode, time.time() - t0, err[-6000:])
    if proc.returncode != 0:
        tail = "\n".join(err.strip().splitlines()[-15:])
        raise StepError(f"ffmpeg ({what}) が失敗しました:\n{tail}",
                        "ログファイルに実行コマンドと全出力があります。素材ファイルが壊れていないか、"
                        "ディスク容量が足りているかを確認してください。")


def probe(path: Path) -> dict:
    """ffprobe 無しで長さ・解像度・fps・音声コーデックを取得する（ffmpeg -i の出力を解析）."""
    proc = subprocess.run([ffmpeg_exe(), "-hide_banner", "-i", str(path)], capture_output=True,
                          encoding="utf-8", errors="replace")
    err = proc.stderr
    info: dict = {"duration": None, "width": None, "height": None, "fps": None,
                  "audio_codec": None, "sample_rate": None, "rotation": 0}
    m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", err)
    if m:
        h, mi, s = m.groups()
        info["duration"] = int(h) * 3600 + int(mi) * 60 + float(s)
    m = re.search(r"Video:.*?,\s*(\d{2,5})x(\d{2,5})", err)
    if m:
        info["width"], info["height"] = int(m.group(1)), int(m.group(2))
    m = re.search(r"(\d+(?:\.\d+)?)\s*fps", err)
    if m:
        info["fps"] = float(m.group(1))
    m = re.search(r"Audio:\s*(\w+).*?(\d{4,6})\s*Hz", err)
    if m:
        info["audio_codec"], info["sample_rate"] = m.group(1), int(m.group(2))
    m = re.search(r"rotation of (-?\d+(?:\.\d+)?)", err) or re.search(r"rotate\s*:\s*(-?\d+)", err)
    if m:
        info["rotation"] = int(float(m.group(1))) % 360
    return info


def backup_existing(path: Path, history_dir: Path, stamp: str) -> Path | None:
    """既存ファイルは削除せず output/_history/<時刻>/ へ移動する."""
    if not path.exists():
        return None
    dst = history_dir / stamp / path.name
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(path), str(dst))
    log.debug("既存ファイルを退避: %s -> %s", path, dst)
    return dst


def hex_to_ass(color: str, alpha: float = 0.0) -> str:
    """#RRGGBB → ASS の &HAABBGGRR（alpha は 0=不透明, 1=透明）."""
    c = (color or "#FFFFFF").lstrip("#")
    if len(c) == 8:  # #RRGGBBAA が来たら AA を不透明度として扱う
        alpha = 1 - int(c[6:8], 16) / 255
        c = c[:6]
    if len(c) != 6:
        raise StepError(f"色の指定が不正です: {color}", "#RRGGBB 形式（例: #FFFFFF）で指定してください。")
    r, g, b = c[0:2], c[2:4], c[4:6]
    a = max(0, min(255, round(alpha * 255)))
    return f"&H{a:02X}{b}{g}{r}".upper()
