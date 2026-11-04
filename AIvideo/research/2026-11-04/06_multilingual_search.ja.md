# 多言語で探索した動画制作手法

日本語、英語、中国語、韓国語、フランス語、スペイン語、ドイツ語で検索した。採用した資料は、モデル開発者、ソフトウェア開発元、制作を担当したVFX会社の一次資料を中心とする。資料の説明言語と、モデルが受け付ける入力言語は区別している。

## 言語と主な検索語

以下は実際に使った検索語の抜粋。全検索結果の保存や、網羅的な文献レビューではない。

| 言語 | 検索語の例 | 読んだ一次資料と得られた内容 |
| --- | --- | --- |
| 日本語 | `AI 動画生成 写実 ComfyUI Wan 2.2 公式 日本語` | [Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2)の日本語導入説明と声モデル規約 |
| 英語 | `AI video generation cinematic photorealistic LTX-2 HunyuanVideo official` | Wan、LTX、Runway、ILM、Framestoreの機能と制作工程 |
| 中国語 | `混元视频 1.5 本地 部署 官方 README_CN` | [Hunyuan中国語README](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5/blob/main/README_CN.md)の実行条件と更新 |
| 韓国語 | `AI 영상 제작 시네마틱 렌더링 site:dev.epicgames.com/documentation/ko-kr` | [Epic韓国語資料](https://dev.epicgames.com/documentation/ko-kr/unreal-engine/cinematic-render-settings-and-formats-in-unreal-engine)のレンダリング設定。表の一部は英語 |
| フランス語 | `génération vidéo Veo guide requêtes site:cloud.google.com` | [Googleフランス語ガイド](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/video/video-gen-prompt-guide?hl=fr)のプロンプト構成 |
| スペイン語 | `vídeo IA cinematográfico guía oficial Runway` とFireflyの追加検索 | [Adobeスペイン語資料](https://helpx.adobe.com/es/firefly/web/work-with-audio-and-video/work-with-video/generate-videos-using-text-prompts.html)のモデル選択と動画生成 |
| ドイツ語 | `KI Video generieren Kamerabewegung site:helpx.adobe.com/de` | [Adobeドイツ語実習](https://helpx.adobe.com/de/firefly/how-to/video-motion-reference.html)のカメラ移動参照 |

追加で、各モデル名と `VRAM`、`offload`、`license`、`README`、`Windows`、`本地 部署`、`音效 语音` 等を組み合わせ、公式リポジトリやモデルカードへ進んだ。検索だけで見つけた非公式ブログ、ミラー、コミュニティ投稿の主張は、機能や性能を確定する根拠には使っていない。

## 言語をまたいで確認した差分

- **英語と中国語のHunyuan:** 同じ開発元の資料として照合した。中国語READMEの4090向け高速化例を、このPCでの速度測定とは扱わなかった。
- **ComfyUIと公式PythonのWan:** 同じ5Bでも、オフロード方式と実行系が異なるため、8GBと24GBの記載を一つの最低要件へ統合しなかった。
- **韓国語のUnreal:** 非推奨の旧Render Movie記事も検索で見つかったため、採用資料にはMRQ/MRGの現行設定を選んだ。
- **フランス語と英語のGoogle:** プロンプト設計と、APIモデルの提供状況を別ページで確認した。翻訳資料が存在しても日本語プロンプトの仕様を保証しない。
- **ドイツ語とスペイン語のAdobe:** カメラ参照の実習と生成UIの説明を併用した。別言語の同じ提供元を、独立した品質評価二件とは数えない。

各差分の出典は [資料一覧](07_sources.ja.md) のV01〜V16、X03、X04にまとめている。

## 事実と提案の扱い

| 区分 | 資料内での扱い |
| --- | --- |
| 公式仕様 | 該当URLと条件を添える。メーカーの品質表現を客観的な順位に置き換えない |
| 実機確認 | environment.jsonに記録。日時と確認範囲を限定する |
| 推奨と制作案 | PC仕様との照合、または創作上の提案として記載する |
| 未確認 | 生成時間、ピークVRAM、実際の画質、独自保存先の既存モデル等を未測定とする |

## 取得できなかった資料と扱い

| URLや対象 | 発生したこと | 扱い |
| --- | --- | --- |
| Blender公式manualのtracking introduction、最新と4.5 | ブラウズ取得が402で失敗 | 手順本文は検証できていない。具体的操作の根拠には採用せず、合成は取得できたFusionとEpicの資料を中心にした |
| Blender公式VFX紹介ページ | 同じく402 | 別のモデル評価で代替したと見なさない |
| FFmpegのffmpeg.html | タイムアウト | 取得できたffmpeg-filters.htmlのamix、loudnormを音声編集の根拠に採用 |
| LTX-2.5モデル配下で推測したLICENSEパス | 404 | モデルカードの正規リンクからLTX-2リポジトリのLICENSE-2_x本文を取得し直した |

取得失敗はサイトに資料が存在しないことを意味しない。アクセスできなかった手順について、検証済みと記録しない。

## 次回の調査で更新する項目

実際にモデルを導入したら、公式テンプレートでの生成結果、処理時間、ピークVRAM、日本語の読み、採用までの試行回数を追加する。次の調査は新しい日付ディレクトリへ置き、この時点の要件と結果を上書きしない。
