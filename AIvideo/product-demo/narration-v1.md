# RocketWright 仮v1：AIナレーション比較と差し替え

2026年11月7日（JST）。同じ日本語の原稿で4テイクを生成し、読み戻しと尺を比較した。仮採用はQwen3-TTSの**明瞭な技術ドキュメンタリー**案。SFの映像に合わせつつ、専門用語・数字を優先した。自動比較での選択であり、耳での試聴や自然さの点数付けは行っていない。

| 比較 | 合成方式・声の方向 | 元の実尺 | ASRの正規化後の文字差率 | 推定F0中央値 |
| --- | --- | ---: | ---: | ---: |
| A | AivisSpeech・阿井田 茂 / Calm | 15.79秒 | 18.1% | 138.5 Hz |
| B | AivisSpeech・阿井田 茂 / ノーマル | 15.77秒 | 15.7% | 145.9 Hz |
| C | Qwen3-TTS VoiceDesign・重厚なSFドキュメンタリー | 23.20秒 | 6.0% | 125.6 Hz |
| D | Qwen3-TTS VoiceDesign・明瞭な技術解説 | 19.92秒 | 3.6% | 147.6 Hz |

[比較原稿と設定](narration-candidates.json)、[自動評価の原記録](narration-comparison.json)。音声認識は同じWhisper smallをCPU・int8・日本語指定で使用した。F0はpYINの推定値。文字差率には同音異字や認識器自身の誤りが入るため、発音品質や自然さそのものの順位にはしない。

4テイクとも「約18.9 m」と「30 m」は認識されたが、「未達」は別表記に認識された。動画の表示は維持し、読み上げを「目標には届いていません」に変更した。Dの冒頭6.75秒を、別の実在人物の録音を使わずに固定声の参照として採用。冒頭の二文と、次の文に入る前の無音を使った。[Qwen公式の設計音声を再利用する手順](https://github.com/QwenLM/Qwen3-TTS)。

## 成果物

書き出し先は `output/media/product-demo/generated/preview-v1/`。[試写素材](../../assets/product-demo/previews/v1/README.md)から共有用のMP4、SRT、比較用MP3を取得できる。

- `rocketwright-preview-v1-narrated.mp4`：新しいナレーションを載せた2分55秒の動画。
- `narration-comparison/`：A〜Dの比較用MP3と音量計測。原音のWAVは `output/media/product-demo/audio/narration-trials/` に保存。
- `rocketwright-preview-v1-narrated.narration.wav`：ナレーション単体。
- `rocketwright-preview-v1-narrated.mix.wav`：ナレーションとBGM。
- `rocketwright-preview-v1-narrated.ja.srt`：音声の立ち上がりと終わりの推定に合わせた外部字幕。焼き込み字幕と各カットの境界は元のv1のまま。
- `rocketwright-preview-v1-narrated.verification.json`：動画ストリームの一致、尺、音量、採用テイクの範囲とハッシュ。

[固定声と読み上げの設定](narration-v1-voice.json) で23カットを生成。字幕用と発音用の文を分け、「階層型」「適応型」「概算高度」を含む3カットを別テイクで更新した。読み戻しでは「適応型」「おおよその高度」「目標には届いていません」「約18.9 m」を確認。「階層型」は「改装型」と同音の表記に認識されたため、音声認識だけでアクセントは判定していない。BGMは元の和音構成を使い、声の前後で滑らかに音量を下げた。

元の動画は残して別ファイルを書き出した。ビデオストリームのハッシュが一致したため、2:33–2:38の印刷実写も同一。解析値、Gemmaによる保存記録、Claude API移行予定の表示を維持している。出力した1080p・30fpsのMP4はFFmpegで全編デコードでき、AACの音量は −16.38 LUFS、最大トゥルーピークは −1.40 dBTPだった。[検証記録](narration-v1-verification.json)。

## 実行環境と利用条件

- [Qwen3-TTS VoiceDesign](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign) と [Base](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-Base) は取得したモデルカードでApache-2.0を確認した。ダウンロード済みの重みをローカルで使用。参照は今回生成した声のみ。
- 比較用の [AivisSpeech Engine 1.2.0](https://github.com/Aivis-Project/AivisSpeech-Engine/releases/tag/1.2.0) はCPU実行。[阿井田 茂](https://hub.aivis-project.com/aivm-models/47e53151-a378-46f3-abee-ce13aa07feb1) のAIVMX 1.0.0は公式メタデータで [ACML 1.0](https://github.com/Aivis-Project/ACML/blob/master/ACML-1.0.md)。制作者・CVは古山キリヲ。比較用音声に使用した。
- 音声合成・認識ともローカルで、課金API、音声の外部送信、ロゴや宣伝音の挿入は行っていない。Qwenの使用コードに透かしを加える処理は見つからなかった。未知の不可聴識別情報を検出する検査は行っていない。
- 音声専用のPython 3.11環境に `qwen-tts 0.1.1`、`transformers 4.57.3`、`faster-whisper 1.2.1` を配置し、既存のCUDA版PyTorchを参照した。既存のComfyUI環境の依存パッケージへ追加インストールしていない。RTX 4090、bfloat16、SDPAで合成した。今回の経路ではFlashAttentionやSoXを追加せず動作した。

## 再生成する場合

比較テイクを再生成して参照を選び直す場合は、そのWAVを試聴・確認し、固定声設定に新しい参照のパス・ハッシュ・読んだ文・範囲を記録する。モデル版・設定・GPU等が変われば同じシードでも波形一致を保証しない。

```powershell
output/narration-runtime/qwen-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/synthesize_narration.py --engine qwen-design --model output/narration-runtime/models/qwen-design --out output/media/product-demo/audio/narration-trials/qwen
output/narration-runtime/qwen-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/synthesize_fixed_narration.py --model output/narration-runtime/models/qwen-base --out output/media/product-demo/audio/narration-trials/adopted
output/media-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/replace_preview_narration.py --takes output/media/product-demo/audio/narration-trials/adopted
```

上記は現在の設定で全カットを再生成する手順。今回の実ファイルでは、`--shot 8 --shot 9 --shot 15`（0始まり）の再生成分を初回テイクに合わせ、`final-takes/` にまとめてから差し替えた。音声は元の映像の各カットに収まるよう調整する。収まらない場合は処理を止めるため、末尾の語を切って合わせない。読み戻しは [review_narration.py](tools/review_narration.py)。最終的な声の好み、アクセント、BGMとの聴こえ方は試聴で確認する。
