# 02. 多言語の比較と探索方法

## 1. 探索した言語と内容

以下は検索・原資料の確認から整理したものです。各国の利用者の好みや、全モデルに共通する特徴の比較ではありません。

| 言語 | 見つかった議論・問題設定 | 対処として参考にした資料 |
| --- | --- | --- |
| 日本語 | 記号による強調、抽象語、比喩、前置きへの実務者の指摘。UIでは冗長さ・過剰な敬語・補足の多さを整理 | [C18 Zenn](https://zenn.dev/fibujrsl/articles/4958a844214709)、[C06 SmartHR](https://smarthr.design/products/contents/writing-style/) |
| 英語 | モデル間・人間との文体差、不確実性の表現、UIの説明過多 | [C01 研究](https://arxiv.org/html/2410.16107v2)、[C09 GOV.UK](https://www.gov.uk/service-manual/design/writing-for-user-interfaces) |
| フランス語 | AI文章の曖昧さ・反復の編集。公共文章では具体性、能動態、比喩の削減 | [C19 Microsoft](https://www.microsoft.com/fr-fr/copilot/ai-knowledge/humanize-ai-text)、[C15 政府ガイド](https://www.info.gouv.fr/marque-de-letat/comment-s-adresser-aux-citoyens) |
| ドイツ語 | Verständlichkeit、Einfache Spracheの文脈で、対象者と用途に合う文章・理解の確認 | [C14 Servicestandard](https://servicestandard.gov.de/handbuch/anleitungen/verstaendlich-schreiben-mit-einfacher-sprache/) |
| スペイン語 | lenguaje claroの文脈で、利用者に必要な内容、短い語・文・段落 | [C16 Argentina.gob.ar](https://www.argentina.gob.ar/contenidosdigitales/estandares/redactar-textos) |
| 中国語 | 文案の曖昧さ、過度な文雅さ、不要な語・句読点 | [C12 Ant Design](https://ant.design/docs/spec/copywriting-cn/) |
| 韓国語 | 意味のない語・文、画面内外の重複、作り手による背景説明の増やしすぎ | [C13 Toss](https://toss.tech/article/21022) |
| ポルトガル語 | linguagem simplesの文脈で、直接的な文、利用者になじむ語、用途に合う書き直し | [C17 gov.br](https://www.gov.br/pt-br/guia-de-edicao-de-servicos-do-gov.br/escrevendo-o-seu-texto) |

ドイツ語・スペイン語・ポルトガル語などの上記ガイドは、AIの文章だけを対象にした実証研究ではありません。AI出力を直す際にも応用できる編集方法として採用しました。

## 2. 実行した検索語の代表例

| 言語・領域 | 検索語 |
| --- | --- |
| 日本語 | 生成AI 文章 カギ括弧 多用 AIっぽい |
| 日本語・実務 | site.smarthr.design ライティング かぎ括弧 簡潔 未実装 |
| 英語・実務 | site.design-system.service.gov.uk writing user interfaces clear concise errors |
| 英語・研究 | site.arxiv.org language models excess vocabulary writing style hedging |
| 英語・多言語研究 | site.aclanthology.org multilingual style LLM-generated |
| フランス語 | texte IA tics langage grandiloquent comment éviter |
| ドイツ語 | KI Texte Floskeln blumige Sprache Anführungszeichen vermeiden |
| スペイン語 | textos IA muletillas lenguaje grandilocuente evitar |
| 中国語 | AI腔 过度 引号 空话 大模型 研究 |
| 韓国語 | AI 글쓰기 과장 표현 불필요 따옴표 |
| ポルトガル語・実務 | site.gov.br linguagem simples interface textos evite termos |

引用符・比喩・留保の話を区別し、実務ガイドは発行元、研究は著者の公開論文や学会・出版社の原ページを確認しました。検索語そのものを現象の発生証拠とは扱いません。

## 3. 採用時の注意

- 英語のquotation marksと、日本語のかぎ括弧、補足用の丸括弧は用途が異なる。規則をそのまま移さない。
- フランス語やスペイン語の単語数の目安を、日本語の文字数制限に変換しない。
- AIっぽさへの実務者の感想と、コーパス・実験に基づく知見を分ける。
- AI検出・文章の人間化を売るサイトは、独立した性能検証の代わりにしない。
- 文体の違いは、モデル、指示、対象ジャンル、言語、利用者の読み方に依存する。
- 全ての留保を削除するのではなく、内容の確かさに合う具体的な条件へ書き換える。

## 4. 確認の粒度と限界

出典台帳の `verification` は `page_text`（本文・該当節）、`abstract`（論文概要）、`practitioner_observation`（実務者自身の観察）を区別します。根拠の種類は `kind` に記録します。

原資料の全文、画像、翻訳の転載はしていません。本文中の書き換え例は、この調査から作成する独自の例であり、実在サイトの問題文を採取したコーパスではありません。

PMCの候補ページはブラウザ確認画面になったため根拠として採用せず、出版社と著者公開版を利用しました。取得できなかった情報を読了済みとして数えません。検索結果だけで得た候補のうち、根拠に採らなかったページは台帳へ水増ししていません。

今回、モデルを同じプロンプトで八言語比較する生成実験や、改善コピーの利用者テストは実施していません。スキルへの反映は、原資料の知見、今回のユーザー指定、実務上の判断を組み合わせたものです。
