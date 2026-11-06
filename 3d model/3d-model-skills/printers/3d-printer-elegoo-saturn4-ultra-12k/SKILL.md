---
name: 3d-printer-elegoo-saturn4-ultra-12k
description: "元のSaturn 4 Ultra 12Kのティルト剥離、レベリング、レジンとLAN送信を確認する。16K世代の機能・露光・加温を前提にしない。"
---

# ELEGOO Saturn 4 Ultra 12K

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/resin-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- ラベルとプロファイルで元の12K版を確認する。16K版の加温等の機能や設定を持つと仮定しない。
- ティルト式タンクの剥離を前提に、膜・異物・支持と急な大断面を確認する。露光、底層、速度モードを別々に扱う。
- 自動レベリングでもプレートの固定と実物の底層を確認する。公式の調整用60/90秒は調整時間のための条件で、通常露光の推奨ではない。
- 大きい部品は吸盤状の空洞と排液を層画像で調べる。FDMの広いブリムや速度35 mm/sをレジンの解決策へ移さない。

## 最小限の比較試行

同じレジン・温度・層高の小試験後、支持接点と大断面が現れる部分を確認する。支持だけ残るか底層から剥がれるかを記録する。

## 接続

公式の12K版向けWi-Fi／Network Sending手順を使い、ChituManagerを別途確認する。送信先の本体型番・解像度・スライス形式を照合する。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [12K版の機構](https://us.elegoo.com/products/saturn-4-ultra-12k-10inch-monochrome-lcd-resin-3d-printer)
- [特殊なレベリング調整](https://wiki.elegoo.com/saturn/saturn-4-ultra-how-to-improve-leveling-results)
- [12K版LAN接続](https://wiki.elegoo.com/saturn/saturn-4-ultra-how-to-enable-remote-printing-via-network-connection)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
