---
name: 3d-material-pet
description: "PET系とPET CFをPETGと区別し、製品・機種/コア・吸湿・反り・熱処理前後の寸法と強度を確認する。繊維入りでは摩耗条件も併用する。"
---

# PET・PET CF

[材料条件](../3d-print-materials/references/material-contract.md)を使い、正確な商品・実機と完成状態を記録する。必要な項目だけ読み、一般の材料名から温度や物性を固定しない。

PETとPETG、PET CFや他の改質品を同一材料プロファイルにまとめない。未充填PETならその製品のTDS/プロファイルを取得し、CF製品向けの数値を移さない。CF品は[繊維入り条件](../3d-material-fiber-filled/SKILL.md)も読む。

## UltiMaker PET CFの具体例

確認日2026-11-07の[公式手順](https://support.ultimaker.com/s/article/pet-cf-instructions)では、S5のUltiMaker PET CF（2.85mm）はCC0.4またはCC0.6。既存のTough PLA用AA0.4を流用せず、当該製品・コアのCura/FW・給材/乾燥条件へ照合する。PET CFが対応することからPPS CFもS5対応と推定しない。

Factor 4はCC0.4/0.6またはHT0.6、Factor 4+はCC+0.6優先で他の掲載コアは実験扱い等、世代差がある。コア径だけでなく材料・本体・プロファイルを一組で確認する。

支持は同製品向けのPVA/Breakaway等の対応と支持側コア・乾燥・界面を照合する。複合材用の本体コアを、PVAへそのまま使わない。

## 乾燥・熱処理・試作

吸湿/給材抵抗、ベッドと表面、反り、短い層の冷却を切り分ける。乾燥機とスプールの許容範囲を守り、保管箱だけで乾燥完了としない。

アニール等を行う製品は、指定の工程と支持/拘束、処理前後の寸法・反り・層方向を記録する。熱処理後の資料値を未処理部品へ使わず、薄いフィン根元と嵌合を原寸で確認する。部品の質量・重心も[材料置き換え](../3d-material-substitution/SKILL.md)で再評価する。
