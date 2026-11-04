# 既存のローカルLLMを制作に使う

会話モデルは工程選択と動画の構成・説明を提案する。画素生成はComfyUI/Wan2.2、寸法と軌跡に沿うCGはBlender、工程の適用条件と合否はPythonハーネスが担当する。

## 既存モデルを再利用する

このPCのBoeingプロジェクトにある専用Ollamaとモデル保管場所を、同プロジェクトの「Ollama手順を含むPRブランチを取得」の履歴および起動スクリプトから確認した。確認したモデルのmanifestは `gemma3:4b`、`gemma4:12b`、`gemma4:31b`、`gemma4:e4b-it-qat`。通常のホームディレクトリや11434番ポートにないことは、未導入の根拠にならない。

`--assets` に `ollama/ollama.exe` と `ollama-models/` が入った既存ディレクトリを指定する。

```powershell
python AIvideo/local-director/start.py --assets C:/path/to/existing/data/runtime --model gemma4:12b
```

起動先は `127.0.0.1:11436`。既存Boeing用の11434/11435番ポート、撮影サーバー、Tunnelを起動・停止しない。重みのダウンロード・コピー、元のモデルの削除も行わない。ログと接続情報はこのディレクトリの `runtime/` に保存し、Gitから除外する。

APIは接続情報を自動で読み、環境変数 `ROCKETWRIGHT_OLLAMA_URL` と `ROCKETWRIGHT_LOCAL_MODEL` があればそちらを優先する。Ollamaがすでに起動している環境では、その変数だけでも接続できる。空のモデル変数は、保存した設定またはインストール済みGemmaの選択へ戻る。

Ollama側はクラウドを無効にし、同時ロード・並列推論を1に制限する。生成要求は `think=false`、JSON schema、temperature 0、出力上限を指定し、終了時 `keep_alive=0` でアンロードを要求する。WanやTTSとVRAMを競合させないため、会話モデルによる計画が終わってから次の推論工程へ進める。他のチャットのGPU処理は停止しない。

構造化出力は、型・余分な項目・候補IDの検査を通す。動画では説明する部位・カメラ・動きの登録済みIDを選ばせ、字幕と水ロケット用プロンプトは規則から組み立てる。実試験で、自由記述に炎と性能の断言が混ざったため、この境界を設けた。モデルはシェル、CADコード、ComfyUIノード、合否、承認を直接実行・変更できない。不正な出力は工程の失敗として記録する。

一次資料: [Ollama structured outputs](https://docs.ollama.com/capabilities/structured-outputs)、[Windowsとモデル保存場所](https://docs.ollama.com/windows)。
