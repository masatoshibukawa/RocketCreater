# RocketWright 実演入り改善版

渋川さんが共有した実演入り版に、実アプリから始まる7秒の導入と、フィン変更の影響を示す9秒の試算を組み込んだ。実演では見る箇所を5つの短いラベルで案内する。[編集設定](hybrid-v2.json)。

| 時間 | 内容 |
| --- | --- |
| 0:00–0:07 | 実アプリの抜粋。「卵を割らずに20 mへ」という要求を示す。 |
| 0:07–0:16 | 別条件のフィン厚さの試算。変形は減り、重量が増えて概算高度は下がる。部品を改善するときに機体全体を再評価する理由。 |
| 0:16–0:44 | モデルベース開発と開発チーム。 |
| 0:44–1:16 | 階層型、適応型、5者の役割。部品・機体・要求を結び、条件に応じて次の解析を選ぶ。1:04から実画面の抜粋に役割を重ねる。 |
| 1:16–2:22 | 要求の範囲確認、Claudeの候補選択、ハーネスの検査、飛行・流体計算、製作票と部品表の出力。 |
| 2:22–2:34 | 別試作のフィンを印刷する実写。実機確認へ渡す場面。 |
| 2:34–2:47 | 開発時のClaude Codeと、実行時のClaude APIを示す。 |

冒頭のフィン試算と実アプリの20 m案件は別条件。実写は既存2 L案のフィンの印刷工程。実演の待ち時間は収録素材と同じ省略表示を使う。詳しい出典は[解析の構成メモ](analysis-story.md)、[印刷の記録](print-progress.md)、[仮v1の音声記録](narration-v1.md)にある。

[キックオフの説明](https://vimeo.com/1242214578#t=28m01s)で3分の動画と閲覧可能なリンク、29:13付近で前提知識のない視聴者にも伝わる冒頭を確認した。セッション3の紹介にある「最初に動く機能」の考え方を、入力から製作データ出力までの一件に反映した。セッション4の26:04付近で語られたストーリーの考え方を使い、冒頭の設計の問いを実演までつないだ。セッション5の紹介にある全体図から具体的なデータ分析へ移る構成を、5者の役割から実画面への切替に使った。セッション1・2と6は提供された紹介文を参照した。

## 再書き出し

ソースはローカルに保存した実演入りMP4と、Gitで共有しているAIナレーション入り仮v1。冒頭音声は[固定声の設定](narration-v1-voice.json)を使って `opening_speech` の一文を合成する。以下の例は合成用の1カットの設定と出力先を作り、映像を編集する。既存の音声環境を利用する。

```powershell
$out = 'output/media/product-demo/generated/hybrid-v2'
New-Item -ItemType Directory -Force -Path $out | Out-Null
$edit = Get-Content -Raw -Encoding UTF8 AIvideo/product-demo/hybrid-v2.json | ConvertFrom-Json
@{ shots = @(@{ caption = $edit.opening_caption; speech = $edit.opening_speech }) } |
    ConvertTo-Json -Depth 4 | Set-Content -Encoding utf8NoBOM "$out/opening-voice.json"
output/narration-runtime/qwen-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/synthesize_fixed_narration.py --model output/narration-runtime/models/qwen-base --plan "$out/opening-voice.json" --out "$out/takes" --shot 0
output/media-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/render_hybrid_v2.py --hybrid 'path/to/rocketwright-demo-hybrid-voiced.mp4' --preview assets/product-demo/previews/v1/rocketwright-preview-v1-narrated.mp4 --take "$out/takes/00.wav" --out $out
```

## 書き出しの確認

MP4は167秒、1920×1080、30 fps、全5,010フレーム。FFmpegで全編をデコードし、冒頭の要求、フィン試算、5者の表示、実演の各段階、締めの表示を確認した。印刷部分は約2:25からの150フレームを仮v1と照合した。音声は −16.25 LUFS、最大トゥルーピーク −1.40 dBTP。新規ナレーションの「20メートル」と前後の文は自動読み戻しで確認した。人による試聴は未実施。

書き出したファイルのSHA-256は `a991a349a66edc8524051067292a61f60b6aedb5f65384ee641ca310ab15ff13`。提出URLと閲覧権限の確認は提出工程で行う。
