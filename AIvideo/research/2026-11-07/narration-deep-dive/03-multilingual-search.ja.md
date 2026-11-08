# 多言語の探索記録

確認日：2026年11月7日。8言語で探索し、各言語の本文を読んだ。以下の資料が全て最新の生成モデルを説明するわけではない。基礎資料、原著論文、実装、API仕様を役割別に採用した。

| 探索言語 | 実際に使った検索語・探し方 | 本文を確認した資料 | 得た視点 |
| --- | --- | --- | --- |
| 日本語 | 既存の公式実装とOJADを直接確認 | [OJAD](https://www.gavo.t.u-tokyo.ac.jp/ojad/)、AivisSpeech、Style-Bert-VITS2（S07・S27・S28） | 読みとアクセント、文ごとの編集 |
| 英語 | 原著論文名と既知のarXiv識別子で直接確認 | WaveNet、FastSpeech 2、VITS、F5-TTS、Qwen等の原著・実装（S09〜S26ほか） | 方式の違いと測定の条件 |
| 中国語 | 语音合成 多音字 SSML phoneme／CosyVoice 流式 | [Alibaba CloudのSSML本文](https://help.aliyun.com/zh/isi/user-guide/ssml-overview)（S06） | ピンイン、数値の読み分け、時刻。CosyVoiceの結論は英語の原著とカードへ戻した |
| 韓国語 | 음성합성 운율 딥러닝／한국어 음성 합성 | [NAVER Cloud TTS仕様](https://api.ncloud-docs.com/docs/ai-naver-clovavoice-ttspremium)（S05） | 声質・感情・話速・出力形式を別に扱う |
| ドイツ語 | Sprachsynthese Prosodie neuronale／LMUの講義から追跡 | [LMU Sprachsynthese](https://www.phonetik.uni-muenchen.de/studium/skripten/P6_Sprachsynthese/)（S01） | 文字前処理、G2P、韻律、信号生成の分解 |
| フランス語 | synthèse vocale prosodie／開発元の技術説明 | [Caen CRISCOのKali](https://crisco.unicaen.fr/ressources-en-ligne/synthese-vocale-kali/description-des-differentes-operations/)（S02） | 自然さに関わる句・文・段落の高低・強弱・速度 |
| スペイン語 | síntesis de voz prosodia／síntesis de voz SSML | [Llisterriらの著者公開章](https://joaquimllisterri.cat/publicacions/Llisterri_Machuca_Mota_Riera_Rios_03_Entonacion_Tecnologias_Habla.pdf)（S03）、Microsoft公式スペイン語版（S31） | 抑揚と意味。SSMLの制御と製品依存 |
| ポルトガル語 | síntese de fala fonético／UFPAの研究資料 | [Igor Costa do CoutoのUFPA修士論文](https://repositorio.ufpa.br/bitstreams/b0a13f51-3e4b-4a71-a385-d55be2dcda59/download)（S04） | 文字と発音の多対多対応、音声処理の基礎 |

## 件数の読み方

[sources.json](sources.json) は31件の一次資料。資料の言語、対象、日付、読んだ範囲、支持する主張を記録した。論文の要旨だけを読んだものはその範囲を明記し、全文の実験条件を再現したとは扱わない。

原著論文とその公式実装、同じモデルのカードは、別の用途の資料として数えたが、独立した品質評価が三つあるとは数えない。Microsoftのスペイン語版は公式のローカライズであり、英語版から独立した実験ではない。多言語の文書を読んだ件数と、多言語音声を実際に評価した件数も異なる。今回の音声生成・試聴・ベンチマーク件数はゼロ。

## 採用しなかった、または取得できなかったもの

- 検索結果には非公式のミラー、まとめ、ブログ、投稿が含まれた。原理と条件の結論は、開発元、著者、大学、標準化団体の資料へ戻した。
- FalaBrasilのポルトガル語TTS一覧は「Coming soon」で、完成したTTSの導入手順の根拠にはしなかった。関連するUFPAの学位論文で基礎部分を確認した。
- Open JTalk本体のNITechサイトは今回の経路では取得できず、G2Pと辞書の扱いはpyopenjtalkの作者リポジトリを参照した。
- スペイン語のVigo大学の論文概要ページ、NAVERの一部ガイドURLは取得できなかった。著者公開のスペイン語章と、取得できたNAVERの公式API本文を採用した。
- 専用の深掘り調査コネクターは未認証で結果を返さなかった。代わりに公開Webから資料を直接確認した。専用調査の完了結果や応答IDは存在しない。
- 古い教育資料の公開年・サイトの更新年・検索エンジンの取得日は別物。本文にない発行日を検索結果の表示だけで補わず、レジストリでは不明をnullにした。

## 追加調査で残る課題

このPCでの同一原稿の比較、日本語を母語とする確認者による試聴、対象話者の規約と不可聴透かしの検証、具体的なWindows実行経路の測定は残る。資料の記載から性能値を捏造して埋めず、[試験計画](evaluation-plan.example.json) の空の結果として引き継ぐ。
