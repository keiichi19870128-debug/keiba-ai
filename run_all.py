#!/usr/bin/env python3
"""TikTok 向け AI ダンス動画 自動制作パイプライン（ワンコマンド）.

使い方:
  python run_all.py plan                # 1〜6: 素材検出・音源解析・区間分割・振付・プロンプト・一覧表
  python run_all.py generate            # 8: 動画生成（既定はドライラン。--execute で実送信）
  python run_all.py assemble            # 9: 結合（未生成区間は絵コンテで埋めたプレビューを作る）
  python run_all.py all [--execute]     # 上記をまとめて実行
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dance_pipeline import analyze as an  # noqa: E402
from dance_pipeline.assemble import assemble  # noqa: E402
from dance_pipeline.choreo import build_choreography  # noqa: E402
from dance_pipeline.detect import detect_audio, detect_image  # noqa: E402
from dance_pipeline.docs import choreography_md, prompts_md  # noqa: E402
from dance_pipeline.io_utils import backup_existing, safe_write, write_json  # noqa: E402
from dance_pipeline.prompts import DEFAULT_CHARACTER, DEFAULT_SCENE, NEGATIVE_PROMPT, build_prompt, continuity_notes  # noqa: E402
from dance_pipeline.segment import plan_segments  # noqa: E402


def load_config() -> dict:
    return json.loads((ROOT / "config.json").read_text())


def out_dir(cfg: dict) -> Path:
    d = ROOT / cfg.get("output_dir", "output")
    d.mkdir(parents=True, exist_ok=True)
    return d


def find_inputs(cfg: dict, audio: str | None, image: str | None) -> tuple[Path, Path | None]:
    base = (ROOT / cfg.get("input_dir", ".")).resolve()
    a = Path(audio).resolve() if audio else detect_audio(base)
    i = Path(image).resolve() if image else detect_image(base)
    if a is None:
        sys.exit("音源ファイルが見つかりません。mp3/wav/m4a などをこのフォルダ（または input/）に置いてください。")
    print(f"[detect] audio = {a.relative_to(ROOT) if a.is_relative_to(ROOT) else a}")
    print(f"[detect] image = {i.relative_to(ROOT) if i and i.is_relative_to(ROOT) else i}")
    if i is None:
        print("[detect] ※基準画像が見つかりません。プロンプトは作成しますが、生成には画像が必要です。")
    return a, i


def cmd_plan(args, cfg) -> dict:
    od = out_dir(cfg)
    audio, image = find_inputs(cfg, args.audio, args.image)
    print("[analyze] 音源解析中 ...")
    analysis = an.analyze(audio)
    analysis["source_path"] = str(audio.relative_to(ROOT)) if audio.is_relative_to(ROOT) else str(audio)
    analysis["reference_image"] = (str(image.relative_to(ROOT)) if image and image.is_relative_to(ROOT) else (str(image) if image else None))
    print(f"[analyze] {analysis['duration_sec']:.2f}s  BPM≈{analysis['bpm']:.1f}  sections={[(s['label'], s['start']) for s in analysis['sections']]}")

    segs = plan_segments(analysis, **cfg["segment"])
    segs = build_choreography(segs)
    pc = cfg.get("prompt", {})
    character = pc.get("character") or DEFAULT_CHARACTER
    scene = pc.get("scene") or DEFAULT_SCENE
    for i, s in enumerate(segs):
        s["prompt"] = build_prompt(s, analysis["bpm"], character, scene)
        s["prompt_short"] = build_prompt(s, analysis["bpm"], character, scene, short=True)
        s["negative_prompt"] = NEGATIVE_PROMPT
        s["continuity_ja"] = continuity_notes(s, segs[i - 1] if i else None, segs[i + 1] if i + 1 < len(segs) else None)
        s["reference_image"] = analysis["reference_image"]
        s["output_file"] = f"clips/{s['id']}.mp4"
    print(f"[segment] {len(segs)} 区間: " + ", ".join(f"{s['start']:.2f}-{s['end']:.2f}" for s in segs))

    write_json(od / "audio_analysis.json", analysis)
    write_json(od / "segments.json", {
        "source_audio": analysis["source_path"], "reference_image": analysis["reference_image"],
        "duration_sec": analysis["duration_sec"], "bpm": analysis["bpm"], "segments": segs,
    })
    safe_write(od / "choreography_plan.md", choreography_md(analysis, segs))
    safe_write(od / "video_prompts.md", prompts_md(analysis, segs))
    print(f"[plan] 書き出し: {od.relative_to(ROOT)}/audio_analysis.json, segments.json, choreography_plan.md, video_prompts.md")
    return {"analysis": analysis, "segments": segs}


def load_plan(cfg) -> dict:
    od = out_dir(cfg)
    p = od / "segments.json"
    if not p.exists():
        sys.exit("segments.json がありません。先に `python run_all.py plan` を実行してください。")
    return json.loads(p.read_text())


def cmd_generate(args, cfg) -> dict:
    from dance_pipeline.generate import run_generation

    plan = load_plan(cfg)
    only = [int(x) for x in args.only.split(",")] if args.only else None
    return run_generation(ROOT, plan, cfg, provider=args.provider, execute=args.execute, only=only,
                          retry_failed=args.retry_failed, force=args.force)


def cmd_assemble(args, cfg) -> dict:
    od = out_dir(cfg)
    plan = load_plan(cfg)
    segs = plan["segments"]
    audio = ROOT / plan["source_audio"]
    image = ROOT / plan["reference_image"] if plan.get("reference_image") else None
    clips = od / "clips"
    clips.mkdir(exist_ok=True)
    missing = [s["id"] for s in segs if not (clips / f"{s['id']}.mp4").exists()]
    if missing and args.no_placeholders:
        sys.exit(f"未生成のクリップがあります: {missing}")
    target = od / ("final_tiktok_dance.mp4" if not missing else "preview_animatic.mp4")
    if missing:
        print(f"[assemble] 未生成 {len(missing)} 区間は絵コンテ(プレースホルダー)で埋めて {target.name} を作成します")
    backup_existing(target)
    ac = cfg["assemble"]
    rep = assemble(segs, audio, clips, target, od / "_work", image, xfade=ac["crossfade_sec"],
                   allow_placeholders=not args.no_placeholders, max_stretch=ac["max_stretch"],
                   duration=plan["duration_sec"])
    f = rep["final"]
    print(f"[assemble] {target.relative_to(ROOT)}: {f['width']}x{f['height']} {f['duration']:.2f}s audio={f['has_audio']}")
    return rep


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("command", choices=["plan", "generate", "assemble", "all"])
    ap.add_argument("--audio")
    ap.add_argument("--image")
    ap.add_argument("--provider", help="kling / runway / minimax / luma / fal（既定は config.json）")
    ap.add_argument("--execute", action="store_true", help="実際に API に送信する（課金が発生しうる）。無指定はドライラン")
    ap.add_argument("--only", help="生成する区間番号をカンマ区切りで指定 例: 4,5")
    ap.add_argument("--retry-failed", action="store_true", help="failed_segments.json に記録された区間だけ再生成")
    ap.add_argument("--force", action="store_true", help="既存クリップがあっても再生成（旧ファイルは clips/_old に退避）")
    ap.add_argument("--no-placeholders", action="store_true", help="未生成区間があれば結合しない")
    args = ap.parse_args()
    cfg = load_config()
    if args.command in ("plan", "all"):
        cmd_plan(args, cfg)
    if args.command in ("generate", "all"):
        cmd_generate(args, cfg)
    if args.command in ("assemble", "all"):
        cmd_assemble(args, cfg)


if __name__ == "__main__":
    main()
