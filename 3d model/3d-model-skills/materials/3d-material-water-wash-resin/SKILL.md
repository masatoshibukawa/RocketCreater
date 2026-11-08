---
name: 3d-material-water-wash-resin
description: "水洗いレジンの製品世代・洗浄槽・浸漬時間・乾燥・二次硬化・中空部と廃液を扱う。水洗いABS-like等は工学用レジンも併用する。"
---

# 水洗いレジン

製品・実機・根拠の確認は[材料条件](../3d-print-materials/references/material-contract.md)を使う。今回の用途と症状に必要な確認だけを選び、設定の差分・実測・未検証点を記録する。

水洗い可能という特性と、標準/高靱性等の力学特性は別軸。製品名・世代・色を確認し、必要なら[工学用レジン](../3d-material-engineering-resin/SKILL.md)も併用する。水溶性のPVA支持材とも区別する。

## 洗浄と乾燥

メーカー指定の槽・洗浄液・時間で洗い、使用済み水を回収する。水道へ直接流しながら洗わない。低臭/水洗い/環境配慮という販売表現は、未硬化レジンの接触や排水を認める根拠にはならない。SDSと施設・地域の処理方法を使う。

長時間の浸漬による吸水・膨れ・ひびを避けるため、当該製品の洗浄上限と十分な乾燥を確認する。中空部は洗浄水と未硬化液が出入りし、乾燥・必要な内部硬化ができる開口を設計する。表面だけ乾いたことを内部までの合格にしない。

指定の二次硬化後に寸法・割れ・支持除去痕を確認する。露光や硬化不足と、洗浄/吸水による損傷を分けて比較する。

## 世代と説明の差

Anycubic Water-Wash Resin+、2.0、Water-Wash ABS-like等を一製品にまとめない。[旧世代のガイド](https://store.anycubic.com/blogs/3d-printing-guides/user-guide-for-anycubic-water-washable-resin)の浸漬時間や太陽光での硬化説明を、別世代と硬化機の共通設定にしない。[現在の商品ページ](https://store.anycubic.com/products/water-wash-resin)も水洗いの訴求と一般的なアルコール洗浄手順が混在するため、当該製品のTDS/公式プロファイルを優先して不一致を解消する。

別レジンとの液体混合は[複数材料](../3d-material-pairing/SKILL.md)で判断し、混合後も水洗いできると推定しない。廃液は[Formlabsの洗浄廃液の注意](https://formlabs.com/support/Form-Wash-Time-Settings/)も参考に、当該製品SDSへ照合する。硬化・ろ過しただけで排水可能になったとは判断しない。
