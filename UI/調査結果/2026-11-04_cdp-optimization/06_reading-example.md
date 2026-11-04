# 小さな情報を一括取得する例

既存のPlaywright Chromiumセッションで使うJavaScript例。ブラウザ起動や任意の接続先探索は含めない。呼び出し側で対象画面と必要な準備状態を確認し、ナビゲーションやviewport変更と並行実行しない。

## 読み取り関数

`session` は対象pageから作った `CDPSession`。本文や入力値を取得せず、主領域の寸法・横はみ出し・見出し数を一度のevaluateで返す。iframeやshadow DOM内部を含めた検査ではない。

```js
export async function readLayoutFacts(session) {
  const response = await session.send('Runtime.evaluate', {
    expression: `(() => {
      const root = document.documentElement;
      if (!root) throw new Error('Document is not ready');
      const main = document.querySelector('main');
      const rect = main?.getBoundingClientRect();
      return {
        viewport: { width: innerWidth, height: innerHeight, dpr: devicePixelRatio },
        horizontalOverflowPx: Math.max(0, root.scrollWidth - root.clientWidth),
        main: rect ? { x: rect.x, y: rect.y, width: rect.width, height: rect.height } : null,
        mainHeadingCount: main?.querySelectorAll('h1, h2').length ?? 0
      };
    })()`,
    returnByValue: true
  });
  if (response.exceptionDetails) {
    throw new Error('Layout observation failed; inspect the target document');
  }
  if (!response.result || response.result.value === undefined) {
    throw new Error('Layout observation returned no value');
  }
  return response.result.value;
}
```

`Runtime.evaluate` の値返却と例外情報は [公式Runtime定義](https://raw.githubusercontent.com/ChromeDevTools/devtools-protocol/master/json/js_protocol.json) [D03] に基づく。関数の観測項目と異常処理は本資料の例である。

## セッションの寿命を作業に合わせる

```js
export async function inspectPreparedPage(page) {
  const session = await page.context().newCDPSession(page);
  try {
    return await readLayoutFacts(session);
  } finally {
    await session.detach();
  }
}
```

両ブロックは同じモジュールへ置く想定。繰り返す検証では、対象が有効な間だけセッションを再利用して `readLayoutFacts` を呼び、作業全体の最後にdetachできる。[CDPSession API](https://playwright.dev/docs/api/class-cdpsession) [D05]

呼び出し側では、環境に応じた操作・接続タイムアウトを設ける。`main` がないページもあるため、nullだけで欠陥と判断しない。horizontalOverflowPxが0でも重なり・読みにくさ・要素内部の切れまでは検査できない。寸法の取得自体が、直前の変更に対するレイアウト計算を発生させることもある。

## 確認範囲

コードブロックのJavaScript構文をNode.jsで確認した。実ブラウザでの実行、Playwrightの依存追加、CDP接続、速度比較は行っていない。採用時は対象版と画面で動作を確認し、元の取得方法と同じ情報が得られることを確かめる。
