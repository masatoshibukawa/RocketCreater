# PET rocket v2: photo-based rendering

既存の原寸STLと物理計算を保ち、簡略化した背景、均一な材質、機体と一緒に上昇するカメラを改める制作版。未実測値の条件は親ディレクトリのシナリオを引き継ぐ。

Poly Havenの写真由来HDRIとアスファルト素材を使用する。素材は[CC0](https://polyhaven.com/license)。公式APIを利用する取得スクリプトとURL・ハッシュを保存し、モデルや素材の独占的な権利は主張しない。

元のノーズとフィンの頂点を保持し、材質と法線の表示を調整した。ボトルの細かな凹凸や首のリングは未実測の外観表現である。簡略化した木・草原、青く見える水、機体と一緒に上昇するカメラを置き換えた。

## 完成映像

| ファイル | 内容 |
| --- | --- |
| [設計紹介・映像版](renders/pet_rocket_design_cinematic.mp4) | 16秒。作業台での全体、分解、フィン接写、全体へ戻る4章 |
| [打ち上げ予測・映像版](renders/pet_rocket_launch_cinematic.mp4) | 12秒。地上からの開始、水・空気噴射、望遠の上昇と最高点 |
| [設計紹介・注釈付き](renders/pet_rocket_design.mp4) | 寸法・CAD質量・未検証項目を表示 |
| [打ち上げ予測・注釈付き](renders/pet_rocket_launch_prediction.mp4) | 時刻・倍率・高度・速度・残水量・ゲージ圧を表示 |
| [視聴ページ](renders/index.html) | 映像版と注釈付き版、前版との比較 |
| [一式ZIP](renders/pet_rocket_v2_photographic.zip) | 動画、シーン、素材、元CAD、計算、再生成スクリプト |

全て1920×1080、24fps、H.264/AAC。サービスの透かしはない。映像版にも小さなCG表示を残し、音は独自の合成音とする。実飛行の撮影映像ではない。生成動画と写真素材はGitへ含めず、このPCの`renders/`、`cache/`へ保存している。

## 形状と計算の扱い

親ディレクトリの元STLと[シナリオ](../scenario.json)を使用。ノーズとフィンの頂点、3枚120°の配置、部品の取付高さは元データと照合した。薄いPET壁、水の透明度、首のリング、表面の細部、作業台とランチャーは見た目のための近似で、現物の測定結果ではない。

水0.66L、初期ゲージ圧300kPa、9mmノズル、無風・鉛直などの仮定条件を引き継ぐ。元と同じ計算で最高点28.34m、到達2.602秒。映像の12秒には開始前と最高点での静止、低速再生を含む。実機の許容圧力、全機の姿勢安定性、保持強度、回収成功は検証していない。水滴は質量流量に対応する弾道表現で、流体の破断や飛沫のCFDではない。

## 再生成と反復

リポジトリ内では、既存の`AIvideo/local-runtime/runtime/venv/Scripts/python.exe`を使う。ZIPを展開した場合は、親の`requirements.txt`を満たすPythonとBlender 5.2系を用意し、展開先のルートから実行する。`cache/`を同梱しているため、素材の再取得は通常不要。

```powershell
$petPython = 'AIvideo/local-runtime/runtime/venv/Scripts/python.exe'
& $petPython AIvideo/pet-rocket/realism/render.py --preview
& $petPython AIvideo/pet-rocket/realism/render.py
& $petPython AIvideo/pet-rocket/realism/compose.py
& $petPython AIvideo/pet-rocket/realism/check.py
& $petPython AIvideo/pet-rocket/realism/deliver.py
```

ZIPの展開先ではスクリプトを`realism/render.py`などの相対パスで指定する。Blenderの場所は`render.py --blender <実行ファイル>`と`check.py --blender <実行ファイル>`で指定できる。メタデータ検査はGit for Windowsの既存libzstdを参照し、DLL自体は配布しない。字幕はWindowsの日本語システムフォントを使い、フォントを配布しない。

`render.py --preview`は全体、フィン、水噴射、上空の5枚を出す。本編と別のプレビュー用ログに保存し、Blenderのハンドラ例外も検出する。元CAD・シナリオ・スクリプト・素材の指紋が変わったキャッシュは拒否する。条件を変えるときは古い`renders/`を比較用に別のフォルダへ保管し、新しく描画する。`.blend`は形状と照明のシーンであり、動きと水量はスクリプトと時系列データで再現する。

## 確認記録と限界

[geometry-audit.json](geometry-audit.json)で原寸STLと相対素材パス、[verification.json](verification.json)で4本の全1344フレーム・音声信号・打ち上げ288フレームの実際の描画状態を確認。[artifact-audit.json](artifact-audit.json)は保存シーン・動画・画像の不要な作業名や絶対パスを検査する。[delivery-manifest.json](delivery-manifest.json)は収録ファイルのハッシュ、ZIPの外に作る`archive-check.json`はZIPのハッシュと展開検査を記録する。

5枚の代表カット、完成ポスターと時間付きコンタクトシートを目視確認した。実時間の通し再生と実際の聴取は未実施で、音声は信号検査のみ。写真HDRIには完全な3D視差がなく、ボトルや装置の現物一致、実写同等の品質を保証するものではない。[review.json](review.json)に範囲を残す。

環境素材はPoly Haven（Andreas Mischok、Oliksiy Yakovlyev、Rob Tuytel）のCC0素材で、[asset-manifest.json](asset-manifest.json)に配布URLとハッシュを保存。コードと元の新規作成STLは親の[MITライセンス](../LICENSE)を保持する。AI支援によるシーン記述と数値計算、物理ベース描画で制作した。
