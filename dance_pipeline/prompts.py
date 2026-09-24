"""動画生成 AI 用の英語プロンプトを組み立てる（全区間で固定要素を共通化）."""
from __future__ import annotations

# 基準画像 (input/dancer_reference.png) の見た目をもとにした固定記述。
# 画像を差し替えた場合は config.json の "character" / "scene" を書き換えるだけで全区間に反映される。
DEFAULT_CHARACTER = (
    "the same young man from the reference image, same face, same tousled black hair with soft bangs, "
    "same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, "
    "black cargo pants with hanging straps, chunky black sneakers"
)
DEFAULT_SCENE = (
    "same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, "
    "glossy reflective grey floor, same moody low-key lighting"
)
# 全プロンプトに必ず含める固定要素（文言をそのまま含める）
FIXED_STYLE = (
    "Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. "
    "Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. "
    "9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, "
    "realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs."
)
REQUIRED_PHRASES = [
    "Same person", "same black outfit", "same hairstyle", "same studio background", "same lighting",
    "same camera position", "Full body always in frame", "9:16", "TikTok", "K-POP style choreography",
    "cool and confident mood", "realistic human movement", "natural body mechanics", "No extra people",
    "no sudden camera cuts", "no distorted hands or limbs",
]
NEGATIVE_PROMPT = (
    "extra people, crowd, second dancer, camera cut, scene change, zoom, camera shake, cropped feet, cropped head, "
    "out of frame, distorted hands, extra fingers, extra limbs, missing limbs, twisted joints, deformed face, "
    "face change, outfit change, color change, hair change, background change, blurry, low quality, text, watermark, logo"
)

MAX_PROMPT_CHARS = 1000   # Runway の上限。短縮版(prompt_short)はこの文字数以内
FULL_PROMPT_CHARS = 2000  # Kling(2500) / Hailuo(2000) など向けの詳細版


def _fmt(t: float) -> str:
    return f"{t:.1f}s"


def _moves(seg: dict, short: bool = False) -> str:
    key = "en_short" if short else "en"
    out = " ".join(f"{_fmt(p['t_start'])}-{_fmt(p['t_end'])}: he {p[key]}." for p in seg["phases"])
    if seg.get("is_hook"):
        out += " Repeatable signature hook move."
    if seg["is_last"]:
        out += " End on a clear frozen final pose."
    return out


def build_prompt(seg: dict, bpm: float, character: str = DEFAULT_CHARACTER, scene: str = DEFAULT_SCENE,
                 short: bool = False) -> str:
    tempo = f"Slow {round(bpm)} BPM groove, moves land on the beat with crisp hits and smooth flow."
    if not short:
        head = (f"Full-body dance video of {character}, in the {scene}. His signature pose is the pose in the "
                f"reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance.")
        body = f"{head} {tempo} {_moves(seg)} {FIXED_STYLE}"
        limit = FULL_PROMPT_CHARS
    else:
        head = ("The man from the reference image dances in the concrete studio with LED tubes. "
                "Signature pose = his pose in the reference image.")
        limit = MAX_PROMPT_CHARS
        body = f"{head} {tempo} {_moves(seg, True)} {FIXED_STYLE}"
    missing = [ph for ph in REQUIRED_PHRASES if ph not in body]
    if missing or len(body) > limit:
        raise ValueError(f"{seg['id']}: prompt invalid (len={len(body)}, missing={missing})")
    return body

def continuity_notes(seg: dict, prev: dict | None, nxt: dict | None) -> str:
    notes = ["開始フレーム＝基準画像（シグネチャーポーズ）"]
    if prev is not None:
        notes.append(f"前区間({prev['id']})の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める")
    if nxt is not None:
        if seg["template"] == "chorus_to_break":
            notes.append("区間末尾は低めのシグネチャーポーズで“溜め”、次区間の頭（ドロップ）で一気に動く")
        else:
            notes.append(f"区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間({nxt['id']})の開始フレームと一致させる")
        notes.append("区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続")
    else:
        notes.append("最後の小節頭で決めポーズ→音が消えても完全静止で動画終端までホールド")
    notes.append("立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで）")
    return " / ".join(notes)
