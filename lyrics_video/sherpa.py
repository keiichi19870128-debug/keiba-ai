"""sherpa-onnx を使ったボーカル分離（Spleeter）と日本語音声認識（ReazonSpeech）.

PyTorch 不要・CPU で高速。モデルは初回に GitHub (k2-fsa/sherpa-onnx の Releases) から
models/ フォルダへ自動ダウンロードします（無料・以後オフライン）。
"""
from __future__ import annotations

import tarfile
import urllib.request
from pathlib import Path

import numpy as np

from .common import StepError, log

ROOT = Path(__file__).resolve().parents[1]
BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
MODELS = {
    "spleeter": ("source-separation-models", "sherpa-onnx-spleeter-2stems-fp16"),
    "reazonspeech": ("asr-models", "sherpa-onnx-zipformer-ja-reazonspeech-2024-08-01"),
}


def available() -> bool:
    try:
        import sherpa_onnx  # noqa: F401

        return True
    except ImportError:
        return False


def ensure_model(key: str, models_dir: Path) -> Path:
    tag, name = MODELS[key]
    d = models_dir / name
    if d.is_dir() and any(d.glob("*.onnx")):
        return d
    models_dir.mkdir(parents=True, exist_ok=True)
    url = f"{BASE}/{tag}/{name}.tar.bz2"
    tmp = models_dir / f"{name}.tar.bz2.part"
    log.info("[モデル] %s をダウンロード中（初回のみ）: %s", name, url)
    try:
        with urllib.request.urlopen(url, timeout=60) as r, open(tmp, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            while True:
                chunk = r.read(1 << 20)
                if not chunk:
                    break
                f.write(chunk)
                got += len(chunk)
                if total:
                    print(f"\r    {got * 100 // total:3d}% ({got >> 20}MB / {total >> 20}MB)", end="", flush=True)
        print()
        with tarfile.open(tmp, "r:bz2") as t:
            try:
                t.extractall(models_dir, filter="data")
            except TypeError:  # 古い Python
                t.extractall(models_dir)
    except Exception as exc:
        raise StepError(f"モデル {name} のダウンロードに失敗: {exc}",
                        f"ネット接続を確認するか、{url} を手動でダウンロードして models/ に展開してください。") from exc
    finally:
        tmp.unlink(missing_ok=True)
    return d


def separate_vocals(wav44: Path, out_wav: Path, models_dir: Path) -> Path:
    """Spleeter (2stems) でボーカルだけを取り出す."""
    import sherpa_onnx
    import soundfile as sf

    d = ensure_model("spleeter", models_dir)
    cfg = sherpa_onnx.OfflineSourceSeparationConfig(
        model=sherpa_onnx.OfflineSourceSeparationModelConfig(
            spleeter=sherpa_onnx.OfflineSourceSeparationSpleeterModelConfig(
                vocals=str(d / "vocals.fp16.onnx"), accompaniment=str(d / "accompaniment.fp16.onnx")),
            num_threads=4))
    sep = sherpa_onnx.OfflineSourceSeparation(cfg)
    x, sr = sf.read(str(wav44), dtype="float32", always_2d=True)
    if x.shape[1] == 1:
        x = np.repeat(x, 2, axis=1)
    out = sep.process(sample_rate=sr, samples=np.ascontiguousarray(x.T))
    sf.write(str(out_wav), np.asarray(out.stems[0].data).T, out.sample_rate)
    return out_wav


def _cut_points(x: np.ndarray, sr: int, lo: float = 10.0, hi: float = 18.0) -> list[int]:
    """音の小さい所で 10〜18 秒ごとに区切る（言葉の途中で切らないため）."""
    hop = int(0.05 * sr)
    n = len(x) // hop
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    cuts, pos = [0], 0
    while (len(x) - pos) / sr > hi:
        a, b = pos // hop + int(lo / 0.05), min(n, pos // hop + int(hi / 0.05))
        k = a + int(np.argmin(rms[a:b]))
        pos = k * hop
        cuts.append(pos)
    cuts.append(len(x))
    return cuts


def recognize_words(wav16: Path, models_dir: Path) -> list[tuple[float, float, str]]:
    """ReazonSpeech（日本語）で 1 文字ごとの時刻付きで認識する."""
    import sherpa_onnx
    import soundfile as sf

    d = ensure_model("reazonspeech", models_dir)
    rec = sherpa_onnx.OfflineRecognizer.from_transducer(
        encoder=str(d / "encoder-epoch-99-avg-1.int8.onnx"), decoder=str(d / "decoder-epoch-99-avg-1.onnx"),
        joiner=str(d / "joiner-epoch-99-avg-1.int8.onnx"), tokens=str(d / "tokens.txt"),
        num_threads=4, decoding_method="greedy_search")
    x, sr = sf.read(str(wav16), dtype="float32")
    if x.ndim > 1:
        x = x.mean(axis=1)
    words: list[tuple[float, float, str]] = []
    cuts = _cut_points(x, sr)
    for a, b in zip(cuts[:-1], cuts[1:]):
        st = rec.create_stream()
        st.accept_waveform(sr, x[a:b])
        rec.decode_stream(st)
        r = st.result
        ts = [t + a / sr for t in r.timestamps]
        for i, (tok, t) in enumerate(zip(r.tokens, ts)):
            nxt = ts[i + 1] if i + 1 < len(ts) else t + 0.35
            words.append((t, min(nxt, t + 0.8), tok))
        log.debug("[sherpa] %.1f-%.1fs: %s", a / sr, b / sr, r.text)
    return _drop_silent(words, x, sr)


def _drop_silent(words: list[tuple[float, float, str]], x: np.ndarray, sr: int) -> list[tuple[float, float, str]]:
    """歌声が無い所に付いた文字を直す.

    - 直後（3 秒以内）に歌声のある文字が続く → 時刻がずれているだけなので、その直前に移す
      （先頭の文字が 0 秒になる癖など）
    - それ以外 → 無音部分のノイズを誤認識したものとして捨てる
    """
    hop = int(0.05 * sr)
    n = len(x) // hop
    if n == 0:
        return words
    rms = np.sqrt(np.mean(x[: n * hop].reshape(n, hop) ** 2, axis=1) + 1e-12)
    thr = 0.06 * np.percentile(rms, 95)

    def voiced(t: float) -> bool:
        i0, i1 = max(0, int((t - 0.1) / 0.05)), min(n, int((t + 0.4) / 0.05) + 1)
        return i1 > i0 and float(rms[i0:i1].mean()) >= thr

    flags = [voiced(w[0]) for w in words]
    out: list[tuple[float, float, str]] = []
    for i, w in enumerate(words):
        if flags[i]:
            out.append(w)
            continue
        nxt = next((j for j in range(i + 1, len(words)) if flags[j]), None)
        if nxt is not None and words[nxt][0] - w[0] < 3.0:
            t = words[nxt][0] - 0.2 * (nxt - i)
            out.append((t, t + 0.2, w[2]))
            log.debug("[sherpa] 時刻を補正: %s %.2fs → %.2fs", w[2], w[0], t)
        else:
            log.debug("[sherpa] 無音部分の誤認識を除外: %.2fs %s", w[0], w[2])
    return out
