---
name: 3d-figurine-print-review
description: "FDM/光造形フィギュアを最終サイズで確認し、顔と薄部、支持痕、接地、中空の排液、色の経路を評価する。多色変換や自動修復後の検証にも使う。"
---

# フィギュアの印刷・配色の確認


機種と材料製品に合う[印刷スキル](../../categories/3d-model-printing/SKILL.md)を使い、次のうち必要な方式だけ読む。モデルの見た目、メッシュ検査、スライス、実機の成功は別の確認。

## FDM

最終サイズで目・口・指・耳・尻尾とダボをスライスし、実際の線幅/層高で残るかを見る。元モデルの面数や低い層高だけで細部が出ると断定しない。小さい先端は冷却/最小層時間、根元は層方向と外壁を確認する。

支持とseamを顔・正面の重要面から移す候補を比較する。顔の見え方と支持除去での破損を両方見る。狭い接地は[接地スキル](../../categories/3d-print-bed-stability/SKILL.md)、細部の溶けは[速度/冷却](../../categories/3d-print-speed-calibration/SKILL.md)を併用する。S5の既存Tough PLA条件にBambu/AMSの多色機能を追加できるとはみなさない。

## 光造形

接点の傷を隠せる面、断面の変化とisland、耳・尻尾の初期層を全層で確認する。一律45度や自動支持だけで確定しない。[Form 4の最小形状表](https://formlabs.com/global/support/Design-specifications-for-3D-models-Form-4-generation)は機種/樹脂/層高の試験条件付きで、取り外して持てる耳・爪の耐久設計値とは別。

小型フィギュアを常に中空化しない。中空にするなら、造形中の吸盤、各空洞の排液・通気、洗浄・乾燥・必要な内部硬化と後で閉じる経路を設計する。[Lycheeの吸盤検出](https://docs.mango3d.io/doc/resin-documentation/resin-holes/suction-cup-detector/)のDeleteは警告模様を消すだけ。空洞を直したことにはならない。[穴の書出し](https://docs.mango3d.io/doc/resin-documentation/resin-export/export-3d/)と最終スライスを再確認する。

[island検出](https://docs.mango3d.io/doc/resin-documentation/resin-support/island)は層高と検出設定に依存する。重要な形状の未支持を探し、微小な印すべてへ同じ太い支持を付けて表情を壊さない。失敗後は機種手順で残片等を処理し、同じデータで無条件に再出力しない。

## 色の経路

単色＋塗装、色別部品の組立、対応機の多色のどれを使うかを決める。STLから元のテクスチャが自動復元されるとはみなさない。Bambu Studioの[Texture-to-Color](https://wiki.bambulab.com/en/software/bambu-studio/texture-to-color)は、取得時の資料では2.7.1以降、対応テクスチャ付き形式と機種/給材の条件がある。色数を絞り、瞳・頬・腹・耳先の境界が最終サイズで残るか確認する。

[色/材料の割当て](https://wiki.bambulab.com/en/software/bambu-studio/multi-color-printing)、実スロット、[濃色→淡色のパージ](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change)をプレビューと試片で確認する。内部へ流した色が薄い明色の顔へ透けないかも見る。表示色が似ているだけで材料の熱/接着の適合を認めない。

まず顔・薄い根元・接合の原寸小片を必要な範囲で試し、顔の再現と除去後の健全さを見て本形状へ進む。全形状の長時間安定・展示時の転倒は別に確認する。
