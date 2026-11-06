---
name: 3d-printer-bambu-a1-mini
description: "Bambu Lab A1 miniの造形範囲、可動ベッド、校正とネットワーク接続を確認する。A1向け配置やブリムを自動縮小して移さない。"
---

# Bambu Lab A1 mini

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- A1 mini専用プロファイルを選ぶ。大型機用のブリム、パージ、複数配置がそのまま入ると仮定しない。機能寸法を自動縮小して収めない。
- 可動ベッドで背の高い薄い形状の揺れを観察する。標準の自動校正後も、向き・補助接地・加速度の選択が残る。
- A1系の自動フローダイナミクスの対応版を確認する。X1のLidar方式や自動Flow Ratioの対応をそのまま当てはめない。
- プレート表面・材料に合う清掃と接着条件を使う。初層と短い上部の層では冷却を分けて見る。

## 最小限の比較試行

ブリムを含む配置が機種領域内かを先に確認し、1個・原寸で初層から全高まで比較する。全高の試験を全体縮小で代用しない。

## 接続

Bambu StudioでA1 miniを登録し、対応プラグインと同一LAN／クラウドの経路を確認する。LAN Onlyのアクセスコードを別機の値と取り違えない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [A1 miniの構成](https://wiki.bambulab.com/en/a1-mini/manual/intro-a1-mini)
- [フローダイナミクス](https://wiki.bambulab.com/en/software/bambu-studio/calibration_pa)
- [LAN接続](https://wiki.bambulab.com/en/knowledge-sharing/access-code-connect)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
