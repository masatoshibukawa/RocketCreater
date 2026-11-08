# デモ動画の一次出典と確認範囲

確認日: 2026-11-07。制作ガイド7件と事例資料9件、合計16の出典記録。同じ企業やページの再利用を独立した効果研究とは数えない。

## 制作のガイド

| ID | 出典 | 確認した内容と範囲 |
| --- | --- | --- |
| G01 | [Devpost：Video-making best practices](https://help.devpost.com/article/84-video-making-best-practices) | 本文。画面収録＋説明、冒頭、台本、編集、アップロード。審査・評価向けの助言 |
| G02 | [YC：The Application Video](https://www.ycombinator.com/video) | 本文。創業者が話す1分の応募動画と、別欄の製品デモを区別。デモの一般ルールへ転用しない |
| G03 | [TechSmith：How to Make a Product Demo Video](https://www.techsmith.com/blog/make-demo-video/) | 目的、概要と詳細手順の分離、台本、録画、後録り、編集。ツール企業の実務助言 |
| G04 | [TechSmith：How to Storyboard a Video](https://www.techsmith.com/blog/how-to-storyboard-a-video/) | 画面状態、操作、ナレーション、注釈とレビューを対応。2026-09-02公開表示。主に職場向け教材 |
| G05 | [W3C：Audio Content and Video Content](https://www.w3.org/WAI/media/av/av-content/) | 音質、背景音、平易な文、処理する時間、視覚情報の説明。制作ガイドと基準の適用範囲を区別 |
| G06 | [W3C：Captions/Subtitles](https://www.w3.org/WAI/media/av/captions/) | 発話・必要な音情報の同期、自動字幕の確認、配置。同言語字幕と翻訳を区別 |
| G07 | [Devpost：6 Tips for making a winning hackathon demo video](https://info.devpost.com/blog/6-tips-for-making-a-hackathon-demo-video) | 参加者の助言を含む。台本、入力と動作、聞き取り、準備・公開設定。勝率効果を検証した研究ではない |

## 事例の根拠

| ID | 出典 | 確認した内容と範囲 |
| --- | --- | --- |
| C01 | [Figma：Multiplayer Editing in Figma](https://www.figma.com/blog/multiplayer-editing-in-figma/) | 2016-09-28の本文と埋込4短編。本文が説明するカーソル、選択、アバター、追従、端末への反映 |
| C02 | [Apple：Introducing Apple Vision Pro](https://www.apple.com/newsroom/2023/06/introducing-apple-vision-pro/) | 2023-06-05の本文。gestures・multitaskingの公開MP4のフレームを確認。長編紹介動画の全編観察ではない |
| C03 | [Hyundai：An Electric New Era for Atlas](https://www.hyundai.com/worldwide/en/newsroom/detail/an-electric-new-era-for-atlas-0000000752) | 2024-04-22の配布MP4。ページの0:31表記と取得版23.00秒を区別 |
| C04 | [Boston Dynamics：All New Atlas](https://www.youtube.com/watch?v=29ECwExc-_M) | 公式チャンネルのタイトル・公開日2024-04-17・説明。YouTube版の全編映像・音声を取得したわけではない |
| C05 | [Google Developers：How it’s Made—Interacting with Gemini](https://developers.googleblog.com/en/how-its-made-interacting-with-gemini-through-multimodal-prompting/) | 2023-12-06の本文と入力例、タイマーの結果短編。Hands-on制作における画像・文字の組合せも説明。長編の全編評価は未実施 |
| C06 | [Anthropic：2024年Computer Use発表](https://www.anthropic.com/news/3-5-models-and-computer-use) | 2024-10-22。指示、複数の道具、フォーム入力等の公式説明と動画リンク。現在の能力へ一般化しない |
| C07 | [Anthropic：Developing a computer use model](https://www.anthropic.com/news/developing-computer-use) | 画面の取得・操作と限界。動画編集の観察根拠にはしない |
| C08 | [Claude：Computer use for automating operations](https://www.youtube.com/watch?v=ODaHJzOyVCQ) | 公式ページの埋込参照とタイトルを確認。本文抽出では全編・字幕を取得できず、カット順・声・音楽を採点しない |
| C09 | [Nintendo：Switch world premiere／2016-10-20](https://www.nintendo.com/en-gb/News/2016/October/Nintendo-Switch-world-premiere-demonstrates-new-entertainment-experiences-from-a-home-gaming-system-1148687.html) | 当時の公式発表の本文。携帯、場所、人数、コントローラーの利用場面。元動画の全編は未観察 |

## 映像観察の方法

公式HTMLが参照する8ファイルを取得し、短い2ファイルは1秒間隔、残りは2秒間隔で静止フレームを抽出して比較した。メタデータから長さと音声トラックの有無も確認。対象URL、ファイルSHA-256、採取位置は [media-observations.json](media-observations.json) に残す。原映像・抽出画像の再配布はしていない。

静止フレームで確認できるのは画面内容と粗い変化である。細かな動きの滑らかさ、正確なカット点、連続実行、音質、声の調子、BGMの効果をこの方法だけで採点しない。取得ファイルと現在のYouTube版が同一であるとも断定しない。

ブラウザ再生はWorkの設定により無効だった。長時間調査ツールは認証要求を受理したとの応答を繰り返し、調査回答・response IDを取得できなかった。認証後の一度の再試行で停止し、公開ページの直接検索・取得で調査を続けた。成功した長時間調査の回答を参照したとは記録しない。

[調査の入口](README.md)へ。
