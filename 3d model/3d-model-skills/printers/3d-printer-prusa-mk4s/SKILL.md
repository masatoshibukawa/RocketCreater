---
name: 3d-printer-prusa-mk4s
description: "Prusa MK4Sのロードセル初層、高流量ノズルとプロファイル、可動ベッド、PrusaLink/Connect接続を確認する。MK4やCORE Oneと区別する。"
---

# Prusa MK4S

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- MK4S用プロファイルと実際のHF／標準ノズルを一致させる。MMU等の変更があればその構成も合わせる。HF用設定を標準ノズルへ流用しない。
- ロードセルによる初層校正の前にノズルの付着物とシートの汚れを確認する。旧機種のLive Z数値をコピーせず、該当機の校正・エラー手順を使う。
- ベッド移動に伴う高い薄い部品の揺れを確認する。入力整形や高速プロファイルは接地・冷却を置き換えない。
- シート種類と材料に合った表面処理を選ぶ。高流量ノズルでも材料の流量上限と短層の冷却が残る。

## 最小限の比較試行

既知良好なプロファイルで初層を確認した後、実寸に近い高い部品を1個比較する。方向または加速度の変更を分離して観察する。

## 接続

PrusaLinkはローカルIP、Prusa Connectはクラウド。PrusaSlicerの物理プリンター／送信先を設定する。USBメモリーの役割とUSBケーブルの役割を区別する。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [MK4Sアップグレード後の確認](https://help.prusa3d.com/wp-content/uploads/generated/original-prusa-mk4-mk3-9-to-mk4s-mk3-9s-upgrade_2186_guide_754328_en_2026-05-06.pdf)
- [ノズルとHFプロファイル](https://help.prusa3d.com/article/clogged-nozzle-core-one-core-one-l-xl-mk4-s-mk3-9-s_411823?product=xl)
- [PrusaLink設定](https://help.prusa3d.com/wp-content/uploads/generated/prusa-connect-prusalink_1636_guide_413293_en_2026-05-13.pdf)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
