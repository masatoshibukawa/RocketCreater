---
name: 3d-metal-tool-steel
description: "H13、A2、D2等の金属AM用工具鋼を用途・製品世代と熱処理状態から選ぶ。焼結/造形後の硬度、割れ・反り、加工と検査を評価する。"
---

# 工具鋼・H13/A2/D2等

[方式索引](../../industrial/3d-carbon-metal-printing/SKILL.md)で供給形態と造形方式を選び、[施設・品質の記録](../../../11_カーボンと金属/facility-and-quality.md)へ製品・機種・完成状態を残す。必要な項目だけ読み、実物の性能が未検証なら未検証と返す。

熱間工具向けH13と、他の冷間工具鋼等を一つの材料設定にしない。摩耗、熱サイクル、衝撃、必要な硬度と加工性から候補を選ぶ。

焼結後/as-builtと、焼入れ・焼戻し等の後の物性を分ける。鍛造材との比較表をAM部品の実測値へ置き換えない。熱処理、研削/放電加工・仕上げ代と変形の見込みを出力前に含める。

確認日2026-11-07のMarkforged[対応表](https://support.markforged.com/portal/s/article/Material-Compatibility-Matrix)では、H13 v1はMetal X対応・FX10非対応、H13 v2はMetal XとFX10の両方に対応。D2/A2が同社の一覧にあることだけでFX10へ採用しない。

原寸の重要断面、角・薄肉/厚肉差、造形方向を含む試験で、処理後の寸法・硬度と用途の必要な靱性/寿命を確認する。硬度だけで工具として合格にしない。メーカー指定外の共通熱処理レシピを生成しない。

根拠：[H13 v2の積層・焼結・熱処理別TDS](https://www-objects.markforged.com/craft/home/H13-Tool-Steel-v2-Material-Datasheet.pdf)、[H13製品](https://markforged.com/materials/metals/h13-tool-steel)。
