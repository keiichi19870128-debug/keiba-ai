# 動画生成 AI 用プロンプト一覧

全区間で **同じ基準画像**（`input/dancer_reference.png`）を開始フレームに使い、下記プロンプトを送信します。
固定要素（同一人物・同じ黒系衣装・同じ髪型・同じスタジオ背景/照明/カメラ位置・全身常時フレーム内・9:16・K-POP style choreography・cool and confident mood・realistic human movement・natural body mechanics・no extra people・no sudden camera cuts・no distorted hands or limbs）は全プロンプトに含まれています。

**共通ネガティブプロンプト**（対応サービスのみ）:

```
extra people, crowd, second dancer, camera cut, scene change, zoom, camera shake, cropped feet, cropped head, out of frame, distorted hands, extra fingers, extra limbs, missing limbs, twisted joints, deformed face, face change, outfit change, color change, hair change, background change, blurry, low quality, text, watermark, logo
```

## 一覧表

| # | 開始秒 | 終了秒 | 曲の特徴 | 振付内容 | 前後とのつなぎ |
|---|---|---|---|---|---|
| dance_01 | 0.00 | 7.27 | イントロ：静→動。溜めてから動き出す | **Wake Up（目覚め）**<br>シグネチャーポーズのまま静止し、呼吸だけで胸を小さく上下させる（溜め） → 1: 差し出した右手をゆっくり引き戻しながら髪をかき上げる → 3-4: 右→左へステップタッチ → 5-6: 胸を前に出すチェストポップ×2、膝を軽く曲げ重心を落とす → 7: 両腕を胸の前でクロス（X）→ 8: 腕を開きながら脚を大きく開き、シグネチャーポーズでキメ | 開始フレーム＝基準画像（シグネチャーポーズ） / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_02)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_02 | 7.27 | 12.96 | Aメロ：中。横揺れグルーヴで流れを作る | **Glide Groove（グライド・グルーヴ）**<br>1-2: シグネチャーポーズから右手を体に引き寄せ、左へ体を向けながらスライドステップ（腰でリズムを取る） → 3-4: 右手の指先から左手の指先へアームウェーブ → 5-6: 正面に戻り、右肩→左肩の順にショルダーヒット、首も一緒にアクセント → 7: 体を右斜め 45° に向けて肩越しにカメラを見る → 8: 正面に戻りシグネチャーポーズ | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_01)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_03)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_03 | 12.96 | 18.65 | Bメロ(サビ前の盛り上げ)：中→高。拍ごとに鋭くなるビルドアップ | **Rise Up（ビルドアップ）**<br>1-2: その場で膝バウンス（だんだん強く） → 3-4: 頭上で手首をクロスし、上半身を左右にツイスト → 5-6: 両拳を胸まで一気に引き下ろす（プルダウン）＋チェストポップ → 7: 上体を少し後ろへ反らし溜める → 8: サビ頭に向けてシグネチャーポーズへ | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_02)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_04)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_04 | 18.65 | 24.31 | サビ：高。曲の顔になる反復フック | **Reach & Frame（リーチ＆フレーム） ※ポイント振付**<br>1: シグネチャーポーズ（右手をカメラへ差し出す／左手はあご） → 2: 差し出した右手をぐっと握って胸に引き寄せる（“つかむ”） → 3-4: 両手を胸→お腹へなで下ろしながら胸から腰へボディロール、膝を曲げて沈む → 5: 右足を寄せて体を左 45° に向け右肩ヒット → 6: 左肩ヒットで顔だけカメラへ → 7: 腰を右→左にスウェイ → 8: 脚を開いてシグネチャーポーズでキメ（右手をカメラへ） | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_03)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_05)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_05 | 24.31 | 30.00 | サビ：高。曲の顔になる反復フック | **Reach & Frame（リーチ＆フレーム） ※ポイント振付**<br>1: シグネチャーポーズ（右手をカメラへ差し出す／左手はあご） → 2: 差し出した右手をぐっと握って胸に引き寄せる（“つかむ”） → 3-4: 両手を胸→お腹へなで下ろしながら胸から腰へボディロール、膝を曲げて沈む → 5: 右足を寄せて体を左 45° に向け右肩ヒット → 6: 左肩ヒットで顔だけカメラへ → 7: 腰を右→左にスウェイ → 8: 脚を開いてシグネチャーポーズでキメ（右手をカメラへ） | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_04)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_06)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_06 | 30.00 | 35.69 | サビ：高。フックの変化形で飽きさせない | **Slide & Reveal（スライド＆リビール）**<br>1-2: 左へ大きくサイドスライド → 3-4: 腰を大きく 1 回転させるヒップロール、両手は腰 → 5-6: 左手で顔の前を横切り（リビール）、首を傾けて目線をカメラへ → 7: 両肩をすくめるショルダーシュラッグ → 8: シグネチャーポーズへ | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_05)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_07)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_07 | 35.69 | 41.35 | サビ：高→静。音が抜ける瞬間に止める | **Hook Cut → Freeze（フック短縮→ブレイクで静止）**<br>1: シグネチャーポーズ → 2: “つかむ” でフックの頭だけを見せる → 3-4: 右肩・左肩のショルダーヒット（フック後半の要素） → 5-6: 音が抜けるブレイク → 7: 右手をゆっくり目の高さに上げる → 8: ドロップに備え、低めのシグネチャーポーズで溜める | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_06)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾は低めのシグネチャーポーズで“溜め”、次区間の頭（ドロップ）で一気に動く / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_08 | 41.35 | 47.04 | ラストサビ/ドロップ(低音主体)：高（重低音）。重く大きく | **Heavy Drop（ヘビー・ドロップ）**<br>1: ドロップと同時に右足で踏み込み（スタンプ）、両腕を一気に下へ振り下ろして胸を落とす → 2-4: 低い重心のハーフタイム・ボディロール×2、肩を大きく使う → 5-6: フックの“差し出す→つかむ”をもう一度 → 7: 体を右へ 1/4 ターン → 8: 正面に戻ってシグネチャーポーズ | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_07)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 区間末尾（カウント8）は必ずシグネチャーポーズに戻し、次区間(dance_09)の開始フレームと一致させる / 区間切り替え点は小節頭。0.2 秒の短いクロスフェードで接続 / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |
| dance_09 | 47.04 | 51.72 | ラストサビ/ドロップ(低音主体)：高→静。最後の小節頭で明確な決めポーズを打ち、音が消えるまでホールド | **Final Pose（決めポーズ）**<br>1: シグネチャーポーズ（最後の“差し出す”） → 2: 差し出した手をつかんで胸へ引き寄せる → 3: 胸→腰のボディロールで沈み、体を正面へ → 4: 立ち上がりながら右手 2 本指を眉の横から前へ（サリュート） → 5〜最後: 最後の小節頭でキメ | 開始フレーム＝基準画像（シグネチャーポーズ） / 前区間(dance_08)の最後もシグネチャーポーズなので、同じ立ち位置・向きのまま始める / 最後の小節頭で決めポーズ→音が消えても完全静止で動画終端までホールド / 立ち位置は画面中央から動かさない（横移動は半歩〜1 歩まで） |

## 区間別プロンプト（コピペ用）

### dance_01（0.00–7.27 秒 / 7.27 秒）— Wake Up（目覚め）

- 生成尺の目安: 7.27 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1513 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.6s: he holds his signature pose almost still, only breathing. 1.6s-3.0s: he slowly pulls the right hand back and sweeps it through his hair while bringing his feet to shoulder width, slow head roll. 3.0s-4.4s: he step-touches right then left with relaxed shoulder bounces on the beat. 4.4s-5.8s: he does two sharp chest pops forward while bending the knees. 5.8s-7.3s: he crosses both arms in an X in front of his chest, then opens them and lands back in his signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 901 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.6s: he holds the signature pose, breathing. 1.6s-3.0s: he sweeps his right hand through his hair, feet come together. 3.0s-4.4s: he step-touches right and left with shoulder bounces. 4.4s-5.8s: he does two sharp chest pops, knees bent. 5.8s-7.3s: he crosses arms in an X, then opens into the signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_02（7.27–12.96 秒 / 5.69 秒）— Glide Groove（グライド・グルーヴ）

- 生成尺の目安: 5.69 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1492 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he draws the right arm in and glides one step to his left, hips swaying with the groove. 1.4s-2.9s: he does a smooth arm wave from the right fingertips across to the left, knees bouncing down on each beat. 2.9s-4.3s: he turns back to face the camera and hits right shoulder then left shoulder with small head accents. 4.3s-5.7s: he turns 45 degrees to his right, glances back over his shoulder at the camera, then snaps back into his signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 851 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he glides one step left, hips swaying. 1.4s-2.9s: he does a smooth arm wave, knees bouncing. 2.9s-4.3s: he faces the camera, hits right then left shoulder. 4.3s-5.7s: he turns 45 degrees, looks back over his shoulder, then snaps into the signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_03（12.96–18.65 秒 / 5.69 秒）— Rise Up（ビルドアップ）

- 生成尺の目安: 5.69 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1434 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he bounces his knees in place, getting stronger, while raising both arms from his sides up over his head. 1.4s-2.8s: he crosses his wrists above his head and twists his upper body left and right. 2.8s-4.3s: he sharply pulls both fists down to his chest with a strong chest pop, a clear hit. 4.3s-5.7s: he leans back slightly to build tension, then lands in his signature pose for the chorus. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 838 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he bounces his knees, raising both arms overhead. 1.4s-2.8s: he crosses wrists overhead, twisting his torso. 2.8s-4.3s: he pulls both fists down to his chest with a hard chest pop. 4.3s-5.7s: he leans back, then lands in the signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_04（18.65–24.31 秒 / 5.67 秒）— Reach & Frame（リーチ＆フレーム） ※ポイント振付

- 生成尺の目安: 5.67 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1673 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he starts in his signature pose, right hand reaching to the camera. 0.7s-1.4s: he closes the reaching hand into a fist and pulls it to his chest as if grabbing something, weight shifts to the left leg. 1.4s-2.8s: he slides both hands down from chest to waist with a slow body roll from chest to hips, sinking into bent knees. 2.8s-4.3s: he steps the right foot in, turns 45 degrees left and hits the right shoulder, then the left shoulder as his head snaps to the camera. 4.3s-5.7s: he sways his hips right then left, then opens his stance and hits his signature pose again, reaching to the camera. Repeatable signature hook move. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 987 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he reaches to the camera in the signature pose. 0.7s-1.4s: he grabs the air and pulls the fist to his chest. 1.4s-2.8s: he slides both hands down his chest in a slow body roll, knees bending. 2.8s-4.3s: he turns 45 degrees left, hits right shoulder, then left shoulder, head snaps to camera. 4.3s-5.7s: he sways his hips, then hits the signature pose again. Repeatable signature hook move. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_05（24.31–30.00 秒 / 5.69 秒）— Reach & Frame（リーチ＆フレーム） ※ポイント振付

- 生成尺の目安: 5.69 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1673 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he starts in his signature pose, right hand reaching to the camera. 0.7s-1.4s: he closes the reaching hand into a fist and pulls it to his chest as if grabbing something, weight shifts to the left leg. 1.4s-2.9s: he slides both hands down from chest to waist with a slow body roll from chest to hips, sinking into bent knees. 2.9s-4.3s: he steps the right foot in, turns 45 degrees left and hits the right shoulder, then the left shoulder as his head snaps to the camera. 4.3s-5.7s: he sways his hips right then left, then opens his stance and hits his signature pose again, reaching to the camera. Repeatable signature hook move. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 987 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he reaches to the camera in the signature pose. 0.7s-1.4s: he grabs the air and pulls the fist to his chest. 1.4s-2.9s: he slides both hands down his chest in a slow body roll, knees bending. 2.9s-4.3s: he turns 45 degrees left, hits right shoulder, then left shoulder, head snaps to camera. 4.3s-5.7s: he sways his hips, then hits the signature pose again. Repeatable signature hook move. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_06（30.00–35.69 秒 / 5.69 秒）— Slide & Reveal（スライド＆リビール）

- 生成尺の目安: 5.69 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1420 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he does a wide side slide to his left while his right arm draws a big arc over his head. 1.4s-2.8s: he rolls his hips in a big circle with both hands on his hips. 2.8s-4.3s: he passes his left hand across his face like a reveal, tilts his head and locks eyes with the camera, right foot steps back. 4.3s-5.7s: he does a sharp shoulder shrug, then returns to his signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 853 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he slides left, right arm drawing a big arc overhead. 1.4s-2.8s: he rolls his hips in a big circle, hands on hips. 2.8s-4.3s: he passes his hand across his face as a reveal, eyes to camera. 4.3s-5.7s: he shrugs sharply, then returns to the signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_07（35.69–41.35 秒 / 5.67 秒）— Hook Cut → Freeze（フック短縮→ブレイクで静止）

- 生成尺の目安: 5.67 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1411 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he hits the signature reach, then grabs and pulls the fist to his chest. 1.4s-2.8s: he does two sharp shoulder hits, right then left. 2.8s-4.3s: he the music drops out: he freezes completely, then turns only his head slowly to the side in slow motion. 4.3s-5.7s: he slowly raises his right hand to eye level, then settles into a low signature pose, ready for the drop. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 844 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-1.4s: he reaches to the camera, then grabs to his chest. 1.4s-2.8s: he hits right then left shoulder. 2.8s-4.3s: he freezes completely, then slowly turns only his head. 4.3s-5.7s: he raises his hand to eye level, then settles into a low signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_08（41.35–47.04 秒 / 5.69 秒）— Heavy Drop（ヘビー・ドロップ）

- 生成尺の目安: 5.69 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1418 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he on the drop he stomps his right foot and swings both arms down hard, dropping his chest. 0.7s-2.9s: he does two heavy half-time body rolls in a low stance, using his shoulders big. 2.9s-4.3s: he repeats the hook: reaches to the camera, then grabs and pulls the fist to his chest. 4.3s-5.7s: he does a quarter turn to his right, then turns back and hits his signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 840 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he stomps and swings both arms down hard on the drop. 0.7s-2.9s: he does two heavy body rolls in a low stance. 2.9s-4.3s: he reaches to the camera, then grabs to his chest. 4.3s-5.7s: he quarter-turns right, then back into the signature pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

### dance_09（47.04–51.72 秒 / 4.68 秒）— Final Pose（決めポーズ）

- 生成尺の目安: 4.68 秒以上（サービスの選択肢から自動選択）。開始フレーム = 基準画像

**詳細版**（Kling / Hailuo / Luma / fal 用, 1577 文字）

```text
Full-body dance video of the same young man from the reference image, same face, same tousled black hair with soft bangs, same all-black outfit: oversized black button-up shirt-jacket over a black T-shirt, black belt, black cargo pants with hanging straps, chunky black sneakers, in the same bare concrete dance studio, two vertical warm LED light tubes on the left and right walls, glossy reflective grey floor, same moody low-key lighting. His signature pose is the pose in the reference image: right arm reaching toward the camera, left hand at his jaw, wide low stance. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he reaches to the camera in his signature pose one last time. 0.7s-1.4s: he grabs and pulls the fist to his chest. 1.4s-2.1s: he does a slow body roll sinking down, squaring his body to the camera. 2.1s-2.7s: he rises with a two-finger salute from his brow toward the camera. 2.7s-4.7s: he hits the final pose on the last downbeat: wide stance, left hand on his belt, right index finger pointing straight at the camera, chin down, eyes locked on the camera, then holds completely still until the end. End on a clear frozen final pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

**短縮版**（Runway など 1000 文字上限のサービス用, 972 文字）

```text
The man from the reference image dances in the concrete studio with LED tubes. Signature pose = his pose in the reference image. Slow 83 BPM groove, moves land on the beat with crisp hits and smooth flow. 0.0s-0.7s: he reaches to the camera in the signature pose. 0.7s-1.4s: he grabs and pulls the fist to his chest. 1.4s-2.1s: he does a slow body roll, squaring to the camera. 2.1s-2.7s: he rises with a two-finger salute. 2.7s-4.7s: he hits the final pose: wide stance, left hand on belt, right finger pointing at the camera, then holds completely still. End on a clear frozen final pose. Same person, same black outfit, same hairstyle, same studio background, same lighting, same camera position. Static camera, no zoom, no sudden camera cuts. Full body always in frame, head to sneakers. 9:16 vertical TikTok dance video. K-POP style choreography, cool and confident mood, realistic human movement, natural body mechanics. No extra people, no distorted hands or limbs.
```

