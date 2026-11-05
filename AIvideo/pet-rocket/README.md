# PET rocket v2 engineering videos

既存の2L PET試作v2を使った設計紹介と、条件付き打ち上げ予測の2本。未実測値は仮定として字幕とデータに明示している。無料のローカル環境で制作し、サービスの透かしは入れていない。

**最新の写実化版は[realism/README.md](realism/README.md)。** 写真由来の光と地面、透明PET、地上カメラで1080pへ作り直し、映像版と注釈付き版を保存した。以下は最初の技術説明版の記録。

| 完成物 | 内容 |
| --- | --- |
| [詳細設計の紹介](renders/pet_rocket_design.mp4) | 24秒。全体寸法、分解配置、フィン取付部、CAD材料質量と残課題 |
| [条件付き打ち上げ予測](renders/pet_rocket_launch_prediction.mp4) | 14秒。水噴射、空気噴射、慣性上昇、最高点。計算時刻と再生倍率を表示 |
| [視聴ページ](renders/index.html) | 2本を並べたローカル再生用HTML |
| [一式のZIP](renders/pet_rocket_v2_video_project.zip) | 動画、データ、シーン、スクリプト、検証記録 |

どちらも1280×720、24fps、H.264/AAC。日本語字幕と独自の合成音を使用し、音声ナレーションは含まない。生成物は`renders/`に保存しGitから除外しているため、GitHub上では再生用ファイルは取得できない。共有する場合はZIPを渡す。

## 設計データと仮定

`source-data/`と`assets/`は、コミット`ecb270ead537073bfa38b110ac4e37f91de7161b`の`3d model/prototypes/pet-rocket-coke-2l/`から固定したもの。出典とSHA256は[provenance.json](provenance.json)。ノーズとフィンは元STLを変更せずmm→mで描画し、3枚120度、ノーズ基部z=262mm、フィン後端z=100mmを保つ。組立の全長は365.9mm、最大幅214.4mm。

| 値 | 根拠・状態 |
| --- | --- |
| ボトル外径110mm、高さ315mm | 元設計の未実測の外形仮定 |
| ノーズ56.40g、フィン15.51g×3、合計102.94g | CAD材料体積×仮定密度1.24g/cm³。印刷重量ではない |
| ボトル55g、9mmノズル10g | 既存カタログの暫定値。適合は未確認 |
| 保持具6g、乾燥合計173.94g | 保持具は今回の質量枠。装置は未設計 |
| 水0.66L、初期ゲージ圧300kPa、流量係数0.9 | 今回の計算条件。実機の許容圧力を示さない |
| 軸方向Cd=0.5、無風、鉛直、1mガイド | 仮定条件。抗力の実測校正や姿勢計算はしていない |

ボトルとランチャーは仮の外観。ノーズの軟質キャップ、固定・保持、回収、全機のCG/CP・飛行安定性は未検証である。

## 条件付きの予測結果

[simulate.py](simulate.py)は、水噴射、チョーク／非チョーク空気噴射、重力と軸方向抗力を連続した可変質量ODEで解く。準定常の有効ノズル面積、乾燥空気の断熱変化を仮定する。水噴射終了は0.589秒、空気噴射終了は0.750秒、名目最高点は**28.34m、到達2.602秒**。映像は低速再生と静止を含む。

初期圧力±15%とCd=0.35〜0.70の9条件では最高点21.3〜36.7m。これは仮定を変えたシナリオ範囲で、統計的な信頼区間ではない。熱移動、凝縮、水の慣性・スロッシング、弾性、角運動、横風、回収を解いていない。完全な鉛直対称状態に限定した最高点までの予測で、実飛行の再現・安全性・飛行適格性を保証しない。

[scenario.json](scenario.json)が入力条件、[simulation.json](simulation.json)が結果と限界、[trajectory-keyframes.csv](trajectory-keyframes.csv)が計算の時系列、[launch-frame-data.csv](launch-frame-data.csv)が完成映像の時系列。描画には`renders/trajectory.npz`を使う。水滴は計算流量に対応した弾道表現であり、CFDや実測した飛沫ではない。

## 再生成と反復

このPCでは既存の分離Python環境とBlender 5.2.2 LTS、RTX4090を使用。依存ライブラリは[requirements.txt](requirements.txt)。Blenderには`bpy`とNumPyが付属する。字幕はWindowsの日本語システムフォントを参照し、フォント自体は配布しない。

リポジトリのルートから実行する例：

```powershell
$petPython = 'AIvideo/local-runtime/runtime/venv/Scripts/python.exe'
& $petPython AIvideo/pet-rocket/simulate.py
& $petPython -m unittest discover -s AIvideo/pet-rocket -p 'test_*.py' -v
& $petPython AIvideo/pet-rocket/render_all.py --samples 24
& $petPython AIvideo/pet-rocket/compose.py
$env:BLENDER_USER_RESOURCES = Join-Path (Get-Location) 'AIvideo/pet-rocket/renders/blender-user'
& 'C:/Program Files/Blender Foundation/Blender 5.2/blender.exe' --background --python-exit-code 1 --python AIvideo/pet-rocket/audit_scene.py
& $petPython AIvideo/pet-rocket/verify.py
& $petPython AIvideo/pet-rocket/audit_metadata.py
& $petPython AIvideo/pet-rocket/package.py
```

`render_all.py --blender <実行ファイル>`でBlenderの場所を変更できる。ZIPを別の場所へ展開した場合は、各スクリプトを展開先のパスで実行する。

条件を変える場合は`scenario.json`を編集して計算し直し、`render-settings.json`のフレーム出力先を新しくする。入力の指紋が違うキャッシュは再利用しない。設計紹介の中断再開は最初の未生成フレームから続ける。打ち上げの一部フレームが不足する場合は、実際の描画状態の全フレーム記録を保つため先頭から再描画する。既存キャッシュを初めて採用する`--reuse-verified`は、現在の入力での検証が成功したときだけ使える。設計説明は384枚の元フレームから各章の最後を2秒保持し、完成尺を24秒にしている。

`.blend`は形状と照明の保存シーンで、単独で全アニメーションを再生できるベイク済みファイルではない。動き・水量・粒子は`render_scene.py`と時系列データで再現する。

描画完了後は保存シーン内のファイル選択画面の絶対パスだけを相対化する。展開にはこのPCのGit for Windows付属libzstdを使い、DLL自体は配布しない。別環境では`audit_metadata.py --zstd-dll <ライブラリ>`で検査用ライブラリを指定できる。

## 検証と残る制限

物理・時間対応の6テスト、質量収支、刻み幅を半分にした最高点の収束、保存シーンと元STLの頂点・配置の比較が通過した。2本の全912フレームをデコードし、打ち上げ336フレームの描画状態と字幕値を照合。計算時刻・残水量・圧力の差は0、高度の最大差は約0.95µmであった。

[verification.json](verification.json)、[geometry-audit.json](geometry-audit.json)、[review.json](review.json)、[delivery-manifest.json](delivery-manifest.json)に検証範囲を保存。代表フレームとコンタクトシートで見た目を確認した。実時間の通し再生と実際の聴取は未実施で、音声は信号検査のみ。背景・装置・ボトルは近似CGであり、実写同等の写実性や実機との一致は主張しない。

ZIPには収録ファイルのハッシュ一覧を含め、展開後の一致と視聴ページの参照先を確認する。ZIP自体のハッシュと展開検査結果は、ZIPの外に生成される`archive-check.json`へ記録する。

## 出典と制作方式

NASAの[圧縮性流量とチョーク](https://www.grc.nasa.gov/www/k-12/airplane/mflchk.html)、[一般推力式](https://www.grc.nasa.gov/www/k-12/airplane/thrsteq.html)、[水ロケットの実験と計算の比較](https://www.grc.nasa.gov/www/k-12/rocket/BottleRocket/journey.htm)を参照。湿潤空気の効果は[Romanelliほかの論文](https://arxiv.org/abs/1211.1923)をモデルの限界として参照した。空の設定はBlender 5.2の[Sky Texture公式資料](https://docs.blender.org/manual/en/latest/render/shader_nodes/textures/sky.html)で確認した。

AI支援によるシーン記述、数値積分、原寸STLと物理ベース3D描画で制作した。形状や軌道に拡散モデルの変形を加えていない。コードと元の新規作成STLにはリポジトリの[MITライセンス](LICENSE)を保持する。水・空気噴射の音は独自合成で、実測音響ではない。
