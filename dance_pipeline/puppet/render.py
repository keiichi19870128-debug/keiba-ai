"""2D パペットの区間クリップ（dance_XX.mp4）をローカルでレンダリングする（無料・API 不要）."""
from __future__ import annotations

import json
import math
import multiprocessing as mp
import os
import subprocess
from pathlib import Path

import cv2
import numpy as np

from ..ffmpeg_utils import ffmpeg_exe
from .deform import render_pose
from .motion import build_timeline, pose_at
from .rig import build_rig

OUT_W, OUT_H, FPS = 1080, 1920, 30
_G: dict = {}


def _init(rig_cache: str, image: str, plan_path: str, analysis_path: str):
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    cv2.setNumThreads(1)
    rig = build_rig(Path(image), cache=Path(rig_cache))
    plan = json.loads(Path(plan_path).read_text())
    analysis = json.loads(Path(analysis_path).read_text())
    segs = plan["segments"]
    bg = rig["bg"].astype(np.float32)
    lum = cv2.cvtColor(rig["bg"], cv2.COLOR_BGR2GRAY)
    glow = cv2.GaussianBlur((lum > 200).astype(np.float32), (0, 0), 25)
    glow = glow / max(glow.max(), 1e-6)
    H, W = lum.shape
    yy, xx = np.mgrid[0:OUT_H, 0:OUT_W].astype(np.float32)
    vig = 1 - 0.28 * (((xx - OUT_W / 2) / (OUT_W / 2)) ** 2 + ((yy - OUT_H / 2) / (OUT_H / 2)) ** 2) ** 1.2
    j = rig["joints"]
    _G.update(rig=rig, segs=segs, analysis=analysis, tl=build_timeline(segs, analysis), glow=glow[..., None],
              vig=np.clip(vig, 0, 1)[..., None], center=(float(j["pelvis"][0]), float(j["neck"][1] + 150)), bg=bg)


def _label_at(t: float, analysis: dict) -> str:
    for s in analysis["sections"]:
        if s["start"] <= t < s["end"]:
            return s["label"]
    return analysis["sections"][-1]["label"]


def _fx(t: float) -> dict:
    a = _G["analysis"]
    segs = _G["segs"]
    lab = _label_at(t, a)
    zoom, flash, shake, glow, desat, dark = 1.0, 0.0, 0.0, 0.10, 0.0, 0.0
    hot = lab in ("chorus", "final_chorus")
    # 強拍ごとのズームパンチ・ライトの明滅
    for db in a["downbeats"]:
        d = t - db
        if 0 <= d < 0.6 and (hot or lab == "pre_chorus"):
            zoom += (0.022 if hot else 0.012) * math.exp(-d / 0.16)
    for b in a["beats"]:
        d = t - b["time"]
        if 0 <= d < 0.5 and hot:
            glow += 0.35 * math.exp(-d / 0.18)
    # セクション頭（サビ頭・ドロップ）: フラッシュ + 大きめのズーム、ドロップは揺れ
    for s in a["sections"][1:]:
        d = t - s["start"]
        if 0 <= d < 0.8 and s["label"] in ("chorus", "final_chorus") and s.get("chorus_part") != "B":
            flash += 0.45 * math.exp(-d / 0.12)
            zoom += 0.05 * math.exp(-d / 0.25)
            if s["label"] == "final_chorus":
                shake += 12 * math.exp(-d / 0.3)
    # サビ前はじわじわ寄る / ブレイクはモノクロ気味に暗く / エンディングはゆっくり寄る
    for s in a["sections"]:
        if s["start"] <= t < s["end"]:
            u = (t - s["start"]) / (s["end"] - s["start"])
            if s["label"] == "pre_chorus":
                zoom += 0.045 * u
            if s["label"] == "break":
                desat, dark = 0.85, 0.22
                zoom += 0.03 * u
            if s["label"] == "chorus":
                glow += 0.12
    last = segs[-1]
    fin = max(k[0] for k in _G["tl"]["keys"])
    if t >= fin:
        zoom += 0.05 * min((t - fin) / 1.8, 1.0)
        d = t - fin
        flash += 0.3 * math.exp(-d / 0.1) if d < 0.5 else 0
    # 最後 0.35 秒でやや暗く
    if t > last["end"] - 0.35:
        dark = max(dark, (t - (last["end"] - 0.35)) / 0.35 * 0.35)
    return dict(zoom=zoom, flash=flash, shake=shake, glow=glow, desat=desat, dark=dark)


def render_frame(t: float) -> bytes:
    rig = _G["rig"]
    p = pose_at(t, _G["tl"], _G["analysis"], _G["segs"])
    img = render_pose(rig, p)
    fx = _fx(t)
    img = img + _G["glow"] * fx["glow"] * np.array([180, 215, 255], np.float32)  # BGR（暖色）
    cx, cy = _G["center"]
    s = OUT_W / img.shape[1] * fx["zoom"]
    dx = fx["shake"] * math.sin(t * 2 * math.pi * 17)
    dy = fx["shake"] * 0.6 * math.cos(t * 2 * math.pi * 13)
    # 注視点（上半身）を中心にズーム
    tx = OUT_W / 2 - s * cx + (cx * OUT_W / img.shape[1] - OUT_W / 2) * (1 - 1 / fx["zoom"]) * 0 + dx
    ty = OUT_H / 2 - s * cy + (cy * OUT_H / img.shape[0] - OUT_H / 2) + dy
    tx += (cx * OUT_W / img.shape[1] - OUT_W / 2)
    M = np.array([[s, 0, tx], [0, s, ty]], np.float32)
    out = cv2.warpAffine(img, M, (OUT_W, OUT_H), flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
    if fx["desat"]:
        g = out.mean(2, keepdims=True)
        out = out * (1 - fx["desat"]) + g * fx["desat"]
    out = out * _G["vig"]
    if fx["dark"]:
        out = out * (1 - fx["dark"])
    if fx["flash"]:
        out = out * (1 - fx["flash"]) + 255 * fx["flash"]
    return np.clip(out, 0, 255).astype(np.uint8).tobytes()


def render_range(t0: float, t1: float, out: Path, ctx: tuple, workers: int | None = None) -> Path:
    n = int(round((t1 - t0) * FPS))
    times = [t0 + i / FPS for i in range(n)]
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgr24",
           "-s", f"{OUT_W}x{OUT_H}", "-r", str(FPS), "-i", "-", "-c:v", "libx264", "-preset", "medium",
           "-crf", "16", "-pix_fmt", "yuv420p", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    workers = workers or max(1, (os.cpu_count() or 2))
    with mp.get_context("fork").Pool(workers, initializer=_init, initargs=ctx) as pool:
        for fr in pool.imap(render_frame, times, chunksize=4):
            proc.stdin.write(fr)
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError("ffmpeg encode failed")
    return out


def render_segments(root: Path, plan: dict, cfg: dict, only: list[int] | None = None, force: bool = False,
                    tail: float = 0.4) -> dict:
    od = root / cfg.get("output_dir", "output")
    clips = od / "clips"
    clips.mkdir(parents=True, exist_ok=True)
    image = root / plan["reference_image"]
    cache = od / "_work" / "rig.npz"
    build_rig(image, cache=cache)  # 1 回だけ構築してキャッシュ
    ctx = (str(cache), str(image), str(od / "segments.json"), str(od / "audio_analysis.json"))
    done, skipped = [], []
    for seg in plan["segments"]:
        if only and seg["index"] not in only:
            continue
        dst = clips / f"{seg['id']}.mp4"
        if dst.exists() and not force:
            skipped.append(seg["id"])
            continue
        if dst.exists():
            old = clips / "_old"
            old.mkdir(exist_ok=True)
            dst.rename(old / dst.name)
        end = seg["end"] + (0 if seg["is_last"] else tail)
        print(f"[local] {seg['id']}: {seg['start']:.2f}-{end:.2f}s をレンダリング中 ...", flush=True)
        render_range(seg["start"], end, dst, ctx)
        done.append(seg["id"])
    print(f"[local] 完了: 生成 {len(done)} / スキップ {len(skipped)}")
    return {"provider": "local", "done": done, "skipped": skipped, "failed": []}
