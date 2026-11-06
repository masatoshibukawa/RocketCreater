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

ワークベンチの画面は外した。下の3項目のうち、文献と参照機体は「設計例と資料」タブで今も見られる。解析履歴の固定と凍結した案の組立手順PDFはプロジェクトが前提なので、APIにだけ残る。

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

## 画面の案の流体解析（`/aero/loop`）

「流体解析」タブが使う。プロジェクトは要らない。CFD は数分かかるので、POST は解析を始めるだけですぐ返り、画面は GET で終わるまで読みに行く。解析は API のプロセス内で1件ずつ進み、API を再起動すると記録は消える。

`POST /aero/loop`、本文 `{"design": …, "target_altitude_m": n, "requirement": …?, "env": …?, "seed": n?, "n": n?}`。バックエンドは下のワークベンチのループと同じ `ROCKETWRIGHT_AERO_BACKEND` で選ぶ。

| 状態 | 意味 |
| --- | --- |
| 202 | 解析を受け付けた。下の job を返す。同じ本文の解析が進行中か完了済みなら、その job を返す |
| 422 | 本文の不備、`ROCKETWRIGHT_AERO_BACKEND` の値の誤り、企業級・重工級の案 |
| 429 | 待ちが4件ある |

`GET /aero/loop/{id}` は job を返す。`status`（`queued`、`running`、`done`、`failed`）、`elapsed_s`、`result`、`error`、`images`。ない `id` は 404。失敗した解析は同じ本文でもう一度実行できる。

`GET /aero/loop/{id}/images/{name}` は `images[].url` の画像を返す。その解析の `flow/*.png` だけで、他のファイル、フォルダーの外を指す名前やリンクは 404。

`result` の項目は下のワークベンチの表と同じ形で、次が違う。

- 重心と機体の形は案の代表形状を使う。組立の計画がないため。部品のフィンの寸法も入らないので、`static_margin_cal` は画面の静安定余裕と一致しないことがある。
- ボトルの圧力は、一覧の値のうち案の圧力より低いものと案の圧力から選ぶ。この案の発射台や定格が分からないので、案の圧力より上げない。
- `dispersion` は `final_design` の多数回試行。`seed` と `n` は本文の値で、ないときは 1701 と 100。予算は判定に入れない。ループが変えるのは圧力と Cd だけで、費用の概算が部品表と食い違うことがあるため。
- アマチュアは調整する圧力がないので、CFD の Cd で飛ばし直して Cd が落ち着くのを見るだけ。`rounds[]` に圧力の項目はなく、`final_design` は元の案のまま、`dispersion` は `null`。`AmateurDesign` に Cd の項目がなく、多数回試行に CFD の Cd を渡せないため。
- `artifacts_dir` は返さない。

## 画面の案の製作データ（`/artifacts/package`）

「製作データ」タブが使う。`POST /artifacts/package`、本文 `{"design": …, "build": …?, "requirement": …?, "env": …?, "seed": n?, "n": n?}`。案のシミュレーションと多数回試行をやり直し、合格ならファイルを `/artifacts/*` に置く。不合格は 409 で、ファイルを作らない。`build` があれば部品表と費用は部品の値になり、ボトルの静安定余裕もレポートに入る。企業級・重工級は 422。

返り値の `files[]` は、ボトルで製作票 PDF、設計レポート（Markdown、JSON）、部品表 CSV、側面図 SVG。アマチュアは製作票がない。画面は合格案だけにボタンを出し、実機の縮尺案（参照元の条件で飛んだ案）には出さない。`unavailable[]` は作れないものと理由。

`rocketwright/agent/manual.py` の組立手順PDFは出さない。その入力は `bottle_assembly.assembly()` の計画で、1.5 Lの製作例の寸法・材料・部品を固定し、質量と Cd も書き換える。Claudeの案に当てはめると、シミュレーションした機体とは別の機体の手順になる。製作票は案の値・シミュレーションの結果・部品表・実物で確認する項目だけを載せ、手順の文章と機体の寸法は載せない。

## 飛行・CFDループのAPI（UI担当向け）

確認済みプロジェクトに、CFD を反映した案を併記する操作。既存の工程、凍結した design、製作ファイルは変わらない。計算の中身は [aero.md §7](aero.md) を参照。

`POST /workbench/projects/{id}/aero-loop`、本文 `{"revision": n}`。他の工程と同じく、終わるまで応答しない。OpenFOAM は 1 周あたり数分かかる（同じ形状と速度はキャッシュで即時）。実行中は `GET /workbench/projects/{id}` の `active` が `{"name": "aero_loop", "started_at": …}` になる。成功でも失敗でも `revision` は 1 増える。

| 状態 | 意味 |
| --- | --- |
| 200 | プロジェクトの view を返す。`aero_loop` に結果が入る |
| 404 | プロジェクトがない |
| 409 | 確認済みでない、`revision` が古い、別の操作が実行中、解析コードが変わった |
| 422 | 本文の不備、`ROCKETWRIGHT_AERO_BACKEND` の値の誤り、CFD が扱えない条件 |
| 503 | CFD の実行失敗か時間切れ。理由は `detail` と view の `error`。前回の `aero_loop` は残る |

バックエンドは API の環境変数 `ROCKETWRIGHT_AERO_BACKEND`（`auto`、`barrowman`、`openfoam_pipeline`、`lbm_gpu`。既定は `auto`）で選ぶ。`auto` で CFD が使えないと L0 で完了する。その場合 `rounds[].fidelity` が `L0` になり、Cd は設計の値のまま。

view の `aero_loop`（未実行なら `null`）：

| 項目 | 内容 |
| --- | --- |
| `source_action` | 対象の確認工程の ID |
| `backend_requested`、`target_apogee_m`、`cg_from_nose_m` | 実行条件。重心は水を積んだ状態 |
| `rounds[]` | 周ごとの記録。下記 |
| `converged` | Cd の変化 2 % 未満かつ圧力が不変で止まったら `true`。周回上限で止まったら `false` |
| `final_design` | CFD の Cd（`axial_drag_coefficient`）と更新後の圧力を入れた `BottleDesign`。製作には使わない |
| `baseline` | 確認工程の値：`pressure_kpa`、`cd`、`success_rate` |
| `dispersion` | `final_design` の多数回試行（確認工程と同じ `n`、`seed`）：`n`、`seed`、`success_rate`、`passes`、`failure_counts`、`apogee_m`、`descent_speed_mps`（分位点） |
| `artifacts_dir` | 流れの画像と `report.md` のあるサーバー上のフォルダ。L0 では `null`。ブラウザー用の URL ではない |
| `notes` | 解法の注意。校正の組が崩れる旨もここに入るので、そのまま表示する |

`rounds[]` の各要素：`round`、飛行の `flight_pressure_kpa`・`flight_cd`・`flight_apogee_m`・`max_speed_mps`、CFD の `cfd_speed_mps`・`cd`・`cd_change_frac`・`x_cp_from_nose_m`・`static_margin_cal`（`null` がありうる）、更新後の `pressure_kpa`・`apogee_m`・`descent_speed_mps`、`elapsed_s`、`cached`、`backend`、`fidelity`。

`aero_loop` の高度は校正から外れた値なので、確認工程の結果と並べるときは別の根拠として表示する。工程をさらに進めても `aero_loop` は消えない。`source_action` と今の確認工程を見比べて、古い結果かどうかを判断する。

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
