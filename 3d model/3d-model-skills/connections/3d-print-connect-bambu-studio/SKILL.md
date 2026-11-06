---
name: 3d-print-connect-bambu-studio
description: "Bambu Studioのネットワークプラグイン、クラウドとLAN Only、IPとアクセスコード、PC別の導入・検出・認証を確認する。"
---

# Bambu Studioの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

Windows／macOS／Linuxの配布と対応プラグインを照合する。Linuxのスライサーが起動したことだけでネットワークモジュールの導入済みを判断しない。初回プラグイン取得はインターネットを必要とする。

## 接続の手順

1. 実機型番と対応Wi-Fi、PCのLAN経路を確認し、対応するStudioとネットワークプラグインを導入する。
2. クラウド接続かLAN Onlyかを選び、既存のクラウド利用への影響を説明する。クラウドは同じアカウント／地域、LANは実機の設定状態を確認する。
3. LAN接続はDeviceのプリンター一覧から該当機を選び、アクセスコードを入力する。検出しない構成では公式のIP＋コード方式を使う。VLANやファイアウォールで通信が許可されることが前提。
4. 型番・プレート・ノズル・材料の対応を確認して送信先を選ぶ。手動IP方式の再起動後の再入力等、版別の認証動作も確認する。

## 行き詰まったとき

LAN Onlyではクラウドの遠隔機能が変わる。ファームの認証変更に対して古い第三者接続手順を固定しない。アクセスコードを公開ファイルへ保存せず、対応カードによる搬送も使えるか実機で確認する。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [Studio初期設定](https://wiki.bambulab.com/en/software/bambu-studio/studio-quick-start)
- [IP／アクセスコード](https://wiki.bambulab.com/en/knowledge-sharing/access-code-connect)
- [LANモード・中国語原文](https://wiki.bambulab.com/zh/knowledge-sharing/enable-lan-mode)
