---
name: 3d-material-nylon
description: "PA6/PA12/PA11や共重合ナイロン等を製品別に選び、吸湿・乾燥・給材・反り・寸法と層間強度を評価する。繊維入りPAは複合材スキルを併用する。"
---

# PA・ナイロン

製品・実機・根拠の確認は[材料条件](../3d-print-materials/references/material-contract.md)を使う。今回の用途と症状に必要な確認だけを選び、設定の差分・実測・未検証点を記録する。

PAという一語で設定しない。PA6/PA12/PA11・共重合・充填材・熱処理の要否をTDSとプロファイルで確認する。材料を変えたときはナイロン同士でも同等とみなさない。

## 吸湿と熱環境

密封保管と乾燥履歴、印刷中の防湿給材を確認する。乾燥剤を入れた保管箱だけで既に湿った材料が乾くと判断しない。乾燥温度/時間は材料とスプール・機器の両方の指定を照合する。

泡・荒れ・糸引き・層間の弱さは、吸湿のほか押出不足・温度・冷却も分ける。乾いた同製品との対照で評価し、仕上がりだけから乾燥完了を断定しない。

製品に必要なベッド/庫内と、PA向けプレート・接着剤を確認する。ナイロンを滑面PEIで一般的に扱えると仮定しない。広い形状は小片より反りやすいため、原寸の角と全高も確認する。

## 寸法と強度

試験時の乾燥状態と、用途環境に置いた後の寸法・剛性を区別する。吸湿で質量や寸法が変わる可能性を嵌合へ織り込む。PA-CF/GFは[複合材](../3d-material-fiber-filled/SKILL.md)も読み、ノズル摩耗と層間の性能を別に確認する。

根拠：[Prusa PA](https://help.prusa3d.com/article/polyamide-nylon_167188)、[Bambu PA-CFの不良対策](https://wiki.bambulab.com/en/knowledge-sharing/pa-cf-printing-tips)、[Prusa乾燥とスプール](https://help.prusa3d.com/article/drying-filament_332086)。
