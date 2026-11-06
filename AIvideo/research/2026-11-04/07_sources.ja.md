# 動画制作の一次資料一覧

2026年11月4日に本文を確認した38件。モデルやアプリの公式資料、モデルカード、制作会社の事例を集めた。言語別の翻訳や同じプロジェクトの別ファイルを含む資料数であり、独立した比較実験の件数ではない。機械可読版は [sources.json](sources.json)。

## 映像モデルと生成手法

| ID | 資料と発行元 | 言語 | 確認した内容 |
| --- | --- | --- | --- |
| V01 | [Wan2.2 official repository](https://github.com/Wan-Video/Wan2.2) — Wan-Video | en | T2V、I2V、5Bの24GB用コマンドとモデル系列。 |
| V02 | [Wan2.2 native workflow examples](https://docs.comfy.org/tutorials/video/wan/wan2_2) — Comfy Org | en | ComfyUIの5Bオフロード条件、構成ファイル、14Bと開始終了フレーム。 |
| V03 | [HunyuanVideo 1.5 README](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5) — Tencent Hunyuan | en | 14GBはオフロード有効時。ソース実行のOS要件はLinux。 |
| V04 | [HunyuanVideo 1.5 中文文档](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/README_CN.md) — Tencent Hunyuan | zh | 中国語の実行説明と蒸留モデルの更新。V03と同じプロジェクトで独立検証ではない。 |
| V05 | [LTX Desktop README](https://github.com/Lightricks/LTX-Desktop) — Lightricks | en | Windows要件、ローカル生成、任意クラウド機能、Qwenアシスタント。 |
| V06 | [LTX-2 Python inference README](https://github.com/Lightricks/LTX-2) — Lightricks | en | 確認時の2.5用分割コンポーネント、量子化とオフロード。 |
| V07 | [LTX-2.5 model card](https://huggingface.co/Lightricks/LTX-2.5) — Lightricks | en | 重みのゲート、モデル構成、Community License表示。 |
| V08 | [FramePack README](https://github.com/lllyasviel/FramePack) — lllyasviel | en | 逐次生成、Windows配布、最低VRAMと処理時間は別の条件。 |
| V09 | [VACE README](https://github.com/ali-vilab/VACE) — Tongyi Lab | en | 参照、動画変換、マスク編集。公開モデルごとにベース系列とライセンスが異なる。 |
| V10 | [Comfy Desktop for Windows](https://docs.comfy.org/installation/desktop/windows) — Comfy Org | en | 公式Windows導入経路と新しい標準保存先。 |
| V11 | [Gen-4 Video Prompting Guide](https://help.runwayml.com/hc/en-us/articles/39789879462419-Gen-4-Video-Prompting-Guide) — Runway | en | 入力画像と動作を重視する簡潔な指示。Gen-4で否定表現を一般化しない。 |
| V12 | [Veo 3.1 Gemini API guide and retirement notice](https://aistudio.google.com/docs/veo) — Google | en | Veo 3.1 Previewの2026年10月22日終了案内。旧URL ai.google.dev/gemini-api/docs/veo から転送。 |
| V13 | [Veo 3.1 GA model reference](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/veo/3-1-generate) — Google Cloud | en | GAモデルIDと提供経路。Gemini API Previewとは区別する。 |
| V14 | [Guide des prompts pour la génération de vidéos](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/video-gen-prompt-guide?hl=fr) — Google Cloud | fr | 被写体、動作、環境、カメラ等の分解。公式ローカライズ資料。 |
| V15 | [Generación de vídeos mediante indicaciones de texto](https://helpx.adobe.com/es/firefly/web/work-with-audio-and-video/work-with-video/generate-videos-using-text-prompts.html) — Adobe | es | モデル選択と生成設定。スペイン語公式資料。 |
| V16 | [Kamerabewegung von echtem Videomaterial übernehmen](https://helpx.adobe.com/de/firefly/how-to/video-motion-reference.html) — Adobe | de | カメラ移動を実写から参照するドイツ語の公式実習。 |

## 音声と音楽

| ID | 資料と発行元 | 言語 | 確認した内容 |
| --- | --- | --- | --- |
| A01 | [Qwen3-TTS README](https://github.com/QwenLM/Qwen3-TTS) — Qwen | en | 話者合成、声の設計、複製のモデル区分、分離環境、Web UI。 |
| A02 | [Qwen3-TTS CustomVoice model card](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) — Qwen | en | 日本語を含む言語と、CustomVoice重みのApache 2.0表示。 |
| A03 | [Fun-CosyVoice 3.0 README](https://github.com/FunAudioLLM/CosyVoice) — FunAudioLLM | en | 日本語を含む多言語TTS、ストリーミングと指示制御。 |
| A04 | [CosyVoice source license](https://github.com/FunAudioLLM/CosyVoice/blob/main/LICENSE) — FunAudioLLM | en | リポジトリのApache 2.0本文。各配布モデルは別途照合する。 |
| A05 | [Style-Bert-VITS2 README](https://github.com/litagin02/Style-Bert-VITS2) — litagin02 | ja, en | 日本語スタイル制御、Windows導入、CPU合成、AGPL表記。 |
| A06 | [Style-Bert-VITS2 model terms](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md) — litagin02 | ja | ソースコードと声モデルの条件を分離。声モデルごとの表記条件等。 |
| A07 | [Text to Speech documentation](https://elevenlabs.io/docs/overview/capabilities/text-to-speech) — ElevenLabs | en | 多言語の声、モデルごとの特性、出力形式。 |
| A08 | [MMAudio README](https://github.com/hkchengrex/MMAudio) — MMAudio authors / Sony AI / UIUC | en | 動画同期音、制約、コードMITと重みCC-BY-NCの区別。 |
| A09 | [Stable Audio Open 1.0 model card](https://huggingface.co/stabilityai/stable-audio-open-1.0) — Stability AI | en | テキストから音素材、47秒と44.1kHz、独自ライセンスへの参照。 |
| A10 | [AudioCraft README](https://github.com/facebookresearch/audiocraft) — Meta / Facebook Research | en | MusicGen等、コードMITと重みCC-BY-NCの区別。 |
| A11 | [MuseTalk README](https://github.com/TMElyralab/MuseTalk) — Tencent Music Entertainment Lyra Lab | en | 音声から口の同期、顔領域の限界、依存物と試験素材の別条件。 |

## SF映画とVFX

| ID | 資料と発行元 | 言語 | 確認した内容 |
| --- | --- | --- | --- |
| X01 | [Avengers Endgame production case](https://www.ilm.com/vfx/avengers-endgame/) — Industrial Light & Magic | en | Anymaと俳優の演技を用いるデジタルキャラクター制作。 |
| X02 | [Avengers Endgame production case](https://www.framestore.com/work/avengers-endgame?language=en) — Framestore | en | 衣装置換、デジタルダブル、量子効果、照明と合成の連携。 |
| X03 | [Movie Render Pipeline](https://dev.epicgames.com/documentation/en-us/unreal-engine/movie-render-pipeline-in-unreal-engine) — Epic Games | en | Unrealのオフライン連番・動画出力とMRQ/MRG。 |
| X04 | [시네마틱 렌더 세팅 및 포맷](https://dev.epicgames.com/documentation/ko-kr/unreal-engine/cinematic-render-settings-and-formats-in-unreal-engine) — Epic Games | ko, en | 韓国語本文と一部英語表。出力、サンプル、シャッター、OCIO等の設定。 |
| X05 | [Introduction to Pyro](https://www.sidefx.com/docs/houdini/pyro/intro.html) — SideFX | en | 煙や炎のボリューム、ソース、ソルバー、キャッシュ、描画。 |
| X06 | [DaVinci Resolve Fusion](https://www.blackmagicdesign.com/products/davinciresolve/fusion) — Blackmagic Design | en | ノード合成、追跡、マスク、キー、粒子。機能は使用する版で照合する。 |

## PC内のLLMと音声編集

| ID | 資料と発行元 | 言語 | 確認した内容 |
| --- | --- | --- | --- |
| L01 | [Ollama API introduction](https://docs.ollama.com/api/introduction) — Ollama | en | ローカルとクラウドの基点を区別する。 |
| L02 | [LM Studio compatibility endpoints](https://lmstudio.ai/docs/developer/openai-compat) — LM Studio | en | ローカル会話モデルAPIの基点とモデル一覧。 |
| L03 | [FFmpeg filters documentation](https://ffmpeg.org/ffmpeg-filters.html) — FFmpeg | en | amixとloudnormによる音のミックス・正規化。 |

## 独自ライセンスの本文

| ID | 資料と発行元 | 言語 | 確認した内容 |
| --- | --- | --- | --- |
| R01 | [Tencent Hunyuan Community License Agreement](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/LICENSE) — Tencent | en | EU、英国、韓国を除くTerritory等の独自条件。 |
| R02 | [LTX-2.x Community License Agreement](https://github.com/Lightricks/LTX-2/blob/main/LICENSE-2_x) — Lightricks | en | 売上規模に応じる利用条件等。アプリのApache表記とは別。 |

## 利用条件を比較するときの要点

| 対象 | 資料で確認した区分 | 制作前に確認すること |
| --- | --- | --- |
| Wan2.2 | 公式のApache 2.0表示 | 採用する重みや追加LoRAが同じ条件か |
| HunyuanVideo 1.5 | Tencent Hunyuan Community License | TerritoryからEU、英国、韓国を除く等の独自条件。配布や提供形態も本文で確認する |
| LTX DesktopとLTX重み | アプリのApache表記と、重みのLTX-2.x Community Licenseは別 | 重みには売上規模等の条件がある。アプリのライセンスだけで判断しない |
| Qwen3-TTS CustomVoice | 公式モデルカードのApache 2.0表示 | 使用するモデル系列と参照音声の条件 |
| Style-Bert-VITS2 | コードのAGPLと、声モデル別条件 | 話者モデル、音源、必要なクレジット |
| MMAudioとAudioCraftの配布重み | CC BY-NC 4.0 | コードのMITから商用利用可能とは推定しない |
| Stable Audio Open | stable-audio-community | 適用される契約と商用条件 |
| MuseTalk | コードとモデルの説明、依存モデルと試験素材の別条件 | 同梱のテスト映像と自分の素材を区別する |

出典は上表のV01、V07、A02、A05〜A06、A08〜A11、R01〜R02。これは利用条件を読むための整理であり、個別作品の権利処理が完了したことを示すものではない。配布サイトのモデルカード、重みの条件、使用する声や入力素材を作品単位で記録する。

## 再利用のための記録

資料の説明を要約して保存しており、原文の全文や第三者の動画・音声は複製していない。モデルの速度や品質は公表環境と実機を分けて評価する。次の実験では、使用したrevisionやハッシュ、実行系、失敗も含む結果を [生成記録テンプレート](templates/generation_record.example.json) に記録する。
