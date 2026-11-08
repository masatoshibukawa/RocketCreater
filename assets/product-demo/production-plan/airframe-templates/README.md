# 機体テンプレートの試行記録

[条件・解釈・再現手順](../../../../docs/airframe-template-experiment.md)。
CGと数値解析の確認記録であり、実際の飛行映像や印刷成功の記録ではない。

- `native-benchmark.json`: 3種類のCAD/質量/飛行と6枚の1080p静止画の計測原本。
- `three-airframes.jpg`, `pet-*-six-stills.jpg`: 参照外形3種類の比較。
- `reference-comparison.jpg`: 同一入力の旧包絡とKirin Lemon参照外形。
- `design-explanation.mp4`, `launch-cg.mp4`: UIから生成した新しい1.5 L案件の540p/12fpsプレビュー。
- `*-timed.jpg`: 各MP4から9時刻ずつ復号した比較。連続全フレームの目視ではない。
- `verification.json`, `render-cache.json`, `scene-source.json`, `progress.json`: 上記プレビューの検査・実行原本。
- `selection.png`, `production-ui.png`, `playback.json`, `ui-measurement.json`: 実画面の選択/制作と再生・時間。
- `mesh-audits.json`: 保存したBlenderシーンのノーズ/フィン15部品と元のCADの照合。
- `reproduction-check.json`, `replay-audit.json`, `replay-video-verification.json`: 展開したソース/素材から別フォルダーへのプレビュー範囲の再生成。別PC・新環境の確認ではない。
- `slice-review.json`, `print-samples/`: S5 / Tough PLA Gray / AA0.4専用のフィン例。
  `fin-mm.stl`はmm単位、UFPは20 mmの除去ブリム付き。ファイル検査済み・実機印刷未確認。
  ボトル、耐圧部品の印刷データは含まない。

ボトル原本・完全なBSD/MIT許諾文・出典は
[参照カタログ](../../../../rocketwright/catalog/airframes/reference/)に保持。
CG舞台のHDRIと地面テクスチャは既存のPoly Haven CC0素材。
各素材の出典・保存ハッシュは`appearance-sources.json`に保持。
画面下部に映る整備員の既存参考イラストは新しい機体の生成結果ではない。
