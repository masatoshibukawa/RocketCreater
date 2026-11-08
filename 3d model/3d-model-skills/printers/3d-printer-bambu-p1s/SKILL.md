---
name: 3d-printer-bambu-p1s
description: "Bambu Lab P1Sの密閉環境、補助ファン、手動流量校正と接続を確認する。P1PやX1の自動校正機能と区別する。"
---

# Bambu Lab P1S

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- P1SはP1Pと異なる筐体・補助冷却を持つ。P1向けフローダイナミクスは公式の対応表では手動。自動ベッド校正があることを自動PA校正と混同しない。
- PLA等の低温材料で長時間密閉するとheat creepの候補になる。反り対策として温度を上げ続ける前に、プレート・室内温度・筐体換気・ファンを機種手順で照合する。
- 補助ファン側に偏った反りを観察する。ファンを一律最大にせず、材料の冷却条件を保ちながら配置と冷却の影響を比較する。
- CoreXYでも接地が小さい高い部品の反り・ノズル接触は残る。広告速度やSport等の倍率を基準にしない。

## 最小限の比較試行

同じ材料とプレートで1個を比較し、補助ファン側の角の浮き、上部の熱変形、接触跡を記録する。室内温度と筐体の状態も残す。

## 接続

Bambu StudioのクラウドまたはLAN Only。手動IP・アクセスコードを使う場合も到達性とファームの認証方式を確認する。Orca側の対応はStudioと同一とは限らない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [P1 FAQ](https://wiki.bambulab.com/en/p1/manual/faq)
- [Heat creep](https://wiki.bambulab.com/en/filament-acc/filament/heat-creep)
- [フローダイナミクス](https://wiki.bambulab.com/en/software/bambu-studio/calibration_pa)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
