---
name: 3d-print-connect-prusa
description: "PrusaSlicerからPrusaLinkローカルまたはPrusa Connectクラウドへ送る。MK4S/COREOneの接続、USB媒体とPC差を確認する。"
---

# PrusaSlicerの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

Windows／macOS／Linuxの対象版と公式配布を確認する。Linuxの配布方法はリリースで変わるためAppImageと決め打ちしない。スライサーからの送信とブラウザーの管理画面を分ける。

## 接続の手順

1. 対象のMK4S／CORE OneをEthernetまたは対応Wi-Fiへ接続する。公式の設定ファイル方式等を使った場合、認証情報を含む媒体を公開しない。
2. LAN内で使う場合は本体のIPとPrusaLinkの認証設定を確認する。クラウドの場合はPrusa Connectに登録し、対応するアカウントと実機を選ぶ。
3. PrusaSlicerの物理プリンター／送信先で実機とホスト方式、必要な認証を設定する。ブラウザーへ入れることとスライサーからアップロードできることを別に試す。
4. 正しい機種・ノズル・材料でスライスし、転送先と状態を確認する。USBメモリーがジョブ保存や初回設定に必要な条件は実機ガイドに従う。

## 行き詰まったとき

PrusaLinkのローカルIPをPrusa Connectの登録先と混同しない。旧MK3の外付けRaspberry Piの手順を、対応新機種に一律追加しない。USB-CをUSBメモリー印刷と同じ経路としない。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [PrusaLink／Wi-Fi設定](https://help.prusa3d.com/wp-content/uploads/generated/prusa-connect-prusalink_1636_guide_413293_en_2026-05-13.pdf)
- [Connect登録](https://help.prusa3d.com/wp-content/uploads/generated/prusa-connect-prusalink_1636_guide_417586_en_2026-05-13.pdf)
- [ソフト版別配布](https://github.com/prusa3d/PrusaSlicer/releases)
