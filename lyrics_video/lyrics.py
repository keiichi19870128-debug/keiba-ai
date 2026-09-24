"""歌詞ファイルの読み込み・セクション判定・強調語・短いフレーズへの分割."""
from __future__ import annotations

import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .common import StepError, log

CHORUS_WORDS = ("chorus", "hook", "refrain", "drop", "サビ", "さび", "コーラス", "ｻﾋﾞ")
INTRO_WORDS = ("intro", "instrumental", "イントロ", "前奏", "inst")
TAG_RE = re.compile(r"^\s*[\[【\(（<＜]\s*([^\]】\)）>＞]{1,40})\s*[\]】\)）>＞]\s*$")
LRC_RE = re.compile(r"^\s*\[(\d{1,2}):(\d{1,2}(?:[.:]\d{1,3})?)\]\s*(.*)$")
LRC_META_RE = re.compile(r"^\s*\[(ar|ti|al|by|offset|length|re|ve):.*\]\s*$", re.I)
EMPH_RE = re.compile(r"[*＊]{1,2}(.+?)[*＊]{1,2}")
# このあとで区切ると自然な接続の言葉
CONJ = ("のに", "けど", "けれど", "から", "ので", "ても", "でも", "たら", "なら", "ながら", "まま", "より")
# 助詞に見えても 1 語なので区切らない組み合わせ
NO_BREAK = ("はず", "にも", "では", "には", "とは", "ても", "でも", "がら", "もの", "よう", "ばか", "にな", "とき", "ねむ")
BREAK_PUNCT = "、，,。．！!？?・…～〜♪"


@dataclass
class LyricLine:
    text: str                       # 表示用テキスト（強調記号は除去済み）
    emph: list[tuple[int, int]]     # 強調する文字範囲 [start, end)
    block: int                      # 空行で区切られたブロック番号
    section: str = ""               # [Verse] などのタグ名
    chorus: bool = False
    time: float | None = None       # LRC で指定された開始時刻
    end_time: float | None = None   # LRC の「時刻だけの行」で指定された終了時刻
    intro: bool = False             # 最初の歌詞の前に [Intro] などの前奏タグがあった


@dataclass
class Phrase:
    """画面に一度に出す 1 単位（1〜2 行）."""
    rows: list[str]
    emph: list[list[tuple[int, int]]]   # 行ごとの強調範囲
    line_idx: int                       # 元の LyricLine 番号
    chorus: bool
    start: float = 0.0
    end: float = 0.0
    char_from: int = 0                  # 元の行の中での文字位置（タイミング配分用）
    char_to: int = 0
    extra: dict = field(default_factory=dict)

    @property
    def text(self) -> str:
        return "".join(self.rows)


def is_chorus(section: str) -> bool:
    low = section.lower()
    if any(w in low for w in ("pre", "プレ", "bメロ", "post")):  # Pre-Chorus はサビ扱いしない
        return False
    return any(w in low for w in CHORUS_WORDS)


def read_text_any(path: Path) -> str:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "utf-16", "cp932", "euc-jp"):
        try:
            txt = raw.decode(enc)
            if enc == "utf-16" and not raw[:2] in (b"\xff\xfe", b"\xfe\xff"):
                continue
            return txt
        except UnicodeDecodeError:
            continue
    return raw.decode("utf-8", errors="replace")


def parse_lyrics(path: Path) -> list[LyricLine]:
    text = read_text_any(path).replace("\r\n", "\n").replace("\r", "\n")
    lines: list[LyricLine] = []
    block, section, last_blank = 0, "", True
    intro_tag = False
    for raw in text.split("\n"):
        s = raw.strip().replace("　", " ")
        if s.startswith(("#", "//")):  # コメント行
            continue
        if not s or LRC_META_RE.match(s):
            if not s and not last_blank:
                block += 1
            last_blank = last_blank or not s
            continue
        t = None
        m = LRC_RE.match(s)
        if m:
            t = int(m.group(1)) * 60 + float(m.group(2).replace(":", "."))
            s = m.group(3).strip()
            if not s:  # 時刻だけの行は「ここで一旦消す」の意味として扱う
                if lines and lines[-1].time is not None and lines[-1].end_time is None:
                    lines[-1].end_time = t
                continue
        tag = TAG_RE.match(s)
        if tag:
            if not last_blank:
                block += 1
            section = tag.group(1).strip()
            if not lines and any(w in section.lower() for w in INTRO_WORDS):
                intro_tag = True
            last_blank = True
            continue
        emph: list[tuple[int, int]] = []
        out, pos = "", 0
        for em in EMPH_RE.finditer(s):
            out += s[pos:em.start()]
            emph.append((len(out), len(out) + len(em.group(1))))
            out += em.group(1)
            pos = em.end()
        out += s[pos:]
        out = re.sub(r"\s+", " ", out).strip()
        if not out:
            continue
        low = section.lower()
        lines.append(LyricLine(text=out, emph=emph, block=block, section=section,
                               chorus=is_chorus(low), time=t))
        last_blank = False
    if not lines:
        raise StepError(f"歌詞ファイルに歌詞がありません: {path}")
    lines[0].intro = intro_tag
    # ブロック番号を 0.. に詰める
    remap = {b: i for i, b in enumerate(sorted({ln.block for ln in lines}))}
    for ln in lines:
        ln.block = remap[ln.block]
    n_lrc = sum(ln.time is not None for ln in lines)
    log.info("[歌詞] %d 行 / %d ブロック%s", len(lines), len(remap),
             f" / LRC タイム指定 {n_lrc} 行" if n_lrc else "")
    return lines


def extract_embedded_lyrics(audio: Path, work: Path) -> Path | None:
    """音源ファイルのタグに埋め込まれた歌詞（Suno の mp3 など）を取り出して txt にする."""
    import subprocess

    from .common import ffmpeg_exe

    meta = work / "embedded_meta.txt"
    subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y", "-i", str(audio),
                    "-f", "ffmetadata", str(meta)], capture_output=True)
    if not meta.exists():
        return None
    raw = meta.read_text(encoding="utf-8", errors="replace")
    entries, cur = [], ""
    for line in raw.splitlines():  # ffmetadata: 値の中の改行は行末の \ で表される
        if cur.endswith("\\") and not cur.endswith("\\\\"):
            cur = cur[:-1] + "\n" + line
        else:
            if cur:
                entries.append(cur)
            cur = line
    if cur:
        entries.append(cur)
    for e in entries:
        key, _, val = e.partition("=")
        if key.strip().lower().startswith(("lyrics", "unsyncedlyrics", "uslt")) and val.strip():
            val = re.sub(r"\\(.)", r"\1", val)
            out = work / "embedded_lyrics.txt"
            out.write_text(val.strip() + "\n", encoding="utf-8")
            log.info("[歌詞] 歌詞ファイルが無いため、音源に埋め込まれた歌詞を使います（%s）", key)
            return out
    return None


def norm(s: str) -> str:
    """比較用の正規化（全角半角・大文字小文字・記号・空白の違いを無視、カタカナ→ひらがな）."""
    s = unicodedata.normalize("NFKC", s).lower()
    s = "".join(chr(ord(c) - 0x60) if "ァ" <= c <= "ヶ" else c for c in s)
    return "".join(c for c in s if c.isalnum())


def mark_chorus_by_repetition(lines: list[LyricLine]) -> bool:
    """タグが無い場合: 他のブロックでも繰り返される行が多いブロックをサビとみなす."""
    if any(ln.chorus for ln in lines):
        return True
    counts = Counter(norm(ln.text) for ln in lines)
    blocks: dict[int, list[LyricLine]] = {}
    for ln in lines:
        blocks.setdefault(ln.block, []).append(ln)
    found = False
    for bl in blocks.values():
        rep = sum(counts[norm(ln.text)] >= 2 for ln in bl)
        if len(bl) >= 2 and rep / len(bl) >= 0.5:
            for ln in bl:
                ln.chorus = True
            found = True
    if found:
        log.info("[歌詞] 繰り返しの多いブロックをサビと判定しました")
    return found


def mark_emphasis(lines: list[LyricLine], cfg: dict) -> None:
    """*強調* の指定が無い場合、config の単語リスト＋自動抽出で強調語を決める."""
    ecfg = cfg["emphasis"]
    if not ecfg["enabled"]:
        for ln in lines:
            ln.emph = []
        return
    words = [w for w in ecfg.get("words") or [] if w]
    has_markup = any(ln.emph for ln in lines)
    if ecfg.get("auto") and not has_markup:
        words += auto_keywords(lines, int(ecfg.get("max_auto_words", 6)))
    if words:
        log.info("[歌詞] 強調語: %s", " / ".join(dict.fromkeys(words)))
    for ln in lines:
        for w in sorted(set(words), key=len, reverse=True):
            for m in re.finditer(re.escape(w), ln.text, flags=re.I):
                span = (m.start(), m.end())
                if span[1] - span[0] >= len(ln.text):  # 行全体を強調しても意味がない
                    continue
                if not any(a < span[1] and span[0] < b for a, b in ln.emph):
                    ln.emph.append(span)
        ln.emph.sort()


def auto_keywords(lines: list[LyricLine], limit: int) -> list[str]:
    """カタカナ語・英単語・スペース区切りの短い語のうち、繰り返し/サビに出る物を強調語にする."""
    stop = {"the", "and", "you", "your", "for", "but", "are", "with", "that", "this", "all", "can", "not", "was"}
    score: Counter = Counter()
    for ln in lines:
        toks = set(re.findall(r"[ァ-ヴー]{2,}|[A-Za-z][A-Za-z']{2,}", ln.text))
        parts = re.split(r"[ 　" + re.escape(BREAK_PUNCT) + r"]+", ln.text)
        if len(parts) > 1:
            toks |= {p for p in parts if 2 <= len(p) <= 6}
        for t in toks:
            if t.lower() in stop:
                continue
            score[t] += 2 if ln.chorus else 1
    picked = [t for t, c in score.most_common() if c >= 2][:limit]
    return picked


# ---------------------------------------------------------------------------
# フレーズ分割
# ---------------------------------------------------------------------------
def char_units(c: str) -> float:
    """1 文字の幅（全角=1.0, 半角≒0.55）."""
    if c == " ":
        return 0.3
    return 1.0 if unicodedata.east_asian_width(c) in "WFA" else 0.58


def units(s: str) -> float:
    return sum(char_units(c) for c in s)


def _kind(c: str) -> str:
    if "ぁ" <= c <= "ゖ":
        return "hira"
    if "ァ" <= c <= "ヺ" or c == "ー":
        return "kata"
    if c.isascii() and c.isalnum():
        return "latin"
    if c == " ":
        return "space"
    if c in BREAK_PUNCT:
        return "punct"
    return "kanji"


def break_points(s: str) -> list[tuple[int, float]]:
    """分割候補位置とその良さ（大きいほど自然）. 位置 i は s[:i] | s[i:] の境目."""
    pts = []
    for i in range(1, len(s)):
        a, b = _kind(s[i - 1]), _kind(s[i])
        if b == "space":
            continue
        if a == "space":
            pts.append((i, 3.0))
        elif a == "punct" and b != "punct":
            pts.append((i, 2.6))
        elif a == "hira" and b in ("kanji", "kata", "latin"):
            pts.append((i, 1.6))   # 助詞・送り仮名のあと
        elif a in ("kanji", "kata") and b == "latin" or a == "latin" and b in ("kanji", "kata", "hira"):
            pts.append((i, 1.2))
        elif a == "kata" and b == "kanji" or a == "kanji" and b == "kata":
            pts.append((i, 0.8))
        elif a == "hira" and b == "hira":
            if any(s[:i].endswith(w) for w in CONJ):
                pts.append((i, 2.2))   # 「〜のに」「〜けど」「〜から」のあと
            elif s[i - 1] in "はがをにでともへやねよてば" and s[i - 1:i + 1] not in NO_BREAK:
                pts.append((i, 0.4))
    return pts


def best_split(s: str, max_units: float) -> int | None:
    """s を 2 つに分ける位置（両側が max_units 以内・中央寄り・自然な切れ目を優先）."""
    total = units(s)
    best, best_score = None, -1e9
    for i, good in break_points(s):
        left, right = units(s[:i].rstrip()), units(s[i:].lstrip())
        over = max(0.0, left - max_units) + max(0.0, right - max_units)
        balance = abs(left - right) / max(total, 1)
        score = good - 3.0 * balance - 4.0 * over
        if score > best_score:
            best, best_score = i, score
    if best is None and len(s) > 1:
        # 候補が無い（長い英単語など）→ 幅の中央で強制分割
        acc = 0.0
        for i, c in enumerate(s):
            acc += char_units(c)
            if acc >= total / 2:
                return max(1, i)
    return best


def _split_rec(s: str, lo: int, max_units: float) -> list[tuple[int, int]]:
    """s[lo:] を max_units 以下のかたまりに再帰分割し、(開始, 終了) の文字範囲を返す."""
    if units(s) <= max_units or len(s) <= 1:
        return [(lo, lo + len(s))]
    i = best_split(s, max_units)
    if i is None:
        return [(lo, lo + len(s))]
    return _split_rec(s[:i], lo, max_units) + _split_rec(s[i:], lo + i, max_units)


def _trim(s: str, a: int, b: int) -> tuple[int, int]:
    while a < b and s[a] == " ":
        a += 1
    while b > a and s[b - 1] == " ":
        b -= 1
    return a, b


def split_into_phrases(lines: list[LyricLine], row_units: float, phrase_units: float,
                       max_lines: int, chorus_scale: float) -> list[Phrase]:
    """各歌詞行を「一度に表示するフレーズ（1〜max_lines 行）」に分ける.

    row_units    : 1 行に入る全角文字数（画面幅と文字サイズから計算）
    phrase_units : 1 フレーズの目安の長さ。これより長い行は自然な切れ目で別フレーズにする
    """
    phrases: list[Phrase] = []
    for li, ln in enumerate(lines):
        s = ln.text
        r_units = row_units / (chorus_scale if ln.chorus else 1.0)
        cap = min(phrase_units, r_units * max_lines)
        chunks = _split_rec(s, 0, cap) if units(s) > cap else [(0, len(s))]
        for a, b in chunks:
            a, b = _trim(s, a, b)
            if a >= b:
                continue
            seg = s[a:b]
            rows = [(a, b)]
            # 少しはみ出すだけなら 2 行に割らず、文字を少し縮めて 1 行で見せる（subtitles 側で自動縮小）
            if units(seg) > r_units * 1.15 and max_lines >= 2:
                rows = [(a + x, a + y) for x, y in _split_rec(seg, 0, r_units)][:max_lines]
                if rows[-1][1] < b:  # 行数を超えた分は最後の行に寄せる（下で文字サイズを縮めて収める）
                    rows[-1] = (rows[-1][0], b)
            row_txt, row_emph = [], []
            for x, y in rows:
                x, y = _trim(s, x, y)
                row_txt.append(s[x:y])
                row_emph.append([(max(ea, x) - x, min(eb, y) - x) for ea, eb in ln.emph if ea < y and x < eb])
            phrases.append(Phrase(rows=row_txt, emph=row_emph, line_idx=li, chorus=ln.chorus,
                                  char_from=a, char_to=b))
    return phrases
