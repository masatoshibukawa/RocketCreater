# 空力レイヤー（`rocketwright/aero/`）

機体形状から空力係数（C_D、C_Nα、圧力中心、静安定余裕）を求める処理を、差し替え可能な窓口 1 つにまとめた層。プロダクトオーナーの決定（2026-11-05）に沿っている。

- 精度は今は問わない。「シミュレーターを 1 つ、拡張できる形で入れる」。
- 大きな係数表は事前に作らない。CFD はその場で回し、形状ごとに結果をキャッシュする。
- OpenFOAM ベースの [Model-Rocket-CFD-Pipeline](https://github.com/LouiseMcMahon/Model-Rocket-CFD-Pipeline) をバックエンドに採用する。

既定の動作は変わらない。`simulate_design` と `design_from_parts` は `aero_backend` を指定したときだけこの層を通る。

## 1. 構成

```
Design ─ rocketwright/geometry.py ─ STL（メートル、ノーズ先端が原点、+x が機尾側）＋寸法 dict
            │
AeroQuery(design, speed_mps, alphas_deg, cg_from_nose_m, extra, shape)
            │
registry.evaluate(query, backend="auto" | 名前)
   │   キャッシュ：sha256(バックエンド名, STL バイト列, 速度, 迎角, 設定, 組立形状) → $ROCKETWRIGHT_AERO_CACHE
   ├─ openfoam_pipeline（L2）  Docker の外部プロセス：snappyHexMesh + simpleFoam（k-ω SST）
   ├─ lbm_gpu（L2）            外部プロセス：scenarios/cfd/run_flow.py（GPU の格子ボルツマン法）
   └─ barrowman（L0）          今の定数（DEFAULT_CD）と Barrowman 式。常に使える
            │
AeroResult(cd, cn_alpha_per_rad, x_cp_from_nose_m, static_margin_cal, per_case, backend,
           fidelity, provisional, notes, source, ...)
```

- `auto` は使える CFD バックエンドを上から順に試し（`openfoam_pipeline` → `lbm_gpu`）、どれも使えないか失敗したら L0 に落ちる。理由は `notes` に残る。
- 新しいバックエンドは `AeroBackend` プロトコル（`name`, `fidelity`, `cacheable`, `available()`, `supports(design)`, `evaluate(query)`）を実装して `registry.register()` するだけでよい。
- CFD は同じ入力でも結果が少し変わる（§5）。キャッシュは再計算を省くだけでなく、値を固定する役目も持つ。
- キャッシュのキーに重心は含めない。質量が変わっても形状が同じなら解き直さず、静安定余裕だけ計算し直す。
- 報告書と図は `<キャッシュ>/artifacts/<id>/` に残す。OpenFOAM のケース本体は終了後に消す（`ROCKETWRIGHT_AERO_KEEP_RUNS=1` で保持）。

### 係数の基準

- `cd` などの基準面積は結果の `ref_diameter_m` の円。CFD は geometry の胴径（drawing.py の規則。1.5 L で 81.7 mm）、L0 は飛行モデルの抗力面積（`water.bottle_diameter_m`。1.5 L で 90 mm）。
- `cd_for_physics(result, design)` が飛行モデルの面積に換算する（抗力が同じになる換算）。`aero_cd_ratio` はこの換算後の値。
- `per_case[].cm` は `cm_ref_from_nose_m` まわりのモーメント係数。`cm = cn (x_cp − x_ref) / d`（OpenFOAM はノーズ先端、LBM は重心が基準）。

### 形状の割り切り（`# SIMPLIFICATION:`）

- bottle：drawing.py の規則（径 d = (4V/3.5π)^(1/3)、半楕円ノーズ 0.8d、胴 3.5d、ネック 0.3d）。ノズル端は閉じる。`BottleDesign` にフィン寸法がないので、drawing.py の代表形（4 枚、翼根 1.0d、翼端 0.35×翼根、スパン 0.8d、厚さ 2 mm）を仮定している。
- 組立形状（`AeroQuery.shape`）：`geometry.assembled_shape(plan["dimensions_mm"])` が作る `AssembledShape` を渡すと、上の規則の代わりに実機の外形を解く。`bottle_packet.side_view` の図と同じで、円錐ノーズ、スカート端までの直円筒、平らな底、フィンは底から `fin_tail_inset` 前。ノズルと底の凹みは閉じたまま。`dimensions_mm` にフィンの厚さがないので 2 mm を仮定している。形状は `BottleDesign` に持たせない（`Design` のスキーマがエージェントのツール定義に入るため）。
- bottle の重心は離床時の概算（乾燥質量は全長の中央、積載物はノーズ根元、水は胴の後端に詰めた円柱）。
- 胴とフィンは重なった別々の閉曲面。一体化はパイプライン側（manifold の和集合）が行う。
- 1 つの代表速度（bottle 15 m/s、amateur 50 m/s）で求めた C_D を飛行全体で一定として使う。

## 2. 使い方

```sh
# どのバックエンドが使えるか
uv run python scripts/aero_eval.py --status
# 1 形状を評価（AeroResult の JSON を表示）
uv run python scripts/aero_eval.py examples/designs/bottle.json --backend openfoam_pipeline --speed 15 --aoa 0 4
# 機体の STL だけ欲しいとき（単位はメートル）
uv run python scripts/aero_eval.py examples/designs/bottle.json --backend barrowman --stl /tmp/bottle.stl
```

エージェントのツールでは `simulate_design` / `design_from_parts` の `aero_backend` に `auto`・`barrowman`・`openfoam_pipeline`・`lbm_gpu` を渡す（`null` か `none` で無効）。結果には `metrics.aero_cd_ratio`、`aero_static_margin_cal`、`aero_x_cp_m`、出典つきの `warnings`、要約の `aero` が付く。

`run_dispersion` はこの層を通らない（design の `axial_drag_coefficient`、なければモジュールの定数 C_D を使う）。CFD の C_D を多数回試行に反映するには §7 のループの最終 design を渡す。

### OpenFOAM イメージの作成

リポジトリのルートで 1 回だけ実行する。ベースは ESI 公式の `opencfd/openfoam-default:2412`（Ubuntu 24.04）。

```sh
docker build -t rocketwright/openfoam-pipeline:2412 -f tools/aero/openfoam-pipeline.Dockerfile tools/aero
```

できるイメージは 1.92 GB。パイプラインはビルド時にコミット `b43605c` を clone する。実行時は `--cpus=8`（`ROCKETWRIGHT_OPENFOAM_CPUS`）、`--network=none`、呼び出したユーザーの uid で動き、45 分で打ち切る（`ROCKETWRIGHT_OPENFOAM_TIMEOUT_S`）。粗い格子の既定は `mesh.preset: coarse`、800 反復、後半 150 反復の平均。`--mesh-preset medium|fine` で変えられる。

### GPU LBM の準備

`scenarios/cfd/run_flow.py` は変更せず別プロセスで呼ぶ。CuPy の入った Python を用意する（プロジェクトの依存には入れない）。

```sh
uv venv -p 3.12 ~/tools/lbm-venv
VIRTUAL_ENV=~/tools/lbm-venv uv pip install numpy "cupy-cuda12x>=13,<14"
```

`~/tools/lbm-venv/bin/python` があれば自動で使う。別の場所なら `ROCKETWRIGHT_LBM_PYTHON` で指定する。

`assembly.json` は `lbm_gpu.assembly_for()` が設計から作る。カーネルの形状の範囲に収めるため、次の制約がある。

- 機体は「ノーズ＋直円筒＋平底」のみ（円錐は `--shape flat`、半楕円とオジャイブは `--shape rounded_flat`）。bottle の肩とネックは再現されない。
- フィンは厚さゼロの 4 枚固定。他の枚数は `supports()` が断る。組立形状の枚数は `evaluate()` が `ValueError` で断り、`auto` では理由を `notes` に残して次のバックエンドへ進む。組立形状の平面形は `assembly_for()` がそのままカーネルに渡すが、厚さは効かない。
- 領域が 15 胴径なので、全長 10 胴径を超える機体は断る。速度は 35 m/s まで、|α| は 15° まで（`run_flow.py` の制限）。

## 3. ライセンス

**Model-Rocket-CFD-Pipeline のリポジトリにはライセンスファイルがない（2026-11-05 確認、コミット `b43605c`）。** ライセンスがないコードは、著作権者の許諾なしに再配布できないものとして扱う。そのため：

- このリポジトリ（MIT）には同パイプラインのコードを一切コピーしない。入っているのは Dockerfile と、公開された CLI・設定ファイル・出力ファイルの形式に合わせて新規に書いた呼び出しコードだけ。
- パイプラインは各自のマシンで、イメージのビルド時に clone する。イメージは配布しない（レジストリに push しない）。
- `docs/aero/demo_bottle/` にあるのは、我々の形状を実行して生成された出力だけで、パイプラインのコードは含まない。
- 作者に確認してライセンスを付けてもらうのが望ましい。これは人間の判断事項とする。法的助言ではない。

OpenFOAM は GPL-3.0 で、[docs/simulators.md §4.3](simulators.md) の方針どおり別プロセスとして STL と設定ファイル・CSV でやり取りする。

## 4. 実測（`examples/designs/bottle.json`、1.5 L、15 m/s、α = 0°, 4°）

2026-11-05、Quadro RTX 5000、OpenFOAM は 8 CPU（共用機、負荷平均 13〜29）で実行。出力は [coarse 3 回目](aero/demo_bottle/report.md)、[medium](aero/demo_bottle/medium/report.md)。1・2 回目と LBM の結果は同じフォルダの `aero_result_*.json`。

| 手法 | C_D（胴径 81.7 mm 基準） | C_D（飛行モデル 90 mm 基準） | C_Nα /rad（81.7 mm 基準） | x_cp mm | 静安定余裕 cal（81.7 mm、重心 262 mm） | 到達高度 m | 実行時間 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| L0 Barrowman（今の定数） | 0.970 | 0.800 | 7.40 | 230 | −0.40 | 31.1 | 0 s |
| OpenFOAM coarse 1 回目（12.0 万セル） | 0.378 | 0.311 | 7.13 | 223 | −0.48 | 42.5 | 176 s |
| OpenFOAM coarse 2 回目（12.1 万セル） | 0.382 | 0.315 | 8.04 | 233 | −0.36 | 42.4 | 598 s（medium と同時実行） |
| OpenFOAM coarse 3 回目（12.1 万セル、保存した出力） | 0.378 | 0.312 | 7.13 | 223 | −0.48 | 42.5 | 174 s |
| OpenFOAM medium（42.9 万セル、壁面 3 層） | 0.355 | 0.292 | 8.34 | 237 | −0.31 | 43.2 | 1933 s（他の実行と同時） |
| GPU LBM（16 セル/胴径、簡略形状） | 1.031 | 0.850 | 9.39 | 239 | −0.28 | 30.4 | 51 s |

`AeroResult` の L0 の余裕は飛行モデルの径（90 mm）で割るので −0.36 cal になる。上の表は比べやすいように 81.7 mm にそろえた。

実測の参考値（機体が同じではない。あくまで目安）：

| 出典 | C_D | 条件 |
| --- | --- | --- |
| 渡辺ら 2004 表 3（[results.md](../scenarios/cfd/results.md)） | 0.253 | 別の模型（全長 463 mm、径 92 mm、丸いノーズ）、風洞 20 m/s、α = 0° |
| Fischer ら 2020（water.py のコメント、[simulators.md](simulators.md) [7]） | 0.6 ± 0.2 | 流線形の 1 L 機、風洞 |

到達高度は `water.simulate` に C_D（90 mm 基準）を渡した値。`simulate_design` の `aero_backend` でも同じ値になる（既定 31.1 m、OpenFOAM coarse 42.5 m、LBM 30.4 m を確認）。

読み取れること：

- **圧力中心はどの手法でも 223〜239 mm に収まった。** この設計では離床時の推定重心 262 mm より前にあり、水を積んだ状態の静安定余裕は全手法で負（−0.28〜−0.48 cal）。水が抜けた後の重心は 142 mm の概算で、余裕は約 +1 cal。重心の推定は粗いので、この符号を確定とはしない。
- **C_D は手法で約 2.7 倍ちがう**（胴径基準で 0.378 と 1.031）。RANS は圧力と摩擦が分かれて出る（coarse の α = 0° で圧力 0.24、摩擦 0.14 前後）。LBM は Uchida の検証どおり大きめに出る（階段状の表面、[results.md](../scenarios/cfd/results.md) では実測の約 3.2 倍）。どちらが正しいかは今回のデータでは判断できない。
- **到達高度は C_D の選び方で 30〜43 m に分かれる。** CFD の C_D を飛行計算に使うかどうかは、この差を承知のうえで決める必要がある。
- 実行時間は機械の混み具合で大きく変わる。coarse は同じ設定で 174〜598 s だった。

## 5. 精度についての注意

- **格子収束は確認していない。** 既定の coarse は胴径あたり約 10 セル、壁面の層なし、約 12 万セル。medium との差は C_D で 6 %、C_Nα で 4〜17 %。fine は実行していない。フィン厚 2 mm は coarse の表面セル 7.8 mm より薄い。流れの図でフィンの外形は残っているが、厚みと前縁は解像できていない。絶対値は目安で、同じ設定の形状どうしの比較に使う程度にとどめる。
- **同じ入力でも結果が一致しない。** 同じ STL と設定で 3 回実行すると、格子のセル数が 120,030／120,506／120,569 と変わり、C_D は 0.378〜0.382（約 1 %）、C_Nα は 7.13〜8.04（13 %）、x_cp は 223〜233 mm、余裕は −0.48〜−0.36 cal とばらついた。原因は特定していない（並列の snappyHexMesh が疑わしいが未確認）。CLAUDE.md の「決定的に動くこと」を CFD 単体では満たさないので、**再現性はキャッシュで担保する**（1 回解いた値を以後ずっと返す）。キャッシュを消すと値が変わりうる。C_Nα と余裕の差を議論するときは、この幅より小さい差を意味のある差として扱わない。
- 完全乱流の定常 RANS で、ノーズの層流域がない。底面の後流は定常解法では振動しうる。`notes` の未収束の表示を確認すること。今回の α = 0° は coarse でも 800 反復で残差の基準に届かなかった（C_D の変動は 0.01 % 未満）。
- 対称な機体なのに α = 0° で C_N が −0.05〜+0.01 になる（格子の非対称とみられる）。`--aoa -4 0 4` にすると打ち消せる（ケースが 1 つ増える）。ただし α = 4° の C_N 自体も coarse の 3 回で 0.448〜0.536 と動くので、これだけでは上のばらつきは消えない。
- 渡辺らの 0.253 も Fischer らの 0.6 も別の機体の値で、今回の形状の検証にはならない。この表は「桁が合っているか」の確認であり、係数の校正には使っていない。
- 結果はすべて `provisional: true`。

## 6. テスト

`tests/test_geometry.py`、`tests/test_aero.py`、`tests/test_aero_loop.py`。Docker と GPU は使わない（CFD は偽物のバックエンドか、実行で得た出力ファイル `tests/fixtures/aero_openfoam/` で置き換える）。

## 7. 飛行 → CFD → C_D → 飛行 → 設計更新のループ

`rocketwright/aero/loop.py` の `run_aero_loop()`。bottle の設計だけが対象。

1. 今の design（圧力、C_D）で飛ばす（`water.simulate`）。
2. その飛行の最大速度を 1 m/s に丸めて CFD を解く。丸めるのは、近い飛行どうしでキャッシュを共有するため。
3. `cd_for_physics()` で飛行モデルの基準面積（90 mm）の C_D に直す。
4. 候補の圧力のうち、新しい C_D で目標高度に最も近いものへ design を更新する。
5. C_D の変化が 2 % 未満で、かつ圧力が変わらなければ収束。そうでなければ 1 に戻る（既定で最大 6 周）。

`# SIMPLIFICATION:` 1 つの速度（最大速度）の C_D を飛行全体に使う。更新するのは圧力だけで、充填率、ノズル、機体はそのまま。

`auto` は 1 周目で決まったバックエンドに固定する。2 周目以降に別の解法へ落ちると、解法の差が C_D の変化に混ざり、L0 なら設計の C_D を返すだけなので見かけ上の収束になるため。固定後に失敗したらループはそのエラーで止まる。解いた分はキャッシュに残るので、やり直しは続きから進む。

### 校正の組について

**`water.py` の C_D 0.8 は、空気噴射の効率 0.25 と組で、`catalog/references/bottle.yaml` の 5 回の飛行の実測に合わせた値（`scripts/calibrate_small_rockets.py`、高度の RMS 誤差 18.9 %）である。** 空気の噴射が実際より弱いぶんと抗力が実際より大きいぶんが、高度の上で打ち消し合っている可能性がある。C_D だけを CFD の値に替えると、この組が崩れる。

- ループの高度と圧力は、校正された予測ではない。CFD の C_D が小さいほど高く飛ぶと計算され、圧力は下がる方向に動く。その圧力で実機が目標に届く根拠はない。
- 対応するには、CFD の C_D を固定して効率を実測に合わせ直す必要がある。今回はやっていない。
- そのため結果には校正の注意が `notes` として必ず付き、ワークベンチでも確認済みの案を置き換えず併記するだけにしている。製作ファイルは確認工程の design のまま。

### 実機の形状

`geometry.assembled_shape(plan["dimensions_mm"])` が作る `AssembledShape` を `AeroQuery.shape` で渡す（§1）。外形は STL に入り、STL のバイト列と `repr(shape)` がキャッシュのキーに入るので、フィンの幅や厚さを変えれば解き直しになる。形状を渡さない問い合わせのキーは今までと同じ。

| バックエンド | 組立形状の扱い |
| --- | --- |
| `openfoam_pipeline` | 実機の外形の STL を解く |
| `barrowman` | 円錐ノーズと実機のフィンで C_Nα と x_cp を計算する。`plan["cp_mm"]` と一致する。C_D は設計の値のまま |
| `lbm_gpu` | 平面形はカーネルに渡す。厚さは解けないので結果の `notes` にその旨を残す。4 枚以外は断る |

### 実行

```sh
uv run python scripts/aero_loop.py --action D02/9/325/25/carton_wide --backend openfoam_pipeline
uv run python scripts/aero_loop.py examples/designs/bottle.json --target 30 --backend barrowman
```

`--json` で結果全体を書き出す。収束しなければ終了コード 1。設計ファイルは変更しない。画面の案には `POST /aero/loop`、ワークベンチのプロジェクトには `POST /workbench/projects/{id}/aero-loop`（[integration.md](integration.md)）で、確認済みの案に対して実行する。バックエンドは環境変数 `ROCKETWRIGHT_AERO_BACKEND`（既定 `auto`）。確認工程と同じ `n`、`seed` で最終 design の `run_dispersion` も回す。

### 実測（ワークベンチの採用案 D02、紙製フィン幅広、325 kPa、充填率 25 %）

2026-11-06、OpenFOAM coarse（19.8 万セル、表面セル 5.96 mm、壁面の層なし、8 CPU）、実機の外形（全長 572 mm、径 90 mm、フィンは翼根 70、翼端 35、スパン 140、後退 35 mm）、水を積んだ重心 428 mm。目標 20 m。

| 周 | 飛行の圧力 kPa | 飛行の C_D | 高度 m | 最大速度 m/s | CFD の速度 m/s | CFD の C_D | C_D の変化 | x_cp mm | 余裕 cal | 更新後の圧力 kPa | 更新後の高度 m | 経過 s | キャッシュ |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | 325 | 0.828 | 19.46 | 20.69 | 21 | 0.595 | 28.2 % | 461 | +0.36 | 325 | 20.76 | 147 | なし |
| 2 | 325 | 0.595 | 20.76 | 20.82 | 21 | 0.595 | 0 % | 461 | +0.36 | 325 | 20.76 | 0.6 | あり |

2 周で収束。L0（同じ形状）は C_Nα 14.4 /rad、x_cp 463 mm、余裕 +0.38 cal で、CFD は C_Nα 16.3 /rad、x_cp 461 mm、余裕 +0.36 cal。隣の圧力は 300 kPa で 19.00 m、350 kPa で 22.48 m なので、325 kPa のまま。

`final_design`（C_D 0.595、325 kPa）の `run_dispersion`（n = 64、seed = 77131）は 59/64 = 92.2 %、高度の p05/p50/p95 は 18.9/20.6/22.6 m。確認工程の値（C_D 0.828）は同じ 59/64 で、17.8/19.3/21.0 m。

読み取れること：

- **実機の C_D 0.595 は、代表形の 0.312（§4）の約 2 倍。** 平らな底と幅広のフィンの効果とみられるが、分けて調べてはいない。圧力抵抗 0.434、摩擦 0.161（α = 0°）。ノズルとスカートの凹みは閉じた面として扱っている。
- **この収束は 2 周目がキャッシュに当たったことによる。** 最大速度が 20.69 と 20.82 m/s で、どちらも 21 m/s に丸まった。C_D の速度依存は確かめていない。
- **2 % の判定はループの止め方で、CFD の精度ではない。** §5 のとおり同じ入力でも C_D は約 1 %、coarse と medium の差は 6 % あった。この形状の medium は実行していない。フィン厚 2 mm は表面セル 5.96 mm より薄い。
- α = 0° で C_N が 0.064（§5 の格子の非対称とみられる）。x_cp は 2 点の傾きなので、余裕の +0.36 と +0.38 の差に意味はない。どちらも 1 cal の目安を下回る。
- 高度 20.76 m は校正の組を崩した値なので、確認工程の 19.46 m より正しいとは言えない。
