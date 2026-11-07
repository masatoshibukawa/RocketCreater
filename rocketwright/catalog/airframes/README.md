# 機体テンプレート

1 L、1.5 L、2 Lの編集可能な出発案。未解析・未採用で作り、既存の寸法検証、印刷部品CAD、質量積上げ、飛行計算へ渡す。テンプレートの選択だけでは合格にしない。

参照元は「ペトロケ資料を収集・整理」（`01a1a42d-e515-7920-888e-19704ae2bbef`）の公開モデル。収集ブランチ`3da2a93`から、次の原本とライセンスをバイト列のまま保持した。

| テンプレート | 外形の参照 | 取扱い |
|---|---|---|
| pet-1l | Adrian Schlatter / RocketFinsのbottle.scad | BSD-2-Clause。参照プロファイルを1 L用の編集寸法へ調整した例。元資料が1 Lの実測モデルという意味ではない |
| pet-15l | castetsb/waterRocketToolbox / Kirin Lemon 1.5 L STEP | MIT。参照CADの外径・長さを初期値にし、映像に元の壁・口の形を利用 |
| pet-2l | castetsb/waterRocketToolbox / Soda 2 L STEP | MIT。同上 |

原本・著作権表示・許諾文は[reference](reference/)に保持。元リポジトリの版、元ハッシュは[sources.json](reference/sources.json)。`schlatter-bottle.scad`は参照原本であり、依存SCADを含めた実行パッケージではない。独自の回転体生成でプロファイルを再現する。

STEPはローカルのGmsh 4.15.2で表面三角形へ変換し、右手座標・口が下になる向きへ正規化した。基準半径1・高さ1のSTLと変換記録を保持する。参照モデルはユーザーの手元の容器を測ったデータではなく、容量・材質特性・肉厚の実機認定でもない。[変換API](https://gmsh.info/doc/texinfo/#gmsh_002fmodel_002focc_002fimportShapes)。

映像では入力寸法へ合わせ、ノーズカバーに隠れる領域を共有の取付面で非表示にする。この処理は表示だけで、印刷部品や解析寸法を変更しない。ボトル外形モデルは印刷対象外。印刷出力は従来のノーズ・フィン・嵌合リングに限定する。

CAD部品は生成条件・実装・全ファイルハッシュが一致した場合だけ再利用する。搭載質量等が変われば質量・飛行は再計算し、寸法変更やファイル破損は再生成へ戻す。映像のボトルメッシュは別の内容ハッシュで保存し、字幕・飛行・共通舞台の既存キャッシュへ接続する。

変換ツールは`python scripts/prepare_airframe_references.py --libs CONVERTER_ENV/Lib/site-packages`。通常のアプリ実行では変換済みモデルを読み、Gmshを起動しない。モデル選択ではローカルLLMが登録済みIDと理由だけを返し、スクリプトが寸法と実行処理を所有する。
