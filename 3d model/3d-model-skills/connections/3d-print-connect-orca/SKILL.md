---
name: 3d-print-connect-orca
description: "OrcaSlicerの物理プリンター、Moonraker/Octo系ホスト、Bambuプラグインを機種と版で選ぶ。モデル用プロファイルと通信対応を区別する。"
---

# OrcaSlicerの接続

確認日：2026-11-06。既存の機材記録・チャットを先に使い、[PC・接続方式の表](../../../09_実機トラブルと機種別対策/connections.md)と[PC別の切り分け](../../../09_実機トラブルと機種別対策/pc-connection-checks.md)から該当部分を読む。

## PCとソフトの条件

公式リリースでOS・CPU・配布形態を確認する。Linuxは版によりFlatpak等があり、保存先・LAN権限も調べる。WebのDevice画面とファイル送信は別機能として確認する。

## 接続の手順

1. 型番だけでなく実機のホスト方式とファームを確認する。Orcaに機種プロファイルがあるだけで通信可能としない。
2. Neptune 4 Proなら本体を有線LANに接続し、IPをブラウザーで確認する。公式の旧版例はOcto/Klipper。新しい版のMoonrakerホスト等は実際の対応APIと一致するときだけ選ぶ。
3. 物理プリンターのホスト・アドレス、必要ならAPIキーを個別環境で設定して接続テストする。テストとUpload and Printを区別する。
4. Bambu機ではネットワークプラグインと本体の認証方式を照合する。対応しない版なら、Bambu Studioでの送信または適合する媒体へ戻す。

## 行き詰まったとき

Klipper用のAPI設定をS5やレジン機へ移さない。DeviceのWeb画面が開いても、ホスト設定・認証が違えばアップロードできない。接続問題のために無条件のroot化や全認証解除を追加しない。

自動検出、IP到達、認証、転送、印刷開始のどこで止まるかを返す。機器のコードやAPIキーを公開記録へ残さない。調査依頼を実機開始まで拡大しない。

## 一次資料

- [公式リリース](https://github.com/OrcaSlicer/OrcaSlicer/releases)
- [Neptune4の公式Orca手順](https://wiki.elegoo.com/machines/neptune/maintenance/neptune-4-series/networked-control-with-orcaslicer)
- [新しいホスト方式の版別例](https://www.orcaslicer.com/wiki/releases/release_2_4_0_beta.html)
