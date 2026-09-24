"""歌詞タイミングの推定.

優先順位（timing.method = "auto" の場合）:
  0. 歌詞ファイルが LRC 形式（[mm:ss.xx] 付き）ならその時刻をそのまま使う
  1. align   : stable-ts による「歌詞テキストとボーカル音声の強制アラインメント」
  2. whisper : faster-whisper / openai-whisper で文字起こし → 歌詞と文字単位で突き合わせ
  3. heuristic: 歌声らしさ・無音・ビートから推定（追加ライブラリ不要）
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from difflib import SequenceMatcher
from pathlib import Path

import numpy as np

from .audio import AudioInfo, decode
from .common import log
from . import sherpa
from .lyrics import LyricLine, Phrase, norm, units

# 各行の「1 文字ごとの (開始, 終了) 時刻」を持つ
CharTimes = list[list[tuple[float, float]]]


# ---------------------------------------------------------------------------
# 文字 ↔ 読み の対応（pykakasi があれば漢字をひらがなに直して突き合わせ精度を上げる）
# ---------------------------------------------------------------------------
_KKS = None


def _kakasi():
    global _KKS
    if _KKS is None:
        try:
            import pykakasi

            _KKS = pykakasi.kakasi()
        except Exception:
            _KKS = False
    return _KKS or None


def reading_chars(text: str) -> list[tuple[str, int]]:
    """text を比較用の文字列に直し、各文字が元の text の何文字目に当たるかを返す."""
    out: list[tuple[str, int]] = []
    kks = _kakasi()
    if kks:
        pos = 0
        for item in kks.convert(text):
            orig = item["orig"]
            start = text.find(orig, pos) if orig else pos
            if start < 0:
                start = pos
            rd = norm(item["hira"] or orig)
            for k, c in enumerate(rd):
                out.append((c, start + min(len(orig) - 1, int(k * len(orig) / max(len(rd), 1))) if orig else start))
            pos = start + len(orig)
        return out
    for i, ch in enumerate(text):
        for c in norm(ch):
            out.append((c, i))
    return out


# ---------------------------------------------------------------------------
# 1 / 2. Whisper 系
# ---------------------------------------------------------------------------
def _file_hash(p: Path) -> str:
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()[:16]


def _device(cfg_dev: str) -> str:
    if cfg_dev and cfg_dev != "auto":
        return cfg_dev
    try:
        import ctranslate2

        if ctranslate2.get_cuda_device_count() > 0:
            return "cuda"
    except Exception:
        pass
    try:
        import torch

        if torch.cuda.is_available():
            return "cuda"
    except Exception:
        pass
    return "cpu"


def separate_vocals(audio: Path, work: Path, cfg: dict) -> Path | None:
    """伴奏を消してボーカルだけにする（認識精度が大きく上がる）. demucs > sherpa-onnx (Spleeter) の順."""
    mode = cfg["timing"]["vocal_separation"]
    if mode is False or mode == "off":
        return None
    try:
        import demucs  # noqa: F401
        has_demucs = True
    except ImportError:
        has_demucs = False
    if has_demucs:
        src = decode(audio, work / "demucs_in.wav", 44100, mono=False)
        out = work / "demucs"
        log.info("[タイミング] demucs でボーカルを分離中（初回はモデルをダウンロードします）...")
        cmd = [sys.executable, "-m", "demucs", "--two-stems", "vocals", "-n", "htdemucs", "-o", str(out), str(src)]
        proc = subprocess.run(cmd, capture_output=True, encoding="utf-8", errors="replace")
        log.debug("[demucs] exit=%s\n%s", proc.returncode, proc.stderr[-4000:])
        voc = out / "htdemucs" / src.stem / "vocals.wav"
        if proc.returncode == 0 and voc.exists():
            return voc
        log.warning("[タイミング] demucs のボーカル分離に失敗しました（詳細はログ）")
    if sherpa.available():
        try:
            log.info("[タイミング] Spleeter (sherpa-onnx) でボーカルを分離中 ...")
            src = decode(audio, work / "sep_in.wav", 44100, mono=False)
            return sherpa.separate_vocals(src, work / "vocals.wav", models_dir(cfg))
        except Exception as exc:
            log.warning("[タイミング] ボーカル分離に失敗したため元音源で続行します: %s", exc)
            log.debug("traceback", exc_info=True)
    elif mode is True:
        log.warning("[タイミング] vocal_separation=true ですが demucs / sherpa-onnx が入っていません")
    return None


def models_dir(cfg: dict) -> Path:
    p = Path(cfg["timing"].get("models_dir") or "models")
    return p if p.is_absolute() else sherpa.ROOT / p


def whisper_words(engine: str, wav16: Path, lyrics_text: str, cfg: dict) -> list[tuple[float, float, str]]:
    """engine = 'align'（stable-ts 強制アラインメント）/ 'whisper'（文字起こし）で単語時刻を得る."""
    tc = cfg["timing"]
    model_name, lang = tc["whisper_model"], tc["language"] or None
    dev = _device(tc["device"])
    words: list[tuple[float, float, str]] = []
    if engine == "align":
        import stable_whisper  # stable-ts

        try:
            model = stable_whisper.load_faster_whisper(model_name, device=dev,
                                                      compute_type="int8" if dev == "cpu" else "float16")
        except Exception:
            model = stable_whisper.load_model(model_name, device=dev)
        res = model.align(str(wav16), lyrics_text, language=lang or "ja")
        for seg in res.segments:
            for w in seg.words:
                words.append((float(w.start), float(w.end), w.word))
        return words

    prompt = None
    if tc.get("use_lyrics_prompt"):
        prompt = lyrics_text.replace("\n", " ")[:120]
    try:
        from faster_whisper import WhisperModel

        ct = tc["compute_type"] if tc["compute_type"] != "auto" else ("int8" if dev == "cpu" else "float16")
        model = WhisperModel(model_name, device=dev, compute_type=ct)
        segs, _info = model.transcribe(str(wav16), language=lang, word_timestamps=True, vad_filter=False,
                                       condition_on_previous_text=False, initial_prompt=prompt, beam_size=5)
        for s in segs:
            for w in s.words or []:
                words.append((float(w.start), float(w.end), w.word))
        return words
    except ImportError:
        pass
    import whisper  # openai-whisper

    model = whisper.load_model(model_name, device=dev)
    res = model.transcribe(str(wav16), language=lang, word_timestamps=True, initial_prompt=prompt,
                           condition_on_previous_text=False, fp16=(dev == "cuda"))
    for s in res["segments"]:
        for w in s.get("words", []):
            words.append((float(w["start"]), float(w["end"]), w["word"]))
    return words


def align_words_to_lines(lines: list[LyricLine], words: list[tuple[float, float, str]],
                         duration: float) -> tuple[CharTimes, float]:
    """単語時刻付きの文字起こしと歌詞を文字単位で突き合わせ、歌詞 1 文字ごとの時刻を求める."""
    tr_chars: list[str] = []
    tr_times: list[tuple[float, float]] = []
    for s, e, w in words:
        rc = [c for c, _ in reading_chars(w)]
        n = len(rc)
        for k, c in enumerate(rc):
            tr_chars.append(c)
            tr_times.append((s + (e - s) * k / n, s + (e - s) * (k + 1) / n))

    ly_chars: list[str] = []
    ly_owner: list[tuple[int, int]] = []  # (行番号, 行内の文字位置)
    for li, ln in enumerate(lines):
        for c, pos in reading_chars(ln.text):
            ly_chars.append(c)
            ly_owner.append((li, pos))
    if not ly_chars or not tr_chars:
        return [], 0.0

    sm = SequenceMatcher(None, ly_chars, tr_chars, autojunk=False)
    known: dict[int, tuple[float, float]] = {}
    for a, b, size in sm.get_matching_blocks():
        for k in range(size):
            known[a + k] = tr_times[b + k]
    ratio = len(known) / len(ly_chars)

    # 一致しなかった文字は前後の一致文字から線形補間
    idx = np.array(sorted(known))
    t = np.full(len(ly_chars), np.nan)
    te = np.full(len(ly_chars), np.nan)
    if len(idx):
        t[idx] = [known[i][0] for i in idx]
        te[idx] = [known[i][1] for i in idx]
        allk = np.arange(len(ly_chars))
        rate = 0.22  # 1 文字あたりの仮の歌唱時間（前後の外挿用）
        t = np.interp(allk, idx, t[idx], left=np.nan, right=np.nan)
        te = np.interp(allk, idx, te[idx], left=np.nan, right=np.nan)
        first, last = idx[0], idx[-1]
        for k in range(first - 1, -1, -1):
            t[k], te[k] = max(0.0, t[k + 1] - rate), t[k + 1]
        for k in range(last + 1, len(ly_chars)):
            t[k], te[k] = te[k - 1], min(duration, te[k - 1] + rate)

    char_times: CharTimes = [[(np.nan, np.nan)] * max(len(ln.text), 1) for ln in lines]
    for k, (li, pos) in enumerate(ly_owner):
        a, b = char_times[li][pos]
        char_times[li][pos] = (t[k] if np.isnan(a) else min(a, t[k]), te[k] if np.isnan(b) else max(b, te[k]))
    for row in char_times:  # 記号・空白など読みの無い文字は隣から埋める
        _fill_nan(row)
    return char_times, ratio


def _fill_nan(row: list[tuple[float, float]]) -> None:
    last = None
    for i, (a, b) in enumerate(row):
        if np.isnan(a):
            if last is not None:
                row[i] = (last, last)
        else:
            last = b
    nxt = None
    for i in range(len(row) - 1, -1, -1):
        a, b = row[i]
        if np.isnan(a):
            if nxt is not None:
                row[i] = (nxt, nxt)
        else:
            nxt = a


def _proportional(line: LyricLine, start: float, end: float) -> list[tuple[float, float]]:
    """行の [start, end] を文字幅に比例して 1 文字ずつに割り振る."""
    w = np.array([max(units(c), 0.3) for c in line.text] or [1.0])
    cum = np.concatenate([[0], np.cumsum(w)]) / w.sum()
    return [(start + (end - start) * cum[i], start + (end - start) * cum[i + 1]) for i in range(len(w))]


# ---------------------------------------------------------------------------
# 0. LRC
# ---------------------------------------------------------------------------
def lrc_timing(lines: list[LyricLine], a: AudioInfo) -> CharTimes:
    known = [(i, ln.time) for i, ln in enumerate(lines) if ln.time is not None]
    idx = np.array([k for k, _ in known], float)
    tt = np.array([v for _, v in known], float)
    starts = np.interp(np.arange(len(lines)), idx, tt)
    out: CharTimes = []
    for i, ln in enumerate(lines):
        nxt = starts[i + 1] if i + 1 < len(lines) else min(a.duration, starts[i] + 4.0)
        end = ln.end_time if ln.end_time else nxt
        sung = min(end, starts[i] + 0.3 * len(norm(ln.text)) + 0.6)  # 行の後半に文字が寄りすぎないよう
        out.append(_proportional(ln, starts[i], max(starts[i] + 0.3, sung)))
    return out


# ---------------------------------------------------------------------------
# 3. ヒューリスティック（歌声らしさ・無音・ビート）
# ---------------------------------------------------------------------------
def heuristic_timing(lines: list[LyricLine], a: AudioInfo) -> CharTimes:
    segs = [(max(s, a.music_start), min(e, a.music_end)) for s, e in a.vocal_segments()]
    segs = [(s, e) for s, e in segs if e - s > 0.25]
    if not segs:
        segs = [(a.music_start, a.music_end)]
    # 歌い出し: [Intro] タグがある / 曲の頭からいきなり歌声判定になっている場合は、
    # 曲構成の最初の切れ目（イントロの終わり）より前には歌詞を置かない
    early = segs[0][0] - a.music_start < 1.5
    if (lines[0].intro or early) and a.boundaries is not None:
        cand = [b for b in a.boundaries if a.music_start + 2.0 <= b <= min(15.0, a.duration * 0.3)]
        if cand:
            vstart = float(cand[0])
            segs = [(max(s, vstart), e) for s, e in segs if e > vstart + 0.3]
            log.info("[タイミング] イントロの終わり ≈ %.2fs から歌詞を配置します", vstart)

    blocks: dict[int, list[int]] = {}
    for i, ln in enumerate(lines):
        blocks.setdefault(ln.block, []).append(i)
    bl = [blocks[k] for k in sorted(blocks)]
    weight = [sum(units(lines[i].text) + 1.5 for i in b) for b in bl]
    group = _assign_blocks(segs, weight)

    out: CharTimes = [[] for _ in lines]
    for b, (g0, g1) in zip(bl, group):
        gsegs = segs[g0:g1]
        active = sum(e - s for s, e in gsegs)
        w = np.array([units(lines[i].text) + 1.5 for i in b])
        cum = np.concatenate([[0], np.cumsum(w)]) / w.sum() * active
        for k, li in enumerate(b):
            s = _active_to_time(gsegs, cum[k])
            e = _active_to_time(gsegs, cum[k + 1] - 1e-3)
            s = _snap_to_onset(s, gsegs)
            out[li] = _proportional(lines[li], s, max(e, s + 0.4))
    return out


def _assign_blocks(segs: list[tuple[float, float]], weight: list[float]) -> list[tuple[int, int]]:
    """歌声区間の並びを、歌詞ブロック数のまとまりに分ける（長い無音をブロックの境目にしやすくする DP）."""
    B, N = len(weight), len(segs)
    if B <= 1 or N < B:
        if N < B:  # 区間が足りない → 全体を均等に切り直す
            s0, s1 = segs[0][0], segs[-1][1]
            W = sum(weight)
            cuts = np.concatenate([[0], np.cumsum(weight)]) / W * (s1 - s0) + s0
            segs[:] = [(cuts[i], cuts[i + 1] - 0.05) for i in range(B)]
            return [(i, i + 1) for i in range(B)]
        return [(0, N)]
    dur = np.array([e - s for s, e in segs])
    gaps = np.array([segs[i + 1][0] - segs[i][1] for i in range(N - 1)])
    T, W = dur.sum(), sum(weight)
    cum = np.concatenate([[0], np.cumsum(dur)])
    gmax = gaps.max() + 1e-9
    INF = 1e18
    cost = np.full((B + 1, N + 1), INF)
    back = np.zeros((B + 1, N + 1), int)
    cost[0][0] = 0
    for b in range(1, B + 1):
        for j in range(b, N + 1):
            best, arg = INF, 0
            for i in range(b - 1, j):
                if cost[b - 1][i] >= INF:
                    continue
                share = (cum[j] - cum[i]) / T - weight[b - 1] / W
                c = cost[b - 1][i] + 8.0 * share * share
                if j < N:
                    c -= 0.08 * gaps[j - 1] / gmax  # 境目が長い無音ならボーナス
                if c < best:
                    best, arg = c, i
            cost[b][j], back[b][j] = best, arg
    res, j = [], N
    for b in range(B, 0, -1):
        i = back[b][j]
        res.append((i, j))
        j = i
    return res[::-1]


def _active_to_time(segs: list[tuple[float, float]], x: float) -> float:
    for s, e in segs:
        if x <= e - s:
            return s + max(0.0, x)
        x -= e - s
    return segs[-1][1]


def _snap_to_onset(t: float, segs: list[tuple[float, float]], tol: float = 0.45) -> float:
    starts = [s for s, _ in segs]
    near = min(starts, key=lambda s: abs(s - t))
    return near if abs(near - t) <= tol else t


# ---------------------------------------------------------------------------
# まとめ
# ---------------------------------------------------------------------------
def estimate(lines: list[LyricLine], a: AudioInfo, audio: Path, work: Path, cfg: dict,
             method: str | None = None) -> tuple[CharTimes, str]:
    method = (method or cfg["timing"]["method"] or "auto").lower()
    n_lrc = sum(ln.time is not None for ln in lines)
    if method in ("auto", "lrc") and n_lrc >= max(1, int(0.6 * len(lines))):
        log.info("[タイミング] 歌詞ファイルの LRC 時刻を使用します")
        return lrc_timing(lines, a), "lrc"

    ja = (cfg["timing"]["language"] or "ja").lower().startswith("ja")
    full = ["align", "sherpa", "whisper", "heuristic"] if ja else ["align", "whisper", "heuristic"]
    order = {"auto": full, "lrc": full, "align": full, "sherpa": ["sherpa", "whisper", "heuristic"],
             "whisper": ["whisper", "heuristic"], "heuristic": ["heuristic"]}
    lyrics_text = "\n".join(ln.text for ln in lines)
    cache_dir = work / "cache"
    cache_dir.mkdir(parents=True, exist_ok=True)
    wav16 = None
    for m in order.get(method, order["auto"]):
        if m == "heuristic":
            log.info("[タイミング] 音声解析（歌声らしさ・無音・ビート）から推定します")
            return heuristic_timing(lines, a), "heuristic"
        if m == "align":
            try:
                __import__("stable_whisper")
            except ImportError:
                log.info("[タイミング] stable-ts 未インストールのため強制アラインメントはスキップ")
                continue
        elif m == "sherpa":
            if not sherpa.available():
                log.info("[タイミング] sherpa-onnx 未インストールのため ReazonSpeech はスキップ")
                continue
        else:
            try:
                __import__("faster_whisper")
            except ImportError:
                try:
                    __import__("whisper")
                except ImportError:
                    log.info("[タイミング] faster-whisper / openai-whisper 未インストールのため文字起こしはスキップ")
                    continue
        try:
            key = hashlib.sha1(f"{_file_hash(audio)}|{m}|{cfg['timing']['whisper_model']}|"
                               f"{cfg['timing']['vocal_separation']}|{lyrics_text if m == 'align' else ''}"
                               .encode("utf-8")).hexdigest()[:16]
            cache = cache_dir / f"words_{m}_{key}.json"
            if cache.exists():
                words = [tuple(w) for w in json.loads(cache.read_text(encoding="utf-8"))]
                log.info("[タイミング] %s: 前回の解析結果（キャッシュ）を使用", m)
            else:
                if wav16 is None:
                    voc = separate_vocals(audio, work, cfg)
                    wav16 = decode(voc or audio, work / "whisper_16k.wav", 16000)
                if m == "sherpa":
                    log.info("[タイミング] ReazonSpeech (sherpa-onnx) で歌声を認識中 ...")
                    words = sherpa.recognize_words(wav16, models_dir(cfg))
                else:
                    log.info("[タイミング] %s (%s モデル) で解析中 ... 初回はモデルのダウンロードがあります",
                             "stable-ts 強制アラインメント" if m == "align" else "Whisper 文字起こし",
                             cfg["timing"]["whisper_model"])
                    words = whisper_words(m, wav16, lyrics_text, cfg)
                cache.write_text(json.dumps(words, ensure_ascii=False), encoding="utf-8")
            log.debug("[タイミング] 単語 %d 個: %s", len(words), " ".join(w[2] for w in words)[:2000])
            ct, ratio = align_words_to_lines(lines, words, a.duration)
            log.info("[タイミング] %s: 歌詞との一致率 %.0f%%", m, ratio * 100)
            if ct and ratio >= float(cfg["timing"]["min_match_ratio"]):
                return ct, m
            log.warning("[タイミング] %s の一致率が低いため次の方法を試します", m)
        except Exception as exc:  # モデルのダウンロード失敗・メモリ不足など
            log.warning("[タイミング] %s が失敗しました: %s（次の方法を試します。詳細はログ）", m, exc)
            log.debug("traceback", exc_info=True)
    log.info("[タイミング] 音声解析（歌声らしさ・無音・ビート）から推定します")
    return heuristic_timing(lines, a), "heuristic"


def mark_chorus_by_energy(lines: list[LyricLine], ct: CharTimes, a: AudioInfo) -> None:
    """タグも繰り返しも無い場合、音量の大きいブロックをサビとみなす."""
    blocks: dict[int, list[int]] = {}
    for i, ln in enumerate(lines):
        blocks.setdefault(ln.block, []).append(i)
    if len(blocks) < 2:
        return
    e = {b: a.energy_between(ct[ix[0]][0][0], ct[ix[-1]][-1][1]) for b, ix in blocks.items()}
    lo, hi = min(e.values()), max(e.values())
    if hi - lo < 0.08:
        return
    thr = lo + 0.7 * (hi - lo)
    for b, ix in blocks.items():
        if e[b] >= thr:
            for i in ix:
                lines[i].chorus = True
    log.info("[歌詞] 音量の大きいブロックをサビと判定: %s", [b for b in blocks if e[b] >= thr])


def phrase_times(phrases: list[Phrase], ct: CharTimes, a: AudioInfo, cfg: dict, method: str) -> None:
    """フレーズごとの表示開始/終了を決める（先出し・ビート吸着・重なり防止・最短/最長表示時間）."""
    sc = cfg["subtitle"]
    off = float(cfg["timing"]["offset_sec"])
    lead, hold, gap = float(sc["lead_in_sec"]), float(sc["hold_sec"]), float(sc["gap_sec"])
    grid = np.sort(np.concatenate([a.beats, (a.beats[:-1] + a.beats[1:]) / 2])) if len(a.beats) > 1 else a.beats
    snap = sc["beat_snap"] and method != "lrc" and len(grid)
    tol = float(sc["beat_snap_tolerance"])

    for p in phrases:
        row = ct[p.line_idx]
        a0 = row[min(p.char_from, len(row) - 1)][0]
        a1 = row[min(p.char_to, len(row)) - 1][1]
        p.extra["sung"] = (float(a0) + off, float(a1) + off)
        s = float(a0) + off - lead
        if snap:
            j = int(np.argmin(np.abs(grid - s)))
            if abs(grid[j] - s) <= tol:
                s = float(grid[j])
        p.start = max(0.0, s)

    min_step = 0.35
    for i in range(1, len(phrases)):
        if phrases[i].start < phrases[i - 1].start + min_step:
            phrases[i].start = phrases[i - 1].start + min_step

    for i, p in enumerate(phrases):
        nxt = phrases[i + 1].start if i + 1 < len(phrases) else a.duration
        want = max(p.extra["sung"][1] + hold, p.start + float(sc["min_duration"]))
        end = min(want, p.start + float(sc["max_duration"]), nxt - gap, a.duration - 0.05)
        p.end = max(end, p.start + 0.3)
        if i + 1 < len(phrases) and p.end > nxt:
            p.end = nxt


def write_lrc(path: Path, lines: list[LyricLine], ct: CharTimes) -> None:
    """推定したタイミングを LRC で出力（修正して input/ に置けば次回その時刻で作れる）."""
    out = ["[re:generate_tiktok.py]",
           "# この時刻を直して input フォルダに lyrics.lrc として置くと、その時刻で字幕を作ります"]
    block = None
    for ln, row in zip(lines, ct):
        if block is not None and ln.block != block:
            out.append("")
        if ln.block != block and ln.section:
            out.append(f"[{ln.section}]")
        block = ln.block
        t = max(0.0, float(row[0][0]))
        text = ln.text
        for a0, b0 in sorted(ln.emph, reverse=True):
            text = text[:a0] + "*" + text[a0:b0] + "*" + text[b0:]
        out.append(f"[{int(t // 60):02d}:{t % 60:05.2f}]{text}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
