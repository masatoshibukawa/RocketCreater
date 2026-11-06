# 受賞作品と、単純な勝ち筋では説明できない事例

確認日: 2026-11-07。指定チャットの20作品を引き継ぎ、海洋・宇宙の2受賞作と生命科学の3作品を加えた。**22件は主催者等の公式受賞表示を確認。追加の生命科学3件は公式Finalist表示を確認し、うち2件には本人の受賞報告がある。** この3件の正式順位・トラックは、取得できた主催者本文では確定していない。

作品説明と公開READMEによる比較であり、25本の動画を全編視聴した分析や、25アプリの動作検証ではない。以下の長所は、公開された仕組みを基にした分析である。

## Anthropic本体主催の3大会・14受賞作品

| 大会 | 作品・受賞 | 専門性・体験で注目する点 | 受賞根拠 |
| --- | --- | --- | --- |
| Opus 4.6 | CrossBeam／1位 | 法律・図面の問題を修正方針へつなぐ | D04 |
| Opus 4.6 | Elisa／2位 | 娘のための仕様・実装・テストの操作を作る | D04 |
| Opus 4.6 | PostVisit.ai／3位 | 臨床経験を診察後の理解支援へ使う | D04 |
| Opus 4.6 | TARA／Keep Thinking | 道路行政の知識を投資判断用の報告へ使う | D04 |
| Opus 4.6 | Conductr／Creative Exploration | 演奏に応じた編曲で表現を広げる | D04 |
| Opus 4.7 | Medkit／1位 | 医療を学ぶ人の模擬診療と評価 | D05 |
| Opus 4.7 | Wrench Board／2位 | 修理現場の測定と仮説更新を支援 | D05 |
| Opus 4.7 | Maieutic／3位 | 学生自身が仕様とコードを説明する | D05 |
| Opus 4.7 | Virtual Puppet Theater／Most Creative Use | 声と動きで親子の遊びを作る | D05 |
| Opus 4.7 | MaestrIA／Keep Thinking | 職人への聞き取りを判断と評価へ使う | D05 |
| Opus 4.7 | ARIA／Best Managed Agents | 保全の知識を異常診断と作業指示へつなぐ | D05 |
| Opus 4.8 | Tekton／1位 | 3Dの部品から資料の根拠を辿る | D06 |
| Opus 4.8 | Sim Francisco／2位 | 合成住民の応答を地域別に扱う | D06 |
| Opus 4.8 | Custom Universe／3位 | ロボティクスの環境作成を操作へ落とす | D06 |

出典: [Opus 4.6](https://claude.com/resources/articles/meet-the-winners-of-our-built-with-opus-4-6-claude-code-hackathon)、[Opus 4.7](https://claude.com/resources/articles/meet-the-winners-of-built-with-opus-4-7-claude-code-hackathon)、[Opus 4.8](https://claude.com/resources/articles/meet-the-winners-of-our-claude-opus-4-8-build-day-hackathon)。

主催者は4.6の受賞者5人中4人を職業開発者ではないと紹介している。それは、技術経験やプログラミング経験が全くなかったという意味ではない。全大会で非エンジニアが有利になるとの統計にもならない。

## 学生大会の6受賞作品

Columbia X NYUは補助比較とする。Anthropic本体主催の上記シリーズと同一の募集・審査とは扱わない。個別順位は付けない。[公式ギャラリー](https://claude-hackathon-2026.devpost.com/project-gallery)

| 作品・受賞表示 | 利用者に渡すもの | 確認範囲・限界 |
| --- | --- | --- |
| [NestIn／Claude Track](https://devpost.com/software/nestin) | 引っ越し先の必要品・購入候補 | 作品説明。実購入や価格精度は再現していない |
| [AgentOS／Claude Track](https://devpost.com/software/agentos-pwib10) | AI担当者を選び接続・起動する導線 | 作者はデモの範囲を起動までとしている。業務遂行は次の段階 |
| [Grey Matter／Claude Track](https://devpost.com/software/grey-matter-l3e4ap) | 動画の予測神経応答から改善を説明 | TRIBE V2の予測。実際の視聴者の脳計測とは違う |
| [CityPulse／Linkup Challenge](https://devpost.com/software/citypulse-mcg12l) | 住宅政策の想定変化と地域別の説明 | 加算的なヒューリスティック。政策の因果効果を実証していない |
| [Pulse／Linkup Challenge](https://devpost.com/software/pulse-tgiz8u) | 地域のリスクと支援計画を可視化 | 模擬データと重み付け。現実の予測・派遣を確認したものではない |
| [Clauduck／Linkup Challenge](https://devpost.com/software/clauduck) | 講義資料との対話と予習・復習 | 学習効果は独立検証していない |

主催者ギャラリーのWinner表示と、作品ごとの賞名を照合した。Pulseの取得本文からはClaudeの具体的な役割を確認できない。受賞している事実を「全作が同じ方法でClaude APIを活用した」という主張に置き換えない。[D18〜D24](sources.md)

## 海洋・宇宙の2受賞作品

| 作品・受賞 | 確認できる良さ | デモへ応用する案 |
| --- | --- | --- |
| FeedRight／Ocean Hackathon 2025国際決勝1位 | CEMACSの養殖研究と、給餌・水質の課題を技術へ結び付けた。大学は科学的な堅牢さ等が評価されたと紹介 | 観測 → 判断 → 現場で取る行動を一件で示す。削減率等は測定済みの範囲で説明 |
| SpaceGenes+／NASA Space Apps 2025 Best Use of Science | 放射線と微小重力の組み合わせを、研究者が調べられるダッシュボードにした | データ、比較条件、見つかる変化を見せ、実験や医学的結論と区別 |

出典: [USM CEMACS](https://cemacs.usm.my/about-us/latest-news/241-cemacs-led-innovation-secures-malaysias-win-at-ocean-hackathon-r-2026.html)、[NASA公式発表](https://www.nasa.gov/learning-resources/stem-engagement-at-nasa/nasa-announces-2025-international-space-apps-challenge-global-winners/)。後者は受賞紹介を確認したが、今回、個別作品ページの取得は502で失敗した。細かな計算方法を取得成功したかのように補っていない。

## 生命科学の3追加事例

| 作品 | 公式表示と受賞情報の確度 | 専門知識が効く点 | 確認の限界 |
| --- | --- | --- | --- |
| [Lazarus](https://cerebralvalley.ai/e/built-with-claude-life-sciences/hackathon/gallery/50) | 公式Finalist。作者Dean Sherryが受賞を報告 | 動かない研究コードを復旧し、実行成功と論文の結果の再現を分ける | 作者の報告・公開実装の説明。ベンチマークは再実行していない |
| [NCypher](https://cerebralvalley.ai/e/built-with-claude-life-sciences/hackathon/gallery/74) | 公式Finalist。取得した主催者本文では賞・順位未確定 | 分野と細胞の文脈に合う根拠を使い、候補と不確実性を返す | 研究候補選びの道具。臨床有効性の確認ではない |
| [Extremolith](https://cerebralvalley.ai/e/built-with-claude-life-sciences/hackathon/gallery/211) | 公式Finalist。作者Jaymin Patelが2位を報告。トラック未確定 | データ・学習・検査の研究工程をClaudeで進める | 7月19日の作者記事はWeb画面がサンプル出力と明記。実験検証は今後 |

出典: [Lazarus作者の報告](https://www.linkedin.com/posts/dean-sherry-phd-46652315b_github-doctordeanlazarus-an-agent-that-activity-7483587303781646337-689u)、[NCypher README](https://github.com/faith-ogun/ncypher/blob/main/README.md)、[Extremolith作者の記事](https://www.linkedin.com/pulse/explaining-my-build-claude-science-project-jaymin-patel-fwslc)。公式ギャラリーの数値14・9・4等は順位として数えていない。Finalist7件を自動的に受賞7件とも数えていない。

この3例からは、再現手順、反証できる成功条件、適用範囲を説明することも見せ場になると考えられる。研究トラックの成果物を、日本大会の実動作要件の代替に使うことはできない。

## 特に取り入れたい工夫

以下の「取り入れ方」はこちらの提案である。受賞記事の記述から、当該工夫に何点が付いたかは分からない。

### CrossBeam：方向転換の理由に、現場知識がある

第4弾インタビューでは、図面を直接変える案の問題を認識し、自治体側に確認して修正通知へ重点を移した経緯が語られる。[U03](sources.md)

取り入れるなら「最初の案 → 現場で分かった不足 → 今の設計」という短い説明にする。苦労話の長さより、判断が良くなった理由を示す。

### Wrench Board：推論の変化を、対象物の上に置く

修理の測定と仮説更新が核である。現在のREADMEでは、対象部品の照合や決定的なエンジンも説明される。現在のモデル・機能を受賞時へ遡らせない。[README／D25](sources.md)

取り入れるなら、どの対象を調べ、どの観測で候補が変わったかをハイライトする。重要なのは判断に必要な根拠である。

### MaestrIA：経験を、知識と評価へ変換する

主催者記事は、父への聞き取りを構造化し、父の判定を使う評価を作ったと紹介する。[D05](sources.md)

取り入れるなら、専門家から得た一つの制約を、知識を入れる前後で比較する。評価者と知識提供者が同一なら、その一致が外部への一般化を保証しないことも示す。

### ARIA：見える診断と、使える指示をつなぐ

公開READMEはシミュレーターと故障注入を説明し、データからエージェントと画面への接続を示している。[README／D26](sources.md)

取り入れるなら、入力した異常と、根拠を含む成果物を対応させる。シミュレーションを実工場の予知実績へ言い換えず、仕組みを検証する実演として使う。

### Tekton：3Dの見栄えに、出典と検査を結ぶ

現在のREADMEは固定成果物を表示し、実行時のサイトはLLMを呼ばないと説明する。生成・検証と表示の役割が分かれている。[README／D27](sources.md)

取り入れるなら、部品を選ぶと根拠を辿れ、意図的に壊した条件を検査で止められる構成にする。これは現在の公開設計の参考であり、受賞時にAPIを使っていなかったとの証明にはしない。

### Conductr：AIに任せる時間尺度を選ぶ

READMEでは、Claudeによる編曲判断とWASMによる音符生成を分け、APIが使えない時のルールベース動作も説明している。[README／D28](sources.md)

取り入れるなら、判断・計算・描画の役割を分け、必要な時にだけAIを呼ぶ。回数より、体験の変化と応答を示す。代替処理で収録した部分は、その条件が分かる形にする。

## 比較によって修正される仮説

- **自動化の量が最大なら良い、とはならない。** Elisaは作る能力を渡し、Maieuticは学ぶ人の思考を残す。目指す利用者の変化が異なる。
- **業務効率化だけが価値ではない。** Conductrと人形劇は、表現・遊びの体験を示す。
- **専門家の肩書だけでは説明できない。** どの知識が仕様・データ・評価を変えたかを追う必要がある。
- **すべての処理をLLMへ任せる必要はない。** 計算や時間制約の厳しい処理との分担が参考になる。
- **受賞と、実利用での有効性は別の確認である。** 模擬データ、予測、部分実装、受賞後の変更を区別する。
- **受賞者比較は必勝法の証明にならない。** 不採用作品の同条件比較、採点内訳、審査員の理由が揃っていない。

企画時には「自分たちには、何を良い結果と判断できる根拠があるか」を問う。この根拠を利用者に渡せる操作と成果物へ変える。
