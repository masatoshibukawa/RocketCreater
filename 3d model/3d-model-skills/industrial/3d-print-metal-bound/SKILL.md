---
name: 3d-print-metal-bound
description: "金属粉末を結合材に含むFFF/Bound Powder Extrusionの機械・材料・脱脂・焼結を計画する。金属風樹脂、グリーン品、最終金属を区別する。"
---

# 結合材を使う金属押出・脱脂・焼結


金属色のPLA、装飾用金属入り樹脂、脱脂・焼結用の高金属含有材料を区別する。商品が後者で、受入可能な脱脂/焼結工程が確定した場合だけ実金属へつながる。[工程比較](../../../11_カーボンと金属/process-comparison.md)で到達点を示す。

## 出力前に決める条件

材料製品・世代・径・対応ノズル、専用界面材、スライサー、脱脂方法（溶剤/触媒/熱）、焼結炉・雰囲気・受入条件を揃える。Markforged Wash-1とMetalFuseの触媒脱脂を同じ洗浄レシピにしない。家庭用オーブンや任意の炉へ焼結温度だけ移す手順は作らない。

グリーン品の取り外し/搬送と、脱脂後の脆いブラウン品を支える経路、焼結時のセッター/ラフト・界面・垂れを設計する。プリンターの造形域より最終部品サイズが制限され得る。肉厚と脱脂経路、重い塊、閉じた空洞、加工代を先に受託先/機械資料へ照合する。

焼結収縮は材料・方向・炉・形状で校正し、ソフトの自動補正との二重適用を避ける。LPBFや全合金へ同じ拡大率を移さない。原寸重要部の試片を同じ工程で処理し、最終寸法・変形・密度/空隙と必要な物性を確認する。

## 状態を区別して渡す

グリーン品、脱脂/乾燥済み、焼結済み、熱処理/加工済み、検査済みを別状態として記録する。脱脂は指定の減量/乾燥等の判定を使い、表面の見た目や経過時間だけで炉へ進めない。焼結が終わっても指定の硬度・耐食性・寸法が成立したとは限らない。

[Ultrafuse公式ガイド](https://forward-am.com/gain-knowledge/ultrafuse-metal-solution-quick-start-guide)にはMetal Solutionの終了表示がある。既存在庫・古い動画から、現在の材料供給やD&Sサービス受入を推定せず、使う前に確認する。[MetalFuse](https://www.raise3d.com/metalfuse)の掲載との違いも残す。

製品別の例：[Markforgedの工程](https://markforged.com/resources/learn/design-for-additive-manufacturing-metals/metal-additive-manufacturing-introduction/metal-additive-manufacturing-process)、[脱脂と乾燥の判定](https://support.markforged.com/portal/s/article/Understanding-the-Wash-Process)、[FX10専用316L](https://support.markforged.com/portal/s/article/Printing-with-316L-Stainless-Steel)。316Lの炉投入質量・減量・時間制限を他合金の既定値にしない。
