# 公開スキルの比較と検証の改善

確認日：2026-11-07。公開スキルの分析を、既存の制作・機種・材料スキルへ追加する。外部パッケージやそのコードは導入せず、採用する考え方と適用しない条件を分けた。

| 必要な判断 | 入口 |
| --- | --- |
| 修正・書出し後の寸法、姿勢、形状差分 | [出力検証スキル](../3d-model-skills/quality/3d-model-export-verification/SKILL.md) |
| 設定と実際の接地・支持・速度指令の照合 | [実経路確認スキル](../3d-model-skills/quality/3d-print-toolpath-review/SKILL.md) |
| 過去の失敗をどの条件へ適用するか | [試行・改善スキル](../3d-model-skills/quality/3d-print-outcome-learning/SKILL.md) |
| 採用理由と公開実装の限界 | [比較記録](adoption.md)、[出典台帳](sources.csv) |
| その案件の検査を保存する | [検証記録](verification-record.example.json)、[試行と知見](outcome-lesson.example.json) |

今回の追加は既存スキルの原本内に保存する。実機での新たな印刷・接続・耐久試験を実施したものではない。
