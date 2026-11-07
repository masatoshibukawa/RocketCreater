# 日本語AIナレーション：無料・ローカル制作の調査

確認日：2026年11月7日（JST）。対象はRocketWrightの約3分の日本語デモ。自然さ、専門語の読み、同じ声の維持、尺の調整、公開条件、透かしを比較した。日本語・英語の公式文書、モデルカード、開発元の実装を参照した。

**制作上の提案は、まずAivisSpeechとVOICEVOXで日本語の編集しやすさを比較し、SFらしい声質・演技を狙う候補としてQwen3-TTS 1.7Bを加えること。** 実機での品質順位ではない。今回の作業は調査とスキルへの整理で、新しい音声エンジンの導入、モデル取得、追加の音声合成、動画の差し替えは行っていない。

## 候補の比較

「無料」は主にローカル合成時のサービス利用料を指す。電気・機材・ダウンロードの費用を含む保証ではない。

| 候補と対象 | 日本語での使いどころ | 実行・無料の範囲 | 公開条件と今回の判断 |
| --- | --- | --- | --- |
| AivisSpeech / AivisSpeech Engine | 文ごとの話者・感情・速度・読みを編集。デモの主ナレーター候補 | Windows/macOSのローカルアプリ。初回のモデル取得後はオフライン利用可。CPU経路あり | 本体は無料でクレジット不要。音声モデルの規約は別。ACMLとACML-NCを混同せず、採用モデルの商用条件を確認 |
| VOICEVOX / VOICEVOX ENGINE | 読みとアクセントを手動修正しやすい。安定した説明音声の候補 | Windows等のローカル。CPU版あり | クレジットが必要。各音声ライブラリの条件も適用。概要欄に表記できるため、常時画面にロゴを重ねる必要とは異なる |
| Style-Bert-VITS2 JP-Extra系 | 日本語のスタイル調整や自作話者。AivisSpeechより直接モデルを扱いたい場合 | Windows公式手順、CPU合成対応。学習済みモデルで試せる | ソフトと個別話者の条件は別。既定モデルも同じ規約ではない。学習やモデル管理まで必要なときの候補 |
| Qwen3-TTS-12Hz-1.7B-CustomVoice / VoiceDesign / Base | 日本語を含む多言語。1.7Bの演技指示、声の設計、許諾済み録音を使う複製 | ローカル。Python専用環境とモデル取得が必要 | 対象CustomVoiceカードはApache-2.0。役割と重みを区別する。今回のPCでの推論時間・品質は未測定 |
| Kokoro-82M | 小型モデルによる短い読み上げ。軽い比較対象 | ローカル。日本語には対応する前処理と話者が必要 | 重みはApache-2.0。日本語話者一覧には話者別のCC BY参照もある。小型であることだけで日本語品質を最上位としない |
| ElevenLabs TTS | 設定・導入の手間を小さくしたクラウド比較 | 無料枠と有料契約がある。ローカル実行とは別 | 無料枠は非商用・帰属表示付き。今回の無料の製品紹介用として初期採用しない。公式は不可聴の透かしも説明 |
| Chatterbox Multilingual | 日本語対応、多言語と感情制御の比較対象 | ローカル、MIT表示 | 公式がPerThの不可聴透かしを説明。透かしを避ける条件に無条件では合わない |
| Fish Audio S2-Pro | 日本語や表現制御の比較対象 | 自前推論の経路あり | S2-Pro重みはResearch Licenseで非商用向け。商用は別ライセンス。無料の製品紹介への初期採用から外す |

根拠：[AivisSpeech](https://aivis-project.com/AivisSpeech)、[Aivis FAQ](https://aivis-project.com/faq)、[VOICEVOX規約](https://voicevox.hiroshiba.jp/term/)、[VOICEVOX Q&A](https://voicevox.hiroshiba.jp/qa/)、[Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2)、[既定モデル規約](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md)、[Qwenモデルカード](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)、[Kokoroモデルカード](https://huggingface.co/hexgrad/Kokoro-82M)、[Kokoro話者一覧](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)、[ElevenLabs利用条件の説明](https://elevenlabs.io/docs/overview/administration/billing)、[Chatterbox](https://github.com/resemble-ai/chatterbox)、[Fish Audio S2](https://fish.audio/ja/s2/)。

## 透かしとクレジットは分ける

画面ロゴ、聞こえる宣伝音、不可聴の識別情報、利用時のクレジットは別の項目である。音声だけの素材でも不可聴透かしは存在し得る。

- VOICEVOX：公式Q&Aは動画内または概要欄へのクレジットを案内する。話者ごとの指定も確認する。
- AivisSpeech：本体のクレジットは任意。モデルのクレジット不要と商用利用可能は別条件で、ACML-NCを商用可としない。
- Chatterbox：READMEが生成音声へのPerTh埋込みを明記。
- ElevenLabs：Audio Detectorの説明が不可聴透かしを明記。
- AivisSpeech、VOICEVOX、Qwen3-TTS、Kokoro：今回参照した文書から、強制的な画面ロゴや宣伝音を付ける要件は確認しなかった。ただし全配布物の不可聴透かしの不存在を検証したわけではない。採用する具体的なアプリ・重み・話者と、短い生成素材で再確認する。

出典：[VOICEVOX Q&A](https://voicevox.hiroshiba.jp/qa/)、[Aivis FAQ](https://aivis-project.com/faq)、[Chatterbox Watermarking](https://github.com/resemble-ai/chatterbox#built-in-perth-watermarking-for-responsible-ai)、[ElevenLabs Audio Detector](https://elevenlabs.io/docs/eleven-creative/audio-tools/audio-detector)。透かしの削除を制作手順には含めない。

## 実装上の違い

**AivisSpeechとVOICEVOX。** 両者はローカルHTTP APIを使える。AivisSpeech Engineは通常10101、VOICEVOX ENGINEは通常50021で、実際の起動設定を優先する。`/speakers`でスタイルを調べ、`/audio_query`からクエリを作り、`/synthesis`でWAVにする。AivisSpeechのスタイルIDを例の固定値で決めない。

AivisSpeechの`intonationScale`はVOICEVOXの全体抑揚と同じ意味ではなく、感情表現の強さに対応する。`pauseLength`等、互換フィールドでも無視されるものがある。VOICEVOX用のクエリ編集やモーラ単位の長さ指定を、そのままAivisSpeechに持ち込まない。これは自動化で音が不自然になる原因になり得る。[AivisSpeechのAPIと互換性](https://github.com/Aivis-Project/AivisSpeech-Engine#音声合成-api-を使う)、[VOICEVOX ENGINEの例](https://github.com/VOICEVOX/voicevox_engine#音声を調整するサンプルコード)。

**Style-Bert-VITS2。** エディターには文ごとの設定と辞書がある。推論モデルには設定・重み・スタイルベクトルが必要。コードのライセンスだけで話者や音声の条件を決めない。[公式README](https://github.com/litagin02/Style-Bert-VITS2#使い方)、[モデル規約](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md)。

**Qwen3-TTS。** 1.7B-CustomVoiceは既成話者と演技指示、VoiceDesignは文章による声の設計、Baseは参照音声による複製等を担当する。0.6B-CustomVoiceに1.7Bと同じ演技制御があると推測しない。実行時に対応言語・話者を列挙し、日本語話者の一例は`Ono_Anna`。1.7Bの公式例は`instruct`を使う。モデル読込時に重みを取得する場合がある。FlashAttentionは追加最適化であり、Windowsへの導入可否を確認せず必須化しない。[Qwen公式実装](https://github.com/QwenLM/Qwen3-TTS)、[対象モデルカード](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)。

**Kokoro。** 日本語は`lang_code='j'`、前処理は`misaki[ja]`、日本語話者は`jf_alpha`等を使う。英語デモの話者や言語設定をそのまま流用しない。[Kokoro公式](https://github.com/hexgrad/kokoro)、[話者一覧](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md)。

## 今回の動画に適用する案

仮v1はMicrosoft HarukaのWindowsローカル音声で生成済み。この事実は [試写記録](../../product-demo/preview-v1.md) と既存の生成コードで確認できる。比較試聴なしに、今回の候補がHarukaより自然だと断定はしない。

2026年11月7日の読取ではRTX 4090・VRAM約24 GBを確認した。この仕様はローカルTTSの検討材料になるが、実際の必要VRAMや生成速度を実測したものではない。動画生成とTTSがGPUを共用する場合は、現在の使用状況を見て順番に実行する。

提案する比較は、AivisSpeech、VOICEVOX、Qwen3-TTS 1.7Bから同じ20〜30秒を作ること。主ナレーターは一人に固定し、背景、技術説明、締めの演技を変える。コックピットのAI音声を追加する場合も、主説明との聞き分けが有益か短い場面で比較してから決める。

既存の編集データには字幕用`caption`と読み上げ用`speech`があり、固有名詞と単位の読みを引き継げる。TTSを替える場合は音声の実尺を測って再編集する。現在のレンダラーには速度変更の上限があるが、これは仮v1の実装上の制約であって、自然さを保証する閾値ではない。ピーク正規化したことも、ラウドネス測定や試聴の代わりにはならない。

具体的な短尺比較、読みの辞書、一文ごとの修正、字幕同期、音量の確認は [ナレーション制作の手順](../../skills/video-production/video-audio/references/japanese-narration.md) に集約した。FFmpegの`atempo`、`loudnorm`、`sidechaincompress`等は仕上げの選択肢であり、納品先に応じて使う。[FFmpeg公式フィルター](https://www.ffmpeg.org/ffmpeg-filters.html)。

## 一次資料の記録

以下は全て2026年11月7日に本文またはモデルカードを確認した。モデルや契約を採用するときは、具体的な版と条件をもう一度読む。サイトの宣伝表現を実測評価として転載していない。

| 発行元・資料 | 言語 | 対象と確認したこと |
| --- | --- | --- |
| [Aivis Project：AivisSpeech](https://aivis-project.com/AivisSpeech) / [FAQ](https://aivis-project.com/faq) | 日本語 | 無料、CPU、オフライン、モデル別条件 |
| [AivisSpeech Engine README](https://github.com/Aivis-Project/AivisSpeech-Engine) | 日本語 | API、10101、スタイルID、VOICEVOXとの仕様差 |
| [VOICEVOX規約](https://voicevox.hiroshiba.jp/term/) / [Q&A](https://voicevox.hiroshiba.jp/qa/) | 日本語 | クレジット、音声ライブラリ、対応OS |
| [VOICEVOX ENGINE](https://github.com/VOICEVOX/voicevox_engine) | 日本語 | クエリとWAV生成、話速変更 |
| [Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2) / [規約](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md) | 日本語・英語 | Windows、CPU合成、エディター、モデル別条件 |
| [Qwen3-TTS公式](https://github.com/QwenLM/Qwen3-TTS) / [1.7B-CustomVoice](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice) | 英語 | 対象モデル群、日本語、指示制御、Apache表示 |
| [Kokoro-82M](https://huggingface.co/hexgrad/Kokoro-82M) / [実装](https://github.com/hexgrad/kokoro) / [VOICES.md](https://huggingface.co/hexgrad/Kokoro-82M/blob/main/VOICES.md) | 英語 | 82M、日本語前処理、話者と帰属表示の参照 |
| [ElevenLabs Billing](https://elevenlabs.io/docs/overview/administration/billing) / [Audio Detector](https://elevenlabs.io/docs/eleven-creative/audio-tools/audio-detector) | 英語 | 無料枠の非商用条件、不可聴透かし |
| [Resemble AI：Chatterbox](https://github.com/resemble-ai/chatterbox) | 英語 | Multilingualの日本語とPerTh |
| [Fish Audio：S2](https://fish.audio/ja/s2/) | 日本語 | S2-Pro重みのResearch License |
| [FFmpeg Filters](https://www.ffmpeg.org/ffmpeg-filters.html) | 英語 | 話速、音量正規化、音声ミックスの手段 |

ライセンス本文のない第三者の「無料・商用可」一覧は、結論の根拠にしていない。MicrosoftのAPI文書は今回取得できなかったため、Windows音声に関して新しい公開利用条件の結論は追加していない。
