# Local video generation

ComfyUIとWan2.2 TI2V-5Bを、このディレクトリの`runtime/`へ分離して導入する。サービスへの生成課金や、サービスのロゴを合成する処理は使わない。電力、保存容量、生成時間は必要になる。

写実性の改善、写真調の開始画像と14B版の比較、テイクの再開・保存・比較ページは[反復制作の手順](ITERATION.md)を参照する。以下の2秒テストは初回の基準記録として保持している。

## Install

WindowsのPythonで実行する。今回の検証はPython 3.11.6、RTX 4090 24GB、RAM約63GiB。

```powershell
python AIvideo/local-runtime/bootstrap.py --install
```

公式ComfyUIリリース、PyTorchのCUDA 13.0用wheel、ComfyOrgが再配布する公式Wan2.2ワークフロー用の重みを取得する。モデルはHugging Faceが公開するLFSのSHA-256とサイズで照合する。仮想環境、モデル、キャッシュは`runtime/`へ保存し、Gitには含めない。

導入したのはComfyUI 0.44.0、PyTorch 2.14.1+cu130、Wan2.2 TI2V-5B FP16、UMT5 FP8、Wan2.2 VAE。モデル3点は合計18,144,966,705バイトで、公開LFSハッシュとの一致を確認済み。[installation.json](installation.json)にソースとモデルのリビジョン、サイズ、ハッシュを、[requirements-lock.txt](requirements-lock.txt)に実際のパッケージ版を記録した。bootstrapは配布先から依存関係を解決するので、将来の実行で同一の版が選ばれる保証はない。

## Start and generate

リポジトリのルートから起動する。通常は1つ目のターミナルでサーバーを起動したまま、2つ目で生成する。

```powershell
python AIvideo/local-runtime/start.py
```

画面は <http://127.0.0.1:8188>。`--offline`で外部サービスへ接続するノードを無効にし、カスタムノードも読み込まない。モデル実行はこのPCのGPUで行う。生成物にプロンプトを埋め込む機能も無効にしている。

```powershell
AIvideo/local-runtime/runtime/venv/Scripts/python.exe AIvideo/local-runtime/generate.py
AIvideo/local-runtime/runtime/venv/Scripts/python.exe AIvideo/local-runtime/verify.py
```

入力は[再現プロジェクト](../Test%20project/README.md)で作ったHUDなしの`renders/frames/frame_0170.png`。未作成なら先にBlenderレンダリングを実行するか、`generate.py --image <画像のパス>`を指定する。生成スクリプトは専用venvで実行する。システムPythonへ画像ライブラリ等を入れる必要はない。

`workflow-api.json`は実行したComfyUI API形式のグラフで、画面配置を持つUI形式JSONとは異なる。ノードと入力の実在をローカルAPIで確認してからキューへ送る。実行の記録は[generation-result.json](generation-result.json)、動画の機械的な確認は[verification.json](verification.json)、目視での所見は[review.json](review.json)に保存する。

## Observed result — 2026-11-04

- 832×480、24fps、49フレーム、約2.04秒、H.264 MP4、無音。
- 20 steps、CFG 5、uni_pc、simple、shift 8、seed 20261104。公式5Bテンプレートのノード構成とサンプラー設定を基に、画像入力を有効化し、解像度・尺・プロンプトを試作用に変更した。
- ComfyUIサーバーの実行時間は26.52秒。API送信から完了確認までは30.09秒で、ポーリングの待ち時間を含む。今回の1回の測定で、他の解像度・尺の速度を保証しない。
- `outputs/rocketwright_wan22_test.mp4`を全49フレームデコード。寸法、fps、枚数、非黒画像、フレーム間変化、メタデータを確認。
- `outputs/contact_sheet.jpg`の6時点と終端フレームを目視確認。大きな構図と二つのフェアリングは維持され、動きはごく小さい。CG由来の見た目と細部の軟化が残る。機械部品の厳密な形状保持、写実性の向上、映像全体の実時間再生による確認は未達・未実施。
- 確認したフレームにサービスのロゴや透かしは見当たらない。サービスの透かしを合成・除去する処理はない。AI生成であることはMP4のcommentに保持する。

動画と確認用画像は`outputs/`に保存し、Gitへ含めない。PRには再実行コードと記録だけを保存する。今回の短い生成成功は、元のLinkedIn映像の完全再現を意味しない。

## Runtime notes

この実行環境では、ネットワーク制限下のプロセスはlocalhostへの接続も拒否された。サーバーとAPI呼び出しにローカルネットワーク接続の権限が必要だった。起動が止まる場合、GPU認識だけで成功とせず、ログの`Starting server`と`/system_stats`の応答を確認する。通常のPC環境にこの制限があるとは限らない。

`start.py --background`はウィンドウを表示せずに起動し、`runtime/server.log`、PID、URLを記録する。ポートが既に使用されている場合は、既存サーバーを停止せずに終了する。試験時のサーバーはこの方法で起動した。

ComfyUI、Wan、エンコーダー等の配布物のライセンスは各配布元に従う。取得したComfyUIのLICENSEは`runtime/ComfyUI/LICENSE`に保持し、モデルや依存ライブラリをこのリポジトリのMITライセンスとして再配布しない。

## Sources

- [ComfyUI manual installation](https://docs.comfy.org/installation/manual_install)
- [Official Wan2.2 workflow](https://docs.comfy.org/tutorials/video/wan/wan2_2)
- [Wan2.2 model and license](https://github.com/Wan-Video/Wan2.2)
- [ComfyOrg model repackaging](https://huggingface.co/Comfy-Org/Wan_2.2_ComfyUI_Repackaged)
