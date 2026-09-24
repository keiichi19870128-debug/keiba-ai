# TikTok 歌詞付き縦動画 自動生成（generate_tiktok.py）

Suno などで作った曲を、**音源・歌詞・背景を入れ替えて 1 コマンド実行するだけ**で
TikTok にそのまま投稿できる歌詞付き縦動画にします。有料 API は使いません（すべてローカル・無料）。

```
input/
  song.mp3          ← 音源（mp3 / wav / m4a / flac）
  lyrics.txt        ← 歌詞（txt。タイム付きの .lrc でも可）
  background.mp4    ← 背景（mp4 / mov または jpg / png）

python generate_tiktok.py

output/
  final_tiktok.mp4      ← 完成動画（1080x1920 / 9:16 / 30fps / H.264 + AAC 320kbps / faststart）
  lyrics.ass            ← 動画に焼き込んだ字幕（アニメーション・強調入り）
  lyrics.srt            ← 汎用字幕（他の編集ソフト用）
  lyrics.lrc            ← 推定した歌詞タイミング（直して input に置けば次回その時刻で作成）
  lyrics_timing.json    ← フレーズごとの表示時刻（確認用）
  logs/generate_*.log   ← 実行ログ（エラーの原因調査用。ffmpeg のコマンドと出力も全部入り）
```

## 1. セットアップ（Windows・初回だけ）

1. **Python 3.10 以上** を入れる: https://www.python.org/downloads/ （インストール時に「Add python.exe to PATH」にチェック）
2. このフォルダでコマンドプロンプト（または PowerShell）を開き、ライブラリを入れる:

   ```bat
   python -m pip install -U pip
   pip install -r requirements-lyrics.txt
   ```

   - ffmpeg は `imageio-ffmpeg` に同梱の物（字幕描画 libass 入り）を自動で使うので、別途インストール不要です。
     PATH に自分の ffmpeg がある場合は、それが libass に対応していればそちらを使います。
   - `faster-whisper` は歌詞タイミングの自動合わせに使います。**初回実行時だけ**音声認識モデル
     （small ≈ 500MB）をダウンロードし、以後はオフラインで動きます。
3. （任意・精度をさらに上げたい場合）

   ```bat
   pip install stable-ts demucs
   ```

   - `stable-ts` … 歌詞テキストとボーカルの**強制アラインメント**（最優先で使われます）
   - `demucs` … 伴奏を消してボーカルだけにしてから解析（入っていれば自動で使用）
   - どちらも PyTorch が入るため数 GB あります。NVIDIA GPU がある場合は先に
     https://pytorch.org/get-started/locally/ の手順で CUDA 版 PyTorch を入れると高速です。

日本語フォントは `fonts/NotoSansJP-Black.otf`（SIL Open Font License, `fonts/OFL.txt`）を同梱しています。

## 2. 使い方

```bat
python generate_tiktok.py
```

- `input/` の中から音源・歌詞・背景を**自動検出**します（`input/` に音源が無ければ、このスクリプトと同じフォルダも探します）。
  - ファイル名は自由（日本語名も OK）。複数ある場合は `song` / `lyrics`・`歌詞` / `background`・`bg`・`背景`
    を含む名前が優先されます。背景は動画 > 画像の順で、`bg1.jpg` `bg2.jpg` … のように**背景らしい名前の画像が
    複数あると、小節頭でクロスフェードしながら切り替わるスライドショー**になります。
  - 背景が無い場合はゆっくり動くグラデーション背景、歌詞が無い場合は字幕なしで作ります。
  - **写真素材が無いとき**は `python tools/make_night_background.py` で「深夜・雨の窓・にじむ街の灯り」の
    背景動画（16 秒のシームレスループ、全部プログラムで描くので権利フリー）を `input/background.mp4` に作れます。
    `--seed 3` で配置違い、`--palette blue` / `warm` で色味違い、`--rain 0` で雨なし。
- 次の曲を作るときは `input/` の 3 ファイルを入れ替えて同じコマンドを実行するだけです。
  前回の `final_tiktok.mp4` や字幕は削除せず `output/_history/<日時>/` に退避されます。

| オプション | 内容 |
|---|---|
| `--preview` | 半分の解像度で素早く書き出し（`final_tiktok_preview.mp4`）。見た目の確認用 |
| `--variants 3` | 背景の動きを変えた動画を 3 本作る（`final_tiktok.mp4`, `final_tiktok_v2.mp4`, `_v3`）|
| `--method whisper` | タイミング推定方法を指定（`auto` / `lrc` / `align` / `sherpa` / `whisper` / `heuristic`）|
| `--ass output/lyrics.ass` | 手で直した ASS 字幕をそのまま使って再描画 |
| `--audio 曲.wav --lyrics 歌詞.txt --background 背景.mov` | 使うファイルを直接指定 |
| `--input 別フォルダ --output 出力先` | 素材フォルダ・出力先を変える |
| `--batch songs` | `songs/曲A/`, `songs/曲B/` … を 1 曲ずつまとめて作成（出力は `output/曲A/` …）|
| `-v` | 詳しい進行状況を表示 |

## 3. 歌詞ファイルの書き方

```
[Intro]

[Verse]
夜明け前の 交差点
信号待ちの 君を見てた

[Chorus]
走り出せ *今夜* だけは
誰にも止められない
```

- 1 行 = 1 フレーズ。空行や `[Verse]` `[Chorus]` などのタグ（Suno の歌詞そのままで OK）でブロックを区切ります。
- **サビ判定**: `[Chorus]` `[サビ]` `[Hook]` タグ → 無ければ「繰り返されるブロック」 → 無ければ「音量の大きいブロック」
  の順で自動判定し、サビは文字を少し大きく・ポップするアニメーションで表示します。
- **強調**: `*今夜*` のように `*` で囲んだ語は大きく・黄色で表示。囲みが無い場合は、繰り返し出る
  カタカナ語・英単語・スペース区切りの短い語を自動で強調します（`config.json` の `emphasis.words` で指定も可）。
  1 フレーズで強調するのは 1 語まで（`max_per_phrase`）なので「重要な単語だけ」が目立ちます。
- 長い行は、スペース → 句読点 → 助詞のあと（「〜の」「〜を」の後ろ）など自然な位置で
  短いフレーズ・最大 2 行に自動で分割し、画面幅からはみ出す場合は文字を縮めて収めます。
- **歌詞ファイルが無い場合、音源に埋め込まれた歌詞（Suno でダウンロードした mp3 には入っています）を自動で使います。**
  ただしセクションタグや強調の指定が無いので、見た目にこだわる場合は txt を用意してください。
- `#` で始まる行はコメントとして無視します。文字コードは UTF-8 / Shift_JIS / UTF-16 どれでも読めます。

## 4. 歌詞タイミングの決め方（自動）

`timing.method = "auto"` のとき、使えるものを上から順に試します。

| 順 | 方法 | 必要なもの | 精度 |
|---|---|---|---|
| 0 | 歌詞ファイルが LRC 形式（`[00:12.30]歌詞`）ならその時刻を使う | なし | 指定どおり |
| 1 | **stable-ts で歌詞テキストとボーカルを強制アラインメント** | `pip install stable-ts` | ◎ |
| 1.5 | **sherpa-onnx: ボーカル分離 (Spleeter) → 日本語音声認識 ReazonSpeech で 1 文字ごとの時刻を取得 → 歌詞と突き合わせ**（日本語の曲のみ） | `sherpa-onnx`（requirements に含む） | ◎ |
| 2 | **Whisper で文字起こし → 歌詞と文字単位で突き合わせ**（漢字/かなの違いは読みに直して比較） | `faster-whisper`（requirements に含む） | ○ |
| 3 | 歌声らしさ（中央定位の人声帯域）・無音・曲構成の切れ目・ビートから推定 | なし | △（目安） |

- 1〜2 は伴奏を消してボーカルだけにしてから解析します（`demucs` があれば demucs、無ければ sherpa-onnx の Spleeter）。
  sherpa-onnx のモデルは初回に GitHub (k2-fsa/sherpa-onnx Releases) から `models/` へ自動ダウンロードされます。結果は `output/_work/cache/` に保存され、
  同じ曲なら 2 回目以降は解析をスキップします（デザインだけ変えて何度も作り直すのが速い）。
- 一致率が低い（`timing.min_match_ratio` 未満）場合やモデルのダウンロードに失敗した場合は、自動で次の方法に切り替え、
  理由をログに残します。
- どの方法でも最後に、表示を少し早める（`lead_in_sec`）→ 近くの拍に吸着（`beat_snap`）→ 重なり防止・最短/最長表示時間の調整
  を行い、**歌詞の切り替えがビートに乗る**ようにしています。

### ずれを直したいとき

1. `output/lyrics.lrc` をメモ帳で開き、ずれている行の `[分:秒.百分の一秒]` を直す
2. `input/lyrics.lrc` として保存（`.lrc` があれば `.txt` より優先されます）
3. もう一度 `python generate_tiktok.py`

全体が一定量ずれているだけなら `config.json` の `timing.offset_sec`（例: `-0.2` で 0.2 秒早く）で調整できます。
細かな見た目を 1 か所だけ直したい場合は `output/lyrics.ass` を直接編集し `--ass output/lyrics.ass` で再描画できます。

## 5. config.json の設定（`"lyrics_video"` の中）

`config.json` はダンス動画パイプライン（下記）と共用で、歌詞動画の設定は `"lyrics_video"` の中にあります。
書かなかった項目は既定値が使われます。

**曲ごとの設定**: 素材フォルダ（例 `songs/赤い糸/`）に `config.json` を置くと、その曲だけ書いた項目が上書きされます。

```json
{ "emphasis": {"color": "#FF4D6D"}, "background": {"image_motion": "zoom_in", "image_zoom": 1.06} }
```

| 項目 | 既定値 | 内容 |
|---|---|---|
| **文字サイズ** `font.size` | `92` | 1080px 幅での文字の大きさ（px）。解像度を変えても比率は自動で合わせます |
| **フォント** `font.file` | `"auto"` | フォントファイル（例 `"fonts/MPLUSRounded1c-Black.ttf"`）。`fonts/` に自分で入れたフォントがあれば auto でも最優先 |
| `font.name` | `"auto"` | Windows にインストール済みのフォント名で指定する場合（例 `"Meiryo"`, `"BIZ UDPGothic"`）|
| `font.bold` | `true` | 太字 |
| **文字位置** `subtitle.position_y` | `0.60` | 歌詞の中心の高さ（0=上端, 1=下端）。0.5〜0.65 が中央〜中央下 |
| `subtitle.margin_x` | `90` | 左右の余白（px）。TikTok の右側ボタンに被らないよう広めに |
| `subtitle.safe_top` / `safe_bottom` | `0.14` / `0.24` | 上下の安全領域（画面比）。TikTok の説明文・ボタンに被らない範囲に歌詞を収めます |
| **字幕の最大行数** `subtitle.max_lines` | `2` | 一度に表示する最大行数 |
| `subtitle.phrase_max_chars` | `12` | 1 フレーズの目安の文字数（全角換算）。小さくするほど短く区切って切り替えが増えます |
| `subtitle.max_chars_per_line` | `0` | 1 行の最大文字数（0 = 画面幅から自動計算）|
| **字幕色** `subtitle.primary_color` | `"#FFFFFF"` | 文字色 |
| **縁取り** `subtitle.outline` / `outline_color` / `outline_blur` | `6` / `"#000000"` / `1.5` | 縁取りの太さ・色・ぼかし |
| `subtitle.shadow` / `shadow_color` / `shadow_alpha` | `3` / `"#000000"` / `0.55` | 影の距離・色・透明度 |
| `subtitle.letter_spacing` / `line_spacing` | `1` / `0.18` | 字間（px）・行間（文字サイズ比）|
| **字幕アニメーション** `subtitle.animation` | `"slide_up"` | `fade` / `slide_up`（下からふわっと）/ `pop`（ポンと弾む）/ `zoom`（ゆっくり拡大）/ `blur`（ぼかしから浮かぶ）/ `none` |
| `subtitle.fade_in_ms` / `fade_out_ms` | `180` / `160` | フェードの長さ |
| `subtitle.lead_in_sec` | `0.12` | 歌い出しより少し早く表示する秒数 |
| `subtitle.hold_sec` / `min_duration` / `max_duration` | `0.45` / `0.8` / `6.0` | 歌い終わり後の表示時間・最短/最長表示時間 |
| `subtitle.beat_snap` / `beat_snap_tolerance` | `true` / `0.16` | 切り替えを近くの拍（半拍）に合わせる / 合わせる最大ずれ（秒）|
| **サビの文字強調** `chorus.scale` | `1.15` | サビの文字サイズ倍率 |
| `chorus.animation` / `chorus.color` | `"pop"` / `null` | サビだけのアニメーション・文字色（null = 通常と同じ）|
| `chorus.detect` | `"auto"` | サビ判定: `auto` / `repeat`（繰り返し）/ `energy`（音量）|
| `emphasis.scale` / `emphasis.color` | `1.28` / `"#FFE45C"` | 強調語の倍率・色 |
| `emphasis.auto` / `emphasis.words` | `true` / `[]` | 強調語の自動抽出 / 必ず強調する語のリスト |
| **動画解像度** `video.width` / `video.height` | `1080` / `1920` | 出力解像度（9:16）|
| **FPS** `video.fps` | `30` | フレームレート |
| `video.crf` / `video.preset` | `18` / `"slow"` | 画質（小さいほど高画質）/ エンコード速度（`medium` にすると速い）|
| `video.audio_bitrate` / `audio_sample_rate` | `"320k"` / `"source"` | 音声ビットレート / サンプルレート（source = 元のまま）。元が AAC なら再エンコードせずコピー |
| `video.fade_in_sec` / `fade_out_sec` | `0.4` / `1.2` | 動画の最初と最後のフェード |
| **背景の明るさ** `background.brightness` | `0.78` | 背景の明るさ（1.0 = そのまま、小さいほど暗く＝歌詞が読みやすい）|
| `background.contrast` / `saturation` / `blur` / `vignette` | `1.0` / `1.0` / `0` / `true` | コントラスト・彩度・ぼかし・周辺減光 |
| `background.text_scrim` | `0.28` | 歌詞の周りだけ帯状にうっすら暗くする濃さ（0 で無効）|
| `background.fit` | `"cover"` | `cover`（縦にクロップ）/ `blur`（全体を表示し余白はぼかし背景）/ `auto`（横長素材だけ blur）|
| `background.video_start_sec` | `0` | 背景動画の使い始め位置 |
| `background.loop_crossfade_sec` | `1.0` | 背景動画が曲より短いときループの継ぎ目をクロスフェードする秒数（急なカットを防ぐ）|
| `background.image_motion` | `"auto"` | 画像の動き: `zoom_in` / `zoom_out` / `pan_left` / `pan_right` / `pan_up` / `pan_down` / `zoom_in_left` / `zoom_out_right`、`auto`、または `["zoom_in","pan_left"]` のようなリスト |
| `background.image_zoom` | `1.15` | Ken Burns のズーム量 |
| `background.image_crossfade_sec` | `1.2` | 複数画像の切り替えクロスフェード |
| `background.motion_seed` | `0` | 数字を変えると auto の動きの組み合わせが変わる |
| `timing.method` | `"auto"` | 上記「タイミングの決め方」参照 |
| `timing.whisper_model` | `"small"` | `base`（速い）/ `small` / `medium` / `large-v3`（高精度・遅い）|
| `timing.language` / `device` | `"ja"` / `"auto"` | 歌の言語 / `cpu` / `cuda` |
| `timing.vocal_separation` | `"auto"` | demucs があれば使う / `true` / `false` |
| `timing.offset_sec` | `0.0` | 全体のタイミングを一律にずらす（秒）|
| `timing.models_dir` | `"models"` | sherpa-onnx のモデルを置くフォルダ |
| `variants` | `1` | 1 回で作る本数（`--variants` と同じ）|
| `files.audio` / `lyrics` / `background` | `null` | ファイルを固定したい場合にパスを書く |

## 6. 動画の仕様

- 1080x1920（9:16）/ 30fps / H.264 High@4.2 / yuv420p / BT.709 / CRF 18
- 音声: AAC 320kbps（元が AAC ならコピーで無劣化）、長さは音源と同じ
- `+faststart` 付き MP4（スマホからそのまま TikTok にアップロードできます）
- 背景動画: 曲より長ければトリミング、短ければ継ぎ目をクロスフェードしてループ。縦にクロップ（または blur fit）
- 背景画像: 3 倍の解像度でズームしてから縮小するので、ゆっくりした Ken Burns でもガタつきません

## 7. トラブルシューティング

エラーが出ると「エラー: 〜」「対処: 〜」と表示され、詳細は `output/logs/generate_<日時>.log` に残ります。

| 症状 | 対処 |
|---|---|
| `ModuleNotFoundError` | `pip install -r requirements-lyrics.txt` |
| `ffmpeg が見つかりません` / `libass に対応していません` | `pip install -U imageio-ffmpeg`（または gyan.dev の full 版 ffmpeg を PATH に）|
| `whisper が失敗しました`（ダウンロード失敗など）| ネット接続を確認。失敗しても音声解析で推定して最後まで作ります |
| 文字が□になる / 別のフォントに見える | ログに「代用されています」と出ていないか確認し、`font.file` に日本語フォントを指定 |
| タイミングがずれる | 「ずれを直したいとき」を参照。`timing.whisper_model` を `medium` に、`pip install stable-ts demucs` も効果大 |
| 文字が TikTok のボタンに被る | `subtitle.position_y` を 0.55 前後に、`margin_x` を大きく |
| 処理が遅い | `video.preset` を `"medium"`、確認中は `--preview` |

---

# （別ツール）TikTok AI ダンス動画 自動制作パイプライン（run_all.py）

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
        ▼  python run_all.py generate                （既定: local = 無料・ローカル生成）
        ▼  python run_all.py generate --provider kling --execute   （API キーがある場合）
output/clips/dance_01.mp4 … dance_09.mp4
        │
        ▼  python run_all.py assemble
output/final_tiktok_dance.mp4  1080x1920 / 30fps / H.264 + AAC / 元音源で同期
（クリップ未生成の区間があると output/preview_animatic.mp4 = 絵コンテ入りのタイミング確認動画を作成）
```

## 無料のローカル生成（既定）

`--provider local`（config.json の既定）は外部 API を使わず、この PC 上だけでクリップを作ります。

1. 基準画像から人物の骨格（MediaPipe）と切り抜きを自動推定し、胴体・頭・左右の腕のレイヤーに分解
2. 人物を消した背景プレートを自動生成
3. 振付テンプレートを拍に同期したキーフレームに変換（膝の曲げ伸ばし・重心移動・上体の傾き・肩ヒット・
   首・腕の引き寄せ・体の向き）し、メッシュ変形 + 脚の IK で動かす
4. 強拍のズーム、サビ頭のフラッシュ、ドロップのカメラ揺れ、ブレイクのモノクロ静止、LED の明滅を拍に同期

4 コア CPU で 9 区間 ≈ 2.5 分、結合 ≈ 1.5 分。1 枚の画像を変形させる方式のため、動きの幅は AI 動画生成より小さめです
（腕を大きく回す・ターン・足を大きく踏み替える動きは再現しません）。より本格的な動きが必要になったら、
同じプロンプトで API 生成に切り替えてください（`--provider kling --execute` など、既存クリップは `--force` で作り直し）。

## セットアップ

```bash
pip install -r requirements.txt     # ffmpeg は imageio-ffmpeg 同梱のものを自動使用
```

## コマンド

| コマンド | 内容 |
|---|---|
| `python run_all.py plan` | 素材検出 → 音源解析 → 区間分割 → 振付設計 → プロンプト/一覧表の出力 |
| `python run_all.py generate` | 無料のローカル生成（`provider=local`）で `output/clips/dance_XX.mp4` を作成 |
| `python run_all.py generate --provider kling` | API 用の**ドライラン**（送信内容を `output/requests/` に保存。課金なし） |
| `python run_all.py generate --provider kling --execute` | API に実送信して `output/clips/dance_XX.mp4` を保存（既存クリップはスキップ） |
| `python run_all.py generate --execute --only 4,5` | 指定区間だけ生成 |
| `python run_all.py generate --execute --retry-failed` | 失敗記録 (`output/failed_segments.json`) の区間だけ再生成 |
| `python run_all.py generate --execute --only 4 --force` | 気に入らない区間を作り直し（旧クリップは `clips/_old/` に退避） |
| `python run_all.py assemble` | 結合して最終 MP4 を作成 |
| `python run_all.py all` | 全部まとめて（無料ローカル生成 → 結合） |

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
