# 水ロケットの三次元外部流

生成した機体の無推力・固定姿勢に対し、空気が機体と4枚のフィンに与える力とモーメントを計算する。CUDA C++が格子上の時間発展を解き、Pythonは形状入力、GPUへの起動、出力を担当する。入力は[試作ハーネス](../bottle_prototype.md)の `assembly.json`。

## 再実行

NVIDIA GPU、CUDA 12のNVRTC、Python、NumPy、CuPy 13系が必要。既存のPython環境に対応した `cupy-cuda12x` を使う。WindowsでMATLAB付属のCUDAを使う場合、`CUDA_PATH` を MATLAB 配下の `sys/cuda/win64/cuda`、`CFD_CUDA_DLL_DIR` を `bin/win64` に指定する。リポジトリのルートで以下を実行する。出力先は各ケースごとに新しいディレクトリを指定する。

```sh
python scenarios/cfd/run_flow.py output/prototype/assembly.json output/cfd/sphere --shape sphere --sphere-re 100 --width 14 --upstream 7 --cells 16 --times 40
python scenarios/cfd/run_flow.py output/prototype/assembly.json output/cfd/rocket24 --shape recess --cells 24 --times 48
python scenarios/cfd/run_flow.py output/prototype/assembly.json output/cfd/angle5 --cells 16 --angle 5 --times 48
```

`history.csv` に無次元時刻・抗力・揚力・3方向の力・3軸モーメント、`case.json` に後半区間の平均と、その区間をさらに二分した平均の差を保存する。`slice.npz` は最終時刻の中央近傍の断面で、流れ方向・横方向の速度、圧力係数、固体マスクを含む。角度単位は度。流れは先端から尾部へ向かって +x、小さな正迎角では流入速度に +y 成分を与える。+z モーメントはこのとき機首を相対風へ向ける方向。力は胴体前面積と動圧、モーメントはこれに胴径を乗じて正規化する。モーメントの基準点は搭載物を含む乾燥時重心。

## 数値モデルと照合条件

等温・弱圧縮のD3Q19格子ボルツマン法。衝突時に非平衡の二次モーメントを再構成し、Smagorinskyモデル（機体でCs=0.16）により局所緩和時間を調整する。静止壁の跳ね返りリンクで運動量交換を積分する。横方向は周期境界、入口は一様平衡分布、出口は分布のゼロ勾配と手前2胴径の緩衝帯。正面風は15 m/s、動粘性係数は1.5×10⁻⁵ m²/s。胴径基準Re=90,000を合わせ、格子マッハ数は約0.13とする。球のRe=100ケースは乱流モデルを使わない。[正則化の原論文](https://arxiv.org/abs/physics/0506157)・[格子ボルツマン法の渦粘性モデル](https://arxiv.org/abs/comp-gas/9401004)

円錐・円筒・台形フィンの寸法は製作票から読み込む。フィンは流体リンクと交差する厚さゼロの固定板。曲面は直交格子上の階段近似で、スカート内部の現物形状は未測定。`recess` は内側に仮定した線形テーパと1セル厚の外筒、`flat` は平らな底面。格子変更時には外筒の表現厚も変わる。シールやテープ、紙のたわみ、噴流、自由回転を含まない。

空の領域での一様流保持、球の既知Cd、機体の格子依存性、横幅依存性、時間平均の前後差、正負迎角を別々に点検する。プロジェクトの目安はRe=100の球で相関値1.0917との差10%以内、機体で直近格子間と横幅変更のCd差5%以内、平均区間の前後差3%以内。これらは数値品質の目安で、実機の誤差保証ではない。実機形状・境界層・風洞／飛行データとの整合は別途必要。[球の検証ケース](https://mfix.netl.doe.gov/doc/mfix-exa/guide/latest/tutorials/fluid/steady-flow-around-sphere.html)
