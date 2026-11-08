# 3Dプリンターの実写：採用候補は5秒版

最新の編集指定により、6秒版の**先頭1秒を除いた5秒版**を作成した。追加の早送りはしていない。6秒版のフレーム30〜179を30fpsで使い、出力は150フレーム・5.0秒。全150フレームを元の6秒版と比較し、6秒版のハッシュが変わらないことも確認した。[5秒版の検証](print-insert-5s-verification.json)を参照。

ローカルの出力は `output/media/product-demo/generated/print-progress/printing-progress-5s.mp4`。共有用の[5秒版](../../assets/product-demo/previews/v1/printing-progress-5s.mp4)、[6秒版](../../assets/product-demo/previews/v1/printing-progress-6s.mp4)、[200倍速版](../../assets/product-demo/previews/v1/printing-progress-200x.mp4)も用意した。

```powershell
output/media-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/trim_print_insert.py
```

以下は保持している6秒マスターと元の切り出しの記録。

元の早送り映像から、初期層の造形中である1.5秒（フレーム15）〜転倒が始まる31.7秒の直前までを切り出した。最終採用フレームは316（31.6秒）。フレーム306〜324を連続した静止画で確認し、317で姿勢の崩れが見え始めるため、そのフレーム以降を含めない。

| 出力 | 内容 |
| --- | --- |
| `output/media/product-demo/generated/print-progress/printing-progress-6s.mp4` | 全302元フレームの範囲を均等に時間圧縮。800×600、30fps、180フレーム、6秒、無音 |
| `output/media/product-demo/generated/print-progress/printing-progress-200x.mp4` | 切り出した全区間。800×600、10fps、302フレーム、30.2秒、無音 |
| 同じ場所の`contact.jpg`、`last-upright-frame.png` | 時刻と元フレームの対応、最後の直立フレーム |

6秒版は30.2秒の区間を約5.033倍に早送りしている。元映像の公称200倍速と合わせて約1,007倍相当。元の撮影には再加熱時の約58秒の空白があるため、厳密に一定倍率の実時間記録ではない。映像内へ新しい造形画像を生成・補間していない。

[切り出しレシピ](print-progress-cut.json)と[検証記録](print-progress-verification.json)を保存。全482出力フレームをデコードし、元フレームとの対応と圧縮差を確認した。元映像のSHA-256は前後で一致。フルレンジの元映像の色範囲を引き継ぎ、保存メタデータから不要な作業名を除いた。最終フレームとコンタクトシートを目視した。実時間での通し再生は別の確認として未実施。

## 使う場面

SF調の「FABRICATION / 試作工程」枠に入れ、解析・CADから実物の試作へつなぐ5秒の挿入素材とする。元の解像度は800×600・4:3。1080pの中で枠に配置しても、元から1080pで撮影した映像とは扱わない。

対象は**既存2L PET v2のフィンの試作**。現在の仮台本にある1.5L・30m要求の案件との同一性は未確認なので、その案から自動製造した成果とは結び付けない。別試作の実機接続記録として表示する。

表示案は「フィンの印刷試作 / 実写・早送り」。切り抜きは印刷工程を見せるもので、完成品・強度・飛行性能の証明ではない。[元の試行記録](../../assets/print-trials/2026-11-06-fin-retry02/README.md)と全動画は保持し、切り抜き後もその結果を書き換えない。

## 再生成

```powershell
output/media-venv/Scripts/python.exe -X utf8 AIvideo/product-demo/tools/clip_print_progress.py
```

既存のメディア環境のPyAV、NumPy、Pillow、imageio-ffmpegを使う。プリンターへの接続・送信・開始・停止は行わない。
