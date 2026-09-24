"""音源解析: 長さ / BPM / ビート / 強拍 / 曲調変化 / サビ / 振付切り替え候補."""
from __future__ import annotations

import os

import numpy as np
import librosa
import soundfile as sf
from pathlib import Path
from scipy.ndimage import median_filter
from scipy.signal import find_peaks

SR = 22050
HOP = 512


def _norm(x: np.ndarray) -> np.ndarray:
    x = np.asarray(x, dtype=float)
    rng = x.max() - x.min()
    return (x - x.min()) / rng if rng > 1e-12 else np.zeros_like(x)


def exact_duration(path: Path) -> float:
    try:
        info = sf.info(str(path))
        if info.frames > 0:
            return info.frames / info.samplerate
    except Exception:
        pass
    y, sr = librosa.load(str(path), sr=None, mono=True)
    return len(y) / sr


def _estimate_tempo(oenv: np.ndarray, prefer=(60.0, 115.0)) -> tuple[float, list[dict]]:
    """テンポグラムから BPM 候補を出し、「ゆっくりめの曲」前提で倍/半テンポの曖昧さを解消."""
    tg = librosa.feature.tempogram(onset_envelope=oenv, sr=SR, hop_length=HOP)
    ac = tg.mean(axis=1)
    bpms = librosa.tempo_frequencies(tg.shape[0], sr=SR, hop_length=HOP)
    ok = (bpms > 40) & (bpms < 200)
    peaks, _ = find_peaks(np.where(ok, ac, 0))
    cands = sorted(((float(bpms[i]), float(ac[i])) for i in peaks), key=lambda t: -t[1])[:6]
    base = float(librosa.feature.tempo(onset_envelope=oenv, sr=SR, hop_length=HOP, start_bpm=85)[0])
    tempo = base
    while tempo > prefer[1]:
        tempo /= 2
    while tempo < prefer[0]:
        tempo *= 2
    return tempo, [{"bpm": round(b, 2), "strength": round(s, 4)} for b, s in cands]


def analyze(audio_path: Path) -> dict:
    duration = exact_duration(audio_path)
    y, _ = librosa.load(str(audio_path), sr=SR, mono=True)
    y_h, y_p = librosa.effects.hpss(y)

    oenv = librosa.onset.onset_strength(y=y, sr=SR, hop_length=HOP)
    tempo0, tempo_cands = _estimate_tempo(oenv)

    # ---- ビート追跡 ----
    _, beat_frames = librosa.beat.beat_track(
        onset_envelope=oenv, sr=SR, hop_length=HOP, bpm=tempo0, tightness=120, trim=False
    )
    beats = librosa.frames_to_time(beat_frames, sr=SR, hop_length=HOP)
    if len(beats) < 8:
        raise RuntimeError("ビートがほとんど検出できませんでした。")
    period = float(np.median(np.diff(beats)))
    bpm = 60.0 / period
    # 検出前後を一定周期で補完（イントロ/アウトロにもカウントを振るため）
    detected = beats.copy()
    pre = np.arange(beats[0] - period, -period * 0.3, -period)[::-1]
    post = np.arange(beats[-1] + period, duration - period * 0.3, period)
    beats = np.concatenate([pre[pre >= 0], beats, post])
    extrap = np.concatenate([np.ones(len(pre[pre >= 0]), bool), np.zeros(len(detected), bool), np.ones(len(post), bool)])
    beat_frames_all = librosa.time_to_frames(beats, sr=SR, hop_length=HOP)
    beat_frames_all = np.clip(beat_frames_all, 0, len(oenv) - 1)

    # ---- 強拍 (小節頭) 推定: 4/4 を仮定し 4 通りの位相をスコア比較 ----
    S = np.abs(librosa.stft(y, hop_length=HOP))
    freqs = librosa.fft_frequencies(sr=SR)
    low = S[freqs < 150].sum(axis=0)  # キック帯域
    chroma = librosa.feature.chroma_cqt(y=y_h, sr=SR, hop_length=HOP)
    chroma_sync = librosa.util.sync(chroma, beat_frames_all, aggregate=np.median)
    chroma_change = np.r_[0, np.linalg.norm(np.diff(chroma_sync, axis=1), axis=0)]
    chroma_change = chroma_change[: len(beats)]
    if len(chroma_change) < len(beats):
        chroma_change = np.pad(chroma_change, (0, len(beats) - len(chroma_change)))
    beat_onset = _norm(oenv[beat_frames_all])
    beat_low = _norm(low[np.clip(beat_frames_all, 0, len(low) - 1)])
    beat_harm = _norm(chroma_change)
    beat_score = 0.35 * beat_onset + 0.35 * beat_low + 0.30 * beat_harm
    phase_scores = [float(beat_score[k::4].mean()) for k in range(4)]
    phase = int(np.argmax(phase_scores))
    downbeat_idx = list(range(phase, len(beats), 4))
    downbeats = beats[downbeat_idx]
    # 小節番号 / 拍番号 (1..4)
    beat_in_bar = [((i - phase) % 4) + 1 for i in range(len(beats))]

    # ---- 曲調変化 (セクション境界) : ビート同期特徴の自己相似 + チェッカーボード新規性 ----
    mfcc = librosa.feature.mfcc(y=y, sr=SR, hop_length=HOP, n_mfcc=13)
    rms = librosa.feature.rms(y=y, hop_length=HOP)[0]
    cent = librosa.feature.spectral_centroid(y=y, sr=SR, hop_length=HOP)[0]
    feats = np.vstack([
        librosa.util.normalize(mfcc, axis=1),
        chroma,
        _norm(rms)[None, :] * 3,
        _norm(cent)[None, :],
    ])
    Fs = librosa.util.sync(feats, beat_frames_all, aggregate=np.mean)
    Fs = Fs / (np.linalg.norm(Fs, axis=0, keepdims=True) + 1e-9)
    ssm = Fs.T @ Fs
    L = 8  # 2 小節 = 8 拍 のカーネル
    g = np.outer(np.hanning(2 * L), np.hanning(2 * L))
    sign = np.ones((2 * L, 2 * L))
    sign[:L, L:] = -1
    sign[L:, :L] = -1
    kern = g * sign
    n = ssm.shape[0]
    pad = np.pad(ssm, L, mode="edge")
    novelty = np.array([(pad[i:i + 2 * L, i:i + 2 * L] * kern).sum() for i in range(n)])
    # RMS の段差も加味（音量の立ち上がり＝展開）
    rms_b = librosa.util.sync(rms[None, :], beat_frames_all, aggregate=np.mean)[0][:n]
    rms_step = np.abs(np.convolve(rms_b, np.r_[np.ones(4), -np.ones(4)] / 4, mode="same"))
    nov = 0.7 * _norm(np.maximum(novelty, 0)) + 0.3 * _norm(rms_step)
    nov = nov[: len(beats)]
    # 小節単位の特徴（音量・低域・高域・明るさ）の段差でも境界を拾う
    frame_t0 = librosa.times_like(rms, sr=SR, hop_length=HOP)
    hi = S[freqs > 4000].sum(axis=0)
    bar_edges = list(downbeats) + [duration]
    bar_feat = []
    for a, b in zip(bar_edges[:-1], bar_edges[1:]):
        m = (frame_t0 >= a) & (frame_t0 < b)
        bar_feat.append([
            np.log(rms[m].mean() + 1e-6), np.log(low[m[: len(low)]].mean() + 1e-6),
            np.log(hi[m[: len(hi)]].mean() + 1e-6), cent[m].mean() / 1000.0,
        ])
    bar_feat = np.array(bar_feat)
    bar_rms = np.exp(bar_feat[:, 0])
    z = (bar_feat - bar_feat.mean(0)) / (bar_feat.std(0) + 1e-9)
    bar_jump = np.r_[0, np.linalg.norm(np.diff(z, axis=0), axis=1)]
    bar_nov = np.array([nov[max(0, i - 1):i + 2].max() if 0 <= i < len(nov) else 0 for i in downbeat_idx])
    bar_score = 0.6 * _norm(bar_jump) + 0.4 * _norm(bar_nov)
    # 外れ値（ブレイク）に閾値が引っ張られないよう中央値+MAD で判定
    mad = float(np.median(np.abs(bar_score - np.median(bar_score)))) + 1e-9
    thr = float(np.median(bar_score)) + 1.0 * mad
    cand = [i for i in range(1, len(bar_score)) if bar_score[i] > thr]
    if os.environ.get("DANCE_DEBUG"):
        print("bar_score", np.round(bar_score, 2), "thr", round(thr, 2))
    # 末尾の減衰小節（曲終わりの余韻）は境界にしない
    cand = [i for i in cand if bar_edges[i] < duration - 3.0]
    # 近接候補は強い方を残す（最低 2 小節間隔。ただし急激な音量低下=ブレイクは 1 小節も許容）
    chosen: list[int] = []
    for i in sorted(cand, key=lambda i: -bar_score[i]):
        near = [c for c in chosen if abs(c - i) < 2]
        is_drop = bar_rms[i] < 0.6 * np.median(bar_rms) or (i > 0 and bar_rms[i - 1] < 0.6 * np.median(bar_rms))
        if not near or (is_drop and all(abs(c - i) >= 1 for c in near)):
            chosen.append(i)
    merged = [0.0] + sorted(float(bar_edges[i]) for i in chosen) + [duration]
    # 最初の小節頭より前のピックアップはイントロに含める / 2.5 秒未満の断片は統合
    cleaned = [merged[0]]
    for t in merged[1:-1]:
        if t - cleaned[-1] >= 2.5:
            cleaned.append(t)
    if duration - cleaned[-1] < 2.5 and len(cleaned) > 1:
        cleaned.pop()
    merged = cleaned + [duration]

    # ---- セクションごとのエネルギー / ラベル ----
    frame_t = librosa.times_like(rms, sr=SR, hop_length=HOP)
    rms_n = rms / (rms.max() + 1e-9)
    onset_n = oenv / (oenv.max() + 1e-9)

    def stats(a: float, b: float) -> dict:
        m = (frame_t >= a) & (frame_t < b)
        mo = m[: len(onset_n)]
        return {
            "start": round(a, 3), "end": round(b, 3),
            "energy": round(float(rms_n[m].mean()), 4),
            "onset_density": round(float(onset_n[mo].mean()), 4),
            "brightness": round(float(cent[m].mean()), 1),
        }

    # サビ / 最も印象が強い部分: 最大 16 秒窓でエネルギー+密度+明るさ最大
    win = min(4 * 4 * period, 16.0)
    score_curve = 0.6 * _norm(median_filter(rms, 21)) + 0.25 * _norm(median_filter(oenv, 21))[: len(rms)] + 0.15 * _norm(cent)
    best, best_s = 0.0, -1.0
    for st in downbeats:
        if st + win > duration:
            break
        m = (frame_t >= st) & (frame_t < st + win)
        sc = float(score_curve[m].mean())
        if sc > best_s:
            best, best_s = float(st), sc
    highlight = {"start": round(best, 3), "end": round(min(best + win, duration), 3), "score": round(best_s, 4)}

    coarse = [stats(a, b) for a, b in zip(merged[:-1], merged[1:])]
    energies = np.array([c["energy"] for c in coarse])
    med, emax = float(np.median(energies)), float(energies.max())
    for i, c in enumerate(coarse):
        e, ln = c["energy"], c["end"] - c["start"]
        ov = max(0.0, min(c["end"], highlight["end"]) - max(c["start"], highlight["start"])) / ln
        if e < 0.6 * med and ln <= 6.5 and 0 < i < len(coarse) - 1:
            c["label"] = "break"
        elif i > 0 and coarse[i - 1].get("label") == "break" and e >= 0.75 * emax:
            c["label"] = "final_chorus"
        elif e >= 0.85 * emax or ov > 0.5:
            c["label"] = "chorus"
        elif i == 0:
            c["label"] = "intro"
        else:
            c["label"] = "verse"
    if not any(c["label"] in ("chorus", "final_chorus") for c in coarse):
        coarse[int(np.argmax(energies))]["label"] = "chorus"

    # ---- フレーズ(小節)単位で細分化: イントロ / Aメロ / サビ前 / サビ前半・後半 ----
    bar = 4 * period
    dbs = np.array(downbeats)

    def db_after(t: float, n_bars: int) -> float:
        idx = int(np.searchsorted(dbs, t - 0.05))
        j = idx + n_bars
        return float(dbs[j]) if j < len(dbs) else duration

    def db_before(t: float, n_bars: int) -> float:
        idx = int(np.searchsorted(dbs, t - 0.05))
        j = idx - n_bars
        return float(dbs[j]) if j >= 0 else 0.0

    pieces: list[tuple[float, float, str]] = []
    for i, c in enumerate(coarse):
        a, b, lab = c["start"], c["end"], c["label"]
        nxt = coarse[i + 1]["label"] if i + 1 < len(coarse) else None
        if lab in ("intro", "verse") and nxt == "chorus" and (b - a) > 3.5 * bar:
            pre_a = db_before(b, 2)
            head = [(a, pre_a, lab)]
            if lab == "intro" and (pre_a - a) > 3.0 * bar:
                first_db = float(dbs[0]) if dbs[0] > 0.3 else float(dbs[1])
                intro_end = first_db + bar if first_db < 2.0 else first_db
                head = [(a, intro_end, "intro"), (intro_end, pre_a, "verse")]
            pieces += head + [(pre_a, b, "pre_chorus")]
        elif lab == "chorus" and (b - a) > 5.5 * bar:
            mid = db_after(a, 4)
            pieces += [(a, mid, "chorus"), (mid, b, "chorus")]
        else:
            pieces.append((a, b, lab))

    sections = []
    for a, b, lab in pieces:
        st = stats(a, b)
        st["label"] = lab
        sections.append(st)
    ch_idx = [i for i, s in enumerate(sections) if s["label"] == "chorus"]
    for k, i in enumerate(ch_idx):
        sections[i]["chorus_part"] = "A" if k % 2 == 0 else "B"
    sections[-1]["is_ending"] = True
    labels_ja = {"intro": "イントロ", "verse": "Aメロ", "pre_chorus": "Bメロ(サビ前の盛り上げ)", "chorus": "サビ",
                 "break": "ブレイク(音が抜ける)", "final_chorus": "ラストサビ/ドロップ(低音主体)", "outro": "アウトロ"}
    for s in sections:
        s["label_ja"] = labels_ja.get(s["label"], s["label"])
    merged = [s["start"] for s in sections] + [duration]

    # ---- キメ(アクセント)候補: 強いオンセット ----
    thr = np.percentile(oenv, 96)
    apk, _ = find_peaks(oenv, height=thr, distance=int(0.6 * SR / HOP))
    accents = [round(float(t), 3) for t in librosa.frames_to_time(apk, sr=SR, hop_length=HOP)]

    # 無音で終わる末尾（リリース）
    tail_m = frame_t > duration - 3
    silent = frame_t[(rms_n < 0.05) & tail_m]
    music_end = float(silent[0]) if len(silent) else duration

    # ---- 振付切り替え候補: セクション境界 > セクション内 2 小節フレーズ頭 > 小節頭 ----
    switch = []
    sec_starts = [s["start"] for s in sections]
    for i, t in enumerate(downbeats):
        sec_i = max(k for k, st in enumerate(sec_starts) if st <= t + 0.05)
        bars_into = int(round((t - sections[sec_i]["start"]) / bar))
        if any(abs(t - st) < 0.05 for st in sec_starts[1:]):
            kind = "section"
        elif bars_into % 2 == 0:
            kind = "phrase_2bar"
        else:
            kind = "bar"
        switch.append({"time": round(float(t), 3), "type": kind, "bar": i + 1, "section": sections[sec_i]["label"]})

    return {
        "source_file": audio_path.name,
        "duration_sec": round(duration, 3),
        "music_end_sec": round(music_end, 3),
        "sample_rate_analysis": SR,
        "bpm": round(bpm, 2),
        "bpm_candidates": tempo_cands,
        "beat_period_sec": round(period, 4),
        "time_signature_assumed": "4/4",
        "beats": [
            {"time": round(float(t), 3), "beat_in_bar": int(bb), "strength": round(float(s), 3), "extrapolated": bool(x)}
            for t, bb, s, x in zip(beats, beat_in_bar, beat_score, extrap)
        ],
        "downbeats": [round(float(t), 3) for t in downbeats],
        "downbeat_phase_scores": [round(p, 4) for p in phase_scores],
        "sections": sections,
        "section_boundaries": [round(t, 3) for t in merged],
        "highlight": highlight,
        "accents": accents,
        "choreo_switch_candidates": switch,
        "novelty_curve_per_beat": [round(float(v), 3) for v in nov],
    }
