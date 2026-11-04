# CDPでサイト自体の性能を改善する

## 観測から修正へつなぐ

CDPを通じて集めた情報は、遅い処理を見つけるために使う。サイトのコードや配信を変え、同じ利用場面で再測定して初めて改善を判断する。

| 症状 | 最初の観測 | 修正候補と再確認 |
| --- | --- | --- |
| 主画像や見出しが遅い | 通信の開始順、応答待ち、LCPの内訳 | 主画像の発見・サイズ・優先度、サーバ応答、描画待ち |
| クリック後に固まる | 対象操作のトレース、主スレッドの長い処理 | 処理の分割、不要な再計算、表示更新の範囲 |
| 表示後に内容が動く | Layout shiftsとその前後の画像 | 画像・埋め込み領域の寸法、フォント、挿入内容 |
| スクロールやSF演出が重い | Layout / Paint / フレームの時系列 | 反復する寸法変更、広い描画範囲、要素数、演出頻度 |
| 操作を繰り返すほど重い | 同じ操作後のメモリ推移、必要時のheap調査 | 解放されない購読、DOM、データ保持 |

表の修正候補は診断の仮説であり、すべてを先に実装するチェックリストではない。

## 通信: 時間と条件を一緒に読む

Networkのwaterfallでは、待ち、依存関係、転送、キャッシュの使われ方を確認する。短い要求でも、それが後続の主画像やスクリプトの開始を遅らせるなら重要になる。単純なファイル件数削減だけで判断しない。[Networkの公式ガイド](https://developer.chrome.com/docs/devtools/network) [D25]

CDPでイベントを収集する場合は、request IDとredirect、失敗、キャッシュ、Service Workerを区別する。`loadingFinished.encodedDataLength` の合計は、その記録で観測した対象の集計として扱い、ブラウザ全体の総帯域量と呼ばない。保存する情報は調査に必要な時刻・種別・サイズなどに絞り、本文や認証ヘッダを通常ログへ含めない。

冷たいキャッシュと再訪を別ケースにする。HTTPキャッシュの無効化とService Workerの迂回は別設定なので、どちらを変えたか記録する。現行定義では古い `Network.emulateNetworkConditions` は非推奨で、新しいルール別制御とnavigator側の状態変更が分かれている。後者の新APIはexperimentalであり、対象Chromeでの対応を確認して選ぶ。[Networkの公式定義](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Network.pdl) [D27]

## LCP・INP・CLSを混ぜない

| 指標 | 見る体験 | 診断の着眼点 |
| --- | --- | --- |
| LCP | viewport内の大きな画像・文字が描かれるまで | 応答待ち、リソース開始待ち、転送、描画待ちの内訳 |
| INP | 訪問中の対象操作に対する応答性 | 入力待ち、イベント処理、次の描画までの遅れ |
| CLS | 表示内容の予期しない位置変化 | 寸法未確保の画像・埋め込み、フォント、後から入る内容 |

LCPは画像圧縮だけに還元せず、ボトルネックの内訳に応じて直す。[LCP最適化](https://web.dev/articles/optimize-lcp) [D12]

INPはページ読み込み時間や `click()` のPromiseが返るまでの時間と同じではない。実際の操作を含めて観測する。INPは訪問全体の対象操作に基づくため、一操作のラボ結果を全利用者のINPに置き換えない。[INP最適化](https://web.dev/articles/optimize-inp) [D13]

CLSは時間の単位を持たない。読み込み後の変化も起こるため、初回ロードだけで十分とは限らない。[CLS最適化](https://web.dev/articles/optimize-cls) [D14]

`Performance.getMetrics` はランタイム指標の値を返す入口であり、これ一回でCore Web Vitalsが揃うAPIではない。メトリックの意味と単位を確認する。累積時間は同じ区間で前後を比較し、メモリ使用量のような瞬時値は累積値として引き算しない。ナビゲーションやプロセス変更をまたぐ差分には注意する。

## トレース: 原因調査に必要な区間だけ記録する

Performanceパネルでは読み込みと実行中の記録を使い分けられる。まず再現操作を絞り、どの処理が時間を使うかを調べる。CPU slowdownは手元のCPUに対する相対的な制限であり、特定のスマートフォンそのものの再現にはならない。[Performance reference](https://developer.chrome.com/docs/devtools/performance/reference) [D09]

CDPでの記録は次のように設計する。

1. 必要なカテゴリと区間を決める。スクリーンショット、詳細サンプリング、メモリなどを全部常時取得する前に、必要性を判断する。
2. 完了イベントを購読してから記録を開始し、再現操作後に `Tracing.end` を送る。
3. 応答だけで終了扱いにせず `Tracing.tracingComplete` を待つ。stream方式なら `IO.read` で順次保存して `IO.close` する。
4. `dataLossOccurred` を確認する。データ欠損のある記録は、そのまま完全な証拠として扱わない。

これはAPIの利用順序の要点で、カテゴリ名や対象プロセスの選択は対象版に合わせる。streamは大きな結果の受け渡しを管理しやすくする方式であり、ページの処理自体を軽くする機能ではない。読み出しでは `base64Encoded` と `eof` も扱う。[Tracingの公式定義](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/Tracing.pdl) [D28]、[IOの公式定義](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/pdl/domains/IO.pdl) [D29]

詳細な計測もブラウザ上の仕事を増やす。比較用の最小観測と、原因調査用の詳細記録を分け、どちらの条件で測ったか残す。この使い分けは本調査の運用提案である。

## レイアウト・コード・メモリ

寸法の書き換えと読み取りを交互に繰り返すと、強制同期レイアウトが増えることがある。読み取りをまとめ、その後で変更する案をトレースで確かめる。大きなDOMや複雑な配置も、負荷との関係を確認する。[レイアウトの解説](https://web.dev/articles/avoid-large-complex-layouts-and-layout-thrashing) [D15]

Coverageは未使用のJavaScript/CSSの候補を見つける入口になる。ただし、その記録中に未実行だったコードには別画面・条件・操作で使うものも含まれる。分割や削除は既存の依存関係と利用場面を確認して行う。[Coverageの公式ガイド](https://developer.chrome.com/docs/devtools/coverage) [D16]

メモリは一回の大きな値だけでリークと断定しない。同じ操作・待ち・観測条件で繰り返し、増加が落ち着くかを調べ、必要なら保持元を追う。強制GCやheap snapshotを比較の片側だけで実行しない。
