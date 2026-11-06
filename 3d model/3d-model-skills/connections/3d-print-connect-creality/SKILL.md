---
name: 3d-print-connect-creality
description: "Creality PrintでSE/KE/K1Cの対応転送方式とOSを選び、LAN追加、認証、クラウドと媒体を切り分ける。"
---

# Creality Printの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

使うCreality Printの版・OS・CPUを公式配布で確認する。古いQuick Startの最低OS値を現在のバイナリーへ固定しない。機種とファームでLAN機能・認証の対応が変わる。

## 接続の手順

1. 型番と世代を先に確認する。Ender-3 V3 SEにKEと同じ標準LAN機能があると仮定しない。
2. KE／K1C等の対応機は本体のネットワーク状態とIPを確認し、同一LANからCreality PrintのDeviceで追加する。自動検出が失敗したら対応版の手動追加を確認する。
3. 必要な本体認証とモデル・材料・ノズルを照合する。K1CのLAN表記だけで有線端子を要求しない。
4. 実機とジョブを選んで転送状態を確認する。Creality Cloudを使う場合はローカル経路と別にアカウント・地域とインターネット接続を確認する。

## 行き詰まったとき

SEは対応メモリーカード、KE/K1Cは対応USB媒体も選べる。Cura等でスライスできることと、Crealityのネットワーク送信が同じように使えることを区別する。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [ソフト初期設定](https://wiki.creality.com/en/software/update-released/Basic-introduction/Quick-Start)
- [K1C対応転送](https://www.creality.com/support/k1c-carbon-3d-printer)
- [SE機種手順](https://wiki.creality.com/en/ender-series/ender-3-v3-se/quick-start-guide/user-manual)
- [KE手順](https://wiki.creality.com/products/diy/ender%E7%B3%BB%E5%88%97/ender-3v3-ke/%E5%A4%9A%E8%AF%AD%E7%A7%8D%E8%AF%B4%E6%98%8E%E4%B9%A6/ender-3_v3_ke-sm-001__user_manual%EF%BC%88en%EF%BC%89.pdf)
