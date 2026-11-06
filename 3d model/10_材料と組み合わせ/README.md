# 材料と組み合わせ

追加調査日：2026-11-07。材料系の名前と個々の製品を分け、公式の材料資料・対応表を英語、日本語、中国語、ドイツ語で照合した。本文は日本語。翻訳ごとに内容・更新状況が異なる場合があり、数字を平均して使わない。

入口は[材料索引スキル](../3d-model-skills/materials/3d-print-materials/SKILL.md)。条件は[材料記録の基準](../3d-model-skills/materials/3d-print-materials/references/material-contract.md)で揃える。

| 判断したいこと | スキル・資料 |
| --- | --- |
| この実機で使えるか | [機種と材料の適合スキル](../3d-model-skills/materials/3d-material-machine-match/SKILL.md) |
| 複数材料・支持材・液の混合 | [組み合わせスキル](../3d-model-skills/materials/3d-material-pairing/SKILL.md)、[条件付き適合表](compatibility.md) |
| 別の材料へ変える | [材料置き換えスキル](../3d-model-skills/materials/3d-material-substitution/SKILL.md) |
| 条件を残す | [材料記録JSON](material-record.example.json)、[出典CSV](sources.csv) |

ここでの対応表は代表的な判断例で、全ブランドの全組み合わせを実験した結果ではない。公式対応・条件付き試作・非対応・不明を分け、製品・機種・版を付けて使う。数値の既定値を一律に配布する資料ではない。

追加調査の[出典CSV](sources.csv)は34件の公式URLについて言語・確認範囲・参照先を記録する。資料内で世代や説明が食い違う例も残した。新しい材料・混合物の実機試験は行っていない。

## 材料別スキル

16系統のスキルを用意した。繊維入りは基材スキルへ重ね、水洗い高靱性レジン等は必要な2種類を併用する。PLA+やABS-likeは標準化された組成の名称として扱わない。

| 材料 | スキル |
| --- | --- |
| PLA | [3d-material-pla](../3d-model-skills/materials/3d-material-pla/SKILL.md) |
| Tough PLA・PLA+ | [3d-material-tough-pla](../3d-model-skills/materials/3d-material-tough-pla/SKILL.md) |
| PETG | [3d-material-petg](../3d-model-skills/materials/3d-material-petg/SKILL.md) |
| ABS | [3d-material-abs](../3d-model-skills/materials/3d-material-abs/SKILL.md) |
| ASA | [3d-material-asa](../3d-model-skills/materials/3d-material-asa/SKILL.md) |
| TPU・TPEの柔軟材 | [3d-material-tpu](../3d-model-skills/materials/3d-material-tpu/SKILL.md) |
| PA・ナイロン | [3d-material-nylon](../3d-model-skills/materials/3d-material-nylon/SKILL.md) |
| PC・PCブレンド | [3d-material-pc](../3d-model-skills/materials/3d-material-pc/SKILL.md) |
| PP | [3d-material-pp](../3d-model-skills/materials/3d-material-pp/SKILL.md) |
| CF・GF等の繊維入り材料 | [3d-material-fiber-filled](../3d-model-skills/materials/3d-material-fiber-filled/SKILL.md) |
| LW-PLA・発泡PLA | [3d-material-foaming-pla](../3d-model-skills/materials/3d-material-foaming-pla/SKILL.md) |
| PVA・BVOHの水溶性支持材 | [3d-material-soluble-support](../3d-model-skills/materials/3d-material-soluble-support/SKILL.md) |
| Breakaway・剥離用支持材 | [3d-material-breakaway-support](../3d-model-skills/materials/3d-material-breakaway-support/SKILL.md) |
| 標準・模型用レジン | [3d-material-standard-resin](../3d-model-skills/materials/3d-material-standard-resin/SKILL.md) |
| 工学用・高靱性・柔軟・耐熱レジン | [3d-material-engineering-resin](../3d-model-skills/materials/3d-material-engineering-resin/SKILL.md) |
| 水洗いレジン | [3d-material-water-wash-resin](../3d-model-skills/materials/3d-material-water-wash-resin/SKILL.md) |
