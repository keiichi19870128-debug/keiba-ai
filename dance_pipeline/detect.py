"""作業フォルダ内の音源ファイル・基準画像を自動検出する."""
from __future__ import annotations

from pathlib import Path

AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".aiff", ".aif"}
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
# 出力やデモ素材を誤検出しないよう除外するディレクトリ
EXCLUDE_DIRS = {"output", "demo_assets", ".git", "__pycache__", "dance_pipeline", "node_modules"}
# 画像名にこれらが含まれていれば優先（基準画像らしい名前）
IMAGE_HINTS = ("ref", "base", "dancer", "model", "man", "male", "boy", "character", "基準", "男性", "ダンサー")


def _candidates(root: Path, exts: set[str]) -> list[Path]:
    found: list[Path] = []
    search_dirs = [root, root / "input", root / "inputs", root / "assets"]
    for d in search_dirs:
        if not d.is_dir():
            continue
        for p in sorted(d.iterdir()):
            if p.is_file() and p.suffix.lower() in exts and not p.name.startswith("."):
                found.append(p)
    # 直下で見つからなければ 2 階層まで探す
    if not found:
        for p in sorted(root.rglob("*")):
            if any(part in EXCLUDE_DIRS for part in p.relative_to(root).parts[:-1]):
                continue
            if len(p.relative_to(root).parts) > 3:
                continue
            if p.is_file() and p.suffix.lower() in exts:
                found.append(p)
    return found


def detect_audio(root: Path) -> Path | None:
    cands = _candidates(root, AUDIO_EXT)
    if not cands:
        return None
    # 50 秒前後の曲を最優先、なければ最大サイズ
    try:
        import soundfile as sf

        def score(p: Path) -> float:
            try:
                return abs(sf.info(str(p)).duration - 51.0)
            except Exception:
                return 1e6 - p.stat().st_size / 1e9

        return sorted(cands, key=score)[0]
    except Exception:
        return max(cands, key=lambda p: p.stat().st_size)


def detect_image(root: Path) -> Path | None:
    cands = _candidates(root, IMAGE_EXT)
    if not cands:
        return None

    def score(p: Path) -> tuple:
        name = p.stem.lower()
        hint = any(h in name for h in IMAGE_HINTS)
        portrait = 0.0
        try:
            from PIL import Image

            with Image.open(p) as im:
                w, h = im.size
                portrait = h / max(w, 1)  # 縦長ほど全身画像の可能性が高い
        except Exception:
            pass
        return (not hint, -portrait, -p.stat().st_size)

    return sorted(cands, key=score)[0]
