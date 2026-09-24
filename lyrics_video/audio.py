"""音源の解析: 長さ・ビート・強拍・歌声らしさ（ボーカル区間の推定）・音量カーブ."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .common import StepError, log, run_ffmpeg

SR = 22050
HOP = 512


@dataclass
class AudioInfo:
    duration: float
    beats: np.ndarray          # 拍の時刻 [秒]
    downbeats: np.ndarray      # 小節頭（4/4 と仮定）
    bpm: float
    frame_times: np.ndarray    # 以下のカーブの時刻
    vocal: np.ndarray          # 0..1 歌声らしさ
    energy: np.ndarray         # 0..1 音量（数秒平滑）
    music_start: float
    music_end: float
    boundaries: np.ndarray = None  # 曲構成の切れ目の候補（イントロ終わり等）

    def energy_between(self, a: float, b: float) -> float:
        m = (self.frame_times >= a) & (self.frame_times < max(b, a + 0.05))
        return float(self.energy[m].mean()) if m.any() else 0.0

    def vocal_segments(self, thr: float | None = None, min_gap: float = 0.35, min_len: float = 0.3) -> list[tuple[float, float]]:
        """歌声らしさがしきい値を超える区間の一覧."""
        v = self.vocal
        if thr is None:
            lo, hi = np.percentile(v, 20), np.percentile(v, 90)
            thr = lo + 0.35 * (hi - lo)
        on = v > thr
        segs: list[list[float]] = []
        t = self.frame_times
        i = 0
        while i < len(on):
            if on[i]:
                j = i
                while j < len(on) and on[j]:
                    j += 1
                a, b = float(t[i]), float(t[min(j, len(t) - 1)])
                if segs and a - segs[-1][1] < min_gap:
                    segs[-1][1] = b
                else:
                    segs.append([a, b])
                i = j
            else:
                i += 1
        return [(a, b) for a, b in segs if b - a >= min_len]


def decode(audio: Path, out_wav: Path, sr: int, mono: bool = True) -> Path:
    """どんな形式/ファイル名でも確実に読めるよう、一度 wav に変換する."""
    args = ["-i", str(audio), "-vn", "-ar", str(sr)]
    if mono:
        args += ["-ac", "1"]
    args += ["-c:a", "pcm_s16le", str(out_wav)]
    run_ffmpeg(args, f"音源のデコード({sr}Hz)")
    return out_wav


def _smooth(x: np.ndarray, n: int) -> np.ndarray:
    if n <= 1:
        return x
    k = np.hanning(n + 2)[1:-1]
    k /= k.sum()
    return np.convolve(np.pad(x, (n // 2, n - n // 2 - 1), mode="edge"), k, mode="valid")


def analyze(audio: Path, work: Path) -> AudioInfo:
    try:
        import librosa
        import soundfile as sf
    except ImportError as exc:
        raise StepError(f"ライブラリが入っていません: {exc}", "pip install -r requirements.txt を実行してください。") from exc

    stereo_wav = decode(audio, work / "analysis_stereo.wav", SR, mono=False)
    y2, sr = sf.read(str(stereo_wav), dtype="float32", always_2d=True)
    y2 = y2.T
    y = y2.mean(axis=0)
    duration = len(y) / sr
    if duration < 1:
        raise StepError(f"音源が短すぎます ({duration:.2f}s): {audio}")

    # --- ビート ---
    onset = librosa.onset.onset_strength(y=y, sr=sr, hop_length=HOP)
    tempo, beat_frames = librosa.beat.beat_track(onset_envelope=onset, sr=sr, hop_length=HOP, trim=False)
    bpm = float(np.atleast_1d(tempo)[0]) if np.size(tempo) else 0.0
    beats = librosa.frames_to_time(beat_frames, sr=sr, hop_length=HOP)
    if len(beats) < 4:  # ビートが取れない曲（アンビエント等）は 120BPM の仮グリッド
        bpm = bpm or 120.0
        beats = np.arange(0, duration, 60.0 / bpm)
    # 小節頭: 4 通りの位相のうちアタックが最も強いもの
    strength = onset[np.clip(beat_frames, 0, len(onset) - 1)] if len(beat_frames) >= 4 else np.ones(len(beats))
    phase = int(np.argmax([strength[p::4].mean() if len(strength[p::4]) else 0 for p in range(4)]))
    downbeats = beats[phase::4]

    # --- 歌声らしさ: 中央定位 (Mid - Side) の調波成分のうち 250〜3500Hz 帯のエネルギー ---
    n_fft = 2048
    if y2.shape[0] >= 2:
        mid, side = (y2[0] + y2[1]) / 2, (y2[0] - y2[1]) / 2
        M = np.abs(librosa.stft(mid, n_fft=n_fft, hop_length=HOP))
        S = np.abs(librosa.stft(side, n_fft=n_fft, hop_length=HOP))
        C = np.maximum(M - 1.0 * S, 0)
    else:
        C = np.abs(librosa.stft(y, n_fft=n_fft, hop_length=HOP))
    H, _P = librosa.decompose.hpss(C, margin=2.0)
    freqs = librosa.fft_frequencies(sr=sr, n_fft=n_fft)
    band = (freqs >= 250) & (freqs <= 3500)
    ve = np.log1p(100 * H[band].sum(axis=0) / (H[band].sum(axis=0).max() + 1e-9))
    ve = _smooth(ve, 9)
    vocal = (ve - ve.min()) / (ve.max() - ve.min() + 1e-9)

    rms = librosa.feature.rms(y=y, frame_length=n_fft, hop_length=HOP)[0]
    n = min(len(vocal), len(rms), len(onset))
    vocal, rms = vocal[:n], rms[:n]
    frame_times = librosa.frames_to_time(np.arange(n), sr=sr, hop_length=HOP)
    energy = _smooth(rms, int(2.0 * sr / HOP))
    energy = (energy - energy.min()) / (energy.max() - energy.min() + 1e-9)

    loud = np.where(rms > 0.05 * rms.max())[0]
    music_start = float(frame_times[loud[0]]) if len(loud) else 0.0
    music_end = float(frame_times[loud[-1]]) if len(loud) else duration

    boundaries = _structure_boundaries(y, sr)

    log.info("[解析] 長さ %.2fs / BPM≈%.1f / 拍 %d / 音の鳴り始め %.2fs・終わり %.2fs",
             duration, bpm, len(beats), music_start, music_end)
    return AudioInfo(duration=duration, beats=np.asarray(beats), downbeats=np.asarray(downbeats), bpm=bpm,
                     frame_times=frame_times, vocal=vocal, energy=energy,
                     music_start=music_start, music_end=music_end, boundaries=boundaries)


def _structure_boundaries(y: np.ndarray, sr: int) -> np.ndarray:
    """音色・和音の自己相似行列のノベルティから、曲構成の切れ目（イントロ→Aメロ 等）を推定する."""
    import librosa
    import scipy.signal

    try:
        mfcc = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13, hop_length=HOP)
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr, hop_length=HOP)
        feat = np.vstack([librosa.util.normalize(mfcc, axis=1), chroma])
        step = max(1, int(0.25 * sr / HOP))  # 0.25 秒ごと
        feat = librosa.util.sync(feat, np.arange(0, feat.shape[1], step), aggregate=np.mean)
        times = np.arange(feat.shape[1]) * step * HOP / sr
        f = (feat - feat.mean(1, keepdims=True)) / (feat.std(1, keepdims=True) + 1e-9)
        f /= np.linalg.norm(f, axis=0, keepdims=True) + 1e-9
        ssm = f.T @ f
        k = 8  # 前後 2 秒ずつを比べる
        sign = np.r_[-np.ones(k), np.ones(k)]
        g = np.outer(sign, sign) * np.outer(np.hanning(2 * k), np.hanning(2 * k))
        pad = np.pad(ssm, k, mode="edge")
        nov = np.array([np.sum(pad[i:i + 2 * k, i:i + 2 * k] * g) for i in range(ssm.shape[0])])
        nov = np.maximum(nov, 0)
        nov /= nov.max() + 1e-9
        peaks, _ = scipy.signal.find_peaks(nov, height=0.2, distance=8)
        return times[peaks]
    except Exception as exc:
        log.debug("構成推定に失敗: %s", exc)
        return np.array([])
