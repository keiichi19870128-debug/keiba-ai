"""生成クリップ(dance_XX.mp4)を正規化・結合し、元音源と同期した 1080x1920 の TikTok 用 MP4 を作る.

同期の考え方:
  各クリップの 0 秒 = その区間の開始秒。クロスフェード(xfade)は「前クリップの余り(尾)」と
  「次クリップの先頭」を区間境界から重ねるため、次クリップの振付は境界ちょうどから始まり、
  全体の長さ = 曲の長さ に一致する（音ズレが累積しない）。
"""
from __future__ import annotations

import json
import subprocess
import textwrap
from pathlib import Path

from .ffmpeg_utils import ffmpeg_exe, probe, run

W, H, FPS = 1080, 1920, 30
FONT_CANDIDATES = [
    "/usr/share/fonts/opentype/ipafont-gothic/ipag.ttf",
    "/usr/share/fonts/truetype/fonts-japanese-gothic.ttf",
    "/System/Library/Fonts/ヒラギノ角ゴシック W6.ttc",
    "C:/Windows/Fonts/meiryo.ttc",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]


def _font(size: int):
    from PIL import ImageFont

    for f in FONT_CANDIDATES:
        if Path(f).exists():
            try:
                return ImageFont.truetype(f, size)
            except Exception:
                continue
    return ImageFont.load_default()


def render_placeholder(seg: dict, ref_image: Path | None, out: Path, length: float, fps: int = FPS) -> Path:
    """AI クリップ未生成の区間用に、基準画像＋カウント表示の“絵コンテ動画”を作る（タイミング確認用）."""
    from PIL import Image, ImageDraw

    pw, ph = 540, 960
    if ref_image and Path(ref_image).exists():
        base = Image.open(ref_image).convert("RGB")
        scale = max(pw / base.width, ph / base.height)
        base = base.resize((int(base.width * scale) + 1, int(base.height * scale) + 1))
        l, t = (base.width - pw) // 2, (base.height - ph) // 2
        base = base.crop((l, t, l + pw, t + ph))
    else:
        base = Image.new("RGB", (pw, ph), (25, 25, 30))
    f_big, f_mid, f_small = _font(64), _font(26), _font(20)
    beats = [b["rel"] for b in seg["beats"]]
    downs = [b["rel"] for b in seg["beats"] if b["beat_in_bar"] == 1]
    n = int(round(length * fps))
    cmd = [ffmpeg_exe(), "-hide_banner", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{pw}x{ph}",
           "-r", str(fps), "-i", "-", "-vf", f"scale={W}:{H}:flags=lanczos,format=yuv420p",
           "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stderr=subprocess.DEVNULL)
    counts = {}
    first_db = next((i for i, b in enumerate(seg["beats"]) if b["beat_in_bar"] == 1), 0)
    for i, b in enumerate(seg["beats"]):
        counts[b["rel"]] = i - first_db + 1
    for k in range(n):
        t = k / fps
        # 拍に合わせて軽くズーム（強拍は大きめ）
        pulse = 0.0
        for bt in beats:
            d = t - bt
            if 0 <= d < 0.25:
                pulse = max(pulse, (0.035 if bt in downs else 0.015) * (1 - d / 0.25))
        z = 1 + pulse
        if pulse > 0:
            zw, zh = int(pw * z), int(ph * z)
            fr = base.resize((zw, zh))
            fr = fr.crop(((zw - pw) // 2, (zh - ph) // 2, (zw - pw) // 2 + pw, (zh - ph) // 2 + ph))
        else:
            fr = base.copy()
        d = ImageDraw.Draw(fr, "RGBA")
        d.rectangle([0, 0, pw, 70], fill=(0, 0, 0, 150))
        d.text((14, 10), f"{seg['id']}  {seg['section_ja']}", font=f_mid, fill=(255, 255, 255))
        d.text((14, 42), "PLACEHOLDER — AI clip not generated yet", font=f_small, fill=(255, 200, 80))
        # 現在のカウント
        cur = [c for bt, c in counts.items() if bt <= t + 1e-6]
        if cur:
            c = cur[-1]
            label = str(((c - 1) % 8) + 1) if c >= 1 else "・"
            d.text((pw - 90, 90), label, font=f_big, fill=(255, 255, 255, 230))
        # 現在のフェーズ説明
        ph_cur = [p for p in seg["phases"] if p["t_start"] <= t < p["t_end"] + 1e-6]
        d.rectangle([0, ph - 220, pw, ph], fill=(0, 0, 0, 170))
        d.text((14, ph - 210), seg["move_name"].split("※")[0].strip(), font=f_mid, fill=(120, 220, 255))
        if seg.get("is_hook"):
            d.text((pw - 170, ph - 250), "★ポイント振付", font=f_small, fill=(255, 220, 90))
        if ph_cur:
            txt = "\n".join(textwrap.wrap(ph_cur[-1]["ja"], 22)[:5])
            d.multiline_text((14, ph - 172), txt, font=f_small, fill=(255, 255, 255), spacing=6)
        proc.stdin.write(fr.tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        raise RuntimeError(f"placeholder render failed: {out}")
    return out


def normalize_clip(src: Path, dst: Path, seg_len: float, need_len: float, max_stretch: float = 1.2) -> dict:
    """1080x1920/30fps に揃え、区間長に合わせてトリム・（必要なら）軽いスロー・末尾フリーズ延長."""
    info = probe(src)
    D = info["duration"] or seg_len
    factor = 1.0
    if D < seg_len:
        factor = min(seg_len / D, max_stretch)
    stretched = D * factor
    pad = max(0.0, need_len - stretched) + 0.1
    vf = (
        f"setpts={factor:.5f}*(PTS-STARTPTS),fps={FPS},"
        f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H},setsar=1,"
        f"tpad=stop_mode=clone:stop_duration={pad:.3f},trim=duration={need_len:.3f},setpts=PTS-STARTPTS,format=yuv420p"
    )
    run(["-i", str(src), "-an", "-vf", vf, "-c:v", "libx264", "-preset", "fast", "-crf", "14", "-r", str(FPS), str(dst)])
    return {"src_duration": round(D, 3), "stretch": round(factor, 4), "frozen_tail": round(max(0.0, need_len - stretched), 3)}


def assemble(segments: list[dict], audio: Path, clips_dir: Path, out_path: Path, work_dir: Path,
             ref_image: Path | None = None, xfade: float = 0.2, allow_placeholders: bool = True,
             max_stretch: float = 1.2, duration: float | None = None) -> dict:
    work_dir.mkdir(parents=True, exist_ok=True)
    report = {"output": str(out_path), "segments": [], "placeholders": []}
    norm_paths = []
    for i, seg in enumerate(segments):
        last = i == len(segments) - 1
        need = seg["duration"] + (0 if last else xfade)
        src = clips_dir / f"{seg['id']}.mp4"
        entry = {"id": seg["id"], "start": seg["start"], "end": seg["end"]}
        if not src.exists():
            if not allow_placeholders:
                raise FileNotFoundError(f"クリップがありません: {src}")
            src = work_dir / f"placeholder_{seg['id']}.mp4"
            render_placeholder(seg, ref_image, src, need + 0.1)
            report["placeholders"].append(seg["id"])
            entry["placeholder"] = True
        dst = work_dir / f"norm_{seg['id']}.mp4"
        entry.update(normalize_clip(src, dst, seg["duration"], need, max_stretch))
        report["segments"].append(entry)
        norm_paths.append(dst)

    total = duration or segments[-1]["end"]
    args: list[str] = []
    for p in norm_paths:
        args += ["-i", str(p)]
    args += ["-i", str(audio)]
    a_idx = len(norm_paths)
    if len(norm_paths) == 1:
        fc = "[0:v]null[v]"
    elif xfade > 0:
        parts, cur = [], "[0:v]"
        for k in range(1, len(norm_paths)):
            off = segments[k]["start"] - segments[0]["start"]
            outl = "[v]" if k == len(norm_paths) - 1 else f"[x{k}]"
            parts.append(f"{cur}[{k}:v]xfade=transition=fade:duration={xfade:.3f}:offset={off:.3f}{outl}")
            cur = outl
        fc = ";".join(parts)
    else:
        fc = "".join(f"[{k}:v]" for k in range(len(norm_paths))) + f"concat=n={len(norm_paths)}:v=1:a=0[v]"
    fc += f";[{a_idx}:a]aresample=48000,apad[a]"
    args += [
        "-filter_complex", fc, "-map", "[v]", "-map", "[a]", "-t", f"{total:.3f}",
        "-c:v", "libx264", "-preset", "medium", "-crf", "18", "-profile:v", "high", "-level", "4.1",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-g", str(FPS * 2),
        "-c:a", "aac", "-b:a", "192k", "-ar", "48000", "-movflags", "+faststart",
        str(out_path),
    ]
    run(args)
    info = probe(out_path)
    report["final"] = info
    (work_dir / "assemble_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2))
    return report
