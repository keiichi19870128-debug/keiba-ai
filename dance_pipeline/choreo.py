"""振付設計: 区間ごとに K-POP 風 8 カウント振付を割り当てる.

設計方針
- 基準画像のポーズ（右手をカメラへ差し出し、左手をあごに添え、脚を大きく開いた低めのスタンス）を
  「シグネチャーポーズ」として振付に組み込む。画像→動画生成では各区間がこのポーズから始まるため、
  各 8 カウントの最後もこのポーズに戻して区間のつなぎ目を自然にする（ループ構造）。
- サビのポイント振付「Reach & Frame」は 3 つの分かりやすい形（差し出す→つかむ→ボディロールで下ろす）
  と肩ヒットで構成し、一般人でも真似しやすく、経験者が踊るとキレが出る設計。
- 全区間で肩・腕・腰・脚・体の向きを組み合わせ、手だけの振付にしない。
- テンポが遅め (≈83BPM) なので、1 拍の中にアクセント（ヒット/ポップ）と流れ（ロール/ウェーブ）を
  混ぜて間延びを防ぐ。
"""
from __future__ import annotations

SIGNATURE_POSE_JA = "シグネチャーポーズ（右手をカメラへ差し出す・左手をあごに添える・脚を大きく開いた低めのスタンス）"
SIGNATURE_POSE_EN = ("his signature pose from the reference image (right arm reaching toward the camera with an open palm, "
                     "left hand touching his jaw, wide low stance)")

HOOK_NAME = "Reach & Frame（リーチ＆フレーム）"

# 各フェーズ: (開始カウント, 終了カウント, 日本語, 英語(詳細), 英語(短縮版プロンプト用))。カウント 1 = 区間内最初の小節頭。
# カウント 0 以下 = 最初の小節頭より前のピックアップ。
TEMPLATES: dict[str, dict] = {
    'intro': {
        "name": 'Wake Up（目覚め）',
        "energy": '静→動。溜めてから動き出す',
        "phases": [
            (-8, 0, 'シグネチャーポーズのまま静止し、呼吸だけで胸を小さく上下させる（溜め）',
             'holds his signature pose almost still, only breathing',
             'holds the signature pose, breathing'),
            (1, 2, '1: 差し出した右手をゆっくり引き戻しながら髪をかき上げる。2: 同時に開いていた脚を肩幅に寄せ、首をゆっくり回す',
             'slowly pulls the right hand back and sweeps it through his hair while bringing his feet to shoulder width, slow head roll',
             'sweeps his right hand through his hair, feet come together'),
            (3, 4, '3-4: 右→左へステップタッチ。肩を拍に合わせて上下（ショルダーバウンス）',
             'step-touches right then left with relaxed shoulder bounces on the beat',
             'step-touches right and left with shoulder bounces'),
            (5, 6, '5-6: 胸を前に出すチェストポップ×2、膝を軽く曲げ重心を落とす',
             'does two sharp chest pops forward while bending the knees',
             'does two sharp chest pops, knees bent'),
            (7, 8, '7: 両腕を胸の前でクロス（X）→ 8: 腕を開きながら脚を大きく開き、シグネチャーポーズでキメ',
             'crosses both arms in an X in front of his chest, then opens them and lands back in his signature pose',
             'crosses arms in an X, then opens into the signature pose'),
        ],
        "hint_ja": '序盤は動きを小さく、8 カウント目のキメで一気に大きく。',
    },
    'verse': {
        "name": 'Glide Groove（グライド・グルーヴ）',
        "energy": '中。横揺れグルーヴで流れを作る',
        "phases": [
            (1, 2, '1-2: シグネチャーポーズから右手を体に引き寄せ、左へ体を向けながらスライドステップ（腰でリズムを取る）',
             'draws the right arm in and glides one step to his left, hips swaying with the groove',
             'glides one step left, hips swaying'),
            (3, 4, '3-4: 右手の指先から左手の指先へアームウェーブ。同時に膝でダウンのリズム',
             'does a smooth arm wave from the right fingertips across to the left, knees bouncing down on each beat',
             'does a smooth arm wave, knees bouncing'),
            (5, 6, '5-6: 正面に戻り、右肩→左肩の順にショルダーヒット、首も一緒にアクセント',
             'turns back to face the camera and hits right shoulder then left shoulder with small head accents',
             'faces the camera, hits right then left shoulder'),
            (7, 8, '7: 体を右斜め 45° に向けて肩越しにカメラを見る → 8: 正面に戻りシグネチャーポーズ',
             'turns 45 degrees to his right, glances back over his shoulder at the camera, then snaps back into his signature pose',
             'turns 45 degrees, looks back over his shoulder, then snaps into the signature pose'),
        ],
        "hint_ja": '足は小さく横移動のみ。フレームアウトしないよう前後移動は避ける。',
    },
    'pre_chorus': {
        "name": 'Rise Up（ビルドアップ）',
        "energy": '中→高。拍ごとに鋭くなるビルドアップ',
        "phases": [
            (1, 2, '1-2: その場で膝バウンス（だんだん強く）。両腕を体の横から頭上へゆっくり上げる',
             'bounces his knees in place, getting stronger, while raising both arms from his sides up over his head',
             'bounces his knees, raising both arms overhead'),
            (3, 4, '3-4: 頭上で手首をクロスし、上半身を左右にツイスト',
             'crosses his wrists above his head and twists his upper body left and right',
             'crosses wrists overhead, twisting his torso'),
            (5, 6, '5-6: 両拳を胸まで一気に引き下ろす（プルダウン）＋チェストポップ。ここが強いキメ',
             'sharply pulls both fists down to his chest with a strong chest pop, a clear hit',
             'pulls both fists down to his chest with a hard chest pop'),
            (7, 8, '7: 上体を少し後ろへ反らし溜める → 8: サビ頭に向けてシグネチャーポーズへ',
             'leans back slightly to build tension, then lands in his signature pose for the chorus',
             'leans back, then lands in the signature pose'),
        ],
        "hint_ja": 'サビ直前。5-6 のプルダウンを最も強いアクセントに。',
    },
    'chorus_A': {
        "name": HOOK_NAME + " ※ポイント振付",
        "energy": '高。曲の顔になる反復フック',
        "is_hook": True,
        "phases": [
            (1, 1, '1: シグネチャーポーズ（右手をカメラへ差し出す／左手はあご）',
             'starts in his signature pose, right hand reaching to the camera',
             'reaches to the camera in the signature pose'),
            (2, 2, '2: 差し出した右手をぐっと握って胸に引き寄せる（“つかむ”）。重心を左脚へ',
             'closes the reaching hand into a fist and pulls it to his chest as if grabbing something, weight shifts to the left leg',
             'grabs the air and pulls the fist to his chest'),
            (3, 4, '3-4: 両手を胸→お腹へなで下ろしながら胸から腰へボディロール、膝を曲げて沈む',
             'slides both hands down from chest to waist with a slow body roll from chest to hips, sinking into bent knees',
             'slides both hands down his chest in a slow body roll, knees bending'),
            (5, 6, '5: 右足を寄せて体を左 45° に向け右肩ヒット → 6: 左肩ヒットで顔だけカメラへ',
             'steps the right foot in, turns 45 degrees left and hits the right shoulder, then the left shoulder as his head snaps to the camera',
             'turns 45 degrees left, hits right shoulder, then left shoulder, head snaps to camera'),
            (7, 8, '7: 腰を右→左にスウェイ → 8: 脚を開いてシグネチャーポーズでキメ（右手をカメラへ）',
             'sways his hips right then left, then opens his stance and hits his signature pose again, reaching to the camera',
             'sways his hips, then hits the signature pose again'),
        ],
        "hint_ja": '“差し出す→つかむ→なで下ろす→肩・肩→差し出す”。サビで毎回繰り返す象徴的な振付。',
    },
    'chorus_B': {
        "name": 'Slide & Reveal（スライド＆リビール）',
        "energy": '高。フックの変化形で飽きさせない',
        "phases": [
            (1, 2, '1-2: 左へ大きくサイドスライド。右腕で頭上に大きな弧を描く',
             'does a wide side slide to his left while his right arm draws a big arc over his head',
             'slides left, right arm drawing a big arc overhead'),
            (3, 4, '3-4: 腰を大きく 1 回転させるヒップロール、両手は腰',
             'rolls his hips in a big circle with both hands on his hips',
             'rolls his hips in a big circle, hands on hips'),
            (5, 6, '5-6: 左手で顔の前を横切り（リビール）、首を傾けて目線をカメラへ。右足を半歩引く',
             'passes his left hand across his face like a reveal, tilts his head and locks eyes with the camera, right foot steps back',
             'passes his hand across his face as a reveal, eyes to camera'),
            (7, 8, '7: 両肩をすくめるショルダーシュラッグ → 8: シグネチャーポーズへ',
             'does a sharp shoulder shrug, then returns to his signature pose',
             'shrugs sharply, then returns to the signature pose'),
        ],
        "hint_ja": 'フックと同じ“最後はシグネチャーポーズ”で統一感を保つ。',
    },
    'chorus_to_break': {
        "name": 'Hook Cut → Freeze（フック短縮→ブレイクで静止）',
        "energy": '高→静。音が抜ける瞬間に止める',
        "phases": [
            (1, 2, '1: シグネチャーポーズ → 2: “つかむ” でフックの頭だけを見せる',
             'hits the signature reach, then grabs and pulls the fist to his chest',
             'reaches to the camera, then grabs to his chest'),
            (3, 4, '3-4: 右肩・左肩のショルダーヒット（フック後半の要素）',
             'does two sharp shoulder hits, right then left',
             'hits right then left shoulder'),
            (5, 6, '5-6: 音が抜けるブレイク。ピタッと静止→首だけをスローモーションで横へ回す',
             'the music drops out: he freezes completely, then turns only his head slowly to the side in slow motion',
             'freezes completely, then slowly turns only his head'),
            (7, 8, '7: 右手をゆっくり目の高さに上げる → 8: ドロップに備え、低めのシグネチャーポーズで溜める',
             'slowly raises his right hand to eye level, then settles into a low signature pose, ready for the drop',
             'raises his hand to eye level, then settles into a low signature pose'),
        ],
        "hint_ja": 'ブレイクは“止める”ことが最大の見せ場。動かしすぎない。',
    },
    'final_chorus': {
        "name": 'Heavy Drop（ヘビー・ドロップ）',
        "energy": '高（重低音）。重く大きく',
        "phases": [
            (1, 1, '1: ドロップと同時に右足で踏み込み（スタンプ）、両腕を一気に下へ振り下ろして胸を落とす',
             'on the drop he stomps his right foot and swings both arms down hard, dropping his chest',
             'stomps and swings both arms down hard on the drop'),
            (2, 4, '2-4: 低い重心のハーフタイム・ボディロール×2、肩を大きく使う',
             'does two heavy half-time body rolls in a low stance, using his shoulders big',
             'does two heavy body rolls in a low stance'),
            (5, 6, '5-6: フックの“差し出す→つかむ”をもう一度',
             'repeats the hook: reaches to the camera, then grabs and pulls the fist to his chest',
             'reaches to the camera, then grabs to his chest'),
            (7, 8, '7: 体を右へ 1/4 ターン → 8: 正面に戻ってシグネチャーポーズ',
             'does a quarter turn to his right, then turns back and hits his signature pose',
             'quarter-turns right, then back into the signature pose'),
        ],
        "hint_ja": '重低音に合わせて“重さ”を表現。上半身を落とすと格好良く見える。',
    },
    'ending': {
        "name": 'Final Pose（決めポーズ）',
        "energy": '高→静。最後の小節頭で明確な決めポーズを打ち、音が消えるまでホールド',
        "phases": [
            (1, 1, '1: シグネチャーポーズ（最後の“差し出す”）',
             'reaches to the camera in his signature pose one last time',
             'reaches to the camera in the signature pose'),
            (2, 2, '2: 差し出した手をつかんで胸へ引き寄せる',
             'grabs and pulls the fist to his chest',
             'grabs and pulls the fist to his chest'),
            (3, 3, '3: 胸→腰のボディロールで沈み、体を正面へ',
             'does a slow body roll sinking down, squaring his body to the camera',
             'does a slow body roll, squaring to the camera'),
            (4, 4, '4: 立ち上がりながら右手 2 本指を眉の横から前へ（サリュート）',
             'rises with a two-finger salute from his brow toward the camera',
             'rises with a two-finger salute'),
            (5, 99, '5〜最後: 最後の小節頭でキメ。脚を大きく開き、左手はベルト、右手の人差し指をまっすぐカメラへ、あごを引いて目線はカメラ。音が消えても完全静止でホールド',
             'hits the final pose on the last downbeat: wide stance, left hand on his belt, right index finger pointing straight at the camera, chin down, eyes locked on the camera, then holds completely still until the end',
             'hits the final pose: wide stance, left hand on belt, right finger pointing at the camera, then holds completely still'),
        ],
        "hint_ja": '最後は完全静止。動画の最後のフレームがそのままサムネイル候補になる。',
    },
}


def pick_template(seg: dict) -> str:
    labels = [c["label"] for c in seg["sections_covered"]]
    if seg["is_last"]:
        return "ending"
    if "break" in labels and len(labels) > 1:
        return "chorus_to_break"
    lab = seg["section"]
    if lab == "chorus":
        return "chorus_A" if seg.get("chorus_part") in (None, "A") else "chorus_B"
    if lab in TEMPLATES:
        return lab
    if lab == "break":
        return "chorus_to_break"
    return "verse"


def _count_times(seg: dict) -> dict[int, float]:
    """カウント番号 → 区間内相対秒。カウント 1 = 区間内で最初の小節頭."""
    beats = seg["beats"]
    first_db = next((i for i, b in enumerate(beats) if b["beat_in_bar"] == 1), 0)
    return {i - first_db + 1: b["rel"] for i, b in enumerate(beats)}


def build_choreography(segments: list[dict]) -> list[dict]:
    out = []
    for seg in segments:
        key = pick_template(seg)
        t = TEMPLATES[key]
        ct = _count_times(seg)
        seg_len = seg["duration"]
        counts = sorted(ct)
        phases = []
        for a, b, ja, en, en_short in t["phases"]:
            avail = [c for c in counts if a <= c <= b]
            if not avail:
                continue
            st = ct[avail[0]]
            nxt = [c for c in counts if c > avail[-1]]
            en_t = ct[nxt[0]] if nxt else seg_len
            if b >= 8 and not nxt:
                en_t = seg_len
            if a <= 0:
                st = 0.0
            phases.append({
                "counts": ("pickup" if a <= 0 else (str(avail[0]) if avail[0] == avail[-1] else f"{avail[0]}-{avail[-1]}")),
                "t_start": round(st, 2), "t_end": round(en_t, 2),
                "abs_start": round(seg["start"] + st, 2), "abs_end": round(seg["start"] + en_t, 2),
                "ja": ja, "en": en, "en_short": en_short,
            })
        # 最後のフェーズを区間末尾まで延ばす
        if phases:
            phases[-1]["t_end"] = round(seg_len, 2)
            phases[-1]["abs_end"] = round(seg["end"], 2)
        out.append({
            **seg,
            "template": key,
            "move_name": t["name"],
            "energy_ja": t["energy"],
            "is_hook": bool(t.get("is_hook")),
            "phases": phases,
            "hint_ja": t["hint_ja"],
        })
    return out
