# このPCでのローカル動画生成

RTX 4090の約24GB VRAMと約64GB級のシステムメモリがあるため、ローカル動画生成を試す候補として **ComfyUIとWan2.2 TI2V 5B** が適している。導入の簡単さを優先するなら **LTX Desktop** も候補になる。これは公開要件と実機仕様を照合した判断であり、このPCでの生成成功や速度を実測した結果ではない。

## 確認したPC仕様

2026年11月4日に読み取り専用コマンドで取得した。機械可読な記録は [environment.json](environment.json) に保存している。

| 項目 | 実測した情報 | 確認方法 |
| --- | --- | --- |
| OS | Windows 11 Pro、10.0.26200 | Win32_OperatingSystem |
| CPU | AMD Ryzen 9 7950X、論理32プロセッサ | Win32_Processor、Win32_ComputerSystem |
| メモリ | 63.1 GiB | TotalPhysicalMemory |
| 主GPU | NVIDIA GeForce RTX 4090 | nvidia-smi |
| VRAM | 24,564 MiB | nvidia-smi memory.total |
| NVIDIAドライバ | 610.88 | nvidia-smi |
| Cドライブ空き | 確認時188.2 GiB | Get-PSDrive |
| PATH上のPython | 3.11.6 | python sys.version |

Windowsの `Win32_VideoController.AdapterRAM` はこのGPUについて約4GB相当を返した。VRAM判断にはこの値を使わず、`nvidia-smi` の値を採用した。

PATH上のPythonではtorch、diffusers、transformers等のインストールを確認できなかった。Ollama、LM Studio、ComfyUIの標準的な一部保存先にもモデルは見つからなかった。ただし別ドライブ、任意フォルダ、別のPython仮想環境は網羅していない。**このPCに既存LLMや動画環境がないとは断定できない。**

## モデルごとの実行条件

| 候補 | 一次資料にある条件 | このPCでの判断 |
| --- | --- | --- |
| Wan2.2 TI2V 5B 公式Python | CPUオフロード等を有効にした720P用コマンドは24GB VRAM以上。例示サイズは1280×704 | 4090が公式例に含まれる。Windowsの依存関係は別に確認する |
| 同5BのComfyUI版 | ComfyUIのネイティブオフロードで8GB VRAMに収まる旨の記載 | 初回候補。公式Pythonの24GBという値と混同しない |
| Wan2.2 A14B | ComfyUIでは高ノイズ・低ノイズの別チェックポイントを使う | 5Bで操作を確認後、FP8やオフロードの条件を確認して比較する |
| HunyuanVideo 1.5 | オフロード有効で最低14GB VRAM、Python 3.10以上。公式ソース実行のOS要件はLinux | VRAM面は候補。Windowsネイティブで動くと断定せず、WSL2または対応ComfyUI統合を調べる |
| LTX Desktop | Windows 10/11、CUDA対応NVIDIA GPU、24GB以上VRAM、RAM32GB。VRAM32GB推奨。空き100GB以上 | 公開要件に照らして候補。追加モデルを増やすと現在の空き容量は圧迫される |

出典: [Wan2.2公式README](https://github.com/Wan-Video/Wan2.2#run-text-image-to-video-generation)、[ComfyUI公式Wan2.2手順](https://docs.comfy.org/tutorials/video/wan/wan2_2)、[HunyuanVideo 1.5公式](https://github.com/Tencent-Hunyuan/HunyuanVideo-1.5#-system-requirements)、[LTX Desktop公式](https://github.com/Lightricks/LTX-Desktop#system-requirements)。

## LLMと動画モデルの役割

会話用LLMには、台本、ショット分解、英語プロンプト、生成条件の整理、採用理由の記録を担当させる。画素列の生成はWanやLTXなどの動画モデル、ナレーションはTTSモデルに担当させる構成が扱いやすい。通常のチャット用重みをダウンロードしただけで、動画生成機能が加わるわけではない。

LTX DesktopにはローカルQwenを使うアシスタントもある。これは動画ジョブを組み立てる役と動画モデルを同一アプリ内でつなぐ実装例になる。ローカル設定でも、任意のAPI文字エンコードやクラウドによるプロンプト拡張を選ぶと外部通信が発生する。[LTX DesktopのAssistantと動作説明](https://github.com/Lightricks/LTX-Desktop#assistant)。

## 初回導入の進め方

1. RocketCreaterの既存Python環境とは別に、動画用アプリとモデル保存先を用意する。大きなモデル重みはGitリポジトリに入れない。
2. ComfyUIの公式Windows配布と、公式のWan2.2 5Bテンプレートから始める。テンプレートを保存し、チェックポイントとアプリの版を記録する。
3. 参照画像1枚から短い単独ショットを生成し、最初はテンプレート標準値を使う。解像度・フレーム数を同時に増やさない。
4. LLM、TTS、動画モデルを同時にGPUへ常駐させず、工程ごとにロードする。これはVRAM競合を避けるための運用案である。
5. OOMなら、使用中GPUメモリ、フレーム数、解像度、オフロード、VAEタイル処理の順に確認する。別モデル専用VAEの混用は避ける。
6. 動画が完成してから音声を生成して編集で合わせる。音声と映像を一括生成したい場合はLTXを比較する。

ComfyUIの5B構成は `wan2.2_ti2v_5B_fp16.safetensors`、`umt5_xxl_fp8_e4m3fn_scaled.safetensors`、`wan2.2_vae.safetensors` をそれぞれ対応フォルダへ置く。ファイルの置き方とワークフローは[公式手順](https://docs.comfy.org/tutorials/video/wan/wan2_2#2-manually-download-models)に従う。

## 実測時に残す項目

同一入力画像、プロンプト、seed、出力サイズ、フレーム数で候補を比較する。経過秒数、ピークVRAM、チェックポイント識別子、失敗理由、採用ショットを残す。同じseedでもアプリ・GPU・演算実装が異なれば同一画素になる保証はない。

現時点ではモデルのダウンロード、アプリ導入、動画生成、GPU速度ベンチマークは行っていない。上記は導入前の判断資料である。
