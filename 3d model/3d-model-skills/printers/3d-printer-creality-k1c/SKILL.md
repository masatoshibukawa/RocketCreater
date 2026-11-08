---
name: 3d-printer-creality-k1c
description: "Creality K1Cの材料プロファイル、校正、筐体とネットワークを確認する。K1/K1 Max/K1C 2025の構成差を先に照合する。"
---

# Creality K1C

確認日：2026-11-06。この機種の条件差を判断する。[機種条件の受け渡し](../3d-printer-profiles/references/profile-contract.md)と[方式別の確認](../../../09_実機トラブルと機種別対策/fdm-reliability.md)から必要な項目を使う。

## この機種で変わる判断

- K1Cの世代、ノズル、ファーム、Creality Printの版を合わせる。公式パラメーター資料はK1Cと2025版を併記するため実機差を確認する。
- 汎用PLAとCR-PLA等の材料選択を区別する。通常材料の実用上限は試験で決め、最高速度へ合わせるために温度だけを上げない。
- 移設、材料条件変更、ファーム変更後の校正の必要性を公式手順で確認する。版によって列挙されるflow／first layer機能を、未搭載の個体にあると断定しない。
- 筐体内の低温材料の熱と、補助冷却による反りを両方見る。CoreXYでも小さい接地とノズル接触は別問題として調べる。

## 最小限の比較試行

実物の材料用プロファイルで1個を観察し、筐体条件、初層、上部の冷却、接触跡を記録する。

## 接続

対応Creality PrintのLAN送信、Creality Cloud、USBメモリーを選ぶ。LANという表記だけで有線Ethernet端子の存在を推測しない。 OSとソフトの組合せは[接続表](../../../09_実機トラブルと機種別対策/connections.md)を使う。認証情報や機器固有番号を公開記録へ書かない。

## 一次資料と確認範囲

- [K1Cの印刷条件](https://wiki.creality.com/en/k1-flagship-series/k1c/print-parameter-settings)
- [K1Cの転送方式](https://www.creality.com/support/k1c-carbon-3d-printer)

資料は対応条件の根拠で、今回の部品の実機成功を示さない。構成・版が異なる場合は該当する現行マニュアルで照合し、未確認は未確認のまま渡す。
