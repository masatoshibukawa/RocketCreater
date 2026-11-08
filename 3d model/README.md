# AIから3Dモデルを作り、3Dプリンターで出力するための調査

初回調査日：2026-11-04。実機失敗と機種・接続別の追加調査：2026-11-06。材料と組み合わせの追加調査：2026-11-07。本文は日本語。英語・日本語・中国語・ドイツ語・フランス語・スペイン語・韓国語の公開資料を調べ、作業に使える手順へ整理した。

**最初は「AIで外観を作る→実寸と形状を修正→正しい機種設定でスライス→原寸の部分試作→本出力」の順で進める。** 寸法を合わせる部品は、パラメトリックCADを中心にする。

## 制作に使うスキル

[3Dモデル制作の索引スキル](3d-model-skills/SKILL.md)から、工程の専門スキルに加え、接地・速度、[17機種の専用スキル](3d-model-skills/printers/3d-printer-profiles/SKILL.md)、[9ソフトの接続スキル](3d-model-skills/connections/3d-printer-connection/SKILL.md)を選べる。詳しい数値や手順は、必要な機種・工程の資料だけを参照する。

[材料索引](3d-model-skills/materials/3d-print-materials/SKILL.md)には材料別16スキルと組み合わせ判断3スキルを追加した。機械・ノズル・プレート・支持材との適合、複数材料とレジン混合、材料変更時の再検証を扱う。

| カテゴリー | スキル |
| --- | --- |
| 全体工程 | [3d-model-overview](3d-model-skills/categories/3d-model-overview/SKILL.md) |
| AI生成 | [3d-model-ai-generation](3d-model-skills/categories/3d-model-ai-generation/SKILL.md) |
| モデル修正と設計 | [3d-model-preparation](3d-model-skills/categories/3d-model-preparation/SKILL.md) |
| 印刷と後処理 | [3d-model-printing](3d-model-skills/categories/3d-model-printing/SKILL.md) |
| トラブル対処 | [3d-model-troubleshooting](3d-model-skills/categories/3d-model-troubleshooting/SKILL.md) |
| 制作レシピ | [3d-model-recipes](3d-model-skills/categories/3d-model-recipes/SKILL.md) |
| チェックと記録 | [3d-model-records](3d-model-skills/categories/3d-model-records/SKILL.md) |
| 多言語調査と出典 | [3d-model-research](3d-model-skills/categories/3d-model-research/SKILL.md) |
| 材料と組み合わせ | [3d-print-materials](3d-model-skills/materials/3d-print-materials/SKILL.md) |

利用時は`3d model/3d-model-skills/SKILL.mdを使って…`のように入口を指定する。ここでは指定場所にスキル原本を保存しており、自動検出やインストールの設定は行っていない。

## カテゴリー別の資料

工程と用途で分類し、実機・機種・接続の追加調査を9番目、材料と組み合わせを10番目にまとめた。フォルダー番号は読む順番の目安で、文書名の番号は元の工程順を保持している。

| カテゴリー / フォルダー | 主な内容 | 読む資料 |
| --- | --- | --- |
| `01_全体工程` | 作り方の選択、工程ごとの合格条件、ファイル形式 | [全体工程と方法の選び方](01_全体工程/01_workflow-and-choices.md) |
| `02_AI生成` | 参考画像、プロンプト、クラウド/ローカル、ツールと利用条件 | [AI生成](02_AI生成/02_ai-generation.md) |
| `03_モデル修正と設計` | Blender/CAD、メッシュ修復、実寸、壁厚、公差、方向、分割・接合 | [メッシュ修復とCAD](03_モデル修正と設計/03_mesh-and-cad.md)、[印刷設計](03_モデル修正と設計/04_design-for-print.md) |
| `04_印刷と後処理` | 材料、スライス、校正、支持、実機出力、洗浄・乾燥・硬化、仕上げ | [FDM/FFF](04_印刷と後処理/05_fdm-printing.md)、[光造形](04_印刷と後処理/06_resin-printing.md) |
| `05_トラブル対処` | 26の症状、原因確認、戻る工程、再試作 | [症状別の切り分け](05_トラブル対処/07_troubleshooting.md) |
| `06_制作レシピ` | マスコット、寸法付きプレート、浮き彫り、指示文、外注の準備 | [制作レシピと指示文](06_制作レシピ/08_recipes-and-prompts.md) |
| `07_チェックと記録` | 工程別チェック、保存、費用、受け渡し、記入用テンプレート | [チェックと記録](07_チェックと記録/10_checklists-and-records.md) |
| `08_多言語調査と出典` | 7言語の検索と知見、用語対照、資料の違いと限界、39件の出典 | [多言語調査](08_多言語調査と出典/09_multilingual-research.md)、[出典一覧CSV](08_多言語調査と出典/sources.csv) |
| `09_実機トラブルと機種別対策` | 接地・転倒・速度・加速度・流量・光造形、17機種、9ソフト、OS/CPU別接続 | [実機対策の入口](09_実機トラブルと機種別対策/README.md)、[接続表](09_実機トラブルと機種別対策/connections.md)、[PC別確認](09_実機トラブルと機種別対策/pc-connection-checks.md) |
| `10_材料と組み合わせ` | 材料製品の条件、機械・ノズル・プレート・支持材の適合、異材と材料変更 | [材料の入口](10_材料と組み合わせ/README.md)、[組み合わせ表](10_材料と組み合わせ/compatibility.md) |

記入用テンプレートは`07_チェックと記録/templates/`にまとめている：[仕様メモ](07_チェックと記録/templates/project-brief.md)、[印刷記録CSV](07_チェックと記録/templates/print-log.csv)、[比較試験CSV](07_チェックと記録/templates/experiment-log.csv)、[制作記録JSON](07_チェックと記録/templates/project-record.example.json)。

出典CSVは、元の`topic`（資料の主題）に加え、`referenced_categories`で参照されるカテゴリーを絞り込める。複数のカテゴリーで使う資料は`|`で区切って記録し、出典IDと言語・確認範囲は共通で管理している。

## 目的から選ぶ

| やりたいこと | 読む順番 |
| --- | --- |
| まず全工程を把握する | [全体工程](01_全体工程/01_workflow-and-choices.md) → [チェックと記録](07_チェックと記録/10_checklists-and-records.md) |
| 置物やマスコットを作る | [AI生成](02_AI生成/02_ai-generation.md) → [制作レシピ](06_制作レシピ/08_recipes-and-prompts.md) → [FDM](04_印刷と後処理/05_fdm-printing.md)または[光造形](04_印刷と後処理/06_resin-printing.md) |
| 寸法を合わせる部品を作る | [メッシュとCAD](03_モデル修正と設計/03_mesh-and-cad.md) → [公差・接合の設計](03_モデル修正と設計/04_design-for-print.md) → [寸法付きの制作例](06_制作レシピ/08_recipes-and-prompts.md) |
| 印刷がうまくいかない | [症状別の切り分け](05_トラブル対処/07_troubleshooting.md) → 該当する修正・設計・印刷工程 |
| 原語の資料や根拠を調べる | [多言語調査](08_多言語調査と出典/09_multilingual-research.md) → [カテゴリ付き出典CSV](08_多言語調査と出典/sources.csv) |

```mermaid
flowchart LR
  A["用途・寸法を決める"] --> B["AI生成 / CAD"]
  B --> C["実寸・メッシュ修正"]
  C --> D["壁厚・方向・分割"]
  D --> E["方式別にスライス"]
  E --> F["原寸の部分試作"]
  F --> G["本出力・後処理"]
  G --> H["検査・記録"]
  F -->|"未達の条件を修正"| D
```

対象は家庭用・小規模工房で使うFDM/FFFと光造形（SLA・MSLA・DLP）。人物、マスコット、装飾品に加え、寸法を合わせるケースや治具も扱う。プリンター機種は未指定のため、機種・材料に依存する設定値と、設計上の一般原則を区別する。

このディレクトリは調査資料であり、実機での造形結果や、特定サービスの比較実験を記録したものではない。試作の出発点となる数値には、条件と確認方法を付ける。39件は出典ページの件数で、公式翻訳や地域版を含む。独立した39件の実験ではない。

## 試作例

実機での接地不足・速すぎる造形・終盤転倒を受けた[再調査と対処手順](09_実機トラブルと機種別対策/fdm-reliability.md)を追加した。[接地と転倒対策](3d-model-skills/categories/3d-print-bed-stability/SKILL.md)と[速度・流量校正](3d-model-skills/categories/3d-print-speed-calibration/SKILL.md)は、既存の印刷・トラブル対処スキルからも参照できる。

[コカ・コーラ2Lを想定したペットボトルロケットのコーンとフィン](prototypes/pet-rocket-coke-2l/README.md)に、調整用パラメーター、生成スクリプト、STL、編集用Blenderファイル、形状検査を保存した。生成時は機種未指定の形状・スライス確認だった。その後、S5でフィンの終盤転倒を記録したため、実機成功とは扱わない。実寸への適合・強度・飛行の確認は残る。試作例の検証範囲と失敗後の対策は各記録を参照する。
[コカ・コーラ2Lを想定したペットボトルロケットのコーンとフィン](prototypes/pet-rocket-coke-2l/README.md)に、調整用パラメーター、生成スクリプト、STL、編集用Blenderファイル、形状検査を保存した。独立レビューで印刷姿勢・補強・先端・嵌合確認を改善している。ボトルの実寸とプリンター機種は未確認で、実印刷・飛行は行っていない。試作例の検証範囲は各記録を参照する。

カテゴリー別の調査資料には印刷済み作品は含まない。まず使う機種と材料を決め、対応する公式プロファイルで小試作するための資料として使う。
