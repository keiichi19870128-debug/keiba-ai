"""input/ フォルダから音源・歌詞・背景を自動検出する."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .common import StepError, log

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
LYRICS_EXT = {".txt", ".lrc"}
VIDEO_EXT = {".mp4", ".mov", ".m4v", ".webm", ".mkv"}
IMAGE_EXT = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}

# ファイル名にこれらが入っていれば優先
AUDIO_HINTS = ("song", "music", "track", "audio", "曲", "音源", "suno")
LYRICS_HINTS = ("lyric", "lyrics", "歌詞", "kashi")
BG_HINTS = ("background", "bg", "back", "背景", "loop")
# 他の用途のファイルと取り違えないよう、読むのはこれらのファイル名を除いたもの
IGNORE_NAMES = ("readme", "requirements", "license", "ofl", "manual")


@dataclass
class Inputs:
    audio: Path
    lyrics: Path | None
    backgrounds: list[Path] = field(default_factory=list)
    bg_kind: str = "none"  # video / image / none


def _files(d: Path, exts: set[str]) -> list[Path]:
    if not d.is_dir():
        return []
    out = []
    for p in sorted(d.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.name.startswith((".", "~")) or p.suffix.lower() not in exts:
            continue
        if any(n in p.stem.lower() for n in IGNORE_NAMES):
            continue
        out.append(p)
    return out


def _hinted(p: Path, hints: tuple[str, ...]) -> bool:
    s = p.stem.lower()
    return any(h in s for h in hints)


def _pick(cands: list[Path], hints: tuple[str, ...]) -> Path | None:
    if not cands:
        return None
    return sorted(cands, key=lambda p: (not _hinted(p, hints), -p.stat().st_size))[0]


def detect_inputs(input_dir: Path, overrides: dict) -> Inputs:
    """input_dir（無ければスクリプトと同じフォルダ）から素材を探す.

    overrides: {"audio": path, "lyrics": path, "background": path}（コマンドライン/config で指定された物を優先）
    """
    dirs = [input_dir]
    if not _files(input_dir, AUDIO_EXT) and input_dir.parent not in dirs:
        dirs.append(input_dir.parent)  # input に音源が無ければスクリプトと「同じフォルダ」も探す

    def first(exts, hints):
        for d in dirs:
            p = _pick(_files(d, exts), hints)
            if p:
                return p
        return None

    def given(key):
        v = overrides.get(key)
        if not v:
            return None
        p = Path(v)
        if not p.is_absolute():
            p = (input_dir / p) if (input_dir / p).exists() else p.resolve()
        if not p.exists():
            raise StepError(f"指定された {key} ファイルが見つかりません: {v}")
        return p

    audio = given("audio") or first(AUDIO_EXT, AUDIO_HINTS)
    if audio is None:
        raise StepError(f"音源ファイル (mp3 / wav 等) が見つかりません: {input_dir}",
                        "input フォルダに song.mp3 などを置いてください。")

    lyrics = given("lyrics")
    if lyrics is None:
        for d in dirs:
            cands = _files(d, LYRICS_EXT)
            if cands:
                # .lrc（タイム付き）> 名前が lyrics / 歌詞 > 最大サイズ
                lyrics = sorted(cands, key=lambda p: (p.suffix.lower() != ".lrc", not _hinted(p, LYRICS_HINTS),
                                                      -p.stat().st_size))[0]
                break

    bgs: list[Path] = []
    kind = "none"
    g = given("background")
    if g:
        bgs, kind = [g], ("video" if g.suffix.lower() in VIDEO_EXT else "image")
    else:
        for d in dirs:
            vids = [p for p in _files(d, VIDEO_EXT) if not p.stem.lower().startswith("final_tiktok")]
            imgs = _files(d, IMAGE_EXT)
            if vids:
                bgs, kind = [_pick(vids, BG_HINTS)], "video"
                break
            if imgs:
                hinted = [p for p in imgs if _hinted(p, BG_HINTS)]
                # 背景らしい名前の画像が複数あればスライドショー、無ければ 1 枚
                bgs = hinted if hinted else [_pick(imgs, BG_HINTS)]
                kind = "image"
                break

    log.info("[検出] 音源   : %s", audio)
    log.info("[検出] 歌詞   : %s", lyrics or "（無し → 字幕なしで作成）")
    log.info("[検出] 背景   : %s", ", ".join(str(b) for b in bgs) if bgs else "（無し → グラデーション背景）")
    return Inputs(audio=audio, lyrics=lyrics, backgrounds=bgs, bg_kind=kind)
