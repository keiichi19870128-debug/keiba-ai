"""曲を動画生成 AI 向けの 5〜8 秒区間に分割する（ビート・フレーズ・曲調の切れ目を優先）.

候補点(全ビート)の上で動的計画法を解き、以下のコストが最小になる分割を選ぶ:
  - 区間長が [min_len, max_len] から外れるほど大きなペナルティ
  - 目標長 (target_len) からのずれ
  - 切れ目が小節頭でない / 拍の途中であるペナルティ
  - セクション境界(特にサビ頭・ドロップ)で切るとボーナス、区間内に取り込むとペナルティ
"""
from __future__ import annotations

import numpy as np

MAJOR = {"chorus", "final_chorus", "break"}


def plan_segments(analysis: dict, min_len=5.0, max_len=8.0, target_len=6.0, last_min_len=4.5) -> list[dict]:
    dur = analysis["duration_sec"]
    beats = analysis["beats"]
    sections = analysis["sections"]
    period = analysis["beat_period_sec"]

    # 候補点
    pts = [0.0]
    kinds = ["start"]
    for b in beats:
        if b["time"] < 0.5 * period or b["time"] > dur - 0.5:
            continue
        pts.append(b["time"])
        kinds.append({1: "downbeat", 3: "half_bar"}.get(b["beat_in_bar"], "beat"))
    pts.append(dur)
    kinds.append("end")
    pts = np.array(pts)

    # セクション境界の重み
    bounds = []
    for i in range(1, len(sections)):
        lab, prev = sections[i]["label"], sections[i - 1]["label"]
        w = 4.0 if (lab in MAJOR or prev == "break") else 2.5
        if lab == prev:
            w = 1.5  # サビ前半→後半など同種の区切り
        bounds.append((sections[i]["start"], w))

    def cut_cost(j: int) -> float:
        t, k = pts[j], kinds[j]
        c = {"start": 0.0, "end": 0.0, "downbeat": 0.0, "half_bar": 1.2, "beat": 2.5}[k]
        for bt, w in bounds:
            if abs(t - bt) < 0.08:
                c -= w
        return c

    def seg_cost(i: int, j: int) -> float:
        a, b = pts[i], pts[j]
        ln = b - a
        lo = last_min_len if j == len(pts) - 1 else min_len
        c = 0.35 * (ln - target_len) ** 2
        if ln < lo:
            c += 25.0 * (lo - ln) ** 2 + 5
        if ln > max_len:
            c += 25.0 * (ln - max_len) ** 2 + 5
        for bt, w in bounds:  # 境界を区間の途中に飲み込むペナルティ（端から 0.6 秒以上内側）
            if a + 0.6 < bt < b - 0.6:
                c += w * 0.8
        return c

    n = len(pts)
    best = np.full(n, np.inf)
    prev = np.full(n, -1)
    best[0] = 0.0
    for j in range(1, n):
        for i in range(j - 1, -1, -1):
            ln = pts[j] - pts[i]
            if ln > max_len + 2.5:
                break
            if ln < 3.0:
                continue
            c = best[i] + seg_cost(i, j) + cut_cost(j)
            if c < best[j]:
                best[j], prev[j] = c, i
    idx = [n - 1]
    while idx[-1] != 0:
        idx.append(int(prev[idx[-1]]))
    idx = idx[::-1]

    segs = []
    for k, (i, j) in enumerate(zip(idx[:-1], idx[1:]), start=1):
        a, b = float(pts[i]), float(pts[j])
        in_beats = [bt for bt in beats if a - 0.02 <= bt["time"] < b - 0.02]
        overl = []
        for s in sections:
            ov = min(b, s["end"]) - max(a, s["start"])
            if ov > 0.05:
                overl.append((ov, s))
        main = max(overl, key=lambda t: t[0])[1]
        segs.append({
            "index": k,
            "id": f"dance_{k:02d}",
            "start": round(a, 3),
            "end": round(b, 3),
            "duration": round(b - a, 3),
            "cut_type_start": kinds[i],
            "cut_type_end": kinds[j],
            "section": main["label"],
            "section_ja": main["label_ja"],
            "chorus_part": main.get("chorus_part"),
            "sections_covered": [
                {"label": s["label"], "start": max(a, s["start"]), "end": min(b, s["end"])} for _, s in overl
            ],
            "beats": [{"time": bt["time"], "rel": round(bt["time"] - a, 3), "beat_in_bar": bt["beat_in_bar"]} for bt in in_beats],
            "n_beats": len(in_beats),
            "accents": [round(x - a, 3) for x in analysis["accents"] if a <= x < b],
            "energy": round(float(np.mean([s["energy"] for _, s in overl])), 4),
            "is_first": k == 1,
            "is_last": j == n - 1,
        })
    return segs
