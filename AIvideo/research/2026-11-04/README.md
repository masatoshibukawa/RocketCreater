# AI video production research November 4 2026

A dated collection of primary sources, Japanese production notes, and planning templates for photorealistic video, SF visual effects, audio generation, and local inference. Research covers sources in Japanese, English, Chinese, Korean, French, Spanish, and German.

## 日本語の概要

このPCのRTX 4090と約64GB級メモリを活かす初回候補は、ComfyUIとWan2.2 5Bです。GUIで音付き動画も扱いたい場合はLTX Desktop、精密なSF映像には実写や3Dと合成を組み合わせる方法を比較します。推奨は[取得したPC仕様](environment.json)と[公式要件の照合](04_local_pc.ja.md)に基づくもので、このPCでの生成実測ではありません。

制作は「基準画像を決める → 短いショットを生成する → 声と効果音を作る → 編集と合成で仕上げる」の順から始めます。会話用LLMには台本やショット表を担当させ、動画モデルとTTSを工程に応じて使います。

## Reading guide

| File | Contents |
| --- | --- |
| [01 Video methods](01_video_methods.ja.md) | 写実映像、I2V、T2V、参照とマスク、ローカルとクラウド、プロンプト例 |
| [02 Audio methods](02_audio_methods.ja.md) | 日本語TTS、声の設計、効果音、音楽、口の同期、音の編集 |
| [03 SF and VFX](03_sf_vfx.ja.md) | アベンジャーズの制作事例、実写と3DとAIの組合せ、光と合成 |
| [04 Local PC](04_local_pc.ja.md) | 実機仕様、VRAM条件、WindowsとLinuxの違い、導入順 |
| [05 Production recipes](05_production_recipes.ja.md) | 最初の一場面、30秒SF予告編、PC内LLMとの連携、比較方法 |
| [06 Multilingual search](06_multilingual_search.ja.md) | 言語ごとの検索語、採用基準、取得できなかった資料 |
| [07 Sources](07_sources.ja.md) | 38件の一次資料と利用条件への入口 |
| [Source registry](sources.json) | URL、発行元、言語、確認日、要点の機械可読データ |
| [Hardware inventory](environment.json) | 個人識別情報を除いた読み取り専用のPC確認結果 |
| [Shot plan template](templates/shot_plan.example.json) | オリジナルSF予告編の6カット構成案 |
| [Generation record template](templates/generation_record.example.json) | モデル、入力、設定、処理時間、VRAM、評価の記録用 |

## Research status

Sources were checked on November 4, 2026. Findings are summaries, not copies of the source documents. Publisher claims, local hardware observations, and proposed production recipes are distinguished in the notes. Localized documentation from the same publisher is not independent validation.

No model weights were downloaded, no production applications were installed, and no video or audio generation benchmark was run. Existing local LLM installations were not identified in the limited locations inspected; custom locations and other Python environments remain unverified. Cloud pricing and access must be checked when choosing a service.

The JSON files in `templates/` are planning and record templates, not executable ComfyUI workflows. Actual ComfyUI workflow JSON should come from the matching official template and be saved with the app and model versions used.
