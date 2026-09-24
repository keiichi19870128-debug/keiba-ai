# 人間が行う必要がある最小限の操作

解析・区間分割・振付・プロンプト・生成スクリプト・結合スクリプトはすべて完成済みです。
残っているのは **「動画生成サービスで 9 本のクリップを作る」** 部分だけで、これはログイン/API キー/課金判断が
必要なため自動化を止めています（勝手な登録・課金はしていません）。

> この作業環境（クラウド）には API キーが無く、さらにネットワークポリシーで
> `api-singapore.klingai.com` / `api.dev.runwayml.com` などへの通信が遮断されていました。
> 生成は **手元の PC** で実行してください（クラウド環境で実行したい場合は、環境設定の Network access で
> 該当ホストを許可すれば同じコマンドが動きます）。

---

## 方法 A：API キーがある場合（ほぼ全自動・操作 3 つ）

1. 手元でリポジトリを取得し、依存を入れる
   ```bash
   pip install -r requirements.txt
   ```
2. API キーを `.env`（git 管理外）に書く。**使うサービスの行だけで OK**
   ```dotenv
   # Kling 公式 API（推奨：終了フレーム指定でつなぎ目が最も自然）
   KLING_ACCESS_KEY=xxxxxxxx
   KLING_SECRET_KEY=xxxxxxxx
   # Runway
   RUNWAYML_API_SECRET=key_xxxxxxxx
   # MiniMax (Hailuo)
   MINIMAX_API_KEY=xxxxxxxx
   # Luma（基準画像の公開 URL も config.json の providers.luma.image_url に必要）
   LUMAAI_API_KEY=xxxxxxxx
   # fal.ai（Kling / Pika / Hailuo を 1 つのキーで）
   FAL_KEY=xxxxxxxx
   ```
3. 実行（ここで初めて課金が発生します）
   ```bash
   python run_all.py generate                       # まずドライラン：送信内容と生成尺を確認（無料）
   python run_all.py generate --execute              # 9 区間を順番に生成 → output/clips/dance_01.mp4 …
   python run_all.py assemble                        # → output/final_tiktok_dance.mp4
   ```
   サービスを変える場合は `--provider runway` など。失敗した区間があれば
   `python run_all.py generate --execute --retry-failed` を実行してから `assemble`。

消費の目安（Kling 既定設定）：10 秒クリップ×1（dance_01）＋ 5 秒クリップ×8 = 合計 50 秒ぶん。
コストを下げたい場合は `config.json` の `providers.kling.mode` を `"std"` に変更してください。

---

## 方法 B：API キーが無い場合（Web 版の無料枠で手動生成）

Kling / Hailuo / Runway / Pika / Luma の Web 版は、無料プランやログインボーナスのクレジットで画像→動画を試せます
（無料枠の量・条件は各サービスの最新情報を確認してください）。

1 区間あたりの操作（×9 回）:

1. 各サービスの **Image to Video** を開き、`input/dancer_reference.png` をアップロード
   - 終了フレーム（End frame / Tail image）を指定できるサービスでは、**同じ基準画像を終了フレームにも**設定
     （`dance_09` だけは終了フレーム指定なし）
2. `output/video_prompts.md` の該当区間のプロンプトを貼り付け
   - 1000 文字制限があるサービス（Runway など）は **短縮版**、それ以外は **詳細版**
   - ネガティブプロンプト欄があれば「共通ネガティブプロンプト」を貼り付け
3. 設定: 縦長 9:16、長さは `dance_01` のみ 10 秒、他は 5 秒（または 6 秒）、カメラ固定
4. 生成された動画をダウンロードし、**`output/clips/dance_01.mp4` … `dance_09.mp4`** の名前で保存

9 本そろったら（そろっていなくても途中確認可）:

```bash
python run_all.py assemble
```

- 9 本すべてあれば `output/final_tiktok_dance.mp4`（1080x1920 / 30fps / H.264+AAC / 元音源で同期）を作成
- 足りない区間は絵コンテで埋めた `output/preview_animatic.mp4` を作るので、どこが未生成か確認できます
- クリップの長さ・解像度・fps はバラバラで構いません（自動でトリム・スケール・同期します）

---

## 仕上がりチェック（1 分）

- `final_tiktok_dance.mp4` を再生し、崩れ（手指の破綻、顔の変化、フレームアウト）がある区間だけ作り直す
  - API: `python run_all.py generate --execute --only 6 --force`（旧クリップは `output/clips/_old/` に退避）
  - Web: 同じプロンプトで再生成して `dance_06.mp4` を置き換え
- `python run_all.py assemble` をもう一度実行

## TikTok への投稿

`output/final_tiktok_dance.mp4` をそのままアップロード（9:16・1080x1920・約 51.7 秒・音声付き MP4）。
TikTok 側で楽曲を追加する必要はありません（元音源を焼き込み済み）。
