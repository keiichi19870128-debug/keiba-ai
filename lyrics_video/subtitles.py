"""TikTok 向けの字幕 (ASS) と汎用 SRT を書き出す."""
from __future__ import annotations

from pathlib import Path

from .common import hex_to_ass
from .lyrics import Phrase, char_units


def _ts(t: float) -> str:
    t = max(0.0, t)
    cs = int(round(t * 100))
    return f"{cs // 360000}:{cs // 6000 % 60:02d}:{cs // 100 % 60:02d}.{cs % 100:02d}"


def _srt_ts(t: float) -> str:
    ms = int(round(max(0.0, t) * 1000))
    return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"


def _esc(s: str) -> str:
    return s.replace("\\", "＼").replace("{", "｛").replace("}", "｝")


def layout_params(cfg: dict) -> dict:
    """文字サイズと画面幅から「1 行に入る全角文字数」などを計算."""
    W, H = int(cfg["video"]["width"]), int(cfg["video"]["height"])
    sc = cfg["subtitle"]
    k = W / 1080.0  # 解像度を変えても見た目の比率が同じになるように
    fs = float(cfg["font"]["size"]) * k
    avail = W - 2 * float(sc["margin_x"]) * k
    row_units = avail / (fs * 1.02)
    if int(sc.get("max_chars_per_line") or 0) > 0:
        row_units = min(row_units, float(sc["max_chars_per_line"]))
    phrase_units = float(sc.get("phrase_max_chars") or 0) or row_units * int(sc["max_lines"])
    return {"W": W, "H": H, "k": k, "fs": fs, "avail": avail, "row_units": row_units,
            "phrase_units": phrase_units}


def _anim(kind: str, cx: float, cy: float, size: float, dur_ms: int, fi: int, fo: int, blur: float,
          delay: int) -> str:
    fi_end = delay + fi
    base = f"\\an5\\blur{blur:g}"
    fade = f"\\fade(255,0,255,{delay},{fi_end},{max(fi_end, dur_ms - fo)},{dur_ms})" if delay else f"\\fad({fi},{fo})"
    pos = f"\\pos({cx:.0f},{cy:.0f})"
    if kind == "none":
        return base + pos
    if kind == "fade":
        return base + pos + fade
    if kind == "slide_up":
        d = size * 0.32
        return base + fade + f"\\move({cx:.0f},{cy + d:.0f},{cx:.0f},{cy:.0f},{delay},{fi_end + 140})"
    if kind == "pop":
        return (base + pos + fade + f"\\fscx72\\fscy72\\t({delay},{fi_end},\\fscx107\\fscy107)"
                f"\\t({fi_end},{fi_end + 110},\\fscx100\\fscy100)")
    if kind == "zoom":
        return base + pos + fade + f"\\fscx95\\fscy95\\t({delay},{dur_ms},0.6,\\fscx105\\fscy105)"
    if kind == "blur":
        return (base + pos + fade + f"\\blur12\\t({delay},{fi_end + 120},\\blur{blur:g})"
                f"\\t({max(fi_end, dur_ms - fo)},{dur_ms},\\blur8)")
    return base + pos + fade


def build_ass(phrases: list[Phrase], cfg: dict, font_name: str) -> str:
    L = layout_params(cfg)
    W, H, k = L["W"], L["H"], L["k"]
    sc, ec, cc = cfg["subtitle"], cfg["emphasis"], cfg["chorus"]
    primary = hex_to_ass(sc["primary_color"])
    outline_c = hex_to_ass(sc["outline_color"])
    shadow_c = hex_to_ass(sc["shadow_color"], float(sc["shadow_alpha"]))
    emph_c = hex_to_ass(ec["color"]) if ec.get("color") else primary
    chorus_c = hex_to_ass(cc["color"]) if cc.get("color") else primary
    bold = -1 if cfg["font"].get("bold", True) else 0
    outline, shadow = float(sc["outline"]) * k, float(sc["shadow"]) * k
    spacing = float(sc.get("letter_spacing", 1)) * k
    blur = float(sc.get("outline_blur", 0))

    head = [
        "[Script Info]",
        "; generate_tiktok.py が自動生成。手で直した場合は python generate_tiktok.py --ass output/lyrics.ass で再描画できます",
        "ScriptType: v4.00+",
        f"PlayResX: {W}",
        f"PlayResY: {H}",
        "WrapStyle: 2",
        "ScaledBorderAndShadow: yes",
        "YCbCr Matrix: TV.709",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, "
        "Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, "
        "MarginR, MarginV, Encoding",
        f"Style: Lyric,{font_name},{L['fs']:.0f},{primary},{primary},{outline_c},{shadow_c},{bold},0,0,0,100,100,"
        f"{spacing:g},0,1,{outline:g},{shadow:g},5,0,0,0,1",
        f"Style: Chorus,{font_name},{L['fs'] * float(cc['scale']):.0f},{chorus_c},{chorus_c},{outline_c},{shadow_c},"
        f"{bold},0,0,0,100,100,{spacing:g},0,1,{outline * 1.1:g},{shadow:g},5,0,0,0,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
    ]
    ev = []
    cx = W / 2
    top_lim, bot_lim = H * float(sc["safe_top"]), H * (1 - float(sc["safe_bottom"]))
    for p in phrases:
        chorus = p.chorus and cc["enabled"]
        style = "Chorus" if chorus else "Lyric"
        size = L["fs"] * (float(cc["scale"]) if chorus else 1.0)
        es = float(ec["scale"]) if ec["enabled"] else 1.0
        emph_rows = _limit_emph(p.emph, int(ec.get("max_per_phrase", 1)))
        # 画面幅に収まるよう、はみ出す行があればフレーズ全体の文字を縮める
        widest = max(_row_width(r, e, es) for r, e in zip(p.rows, emph_rows)) * size + spacing * max(len(r) for r in p.rows)
        fit = min(1.0, L["avail"] / max(widest, 1))
        size *= fit
        heights = [size * (es if e else 1.0) for e in emph_rows]
        gapy = size * float(sc["line_spacing"])
        block_h = sum(h * 1.12 for h in heights) + gapy * (len(heights) - 1)
        cy0 = H * float(sc["position_y"]) - block_h / 2
        cy0 = min(max(cy0, top_lim), bot_lim - block_h)
        dur_ms = int(round((p.end - p.start) * 1000))
        fi, fo = int(sc["fade_in_ms"]), int(sc["fade_out_ms"])
        kind = (cc.get("animation") or sc["animation"]) if chorus else sc["animation"]
        y = cy0
        for ri, (row, em) in enumerate(zip(p.rows, emph_rows)):
            h = heights[ri] * 1.12
            cy = y + h / 2
            y += h + gapy
            delay = min(90 * ri, max(0, dur_ms // 4))  # 2 行目は少し遅れて出す
            tags = _anim(kind, cx, cy, size, dur_ms, fi, fo, blur, delay)
            if fit < 0.999 or chorus:
                tags += f"\\fs{size:.0f}"
            text = _rich(row, em, size, size * es, emph_c, primary if not chorus else chorus_c, fi + delay)
            ev.append(f"Dialogue: {1 + ri},{_ts(p.start)},{_ts(p.end)},{style},,0,0,0,,{{{tags}}}{text}")
    return "\n".join(head + ev) + "\n"


def _limit_emph(emph: list[list[tuple[int, int]]], limit: int) -> list[list[tuple[int, int]]]:
    """1 フレーズで強調するのは最大 limit 個まで（強調しすぎると何も目立たない）."""
    out, n = [], 0
    for row in emph:
        keep = []
        for sp in row:
            if n < limit:
                keep.append(sp)
                n += 1
        out.append(keep)
    return out


def _row_width(row: str, emph: list[tuple[int, int]], es: float) -> float:
    w = 0.0
    for i, c in enumerate(row):
        w += char_units(c) * (es if any(a <= i < b for a, b in emph) else 1.0)
    return w


def _rich(row: str, emph: list[tuple[int, int]], size: float, esize: float, ecolor: str, pcolor: str,
          pop_at: int) -> str:
    if not emph:
        return _esc(row)
    out, pos = "", 0
    for a, b in emph:
        out += _esc(row[pos:a])
        out += (f"{{\\fs{esize * 0.82:.0f}\\1c{ecolor}\\t({pop_at},{pop_at + 160},\\fs{esize:.0f})}}"
                f"{_esc(row[a:b])}{{\\fs{size:.0f}\\1c{pcolor}}}")
        pos = b
    return out + _esc(row[pos:])


def build_srt(phrases: list[Phrase]) -> str:
    out = []
    for i, p in enumerate(phrases, 1):
        out += [str(i), f"{_srt_ts(p.start)} --> {_srt_ts(p.end)}", *p.rows, ""]
    return "\n".join(out)


def write_subs(out_dir: Path, phrases: list[Phrase], cfg: dict, font_name: str) -> tuple[Path, Path]:
    ass, srt = out_dir / "lyrics.ass", out_dir / "lyrics.srt"
    ass.write_text(build_ass(phrases, cfg, font_name), encoding="utf-8-sig")
    srt.write_text(build_srt(phrases), encoding="utf-8-sig")
    return ass, srt

