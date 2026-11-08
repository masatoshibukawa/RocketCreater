---
name: 3d-printer-formlabs-form4
description: "Formlabs Form4の材料・タンク・PreForm、向き・支持・カップとPC接続を確認する。Form3等の設定を流用しない。"
---

# Formlabs Form 4

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/resin-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- Form4用の樹脂・タンク・ビルドプラットフォームとPreFormの対応を確認する。Form3の露光・剥離条件や、他社レジン機の秒数を移さない。
- PreFormの自動配置・支持後も、カップ、急な断面の合流、重要面を確認する。必要な排液孔と、後処理可能な空洞を設計する。
- 標準とFlexのプラットフォームでは該当する準備・取り外し手順を使う。膜の曇り、傷、硬化物、ミキサーと材料の管理を確認する。
- 材料別に洗浄・乾燥・二次硬化を揃えて寸法を評価する。自動で完了したジョブと実物の合格を分ける。

## 最小限の比較試行

適合材料とPreForm設定で、問題の接点・カップ・断面変化を保つ部分を比較する。底層、支持から本体、洗浄後・硬化後を別記録にする。

## 接続

PreFormは対応Windows/macOSで、Form4へUSBケーブル、Ethernet、Wi-Fiを使える。Dashboardのクラウド接続とは別経路。LinuxネイティブやWindows ARMを対応済みと仮定しない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [Form4向け設計・向き](https://formlabs.com/support/Best-practices-for-printing-with-Form-4-generation-printers?language=en_US)
- [タンクの損耗](https://formlabs.com/support/Resin-tank-damage-and-wear-Form-4-generation/)
- [接続方式](https://formlabs.com/support/Connectivity-and-Security/)
- [PC要件](https://formlabs.com/support/What-are-the-system-requirements-to-run-PreForm)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
