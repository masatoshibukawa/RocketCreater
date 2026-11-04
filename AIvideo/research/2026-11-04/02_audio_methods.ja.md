# 音声と効果音と音楽の生成

映像の音は、セリフやナレーションを作るTTS、環境音や効果音を作る音響生成、BGMを作る音楽生成に分けて扱う。まず声だけを聞いて読みと演技を確定し、映像に合わせて効果音を配置すると修正しやすい。

## 声の生成候補

| 候補 | ローカルか | 使いどころ | 確認した条件 |
| --- | --- | --- | --- |
| Qwen3-TTS | ローカル実行可 | 日本語を含む多言語、声のデザイン、声質と演技の制御 | 0.6Bと1.7B等を区別。CustomVoice、VoiceDesign、Baseで用途が異なる |
| Fun-CosyVoice 3.0 | ローカル実行可 | 多言語のゼロショットTTS、読み上げ | 日本語を含む9言語を公式に記載 |
| Style-Bert-VITS2 | ローカル実行可 | 日本語の読みやスタイルを調整する音声制作 | Windows用導入手順があり、合成のみならCPU実行も可能 |
| ElevenLabs | クラウド | 導入を軽くしたいナレーション、演技比較 | 日本語対応、モデルごとに言語・表現・出力形式が異なる |

出典: [Qwen3-TTS](https://github.com/QwenLM/Qwen3-TTS)、[CosyVoice](https://github.com/FunAudioLLM/CosyVoice)、[Style-Bert-VITS2](https://github.com/litagin02/Style-Bert-VITS2)、[ElevenLabs TTS](https://elevenlabs.io/docs/overview/capabilities/text-to-speech)。声の複製を使う制作では、使用を許諾された録音を参照にする。

Qwen3-TTSのCustomVoiceは用意された話者の合成、VoiceDesignは文章による声の設計、Baseは参照音声による複製等を担当する。モデルカードでCustomVoice重みのApache 2.0表示を確認した。[Qwen公式モデルカード](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice)。

## 日本語ナレーションの作り方

次はこの調査から組み立てた制作手順である。

1. 原稿を一文または一息で読む単位に分ける。数字、固有名詞、英略語に読みを付ける。
2. 平静、驚き、緊張などの演技を一つ指定する。音量だけで迫力を作ろうとせず、間と速度を変える。
3. 候補を生成し、映像を見ずに読み間違い、不自然な息継ぎ、語尾の欠けを確認する。
4. 声が決まったら映像の尺を調整する。セリフのたびに映像全体を再生成する必要はない。
5. 声、効果音、環境音、音楽を別トラックに保存する。最後まで無圧縮の中間素材を保持する。

SF予告編用の原稿例:

```text
信号が、戻った。
あの光の先に、まだ誰かがいる。
今度は、私たちが迎えに行く。
```

演技指定例:

```text
落ち着いた日本語。最初は息を抑え、最後の文だけ決意を込める。
叫ばず、短い間を置いて話す。
```

## Qwen3-TTSの起動例

公式READMEは分離したPython 3.12環境を推奨している。このPCのPATH上のPython 3.11.6に、そのまま依存関係を追加する前提にはしない。環境を用意した後の例は次の通り。**このコマンドは保存した手順であり、今回実行していない。** 初回はモデル取得が発生する。

```powershell
python -m pip install qwen-tts
qwen-tts-demo Qwen/Qwen3-TTS-12Hz-1.7B-CustomVoice --ip 127.0.0.1 --port 8000
```

ブラウザで `http://127.0.0.1:8000` を開く。FlashAttention等の追加最適化は、まず選んだOSとPyTorchの組合せでの対応を確認する。[Qwen公式の環境とWeb UI手順](https://github.com/QwenLM/Qwen3-TTS#quickstart)。

Style-Bert-VITS2は公式配布のWindows用zip、インストールbat、音声編集エディターという経路を用意している。複数TTSを試す場合も各環境を分離し、異なるPyTorch要件を一つに押し込まない。[Style-Bert-VITS2の導入手順](https://github.com/litagin02/Style-Bert-VITS2#使い方)。

## 効果音と環境音

| 候補 | 主な入力と出力 | 制作での位置づけ |
| --- | --- | --- |
| MMAudio | 動画や文章から同期した音を生成 | 無音の生成動画への環境音付与、実験用比較 |
| Stable Audio Open 1.0 | 文章から音を生成 | 風、機械音、衝撃音などの素材作り |
| LTX系 | 映像と同期音声をまとめて生成 | 映像と音を一括で試す経路 |
| 録音・効果音ライブラリ | 実際の音素材 | 特定の動作とタイミングを厳密に合わせたい場面 |

MMAudioは公式実験で約6GB GPUメモリという記載があるが、このPCでの測定値ではない。READMEは不明瞭な人声や意図しない音楽の生成も限界として挙げる。[MMAudio公式](https://github.com/hkchengrex/MMAudio)。

Stable Audio Open 1.0は最大47秒、44.1kHzステレオの音を生成するモデルとして公開されている。TTS専用モデルや長い完成曲の代替とは扱わず、必要な短い素材から比較する。[公式モデルカード](https://huggingface.co/stabilityai/stable-audio-open-1.0)。

効果音のオリジナル指示例:

```text
A heavy mechanical door slides open in a large metal hangar.
Low motor hum, a brief hydraulic release, a final metallic latch.
```

```text
Wind passes through a damaged observation tower.
Loose cables rattle nearby and distant machinery pulses slowly.
```

短い衝撃音、低い響き、細かな金属音を別々に作り、編集で重ねる案も試す。全てを一本の生成音へまとめると、後からタイミングを直しにくくなる。

## 音楽と利用条件

AudioCraftにはMusicGen等が含まれるが、**コードのMITと、配布モデル重みのCC BY-NC 4.0は別**である。商用公開を想定した制作の初期候補として、無条件に採用しない。[AudioCraftのライセンス記載](https://github.com/facebookresearch/audiocraft#license)。

同様に、MMAudioはコードがMIT、配布チェックポイントがCC BY-NC 4.0である。Stable Audio Openは独自のCommunity Licenseを参照する必要がある。Style-Bert-VITS2ではソースコードのAGPLと個別の声モデル規約を区別する。[MMAudio](https://github.com/hkchengrex/MMAudio#license)、[Stable Audio Open](https://huggingface.co/stabilityai/stable-audio-open-1.0)、[Style-Bert-VITS2モデル規約](https://github.com/litagin02/Style-Bert-VITS2/blob/master/docs/TERMS_OF_USE.md)。

劇伴の制作案としては、「金管が大きい映画風」だけでなく、低音の持続、打楽器の入り、主題の出現、無音の区間を先に決める。既存映画の旋律を参照するより、場面の役割と楽器編成で指示すると独自の曲を設計しやすい。

## 口と声を合わせる

セリフ付き人物の口の動きが必要な場合は、音声を確定してからMuseTalk等を比較する。MuseTalkは顔の領域を音声に合わせて変える方式で、日本語音声にも対応すると記載する。顔の細部保持や揺れには限界がある。[MuseTalk公式](https://github.com/TMElyralab/MuseTalk)。

ナレーション中心の予告編なら、まず声を画面外に置き、後ろ姿、手元、背景を編集する構成も使える。口の同期が不要になり、映像の選択肢が増える。

## 音の仕上げ

セリフの明瞭さを先に確保し、音楽と効果音の音量を場面ごとに調整する。部屋や屋外の響きを合わせ、衝撃の瞬間に映像と音がずれていないか確認する。FFmpegには音のミックスや音量正規化のフィルタがあるが、正規化の目標値は納品先に合わせて決める。[FFmpegの音声フィルタ](https://ffmpeg.org/ffmpeg-filters.html)。
