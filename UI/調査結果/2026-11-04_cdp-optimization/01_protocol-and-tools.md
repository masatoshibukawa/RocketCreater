# CDPとツールの選択

## 普段の操作と詳細な観測を分ける

Playwrightの通常操作で目的を満たすなら、そのAPIを使う。Chromium固有の計測が必要な箇所で `page.context().newCDPSession(page)` を作り、`send` とイベント購読を加えられる。作業後はセッションをdetachする。[CDPSession](https://playwright.dev/docs/api/class-cdpsession) [D05]

| 選択肢 | 向く用途 | 判断点 |
| --- | --- | --- |
| Playwrightの通常起動・接続 | 通常の画面実装、操作、回帰確認 | 高水準の待機・要素操作を使える |
| 通常のPlaywright + CDPSession | 画面操作にChromium固有の観測を追加 | 既存の操作を維持し、必要なドメインだけ使う |
| `connectOverCDP` | 既存のCDP対応ブラウザへの接続が必要 | Chromium限定。通常のPlaywright接続より機能の再現性に制約がある |
| CDPを直接送受信 | 独自の小さな計測器、プロトコル検証 | 接続、ID、セッション、イベント、期限、後始末を自分で扱う |

Playwrightは `connectOverCDP` を通常のPlaywrightプロトコル接続より低いfidelityと説明している。高速化のために無条件で置き換える根拠にはならない。[BrowserType](https://playwright.dev/docs/api/class-browsertype#browser-type-connect-over-cdp) [D04]

既に提供されたブラウザツールに必要な機能がある場合はそれを使う。CDPの知識は、ツールの許可範囲を広げたり、別経路でユーザーのブラウザへ接続したりする許可にはならない。

## 必要な領域から読む

| ドメイン | 調べる対象・代表的な入口 | Webデザインでの用途 |
| --- | --- | --- |
| Runtime | `evaluate` | 限定したDOM情報・寸法・状態の取得 |
| Page | `captureScreenshot` | 指定した範囲の画面確認 |
| Network | イベント、キャッシュ・通信条件の設定 | リクエストの順序と待ち、条件の再現 |
| Performance | `enable`、`getMetrics` | ランタイムの粗い傾向把握 |
| Tracing / IO | `start`、`end`、ストリームの読み出し | 処理の時系列と原因分析 |
| Target | ターゲット・コンテキスト・セッション | 対象画面の選択、複数画面の分離 |

定義の入口: [browser_protocol.json](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/browser_protocol.json) [D02]、[js_protocol.json](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json) [D03]。表は機能選択の案内であり、毎回全ドメインを有効にする手順ではない。

browser全体の接続先、pageの接続先、page内のframeを同じものとして扱わない。ナビゲーションや別プロセスiframeにより実行コンテキストが変わりうるため、以前取得したオブジェクトやセッションが引き続き有効か確認する。タブが増える作業ではタイトルの曖昧な一致だけで対象を選ばない。

## バージョンと接続設定

公式リポジトリの定義は日々生成・更新される。`master` の仕様やexperimentalな機能が、手元の安定版Chromeにすべてあるとは限らない。ブラウザ、クライアント、使用した定義の版を記録し、未対応の場合は使える方法へ戻す。非推奨APIを古い記事からそのまま採用しない。[リポジトリの更新方法](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/README.md) [D01]

Chrome 136以降では、通常のデータディレクトリを対象とした `--remote-debugging-port` / `--remote-debugging-pipe` は認められず、通常と異なる `--user-data-dir` が必要になった。公式は自動化にChrome for Testingも案内している。自分で起動を管理する検証では専用プロファイルを使い、デバッグ接続先を外部へ公開しない。[Chromeの変更案内](https://developer.chrome.com/blog/remote-debugging-port) [D11]

起動を省くために日常利用のプロファイルを流用する運用にはしない。再利用するのは所有・管理範囲が明確な検証用ブラウザとし、閉じる対象も自分で作ったコンテキストやセッションに限定する。
