---
name: 3d-print-connect-cura
description: "UltiMaker CuraからS5/Ultimaker3等へLAN・Digital Factory・媒体で接続する。検出失敗やPC差を調べ、対応機種だけのUSBケーブル機能と区別する。"
---

# Curaの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

Windows／macOS／Linuxの対応版とCPUを配布ページで照合する。ChromeOS、仮想・RDP環境は確認したCura要件の対応外。MacはIntel／M系を区別する。Windows ARMはその版の配布を別確認する。

## 接続の手順

1. 本体をEthernetまたは対応Wi-Fiへ接続し、電源・型番・取得したIPを確認する。PCと通信できる同一LANを基準にする。
2. Curaのプリンター管理で実機型番を有効にし、Connect via Networkから検出する。見つからなければ再検索と手動IP追加を試す。S5とUM3を取り違えない。
3. 本体が求める認証を完了し、ノズル／コア、左右押出機、材料とプロファイルの一致を確認する。3MFの再読込後も解決済み設定を見る。
4. PREPAREで機種用にスライスし、送信先とジョブを確認する。Monitorに出たこと、転送完了、実機開始を別の状態として記録する。

## 行き詰まったとき

クラウド経路はDigital Factory、オフラインは対応ファイルをUSBメモリーへ保存する。S5／UM3のUSB媒体をPC直結ケーブルと呼ばない。他機種でUSBケーブルを使う場合はシリアル対応・ドライバーとCuraのUSB-cable printing設定を版別に確認する。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [ネットワーク追加](https://support.ultimaker.com/s/article/1667410781484)
- [検出診断](https://support.ultimaker.com/s/article/1667337573408)
- [OS要件](https://support.ultimaker.com/s/article/1667337917781)
- [版別変更](https://github.com/Ultimaker/Cura/releases)
