---
name: 3d-metal-nickel-alloy
description: "IN625/IN718等の金属AM用ニッケル合金を熱・腐食・荷重から選定する。機種・供給形態・熱処理状態と、割れ/変形・加工・検査を評価する。"
---

# ニッケル合金・IN625/IN718等

[方式索引](../../industrial/3d-carbon-metal-printing/SKILL.md)で供給形態と造形方式を選び、[施設・品質の記録](../../../11_カーボンと金属/facility-and-quality.md)へ製品・機種・完成状態を残す。必要な項目だけ読み、実物の性能が未検証なら未検証と返す。

IN625と析出硬化型IN718等を同じ高温金属として設定しない。要求する温度・応力・保持時間、熱サイクル、腐食環境、必要な寿命から合金と完成工程を選ぶ。

LPBF、金属FFF、DEDで供給材と組織・熱履歴が異なる。完成状態（造形/焼結直後、応力除去、溶体化/時効、HIP、加工後）を付けて資料を比較する。メーカーの最高温度表現を任意の荷重での連続使用温度へ変換しない。

残留応力、割れ、支持/切離しと加工代、内面の残粉や仕上げ可能性を確認する。高温用途は室温引張値だけで合格にせず、必要な疲労・クリープ/腐食などの判定条件を用途に合わせる。

根拠：[EOS IN718の材料/後処理資料](https://www.eos.info/metal-solutions/metal-materials/data-sheets/mds-eos-nickelalloy-in718)、[金属FFFの製品別対応](https://support.markforged.com/portal/s/article/Material-Compatibility-Matrix)、[DED材料の成熟度](https://www.waam3d.com/materials)。InconelがMetal X対応でもFX10対応へ広げない。
