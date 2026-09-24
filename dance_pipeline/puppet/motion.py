"""振付テンプレート（choreo.py と同じ名前）→ 拍に同期したポーズパラメータのキーフレーム.

2D パペットで破綻しにくい範囲（膝の曲げ伸ばし・重心移動・上体の傾き・肩ヒット・首・
右腕の引き寄せ/振り上げ・体の向きの擬似回転）で振付を再現する。
各エイトカウントの最後は静止ポーズ＝基準画像（シグネチャーポーズ）に戻る。
"""
from __future__ import annotations

import numpy as np

from .deform import PARAMS


def P(**kw) -> dict:
    return kw


def mix(*poses: dict) -> dict:
    out: dict = {}
    for p in poses:
        for k, v in p.items():
            out[k] = out.get(k, 0.0) + v
    return out


REST = P()
BOUNCE = P(root_y=22)
DEEP = P(root_y=48)
SWAY_R = P(root_x=24, torso=-4, hip=3)
SWAY_L = P(root_x=-24, torso=4, hip=-3)
GRAB = P(r_up=-35, r_lo=-70, root_x=-12)
ROLL1 = P(torso=-5, root_y=22, head=4)
ROLL2 = P(torso=4, root_y=46, root_x=10, head=-2)
SH_R = P(sh_r=-18, head=5, torso=-2)
SH_L = P(sh_l=-18, head=-5, torso=2)
ARMS_UP = P(r_up=55, r_lo=35, l_up=-10, l_lo=-12, root_y=-6)
PULL = P(r_up=-30, r_lo=-62, sh_r=8, sh_l=8, root_y=40, torso=-3)
POP = P(torso=-3, root_y=14, sh_l=-8, sh_r=-8)
XCROSS = P(r_up=-40, r_lo=-75, root_y=24, sh_l=-6)
STOMP = P(root_y=56, torso=-6, sh_l=10, sh_r=10, r_up=-10, head=6)
LEAN = P(root_y=-8, head=-6, torso=3)
TURN = P(turn=0.8, head=-6, torso=3)
RAISE = P(r_up=40, r_lo=40, head=-5)
SHRUG = P(sh_l=-20, sh_r=-20, head=3)
FINAL = P(root_y=18, head=3, r_up=-6)

# (カウント, ポーズ, イージング)  "hit"=拍ちょうどに鋭く到達 / "flow"=前のキーから滑らかに
TEMPLATES_MOTION = {
    "intro": [(0.0, REST, "flow"), (1, BOUNCE, "flow"), (2, RAISE, "flow"), (3, SWAY_R, "flow"), (4, SWAY_L, "flow"),
              (5, POP, "hit"), (5.5, BOUNCE, "flow"), (6, POP, "hit"), (7, XCROSS, "hit"), (8, REST, "hit")],
    "verse": [(1, mix(SWAY_L, P(turn=0.3)), "flow"), (2, mix(SWAY_L, BOUNCE), "flow"), (3, P(r_up=30, r_lo=30, root_y=10), "flow"),
              (4, P(r_up=-10, l_lo=-10, root_y=24), "flow"), (5, SH_R, "hit"), (6, SH_L, "hit"),
              (7, mix(TURN, P(head=14)), "flow"), (8, REST, "hit")],
    "pre_chorus": [(1, BOUNCE, "hit"), (2, mix(P(root_y=30), P(r_up=28, r_lo=18)), "flow"), (3, mix(ARMS_UP, P(torso=-4)), "flow"),
                   (4, mix(ARMS_UP, P(torso=4)), "flow"), (5, PULL, "hit"), (6, mix(PULL, P(root_y=12)), "hit"),
                   (7, LEAN, "flow"), (8, REST, "hit")],
    "chorus_A": [(1, REST, "hit"), (2, GRAB, "hit"), (3, mix(GRAB, ROLL1), "flow"), (4, mix(GRAB, ROLL2), "flow"),
                 (5, mix(SH_R, P(turn=0.6, r_up=-15, r_lo=-30)), "hit"), (6, mix(SH_L, P(turn=0.6, head=-4, r_up=-15, r_lo=-30)), "hit"),
                 (7, SWAY_R, "flow"), (7.5, SWAY_L, "flow"), (8, REST, "hit")],
    "chorus_B": [(1, P(root_x=-30, r_up=45, r_lo=30), "flow"), (2, P(root_x=-30, r_up=70, r_lo=30, root_y=10), "flow"),
                 (3, P(hip=5, root_x=-10, root_y=32), "flow"), (4, P(hip=-5, root_x=12, root_y=32), "flow"),
                 (5, P(l_up=-10, l_lo=-14, head=-9, root_y=10), "flow"), (6, P(head=6, root_y=22, turn=0.4), "hit"),
                 (7, SHRUG, "hit"), (8, REST, "hit")],
    "chorus_to_break": [(1, REST, "hit"), (2, GRAB, "hit"), (3, mix(GRAB, SH_R), "hit"), (4, mix(GRAB, SH_L), "hit"),
                        (5, mix(GRAB, P(head=-2)), "hit"), (6, mix(GRAB, P(head=-12)), "flow"),
                        (7, P(r_up=18, r_lo=18, head=-6, root_y=10), "flow"), (8, mix(REST, P(root_y=34)), "hit")],
    "final_chorus": [(1, STOMP, "hit"), (2, mix(ROLL1, P(root_y=30)), "flow"), (3, mix(ROLL2, P(root_y=14)), "flow"),
                     (4, mix(ROLL1, P(root_y=30)), "flow"), (5, REST, "hit"), (6, GRAB, "hit"), (7, TURN, "flow"),
                     (8, REST, "hit")],
    "ending": [(1, REST, "hit"), (2, GRAB, "hit"), (3, mix(ROLL2, P(root_y=10)), "flow"), (4, P(r_up=30, r_lo=50, root_y=-6), "hit"),
               (5, FINAL, "hit")],
}
# グルーヴ（拍ごとの小さな沈み込み）の強さ
GROOVE = {"intro": 6, "verse": 10, "pre_chorus": 12, "chorus_A": 14, "chorus_B": 14, "chorus_to_break": 12,
          "final_chorus": 16, "ending": 10}


def _ease(u: float, kind: str, dur: float) -> float:
    u = min(max(u, 0.0), 1.0)
    if kind == "hit":
        # 区間の最後 0.16 秒で一気に到達（拍の頭でピタッと止まる）
        w = min(0.16 / max(dur, 1e-3), 1.0)
        v = min(max((u - (1 - w)) / w, 0.0), 1.0)
        return 1 - (1 - v) ** 3
    return u * u * (3 - 2 * u)


def build_timeline(segments: list[dict], analysis: dict, fps: int = 30) -> dict:
    """曲全体のキーフレーム列（絶対秒）を作る."""
    keys: list[tuple[float, dict, str]] = [(0.0, REST, "flow")]
    groove_spans = []
    for seg in segments:
        tpl = seg["template"]
        kf = TEMPLATES_MOTION[tpl]
        beats = seg["beats"]
        first_db = next((i for i, b in enumerate(beats) if b["beat_in_bar"] == 1), 0)
        times = [b["time"] for b in beats]
        period = analysis["beat_period_sec"]

        def count_time(c: float) -> float:
            if c <= 0:
                return seg["start"]
            k = first_db + (c - 1)
            i0 = int(np.floor(k))
            frac = k - i0
            if i0 < len(times):
                t0 = times[i0]
            else:
                t0 = times[-1] + (i0 - len(times) + 1) * period
            return t0 + frac * period

        for c, pose, ease in kf:
            t = count_time(c)
            if t > seg["end"] + 0.01 and not seg["is_last"]:
                continue
            keys.append((t, pose, ease))
        amp = GROOVE.get(tpl, 10)
        groove_spans.append((seg["start"], seg["end"], amp, tpl))
    keys.sort(key=lambda k: k[0])
    return {"keys": keys, "groove": groove_spans}


def pose_at(t: float, tl: dict, analysis: dict, segments: list[dict]) -> dict:
    keys = tl["keys"]
    idx = int(np.searchsorted([k[0] for k in keys], t, side="right"))
    if idx >= len(keys):
        base = dict(keys[-1][1])
    else:
        t0, p0, _ = keys[idx - 1]
        t1, p1, ease = keys[idx]
        u = _ease((t - t0) / max(t1 - t0, 1e-6), ease, t1 - t0)
        base = {k: p0.get(k, 0.0) * (1 - u) + p1.get(k, 0.0) * u for k in PARAMS}
    # グルーヴ: 拍の直後に沈み、次の拍へ向けて戻る
    amp, tpl = 0.0, None
    for a, b, g, tp in tl["groove"]:
        if a <= t < b + 1e-6:
            amp, tpl = g, tp
    # ブレイク区間とエンディングの決めポーズ以降は静止
    brk = [s for s in analysis["sections"] if s["label"] == "break"]
    if any(s["start"] + 0.2 <= t < s["end"] for s in brk):
        amp = 0.0
    last = segments[-1]
    final_key = max(k[0] for k in keys)
    if t >= final_key - 0.05 and t >= last["start"]:
        amp = 0.0
    if amp:
        beats = [b["time"] for b in analysis["beats"]]
        i = int(np.searchsorted(beats, t, side="right")) - 1
        if 0 <= i < len(beats) - 1:
            ph = (t - beats[i]) / (beats[i + 1] - beats[i])
            dip = np.sin(np.pi * min(ph / 0.55, 1.0)) if ph < 0.55 else 0.0
            base["root_y"] = base.get("root_y", 0.0) + amp * dip
            base["head"] = base.get("head", 0.0) + 1.2 * dip * (1 if i % 2 else -1)
    return base
