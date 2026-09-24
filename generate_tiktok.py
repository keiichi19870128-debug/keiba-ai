#!/usr/bin/env python3
"""TikTok 用「歌詞付き縦動画」自動生成.

input/ に 音源(mp3/wav) + 歌詞(txt) + 背景(mp4/mov/jpg/png) を置いて

    python generate_tiktok.py

を実行すると output/final_tiktok.mp4（1080x1920 / 30fps / H.264 + AAC）と
output/lyrics.ass・output/lyrics.srt・output/lyrics.lrc を作ります。

主なオプション:
    --preview             半分の解像度で素早く確認用に書き出す
    --variants 3          背景の動き違いを 3 本作る (final_tiktok.mp4, final_tiktok_v2.mp4, ...)
    --method heuristic    タイミング推定方法を指定 (auto / align / whisper / heuristic)
    --ass output/lyrics.ass   手で直した ASS 字幕をそのまま使って再描画
    --batch songs/        songs/ の下のフォルダ 1 つ = 1 曲 としてまとめて作る
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import traceback
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from lyrics_video import lyrics as ly  # noqa: E402
from lyrics_video import timing as tm  # noqa: E402
from lyrics_video.audio import analyze  # noqa: E402
from lyrics_video.common import (StepError, backup_existing, deep_merge, ffmpeg_exe, load_config, log,  # noqa: E402
                                 setup_logging)
from lyrics_video.detect import detect_inputs  # noqa: E402
from lyrics_video.render import check_font, prepare_background, render_final, resolve_font, verify_output  # noqa: E402
from lyrics_video.subtitles import layout_params, write_subs  # noqa: E402


def build_subtitles(inp, a, cfg: dict, out_dir: Path, work: Path, method: str | None, font_name: str,
                    stamp: str, hist: Path) -> tuple[Path | None, str]:
    if inp.lyrics is None:
        inp.lyrics = ly.extract_embedded_lyrics(inp.audio, work)
    if inp.lyrics is None:
        log.warning("[歌詞] 歌詞ファイルが無いため、字幕なしで作成します")
        return None, "none"
    lines = ly.parse_lyrics(inp.lyrics)
    if cfg["chorus"]["enabled"] and cfg["chorus"]["detect"] in ("auto", "repeat"):
        ly.mark_chorus_by_repetition(lines)
    ly.mark_emphasis(lines, cfg)

    ct, used = tm.estimate(lines, a, inp.audio, work, cfg, method)
    if cfg["chorus"]["enabled"] and cfg["chorus"]["detect"] in ("auto", "energy") and not any(l.chorus for l in lines):
        tm.mark_chorus_by_energy(lines, ct, a)

    L = layout_params(cfg)
    phrases = ly.split_into_phrases(lines, L["row_units"], L["phrase_units"], int(cfg["subtitle"]["max_lines"]),
                                    float(cfg["chorus"]["scale"]) if cfg["chorus"]["enabled"] else 1.0,
                                    float(cfg["emphasis"]["scale"]) if cfg["emphasis"]["enabled"] else 1.0)
    tm.phrase_times(phrases, ct, a, cfg, used)
    log.info("[字幕] %d フレーズ（1 行あたり最大 全角 %.0f 文字 / 最大 %s 行）",
             len(phrases), L["row_units"], cfg["subtitle"]["max_lines"])
    for p in phrases:
        log.debug("  %6.2f-%6.2f %s %s", p.start, p.end, "★" if p.chorus else " ", " / ".join(p.rows))

    for name in ("lyrics.ass", "lyrics.srt", "lyrics.lrc", "lyrics_timing.json"):
        if cfg["keep_history"]:
            backup_existing(out_dir / name, hist, stamp)
    ass, srt = write_subs(out_dir, phrases, cfg, font_name)
    tm.write_lrc(out_dir / "lyrics.lrc", lines, ct)
    (out_dir / "lyrics_timing.json").write_text(json.dumps({
        "method": used, "audio": str(inp.audio), "lyrics": str(inp.lyrics),
        "phrases": [{"start": round(p.start, 3), "end": round(p.end, 3), "rows": p.rows, "chorus": p.chorus,
                     "sung": [round(x, 3) for x in p.extra.get("sung", (0, 0))]} for p in phrases],
    }, ensure_ascii=False, indent=2), encoding="utf-8")
    log.info("[字幕] %s / %s / lyrics.lrc を書き出しました（タイミング: %s）", ass.name, srt.name, used)
    return ass, used


def make_one(cfg: dict, input_dir: Path, out_dir: Path, args) -> list[Path]:
    t0 = time.time()
    stamp = time.strftime("%Y%m%d-%H%M%S")
    hist = out_dir / "_history"
    work = out_dir / "_work"
    work.mkdir(parents=True, exist_ok=True)
    ffmpeg_exe()  # 最初に ffmpeg を確認（無ければここで分かりやすいエラー）

    # 曲フォルダに config.json があれば、その曲だけ設定を上書き（書いた項目だけ変わる）
    song_cfg = input_dir / "config.json"
    if song_cfg.exists() and song_cfg.resolve() != (ROOT / "config.json").resolve():
        try:
            raw = json.loads(song_cfg.read_text(encoding="utf-8-sig"))
        except json.JSONDecodeError as exc:
            raise StepError(f"{song_cfg} の書式エラー: {exc}") from exc
        cfg = deep_merge(cfg, raw.get("lyrics_video", raw))
        log.info("[設定] 曲フォルダの設定を適用: %s", song_cfg)

    overrides = dict(cfg["files"])
    for k in ("audio", "lyrics", "background"):
        if getattr(args, k, None):
            overrides[k] = getattr(args, k)
    inp = detect_inputs(input_dir, overrides)
    a = analyze(inp.audio, work)
    D = a.duration

    font_name, fontsdir = resolve_font(cfg, ROOT, work)
    if args.ass:
        ass, used = Path(args.ass).resolve(), "ass"
        if not ass.exists():
            raise StepError(f"--ass で指定したファイルがありません: {args.ass}")
        log.info("[字幕] 指定された ASS をそのまま使用: %s", ass)
    else:
        ass, used = build_subtitles(inp, a, cfg, out_dir, work, args.method, font_name, stamp, hist)

    if ass is not None:
        first = next((ln for ln in ass.read_text(encoding="utf-8-sig").splitlines() if ln.startswith("Dialogue:")), "")
        if first:
            h, m, sec = first.split(",")[1].split(":")
            check_font(ass, fontsdir, font_name, int(h) * 3600 + int(m) * 60 + float(sec) + 0.3, work)

    outs = []
    n = max(1, int(args.variants or cfg.get("variants", 1)))
    base = Path(cfg["output_name"])
    for v in range(n):
        name = base.name if v == 0 else f"{base.stem}_v{v + 1}{base.suffix}"
        if args.preview:
            name = f"{Path(name).stem}_preview{base.suffix}"
        out = out_dir / name
        log.info("---- 動画 %d/%d: %s ----", v + 1, n, out.name)
        bg_in, chain = prepare_background(inp.backgrounds, inp.bg_kind, D, cfg, work, v, a.downbeats, args.preview)
        if cfg["keep_history"]:
            backup_existing(out, hist, stamp)
        render_final(bg_in, chain, inp.audio, ass, fontsdir, D, cfg, work, out, args.preview)
        verify_output(out, D, cfg)
        outs.append(out)
    log.info("完了 (%.0f 秒): %s", time.time() - t0, ", ".join(str(o) for o in outs))
    if used == "heuristic":
        log.info("※ タイミングは音声解析からの推定です。ずれが気になる場合は README の「ずれを直したいとき」を参照"
                 "（Whisper の導入、または output/lyrics.lrc を直して input/ に置く）。")
    return outs


def main() -> int:
    ap = argparse.ArgumentParser(description="TikTok 用 歌詞付き縦動画の自動生成")
    ap.add_argument("--config", default=str(ROOT / "config.json"))
    ap.add_argument("--input", help="素材フォルダ（既定: config の input_dir = input）")
    ap.add_argument("--output", help="出力フォルダ（既定: output）")
    ap.add_argument("--audio"), ap.add_argument("--lyrics"), ap.add_argument("--background")
    ap.add_argument("--method", choices=["auto", "lrc", "align", "sherpa", "whisper", "heuristic"])
    ap.add_argument("--variants", type=int, help="背景の動き違いを何本作るか")
    ap.add_argument("--preview", action="store_true", help="半分の解像度で素早く確認用に書き出す")
    ap.add_argument("--ass", help="この ASS 字幕をそのまま使う（手で直した字幕で再描画）")
    ap.add_argument("--batch", help="このフォルダの下のサブフォルダを 1 曲ずつ処理する")
    ap.add_argument("-v", "--verbose", action="store_true")
    args = ap.parse_args()

    cfg = load_config(Path(args.config))
    out_root = Path(args.output) if args.output else ROOT / cfg["output_dir"]
    out_root = out_root if out_root.is_absolute() else (Path.cwd() / out_root)
    log_path = setup_logging(out_root / "logs", args.verbose)
    log.debug("config = %s", json.dumps(cfg, ensure_ascii=False))
    log.debug("python = %s / platform = %s", sys.version, sys.platform)

    jobs: list[tuple[Path, Path]] = []
    if args.batch:
        bdir = Path(args.batch).resolve()
        for d in sorted(p for p in bdir.iterdir() if p.is_dir() and not p.name.startswith((".", "_"))):
            jobs.append((d, out_root / d.name))
        if not jobs:
            log.error("--batch のフォルダにサブフォルダがありません: %s", bdir)
            return 1
    else:
        in_dir = Path(args.input).resolve() if args.input else (ROOT / cfg["input_dir"])
        jobs.append((in_dir, out_root))

    failed = 0
    for in_dir, od in jobs:
        if len(jobs) > 1:
            log.info("==================== %s ====================", in_dir.name)
        try:
            make_one(cfg, in_dir, od, args)
        except StepError as exc:
            failed += 1
            log.error("エラー: %s", exc)
            if exc.hint:
                log.error("対処: %s", exc.hint)
            log.debug("traceback:\n%s", traceback.format_exc())
        except KeyboardInterrupt:
            log.error("中断しました")
            return 130
        except Exception as exc:  # 想定外のエラーも原因が追えるよう全文をログへ
            failed += 1
            log.error("想定外のエラー: %s: %s", type(exc).__name__, exc)
            log.debug("traceback:\n%s", traceback.format_exc())
    if failed:
        log.error("%d 件失敗しました。詳しいログ: %s", failed, log_path)
        return 1
    log.info("ログ: %s", log_path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
