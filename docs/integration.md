# RocketWright 統合設計

このブランチは設計・解析本体、ローカル制作環境、UIと制作スキルを一つの作業面へ接続する。既存チャットで進行中の未コミット変更は取り込まない。以下は2026年11月4日に確認したコミットのスナップショットであり、元PRの承認・マージを意味しない。

| 出典 | 取り込む内容 | 確認したコミット |
| --- | --- | --- |
| [PR #1](https://github.com/masatoshibukawa/RocketCreater/pull/1) | 提出期限、階層設計、適用条件と根拠の扱い | `c2d94af` |
| [PR #3](https://github.com/masatoshibukawa/RocketCreater/pull/3) | 映像スキル、Blender作例、ComfyUI/Wan2.2実行系 | `ffb3da0` |
| [PR #4](https://github.com/masatoshibukawa/RocketCreater/pull/4) | 層別の解析候補・評価・適用条件、静的安定性の計画 | `67f9f41` |
| [PR #5](https://github.com/masatoshibukawa/RocketCreater/pull/5) | UI設計・文章・検証のスキルと調査 | `217d83e` |
| [PR #6](https://github.com/masatoshibukawa/RocketCreater/pull/6) | ペトロケ探索、条件付き安定性、購入計画、印刷部品 | `7d8bc41` |
| [PR #7](https://github.com/masatoshibukawa/RocketCreater/pull/7) | 3D制作の索引、工程別スキルと記録 | `2cb8f6e` |
| [PR #8](https://github.com/masatoshibukawa/RocketCreater/pull/8) | 21件の材料・部品・機材候補。#6に同じ実装を含む | `d98243d` |
| [PR #9](https://github.com/masatoshibukawa/RocketCreater/pull/9) | 黒いドック型画面と4状態のUI案 | `882cd74` |

別チャットのユーザー指定から、最初の製作用対象はペットボトルロケット、途中の節目で次の工程へ進むか選択する方式、設計説明動画と打ち上げCGの両方、解析中の小さな作業キャラクターを引き継ぐ。月までの設計は将来目標であり、このペトロケ用解析を外挿しない。

| 担当 | 決めること・実行すること | 持たせない権限 |
| --- | --- | --- |
| LLM | 適用可能な候補IDと理由、説明・ショット構成・動作プロンプトの提案 | 数値の捏造、合否や証拠の上書き、シェル・任意ノードの実行 |
| ハーネス | 候補の絞込み、入力版、工程・確認点、計算予算、出典、出力の所属と状態 | 仮定を実測値に変更すること |
| スクリプト | 数値計算、CAD/STL、Blender、固定ComfyUIグラフ、書出しと検査 | 未確認の工程を完了扱いすること |
| ユーザー | 要求・仮定の確認、次工程の選択、採用、現物測定と実地確認 | — |

## 成果物の契約

- 解析結果は候補ID、入力、条件、seed、計算の根拠と一緒に保持する。
- 寸法図・部品表・STLは同じ採用案から生成する。材料・寸法を変えたら解析と下流出力を作り直す。
- 印刷メッシュ、スライス、実物の寸法・強度、飛行の確認は別々に記録する。プリンター未指定時は機械固有のG-codeを生成しない。
- 設計説明動画は寸法・構成・解析図を確定的に合成する。ローカルLLMは説明とカメラの提案に使う。
- 打ち上げCGは解析の軌跡と演出を区別する。Wan2.2による生成画素から寸法・飛行性能を読み戻さない。
- 進捗の百分率・残り時間は計測できる場合だけ表示する。ショット表を生成済み動画、サーバー起動を推論成功として扱わない。

## 既存実行系

ローカル会話LLMはモデル一覧と実接続を確認して選ぶ。動画推論は既存の [ComfyUI/Wan2.2](../AIvideo/local-runtime/README.md)、精密な構成とHUDは [Blender作例](../AIvideo/Test%20project/README.md) を使う。モデルやランタイムの大容量ファイルはGitに含めない。

API接続の一次資料: [Ollamaの構造化出力](https://docs.ollama.com/capabilities/structured-outputs)、[ComfyUIサーバーの経路](https://docs.comfy.org/development/comfyui-server/comms_routes)。LLMの構造化出力にもアプリ側の検証を適用する。

これは開発の統合であり、最終提出ではない。提出先・対象ファイルが確定した時点で、名称・メタデータ・リンク・公開履歴の最終提出チェックを別に実行する。AI利用申告、著作権、ライセンス、出典を保持する。
