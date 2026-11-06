# 第三者の資料とライセンス

このリポジトリのコード（`rocketwright/`、`api/`、`web/`、`scripts/`、`tests/`）は MIT ライセンスです（[LICENSE](LICENSE)）。次の資料は第三者のもので、それぞれのライセンスに従います。

| 場所 | 内容 | ライセンス |
| --- | --- | --- |
| `文献/CAD/D21-ESP-Controlled-Rocket/` | 第三者が公開したロケットの CAD（STL など） | GPL-3.0（同じフォルダの `LICENSE`） |
| `文献/CAD/D09-RocketFins/` | 第三者が公開したフィンの CAD | BSD 2-Clause（同じフォルダの `LICENSE`） |
| `AIvideo/Test project/`、`AIvideo/pet-rocket/`、`sites/rocketwright-demo/` | それぞれのフォルダの `LICENSE` に従う | 各フォルダを参照 |

同梱していないものもあります。

| 対象 | 扱い |
| --- | --- |
| 流体解析のパイプライン | 外部のリポジトリで、ライセンスの表示がありません。同梱せず、`tools/aero/openfoam-pipeline.Dockerfile` がイメージのビルド時に取得します。RocketWright は別のプロセスとして呼び出すだけです |
| OpenFOAM | Docker のイメージとして利用します（GPL-3.0） |
| 背景の素材（Poly Haven） | CC0。同梱せず、出所を `assets/product-demo/current-design/appearance-sources.json` に記録しています |

素材の出所は次のとおりです。

- `web/public/workshop/` の整備員と工房の絵は、`final output ui example/drafts/` の画像案から切り出した装飾です。画像案は画像生成ツールで作ったもので、生成の記録とプロンプトは同じフォルダにあります。
- `rocketwright/catalog/motors/*.eng` の推力曲線は、公表値に合わせて作った合成の曲線です。元のデータは写していません。
- 部品とエンジンのカタログの値は、項目ごとに出典の URL か `provisional: true` を持ちます。
