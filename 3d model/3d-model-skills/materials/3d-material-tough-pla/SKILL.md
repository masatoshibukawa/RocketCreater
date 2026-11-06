---
name: 3d-material-tough-pla
description: "Tough PLA、PLA+等の改質PLAを製品別に扱う。通常PLAとの置き換え、実際のS5/Tough PLA Gray/AA0.4の試行、靱性と耐熱の混同を確認する。"
---

# Tough PLA・PLA+

製品・実機・根拠の確認は[材料条件](../3d-print-materials/references/material-contract.md)を使う。今回の用途と症状に必要な確認だけを選び、設定の差分・実測・未検証点を記録する。

Tough PLA/PLA+は共通の組成や強度の規格ではない。メーカー、正確な製品・径・色、TDSの試験条件を確認し、普通のPLA・ABSと同一視しない。靱性向上が耐熱向上を意味するとは限らない。

## S5での既存条件を使う場合

既存の試行はUltiMaker S5、UltiMaker Tough PLA Gray、AA0.4、2.85mm。現行のCura/FWに対応する同製品プロファイルを起点にする。色が未認識のときは[公式のGray等の認識手順](https://support.ultimaker.com/s/article/1872100986221)と現在の版を確認し、別ポリマーの種類に偽装して送信しない。

フィンは初層が付いても終盤で倒れた記録がある。[既存の実機対策](../../../09_実機トラブルと機種別対策/fdm-reliability.md)のブリム20–35mm・押出指令35mm/s以下は、その部品の未検証の再試行条件。全Tough PLAの速度や接地の既定値にしない。

## 製品を選び直す場合

- UltiMaker Tough PLAの[TDS](https://um-support-files.ultimaker.com/materials/2.85mm/tds/TOUGH-PLA/UM220509-Tough-PLA-TDS-RB-v2.10.pdf)は積層方向別の値と試験条件を持つ。熱・変形・質量の仮定もこの製品へ照合する。XYの靱性だけで薄いZ方向接続を承認しない。
- 支持が必要なら本体をAA、UltiMaker PVAをBBにする等、[支持材の対応](../3d-material-pairing/SKILL.md)を別に確認する。Breakawayも製品とコアの条件を照合する。
- 別ブランドPLA+へ替えるときは[材料置き換え](../3d-material-substitution/SKILL.md)として、嵌合・根元・支持除去の小試作から再確認する。

返す判断は、採用する製品、機械構成、剛性/靱性/熱の要件、原寸試験の結果と残る条件。[公式製品ページ](https://ultimaker.com/materials/s-series-tough-pla/)の訴求を今回のフィンの実機試験に置き換えない。
