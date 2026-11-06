---
name: 3d-material-petg
description: "PETGの糸引き、ブリッジ、プレート過剰密着、寸法と支持除去を扱う。PETやPET-CF、PETG高速用等の製品差にも注意して選定・印刷条件を整える。"
---

# PETG

製品・実機・根拠の確認は[材料条件](../3d-print-materials/references/material-contract.md)を使う。今回の用途と症状に必要な確認だけを選び、設定の差分・実測・未検証点を記録する。

PETGとボトル用PET、PET-CF、改質コポリエステルを区別する。既存PLAからの変更なら、剛性・変形と嵌合も[置き換え](../3d-material-substitution/SKILL.md)で再評価する。

## 症状から進める

- プレートから取れない：表面の製品名を確認する。Prusaの滑面PEIでは損傷に注意し、指定された別シート/離型層を使う。この指示をS5ガラスや他社PEIへそのまま移さない。
- 糸引き・小粒：吸湿、ノズルの付着、熱とリトラクション、移動を分ける。長い引戻しだけを増やさず、乾いた材料の対照と当該機種のプロファイルから比較する。
- 橋が垂れる/支持が溶着：橋の跨度・流量・ファンと支持界面を確認する。表面を良くする冷却と層の強度の両方を試験する。支持を剥がす時の根元欠けも記録する。
- ノズルに塊が付く：過剰な押出、表面の引きずり、付着した塊と冷却を確認し、接地が弱い高い部品への衝突も追う。

原寸の接地片・橋/界面・嵌合片を、実際の用途に必要なものだけ試す。外観だけから耐水・圧力保持・長期変形の合格を決めない。

根拠：[Prusa PETG英語版](https://help.prusa3d.com/article/petg_2059)、[日本語版](https://help.prusa3d.com/ja/article/petg_2059)、[Bambuのプレート・のり対応](https://wiki.bambulab.com/en/general/filament-guide-material-table)。
