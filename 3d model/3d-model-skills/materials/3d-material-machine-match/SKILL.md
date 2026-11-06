---
name: 3d-material-machine-match
description: "3Dプリンターと材料製品の適合を、径・コア/ノズル・温度・囲い・送り装置・プレート・乾燥まで照合する。新材料導入や周辺品交換時に使う。"
---

# 機種・ノズル・プレートと材料の適合


[材料条件](../3d-print-materials/references/material-contract.md)から実構成を確認し、[機種スキル](../../printers/3d-printer-profiles/SKILL.md)と材料スキルを併用する。[適合表](../../../10_材料と組み合わせ/compatibility.md)は判断例として読む。

## 適合の判断

径と供給経路→摩耗とノズル詰まり→必要な熱環境→プレートと離型→プロファイルの順に、今回変わる条件を照合する。どれかが公式非対応なら、その組み合わせを実機用データとして確定しない。不明なら必要な資料・部品確認を列挙する。

- S5の2.85mmと一般的な1.75mmを区別する。AA0.4のTough PLA構成を、そのままPA-CF等へ流用しない。CF/GFでは製品に対応した耐摩耗コア・ノズル、径、給材部品と公式プロファイルを確認する。
- AMS、AMS lite、AMS 2 Pro/HT、外部スプールは別構成。普通のTPU95AはAMS lite非対応として扱う。専用AMS対応製品もAMS lite対応とは限らず、製品別に照合する。機械に入ることと自動切替で送れることは別。
- ABS/ASA/PC/PA系は、ノズルの最大温度だけで採用しない。必要な囲い・庫内条件、ベッド、排気とドラフト、電子部品の許容条件を照合する。開放型機への自作カバー追加を標準対処にしない。
- のりは接着目的と離型目的を分ける。PETG/TPU/PC等で過剰密着する表面に、接地強化だけを狙って押しつぶしを増やさない。清掃剤もプレート製品の指定を使う。
- レジンは機種・材料世代・色の対応表を確認する。汎用の405nmという表示だけで、Form 4を含む各機種で共通に使えると判断しない。

根拠には[UltiMaker Sシリーズ材料](https://support.ultimaker.com/s/article/1667410778895)、[Bambu対応表](https://wiki.bambulab.com/en/general/filament-guide-material-table)、[Formlabsの機種別検証プロファイル](https://formlabs.com/materials/formlabs-resin-print-settings)を使い、最新の製品条件へ読み替える。

## 次に進める条件

「公式対応/条件付き試作/非対応/不明」を項目ごとに記録し、足りない部品・プロファイルと小試作の内容を返す。機械条件を満たした後に、[接地](../../categories/3d-print-bed-stability/SKILL.md)と[速度・流量](../../categories/3d-print-speed-calibration/SKILL.md)を形状に合わせる。未知の材料を使うために温度上限や保護機能を回避しない。
