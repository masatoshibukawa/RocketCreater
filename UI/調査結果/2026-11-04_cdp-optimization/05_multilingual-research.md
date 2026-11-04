# 多言語での確認と探索方法

## 方法と結果

Chromeの実行時性能教材を、英語・日本語・簡体字中国語・韓国語・ドイツ語・フランス語・スペイン語・ブラジルポルトガル語で確認した。これは同一教材の翻訳間の確認であり、8件の独立研究ではない。APIの綴りとexperimental/deprecated指定は英語の公式JSON・PDLを基準にした。

| 言語 | 確認した用語・観点 | 次に探す場合の検索語 |
| --- | --- | --- |
| 英語 | runtimeとload、主スレッドの処理 | `CDP reduce round trips tracing overhead` |
| 日本語 | ランタイム パフォーマンス、CPUスロットリング | `CDP 一括取得 レイアウト 計測` |
| 中国語 | 运行时性能、CPU 节流 | `CDP 批量读取 性能分析 布局抖动` |
| 韓国語 | 런타임 성능、CPU 제한 | `CDP 성능 분석 강제 동기 레이아웃` |
| ドイツ語 | Laufzeitleistung、実行中とロードの区別 | `CDP Leistung Layout Thrashing messen` |
| フランス語 | performances d'exécution、ロードとの区別 | `CDP performances limiter captures aller-retour` |
| スペイン語 | rendimiento del entorno de ejecución、CPU制限 | `CDP rendimiento trazas latencia automatización` |
| ポルトガル語 | desempenho do ambiente de execução、教材の版 | `CDP desempenho rastreamento automação navegador` |

出典: [EN](https://developer.chrome.com/docs/devtools/performance) [D17]、[JA](https://developer.chrome.com/docs/devtools/performance?hl=ja) [D18]、[ZH](https://developer.chrome.com/docs/devtools/performance?hl=zh-cn) [D19]、[KO](https://developer.chrome.com/docs/devtools/performance?hl=ko) [D20]、[DE](https://developer.chrome.com/docs/devtools/performance?hl=de) [D21]、[FR](https://developer.chrome.com/docs/devtools/performance?hl=fr) [D22]、[ES](https://developer.chrome.com/docs/devtools/performance?hl=es-419) [D23]、[PT-BR](https://developer.chrome.com/docs/devtools/performance?hl=pt-br) [D24]。

検索語は今後の探索用に作成したものを含み、全語句の検索結果を網羅的に調べたという記録ではない。今回の確認では翻訳本文を読み、実行時の処理と読み込みの区別、CPU制限、教材の前提を照合した。

## 実務へ持ち帰る点

教材には特定版Chromeを前提とする説明やデモ専用の制限値がある。例えば4倍slowdownは、どのサイトでも最適な固定値という意味ではない。翻訳された数字を一般的な性能目標へ昇格させない。最新のUIや設定は [現行Performance reference](https://developer.chrome.com/docs/devtools/performance/reference) [D09] と実行環境で確認する。

言語を変えると説明や用語を探しやすくなるが、同じ原文の再翻訳は新しい証拠を増やさない。原著者、原URL、版、更新日を確認し、古いAPI例は現行定義へ戻って検証する。翻訳の数より、目的に合う計測と再現条件の一致を重視する。
