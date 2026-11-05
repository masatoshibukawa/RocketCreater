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

## 最新チャットからの追加統合

2026年11月5日の再確認では、以下の確定済み成果を追加した。元PRのマージは行わず、対象ディレクトリの変更だけをこの統合ブランチへ取り込む。

| 出典 | 内容 | 確認したコミット |
| --- | --- | --- |
| [PR #7](https://github.com/masatoshibukawa/RocketCreater/pull/7) | mainにある2Lコカ・コーラ想定のCAD v2、5 STLの検査とスライス記録 | `ecb270e` |
| [PR #13](https://github.com/masatoshibukawa/RocketCreater/pull/13) | 2L CADと物理を保つ写真由来の1080p設計紹介・上昇予測、再生成コード・照合記録 | `a59a12f` |
| [PR #14](https://github.com/masatoshibukawa/RocketCreater/pull/14) | 固体・液体・ハイブリッド・共通の50資料とモデル目録 | `bdb6b6c` |
| [PR #15](https://github.com/masatoshibukawa/RocketCreater/pull/15) | 途中結果の固定、変更の適用、組立の閲覧と実施記録を分けるUX仕様・3画面 | `2f2ef51` |
| [PR #20](https://github.com/masatoshibukawa/RocketCreater/pull/20) | 出力テキスト・読取専用スクリプト・組立PDFの内容設計とレイアウト見本 | `d25b230` |

文献はその後のmain `b723c37`にある増補も反映し、水ロケット98件・モデルロケット81件の計179件とした。資料の件数はAPIで目録から読み、固定の件数に依存しない。

1.5L・60g・30mの既存探索と、2L・3枚フィンのCAD v2は別設計。2Lの映像・CADを1.5L探索の成果物として添付しない。2Lの胴径110mm・高さ315mmは未実測の仮定であり、現物への嵌合・保持・回収・飛行の検証を引き継がない。履歴の閲覧、結果の固定、実作業の完了も別々に扱う。

最初の取得時には `scenarios/thermostructural/` が未コミットだったため、その作業中の内容は取り込まなかった。その後、別チャットの連成解析と解析プールはPR #17でmainに反映された（確認時 `b723c37`）。この開発用画面の既存の探索通過と、追加解析による検証状態は区別する。mainとの組合せも別の検証用作業ツリーで確認する。

### 画面への接続

- 「設計例と資料」から2L試作v2の4種類のSTL、1080p設計紹介・上昇予測、179件の文献を参照できる。公開用の固定IDからだけファイルを選び、形状の版と記録されたSHA256を照合する。欠損や改変があればダウンロードリンクを出さない。映像本体はGitに含めず、`ROCKETWRIGHT_MEDIA_ROOT`に既存の`AIvideo`ディレクトリを指定して再利用する。
- 解析履歴は選択した結果を固定して読める。実行中の工程とは独立し、新しい結果が届いても表示を切り替えない。「最新へ戻る」で追従を再開する。目的・結果・未確認事項を先に表示し、生の計算JSONは展開して確認する。
- 確認した案の製作ファイルを生成した後、組立手順PDFを生成できる。凍結した`assembly.json`・`build.md`・`report.json`の整合性を検査し、同じ寸法・部品表・手順・出典をPDFへ書き出す。表示やダウンロードで実物の組立を完了扱いしない。
- PDF生成にはReportLabを使う。日本語TrueTypeフォントは`ROCKETWRIGHT_PDF_FONT`で指定可能。Windowsでは既存のメイリオを使用し、ない環境では標準の日本語CIDフォントに切り替える。システムのフォントファイルを配布物へコピーしない。

PR #16のマージ後の接続実装は一度[PR #19](https://github.com/masatoshibukawa/RocketCreater/pull/19)へ反映した。出力仕様の並行更新による6ファイルの競合を避け、検証済みのmain基準ツリーを`feature/local-workbench-integration`へ記録して後続の統合PRに移す。元のブランチ・コミットは保持する。クラウドモデルAPIの許可設定は変更しない。

### 最新mainとの検証

main `b723c37`に本PRの変更だけを重ねて検証した。新しい有限時間の空気排出モデルでは従来の400 kPa案が高度条件を満たさず、古い試行列を無条件には再生できない。既定の探索上限400 kPaを維持し、未達の案の製作出力を許可しない。PDFの試験には別途500 kPaを上限とする数値試験条件を明示して作り、適用可能なIDから計算・試行・独立確認を順番に実行した。これは機材の圧力定格の変更や飛行許可ではない。

ブラウザーで1080pの16秒・12秒の映像、179件の目録、過去結果を固定したまま新着1件となる表示、登録された組立PDFの取得を確認した。既存Gemma `gemma4:12b`の提案は履歴を増やさず、別操作で解析を実行する。クラウド設計APIは423で拒否された。PDFは4ページを画像化して目視し、計算条件・設計ID・出典を照合した。

main由来のCFDコードにはWindowsで`os.getuid()`が存在しない既知のテスト失敗がある（`test_openfoam_docker_command_is_limited_and_offline`）。本PRのローカル映像・文献・製作PDFの経路はこのDocker呼出しを使わない。この失敗を本PRの検証成功に含めない。

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

最終の組合せ試験は598件成功・2件スキップ・上記の既存CFDテスト1件失敗。TypeScriptと本番ビルドは成功した。mainで追加されたThree.jsの依存をロックファイルにも反映し、再現できるインストールにそろえる。
