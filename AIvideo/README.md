# AI video production

Reusable production skills, research notes, source references, and templates for realistic video, SF visual effects, audio generation, and local workflows.

## 日本語の概要

写実的なAI映像、SF映画のVFX、音声・効果音・音楽、ローカル生成について、制作スキルと調査資料を整理しています。

- [動画制作スキルの索引](skills/video-production/SKILL.md) — 入口のスキルと、その下の7カテゴリのスキル
- [フェアリング映像の再現プロジェクト](Test%20project/README.md) — Blenderの3D、カメラ、HUD、音を組み合わせる制作例
- [ローカルAI動画生成](local-runtime/README.md) — ComfyUI＋Wan2.2の分離導入、ロケット画像からの短い動画生成と実測記録
- [2L PET試作v2の設計・上昇予測動画](pet-rocket/README.md) — 原寸STL、連続した水・空気噴射モデル、映像と数値の同期検証
- [写真由来の1080p制作版](pet-rocket/realism/README.md) — HDRI・実写テクスチャ・地上カメラ、映像版と注釈版
- [2026年11月4日の調査結果](research/2026-11-04/README.md)
- [このPCに合う生成方法](research/2026-11-04/04_local_pc.ja.md)
- [実践手順とSF予告編の制作案](research/2026-11-04/05_production_recipes.ja.md)

## Storage

The skill entry point is `skills/video-production/SKILL.md`. It routes to seven nested category skills and loads only the instructions needed for a task. These are repository-local skill sources; creating them does not register them with a runtime. Their relative links reuse the research stored in this directory.

Keep dated research under `research/YYYY-MM-DD/`. Store source links and concise findings with the date checked. Model weights and generated video assets belong in a separate production storage location.
