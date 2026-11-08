---
name: 3d-print-materials
description: "3Dプリントの材料選定、製品別設定、機種との適合、複数材料の併用、材料変更を整理して専門スキルへ案内する。材料が既知なら該当する材料スキルと機種スキルを併用する。"
---

# 3Dプリントの材料索引


材料名だけで温度・乾燥・露光を確定しない。まず[材料条件の記録](references/material-contract.md)を使い、既存のスプール・ボトル・試行記録から分かる項目を埋める。未確定のまま進められる設計・調査と、実機出力に必要な条件を分ける。

## 材料から選ぶ

| 材料系 | 読むスキル |
| --- | --- |
| PLA | [PLA](../3d-material-pla/SKILL.md) |
| Tough PLA・PLA+ | [Tough PLA・PLA+](../3d-material-tough-pla/SKILL.md) |
| PETG | [PETG](../3d-material-petg/SKILL.md) |
| PET・PET CF | [PET系](../3d-material-pet/SKILL.md) |
| PPS・PPS CF | [PPS系](../3d-material-pps/SKILL.md) |
| ABS | [ABS](../3d-material-abs/SKILL.md) |
| ASA | [ASA](../3d-material-asa/SKILL.md) |
| TPU・TPEの柔軟材 | [TPU・TPEの柔軟材](../3d-material-tpu/SKILL.md) |
| PA・ナイロン | [PA・ナイロン](../3d-material-nylon/SKILL.md) |
| PC・PCブレンド | [PC・PCブレンド](../3d-material-pc/SKILL.md) |
| PP | [PP](../3d-material-pp/SKILL.md) |
| CF・GF等の繊維入り材料 | [CF・GF等の繊維入り材料](../3d-material-fiber-filled/SKILL.md) |
| LW-PLA・発泡PLA | [LW-PLA・発泡PLA](../3d-material-foaming-pla/SKILL.md) |
| PVA・BVOHの水溶性支持材 | [PVA・BVOHの水溶性支持材](../3d-material-soluble-support/SKILL.md) |
| Breakaway・剥離用支持材 | [Breakaway・剥離用支持材](../3d-material-breakaway-support/SKILL.md) |
| 標準・模型用レジン | [標準・模型用レジン](../3d-material-standard-resin/SKILL.md) |
| 工学用・高靱性・柔軟・耐熱レジン | [工学用・高靱性・柔軟・耐熱レジン](../3d-material-engineering-resin/SKILL.md) |
| 水洗いレジン | [水洗いレジン](../3d-material-water-wash-resin/SKILL.md) |

## 金属の合金系から選ぶ

| 合金系 | 読むスキル |
| --- | --- |
| ステンレス鋼・316L/17-4PH | [金属材料スキル](../3d-metal-stainless-steel/SKILL.md) |
| 工具鋼・H13/A2/D2等 | [金属材料スキル](../3d-metal-tool-steel/SKILL.md) |
| チタン・Ti6Al4V Grade 5/23等 | [金属材料スキル](../3d-metal-titanium/SKILL.md) |
| アルミニウム・AlSi10Mg等 | [金属材料スキル](../3d-metal-aluminum/SKILL.md) |
| ニッケル合金・IN625/IN718等 | [金属材料スキル](../3d-metal-nickel-alloy/SKILL.md) |
| 銅・Cu/CuCrZr等 | [金属材料スキル](../3d-metal-copper/SKILL.md) |

## 組み合わせから選ぶ

| 依頼 | 読むスキル |
| --- | --- |
| その機械で使えるか、プレート・ノズル・送り装置が合うか | [機種と材料の適合](../3d-material-machine-match/SKILL.md) |
| 複数色、異種材料、支持材、レジン混合 | [複数材料と支持材](../3d-material-pairing/SKILL.md) |
| 別材料・別製品に変えたい | [材料の置き換え](../3d-material-substitution/SKILL.md) |
| 連続繊維、金属の機器・合金・粉末/ワイヤー・焼結を扱う | [カーボン・金属の索引](../../industrial/3d-carbon-metal-printing/SKILL.md) |

材料系ごとの条件は[調査資料](../../../10_材料と組み合わせ/README.md)から選ぶ。機械構成は[機種別索引](../../printers/3d-printer-profiles/SKILL.md)、スライスと後処理は[印刷スキル](../../categories/3d-model-printing/SKILL.md)を併用する。PC・OS・CPU別の検出や認証は[接続スキル](../../connections/3d-printer-connection/SKILL.md)で扱う。

## 振り分けの原則

PLA+、Tough、ABS-like等の販売名は共通の組成・強度規格とみなさない。CF/GFは基材ポリマーに追加する条件。水洗いレジンは洗浄特性の区分で、靱性の区分とは重なり得る。

判断は「公式対応」「条件付き試作」「非対応」「不明」に分け、製品と機種への適用範囲を付ける。公式対応でも今回の形状の印刷成功を保証しない。材料変更で以前の寸法・強度・飛行の合格を引き継がない。
