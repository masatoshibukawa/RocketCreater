# 写実性の反復比較

既存の[導入手順](README.md)でComfyUIを起動してから、専用venvで実行する。今回の比較は`python AIvideo/local-runtime/start.py --conservative`で起動した標準オフロード設定を使う。新しいモデルは任意で、無料公開の配布先からのみ取得する。

```powershell
python AIvideo/local-runtime/download_quality_models.py
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --only baseline-5b cg-short-prompt --max-runs 2
```

`experiments.json`の各IDが一つのテイク。同じIDの設定・入力・モデルが変わる場合は、新しいIDを使う。完了テイクはファイルハッシュを確認してスキップする。投入済みジョブはジョブIDから完了確認を再開する。APIの応答が曖昧な場合に、無条件で再投入しない。

CLI実行中はローカルのOSファイルロックを保持し、別のキャンペーンが同時に投入することを防ぐ。プロセス終了時にはOSがロックを解放する。サーバーの既存キューが空でない場合も、新しい試行は投入しない。

記録とAPIグラフは`experiments/<id>/`、動画・画像は`outputs/experiments/<id>/`へ保存する。元の試作とその検証記録は上書きしない。比較ページは`outputs/experiments/index.html`。

```powershell
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --only photo-a photo-b --max-runs 2
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --only photo-a-5b photo-a-14b --max-runs 2
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --only photo-c photo-c-14b --max-runs 2
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --gallery
```

既定の上限は1回3テイク、次のテイクへ進む前の経過時間20分。`--max-runs`と`--max-minutes`で変更できる。実行中の1ジョブは即座に中断せず、最大30分の完了確認を行う。タイムアウト後は同じコマンドで監視を再開する。ComfyUI再起動でキューと履歴が失われた場合は、既存IDを消さず状態を確認し、新IDで再試行する。

目視で確認した所見は、対応する`experiments/<id>/review.json`へ`decision`（`selected`、`candidate`、`rejected`）と`notes`を保存してから、`--gallery`で反映する。写実性、形状、動き、不要な文字、全体再生をどこまで確認したかを記述する。自動のフレーム差分値は写実性の順位に使わない。

写真の探索と動画の探索を分ける。開始画像の形や接地に問題があれば、動画のseedだけを何度も変える前に素材案を修正する。今回のphoto-a、photo-bはエンジン数と向きが設計と異なり、photo-cでは指示文を修正している。候補を採用する際も、生成AIが厳密なCAD形状を再現したとは記録しない。

## 次のテイクを作る

既存の条件をコピーしてseedだけ変える例。1つ目のコマンドは計画への追加だけを行い、生成しない。IDは未使用のものを指定する。

```powershell
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --fork photo-c-14b --new-id photo-c-seed2 --set seed=20261105 --hypothesis "seedだけ変えて形状の安定性を比較"
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/iterate.py --only photo-c-seed2 --max-runs 1
```

`--set`でseed、steps、cfg、shift、width、height、frames、fps、positive、negative、source、split_step、samplerを変更できる。同じIDへの上書きはできない。複数項目を変える場合は、何の影響かを一つに決めつけない。計画の`enabled: false`は通常の全体実行から除外し、明示的に`--only`を指定したときだけ実行する。

`runtime_profile`は実行時のメモリ設定を明示する。最初のDynamicVRAM比較は約491秒で完了し、標準オフロードでの同条件比較は約56秒だった。GPUの他プロセスやメモリ状態も影響するため、設定だけが速度差の原因だと断定しない。他のアプリや不明なジョブは停止しない。

調査と実験の意図は[追調査](../research/2026-11-04/08_realism_iteration.ja.md)を参照する。新規の写真調画像は別形状の概念案であり、元の機械設計と同一とは扱わない。

## 今回の結果

新規の画像3案と動画6本、既存の基準動画1本を保存した。採用候補は`photo-c-14b-720`で、1280×720、49フレーム、16fps、約3.06秒、無音。サーバー実行は656.293秒だった。低解像度の同じ案は179.267秒で、高解像度化には明確な時間増加がある。

指示文だけを変えた元CG版にはCGの外見が残った。写真調画像を使うと、今回確認したフレームでは金属・床・設備の見え方が自然になった。ただし入力の形状は変わり、ノズルの向きなどの不整合が残る。14Bが5Bより一般に高画質だと結論できる規模の比較ではない。

[experiment-summary.json](experiment-summary.json)に採用テイクと比較の要点を保存した。全動画をデコードし、画像・時刻付きコンタクトシート・選択した高解像度フレームを目視確認した。実時間での動画全体の再生確認は行っていない。

比較ページと前後画像を作り直すには、以下を実行する。`review.json`で選択するテイクは1件にする。

```powershell
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -X utf8 AIvideo/local-runtime/summarize.py
```
