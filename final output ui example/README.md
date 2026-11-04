# RocketWright reference workbench

黒背景の実在する設計サービスを基準に、RocketWright の画面を検討するための試作。
`index.html` をブラウザーで開く。外部パッケージのインストールは不要。

## Main reference

[Zoo Design Studio](https://zoo.dev/design-studio) の[公式公開画面](https://zoo.dev/images/download/start-building-today.webp)を目視確認した。
確認日：2026-11-04。参照画像のステータスバーは v1.1.9。ログイン後の最新版を実操作した記録ではない。

再現した要素：無彩色の黒いキャンバス、細い区切り線、左の構成・プロパティ、右の対話、上の小さなツールバー、下のステータスバー。
角丸カードや発光による強調を増やさず、元画面の情報密度と連続するドック構造を基準にした。

機体、ラベル、データ、利用できる操作は RocketWright 用に置き換えているため、元サービスの完全な機能複製やピクセル単位の一致を意味しない。
元製品のコード、ロゴ、モデルは組み込んでいない。参照ダイアログの画像は Zoo の公式URLから直接読み込み、同梱・再配布していない。
Zoo フロントエンドの[公開リポジトリ](https://github.com/KittyCAD/modeling-app)と[MITライセンス](https://github.com/KittyCAD/modeling-app/blob/main/LICENSE)も確認した。
本試作の実装はこのリポジトリのライセンスに従う。

## Other candidates

- [Spline のUI解説](https://docs.spline.design/basics/understanding-splines-ui)：公式の画面説明を確認。対話、オブジェクト構成、表示領域、プロパティが近い。[ダークテーマ](https://docs.spline.design/basics/change-theme-on-spline)を公式資料で確認。
- [Onshape のテーマ設定](https://cad.onshape.com/help/Content/Plans/my_account_preferences.htm)：ダークモードの対応範囲を公式資料で確認。今回は画面の再現基準には使っていない。
- [SimScale のワークベンチ](https://www.simscale.com/docs/simulation-setup/)：設計・解析機能は近いが、今回の黒い画面の基準には採用していない。

## Working interactions

- 案 A / B の切り替え。寸法、形状、グラフ、出力が同じ選択案を参照する。
- 外形の回転、拡大縮小、全体表示。方向キー、+ / -、0 でも操作できる。
- 機体、寸法図、飛行結果、レポート表示。構成要素から対応する設計変数を確認できる。
- 選択案の SVG / CSV / Markdown / JSON の保存。
- 高度、費用、降下速度についての固定データ比較。新たな設計や会話モデルの呼び出しは行わない。
- 狭い画面では構成と対話をボタンで開く。デスクトップ版は参照画面の左右ドック構成。

## Data and limits

表示値と図面は `origin/main` の既存アマチュア固定デモの2案から生成する。
`generate_demo.py` は `simulate_design` を実行し、環境・要求・seed 42・source_id と一緒に `demo-data.js` へ保存する。
公称飛行での合否と仮置きカタログ・概算費用を表示し、多数回試行の成功率や実機の検証結果を捏造しない。
寸法図、部品表、レポートは既存の出力関数を利用する。

中央の概形は寸法から描く簡易表示。内部構造、モーターの詳細、回収装置の形状、製造用の接合形状は表していない。
ソフトウェア表示用の投影で、姿勢運動を解析する機能ではない。

再生成（リポジトリのPython環境を使用）：

```powershell
python '.\final output ui example\generate_demo.py'
```

このディレクトリは設計検討用。既存の `web/`、API、物理モデルは変更していない。
本番化では Next.js の既存イベント・候補管理をこの画面構成へ接続する必要がある。

## Verification

実行済み：JavaScript構文検査、デモ2案の計算、SVGのXML解析、38個のHTML識別子の重複検査、24個のスクリプト参照先と同梱ファイルの存在確認。
2案とも高度の許容範囲と予算内であること、traceの時刻・高度、部品表とレポートの生成を確認した。
ブラウザー操作は環境設定で無効だったため、完成画面のスクリーンショット、実操作、狭い画面の目視確認は未実施。
参照画面の目視確認と、試作画面の表示検証を区別する。
