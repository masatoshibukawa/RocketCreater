# スキル索引

RocketCreater内のスキルを、用途と参照先から探すための索引です。各項目のリンクから `SKILL.md` を読み、必要な専門スキルと資料へ進んでください。

2026-11-07時点で、確認したリモートブランチに **145スキル**があります。内訳は **mainに28件、未統合の追加分が117件**です。同じパスは1件として集計し、入口やカテゴリ案内も含めています。[基準となるmainのコミット `a579315`](https://github.com/masatoshibukawa/RocketCreater/commit/a579315056ef3cd51026a1dc3ac517e842523705)

## 用途から選ぶ

| やりたいこと | 入口 | 件数 |
| --- | --- | ---: |
| 3D形状の生成、CAD修正、印刷準備、印刷不良の改善 | [3Dモデル制作](../3d%20model/3d-model-skills/SKILL.md) | 9 |
| Web画面の情報設計、配色、文字、コピー、実装とレビュー | [Webデザイン](../UI/web-design-skills/SKILL.md) | 10 |
| AI映像、VFX、音声、ローカル環境、制作進行 | [動画制作](../AIvideo/skills/video-production/SKILL.md) | 8 |
| 共同作業中のGit同期、commit・push・PRの維持 | [Git同期](../.agents/skills/frequent-git-sync/SKILL.md) | 1 |
| 機種・材料・接続別の3Dプリント、品質検証、フィギュア | [3Dプリント拡張の索引](printing-extensions.md)（未統合） | 追加85 |
| ピッチ、研究発表、スライド、デモ、話し方、質疑 | [プレゼンテーションの索引](presentation-extensions.md)（未統合） | 追加31 |
| WebアプリのAPI、認証、データ保存、バックグラウンド処理 | [Webバックエンド](#webバックエンド1件)（未統合） | 追加1 |

複数工程にまたがる依頼は入口から、用途が決まっている依頼は以下の専門スキルから始められます。

## mainにあるスキル（28件）

### 3Dモデル制作（9件）

用途と寸法の整理から、AI生成・メッシュ修復・CAD設計・スライス・不良対処・記録まで扱います。[調査資料と制作例](../3d%20model/README.md)も参照できます。

| スキル | 使う場面 |
| --- | --- |
| [3d-model-skills](../3d%20model/3d-model-skills/SKILL.md) | AIを使う3Dモデル制作と3Dプリントの総合依頼を整理し、全体工程・生成・修正と設計・印刷・トラブル対処・レシピ・記録・調査の専門スキルへ案内する。 |
| [3d-model-ai-generation](../3d%20model/3d-model-skills/categories/3d-model-ai-generation/SKILL.md) | 文章・単画像・複数視点から印刷向けの3D形状を生成し、入力・指示文・ツール・採用案を整える。 |
| [3d-model-overview](../3d%20model/3d-model-skills/categories/3d-model-overview/SKILL.md) | 3Dモデル制作の用途・寸法・印刷方式から、AI生成・CAD・複合方式の経路と合格条件を決める。 |
| [3d-model-preparation](../3d%20model/3d-model-skills/categories/3d-model-preparation/SKILL.md) | 3Dプリント用メッシュを修復し、CADで実寸・壁厚・隙間・方向・分割・接合を設計する。 |
| [3d-model-printing](../3d%20model/3d-model-skills/categories/3d-model-printing/SKILL.md) | FDM/FFFまたは光造形のモデルを対象機種・材料でスライスし、出力と後処理へつなぐ。 |
| [3d-model-recipes](../3d%20model/3d-model-skills/categories/3d-model-recipes/SKILL.md) | 置物・寸法付き部品・浮き彫りの制作レシピを、ユーザーの形状・寸法・機種に合わせて具体化する。 |
| [3d-model-records](../3d%20model/3d-model-skills/categories/3d-model-records/SKILL.md) | 3D制作の仕様・生成条件・モデル版・スライス・試行・後処理を既存テンプレートで記録し、検収や受け渡しへまとめる。 |
| [3d-model-research](../3d%20model/3d-model-skills/categories/3d-model-research/SKILL.md) | AIから3Dプリントまでの技術的な疑問を、既存の多言語出典と現在の一次資料で調べる。 |
| [3d-model-troubleshooting](../3d%20model/3d-model-skills/categories/3d-model-troubleshooting/SKILL.md) | 3Dモデルや印刷の不良を、形状・スライス・実機・後処理へ切り分け、仮説を絞って修正・再試作する。 |

### Webデザイン（10件）

情報の優先順位、見た目、文章、実装、確認までを扱います。総合入口から必要なカテゴリを選べます。

| スキル | 使う場面 |
| --- | --- |
| [web-design-skills](../UI/web-design-skills/SKILL.md) | Webデザインの総合依頼を整理し、基礎・参考探索・配色・文字組み・コピー・実装・SF表現・AIと独自性・実践検証へ案内する。 |
| [web-design-ai-originality](../UI/web-design-skills/categories/web-design-ai-originality/SKILL.md) | AI生成っぽい、テンプレート的、サービス固有の内容が弱いWebデザインを改善する。 |
| [web-design-color](../UI/web-design-skills/categories/web-design-color/SKILL.md) | Webの配色、色トークン、ライト・ダークテーマ、文字や操作対象のコントラスト、データ可視化の色を設計・改善する。 |
| [web-design-copy](../UI/web-design-skills/categories/web-design-copy/SKILL.md) | Webの見出し、説明、ボタン、状態・エラー文を具体的で直接的に書く。 |
| [web-design-foundations](../UI/web-design-skills/categories/web-design-foundations/SKILL.md) | Web画面の目的、情報設計、視覚的な優先順位、余白・整列・構図を設計または改善する。 |
| [web-design-implementation](../UI/web-design-skills/categories/web-design-implementation/SKILL.md) | 決めたWebデザインをHTML・CSS・JavaScriptや既存フレームワークで実装・修正する。 |
| [web-design-practice](../UI/web-design-skills/categories/web-design-practice/SKILL.md) | Webデザインの学習計画、制約を使った練習、画面レビュー、案の比較、利用者による確認を組み立てる。 |
| [web-design-references](../UI/web-design-skills/categories/web-design-references/SKILL.md) | Webデザインの参考サイト、制作事例、デザインシステムを探し、採用理由まで整理する。 |
| [web-design-scifi](../UI/web-design-skills/categories/web-design-scifi/SKILL.md) | SF映画のシステム、FUI、HUD、管制画面、研究端末のようなWeb表現を設計・実装する。 |
| [web-design-typography](../UI/web-design-skills/categories/web-design-typography/SKILL.md) | Webのフォント選択、日本語と欧文の組み合わせ、文字サイズ・太さ・行間・行長・改行・数値の整列を設計または改善する。 |

### 動画制作（8件）

映像生成だけでなく、音・編集・実行環境・素材の利用条件をつないで制作します。

| スキル | 使う場面 |
| --- | --- |
| [video-production](../AIvideo/skills/video-production/SKILL.md) | AI動画制作の入口として、目的に合うカテゴリ別スキルを選び、映像・音・編集をつなぐ。 |
| [video-audio](../AIvideo/skills/video-production/video-audio/SKILL.md) | 動画のナレーション、セリフ、声の設計、効果音、環境音、BGM、口の同期を制作する。 |
| [video-generate](../AIvideo/skills/video-production/video-generate/SKILL.md) | テキストや参照画像からAI動画を生成し、写実表現や人物の一貫性、動作、カメラを調整する。 |
| [video-llm-direction](../AIvideo/skills/video-production/video-llm-direction/SKILL.md) | PC内のLLMなどを使い、動画の台本、ショット分解、生成プロンプト、連続性の条件、改善案を作る。 |
| [video-local-runtime](../AIvideo/skills/video-production/video-local-runtime/SKILL.md) | PCのGPU、VRAM、メモリ、OS、既存モデルを確認し、動画や音声のローカル生成環境を選定・構築・診断する。 |
| [video-production-management](../AIvideo/skills/video-production/video-production-management/SKILL.md) | 動画制作の素材、ショット、テイク、生成条件、編集、書き出しを管理し、完成物を確認する。 |
| [video-research-rights](../AIvideo/skills/video-production/video-research-rights/SKILL.md) | AI動画制作のモデルや手法を多言語の一次資料で調査し、出典、性能の条件、モデル重み・声・素材の利用条件を整理する。 |
| [video-sf-vfx](../AIvideo/skills/video-production/video-sf-vfx/SKILL.md) | SFやヒーロー映画の映像を、AI生成・実写・3D・合成を組み合わせて制作する。 |

### リポジトリ運用（1件）

| スキル | 使う場面 |
| --- | --- |
| [frequent-git-sync](../.agents/skills/frequent-git-sync/SKILL.md) | 安全なpull、細かなcommitと即時push、作業用PRの維持を行う。 |

## 未統合のスキルと更新

以下は確認日時点でmainに入っていないPRです。スキルの参照先は確認したコミットに固定しています。

| PR | 内容 | 索引への数え方 |
| --- | --- | --- |
| [#53：3D制作・印刷と検証の拡張](https://github.com/masatoshibukawa/RocketCreater/pull/53) | 接地・速度、PC接続、機種、材料、カーボン・金属、フィギュア、出力・ツールパス・結果検証。[詳細索引](printing-extensions.md) | 3D分野は既存9件＋追加85件＝94件 |
| [#49：プレゼンテーションの拡張](https://github.com/masatoshibukawa/RocketCreater/pull/49) | 共通入口、8カテゴリ、22専門スキル。[詳細索引](presentation-extensions.md) | 31件すべて追加 |
| [#63：Web公開とバックエンド](https://github.com/masatoshibukawa/RocketCreater/pull/63) | バックエンド設計を追加し、Webデザインの入口と実装・公開の手順を更新。[詳細](#webバックエンド1件) | 追加1件 |
| [#64：製品デモと多言語ナレーション](https://github.com/masatoshibukawa/RocketCreater/pull/64) | 動画制作の入口と [video-audio](https://github.com/masatoshibukawa/RocketCreater/blob/7283e4a2312ab1d78aea7d5179a74ccf6b11d712/AIvideo/skills/video-production/video-audio/SKILL.md) を更新。TTSの比較、読み・演技・尺の調整を扱う。 | 既存2件の更新 |
| [#59：PR活動の定期確認](https://github.com/masatoshibukawa/RocketCreater/pull/59) | 既存のGit同期スキルに、最新PR・レビュー・CIの確認を追加 | 既存1件の更新。追加件数には含めない |

mainの [presentation-techniques](../presentation-techniques/README.md) は、現時点では発表方針・調査資料・ワークシートの資料集です。31件のスキル本体は上記PR #49で追加されています。

### Webバックエンド（1件）

| スキル | 使う場面 |
| --- | --- |
| [web-design-backend](https://github.com/masatoshibukawa/RocketCreater/blob/ebc2f20f758e6ce2fc8c1e714f5c5a2a92bb71cf/UI/web-design-skills/categories/web-design-backend/SKILL.md) | API、認証・認可、データベース、ファイル保存、長時間ジョブを設計する。既存サービスとの接続、無料枠と実行制約の比較、公開後の動作確認にも使う。 |

## 使い方

リポジトリ内のファイルを明示して依頼できます。たとえば次のように指定します。

```text
3d model/3d-model-skills/SKILL.mdを使って、モデルの印刷準備を進めてください。
UI/web-design-skills/categories/web-design-typography/SKILL.mdを使って、日本語の可読性を改善してください。
AIvideo/skills/video-production/SKILL.mdを使って、製品紹介動画を制作してください。
```

この `skills/` は索引の置き場です。スキル本体と参照資料は元の場所で管理しています。索引を追加しても、利用環境のスキル一覧への自動登録やインストールは行われません。

## 索引を更新するとき

1. `git ls-files '*SKILL.md'` で、対象ブランチに追跡されているスキルを確認します。
2. 各ファイルの `name`・`description` と実際の用途を確認し、件数とリンクを更新します。同一パスの版違いを別スキルとして数えません。
3. 関連PRが統合されたら、該当項目をmainの一覧へ移し、リンクを相対パスに変更します。未統合の参照先を更新する場合は、PRの状態とコミットも確認します。
4. ローカルリンクの存在、固定コミット内の参照先、一覧の漏れ・重複を確認します。

PC全体にインストールされたスキル、外部プラグイン、キャッシュ、未追跡ファイルは、このリポジトリの件数に含めていません。
