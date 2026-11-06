---
name: 3d-printer-bambu-a1
description: "Bambu Lab A1の可動ベッド、プレート、フローダイナミクスとBambu Studio接続を調整する。A1 miniの造形域とは区別する。"
---

# Bambu Lab A1

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- A1とA1 miniを区別し、装着ノズルとプレート種をBambu Studioで一致させる。プレートを変えたらその表面用の温度・接着条件で再確認する。
- ベッドが前後に動く。高く薄い部品では接地だけでなく方向転換による揺れを見る。全体倍率だけでなく対象の速度・加速度と向きを比較する。
- A1系の自動フローダイナミクスは対応ファームとStudio版を確認する。これはFlow Ratio自動校正と同一ではなく、接地や最大流量の実証にもならない。
- 開放機のため、高温材料・大断面を密閉機と同じ条件で扱わない。反り対策のために開放機を独自に密閉する手順はこのスキルで追加しない。

## 最小限の比較試行

プレート種と標準材料を固定し、初層試験の後に実寸・全高に近い1個を試す。細い接地方向とベッド移動の関係を比較し、ブリム接続を拡大表示する。

## 接続

Bambu Studioの対応ネットワークプラグインでクラウドまたはLAN Onlyを選ぶ。LANでは実機のアクセスコードを扱う。Wi-Fi設定とLAN到達性を確認し、カード書出しは本体対応形式を使う。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [A1 FAQ](https://wiki.bambulab.com/en/a1/manual/faq)
- [自動・手動フローダイナミクス](https://wiki.bambulab.com/ja/software/bambu-studio/calibration_pa)
- [Bambu Studio初期設定](https://wiki.bambulab.com/en/software/bambu-studio/studio-quick-start)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
