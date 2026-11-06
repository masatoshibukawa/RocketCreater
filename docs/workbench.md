# ローカル統合試験

## 起動

Python依存を既存の `pyproject.toml` から用意し、リポジトリルートでAPIを1プロセス起動する。

```powershell
uv run uvicorn api.main:app --host 127.0.0.1 --port 8000
```

`web/` で `pnpm install`、`pnpm run build`、`pnpm run start --hostname 127.0.0.1` を実行し、`http://127.0.0.1:3000` を開く。ブラウザーからの `/backend/` はNext.jsがローカルAPIへ転送する。APIの場所を変える場合はNext.jsの実行環境に `ROCKETWRIGHT_API_URL` を指定する。直接接続する既存環境には `NEXT_PUBLIC_API_BASE` も残している。

課金APIは `ROCKETWRIGHT_ENABLE_CLOUD_DESIGN=0` が既定。`/design` は明示的に有効化するまでHTTP 423を返す。この試験で有効にする必要はない。

既存LLMの起動は [ローカル制作支援](../AIvideo/local-director/README.md)、既存の動画推論環境は [ComfyUI/Wan2.2](../AIvideo/local-runtime/README.md) を参照する。別作業ツリーにメディア用ライブラリがある場合は、APIの実行環境に `ROCKETWRIGHT_MEDIA_ROOT` をその既存 `AIvideo` ディレクトリへ設定する。

## 操作

1. 設計条件を読み、試験プロジェクトを作る。現在の製作フローは20 m・60 g・1.5 L・材料予算3,000円という既存のペトロケ探索例。
2. 利用可能な解析を選び、理由を記入して1工程実行する。推奨は検証済みの8工程例に沿い、途中で別の選択をすれば既存ハーネスの利用可能な候補へ切り替わる。ローカルLLMに相談しても、計算は実行されない。
3. 合否と根拠を確認する。材料・圧力・充填率の変更には、その組合せについての下位工程の新しい証拠が必要。
4. 独立確認を通過した案の製作ファイルを生成する。搭載部カラー・フィン位置決め治具のSTLに加え、「この設計の印刷データを生成」で同じ設計からフィン・ノーズ・試着リングの形状検査とS5用スライスを実行できる。STL・3MF・UFP・G-code・検査記録・ZIPを保存する。対応機種と実機検証の状態は [設計から3Dプリント用データを作る](printable-design-exports.md) を参照。ボトル本体・耐圧部品は出力しない。
5. 動画画面で「写真調」か「簡易CG」を選び、標準構成かローカルLLMによる構成を確認してから2本を制作する。写真調は1920×1080・24 fps・設計16秒／飛行12秒、簡易CGは960×540・各4秒。両方を同じプロジェクトへ独立して保存できる。いずれも音声なし。写真調はAIvideoの既存CC0素材・照明を使い、元の2 L映像を新しい設計の成果物に流用しない。
6. 必要ならBlenderの参照フレームを、確認したプロンプトと固定グラフでローカルWan2.2へ渡す。キュー投入と結果確認は別操作。CGとAI映像を混同しない。自動で課金サービスへ切り替わる経路はない。

`output/workbench/<project_id>/` に履歴・仮定・解析結果・出力・ハッシュを保存する。ブラウザーは最後のIDだけを保存する。1プロセス内のプロジェクト単位のロックとrevision検査が重複・古い操作を拒否する。中断した工程は次回起動時に記録を残して再試行できる。数学モデル・部品カタログ・数値に関係する実装が変われば、新規プロジェクトで再計算する。LLMの接続先や説明だけの変更で数値の証拠を失効させない。

進捗は処理中の工程と実経過時間を表示する。根拠のある残り時間推定はまだない。任意要求からの製作フロー、月到達の設計、製造認証、実機回収の保証をこの試験から導かない。

## 再現

```powershell
uv run python -m scripts.run_workbench
uv run python -m scripts.run_workbench --local-direction --render
```

2つ目は既存のローカルLLMとBlenderを使う。`ROCKETWRIGHT_BLENDER`、`ROCKETWRIGHT_VIDEO_PYTHON` で実行ファイルを指定できる。合成には既存の `AIvideo/Test project/tools/python`、または [メディア依存](../AIvideo/Test%20project/requirements.txt) を入れたPythonを使う。スクリプトは決まったファイルだけを実行し、LLMの出力をコマンドとして実行しない。

生成物の `verification.json` は、全フレームのデコード、枚数、寸法、fps、画像の変化を記録する。目視、機構の正確さ、音の確認、現物の検証は別項目。Wanの回収時の検査はコンテナ確認までであり、全フレーム検証済みと表示しない。
