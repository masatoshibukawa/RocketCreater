---
name: 3d-material-fiber-filled
description: "CF/GF等の繊維充填フィラメントを基材ポリマーに重ねて評価する。ノズル・給材の摩耗、詰まり、熱条件、異方性と層間性能を確認する。"
---

# CF・GF等の繊維入り材料

製品・実機・根拠の確認は[材料条件](../3d-print-materials/references/material-contract.md)を使う。今回の用途と症状に必要な確認だけを選び、設定の差分・実測・未検証点を記録する。

「カーボン」で一つの設定にしない。PLA-CF、PETG-CF、PET-CF、PA-CF、PC-CF、ASA-CF等の基材と充填量を確認し、基材に合う材料スキルも読む。連続繊維の積層と、短繊維入りフィラメントは別の方式。

## 機械を傷めない構成

製品が指定する耐摩耗ノズル/コアと径、ギヤ・チューブ・給材経路を照合する。真鍮AA0.4等の既存設定をそのまま流用しない。0.6mmが推奨される製品はあるが、全製品の必須径にはしない。Bambuの径・高流量ノズル・AMS等もそれぞれの対応表を使う。

フィラメントが硬く脆い場合の折れ、粗い表面による抵抗、詰まりを確認する。耐摩耗化しても基材の乾燥・庫内条件の要件は残る。ノズル材質/径を変えたら、プロファイルと流量・初層を再確認する。

## 性能を決める試験

充填で剛性や寸法安定性が変わっても、衝撃やZ方向の層間が必ず改善するとは限らない。TDSのXY/Z・乾燥/吸湿・熱処理条件を確認し、薄い根元や荷重方向を含む試験で判断する。

切削/研磨等が必要なら材料SDSと設備に合う粉じん対策を選ぶ。見た目だけのCF添加を構造強化と誤認しない。

根拠：[Prusa繊維充填材](https://help.prusa3d.com/article/composite-materials-filled-with-carbon-kevlar-or-glass_167387)、[Bambu対応表](https://wiki.bambulab.com/en/general/filament-guide-material-table)、[ASA-CF/PAHT-CFの製品別条件](https://wiki.bambulab.com/en/filament/asacf_pahtcf)。
