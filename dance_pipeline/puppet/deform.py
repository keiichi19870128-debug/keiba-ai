"""ポーズパラメータ → 関節位置（FK + 脚 IK）→ メッシュ変形 → レイヤー合成."""
from __future__ import annotations

import math

import cv2
import numpy as np

from .rig import BONES, LAYER_ORDER

PARAMS = ["root_x", "root_y", "torso", "turn", "head", "head_y", "sh_l", "sh_r",
          "r_up", "r_lo", "l_up", "l_lo", "foot_l_x", "foot_r_x", "hip"]


def R(deg: float) -> np.ndarray:
    a = math.radians(deg)
    c, s = math.cos(a), math.sin(a)
    return np.array([[c, -s], [s, c]])


def _ik(hip, ank, l1, l2, knee_rest, hip_rest, ank_rest):
    d = ank - hip
    dist = np.linalg.norm(d)
    dist_c = min(dist, (l1 + l2) * 0.999)
    a = (l1 ** 2 - l2 ** 2 + dist_c ** 2) / (2 * dist_c)
    h = math.sqrt(max(l1 ** 2 - a ** 2, 0))
    u = d / max(dist, 1e-6)
    perp = np.array([-u[1], u[0]])
    # 膝の曲がる向きは静止ポーズと同じ側
    rd = ank_rest - hip_rest
    side = np.sign(np.cross(rd, knee_rest - hip_rest)) or 1.0
    if np.sign(np.cross(u, perp)) != side:
        perp = -perp
    return hip + u * a + perp * h


def pose_joints(J: dict, p: dict) -> dict:
    g = lambda k: p.get(k, 0.0)  # noqa: E731
    pel = J["pelvis"]
    pel2 = pel + np.array([g("root_x"), g("root_y")])
    Rt = R(g("torso"))
    U = lambda v: pel2 + Rt @ (v - pel)  # noqa: E731
    out = {"pelvis": pel2}
    out["neck"] = U(J["neck"])
    out["l_sh"] = U(J["l_sh"]) + np.array([0, g("sh_l")])
    out["r_sh"] = U(J["r_sh"]) + np.array([0, g("sh_r")])
    for side in ("l", "r"):
        up, lo = g(f"{side}_up"), g(f"{side}_lo")
        sh, el, wr, hd = J[f"{side}_sh"], J[f"{side}_el"], J[f"{side}_wr"], J[f"{side}_hand"]
        out[f"{side}_el"] = out[f"{side}_sh"] + R(g("torso") + up) @ (el - sh)
        out[f"{side}_wr"] = out[f"{side}_el"] + R(g("torso") + up + lo) @ (wr - el)
        out[f"{side}_hand"] = out[f"{side}_wr"] + R(g("torso") + up + lo) @ (hd - wr)
    out["nose"] = out["neck"] + R(g("torso") + g("head")) @ (J["nose"] - J["neck"]) + np.array([0, g("head_y")])
    Rh = R(g("torso") * 0.35 + g("hip"))
    for side in ("l", "r"):
        out[f"{side}_hip"] = pel2 + Rh @ (J[f"{side}_hip"] - pel)
        fx = np.array([g(f"foot_{side}_x"), 0.0])
        out[f"{side}_ank"] = J[f"{side}_ank"] + fx
        out[f"{side}_toe"] = J[f"{side}_toe"] + fx
        l1 = np.linalg.norm(J[f"{side}_knee"] - J[f"{side}_hip"])
        l2 = np.linalg.norm(J[f"{side}_ank"] - J[f"{side}_knee"])
        out[f"{side}_knee"] = _ik(out[f"{side}_hip"], out[f"{side}_ank"], l1, l2,
                                  J[f"{side}_knee"], J[f"{side}_hip"], J[f"{side}_ank"])
    return out


def bone_transforms(J: dict, P: dict) -> dict:
    T = {}
    for b, (a, e, _) in BONES.items():
        r = J[e] - J[a]
        n = P[e] - P[a]
        th = math.degrees(math.atan2(n[1], n[0]) - math.atan2(r[1], r[0]))
        s = np.linalg.norm(n) / max(np.linalg.norm(r), 1e-6)
        M = R(th)
        if abs(s - 1) > 0.02:  # ボーン方向のみ伸縮
            u = r / max(np.linalg.norm(r), 1e-6)
            S = np.eye(2) + (s - 1) * np.outer(u, u)
            M = M @ S
        T[b] = (M, J[a], P[a])
    return T


def deform_layer(layer: dict, T: dict) -> np.ndarray:
    V = layer["verts"]
    out = np.zeros_like(V)
    for k, b in enumerate(layer["bones"]):
        M, a, a2 = T[b]
        out += layer["weights"][:, k:k + 1] * ((V - a) @ M.T + a2)
    return out


def global_warp(V: np.ndarray, pivot_x: float, turn: float) -> np.ndarray:
    """体の向きの“回転”を横方向の圧縮で近似（turn=1 で約 45°）."""
    if abs(turn) < 1e-4:
        return V
    V = V.copy()
    V[:, 0] = pivot_x + (V[:, 0] - pivot_x) * (1 - 0.22 * abs(turn))
    return V


def render_layer(canvas: np.ndarray, layer: dict, Vd: np.ndarray) -> None:
    H, W = canvas.shape[:2]
    F = layer["faces"]
    Vs = layer["verts"]
    x0, y0 = np.floor(Vd.min(0)).astype(int) - 2
    x1, y1 = np.ceil(Vd.max(0)).astype(int) + 2
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    if x1 <= x0 or y1 <= y0:
        return
    bw, bh = x1 - x0, y1 - y0
    ids = np.zeros((bh, bw), np.int32)
    tri_d = Vd[F] - np.array([x0, y0])
    for i, t in enumerate(tri_d):
        cv2.fillConvexPoly(ids, np.round(t * 16).astype(np.int32), i + 1, lineType=cv2.LINE_8, shift=4)
    # 各三角形の 逆アフィン（出力 → 元画像）
    src = Vs[F]  # (n,3,2)
    dst = Vd[F]
    ones = np.ones((len(F), 3, 1))
    Dm = np.concatenate([dst, ones], 2)  # (n,3,3)
    det = np.linalg.det(Dm)
    ok = np.abs(det) > 1e-6
    A = np.zeros((len(F), 3, 2))
    A[ok] = np.linalg.solve(Dm[ok], src[ok])  # [x y 1] @ A = src
    A = np.concatenate([np.zeros((1, 3, 2)), A], 0)
    yy, xx = np.mgrid[y0:y1, x0:x1].astype(np.float32)
    Ai = A[ids]
    mx = (xx * Ai[..., 0, 0] + yy * Ai[..., 1, 0] + Ai[..., 2, 0]).astype(np.float32)
    my = (xx * Ai[..., 0, 1] + yy * Ai[..., 1, 1] + Ai[..., 2, 1]).astype(np.float32)
    mx[ids == 0] = -10
    my[ids == 0] = -10
    rgba = cv2.remap(layer["rgba"], mx, my, cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    a = rgba[..., 3:4].astype(np.float32) / 255.0
    roi = canvas[y0:y1, x0:x1]
    roi[:] = roi * (1 - a) + rgba[..., :3].astype(np.float32) * a


def render_pose(rig: dict, p: dict, J: dict | None = None) -> np.ndarray:
    if J is None:
        J = {k: np.array(v) for k, v in rig["joints"].items()}
    P = pose_joints(J, p)
    for k in J:
        P.setdefault(k, J[k])
    T = bone_transforms(J, P)
    canvas = rig["bg"].astype(np.float32).copy()
    pivot = float(P["pelvis"][0])
    # 影（足元の暗がり）を少し動かす
    for name in LAYER_ORDER:
        if name not in rig["layers"]:
            continue
        L = rig["layers"][name]
        Vd = global_warp(deform_layer(L, T), pivot, p.get("turn", 0.0))
        render_layer(canvas, L, Vd)
    return canvas
