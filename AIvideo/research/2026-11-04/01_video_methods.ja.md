# 写実的なAI動画の制作方法

このPCでは、まず参照画像の構図と光を決め、その画像を短く動かす **Image to Video** を試す。人物の外見、場所、衣装を基準画像で固定でき、失敗したショットだけ作り直せるためである。以下の工程は制作案であり、モデル間の画質順位を示すベンチマークではない。

## 入力と目的で手法を選ぶ

| 手法 | 入力 | 適した場面 | 作業上の注意 |
| --- | --- | --- | --- |
| Text to Video | 文章 | アイデア出し、背景、雰囲気の試作 | ショット間の同一人物や同じ機体は別途参照を管理する |
| Image to Video | 画像と動作説明 | 写実的な人物、商品、SF主人公の短い演技 | 開始画像の顔・手・影の破綻を先に直す |
| First and Last Frame | 開始と終了の画像 | 扉の開閉、カメラ移動、変身の始点と終点 | 中間で何が起こるかは生成後に確認する |
| Video to Video | 元動画、文章、参照画像等 | 演技やカメラの動きを活かした見た目変更 | 元映像の動きと生成後の形状保持を別々に評価する |
| マスク編集 | 動画と変更領域 | 背景・衣装の一部変更、不要物除去 | 境界と時間方向のちらつきを確認する |
| Audio to Video | 音声、必要に応じて画像 | セリフや歌、音に合わせた映像 | TTSと区別する。入力音声から映像を作る工程 |
| 実写と3Dの合成 | 撮影素材、3D素材、マスク | 精密な動作、同じ形の乗り物、繰り返し修正 | カメラ、遮蔽、影、色の整合を取る |

VACEは参照画像、動画変換、マスク付き動画編集を統合する研究実装で、公開モデルはWan2.1系等に分かれる。Wan2.2用ファイルと見なして混用しない。[VACE公式](https://github.com/ali-vilab/VACE)。開始・終了フレームは[ComfyUIのWan2.2例](https://docs.comfy.org/tutorials/video/wan/wan2_2)、音からの動画は[LTX Desktop](https://github.com/Lightricks/LTX-Desktop)で公開されている。

## ローカル生成の候補

| 候補 | 役割 | 選ぶ理由と条件 |
| --- | --- | --- |
| Wan2.2 TI2V 5B | テキストまたは画像から動画 | このPCの初回候補。公式PythonとComfyUIでメモリ条件が異なる |
| Wan2.2 A14B | T2V、I2V、開始終了フレーム | 5Bの後の比較対象。ComfyUI例では高ノイズ・低ノイズの重みを区別する |
| HunyuanVideo 1.5 | T2V、I2V、超解像 | 英語・中国語の公式資料がある。公式ソース実行はLinux要件 |
| LTX Desktop | 音付き動画と編集 | GUIでローカル生成を扱う候補。確認時の既定ローカルモデルはLTX 2.5 Fast |
| FramePack | 逐次的に伸ばす動画 | 長さとメモリの関係を調べる候補。長尺が短時間で完成することを意味しない |
| VACE | 参照やマスクを用いる動画編集 | AIによる素材修正や実写との橋渡しを比較する候補 |

出典: [Wan2.2](https://github.com/Wan-Video/Wan2.2)、[ComfyUI Wan2.2](https://docs.comfy.org/tutorials/video/wan/wan2_2)、[HunyuanVideo 1.5](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5)、[LTX Desktop](https://github.com/Lightricks/LTX-Desktop)、[FramePack](https://github.com/lllyasviel/FramePack)、[VACE](https://github.com/ali-vilab/VACE)。実機との照合は [ローカルPC資料](04_local_pc.ja.md) を参照する。

LTXのPythonリポジトリは、確認時には2.5用コンポーネントの分割配置を案内している。旧2.3の単一チェックポイント構成や、そのLoRAをそのまま2.5へ流用する想定は避ける。[LTX公式Python実装](https://github.com/Lightricks/LTX-2)。

## 写実性を作る制作案

まず「映画風」「高画質」などの抽象語を、画像に現れる条件へ置き換える。光がどこから当たるか、何が濡れているか、人物が何を一度だけ行うか、カメラがどう動くかを決める。

1. **基準画像を作る。** 顔、衣装、機体の輪郭、主光源、背景を決定する。皮膚を過度に平滑化せず、服の縫い目や金属の粗さを確認する。
2. **一つの動作を割り当てる。** 視線を上げる、手を伸ばす、ゆっくり振り返る、といった短い行動に分ける。
3. **カメラの動きを独立して決める。** 固定、ゆっくり接近、横移動などから一つ選ぶ。被写体の移動とカメラ移動を混同しない。
4. **複数候補から選ぶ。** 手、目、歯、足の接地、背景の直線、反射を等速再生と静止画で確認する。
5. **採用後に仕上げる。** 色合わせ、粒状感、字幕、効果音を編集で加える。字幕やHUDの正確な文字は編集側で作ると修正しやすい。

RunwayのGen-4向け公式ガイドは、高品質な入力画像と、動きを中心にした簡潔な文章、要素を一つずつ増やす試行を勧めている。**同ガイドは否定表現を推奨していない。** Wan等のnegative prompt欄を、そのままRunwayに持ち込む一般則にはしない。[Runway Gen-4公式ガイド](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide)。

## プロンプトの例

次はオリジナルの例。数値は撮影表現の指定であり、生成モデルが光学的に厳密に再現する保証はない。

**テキストからの写実ショット**

```text
Medium close-up of a field engineer on a rain-soaked rooftop at dusk.
She slowly raises her eyes toward a distant light.
Soft overcast light, a cool rim light from the right, natural skin texture,
damp fabric, subtle breathing. The camera makes a slow dolly in.
Restrained live-action cinematography, shallow depth of field.
```

**同じ画像を動かす場合の短い指示**

```text
The engineer slowly raises her eyes. Rain beads move down her jacket.
The camera gently moves closer while distant clouds drift behind her.
```

**固定画角の指示**

```text
Locked-off camera. The subject exhales, then looks toward the doorway.
```

Googleのフランス語公式ガイドでも、被写体、動作、環境、カメラ等へ分解する考え方を確認できる。資料の言語と、モデルが仕様上サポートする入力言語は別である。[Google動画プロンプトガイド](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/video-gen-prompt-guide?hl=fr)。

## クラウドを使う場合

| 候補 | 比較したい機能 | 導入前の確認事項 |
| --- | --- | --- |
| Runway Gen-4系 | 画像を基準にした動作、既存素材との併用 | 採用する版の機能、利用枠、出力条件。参照したガイドはGen-4専用 |
| Google Veo 3.1 GA | 音声付き生成、参照画像、開始終了フレーム | API提供経路、リージョン、割当、モデルID |
| Adobe Firefly | カメラや構図の制御、Adobe編集との接続 | Firefly独自モデルとパートナーモデルを区別する |

**2026年11月4日時点のAPI差分:** Gemini APIのVeo 3.1 Previewは公式ページ上で2026年10月22日終了と案内されている。ページ内に残る `veo-3.1-generate-preview` の古いサンプルを、そのまま実行手順に採用しない。[終了案内を含む公式ページ](https://aistudio.google.com/docs/veo)。

別経路のGoogle Cloud側では、確認時点のモデルページに `veo-3.1-generate-001` をGAとして掲載している。Gemini APIと同じ認証・利用枠だとは扱わない。[Veo 3.1 GA仕様](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate)。

Fireflyのスペイン語資料では、選ぶモデルによって使用できる設定が変わると明示されている。ドイツ語の公式実習は、実写のカメラ移動を参照として渡す手法を説明している。[Fireflyスペイン語手順](https://helpx.adobe.com/es/firefly/web/work-with-audio-and-video/work-with-video/generate-videos-using-text-prompts.html)、[ドイツ語カメラ参照実習](https://helpx.adobe.com/de/firefly/how-to/video-motion-reference.html)。

## 比較時の失敗の見分け方

| 見える問題 | 次の試行で変える項目 |
| --- | --- |
| 顔が別人へ変わる | 開始画像を統一し、顔の回転や長い移動を減らす |
| 指・機体・衣装が途中で変形 | 動きを単純化し、短く分割する。必要なら3Dや実写に切り替える |
| 背景が歪む | カメラ移動を抑え、直線の多い背景は別素材で合成する |
| 映像は綺麗だが重さがない | 接地、加減速、影、反動、音のタイミングを確認する |
| アップスケール後に不自然 | 元ショットの破綻を先に直す。超解像は形状の一貫性を保証しない |

この表は原因を切り分けるための制作上の仮説。モデルの診断結果ではない。
