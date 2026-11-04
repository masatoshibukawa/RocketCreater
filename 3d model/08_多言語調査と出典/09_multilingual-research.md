# 多言語調査の方法、言語別の知見、資料の読み分け

[全体の目次へ](../README.md)

## 調査範囲

2026-11-04に、公開されている製品開発元・メーカー・公式プロジェクト・規格団体の資料を検索した。英語、日本語、中国語、ドイツ語、フランス語、スペイン語、韓国語の7言語を対象とし、39件を[出典一覧](sources.csv)へ登録した。

技術的な根拠には一次資料を採用した。検索で見つかった個人投稿、掲示板、広告的なまとめ記事は、今回の手順の根拠にはしていない。公式プロジェクトのリポジトリと、公式サイト風の非公式サイトも区別した。

各言語の資料を日本語へ整理したもので、7言語で生成性能を実験したものではない。英語のプロンプトが常に良い、中国語の資料の方が詳しい等の言語の優劣は結論にしていない。

## 検索と採用の記録

検索例は今回使ったクエリから抜粋したもの。追加調査では対象の公式ドメインと、手元のソフトの版を指定すると絞りやすい。

| 言語 | 使用した検索例 | 主な確認先 | 手順へ反映したこと |
| --- | --- | --- | --- |
| 英語 | `site:docs.tripo3d.ai image to model multi view` / `site:help.prusa3d.com "Drying filament"` | Meshy、Tripo、公開生成実装、Blender、OrcaSlicer、3MF等 | 入出力仕様、版別制約、実寸、メッシュ、校正 |
| 日本語 | `site:formlabs.com jp SLA 後処理 洗浄 二次硬化 設計` | Formlabs、Prusa | 完成寸法に後処理も含める、材料ごとの手順を確認 |
| 中国語 | `3D 打印 AI 生成 模型 混元 3D 腾讯 官方 教程` | Tencent Cloud | 単一主体、白モデル、クラウド版とローカル版の区別、サービス移行 |
| ドイツ語 | `site:help.prusa3d.com de modellieren 3d druck wandstärke toleranzen` | Prusa | 外壁と内部充填を区別、修復で失う形状を確認 |
| フランス語 | `site:help.prusa3d.com/fr "Évidement"` | Prusa | 中空化、排液穴、断面確認 |
| スペイン語 | `site:help.prusa3d.com/es "Primera capa" "calibración"` | Prusa、Blender | 初層と支持、機種ごとの調整、再メッシュ |
| 韓国語 | `site:formlabs.com/kr 3d 프린팅 설계 서포트 세척 경화` | Formlabs | 造形後の洗浄・硬化・仕上げを独立した工程として扱う |

主要な対応資料：[S03](https://docs.tripo3d.ai/model-generation/multiview-to-model-v3-0-v3-1.html)、[S21](https://formlabs.com/jp/support/SLA-basic-finishing/)、[S08](https://cloud.tencent.com/document/product/1804/120704)、[S15](https://help.prusa3d.com/de/article/infill_42)、[S17](https://help.prusa3d.com/fr/article/evidement_117285)、[S19](https://help.prusa3d.com/es/article/problemas-en-la-primera-capa_1804)、[S24](https://formlabs.com/kr/post-processing/wash-cure/)

## 翻訳と独立した証拠を区別する

Prusaの独・仏・西語資料には公式の翻訳ページが多い。同じ記事を複数言語で読んでも、別々の実験による裏付けが増えたわけではない。Formlabsの地域版にも同じ製品説明の展開がある。出典数は登録したページ数であり、独立した39件の研究や、39種類の実機比較を意味しない。

また、日本語URLのPrusa「オブジェクトの方向」は本文の多くが英語で、Blenderのスペイン語4.5ページも未訳の英語が混在していた。URLの言語コードだけで読んだ言語を数えず、実際の本文と注記を確認した。[S20](https://help.prusa3d.com/ja/article/オブジェクトの方向_1658)、[S13](https://docs.blender.org/manual/es/4.5/modeling/modifiers/generate/remesh.html)

## 資料同士で違った点と採用方針

| 論点 | 確認できた違い | この資料での扱い |
| --- | --- | --- |
| 最小壁厚 | 総合AIツールの目安と、特定機種・レジンの値が違う | 平均を取らず、機種・材料・層高・支持条件を添える |
| オーバーハング | 一般的な角度目安と、機種の高性能条件が違う | 角度の基準、冷却、材料、層高と試験結果で判断 |
| 3MFのカラー | 3MF規格に色を扱う仕組みがあっても、生成ツールの書出しは形状だけの場合がある | 実際の書出し機能とスライサーの対応を確認 |
| 修復ツール | 古い記事はNetfabb連携やWindowsツールを挙げる | 現在利用できると断定せず、ローカル編集と再検査の方法を中心にする |
| プロンプト | 印刷制約を具体的に指定する説明と、短い主体記述を勧める説明がある | サービスと版に合わせ、生成後の測定で条件を検証 |
| 支持の除去時点 | 材料・メーカーの後処理手順に依存する | 「硬化前/後」を共通ルールにせず材料手順を優先 |
| クラウドと公開実装 | 同じシリーズ名でもAPI、機能、VRAM、ライセンスが違う | 製品名だけでなく版と提供方式まで記録 |
| 無料プラン | 生成、修復、書出し、所有条件が同じ枠ではない | 使う機能ごとの画面・公式条件を確認 |

参照：[S01](https://docs.meshy.ai/en/webapp/guides/use-cases/3d-printing)、[S32](https://formlabs.com/support/Design-specifications-for-3D-models-Form-4-generation/)、[S04](https://docs.tripo3d.ai/export/conversion.html)、[S16](https://help.prusa3d.com/de/article/beschadigte-3d-modelle-zum-drucken_2205)、[S21](https://formlabs.com/jp/support/SLA-basic-finishing/)、[S34](https://help.meshy.ai/en/articles/15696428-what-is-included-on-the-free-plan)

## 取得と確認の限界

出典一覧の「本文確認」は、ブラウジングで本文を取得して確認したもの。「公式検索掲載本文確認」は、直接取得が制限された場合や検索結果に必要な本文が掲載された場合に、その公式ページ由来の掲載内容を確認したもの。一部は両方を併用した。ページ全体やアカウント内のUIを実操作したという意味ではない。

BlenderのExtensionsや最新マニュアルの一部は、直接取得で402になった。公式検索の掲載本文、対応版の履歴、版を固定したマニュアルで確認し、現行UIで全操作を試したとは記載していない。OpenSCADの資料には古いオプション例もあるため、コマンドはインストール済みの版のヘルプと照合する。

料金・無料枠・最新モデルの順位は固定的な結論を避けた。公開情報の記載と実アカウントの条件が異なる可能性があるため、課金や利用の直前に確認する。生成、スライス、実機造形、強度試験、寸法精度の比較実験はこの調査では行っていない。

## 再検索に使う用語：日・英・中

以下は用語を探すための対照表で、各製品の正式なUIラベルを保証するものではない。

| 日本語 | English | 中文 |
| --- | --- | --- |
| 閉じたメッシュ | watertight / closed mesh | 水密网格 / 闭合网格 |
| 非多様体 | non-manifold | 非流形 |
| 壁厚 | wall thickness | 壁厚 |
| 支持材 | support | 支撑 |
| 張り出し | overhang | 悬垂 |
| 内部充填 | infill | 填充 |
| 隙間・公差 | clearance / tolerance | 间隙 / 公差 |
| 中空化 | hollowing | 镂空 / 中空化 |
| 排液穴 | drain hole | 排液孔 |
| 露光 | exposure | 曝光 |
| 洗浄・二次硬化 | washing / post-curing | 清洗 / 二次固化 |

## 再検索に使う用語：独・仏・西・韓

| 日本語 | Deutsch | Français | Español | 한국어 |
| --- | --- | --- | --- | --- |
| 壁厚 | Wandstärke | épaisseur de paroi | espesor de pared | 벽 두께 |
| 支持 | Stützstrukturen | supports | soportes | 서포트 / 지지대 |
| 張り出し | Überhang | surplomb | voladizo | 오버행 |
| 内部充填 | Füllung / Infill | remplissage | relleno | 내부 채움 |
| 公差 | Toleranz | tolérance | tolerancia | 공차 |
| 中空化 | Aushöhlen | évidement | ahuecado | 중공화 |
| 排液穴 | Ablaufloch | trou de drainage | agujero de drenaje | 배출구 |
| 洗浄 | Reinigung | lavage | lavado | 세척 |
| 二次硬化 | Nachhärtung | post-polymérisation | poscurado | 후경화 |

「waterproof」「watertight mesh」を同じ意味にしない。前者が実物の防水を指す資料では、メッシュの閉じ方とは別の試験・材料・仕上げを扱っている可能性がある。

## 追加調査の進め方

1. プリンター機種、ノズルまたはレジン、材料の正式名称を絞る。
2. そのメーカーのマニュアル、TDS/SDS、プロファイルと使用ソフトの公式仕様を優先する。
3. 原語の用語で症状を検索し、同じ機種・材料・条件か確認する。
4. 翻訳違いを独立根拠と数えず、条件が一致する別メーカー・規格・実験が必要か考える。
5. 数値には機種、材料、向き、層高、後処理を一緒に残す。
6. 新しい案は小さな原寸試験で比較し、採用理由と限界を記録する。
