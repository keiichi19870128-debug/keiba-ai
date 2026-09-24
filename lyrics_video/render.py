"""フォント選択・背景の準備（ループ/トリミング/Ken Burns）・最終エンコード."""
from __future__ import annotations

import math
import os
import platform
import shutil
import subprocess
from pathlib import Path

import numpy as np

from .common import StepError, log, probe, run_ffmpeg

FONT_EXT = {".ttf", ".otf", ".ttc"}
# 見つかった順に使う（太めで読みやすい日本語フォント）
FONT_CANDIDATES = [
    "NotoSansJP-Black.otf", "NotoSansJP-ExtraBold.otf", "NotoSansJP-Bold.otf", "NotoSansCJKjp-Black.otf",
    "NotoSansCJKjp-Bold.otf", "NotoSansCJK-Bold.ttc", "BIZ-UDGothicB.ttc", "YuGothB.ttc", "meiryob.ttc",
    "ヒラギノ角ゴシック W7.ttc", "ヒラギノ角ゴシック W6.ttc", "Meiryo.ttc", "meiryo.ttc", "YuGothM.ttc",
    "msgothic.ttc", "ipagp.ttf", "ipag.ttf", "fonts-japanese-gothic.ttf",
]


def _font_dirs(root: Path) -> list[Path]:
    dirs = [root / "fonts"]
    if platform.system() == "Windows":
        windir = Path(os.environ.get("WINDIR", r"C:\Windows"))
        dirs += [windir / "Fonts", Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"]
    elif platform.system() == "Darwin":
        dirs += [Path("/System/Library/Fonts"), Path("/Library/Fonts"), Path.home() / "Library/Fonts"]
    else:
        dirs += [Path("/usr/share/fonts"), Path("/usr/local/share/fonts"), Path.home() / ".fonts"]
    return [d for d in dirs if d.is_dir()]


def resolve_font(cfg: dict, root: Path, work: Path) -> tuple[str, Path | None]:
    """(ASS に書くフォント名, fontsdir) を返す. 選んだフォントは work/fonts にコピーして ffmpeg に渡す."""
    fc = cfg["font"]
    path: Path | None = None
    if fc.get("file") and fc["file"] != "auto":
        p = Path(fc["file"])
        path = p if p.is_absolute() else root / p
        if not path.exists():
            raise StepError(f"config.json の font.file が見つかりません: {fc['file']}",
                            "fonts フォルダにフォントファイルを置き、ファイル名を指定してください。")
    elif fc.get("name") and fc["name"] != "auto":
        log.info("[フォント] %s（システムにインストール済みのフォント名で指定）", fc["name"])
        return fc["name"], None
    else:
        dirs = _font_dirs(root)
        own = sorted(p for p in (root / "fonts").glob("*") if p.suffix.lower() in FONT_EXT) \
            if (root / "fonts").is_dir() else []
        # fonts フォルダに自分で入れたフォントがあれば最優先（同梱の NotoSansJP-Black より先）
        custom = [p for p in own if p.name != "NotoSansJP-Black.otf"]
        if custom:
            path = custom[0]
        for name in ([] if path else FONT_CANDIDATES):
            for d in dirs:
                hits = [d / name] if (d / name).exists() else list(d.rglob(name)) if d.name != "Fonts" else []
                if hits:
                    path = hits[0]
                    break
            if path:
                break
        if path is None and own:
            path = own[0]
    if path is None:
        raise StepError("日本語フォントが見つかりません。",
                        "fonts フォルダに NotoSansJP-Black.otf などを置くか、config.json の font.name に "
                        "\"Meiryo\" などインストール済みのフォント名を書いてください。")
    try:
        from PIL import ImageFont

        family, style = ImageFont.truetype(str(path), 20).getname()
        # libass はフルネーム（例: "Noto Sans JP Black"）で確実に一致する
        if style and style.lower() not in ("regular", "normal", "book", "roman"):
            family = f"{family} {style}"
    except Exception:
        family = path.stem
    fdir = work / "fonts"
    if fdir.exists():
        shutil.rmtree(fdir)
    fdir.mkdir(parents=True)
    shutil.copy2(path, fdir / ("font" + path.suffix.lower()))
    log.info("[フォント] %s (%s)", family, path)
    return family, fdir


# ---------------------------------------------------------------------------
# 背景
# ---------------------------------------------------------------------------
def fit_chain(W: int, H: int, fit: str, src_w: int | None, src_h: int | None, tag: str = "") -> str:
    """任意サイズの素材を W x H の縦画面にする filter（cover=クロップ / blur=ぼかし背景＋全体表示）."""
    if fit == "auto":
        fit = "blur" if (src_w and src_h and src_w / src_h > 1.05) else "cover"
    cover = f"scale={W}:{H}:force_original_aspect_ratio=increase:flags=lanczos,crop={W}:{H}"
    if fit == "blur":
        t = tag
        return (f"split[fa{t}][fb{t}];[fa{t}]{cover},gblur=sigma=40,colorlevels=romax=0.7:gomax=0.7:bomax=0.7[fbg{t}];"
                f"[fb{t}]scale={W}:{H}:force_original_aspect_ratio=decrease:flags=lanczos[ffg{t}];"
                f"[fbg{t}][ffg{t}]overlay=(W-w)/2:(H-h)/2,setsar=1")
    return cover + ",setsar=1"


MOTIONS = ["zoom_in", "pan_right", "zoom_out", "pan_up", "zoom_in_left", "pan_left", "zoom_out_right", "pan_down"]


def zoompan_expr(motion: str, Z: float, N: int) -> tuple[str, str, str]:
    e = f"((1-cos(PI*min(on,{N})/{N}))/2)"  # なめらかに始まり、なめらかに止まる
    cx, cy = "(iw-iw/zoom)/2", "(ih-ih/zoom)/2"
    zin, zout = f"1+{Z - 1:.4f}*{e}", f"{Z:.4f}-{Z - 1:.4f}*{e}"
    table = {
        "zoom_in": (zin, cx, cy),
        "zoom_out": (zout, cx, cy),
        "pan_right": (f"{Z:.4f}", f"(iw-iw/zoom)*{e}", cy),
        "pan_left": (f"{Z:.4f}", f"(iw-iw/zoom)*(1-{e})", cy),
        "pan_up": (f"{Z:.4f}", cx, f"(ih-ih/zoom)*(1-{e})"),
        "pan_down": (f"{Z:.4f}", cx, f"(ih-ih/zoom)*{e}"),
        "zoom_in_left": (zin, f"(iw-iw/zoom)*(0.5-0.35*{e})", cy),
        "zoom_out_right": (zout, f"(iw-iw/zoom)*(0.5+0.35*{e})", cy),
    }
    return table.get(motion, table["zoom_in"])


def _boundaries(D: float, n: int, downbeats: np.ndarray, min_len: float) -> list[float]:
    """画像を切り替える時刻（小節頭に吸着）."""
    b = [0.0]
    for i in range(1, n):
        t = D * i / n
        if len(downbeats):
            j = int(np.argmin(np.abs(downbeats - t)))
            if abs(downbeats[j] - t) < D / n / 3:
                t = float(downbeats[j])
        if t - b[-1] >= min_len:
            b.append(t)
    b.append(D)
    return b


def prepare_background(bgs: list[Path], kind: str, D: float, cfg: dict, work: Path, variant: int,
                       downbeats: np.ndarray, preview: bool) -> tuple[list[str], str]:
    """背景を用意し、(最終エンコードでの入力引数, W x H にするための filter) を返す."""
    V, B = cfg["video"], cfg["background"]
    W, H, F = int(V["width"]), int(V["height"]), int(V["fps"])
    enc = ["-c:v", "libx264", "-preset", "veryfast" if not preview else "ultrafast", "-crf", "14",
           "-pix_fmt", "yuv420p", "-an"]

    if kind == "none" or not bgs:
        out = work / f"bg_gradient_v{variant}.mp4"
        run_ffmpeg(["-f", "lavfi", "-i",
                    f"gradients=s={W}x{H}:r={F}:c0=0x1b1035:c1=0x0b3d5c:c2=0x3a0d3d:nb_colors=3:speed=0.008:"
                    f"seed={variant + 1}:duration={D + 1:.3f}", "-t", f"{D:.3f}"] + enc + [str(out)],
                   "背景(グラデーション)", total=D)
        return ["-i", str(out)], "null"

    if kind == "video":
        src = bgs[0]
        info = probe(src)
        L = info["duration"] or 0
        if not L:
            raise StepError(f"背景動画の長さを取得できません: {src}", "動画ファイルが壊れていないか確認してください。")
        w, h = info["width"], info["height"]
        if info["rotation"] in (90, 270) and w and h:
            w, h = h, w
        chain = fit_chain(W, H, B["fit"], w, h) + f",fps={F}"
        ss = float(B["video_start_sec"] or 0)
        if variant and L > D:  # バリエーションは開始位置をずらす
            ss = (ss + variant * (L - D) / max(2, int(cfg.get("variants", 1)))) % max(L - D, 0.001)
        avail = L - ss
        if avail >= D - 0.05:
            log.info("[背景] 動画 %.1fs → %.1fs から曲の長さ %.1fs 分を使用（トリミング）", L, ss, D)
            return ["-ss", f"{ss:.3f}", "-i", str(src)], chain
        c = float(B["loop_crossfade_sec"] or 0)
        unit = work / f"bg_loop_v{variant}.mp4"
        if c > 0 and avail >= 3 * c:
            log.info("[背景] 動画 %.1fs を曲の長さ %.1fs までループ（継ぎ目を %.1fs クロスフェード）", avail, D, c)
            fc = (f"[0:v]{chain},split[m][h];[m]trim=start={c:.3f}:end={avail:.3f},setpts=PTS-STARTPTS,fps={F}[a];"
                  f"[h]trim=start=0:end={c:.3f},setpts=PTS-STARTPTS,fps={F}[b];"
                  f"[a][b]xfade=transition=fade:duration={c:.3f}:offset={avail - 2 * c:.3f},format=yuv420p[v]")
            run_ffmpeg(["-ss", f"{ss:.3f}", "-i", str(src), "-filter_complex", fc, "-map", "[v]"] + enc + [str(unit)],
                       "背景ループ素材", total=avail)
        else:
            log.info("[背景] 動画 %.1fs を曲の長さ %.1fs までループ", avail, D)
            run_ffmpeg(["-ss", f"{ss:.3f}", "-i", str(src), "-vf", chain] + enc + [str(unit)], "背景ループ素材", total=avail)
        return ["-stream_loop", "-1", "-i", str(unit)], "null"

    # --- 画像: Ken Burns（ゆっくりズーム/パン）。複数枚ならクロスフェードでつなぐ ---
    n = len(bgs)
    xf = float(B["image_crossfade_sec"] or 0) if n > 1 else 0.0
    bnd = _boundaries(D, n, downbeats, min_len=max(2.0, 2 * xf))
    bgs = bgs[: len(bnd) - 1]
    Z = max(1.0, float(B["image_zoom"]))
    S = 2 if preview else 3  # 高解像度でズームしてから縮小 → ガタつきを防ぐ
    motion_cfg = B["image_motion"]
    seed = int(B.get("motion_seed", 0)) + variant * 3
    inputs, parts = [], []
    for k, img in enumerate(bgs):
        seg = bnd[k + 1] - bnd[k] + (xf if k < len(bgs) - 1 else 0)
        N = max(2, int(math.ceil(seg * F)))
        if isinstance(motion_cfg, list):
            mo = motion_cfg[(k + variant) % len(motion_cfg)]
        elif motion_cfg in (None, "", "auto"):
            mo = MOTIONS[(seed + k * 2) % len(MOTIONS)]
        else:
            mo = motion_cfg
        z, x, y = zoompan_expr(mo, Z, N - 1)
        with_info = probe(img)
        pre = fit_chain(W * S, H * S, B["fit"], with_info["width"], with_info["height"], tag=str(k))
        inputs += ["-i", str(img)]
        parts.append(f"[{k}:v]format=rgb24,{pre},zoompan=z='{z}':x='{x}':y='{y}':d={N}:s={W}x{H}:fps={F},"
                     f"trim=end_frame={N},setpts=PTS-STARTPTS,fps={F},format=yuv420p[p{k}]")
        log.info("[背景] 画像 %s: %s（%.1fs）", img.name, mo, seg)
    graph = ";".join(parts)
    last = "[p0]"
    for k in range(1, len(bgs)):
        graph += f";{last}[p{k}]xfade=transition=fade:duration={xf:.3f}:offset={bnd[k]:.3f}[x{k}]"
        last = f"[x{k}]"
    out = work / f"bg_image_v{variant}.mp4"
    run_ffmpeg(inputs + ["-filter_complex", graph, "-map", last, "-t", f"{D:.3f}", "-r", str(F)] + enc + [str(out)],
               "背景(画像の Ken Burns)", total=D)
    return ["-i", str(out)], "null"


def make_scrim(cfg: dict, work: Path) -> Path | None:
    """歌詞の位置だけ少し暗くする縦グラデーション（背景に文字が埋もれないように）."""
    a = float(cfg["background"].get("text_scrim") or 0)
    if a <= 0:
        return None
    from PIL import Image

    W, H = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    cy = float(cfg["subtitle"]["position_y"]) * H
    ys = np.arange(H)
    alpha = a * np.exp(-0.5 * ((ys - cy) / (0.13 * H)) ** 2)
    col = (alpha * 255).astype(np.uint8)
    arr = np.zeros((H, W, 4), np.uint8)
    arr[..., 3] = col[:, None]
    p = work / "scrim.png"
    Image.fromarray(arr, "RGBA").save(p)
    return p


# ---------------------------------------------------------------------------
# 最終エンコード
# ---------------------------------------------------------------------------
def render_final(bg_in: list[str], bg_chain: str, audio: Path, ass: Path | None, fontsdir: Path | None,
                 D: float, cfg: dict, work: Path, out_path: Path, preview: bool) -> None:
    V, B = cfg["video"], cfg["background"]
    W, H, F = int(V["width"]), int(V["height"]), int(V["fps"])
    scrim = make_scrim(cfg, work)

    look = []
    br = float(B["brightness"])
    if abs(br - 1) > 1e-3:
        look.append(f"colorlevels=romax={br:.3f}:gomax={br:.3f}:bomax={br:.3f}")
    if abs(float(B["contrast"]) - 1) > 1e-3 or abs(float(B["saturation"]) - 1) > 1e-3:
        look.append(f"eq=contrast={float(B['contrast']):.3f}:saturation={float(B['saturation']):.3f}")
    if float(B["blur"] or 0) > 0:
        look.append(f"gblur=sigma={float(B['blur']):.2f}")
    if B["vignette"]:
        look.append("vignette=angle=PI/5")

    # 背景の filter は「[0:v] → [bg]」の形に（fit_chain が複数ノードでも動くように）
    chain = bg_chain if bg_chain != "null" else "null"
    g = f"[0:v]{chain},fps={F},format=yuv420p" + ("," + ",".join(look) if look else "") + "[bg]"
    cur = "[bg]"
    inputs = list(bg_in) + ["-i", str(audio)]
    if scrim:
        inputs += ["-loop", "1", "-framerate", str(F), "-i", str(scrim)]
        g += f";[2:v]format=rgba[sc];{cur}[sc]overlay=0:0:shortest=1:format=auto[bs]"
        cur = "[bs]"
    post = []
    if ass is not None:
        local = work / "render.ass"
        shutil.copy2(ass, local)
        post.append("ass=render.ass" + (f":fontsdir={fontsdir.name}" if fontsdir else ""))
    fi, fo = float(V["fade_in_sec"] or 0), float(V["fade_out_sec"] or 0)
    if fi > 0:
        post.append(f"fade=t=in:st=0:d={fi:.2f}")
    if fo > 0:
        post.append(f"fade=t=out:st={max(0, D - fo):.3f}:d={fo:.2f}")
    if preview:
        post.append(f"scale={W // 2}:{H // 2 // 2 * 2}")
    post.append("scale=out_color_matrix=bt709:out_range=tv,format=yuv420p")
    g += f";{cur}{','.join(post)}[v]"

    ainfo = probe(audio)
    if ainfo["audio_codec"] == "aac" and not preview:
        acodec = ["-c:a", "copy"]  # 元が AAC ならそのまま（再エンコードしない＝音質劣化なし）
    else:
        acodec = ["-c:a", "aac", "-b:a", str(V["audio_bitrate"])]
        sr = V.get("audio_sample_rate", "source")
        src_sr = ainfo["sample_rate"]
        if sr and sr != "source":
            acodec += ["-ar", str(int(sr))]
        elif src_sr and src_sr not in (44100, 48000):
            acodec += ["-ar", "48000"]
    venc = ["-c:v", "libx264", "-preset", "veryfast" if preview else str(V["preset"]),
            "-crf", "23" if preview else str(V["crf"]), "-profile:v", "high", "-level:v", "4.2",
            "-pix_fmt", "yuv420p", "-r", str(F), "-g", str(F * 2), "-bf", "2",
            "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709"]
    tmp = work / "render_tmp.mp4"
    args = inputs + ["-filter_complex", g, "-map", "[v]", "-map", "1:a:0", "-t", f"{D:.3f}"] + venc + acodec + \
        ["-movflags", "+faststart", "-tag:v", "avc1", str(tmp)]
    log.info("[書き出し] エンコード中 ...（%s）", "プレビュー画質" if preview else f"CRF {V['crf']} / {V['preset']}")
    run_ffmpeg(args, "最終エンコード", cwd=work, total=D)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(tmp), str(out_path))


def check_font(ass: Path, fontsdir: Path | None, font_name: str, t: float, work: Path) -> None:
    """libass が指定フォントを実際に使えているか 1 フレームだけ描いて確認（別フォントに化けていたら警告）."""
    import re as _re

    from .common import ffmpeg_exe

    shutil.copy2(ass, work / "check.ass")
    vf = "ass=check.ass" + (f":fontsdir={fontsdir.name}" if fontsdir else "") + f",trim=start={t:.2f}"
    cmd = [ffmpeg_exe(), "-hide_banner", "-loglevel", "verbose", "-f", "lavfi", "-i",
           f"color=c=gray:s=320x568:d={t + 0.5:.2f}:r=10", "-vf", vf, "-frames:v", "1", "-f", "null", "-"]
    try:
        err = subprocess.run(cmd, cwd=str(work), capture_output=True, encoding="utf-8", errors="replace",
                             timeout=60).stderr
    except Exception as exc:
        log.debug("フォント確認をスキップ: %s", exc)
        return
    picks = set(_re.findall(r"fontselect: \((.+?), \d+, \d+\) -> (.+?), \d+", err))
    log.debug("fontselect: %s", picks)
    # fontsdir から読んだフォントはファイル名ではなくフォント名で出る。システムのパスが出たら代用されている
    bad = [f for n, f in picks if n == font_name and fontsdir is not None and os.path.isabs(f)]
    if bad:
        log.warning("[フォント] '%s' の一部の文字が %s で代用されています。config.json の font.file / font.name を"
                    "確認してください", font_name, ", ".join(sorted(set(bad))))


def verify_output(path: Path, D: float, cfg: dict) -> dict:
    info = probe(path)
    W, H = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    ok = info["duration"] and abs(info["duration"] - D) < 0.3
    log.info("[確認] %s: %sx%s / %.2fs / %s fps / %.1f MB%s", path.name, info["width"], info["height"],
             info["duration"] or 0, info["fps"], path.stat().st_size / 1e6,
             "" if ok else f"  ※長さが音源 ({D:.2f}s) と違います")
    if (info["width"], info["height"]) != (W, H):
        log.debug("解像度が設定と異なります（プレビューの場合は半分）")
    return info


def open_folder(p: Path) -> None:
    try:
        if platform.system() == "Windows":
            os.startfile(str(p))  # type: ignore[attr-defined]
        elif platform.system() == "Darwin":
            subprocess.Popen(["open", str(p)])
    except Exception:
        pass
