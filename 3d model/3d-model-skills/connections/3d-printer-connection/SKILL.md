---
name: 3d-printer-connection
description: "機種・ソフト・PCのOS/CPUから接続経路を選び、検出・認証・転送・開始を切り分ける。USB媒体・ケーブル、LAN・クラウドを取り違えない。"
---

# 3Dプリンターの接続選択

既存の機材記録・チャットから機種、ファーム、ソフトと版、PCのOS/CPU、希望の経路を確認する。分かっている項目を聞き直さない。[接続方式表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別確認](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当する範囲を読み、以下の1ソフトを選ぶ。

| ソフト | スキル |
| --- | --- |
| Curaの接続 | [専用スキル](../3d-print-connect-cura/SKILL.md) |
| Bambu Studioの接続 | [専用スキル](../3d-print-connect-bambu-studio/SKILL.md) |
| OrcaSlicerの接続 | [専用スキル](../3d-print-connect-orca/SKILL.md) |
| PrusaSlicerの接続 | [専用スキル](../3d-print-connect-prusa/SKILL.md) |
| Creality Printの接続 | [専用スキル](../3d-print-connect-creality/SKILL.md) |
| Anycubic Slicer Nextの接続 | [専用スキル](../3d-print-connect-anycubic-next/SKILL.md) |
| CHITUBOXの接続 | [専用スキル](../3d-print-connect-chitubox/SKILL.md) |
| Photon Workshopの接続 | [専用スキル](../3d-print-connect-photon-workshop/SKILL.md) |
| PreFormの接続 | [専用スキル](../3d-print-connect-preform/SKILL.md) |

PCと機種の両方が対応する経路を選ぶ。Wi-Fiはプリンターがネットワークに入る方法、LANはIP通信、クラウドは外部サービスの経由、USBは媒体かケーブルかを明記する。スライサーが機種を描けることとネットワーク送信の対応を分ける。

接続・認証・転送を実行する依頼では、許可された範囲の確認から進める。プリンターが見つからないことを理由に印刷を開始したり、接続モード・認証・ネットワーク保護を無関係に変更したりしない。接続テストが印刷開始を含む場合はその影響を先に明確にする。

返すものは、選んだ機種／ソフト／OS／CPU／版、経路、確認できた段階、止まった段階と根拠、次の最小確認。別ソフト・別PCへ切り替える案も、互換性とモデル・材料設定を保って示す。
