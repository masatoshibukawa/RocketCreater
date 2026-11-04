# 09. どの資料から読むか

## 1. 日本語で基礎を固める

まず [デジタル庁のタイポグラフィ](https://design.digital.go.jp/dads/foundations/typography/)（S07）を読み、文字の役割をサイズ・太さ・行間・字間で整理する考え方を学びます。次に [ローカルデザインシステム](https://design.digital.go.jp/dads/guidance/local-design-system/)（S39）を入口に、色・余白・配置までルールの対象を広げます。

実例は [SANKOU!](https://sankoudesign.com/)（S30）から探し、日本語の見出し、写真と本文、長いラベルの扱いを自分で観察します。ギャラリー掲載を使いやすさの保証とは扱いません。

## 2. 8言語の入口

| 言語 | 最初に開く資料 | 読む問い |
| --- | --- | --- |
| 日本語 | [デジタル庁](https://design.digital.go.jp/dads/foundations/typography/)（S07） | 日本語の文字を役割別にどう定義するか |
| 英語 | [GOV.UK Paragraphs](https://design-system.service.gov.uk/styles/paragraphs/)（S08） | 本文、導入、補足をどう区別するか |
| フランス語 | [DSFR Espacement](https://www.systeme-de-design.gouv.fr/version-courante/fr/fondamentaux/espacement)（S09） | 余白が関係性と階層をどう示すか |
| ドイツ語 | [KERN Barrierefreiheit](https://www.design-system.gov.de/2.0.6/barrierefreiheit/)（S10） | 一時的・状況的な制約も含めて設計を考えられるか |
| スペイン語 | [MDN CSS基礎](https://developer.mozilla.org/es/docs/Learn_web_development/Core/Styling_basics)（S11） | 内容の構造と見た目の役割を分けられるか |
| 中国語 | [Ant Design 字体](https://ant.design/docs/spec/font-cn)（S12） | 業務画面で文字と数値をどう整理するか |
| 韓国語 | [KRDS Typography](https://www.krds.go.kr/html/site/style/style_03.html)（S14） | 役割別の文字トークンをどう運用するか |
| ポルトガル語 | [政府系V4 AlphaのTipografia](https://next-ds.estaleiro.serpro.gov.br/fundamentos/tipografia)（S16） | 行間と文字体系の違いをどう扱うか |

翻訳を使う場合も、原語の見出しと重要な数値、対象の版を一緒に残します。ポルトガル語資料はAlphaです。規則の採用時は安定版との関係を再確認してください。

## 3. 資料間で数値が違ったとき

デザインシステムには、対象、文章量、密度、書体、端末、組織の方針が反映されます。「一つのシステムが使うサイズ」と「Web全体のアクセシビリティ要件」を同一視しません。

判断の順序は、規格の適用条件 → 自分の対象と内容 → 実際の表示・操作 → チームが運用できるルール、を提案します。複数言語で同じ傾向が見えても、全員に最適だという実証にはなりません。

## 4. 目的別の深掘り

| 深めたいこと | 優先資料 |
| --- | --- |
| 文字と色の要件 | [W3C Contrast](https://www.w3.org/WAI/WCAG22/Understanding/contrast-minimum.html)（S02）、[Text Spacing](https://www.w3.org/WAI/WCAG22/Understanding/text-spacing.html)（S04） |
| 実装と可変レイアウト | [MDN Responsive web design](https://developer.mozilla.org/en-US/docs/Learn_web_development/Core/CSS_layout/Responsive_Design)（S17） |
| 科学・解析の図 | [Carbon Color palettes](https://carbondesignsystem.com/data-visualization/color-palettes/)（S40） |
| 書体の選定 | [Inter公式](https://rsms.me/inter/)（S21）、[Typewolf](https://www.typewolf.com/)（S29） |
| SFの世界観 | [Territory Studio](https://territorystudio.com/project/blade-runner-2049/)（S35）、[GMUNK](https://gmunk.com/OBLIVION-GFX)（S36） |
| AIと独自性 | [Doshi・Hauserの概要](https://arxiv.org/abs/2312.00506)（S37）、[NN/gの実務分析](https://www.nngroup.com/articles/state-of-ux-2026/)（S38） |
| 速度と安定性 | [Web Vitals](https://web.dev/articles/vitals)（S20） |

## 5. この調査で保留したこと

- 実例サイトの実機操作、ログイン後の状態、速度の比較。
- 書体を購入する場合のプランや価格比較。
- 各国のアクセシビリティ関連法への法的な適合判断。
- 「AI生成らしさ」を判定する検出器やスコア。
- 映画や商用サイトの画像・動画・書体の再配布。
- 既存アプリへの設計案の実装と、利用者テスト。

これらを調査済みと誤認しないようにします。今回の成果は、目的を定め、参考を調べ、試作し、検証するための出典付きの学習・制作資料です。
