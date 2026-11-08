---
name: 3d-print-connect-photon-workshop
description: "Photon WorkshopでM7Pro等の機種用データを生成し、対応USB媒体または公式Wi-Fi経路で渡す。Kobra用LAN機能とは区別する。"
---

# Photon Workshopの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

公式の導入要件はWindows／macOSを機種資料とソフト版で照合する。IntelとApple Siliconの要件を区別し、Linux・Windows ARMは未確認のまま対応済みにしない。

## 接続の手順

1. M7 Proの機種・層高・レジンに合うプロファイルを選ぶ。標準／高速の設定群とファームの対応を確認する。
2. USB媒体なら対応形式へスライスし、実機指定の媒体・ファイルシステムへ保存して本体側から選ぶ。PCと本体をUSBケーブルでつなぐ手順ではない。
3. Wi-Fi／クラウド経路は該当ファームと公式ガイドの登録・アカウント・地域を確認する。対応Wi-Fiだけで独立したオフラインLAN送信まで使えるとは仮定しない。
4. 送信先、ファイルの型番、出力形式、レジン・温度・露光を確認する。転送完了と造形開始・成功を別記録にする。

## 行き詰まったとき

Kobra3のNext専用LAN Modeの手順をPhoton Workshopへ移さない。接続の問題を直すために、露光や支持条件を無関係に変更しない。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [M7Pro公式マニュアル](https://wiki.anycubic.com/photon-mono-m7-pro/Photon%20Mono%20M7%20Pro-EN-V0.1.0.pdf)
- [初回とUSB媒体の条件](https://wiki.anycubic.com/en/resin-3d-printer/photon-mono-m7-pro/-quick-start-guide-page-contents)
- [Workshopの導入とOS](https://wiki.anycubic.com/photon-mono-m7-pro/anycubic_photon_workshop-en-v0.2.0-b.pdf)
