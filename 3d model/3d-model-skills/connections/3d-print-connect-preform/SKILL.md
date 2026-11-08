---
name: 3d-print-connect-preform
description: "PreFormとForm4のUSBケーブル・Ethernet・Wi-Fi接続、Dashboardとローカルの差、Windows/macOSのPC要件を確認する。"
---

# PreFormの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

確認した公式要件は64-bit Windows（ARM非対応）とmacOS。Linuxは公式対応OSに含まれない。MacのOSとCPUは現行配布を照合する。

## 接続の手順

1. Form4の型番、材料・タンク・プラットフォームに対応するPreFormとファームを用意する。
2. ネットワーク不要ならデータ対応USBケーブルでPCと本体を接続する。これはUSBメモリー経路と異なる。
3. LANではEthernetまたはWi-Fiに接続し、PreFormで検出する。mDNS検出と実通信の条件を確認する。検出失敗時は公式の手動接続とネットワーク要件を使う。
4. PreFormの送信先とジョブを確認し、アップロードと本体開始を分ける。Dashboardの登録・オンライン状態はインターネット側の別状態として扱う。

## 行き詰まったとき

Dashboardがオフラインでも、USBやLANのローカル接続まで不可能とは判断しない。Windows ARMで動作するはずとしてドライバーを追加し続けず、対応PCを選ぶ。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [PC要件](https://formlabs.com/support/What-are-the-system-requirements-to-run-PreForm)
- [USB／LAN／クラウド](https://formlabs.com/support/Connectivity-and-Security/)
- [Dashboardの診断](https://formlabs.com/support/Troubleshooting-a-Dashboard-connection/)
