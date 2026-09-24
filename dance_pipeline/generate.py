"""各区間のプロンプトを動画生成 API に自動送信し、dance_XX.mp4 として保存する.

- 既定は **ドライラン**（リクエスト内容を output/requests/ に書き出すだけで送信しない＝課金なし）。
  `--execute` を付けたときだけ API に送信する。
- 既に存在するクリップはスキップ（途中から再開可能）。`--force` で再生成（旧ファイルは clips/_old に退避）。
- 失敗した区間は output/failed_segments.json に記録。`--retry-failed` でその区間だけ再生成。
- 全リクエスト/結果は output/generation_log.jsonl に追記。
"""
from __future__ import annotations

import json
import shutil
import time
import traceback
from pathlib import Path

import requests

from .ffmpeg_utils import extract_last_frame, probe
from .providers import get_provider


def choose_duration(seg_len: float, allowed: list[float], max_stretch: float) -> float:
    """区間長をカバーできる最短の生成尺を選ぶ（max_stretch までのスロー補正を許容してコストを抑える）."""
    for d in sorted(allowed):
        if d * max_stretch >= seg_len:
            return d
    return max(allowed)


def prepare_upload_image(src: Path, work: Path, max_bytes: int = 1_500_000) -> Path:
    """アップロード用に JPEG 化して軽量化（元画像はそのまま）。縦横比は維持."""
    from PIL import Image

    if src.stat().st_size <= max_bytes and src.suffix.lower() in (".jpg", ".jpeg"):
        return src
    work.mkdir(parents=True, exist_ok=True)
    dst = work / "reference_upload.jpg"
    im = Image.open(src).convert("RGB")
    for q in (95, 90, 85, 80):
        im.save(dst, "JPEG", quality=q, optimize=True)
        if dst.stat().st_size <= max_bytes:
            break
    return dst


def _log(path: Path, rec: dict) -> None:
    rec = {"time": time.strftime("%Y-%m-%d %H:%M:%S"), **rec}
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(rec, ensure_ascii=False) + "\n")


def _load_failed(path: Path) -> dict:
    return json.loads(path.read_text()) if path.exists() else {}


def _download(url: str, dst: Path) -> None:
    tmp = dst.with_suffix(".part")
    with requests.get(url, stream=True, timeout=300) as r:
        r.raise_for_status()
        with tmp.open("wb") as f:
            for chunk in r.iter_content(1 << 20):
                f.write(chunk)
    tmp.rename(dst)


def run_generation(root: Path, plan: dict, cfg: dict, provider: str | None = None, execute: bool = False,
                   only: list[int] | None = None, retry_failed: bool = False, force: bool = False) -> dict:
    gcfg = cfg["generation"]
    execute = execute or bool(gcfg.get("execute"))
    pname = provider or gcfg["provider"]
    pcfg = gcfg["providers"][pname]
    prov = get_provider(pname, pcfg)
    od = root / cfg.get("output_dir", "output")
    clips = od / "clips"
    reqdir = od / "requests" / pname
    clips.mkdir(parents=True, exist_ok=True)
    reqdir.mkdir(parents=True, exist_ok=True)
    log_path = od / "generation_log.jsonl"
    failed_path = od / "failed_segments.json"
    failed = _load_failed(failed_path)

    ref = root / plan["reference_image"] if plan.get("reference_image") else None
    if ref is None or not ref.exists():
        raise SystemExit("基準画像が見つかりません（segments.json の reference_image）。")

    ref = prepare_upload_image(ref, od / "_work")
    ok_avail, reason = prov.available()
    if execute and not ok_avail:
        print(f"[generate] {pname}: {reason}")
        print("[generate] API キーが無いためドライランに切り替えます（MANUAL_STEPS.md 参照）。")
        execute = False

    segs = plan["segments"]
    if only:
        segs = [s for s in segs if s["index"] in only]
    if retry_failed:
        segs = [s for s in segs if s["id"] in failed]
    max_stretch = cfg["assemble"].get("max_stretch", 1.2)
    summary = {"provider": pname, "execute": execute, "done": [], "skipped": [], "failed": [], "dry_run": []}
    prev_clip: Path | None = None

    for seg in segs:
        dst = clips / f"{seg['id']}.mp4"
        if dst.exists() and not force:
            print(f"[generate] {seg['id']}: 既存のためスキップ")
            summary["skipped"].append(seg["id"])
            prev_clip = dst
            continue
        dur = choose_duration(seg["duration"], pcfg["durations"], max_stretch)
        prompt = seg["prompt_short"] if prov.max_prompt_chars <= 1000 else seg["prompt"]
        start_img = ref
        if gcfg.get("chain_last_frame") and prev_clip is not None and prev_clip.exists():
            start_img = extract_last_frame(prev_clip, od / "_work" / f"lastframe_before_{seg['id']}.png")
        end_img = ref if gcfg.get("end_frame_is_reference") and not seg.get("is_last") else None
        req = prov.build_request(prompt=prompt, negative_prompt=seg.get("negative_prompt", ""), image=start_img,
                                 end_image=end_img, duration=dur)
        (reqdir / f"{seg['id']}.json").write_text(json.dumps(prov.redact(req), ensure_ascii=False, indent=2))
        if not execute:
            print(f"[generate] {seg['id']}: ドライラン（{pname}, 生成尺 {dur}s / 区間 {seg['duration']:.2f}s）→ "
                  f"output/requests/{pname}/{seg['id']}.json")
            summary["dry_run"].append(seg["id"])
            continue

        err = None
        for attempt in range(1, gcfg.get("max_retries", 2) + 2):
            try:
                print(f"[generate] {seg['id']}: 送信 ({pname}, {dur}s, try {attempt})")
                task_id = prov.submit(req)
                _log(log_path, {"id": seg["id"], "event": "submitted", "provider": pname, "task_id": task_id})
                t0 = time.time()
                while True:
                    status, url, perr = prov.poll(task_id)
                    if status == "succeeded":
                        break
                    if status == "failed":
                        raise RuntimeError(perr or "generation failed")
                    if time.time() - t0 > gcfg.get("timeout_sec", 1200):
                        raise TimeoutError(f"timeout waiting task {task_id}")
                    time.sleep(gcfg.get("poll_interval_sec", 10))
                if dst.exists():  # --force 時は旧ファイルを退避
                    old = clips / "_old" / f"{seg['id']}_{time.strftime('%Y%m%d-%H%M%S')}.mp4"
                    old.parent.mkdir(exist_ok=True)
                    shutil.move(str(dst), str(old))
                _download(url, dst)
                info = probe(dst)
                _log(log_path, {"id": seg["id"], "event": "succeeded", "task_id": task_id, "url": url, "video": info})
                failed.pop(seg["id"], None)
                summary["done"].append(seg["id"])
                prev_clip = dst
                err = None
                break
            except Exception as exc:  # 失敗は記録して次の区間へ
                err = f"{type(exc).__name__}: {exc}"
                _log(log_path, {"id": seg["id"], "event": "error", "attempt": attempt, "error": err,
                                "trace": traceback.format_exc()[-2000:]})
                print(f"[generate] {seg['id']}: 失敗 {err}")
                if "401" in err or "403" in err or "insufficient" in err.lower() or "balance" in err.lower():
                    break  # 認証/残高エラーはリトライしない
                time.sleep(5 * attempt)
        if err:
            failed[seg["id"]] = {"error": err, "time": time.strftime("%Y-%m-%d %H:%M:%S"), "provider": pname}
            summary["failed"].append(seg["id"])
        failed_path.write_text(json.dumps(failed, ensure_ascii=False, indent=2))

    print(f"[generate] 完了: 生成 {len(summary['done'])} / スキップ {len(summary['skipped'])} / "
          f"失敗 {len(summary['failed'])} / ドライラン {len(summary['dry_run'])}")
    if summary["failed"]:
        print("[generate] 失敗区間の再生成: python run_all.py generate --execute --retry-failed")
    return summary
