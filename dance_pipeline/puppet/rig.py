"""基準画像 → 人物マスク・骨格・部位レイヤー・メッシュ・スキニングウェイトを作る."""
from __future__ import annotations

import json
import warnings
from pathlib import Path

import cv2
import numpy as np

warnings.filterwarnings("ignore")

# 画像上の「右/左」ではなくダンサー本人から見た左右（MediaPipe 準拠）
JOINTS = ["nose", "l_sh", "r_sh", "l_el", "r_el", "l_wr", "r_wr", "l_hand", "r_hand", "l_hip", "r_hip",
          "l_knee", "r_knee", "l_ank", "r_ank", "l_toe", "r_toe", "l_heel", "r_heel"]


def detect_pose(img_bgr: np.ndarray) -> tuple[dict, np.ndarray]:
    import mediapipe as mp

    H, W = img_bgr.shape[:2]
    rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
    with mp.solutions.pose.Pose(static_image_mode=True, model_complexity=2, enable_segmentation=True) as p:
        r = p.process(rgb)
    if not r.pose_landmarks:
        raise RuntimeError("基準画像から人物の骨格を検出できませんでした。全身が写った画像を使ってください。")
    L = mp.solutions.pose.PoseLandmark
    lm = r.pose_landmarks.landmark

    def P(i):
        return np.array([lm[i].x * W, lm[i].y * H], dtype=np.float64)

    j = {
        "nose": P(L.NOSE), "l_ear": P(L.LEFT_EAR), "r_ear": P(L.RIGHT_EAR),
        "l_sh": P(L.LEFT_SHOULDER), "r_sh": P(L.RIGHT_SHOULDER),
        "l_el": P(L.LEFT_ELBOW), "r_el": P(L.RIGHT_ELBOW), "l_wr": P(L.LEFT_WRIST), "r_wr": P(L.RIGHT_WRIST),
        "l_hand": (P(L.LEFT_INDEX) + P(L.LEFT_PINKY) + P(L.LEFT_THUMB)) / 3,
        "r_hand": (P(L.RIGHT_INDEX) + P(L.RIGHT_PINKY) + P(L.RIGHT_THUMB)) / 3,
        "l_hip": P(L.LEFT_HIP), "r_hip": P(L.RIGHT_HIP), "l_knee": P(L.LEFT_KNEE), "r_knee": P(L.RIGHT_KNEE),
        "l_ank": P(L.LEFT_ANKLE), "r_ank": P(L.RIGHT_ANKLE), "l_toe": P(L.LEFT_FOOT_INDEX), "r_toe": P(L.RIGHT_FOOT_INDEX),
        "l_heel": P(L.LEFT_HEEL), "r_heel": P(L.RIGHT_HEEL),
    }
    j["neck"] = (j["l_sh"] + j["r_sh"]) / 2
    j["pelvis"] = (j["l_hip"] + j["r_hip"]) / 2
    return j, r.segmentation_mask


def refine_mask(img: np.ndarray, soft: np.ndarray) -> np.ndarray:
    """MediaPipe のマスクを GrabCut で輪郭をシャープに."""
    gc = np.full(soft.shape, cv2.GC_PR_BGD, np.uint8)
    gc[soft > 0.35] = cv2.GC_PR_FGD
    gc[soft > 0.85] = cv2.GC_FGD
    gc[soft < 0.05] = cv2.GC_BGD
    bgd, fgd = np.zeros((1, 65)), np.zeros((1, 65))
    cv2.grabCut(img, gc, None, bgd, fgd, 4, cv2.GC_INIT_WITH_MASK)
    m = np.where((gc == cv2.GC_FGD) | (gc == cv2.GC_PR_FGD), 255, 0).astype(np.uint8)
    # 最大連結成分のみ + 穴埋め
    n, lab, stats, _ = cv2.connectedComponentsWithStats(m)
    if n > 1:
        k = 1 + int(np.argmax(stats[1:, cv2.CC_STAT_AREA]))
        m = np.where(lab == k, 255, 0).astype(np.uint8)
    cnts, _ = cv2.findContours(m, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    filled = np.zeros_like(m)
    cv2.drawContours(filled, cnts, -1, 255, -1)
    return filled


def _seg_dist(pts: np.ndarray, a: np.ndarray, b: np.ndarray) -> np.ndarray:
    ab = b - a
    t = np.clip(((pts - a) @ ab) / max(ab @ ab, 1e-6), 0, 1)
    proj = a + t[:, None] * ab
    return np.linalg.norm(pts - proj, axis=1)


# ボーン: 名前 -> (始点関節, 終点関節, 所属レイヤー)
BONES = {
    "spine": ("pelvis", "neck", "body"),
    "l_clav": ("neck", "l_sh", "body"),
    "r_clav": ("neck", "r_sh", "body"),
    "l_thigh": ("l_hip", "l_knee", "body"),
    "l_shin": ("l_knee", "l_ank", "body"),
    "l_foot": ("l_ank", "l_toe", "body"),
    "r_thigh": ("r_hip", "r_knee", "body"),
    "r_shin": ("r_knee", "r_ank", "body"),
    "r_foot": ("r_ank", "r_toe", "body"),
    "head": ("neck", "nose", "head"),
    "l_upper": ("l_sh", "l_el", "l_arm"),
    "l_fore": ("l_el", "l_wr", "l_arm"),
    "l_palm": ("l_wr", "l_hand", "l_arm"),
    "r_upper": ("r_sh", "r_el", "r_arm"),
    "r_fore": ("r_el", "r_wr", "r_arm"),
    "r_palm": ("r_wr", "r_hand", "r_arm"),
}
LAYER_ORDER = ["body", "head", "r_arm", "l_arm"]


def label_parts(mask: np.ndarray, j: dict) -> np.ndarray:
    """人物ピクセルを部位レイヤーに割り当てる（0=背景 1=body 2=head 3=r_arm 4=l_arm）."""
    H, W = mask.shape
    ys, xs = np.nonzero(mask)
    pts = np.stack([xs, ys], 1).astype(np.float64)
    sh_w = np.linalg.norm(j["l_sh"] - j["r_sh"])
    lab = np.zeros(len(pts), np.uint8)

    # 腕: 上腕・前腕・手の線分からの距離（太さ ~ 肩幅の 0.28）で判定
    arm_r = 0.28 * sh_w
    d_l = np.minimum.reduce([_seg_dist(pts, j["l_sh"] * 0.25 + j["l_el"] * 0.75, j["l_el"]),
                             _seg_dist(pts, j["l_el"], j["l_wr"]), _seg_dist(pts, j["l_wr"], j["l_hand"] + (j["l_hand"] - j["l_wr"]) * 0.6)])
    d_r = np.minimum.reduce([_seg_dist(pts, j["r_sh"] * 0.25 + j["r_el"] * 0.75, j["r_el"]),
                             _seg_dist(pts, j["r_el"], j["r_wr"]), _seg_dist(pts, j["r_wr"], j["r_hand"] + (j["r_hand"] - j["r_wr"]) * 0.6)])
    # 頭: 鼻と耳を含む円
    head_c = (j["nose"] + j["l_ear"] + j["r_ear"]) / 3
    head_r = max(np.linalg.norm(j["l_ear"] - j["r_ear"]) * 0.95, 0.42 * sh_w)
    d_h = np.linalg.norm(pts - head_c, axis=1)
    neck_y = j["neck"][1] - 0.18 * sh_w

    # 手のひらは大きめ（カメラ側に差し出した手は遠近で大きく写る）
    hand_r = 0.45 * sh_w
    d_lh = np.linalg.norm(pts - j["l_hand"], axis=1)
    d_rh = np.linalg.norm(pts - j["r_hand"], axis=1)
    lab[:] = 1
    lab[(d_h < head_r * 1.7) & (pts[:, 1] < neck_y)] = 2
    lab[(d_r < arm_r) | ((d_rh < hand_r) & (d_rh < d_h * 0.9))] = 3
    # 体の外側へ突き出した指先も腕レイヤーへ（手の高さ付近で肩より外側）
    for side, k in (("r", 3), ("l", 4)):
        sh, hd = j[f"{side}_sh"], j[f"{side}_hand"]
        out_dir = np.sign(hd[0] - j["neck"][0]) or -1.0
        beyond = (pts[:, 0] - hd[0]) * out_dir > -0.1 * sh_w
        band = np.abs(pts[:, 1] - hd[1]) < 0.5 * sh_w
        near = np.linalg.norm(pts - hd, axis=1) < 1.1 * sh_w
        if k == 3:
            lab[beyond & band & near & (d_h > head_r)] = k
    lab[(d_l < arm_r) | ((d_lh < hand_r * 0.8) & (d_lh < d_h * 0.9))] = 4
    out = np.zeros((H, W), np.uint8)
    out[ys, xs] = lab
    # 小さな飛び地を整理
    for k in (2, 3, 4):
        m = (out == k).astype(np.uint8)
        n, cc, st, _ = cv2.connectedComponentsWithStats(m)
        if n > 2:
            keep = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
            out[(m > 0) & (cc != keep)] = 1
    return out


def build_mesh(region: np.ndarray, step: int = 22) -> tuple[np.ndarray, np.ndarray]:
    """領域（少し膨張）をカバーする三角メッシュ（格子点 + 輪郭点の Delaunay）."""
    reg = cv2.dilate(region, np.ones((9, 9), np.uint8))
    H, W = reg.shape
    pts = []
    for y in range(0, H, step):
        for x in range(0, W, step):
            if reg[y, x]:
                pts.append((x, y))
    cnts, _ = cv2.findContours(reg, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    for c in cnts:
        c = c[:, 0, :]
        for p in c[:: max(1, step // 2)]:
            pts.append(tuple(p))
    pts = np.unique(np.array(pts, np.float64), axis=0)
    subdiv = cv2.Subdiv2D((0, 0, W, H))
    for p in pts:
        subdiv.insert((float(min(p[0], W - 1)), float(min(p[1], H - 1))))
    tris = subdiv.getTriangleList().reshape(-1, 3, 2)
    idx = {tuple(np.round(p, 1)): i for i, p in enumerate(pts)}
    faces = []
    for t in tris:
        ids = [idx.get(tuple(np.round(v, 1))) for v in t]
        if None in ids:
            continue
        c = t.mean(0).astype(int)
        if reg[min(c[1], H - 1), min(c[0], W - 1)]:
            faces.append(ids)
    return pts, np.array(faces, np.int32)


def skin_weights(verts: np.ndarray, j: dict, bones: list[str], sigma: float) -> np.ndarray:
    d = np.stack([_seg_dist(verts, j[BONES[b][0]], j[BONES[b][1]]) for b in bones], 1)
    w = np.exp(-((d - d.min(1, keepdims=True)) / sigma) ** 2)
    # 足・すね等、遠いボーンの影響をカット
    w[d - d.min(1, keepdims=True) > 3 * sigma] = 0
    return w / w.sum(1, keepdims=True)


def fill_background(img: np.ndarray, mask: np.ndarray) -> np.ndarray:
    """人物を消した背景プレート.

    行ごとに左右の背景色を線形補間（壁・床の明るさの流れを保つ）→ 縦方向に平滑化 →
    背景の高周波成分（コンクリートの質感）をタイル状に重ねる。
    """
    m = cv2.dilate(mask, np.ones((31, 31), np.uint8)) > 0
    f = img.astype(np.float32)
    out = f.copy()
    H, W = m.shape
    for y in range(H):
        row = m[y]
        if not row.any():
            continue
        xs = np.nonzero(~row)[0]
        if len(xs) < 2:
            continue
        for c in range(3):
            out[y, row, c] = np.interp(np.nonzero(row)[0], xs, f[y, xs, c])
    sm = cv2.GaussianBlur(out, (0, 0), 6)
    out[m] = sm[m]
    # 質感: 人物のいない領域の高周波を左右反転して流用
    hp = f - cv2.GaussianBlur(f, (0, 0), 4)
    tex = hp[:, ::-1]
    tex_ok = ~m[:, ::-1]
    add = np.where(tex_ok[..., None], tex, 0)
    out[m] += add[m] * 0.8
    return np.clip(out, 0, 255).astype(np.uint8)


def build_rig(image_path: Path, cache: Path | None = None) -> dict:
    if cache and cache.exists():
        d = np.load(cache, allow_pickle=True)
        return d["rig"].item()
    img = cv2.imread(str(image_path))
    j, soft = detect_pose(img)
    mask = refine_mask(img, soft)
    parts = label_parts(mask, j)
    bg = fill_background(img, mask)

    layers = {}
    sh_w = np.linalg.norm(j["l_sh"] - j["r_sh"])
    for li, name in enumerate(LAYER_ORDER, start=1):
        region = (parts == li).astype(np.uint8) * 255
        if region.sum() == 0:
            continue
        # レイヤー画像: 他部位に隠れていた部分をそのレイヤーの色で補完（腕が動いたとき穴が出ないように）
        rgba = np.zeros((*img.shape[:2], 4), np.uint8)
        if name in ("body", "head"):
            # 腕に隠れていた部分だけを補完（腕が動いたときに穴が見えないように）
            hole = (parts >= 3).astype(np.uint8) * 255
            if name == "head":
                hole = hole & cv2.dilate(region, np.ones((41, 41), np.uint8))
            filled = cv2.inpaint(img, hole, 7, cv2.INPAINT_TELEA) if hole.any() else img.copy()
            alpha = np.maximum(region, hole)
            if name == "body":
                # 首・あご周りを下敷きとして胴体にも持たせ、頭が傾いても隙間が出ないようにする
                under = ((parts == 2) & (np.arange(parts.shape[0])[:, None] > j["nose"][1])).astype(np.uint8) * 255
                alpha = np.maximum(alpha, under)
                filled[under > 0] = img[under > 0]
            rgba[..., :3] = filled
        else:
            alpha = region
            rgba[..., :3] = img
        alpha = cv2.GaussianBlur(alpha, (0, 0), 1.2)
        rgba[..., 3] = alpha
        verts, faces = build_mesh((alpha > 10).astype(np.uint8) * 255, step=20 if name != "body" else 26)
        bones = [b for b, (_, _, ly) in BONES.items() if ly == name]
        if name in ("r_arm", "l_arm"):
            bones = bones + [("l_clav" if name == "l_arm" else "r_clav")]
        if name == "head":
            bones = ["head", "spine"]
        w = skin_weights(verts, j, bones, sigma=0.12 * sh_w)
        if name == "head":  # 頭は首より上を完全に head ボーンへ
            above = verts[:, 1] < j["neck"][1] - 0.12 * sh_w
            w[above] = [1.0, 0.0]
        layers[name] = {"rgba": rgba, "verts": verts, "faces": faces, "bones": bones, "weights": w}

    rig = {"joints": {k: v.tolist() for k, v in j.items()}, "mask": mask, "parts": parts, "bg": bg,
           "layers": layers, "size": img.shape[:2], "shoulder_width": float(sh_w)}
    if cache:
        cache.parent.mkdir(parents=True, exist_ok=True)
        np.savez_compressed(cache, rig=np.array(rig, dtype=object))
    return rig


def debug_image(rig: dict, out: Path) -> None:
    H, W = rig["size"]
    colors = {1: (80, 80, 200), 2: (80, 200, 80), 3: (200, 80, 80), 4: (200, 200, 60)}
    vis = rig["bg"].copy()
    ov = np.zeros_like(vis)
    for k, c in colors.items():
        ov[rig["parts"] == k] = c
    vis = cv2.addWeighted(vis, 0.6, ov, 0.4, 0)
    j = {k: np.array(v) for k, v in rig["joints"].items()}
    for b, (a, e, _) in BONES.items():
        cv2.line(vis, tuple(j[a].astype(int)), tuple(j[e].astype(int)), (255, 255, 255), 3)
    cv2.imwrite(str(out), vis)
