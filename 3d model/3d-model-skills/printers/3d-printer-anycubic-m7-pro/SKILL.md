---
name: 3d-printer-anycubic-m7-pro
description: "Photon Mono M7 Proの温調タンク、レジン・露光・支持・供給とPhoton Workshop接続を確認する。非Proの構成と区別する。"
---

# Anycubic Photon Mono M7 Pro

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/resin-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- M7 Proとレジンの実際の組合せを確認する。温調タンクを備えることと、レジンが目標温度で均一に安定していることを区別する。
- 標準／高速等のレジンとプリセット群の適用条件を照合する。最高速度を狙って通常レジンに高速条件をコピーしない。
- 底層不着、底だけ残る、支持だけ残る場合を分ける。診断資料にある底露光80秒等の条件を全レジンの既定値にしない。
- 失敗後は硬化片と膜を確認してから再試行する。失敗したタンクで自動排液を使うと供給系へ異物が入る懸念があり、公式の該当手順へ戻す。

## 最小限の比較試行

温度・層高・レジンを固定して対応の小試験を使う。加温設定値と実際の温度、底層接着と細部・穴の結果を記録する。

## 接続

Photon WorkshopでM7 Pro用データを生成し、対応USBメモリーまたは公式Wi-Fi／クラウド経路で渡す。Kobra用Slicer NextのLAN機能を移植しない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [M7Pro公式マニュアル](https://wiki.anycubic.com/photon-mono-m7-pro/Photon%20Mono%20M7%20Pro-EN-V0.1.0.pdf)
- [不着の診断](https://wiki.anycubic.com/en/resin-3d-printer/photon-mono-m7-pro/model-non-stick-printing-platform)
- [初回・媒体手順](https://wiki.anycubic.com/en/resin-3d-printer/photon-mono-m7-pro/-quick-start-guide-page-contents)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
