---
name: 3d-print-connect-chitubox
description: "CHITUBOXとChituManagerで対応レジン機へLAN送信する。OS別のスライス機能と管理モジュール、機種別形式を分けて確認する。"
---

# CHITUBOXの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

BasicとChituManagerそれぞれのWindows／macOS／Ubuntu欄・配布版を照合する。CPU、プラグイン、対応機種も別条件。Basicが起動しただけでManagerのネットワーク送信が使えるとはしない。

## 接続の手順

1. Mars5Ultra／Saturn4Ultra等の正確な型番・解像度と出力形式を選ぶ。12K版と16K版を混同しない。
2. 本体を対応Wi-Fiへ接続し、IPとネットワーク状態を確認する。PCも通信できる同一LANへ置く。
3. Network Sendingで必要なChituManagerを対応版から導入し、Add Printerで本体を選ぶ。管理モジュールが使えない環境なら媒体経路を使う。
4. スライスの機種・レジン・層高・露光を再確認してファイルを送る。管理画面に出ること、転送、実機開始を区別する。

## 行き詰まったとき

Wi-Fi対応でも全機種・全OSで同じManager機能とは限らない。対応ファイルをUSBメモリーへ保存する経路も残す。露光等の機種パラメーターをネットワーク検出結果だけで確定しない。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [ChituManager導入とOS欄](https://docs.chitubox.com/en-US/chitu-manager/latest/introduction)
- [BasicとNetwork Sending](https://docs.chitubox.com/en-US/chitubox-basic/latest/ui-and-features/preview)
- [Saturn4Ultraの公式手順](https://wiki.elegoo.com/saturn/saturn-4-ultra-how-to-enable-remote-printing-via-network-connection)
