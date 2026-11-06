# RocketWright の画面

Next.js（App Router、TypeScript）の画面です。バックエンド（`api/`）が出すイベントと要約を表示します。数値はすべてバックエンドのツール結果で、画面は単位の変換だけをします。

## 画面

- 上に、設計、解析、出力の 3 工程があります。
- 左は相談です。要求の入力、質問への回答、中断、リセットをここで行います。
- 中央は 3D モデルと整備員の絵です。
- 右は結果で、設計の工程でだけ出ます。
- 左右の欄の幅は、境界をドラッグして変えられます。

質問に回答すると、元の要求に「追加情報:」として追記し、設計を最初からやり直します。バックエンドに会話の記憶がないためです。

## 起動

```bash
npm install
ROCKETWRIGHT_API_URL=http://127.0.0.1:8000 npm run build
npm run start -- --hostname 127.0.0.1 -p 3000
```

- `ROCKETWRIGHT_API_URL` はビルドの時点で決まります（`next.config.ts` の rewrites）。起動時に変えても効きません。
- 開発時は `npm run dev -- --hostname 127.0.0.1` です。
- `--hostname 127.0.0.1` を付けないと、同じネットワークから画面と、`/backend` 経由の API に届きます。
- Claude の設計を実行するには、API 側で環境変数を入れます（ルートの README）。

## 構成

- `app/page.tsx`：画面全体。
- `app/components/`：`ChatPanel`（相談）、`ModelViewer`（3D）、`WorkshopScene`（整備員の絵）、`AeroLoopPanel` と `AeroLiveView`（流体解析と実行中の表示）、`FlightPlayer`（飛行の再生）、`FlightChart`、`ProductionPanel` と `DesignProduction`（出力）、`ResultPanel`、`CostPanel`、`BomPanel`、`DockHandle`（幅の変更）。
- `app/lib/`：`designState.ts`（イベントから画面の状態を作る）、`useDesignStream.ts`、`useAeroLoop.ts`、`caseLabels.ts`、`workshopLayers.ts`（絵の層の表。生成物）。
- 今は使っていない部品：`DetailsPanel` と、その下の `AttemptLog`、`CandidateCards`、`DesignChainPanel`、`DispersionPanel`、`ReviewPanel`。2026-11-07 に画面から外しました。

## 整備員の絵

`public/workshop/` の絵は `scripts/build_workshop_layers.py` が `final output ui example/drafts/` の 02 と 06 から切り出した装飾です。頭や手を別の層にして CSS で動かし、速さは実行中の工程に合わせます。絵の横の数値と流れの画像だけが計算結果です。

## 検査

```bash
npx tsc --noEmit
node --experimental-strip-types --test tests/workshopActivity.test.mjs
```

バックエンドとの対応（イベントの種類、指標の名前、API のパス）は、ルートの `tests/test_web_contract.py` が確かめます。
