# 全資料の分類とスキル設計

整理日: 2026-11-07。これまでの調査・制作物51文書を本文まで読み直し、8カテゴリ・22サブカテゴリに整理した。資料のレビュー基準版は `c40dac0`。元の資料の場所を保ち、一つの文書に主分類一つと関連分類を付ける。カテゴリとスキルの対応、全件の分類理由は [catalog.json](catalog.json) にも保存する。

## 分類の考え方

用途で「何を判断してもらうか」を選び、横断技法で「どう伝えるか」を補う。時間、使用言語、媒体、聴衆の専門性は独立した調整条件として扱う。同じ3分でも、投資家ピッチ、3MT、動作動画では内容と媒体の規則が異なる。

各資料の出典番号はその資料群内の番号であり、分野をまたいで同じS01を同じ出典と扱わない。同じ論文や大会を複数の資料が参照するため、出典件数を足して独立した研究数とはしない。

## カテゴリとサブカテゴリ

| カテゴリ | サブカテゴリ | 主な成果物・判断 |
| --- | --- | --- |
| 目的・構成・時間 | 聴衆と目的 | 誰のどの判断を助ける発表かを定める |
| 目的・構成・時間 | 構成・物語・根拠 | 主張、比較、経験、証拠を結び付ける |
| 目的・構成・時間 | 時間別の設計 | 1・2・3・5・10・15・30分と質疑枠を設計する |
| スライド・図表 | スライド設計 | 投影・配布・読み物に合わせて情報を配置する |
| スライド・図表 | 科学図表・数式 | 分布、独立性、不確実性、仮定を伝える |
| 話し方・質疑・練習 | 声・間・身体・チーム | 説明と画面、視線、役割交代をそろえる |
| 話し方・質疑・練習 | 質疑応答 | 質問に直接答え、根拠と未確認範囲を示す |
| 話し方・質疑・練習 | 理解確認とリハーサル | 初見の理解、尺、本番環境から修正する |
| ビジネスピッチ | 資金調達 | 投資判断に必要な事業・進捗・チーム・資金使途を示す |
| ビジネスピッチ | 顧客デモ・社内提案 | 導入や予算・試行の意思決定を助ける |
| 研究プレゼン | 学会・研究成果の口頭発表 | 問い、貢献、方法、結果、解釈、範囲を論証する |
| 研究プレゼン | 進捗報告・論文紹介 | 次の研究判断と、論文の主張の批判的検討を進める |
| 研究プレゼン | ポスター | 短い入口から図と対話へ進める |
| 研究プレゼン | 学位・資格審査 | 貢献、方法の選択、担当、技術質問を説明する |
| 研究プレゼン | 一般向け研究紹介・3MT | 専門外向けに研究を伝え、競技固有の媒体規則を守る |
| 研究プレゼン | 研究費・研究計画 | 支援の理由、実行可能性、予備的根拠、リスクを示す |
| ハッカソン・デモ・動画・音 | 一般ソフトウェア大会 | 大会別の審査と、動作・技術難所・完成範囲を対応させる |
| ハッカソン・デモ・動画・音 | LLM事業者・専門分野の大会 | モデルの貢献とドメイン知識を利用者の成果へつなぐ |
| ハッカソン・デモ・動画・音 | 実演・録画・編集・音楽 | 入力から結果を見せ、音声・字幕・BGMと障害時の切替を設計する |
| 言語・文化・アクセシビリティ | 多言語・文化・伝達条件 | 国籍で決め付けず用語・単位・字幕・習熟度へ適応する |
| 事例分析・調査 | TED・講演分析 | 発話・構成・背景から工夫を取り出し、映像観察と区別する |
| 事例分析・調査 | 募集・講評・受賞者調査 | 版と賞を照合し、公開事実・自己申告・推論を区別する |

## このチャットの依頼と保存先

| 依頼・議論 | 分類・参照先 |
| --- | --- |
| スライド、構成、内容、話し方、動画、音楽 | 目的・構成／視覚／話し方／デモ映像と音。基礎調査の7資料へ対応 |
| オーディエンスとTPO、1・2・3・5・10・15・30分 | 聴衆と目的、時間別設計、資金調達、顧客・社内提案 |
| Codexの学生大会、LLMで新しくできること、APIの価値 | LLM事業者・専門分野大会。開発利用・実行時利用・明文条件を分ける |
| なぜ自分たちか、ドメイン知識 | 構成・根拠と専門大会。経験が変えた制約・評価・実装を示す |
| 有名なTEDと文字起こし | TED・講演分析。6講演の個別資料、比較、公式日英字幕への入口 |
| 多言語の資金調達ピッチ | 資金調達と多言語。6言語の原語助言、面談・証拠・依頼 |
| 技育などの大会、受賞者の特徴 | 一般ソフトウェア大会と募集・受賞者調査。9作品と41出典 |
| Anthropic・専門家を募る大会、指定チャット全体 | 専門大会と事例調査。指定チャットの分析、10開催回、25作品 |
| 研究プレゼン | 学会、進捗・論文紹介、ポスター、審査、一般向け、研究費＋科学図表 |
| 独立ディレクトリと再利用可能なskills | リポジトリ直下のこの資料集を維持し、分類に対応するモジュールを追加 |

この表は会話の論点の対応表で、非公開チャットの逐語転載ではない。指定された別チャットの確認範囲は [分析記録](domain-hackathons/01-japan-and-chat.md) に残している。

## 全51文書の主分類

主分類は保存先を一つに決めるためのもの。複数の用途に使う資料にはcatalog.jsonで関連分類を付け、スキルから必要な箇所へ直接参照する。

### 目的・構成・時間

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [README.md](README.md) | 聴衆と目的 | 既存の全分野への入口。用途別と横断技法別の二つの経路を加える対象。 |
| [research/2026-11-06/01-audience-and-structure.md](research/2026-11-06/01-audience-and-structure.md) | 聴衆と目的 | 聴衆の判断を起点に冒頭・構成・証拠・結びを選ぶ基礎。 |
| [research/2026-11-06/README.md](research/2026-11-06/README.md) | 聴衆と目的 | 基礎調査の索引と、研究・助言・大会条件・制作案の区別。 |
| [by-duration/01-short-pitches.md](by-duration/01-short-pitches.md) | 時間別の設計 | 1・2・3・5分の役割・連続時間案。枚数や秒数は制作案。 |
| [by-duration/02-long-presentations.md](by-duration/02-long-presentations.md) | 時間別の設計 | 10・15・30分の説明と会話。面談全体と本編のみの時間を区別。 |
| [by-duration/03-purpose-and-rehearsal.md](by-duration/03-purpose-and-rehearsal.md) | 時間別の設計 | 資金調達・顧客・社内の目的で尺を再配分し、計時と初見理解で調整。 |
| [by-duration/README.md](by-duration/README.md) | 時間別の設計 | 7つの時間枠の入口。速度を上げるより、判断に不要な詳細を外す。 |

### スライド・図表

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [research/2026-11-06/02-slides-and-evidence.md](research/2026-11-06/02-slides-and-evidence.md) | スライド設計 | 主張見出し、近接、強調、冗長性。実験の精密な適用範囲は新しい研究発表資料を併読。 |
| [academic-presentations/02-slides-and-figures.md](academic-presentations/02-slides-and-figures.md) | 科学図表・数式 | MRIの110人実験を結果指標別に限定。分布、対応、反復、SD/SE/CIと数式。 |

### 話し方・質疑・練習

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [research/2026-11-06/03-delivery-and-questions.md](research/2026-11-06/03-delivery-and-questions.md) | 声・間・身体・チーム | 声・身体・質疑・チームの練習。7/38/55や10/20/30の普遍化を避ける。 |
| [research/2026-11-06/07-production-workbook.md](research/2026-11-06/07-production-workbook.md) | 理解確認とリハーサル | 主張と画面の対応、なぜ自分たちか、比較、初見理解の検証用シート。 |
| [academic-presentations/04-delivery-questions-language.md](academic-presentations/04-delivery-questions-language.md) | 質疑応答 | 図の解読、未検証への応答、英語の準備負担、字幕・遠隔、補足資料。 |

### ビジネスピッチ

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [fundraising/01-investor-pitch-playbook.md](fundraising/01-investor-pitch-playbook.md) | 資金調達 | 段階別の証拠、顧客・市場・競争・事業・進捗・調達使途。架空数字と実績を分ける。 |
| [fundraising/03-practice-and-templates.md](fundraising/03-practice-and-templates.md) | 資金調達 | 面談、依頼、進捗・数値の定義、質疑と練習。文章作成は外部送信の許可を含まない。 |
| [fundraising/README.md](fundraising/README.md) | 資金調達 | 投資家ピッチの入口。短い登壇・面談・単独で読むデックを区別。 |

### 研究プレゼン

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [academic-presentations/01-purpose-and-structure.md](academic-presentations/01-purpose-and-structure.md) | 学会・研究成果の口頭発表 | 7つの研究の場を区別。理論・定性を含む貢献ごとに証拠と適用範囲を選ぶ。 |
| [academic-presentations/03-formats-and-posters.md](academic-presentations/03-formats-and-posters.md) | ポスター | 口頭・進捗・論文紹介・ポスター・審査・3MT/MT180の規則を分ける。 |
| [academic-presentations/05-timing-and-workbook.md](academic-presentations/05-timing-and-workbook.md) | 学会・研究成果の口頭発表 | 本編のみ3・5・10・15・20・30分案、主張と根拠の表、研究としての評価設計。 |
| [academic-presentations/README.md](academic-presentations/README.md) | 学会・研究成果の口頭発表 | 研究発表7形式の入口。学術誌掲載の助言と効果実験を区別。 |

### ハッカソン・デモ・動画・音

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [pitch-demo-strategy.md](pitch-demo-strategy.md) | LLM事業者・専門分野の大会 | 本チャットのLLM/API・なぜ自分たちかの方針。Codex回の観察とClaude日本大会の条件を分離。 |
| [research/2026-11-06/04-demo-video-and-audio.md](research/2026-11-06/04-demo-video-and-audio.md) | 実演・録画・編集・音楽 | 入力から成果物、編集による省略、BGM研究の条件差、字幕・聞き取り。 |
| [research/2026-11-06/06-hackathon-and-case-studies.md](research/2026-11-06/06-hackathon-and-case-studies.md) | LLM事業者・専門分野の大会 | Codex/Gemini/Anthropicの条件・紹介から仮説を作る。後続の詳細調査へ接続。 |
| [hackathon-demos/01-events-and-judging.md](hackathon-demos/01-events-and-judging.md) | 一般ソフトウェア大会 | 技育祭/CAMP/博/展と開催年・段階、全体賞・企業賞、動作条件を区別。 |
| [hackathon-demos/02-demo-and-technical-depth.md](hackathon-demos/02-demo-and-technical-depth.md) | 一般ソフトウェア大会 | 一場面の入力→結果、制約→判断→実装→証拠。楽しさも価値である。 |
| [hackathon-demos/03-live-video-and-reliability.md](hackathon-demos/03-live-video-and-reliability.md) | 実演・録画・編集・音楽 | 実際の共有画面・機器、録画・字幕・BGM、代替手段、提出URLの再生。 |
| [hackathon-demos/04-scripts-and-questions.md](hackathon-demos/04-scripts-and-questions.md) | 一般ソフトウェア大会 | 1・2・3・5分の台本案、実装と期間内差分、質疑、制作シート。 |
| [hackathon-demos/README.md](hackathon-demos/README.md) | 一般ソフトウェア大会 | 一般ソフトウェア大会の入口。評価項目を確認できる動作へ変換。 |
| [domain-hackathons/01-japan-and-chat.md](domain-hackathons/01-japan-and-chat.md) | LLM事業者・専門分野の大会 | 指定チャットの全7ターンとガイドを再構成。最新認証フォームは未確認。 |
| [domain-hackathons/02-events-and-domain-expertise.md](domain-hackathons/02-events-and-domain-expertise.md) | LLM事業者・専門分野の大会 | 10開催回の目的と専門性。Research/Build、必須/トラック/特別賞/提供を分離。 |
| [domain-hackathons/04-demo-playbook.md](domain-hackathons/04-demo-playbook.md) | LLM事業者・専門分野の大会 | 経験→制約・評価→モデルとツール→利用者成果、比較計画と180秒の動作動画案。 |
| [domain-hackathons/README.md](domain-hackathons/README.md) | LLM事業者・専門分野の大会 | 専門分野・事業者大会の入口。募集目的と知識が効いた判断を示す。 |

### 言語・文化・アクセシビリティ

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [research/2026-11-06/05-language-and-culture.md](research/2026-11-06/05-language-and-culture.md) | 多言語・文化・伝達条件 | 国別類型の根拠の限界、訛りと理解、全文字幕、対象者への確認。 |
| [fundraising/02-language-and-context.md](fundraising/02-language-and-context.md) | 多言語・文化・伝達条件 | 6言語の原語助言を比較。言語差を国民性にせず、通貨・単位・定義をそろえる。 |
| [hackathon-demos/05-language-and-cases.md](hackathon-demos/05-language-and-cases.md) | 多言語・文化・伝達条件 | 6言語と本人の失敗記録。CORS/共有画面/PC障害と説明の作り直し。 |

### 事例分析・調査

| 資料 | 主なサブカテゴリ | 分析して残す要点 |
| --- | --- | --- |
| [research/2026-11-06/sources.md](research/2026-11-06/sources.md) | 募集・講評・受賞者調査 | 38出典の確認範囲。教育の学習効果を受賞・投資へ直接換算しない。 |
| [ted-talks/01-ken-robinson.md](ted-talks/01-ken-robinson.md) | TED・講演分析 | 逸話・会話・ユーモアと主張への復帰。19分の脱線量を短時間へ移さない。 |
| [ted-talks/02-simon-sinek.md](ted-talks/02-simon-sinek.md) | TED・講演分析 | 枠組み・対比・反復。生物学や成功の因果の正しさとは別評価。 |
| [ted-talks/03-brene-brown.md](ted-talks/03-brene-brown.md) | TED・講演分析 | 自己開示と仮説の変更。経験が設計判断を変えた場面へ応用。 |
| [ted-talks/04-hans-rosling.md](ted-talks/04-hans-rosling.md) | TED・講演分析 | 図の読み方を先に示し、変化を追う。平均と内部差・相関と因果を区別。 |
| [ted-talks/05-chimamanda-adichie.md](ted-talks/05-chimamanda-adichie.md) | TED・講演分析 | 複数の立場と自分の誤り。事実と集団を代表することを区別。 |
| [ted-talks/06-tim-urban.md](ted-talks/06-tim-urban.md) | TED・講演分析 | 擬人化の足場と終盤の転換。比喩を実際の脳機序としない。 |
| [ted-talks/comparison.md](ted-talks/comparison.md) | TED・講演分析 | 6講演の比較と短いピッチへの転用、観察事実と解釈の記録用シート。 |
| [ted-talks/README.md](ted-talks/README.md) | TED・講演分析 | TED/TEDxを区別した6講演の索引。字幕を読み、全編映像・音声の採点は未実施。 |
| [ted-talks/sources.md](ted-talks/sources.md) | TED・講演分析 | 公式の講演・日英文字起こし・本人の準備記録等。全文転載ではなく参照入口。 |
| [fundraising/sources.md](fundraising/sources.md) | 募集・講評・受賞者調査 | 6言語15出典。成功率や法的・財務的相場を算出する資料ではない。 |
| [by-duration/sources.md](by-duration/sources.md) | 募集・講評・受賞者調査 | YC等の原助言と独自の時間配分を分離。標準ルールとしない。 |
| [hackathon-demos/06-winner-patterns.md](hackathon-demos/06-winner-patterns.md) | 募集・講評・受賞者調査 | 9作品、8件は公式受賞と照合。非受賞対照なし・映像全編未採点。 |
| [hackathon-demos/sources.md](hackathon-demos/sources.md) | 募集・講評・受賞者調査 | 6言語41出典。要項・運営助言・参加記・README・受賞の確度を記録。 |
| [domain-hackathons/03-winners-and-counterexamples.md](domain-hackathons/03-winners-and-counterexamples.md) | 募集・講評・受賞者調査 | 25作品。22公式受賞＋3公式Finalist。反例で単純なAPI必須・自動化最大仮説を修正。 |
| [domain-hackathons/sources.md](domain-hackathons/sources.md) | 募集・講評・受賞者調査 | 37公開＋3提供資料。原チャット・認証情報の再配布を避け、取得の限界を保存。 |
| [academic-presentations/sources.md](academic-presentations/sources.md) | 募集・講評・受賞者調査 | 4言語26出典。実験・調査・図表解説・大学助言・特定制度の確度を区別。 |

## 横断して分かったこと

- 構成は相手の判断から選ぶ。資金調達の成長性、研究の根拠、デモの動作を同じ順序で説明する必要はない。
- 主張を強くするには、言い切りより比較条件と証拠が効く。計画・仮定・実測・解釈をそろえて管理する。
- 「なぜ自分たちか」は肩書だけでなく、経験によって選んだ制約・評価・実装で説明できる。
- LLM/APIの数やモデル名を価値と同一視しない。開発・利用・検証のどこに貢献したかを具体化する。
- TEDの説明技法は転用できるが、長い逸話の量、人気、拍手を短時間発表の正解や科学的正しさの証明にしない。
- 言語別の助言の違いは国民性を実証しない。制度、専門性、習熟度、字幕、用語、単位を先に調整する。
- 時間配分と練習は理解を確かめるために使う。1枚1分、固定の話速、反復回数を普遍的な合格基準にしない。

## 更新と根拠の限界

既存の学習研究の要約は、新しい研究発表資料の [110人実験の検討](academic-presentations/02-slides-and-figures.md) と併読する。結果指標による違い、複数の設計変更、対象者の範囲を維持する。

受賞者だけの分析には非受賞者の対照がなく、必勝法や勝率を求められない。TEDと受賞作品の資料は、字幕・文章・公開説明を中心とし、全編映像の視線・身振り・音楽を採点した記録ではない。今回のClaude日本大会の最新認証フォームは未確認。過去資料の募集条件は、実際の制作時に開催回・段階・賞を指定して確認し直す。

今回追加するスキルは、この分類から必要な資料を選び、実際の台本・図・デモ・質疑・レビューへ変換するための手順である。AIが代わりに行った調査・実験・動画視聴を装うためのものではない。

