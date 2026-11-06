---
name: 3d-printer-ultimaker-3
description: "Ultimaker 3のAA/BBコア、active leveling、CuraとLAN接続を確認する。S5やExtendedの設定をそのまま移さない。"
---

# Ultimaker 3

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- Ultimaker 3と3 Extendedを先に区別する。実際の造形域と左右コア・材料をCuraへ反映し、S5のプロファイルを借用しない。2.85 mm系であることも照合する。
- ガラスと両ノズル先端を清掃してactive levelingを実施する。補償範囲外なら公式のmanual levelingへ戻る。二材ではコア高さ・XYの校正も別に確認する。
- AA/BBと材料の互換表を使う。溶解支持を使わない単材試験から始められる場合、二材の切替・パージ・支持材管理を不要に増やさない。
- 古い製品向けの最終対応ファームとCuraの互換性を確認する。新型Sシリーズの機能が追加されたと仮定しない。

## 最小限の比較試行

既知良好な単材プロファイルで接地の小さい部品を1個確認する。初層良好でも全高の接触・揺れを観察し、支持を増やす場合は二材設定も再検査する。

## 接続

Curaの対応ネットワーク追加からLAN内の実機を選ぶ。見つからなければ本体のIPと接続状態を確認する。代替はUSBメモリー。PCをUSBケーブルでつなぐだけの経路を推測しない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [Ultimaker 3公式マニュアル](https://um-support-files.ultimaker.com/manuals/user-manual/UM3/Ultimaker%203%20-%20User%20manual%20EN%20v1.4.pdf)
- [ネットワーク診断](https://support.ultimaker.com/s/article/1667337573408)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
