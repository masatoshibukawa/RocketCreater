---
name: 3d-printer-prusa-core-one
description: "元のPrusa CORE Oneの筐体・ノズル・ロードセル・ネットワーク条件を確認する。CORE One+、Gen2、L、INDXの機能を混同しない。"
---

# Prusa CORE One

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- 機体が元のCORE Oneかアップグレード版かを確認し、ノズル、プロファイル、ファームを一致させる。製品名が似たGen2/L/INDXの機能を前提にしない。
- ノズル清掃とロードセルの校正を確認する。高温筐体で低温材料を使う場合はheat creepの候補も調べる。
- 材料に応じて筐体温度・ファン・上部ベントを管理する。元CORE Oneの手動ベントを後発機の自動制御と同一に扱わない。
- CoreXYだから高い薄い部品が倒れないとは考えず、初層の接続と上部の接触を確認する。HFの有無は実機とプロファイルで照合する。

## 最小限の比較試行

材料用プロファイルと筐体条件を固定し、初層から短い上部層まで1個を観察する。反りと熱だまりのどちらがあるかで次の変更を選ぶ。

## 接続

有線Ethernetまたは対応Wi-FiでPrusaLinkを使う。外部からはPrusa Connect。初回設定やジョブ保存でUSB媒体が必要な条件は公式ガイドで照合する。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [CORE One初期設定](https://help.prusa3d.com/wp-content/uploads/generated/prusa-core-one-assembled_2243_en_2025-06-13.pdf)
- [筐体温度とベント](https://help.prusa3d.com/article/chamber-temperature-is-critical-31261-core-one-35261-core-one-l-36261-core-one-indx-17261-xl_861880?product=xl)
- [PrusaLink設定](https://help.prusa3d.com/wp-content/uploads/generated/prusa-connect-prusalink_1636_guide_413293_en_2026-05-13.pdf)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
