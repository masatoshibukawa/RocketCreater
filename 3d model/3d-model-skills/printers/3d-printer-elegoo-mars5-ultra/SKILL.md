---
name: 3d-printer-elegoo-mars5-ultra
description: "Mars 5 Ultraのティルト剥離、自動レベリング、露光・支持とCHITUBOX接続を確認する。Mars5や他機種の動作・露光値をコピーしない。"
---

# ELEGOO Mars 5 Ultra

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/resin-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- Mars 5とUltraを区別する。Ultraのティルト剥離に従来の単純Zリフト設定を移植しない。造形速度の広告値を露光・剥離の設定値にしない。
- 自動レベリングがあっても、プレート固定、タンクの硬化片、膜、レジン・温度と露光を確認する。支持だけ残った場合は通常露光と接点・断面変化も見る。
- 公式のmanual levelingは故障診断用の特殊手順である。そこで調整時間確保のために延長する底露光60/90秒を、通常の印刷レシピへ転記しない。
- 同じレジン・層高・温度で小さな露光／支持試験を行う。空洞は剥離中の吸盤と排液・洗浄まで確認する。

## 最小限の比較試行

適合レジンの小試験と、問題部分の断面・接点を保った試行を分ける。レベリング、底層接着、支持から本体への移行を別々に判定する。

## 接続

Wi-Fi接続後、同一LANのCHITUBOX／対応ChituManagerで追加する。スライサーと管理モジュールのOS対応を別確認し、使えなければ対応USB媒体へ書き出す。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [Mars5系の機種差](https://us.elegoo.com/pages/elegoo-mars-5-series)
- [特殊な手動調整](https://wiki.elegoo.com/en/mars/mars-5-u-manual-leveling-tutorial)
- [LAN送信手順](https://wiki.elegoo.com/en/lcd-slicing-software/elegoo-satellite-chitubox-how-to-print-via-lan)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
