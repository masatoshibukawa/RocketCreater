# 実機の失敗と機種・ソフト・PC別の対策

調査開始日：2026-11-06。初期層は付いたのにフィンが終盤で倒れたS5の記録と、接地・速度についての利用者の指摘を起点に再調査した。公式のメーカー資料とスライサー開発元の説明を優先し、英語・日本語・中国語の本文を参照した。翻訳版は独立した実験として数えない。既存の7言語調査は[従来の出典](../08_多言語調査と出典/09_multilingual-research.md)に保持している。

## 症状から使う

| 状況 | 調査資料 | 作業に使うスキル |
| --- | --- | --- |
| 接地が小さい、反る、終盤に倒れる | [FDMの再調査](fdm-reliability.md) | [接地と転倒対策](../3d-model-skills/categories/3d-print-bed-stability/SKILL.md) |
| 速すぎる、揺れる、高速部が痩せる、先端が崩れる | [速度・流量・冷却](fdm-reliability.md#3-速度を一つの数値として扱わない) | [速度・流量校正](../3d-model-skills/categories/3d-print-speed-calibration/SKILL.md) |
| レジンの底層不着、支持だけ残る、空洞の問題 | [光造形の再調査](resin-reliability.md) | 該当するレジン機の専用スキル |
| 実機固有の校正と制約 | 機種の一次資料を専用スキルから参照 | [17機種の索引](../3d-model-skills/printers/3d-printer-profiles/SKILL.md) |
| PCから見つからない、送れない | [機種・転送方式表](connections.md)、[PC別確認](pc-connection-checks.md) | [9ソフトの接続索引](../3d-model-skills/connections/3d-printer-connection/SKILL.md) |

## 今回の機種とソフト

機種はUltiMaker S5／Ultimaker 3、Bambu A1／A1 mini／P1S／X1 Carbon、Prusa MK4S／CORE One、Ender-3 V3 SE／KE、K1C、Kobra 3、Neptune 4 Pro、Mars 5 Ultra、Saturn 4 Ultra 12K、Photon Mono M7 Pro、Form 4の17種。正確な型番・世代を照合して使う。S5以外でこの部品を実印刷した記録ではない。

接続スキルはCura、Bambu Studio、OrcaSlicer、PrusaSlicer、Creality Print、Anycubic Slicer Next、CHITUBOX／ChituManager、Photon Workshop、PreFormの9種。Windows x64／ARM、macOS Intel／Apple Silicon、Linux、未対応・未確認の環境を区別する。

## 根拠と限界

公式の説明、今回の観察、推定、次回案を分けた。ブリム20～35 mm・35 mm/sはS5フィンの局所的な再試行条件で、メーカー標準でも成功実証でもない。自動レベリング、ベッド内、支持なし、プログラム完了の各状態だけで実物合格にしない。

Web検索と必要箇所の抽出で調査した。Parallelの詳細Researchは認証案内から結果を取得できなかったため、同じ接続のSearch／Fetchと公式ページの直接確認を使った。メーカーWikiや配布要件は更新されるため、導入時にソフト版・機体世代・OS／CPUと照合する。資料のない対応は推測で埋めない。

[出典CSV](sources.csv)は、実際に検索・取得した一次資料のうち本文で参照した71 URLを記録する。検索抜粋と必要箇所の取得を区別し、使用するスキル／資料を逆引きできる。翻訳・同内容のURLを含むため、71件の独立した実験ではない。ドイツ語の初層ページは本文の取得が限定的だったので、追加の数値・機種判断の根拠には採用していない。

このフォルダーの調査とスキル作成では、ソフトの新規導入、ネットワーク設定変更、実機への送信・印刷開始は行っていない。実物の再試行は記録が得られた時点で更新する。

[検証記録](validation.md)には、マニフェスト・参照先・出典対応の確認、4件の独立した依頼シナリオと、その結果で直した文言を記載した。スキルの構造検査と、実機での成功確認は区別する。
