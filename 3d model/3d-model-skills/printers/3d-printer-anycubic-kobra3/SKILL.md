---
name: 3d-printer-anycubic-kobra3
description: "元のAnycubic Kobra 3のレベリング、材料供給、Slicer NextとLAN接続を確認する。V2/MaxやS1の設定を混同しない。"
---

# Anycubic Kobra 3

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- Kobra 3の型番・世代と実ノズルを先に確認する。シリーズ共通ページ内のV2向け説明は対応箇所を分ける。
- ノズル・プレート・供給経路と、共振補償・LeviQの機種用手順を確認する。元から不良な初層を、印刷中にZ値を反復変更して追いかけない。
- 接着不良には公式が清掃、ブリム、レベリング等を挙げる。温度増加の記載も材料上限とプレート条件を照合し、全材料に一定量を足さない。
- ACE Proの有無と乾燥・多色の構成を記録する。単材の比較試行に多色切替やパージを不要に増やさない。

## 最小限の比較試行

材料、ベッド温度、同じ接触域を保ち、初層の均一性と全高の1個を確認する。高速部の欠けと供給抵抗も区別する。

## 接続

対応ファームのLAN ModeはAnycubic Slicer Nextを使う。元のAnycubic Slicerと区別し、LAN Modeでクラウド・アプリの遠隔機能が切れる影響を確認する。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [元のKobra 3入口](https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3)
- [接着不良](https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/model-non-stick-hotbed)
- [Kobra3のLAN](https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/kobra-3-series-lan-connection-guide)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
