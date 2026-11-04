# PET rocket v2 engineering videos

既存の2L PET試作v2のSTL、寸法、組立座標を使い、詳細設計の紹介と条件付き打ち上げ予測を映像化する。ユーザー指定により、未実測値は仮定として表示する。

## Data and physics

`source-data/`と`assets/`は、リポジトリの`research/ai-3d-print-workflow`、コミット`ecb270ead537073bfa38b110ac4e37f91de7161b`にある試作を固定したもの。ノーズとフィンは元STLをそのまま使い、3枚120度、ノーズ基部z=262mm、フィン後端z=100mmという元の組立座標を保つ。出典とハッシュは[provenance.json](provenance.json)。元データは変更しない。

外形のボトル径110mm・高さ315mmは未実測。コーンと3枚のフィンの約102.94gはCAD材料体積と仮定密度による値で、印刷重量ではない。ボトル55gと9mmノズル10gは既存カタログの暫定値。保持具6g、水0.66L、ゲージ圧300kPa、Cd=0.5、無風・鉛直・1mガイドは今回の仮定条件である。圧力条件は実機の使用許可値を示さない。

[simulate.py](simulate.py)は、水噴射、チョーク／非チョーク空気噴射、抗力と重力による上昇を連続した可変質量ODEで解く。断熱乾燥空気、準定常の有効ノズル面積を仮定する。角運動・水のスロッシング・凝縮・熱移動・弾性・固定部や回収装置の成立は計算しない。完全な鉛直対称状態に限定した最高点までの予測で、姿勢安定性や実飛行を実証するものではない。

[scenario.json](scenario.json)が入力条件、[simulation.json](simulation.json)が計算結果と限界、[trajectory-keyframes.csv](trajectory-keyframes.csv)が確認用の時系列。描画用の高密度データは`renders/trajectory.npz`へ保存する。現在は物理計算と4件のテストが完了し、映像を制作中。

```powershell
AIvideo/local-runtime/runtime/venv/Scripts/python.exe AIvideo/pet-rocket/simulate.py
AIvideo/local-runtime/runtime/venv/Scripts/python.exe -m unittest discover -s AIvideo/pet-rocket -p test_physics.py -v
```

NASAの[圧縮性流量とチョーク](https://www.grc.nasa.gov/www/k-12/airplane/mflchk.html)、[一般推力式](https://www.grc.nasa.gov/www/k-12/airplane/thrsteq.html)、[水ロケットの実験と計算の比較](https://www.grc.nasa.gov/www/k-12/rocket/BottleRocket/journey.htm)を参照。湿潤空気の影響は[Romanelliほかの論文](https://arxiv.org/abs/1211.1923)が扱っており、今回の乾燥断熱モデルの適用限界として残す。

コードと元の新規作成STLはリポジトリのMITライセンスに従う。映像はAI支援のシーン記述と物理ベースの3D描画で制作し、機体形状や軌道を拡散モデルで再生成しない。生成物と一時データは`renders/`へ保存し、Gitへ含めない。
