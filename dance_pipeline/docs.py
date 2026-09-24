"""choreography_plan.md / video_prompts.md を生成する."""
from __future__ import annotations

from .choreo import HOOK_NAME, SIGNATURE_POSE_JA, TEMPLATES
from .prompts import NEGATIVE_PROMPT


def _mmss(t: float) -> str:
    return f"{int(t // 60)}:{t % 60:05.2f}"


def _esc(s: str) -> str:
    return s.replace("|", "\\|").replace("\n", " ")


def choreography_md(analysis: dict, segs: list[dict]) -> str:
    hl = analysis["highlight"]
    lines = [
        "# 振付プラン（TikTok / K-POP 風 / 男性ソロ）",
        "",
        f"- 音源: `{analysis['source_file']}`　長さ **{analysis['duration_sec']:.2f} 秒**（音が鳴り終わるのは約 {analysis['music_end_sec']:.2f} 秒）",
        f"- テンポ: **約 {analysis['bpm']:.1f} BPM**（1 拍 ≈ {analysis['beat_period_sec']:.3f} 秒、1 小節 ≈ {analysis['beat_period_sec'] * 4:.2f} 秒）→ 1 区間 ≒ 2 小節 = 1 エイトカウント",
        f"- 最も印象が強い部分（サビ）: **{hl['start']:.2f}〜{hl['end']:.2f} 秒**",
        f"- 区間数: {len(segs)}（すべて小節頭で分割）",
        "",
        "## 曲の構成（自動解析）",
        "",
        "| 区間 | 開始 | 終了 | 構成 | 音量(相対) |",
        "|---|---|---|---|---|",
    ]
    for s in analysis["sections"]:
        lines.append(f"| {s['label']} | {s['start']:.2f} | {s['end']:.2f} | {s['label_ja']} | {s['energy']:.2f} |")
    lines += [
        "",
        "## 振付コンセプト",
        "",
        f"- **{SIGNATURE_POSE_JA}** を振付の“基準形”にする。基準画像がそのまま各区間の開始フレームになるため、"
        "各エイトカウントの 8 カウント目もこのポーズに戻す“ループ構造”にして、区間の継ぎ目を自然にする。",
        f"- サビのポイント振付 **{HOOK_NAME}**: 「差し出す → つかむ → なで下ろす（ボディロール）→ 右肩・左肩 → 差し出す」。"
        "3 つの形がはっきりしていて一般の人でも真似しやすく、ボディロールと肩ヒットのキレで経験者が踊ると格好良く見える。",
        "- テンポが遅めなので、ロール/ウェーブ（流れ）とヒット/ポップ（キメ）を 1 カウントおきに交互に入れて間延びを防ぐ。",
        "- 足は小さな横移動と重心移動が中心。前後移動・床に寝る動き・フルターンは避ける（全身が常に画面内＆AI 生成の破綻防止）。",
        "- ブレイク（音が抜ける 1 小節）は“止める”演出、その後の重低音ドロップは踏み込みで“重さ”を出す。",
        "- 最後の小節頭で決めポーズを打ち、音が消えても完全静止でホールド。",
        "",
        "### ポイント振付の覚え方（キャプションや解説動画用）",
        "",
        "| カウント | 動き |",
        "|---|---|",
    ]
    for a, b, ja, *_ in TEMPLATES["chorus_A"]["phases"]:
        lines.append(f"| {a if a == b else f'{a}-{b}'} | {_esc(ja.split(': ', 1)[-1] if ': ' in ja else ja)} |")
    lines += ["", "## 区間別の振付", ""]
    for s in segs:
        lines += [
            f"### {s['id']}　{s['start']:.2f}–{s['end']:.2f} 秒（{s['duration']:.2f} 秒）　{s['section_ja']} ／ {s['move_name']}",
            "",
            f"- 曲の特徴: {s['energy_ja']}（相対音量 {s['energy']:.2f}、拍数 {s['n_beats']}）",
            f"- ポイント: {s['hint_ja']}",
            "",
            "| カウント | 秒（曲全体） | 振付 |",
            "|---|---|---|",
        ]
        for p in s["phases"]:
            lines.append(f"| {p['counts']} | {p['abs_start']:.2f}–{p['abs_end']:.2f} | {_esc(p['ja'])} |")
        lines += ["", f"つなぎ: {s['continuity_ja']}", ""]
    return "\n".join(lines) + "\n"


def prompts_md(analysis: dict, segs: list[dict]) -> str:
    lines = [
        "# 動画生成 AI 用プロンプト一覧",
        "",
        "全区間で **同じ基準画像**（`input/dancer_reference.png`）を開始フレームに使い、下記プロンプトを送信します。",
        "固定要素（同一人物・同じ黒系衣装・同じ髪型・同じスタジオ背景/照明/カメラ位置・全身常時フレーム内・9:16・"
        "K-POP style choreography・cool and confident mood・realistic human movement・natural body mechanics・"
        "no extra people・no sudden camera cuts・no distorted hands or limbs）は全プロンプトに含まれています。",
        "",
        "**共通ネガティブプロンプト**（対応サービスのみ）:",
        "",
        "```",
        NEGATIVE_PROMPT,
        "```",
        "",
        "## 一覧表",
        "",
        "| # | 開始秒 | 終了秒 | 曲の特徴 | 振付内容 | 前後とのつなぎ |",
        "|---|---|---|---|---|---|",
    ]
    for s in segs:
        moves = " → ".join(p["ja"].split("。")[0] for p in s["phases"])
        lines.append(
            f"| {s['id']} | {s['start']:.2f} | {s['end']:.2f} | {_esc(s['section_ja'] + '：' + s['energy_ja'])} | "
            f"**{_esc(s['move_name'])}**<br>{_esc(moves)} | {_esc(s['continuity_ja'])} |"
        )
    lines += ["", "## 区間別プロンプト（コピペ用）", ""]
    for s in segs:
        lines += [
            f"### {s['id']}（{s['start']:.2f}–{s['end']:.2f} 秒 / {s['duration']:.2f} 秒）— {s['move_name']}",
            "",
            f"- 生成尺の目安: {s['duration']:.2f} 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像",
            "",
            f"**詳細版**（Kling / Hailuo / Luma / fal 用, {len(s['prompt'])} 文字）",
            "",
            "```text",
            s["prompt"],
            "```",
            "",
            f"**短縮版**（Runway など 1000 文字上限のサービス用, {len(s['prompt_short'])} 文字）",
            "",
            "```text",
            s["prompt_short"],
            "```",
            "",
        ]
    return "\n".join(lines) + "\n"
