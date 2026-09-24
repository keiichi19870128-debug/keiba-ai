# TikTok AI ダンス動画 自動制作パイプライン

約 51 秒のオリジナル曲 + 男性ダンサーの基準画像 1 枚から、**曲に同期した 9:16 / 1080x1920 の K-POP 風ダンス動画**を作るためのツール一式です。

```
input/song.mp3                 ← 音源（フォルダ直下 or input/ に置けば自動検出）
input/dancer_reference.png     ← 基準画像（同上）
        │
        ▼  python run_all.py plan
output/audio_analysis.json     長さ・BPM・ビート・強拍・構成・サビ・振付切替候補
output/segments.json           5〜8 秒の区間（小節頭で分割）＋振付＋プロンプト
output/choreography_plan.md    振付プラン（カウント表）
output/video_prompts.md        動画生成 AI 用プロンプト一覧（一覧表＋コピペ用）
        │
        ▼  python run_all.py generate --execute   （API キーがある場合）
output/clips/dance_01.mp4 … dance_09.mp4
        │
        ▼  python run_all.py assemble
output/final_tiktok_dance.mp4  1080x1920 / 30fps / H.264 + AAC / 元音源で同期
（クリップ未生成の区間があると output/preview_animatic.mp4 = 絵コンテ入りのタイミング確認動画を作成）
```

## セットアップ

```bash
pip install -r requirements.txt     # ffmpeg は imageio-ffmpeg 同梱のものを自動使用
```

## コマンド

| コマンド | 内容 |
|---|---|
| `python run_all.py plan` | 素材検出 → 音源解析 → 区間分割 → 振付設計 → プロンプト/一覧表の出力 |
| `python run_all.py generate` | **ドライラン**（送信内容を `output/requests/` に保存。課金なし） |
| `python run_all.py generate --execute` | API に実送信して `output/clips/dance_XX.mp4` を保存（既存クリップはスキップ） |
| `python run_all.py generate --execute --only 4,5` | 指定区間だけ生成 |
| `python run_all.py generate --execute --retry-failed` | 失敗記録 (`output/failed_segments.json`) の区間だけ再生成 |
| `python run_all.py generate --execute --only 4 --force` | 気に入らない区間を作り直し（旧クリップは `clips/_old/` に退避） |
| `python run_all.py assemble` | 結合して最終 MP4 を作成 |
| `python run_all.py all --execute` | 全部まとめて |

`--provider kling|runway|minimax|luma|fal` でサービスを切り替え（既定は `config.json`）。

## 手動で生成したクリップを使う場合

Web 版（Kling / Hailuo / Runway 等の無料枠）で生成した動画を `output/clips/dance_01.mp4` … の名前で置いて
`python run_all.py assemble` を実行するだけで、正規化（1080x1920・30fps）・区間長へのトリム・
短いクロスフェード・元音源との同期まで自動で行います。詳しくは [MANUAL_STEPS.md](MANUAL_STEPS.md)。

## 仕組みのポイント

- **区間分割**: 全ビートを候補点に、動的計画法で「5〜8 秒」「小節頭」「セクション境界（サビ頭・ドロップ）」を
  優先する分割を選択。機械的な等分はしていません。
- **同期**: 各クリップの 0 秒 = 区間の開始秒。クロスフェードは前クリップの“尾”と次クリップの先頭を境界から重ねるので、
  ズレが累積せず全体の長さ = 曲の長さになります。生成尺が区間より少し短い場合は最大 1.2 倍までのスロー補正、
  それでも足りない分は最終フレームを保持して埋めます。
- **つなぎ目**: 基準画像のポーズを「シグネチャーポーズ」として振付に組み込み、各エイトカウントの終わりをこのポーズに戻す
  ループ構造。Kling では `image_tail`（終了フレーム）にも基準画像を渡し、始点・終点を一致させます
  （`config.json` の `end_frame_is_reference`）。
- **安全**: 既定はドライラン。`--execute` を付けない限り外部 API に送信せず、課金は発生しません。
  既存ファイルは削除・上書きせず `output/_history/` や `output/clips/_old/` に退避します。
