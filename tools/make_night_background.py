#!/usr/bin/env python3
"""「深夜・雨の窓・にじむ街の灯り」の背景動画（シームレスループ）を生成する.

著作権フリーの背景素材が手元に無いとき用。写真を使わずに全部プログラムで描くので、
そのまま TikTok に使っても権利の心配がありません。

    python tools/make_night_background.py                     # input/background.mp4 を作成
    python tools/make_night_background.py --seed 3 --out input/bg_night.mp4 --seconds 16

すべての動き（灯りの揺らぎ・窓を伝う雨粒・外の雨）は --seconds 周期で一周するので、
generate_tiktok.py でループしても継ぎ目が目立ちません。
"""
from __future__ import annotations

import argparse
import math
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from lyrics_video.common import ffmpeg_exe  # noqa: E402

PALETTES = {
    # 夜の街: ナトリウム灯のオレンジ・白熱灯・ネオンのマゼンタ/シアン・信号の赤
    "night": [(255, 150, 60), (255, 150, 60), (255, 185, 105), (255, 185, 105), (255, 225, 170),
              (255, 225, 170), (255, 90, 150), (90, 170, 255), (255, 70, 70), (130, 110, 255)],
    "blue": [(90, 160, 255), (140, 200, 255), (200, 220, 255), (120, 110, 255), (80, 230, 230)],
    "warm": [(255, 150, 60), (255, 190, 110), (255, 225, 170), (255, 120, 80), (255, 210, 140)],
    # 駅までの帰り道: 街灯の暖色・白い窓明かり・青信号の緑・赤信号
    "street": [(255, 170, 80), (255, 170, 80), (255, 200, 130), (255, 225, 180), (255, 225, 180),
               (70, 255, 150), (70, 255, 150), (255, 70, 60), (140, 190, 255)],
}

SKIES = {  # (上, 中, 下) の色
    "night": ((6, 8, 24), (20, 14, 46), (34, 14, 38)),
    "dusk": ((10, 14, 42), (40, 30, 80), (95, 45, 60)),   # 日が沈んだ直後の青〜紫〜残照
}


def gradient(W: int, H: int, sky: str = "night") -> np.ndarray:
    y = np.linspace(0, 1, H)[:, None, None]
    top, mid, bot = (np.array(c) / 255 for c in SKIES[sky])
    g = np.where(y < 0.55, top + (mid - top) * (y / 0.55), mid + (bot - mid) * ((y - 0.55) / 0.45))
    return np.broadcast_to(g, (H, W, 3)).astype(np.float32).copy()


def bokeh_layer(W: int, H: int, n: int, rmin: float, rmax: float, blur: float, rng, palette, ybias: float):
    """ぼけた街の灯り（縁が少し明るいレンズのボケ）を描いた RGB レイヤー."""
    img = Image.new("RGB", (W, H), (0, 0, 0))
    d = ImageDraw.Draw(img, "RGBA")
    for _ in range(n):
        r = rng.uniform(rmin, rmax)
        x = rng.uniform(-r, W + r)
        # 画面の下 4 割（遠くの街）に集め、上のほうはまばらに
        y = H * (0.55 + 0.45 * rng.beta(2.0, 1.4)) if rng.random() > 0.12 else H * rng.uniform(0.2, 0.6)
        c = palette[rng.integers(len(palette))]
        a = min(255, int(rng.uniform(70, 190) * ybias))
        d.ellipse([x - r, y - r, x + r, y + r], fill=(*c, a))
        d.ellipse([x - r * 0.93, y - r * 0.93, x + r * 0.93, y + r * 0.93], fill=(*c, int(a * 0.45)))
    img = img.filter(ImageFilter.GaussianBlur(blur))
    return np.asarray(img, np.float32) / 255


def glass_drops(W: int, H: int, n: int, rng) -> np.ndarray:
    """窓ガラスについた水滴（RGBA）. 下側が暗く、左上に小さなハイライト."""
    img = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    for _ in range(n):
        r = rng.gamma(2.0, 2.2) + 1.5
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        ry = r * rng.uniform(1.0, 1.35)
        d.ellipse([x - r, y - ry, x + r, y + ry], fill=(170, 190, 230, 38))
        d.ellipse([x - r, y, x + r, y + ry], fill=(0, 0, 10, 45))
        hr = max(1.0, r * 0.28)
        d.ellipse([x - r * 0.4 - hr, y - ry * 0.45 - hr, x - r * 0.4 + hr, y - ry * 0.45 + hr],
                  fill=(255, 255, 255, 150))
    img = img.filter(ImageFilter.GaussianBlur(0.8))
    return np.asarray(img, np.float32) / 255


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=str(ROOT / "input" / "background.mp4"))
    ap.add_argument("--width", type=int, default=1080)
    ap.add_argument("--height", type=int, default=1920)
    ap.add_argument("--fps", type=int, default=30)
    ap.add_argument("--seconds", type=float, default=16.0, help="ループ 1 周の長さ")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--palette", choices=sorted(PALETTES), default="night")
    ap.add_argument("--rain", type=float, default=1.0, help="雨の強さ (0 で雨なし・窓の水滴もなし)")
    ap.add_argument("--sky", choices=sorted(SKIES), default="night", help="空の色 (night / dusk)")
    args = ap.parse_args()

    W, H, F, T = args.width, args.height, args.fps, args.seconds
    N = int(round(T * F))
    rng = np.random.default_rng(args.seed)
    pal = PALETTES[args.palette]
    k = W / 1080

    base = gradient(W, H, args.sky)
    pad = int(80 * k)  # 灯りのゆらぎ用の余白
    Wp, Hp = W + 2 * pad, H + 2 * pad
    layers = [  # (画像, 横ゆれ幅, 縦ゆれ幅, 明るさ)
        (bokeh_layer(Wp, Hp, 170, 4 * k, 14 * k, 3 * k, rng, pal, 1.0), 10 * k, 4 * k, 1.0),
        (bokeh_layer(Wp, Hp, 55, 18 * k, 45 * k, 10 * k, rng, pal, 0.9), 24 * k, 8 * k, 0.9),
        (bokeh_layer(Wp, Hp, 9, 70 * k, 130 * k, 30 * k, rng, pal, 0.7), 45 * k, 14 * k, 0.6),
    ]
    # 各レイヤーを 2 つに分け、逆位相で明るさを揺らす → 灯りがまたたいて見える
    twinkle = []
    for img, ax, ay, gain in layers:
        mask = (rng.random((Hp // 32 + 1, Wp // 32 + 1)) > 0.5).astype(np.float32)
        mask = np.asarray(Image.fromarray((mask * 255).astype(np.uint8)).resize((Wp, Hp), Image.BILINEAR),
                          np.float32)[..., None] / 255
        twinkle.append((img * mask, img * (1 - mask), ax, ay, gain, rng.uniform(0, 2 * math.pi)))

    drops = glass_drops(W, H, int(420 * k * k * min(1.0, args.rain)), rng)
    drop_rgb, drop_a = drops[..., :3], drops[..., 3:4]

    # 窓を伝う雨粒: 1 周 T 秒で画面を整数回通過する速さにしてループさせる
    drips = [dict(x=rng.uniform(0, W), y0=rng.uniform(0, H), laps=int(rng.integers(1, 3)),
                  r=rng.uniform(3, 5.5) * k, wob=rng.uniform(0, 2 * math.pi)) for _ in range(int(9 * min(1.0, args.rain)))]
    # 外の雨: 細い斜めの線
    streaks = [dict(x=rng.uniform(-200, W), y0=rng.uniform(0, H), laps=int(rng.integers(10, 16)),
                    L=rng.uniform(40, 90) * k, a=rng.uniform(0.12, 0.35)) for _ in range(int(110 * args.rain))]

    yy, xx = np.mgrid[0:H, 0:W].astype(np.float32)
    vig = 1 - 0.55 * (((xx - W / 2) / (W * 0.75)) ** 2 + ((yy - H * 0.55) / (H * 0.7)) ** 2)
    vig = np.clip(vig, 0.25, 1)[..., None].astype(np.float32)
    glow = np.exp(-(((xx - W * 0.78) / (W * 0.45)) ** 2 + ((yy - H * 0.2) / (H * 0.25)) ** 2))[..., None]
    glow = (glow * np.array([0.10, 0.07, 0.16])).astype(np.float32)
    del yy, xx

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(F), "-i", "-", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
           "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(out)]
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for i in range(N):
        ph = 2 * math.pi * i / N
        f = base + glow
        for a, b, ax, ay, gain, p0 in twinkle:
            ox = int(round(pad + ax * math.sin(ph + p0)))
            oy = int(round(pad + ay * math.cos(ph + p0)))
            s1 = gain * (0.8 + 0.2 * math.sin(3 * ph + p0))
            s2 = gain * (0.8 + 0.2 * math.sin(3 * ph + p0 + math.pi))
            f = f + s1 * a[oy:oy + H, ox:ox + W] + s2 * b[oy:oy + H, ox:ox + W]

        rain = Image.new("L", (W, H), 0)
        d = ImageDraw.Draw(rain)
        for s in streaks:
            y = (s["y0"] + s["laps"] * H * i / N) % (H + 200) - 100
            x = s["x"] + 0.18 * y
            d.line([x, y, x + 0.18 * s["L"], y + s["L"]], fill=int(255 * s["a"]), width=max(1, int(2 * k)))
        for dr in drips:
            y = (dr["y0"] + dr["laps"] * H * i / N) % H
            x = dr["x"] + 3 * k * math.sin(ph * 3 + dr["wob"] + y / 150)
            d.line([x, y - 160 * k, x, y], fill=40, width=max(1, int(dr["r"] * 0.5)))
            d.ellipse([x - dr["r"], y - dr["r"] * 1.2, x + dr["r"], y + dr["r"] * 1.2], fill=170)
        rain = rain.filter(ImageFilter.GaussianBlur(1.1 * k))
        r = np.asarray(rain, np.float32)[..., None] / 255
        f = f + r * np.array([0.55, 0.62, 0.8], np.float32)

        f = f * (1 - drop_a) + drop_rgb * drop_a
        f = f * vig
        f = f + rng.normal(0, 0.005, (H // 2, W // 2, 1)).repeat(2, 0).repeat(2, 1).astype(np.float32)
        f = np.clip(f, 0, 1)
        proc.stdin.write((f * 255).astype(np.uint8).tobytes())
        if i % F == 0:
            print(f"\r  {i * 100 // N:3d}%", end="", flush=True)
    proc.stdin.close()
    proc.wait()
    print(f"\r背景を作成しました: {out}")


if __name__ == "__main__":
    main()
