---
name: 3d-print-continuous-fiber
description: "連続カーボン・ガラス・アラミドと樹脂マトリックスの造形を評価する。繊維経路、曲率、切断、配置可能層、層間と荷重を確認し、短繊維入りFDMと区別する。"
---

# 連続繊維による3Dプリント補強


[材料と機械の条件](../../../11_カーボンと金属/facility-and-quality.md)に、樹脂マトリックスと連続繊維の商品を別に記録する。MarkforgedのCFRとAnisoprintのCFCは給材・含浸・切断・設定が異なる。普通のPA-CF用ノズルへ連続繊維を通す手順にしない。

## 設計とツールパス

荷重の向き、穴周辺・根元・曲げ面を特定し、繊維がその経路へ実際に配置されるかスライサーで見る。外形が印刷可能でも、細すぎる領域、急な曲がり、短い閉路に繊維が入るとは限らない。最低幅・最小曲率・開始/終了/切断位置は当該機種の制約を使う。

強化する層、周回/一方向/角度の配置、繊維体積、樹脂だけの表皮・穴周囲を保存する。繊維を増やす前に、荷重方向と層間剥離・Z方向の接続を確認する。CADにない繊維を外観画像や部品名から推定しない。

プリントヘッドの高さ/位置、繊維の切断と引きずり、乾燥・送り、隙間と樹脂の濡れを機種手順で確認する。原寸の根元・締結部を、実際の繊維経路/層方向と使用環境で試験する。アルミ相当という材料比較だけで金属部品の置き換えを承認しない。

根拠：[Markforgedの連続繊維](https://markforged.com/materials/continuous-fibers/continuous-carbon-fiber)、[機種・世代別の対応表](https://support.markforged.com/portal/s/article/Material-Compatibility-Matrix)、[Composerの調整手順](https://support.anisoprint.com/composer/guide)、[Composer材料と運用](https://support.anisoprint.com/composer/manual)。材質名が同じでも他社スプールの互換性を意味しない。
