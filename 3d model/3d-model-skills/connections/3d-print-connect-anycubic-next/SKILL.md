---
name: 3d-print-connect-anycubic-next
description: "元のKobra3をAnycubic Slicer Nextへ接続し、LAN Modeとクラウドを分ける。旧SlicerやPhoton Workshopの接続と混同しない。"
---

# Anycubic Slicer Nextの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

公式のNext Quick StartはWindows／macOSの要件を示す。Linux・ARMや送信モジュールは、その版の公式配布を確認できるまで対応済みとしない。旧Anycubic SlicerとNextを区別する。

## 接続の手順

1. 元のKobra 3の実機・ファームとNextの版を確認する。V2/Max/S1向けの説明を無条件にコピーしない。
2. 公式手順でLAN Modeを有効にする場合、クラウド・アプリ遠隔操作等が使えなくなる影響を先に確認する。
3. PCと本体を通信可能な同一LANに置き、WorkbenchからAdd Printerで検索してConnect Printerを選ぶ。検出しなければゲスト分離と経路を調べる。
4. WorkbenchのLAN Printer表示で接続状態を確かめ、機種・ノズル・材料・実機を一致させてから送信する。

## 行き詰まったとき

LANの公式説明で対応ソフトとされるのはNext。Photon Workshopへ同じ操作を当てはめない。ACE ProのUSB接続をPCとの印刷ケーブルと誤認しない。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [Kobra3 LAN Mode](https://wiki.anycubic.com/en/fdm-3d-printer/kobra-3-combo/kobra-3-series-lan-connection-guide)
- [Next要件と導入](https://wiki.anycubic.com/en/software-and-app/new-page-anycubic-slicer-beta%28orca-version%29/anycubic-slicer-next-slicing-software-quick-start-guide)
