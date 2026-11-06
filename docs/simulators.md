# ロケット飛行シミュレーターと空力解析の調査（RocketWright 用）

調査日：2026-11-04。外部ツールについての記述は、本文末の「出典」の URL で確認できたものだけを書いた。
確認できなかった事項は **未確認** と明記する。計算時間のうち「実測」と書いたもの以外はすべて **推定** である。

## 1. 目的と結論

- **飛行計算は今の Python（scipy `solve_ivp`）のままでよい。** 1 回の飛行は 13〜113 ms、n=100 の多数回試行は 0.3〜2.1 s（このワークステーションで実測、§6）。富岳もワークステーション級の並列計算も要らない。C++/Fortran で書き直しても、精度は上がらない。
- **精度の律速は積分器ではなく空力係数**（一定の C_D、亜音速 Barrowman、迎角ゼロ）。締切（2026-11-08 20:00 JST）までにやるべきなのは、次の 3 つ。(1) 静安定余裕を「飛行中の最小値」で評価する。(2) マッハ数に応じて C_D と C_Nα を補正する（Prandtl–Glauert）。(3) MIT ライセンスの RocketPy で amateur 段階をクロスチェックする。CFD は入れない。
- **フィンと外形の流体解析は「速い工学的手法を飛行計算の中で、CFD はオフラインで係数表を作るだけ」という 2 層構成にする。** 実際の運用では、低速（ボトル・モデルロケット）は Basilisk（C、GPL-3.0）または SU2 の非圧縮ソルバー、遷音速以上は SU2（C++、LGPL-2.1）を使う。メッシュは gmsh（pip で入る）で作る。ハッカソン後の課題とする。
- 公開されている水ロケットのシミュレーターは複数あるが、**ソースを公開していて、かつ実測飛行との誤差を公表しているものは見つからなかった。** 実測と比べた誤差を公表しているのは論文のモデルだけ（Barrio-Perotti ら 2010、最大で約 6 %）。

## 2. 用語と基礎

### 2.1 弾道の常微分方程式

**3 自由度（質点）**：位置 r と速度 v だけを解く。我々の 3 モデルはすべてこの方式（`multistage` は鉛直面内の 2 次元）。

```
m dv/dt = T e_T − ½ ρ |v_a| v_a C_D A_ref + m g,   dm/dt = −ṁ,   v_a = v − v_wind
```

機体軸は対気速度ベクトルに一致させる（迎角 α = 0）。そのため、法線力・圧力中心・減衰は運動に現れない。安定性は別途「静安定余裕」として判定するしかない。

**6 自由度**：姿勢（四元数など）と角速度 ω を加える。

```
I dω/dt + ω × (I ω) = M_aero,
M_aero ≈ −N (x_cp − x_cg) e_⊥ + ½ ρ V² A_ref d · C_mq · (q d / 2V),   N = ½ ρ V² A_ref C_Nα α
```

ここで α が初めて状態量になり、風見効果・風への突っ込み（weathercocking）・振動とその減衰が計算できる。OpenRocket・RocketPy・CamPyRoS・ForRocket は 6 自由度である。

### 2.2 空力係数が入る場所

| 係数 | 意味 | 3 自由度での扱い | 6 自由度での扱い |
| --- | --- | --- | --- |
| C_D（C_A） | 抗力（軸力）係数。M、Re、α で変わる | 運動方程式に直接入る（唯一の空力入力） | 同じ |
| C_Nα | 法線力傾斜 ∂C_N/∂α | 使わない（安定余裕の計算にだけ使う） | 復元力 |
| x_cp | 圧力中心（ノーズ先端からの距離） | 静安定余裕の計算にだけ使う | 復元モーメントの腕 |
| C_mq（C_mq + C_mα̇） | ピッチ減衰 | 使わない | 振動の減衰。短く軽い機体で重要 |

### 2.3 静安定余裕と、それを飛行全体で評価すべき理由

静安定余裕は `SM = (x_cp − x_cg) / d`（単位は口径 cal）。合格基準は CLAUDE.md の ≥ 1.5 cal。SM は機体に固有の定数ではなく、飛行中に変わる。

- **重心が動く**：固体モーターの推進剤や水が抜けると x_cg が前へ移る（後端に重いものがある通常の配置では SM が増える）。ただし、積載物やバラストの位置によってはこの向きが逆になることもあり、一般には最小値が離床時に来るとは限らない。
- **圧力中心が動く**：x_cp はマッハ数と迎角で動く。OpenRocket 技術文書には、フィンの圧力中心は M > 0.5 あたりから後退し始め、M > 2 では別の式になると書かれている（同文書 3.2 節）。
- **我々の現状**：`stability.py` が評価しているのは離床時（モーター満載）の 1 点だけ。`water` には安定性の計算がまったくない（`has_fins` の真偽値だけ）。

### 2.4 空力係数の求め方：計算の重さ順

- **Barrowman 法**（1966–67 年）：細長い機体、小さい迎角、亜音速、平板フィンを前提にした閉形式の式。ノーズの C_Nα は 2、円筒胴体は 0、フィンには胴体との干渉係数を掛ける。圧力中心は各部の C_Nα による加重平均。
- **拡張 Barrowman 法**（OpenRocket）：大迎角での胴体揚力、任意のフィン形状、遷音速・低超音速への拡張を加える。抗力は積み上げ（摩擦・圧力・底面・フィン）で求める。OpenRocket 技術文書の結論では、亜音速で x_cp と C_D の精度は約 10 %、少なくとも M 1.5 までは妥当と見込まれている。
- **VLM（渦格子法）・パネル法**（AVL、VSPAERO）：非粘性・線形のポテンシャル流。フィンのような薄い揚力面に強い。胴体は AVL ではソース・ダブレット線で近似する。安定微係数（減衰微係数を含む）が出せる。AVL は亜音速の Prandtl–Glauert 補正まで。VSPAERO は薄翼モードで超音速を扱えるが、体積による造波抵抗と衝撃波は捉えないと開発者が述べている（2015 年の投稿）。
- **CFD**：Euler（非粘性・圧縮性。衝撃波は出るが摩擦抵抗は出ない）、RANS（乱流モデルつき。抗力と剥離の工学的な標準）、LES と LBM（非定常。後流や剥離の再現性が高い代わりに重い）。
- **圧縮性補正**：線形理論では亜音速で `C_Nα(M) ≈ C_Nα(0)/β`、`β = √(1 − M²)`（Prandtl–Glauert）、超音速で `β = √(M² − 1)`（Ackeret）。M ≈ 0.8〜1.2 の遷音速ではどちらも成り立たない。

### 2.5 精度と計算コストの目安（1 評価＝1 形状・1 飛行条件）

| 手法 | 1 評価の時間 | 得られるもの | 弱点 |
| --- | --- | --- | --- |
| Barrowman（我々の `stability.py`） | 1 ms 未満（推定） | C_Nα、x_cp | 亜音速・α≈0 のみ。抗力は出ない |
| 拡張 Barrowman と抗力の積み上げ | 1〜10 ms（推定） | C_Nα、x_cp、C_D(M, Re) | 遷音速は経験式頼み |
| VLM（AVL） | 0.1〜1 s（推定） | 揚力面の C_Nα、安定微係数 | 非粘性。胴体は粗い近似 |
| パネル法（VSPAERO） | 数秒〜数分（推定） | 機体全体の圧力分布 | 粘性・造波抵抗は近似 |
| Euler CFD、3 次元 10⁶ セル（SU2） | 10〜60 分、40 スレッド（推定） | 衝撃波を含む C_N、x_cp、圧力抗力 | 摩擦抵抗が出ない |
| RANS CFD、3〜10×10⁶ セル（SU2・OpenFOAM） | 1〜10 時間、40 スレッド（推定） | C_D を含む全係数 | メッシュ作りが手間。遷音速は収束が難しい |
| LBM-LES、GPU 10⁸ セル（FluidX3D） | 数分〜数十分、RTX 5000（推定） | 非定常の抗力 | 低マッハ前提。ライセンスの問題（§3.3） |
| LES・DES の大規模計算 | 数日〜（推定） | 剥離・底面流れ | スパコン向け |

1 回の飛行は数千ステップの右辺評価からなる。そのため、毎ステップで CFD を回すことは原理的にできない（§4）。

## 3. 既存シミュレーター一覧

対象の凡例：bottle＝水ロケット、model＝モデルロケット、HPR＝ハイパワー・学生ロケット、orbital＝軌道投入機。

### 3.1 水ロケット

| 名前 | 対象 | 言語 | ライセンス | 物理モデル | 精度の公開検証 | URL | 我々の使い道 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Dean Wheeler「Sim Water Rocket」（BYU） | bottle | Java アプレット（Java 1.1。現行の Chrome・Edge では動かない） | 未確認（利用規約ページのみ。OSS の表記なし） | ランチチューブ・水噴射・ガス噴射の 3 相。T ノズル対応。推力効率の既定値は 0.97。飛行安定性は扱わない | 実測との比較は掲載なし。「1 回打ち上げて C_D を合わせよ」と推奨 | [1] | ランチチューブ相の物理の参考。C_D を合わせる運用は我々の較正と同じ考え方 |
| Clifford Heath「Water Rocket Simulation」 | bottle | Web フォーム（実装言語は未確認） | 未確認（ソースの記載なし） | 飛行全体を数値計算。空気噴出は Berggren の式による瞬時の力積。ランチチューブ、ノズル損失係数あり。C_D は入力（目安 0.1〜0.5） | 記載なし | [2] | 空気噴出を瞬時の力積とする点は我々の `AIR_IMPULSE_EFFICIENCY` と同じ近似 |
| NASA Glenn「Water Rocket Simulator」（BottleRocketSim） | bottle（教育用） | 未確認（試作版。事前の「インストール」が必要） | 未確認 | 未確認 | 記載なし | [3] | なし |
| Water Rocket Toolbox（`waterRocketSim`） | bottle | Python | 未確認 | 噴出速度はベルヌーイ式またはトリチェリの式。陽的 Euler 法で Δt = 0.01 s | 記載なし | [4] | 参考程度 |
| JAXA「水ロケットシミュレーター」（iPad、2013 年） | bottle（教育用） | 非公開 | 無料アプリ | 非公開（ノーズ 3 種・フィン位置・水量・角度・圧力を選ぶ） | 記載なし | [5] | なし |
| Barrio-Perotti ら（2010、Eur. J. Phys. 31 1131、論文） | bottle | コードではない | 論文はオープンアクセス | 質量・運動量・エネルギー保存と空気の熱力学関係 | 野外試験との差は最大で約 6 %（要旨。二次資料経由で確認） | [6] | **次の実測参照データの候補。** 我々のモデル改良（空気相）の手本 |
| Fischer ら（2020、arXiv:2001.08828、論文） | bottle | コードではない | arXiv | 相ごとの解析近似を Runge–Kutta の参照解と比較。C_D を理論推定し風洞で確認 | 「参照データからわずかにずれるだけ」（定量値は本文） | [7] | **既に `bottle.yaml` の参照飛行 4 件として使用中** |
| Hortman（2017、CWU 修士論文、Excel） | 未確認（水ロケットかモデルロケットか不明） | Excel | 未確認 | 未確認 | 「較正係数を使って最高高度を 95 % 信頼で 5.773 % 以内」 | [8] | 較正係数を前提にした精度である点に注意 |

**質問 (b) への答え**：水ロケットのシミュレーターは存在する。ただし、(i) 物理モデルを文書化していて、(ii) ソースが入手でき、(iii) 実測飛行との誤差を公表している、の 3 つを満たすものは見つからなかった。公開されている精度は論文のモデル（約 6 %、Barrio-Perotti）と、較正係数を前提にした Excel モデル（5.8 %）だけ。各ツールが C_D の当てはめを推奨していることからわかるとおり、**水ロケットの頂点高度の誤差は C_D と空気相の扱いで決まる**。我々は較正したうえで RMS 18.9 %（§5）。

### 3.2 弾道・軌道（モデルロケット〜軌道投入機）

| 名前 | 対象 | 言語 | ライセンス | 物理モデル | 精度の公開検証 | URL | 我々の使い道 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| OpenRocket | model・HPR | Java | GPL-3.0 | 6 自由度。拡張 Barrowman と抗力の積み上げ。ロール | 技術文書 6 章：小型機で頂点 +16 %・+7 %、ハイブリッド機で −16 %。x_cp と C_D は亜音速で約 10 % | [9][10] | CLAUDE.md §7 の比較基準値づくり（GUI で人手）。手法の教科書 |
| RocketPy | HPR | Python | **MIT** | 6 自由度、可変質量。Barrowman（任意）。抗力曲線は CFD などから読み込める。Monte Carlo。多段 | J. Aerosp. Eng. 論文。README では頂点の誤差 +0.45 %（EPFL）、−0.75 %（NDRT）の 2 例 | [11] | **amateur 段階のクロスチェック（pip で入り、MIT で両立）** |
| AeroVECTOR | model（推力偏向制御） | Python | GPL-3.0 | 平面 3 自由度（並進 2＋ピッチ）。拡張 Barrowman と独自修正。亜音速 | 記載なし（技術文書 PDF は未読） | [12] | 参照のみ |
| CamPyRoS | HPR | Python | GPL-3.0 | 6 自由度、Monte Carlo、空力加熱 | 未確認 | [13] | 2021 年 7 月以降更新なし。不採用 |
| ForRocket（Susumu Tanaka） | HPR・多段 | C++（Boost・Eigen・makefile からの推定。言語表示は未確認） | **MIT** | 6 自由度。液体・固体・ハイブリッド。分離・投棄のイベント。C_A(M) などを CSV 表で入力 | 未確認 | [14] | C++ の 6 自由度ソルバーの候補（別プロセス、JSON 入力・CSV 出力） |
| OpenTsiolkovsky（インターステラテクノロジズ） | 観測ロケット・軌道 | Rust（旧 C++ 版はタグで保存） | **MIT** | 3 自由度の質点。WGS84、J2、USSA76、風。Monte Carlo で落下楕円 | 未確認 | [15] | `multistage` と同じ粒度の比較対象。J2 と自転の参考 |
| TrajecSimu（PLANET-Q） | HPR（ハイブリッド） | Python | MIT | 6 自由度、遷音速、制御なし | 未確認（v3.0 は 2018 年） | [16] | 日本の学生ロケットの例。参照のみ |
| JSBSim | 航空機一般 | C++ | LGPL-2.1 | 6 自由度の飛行力学（XML で機体を定義）。`pip install jsbsim` | ロケットの例は未確認 | [17] | 不要 |
| WRASP | model | C・C++（Windows） | GPL-2.0 | 1 自由度 | 記載なし（最終更新 2013 年） | [18] | なし |
| RASAero II | model〜観測ロケット | 非公開 | 無料・非オープンソース（第三者の記述。配布元ページでは未確認） | M 0.01〜25 の空力予測と飛行計算 | 開発元：頂点の平均誤差 3.47 %、±10 % 以内が 80.6 % | [19] | 遷音速・超音速の C_D の手動比較（ハッカソン後） |
| Missile DATCOM | ミサイル | 未確認 | ITAR による制限（Wikipedia） | 半経験的な成分積み上げ | — | [20] | 使用不可（入手も配布も不可） |

日本の大学の公開シミュレーター（東大・東工大・九大 CORE など）は、組織名で GitHub を探しても見つからなかった（**未確認**）。確認できた日本発のものは ForRocket、OpenTsiolkovsky、TrajecSimu、MatRockSim（MATLAB）。

### 3.3 空力・流体解析（フィンと外形の評価用）

| 名前 | 対象 | 言語 | ライセンス | 物理モデル | 精度の公開検証 | URL | 我々の使い道 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| AVL（Drela・Youngren、v3.52、2025-09） | 揚力面（フィン） | Fortran＋C（ビルド要件から） | GPL（版は未確認。OptVL は「AVL は GPL v2」と記載） | VLM、細長い胴体のソース・ダブレット線、亜音速 Prandtl–Glauert、安定微係数、固有モード | 未確認 | [21] | フィンの C_Nα と C_mq の照合（Linux 用バイナリ 3.40b あり、別プロセスで呼ぶ） |
| OptVL | 同上 | Python＋改変 AVL | GPL（README では v3 に更新） | AVL＋自動微分による微係数 | — | [22] | `pip install optvl` は cp312 の Linux wheel で入る（dry-run で確認）。ただし同一プロセスへの import になる（§4.3） |
| OpenVSP / VSPAERO（v3.55.0） | 航空機の形状と空力 | C・C++ | NASA Open Source Agreement 1.3 | VLM・パネル法。超音速は薄翼モードのみ。`-stab` で安定微係数 | 未確認 | [23][24] | 形状の作成と VLM。配布 .deb は Ubuntu 24.04・26.04 用で、**このマシン（20.04）ではソースからのビルドが必要**。pip パッケージはない |
| SU2（v8.x） | CFD | C++ | **LGPL-2.1** | 圧縮性 Euler・NS・RANS、非圧縮（`INC_*`）、非平衡（NEMO）、離散随伴による形状最適化 | 個別の数値は未確認 | [25][26] | **遷音速・超音速のオフライン係数表。** Linux のシリアル版バイナリあり（MPI 版は MPICH が必要。配布バイナリには随伴なし） |
| OpenFOAM | CFD | C++ | GPL-3.0 | 有限体積法のツール群。圧縮性は `rhoCentralFoam`（KNP スキーム）など。メッシャー `snappyHexMesh` | ロケット形状 STL の公開手順は見当たらず | [27][28] | SU2 の代替。設定量が多く、締切内には不向き |
| Basilisk | CFD | Basilisk C（C99＋`qcc`） | GPL-3.0 | 適応四分木・八分木。centered NS、埋め込み境界（`embed_force()` で圧力抗力と粘性抗力）、`compressible.h`（**非粘性 Euler のみ**）、`all-mach.h`、GPU 実行あり | 未確認 | [29][30][31] | **唯一の純 C の選択肢。** 低速（ボトル・モデルロケット）の抗力と後流。RANS 乱流モデルと MPI の対応は未確認 |
| FluidX3D | CFD | C++・OpenCL | **独自ライセンス：商用利用・軍事研究・AI 学習への利用を禁止** | LBM（SRT・TRT）、Smagorinsky LES、STL のボクセル化、力・トルクの計算 | 未確認 | [32][33] | **不採用（MIT のリポジトリに同梱できない。利用条件も強い）** |
| gmsh（v4.15.2） | メッシャー | C++（Python API あり） | GPL-2.0 以降 | OpenCASCADE で CAD 形状を作成。四面体メッシュ。SU2 形式で出力 | — | [34][35] | `pip install gmsh` は manylinux wheel で入る（dry-run で確認。CLI の `gmsh` も同梱） |

## 4. 流体解析（フィンと外形の評価）

### 4.1 正直な構成

1 回の飛行は右辺評価が数千回（`solid` は Δt ≤ 0.02 s で約 17 s の飛行）。CFD は 1 条件で数十分〜数時間かかる。したがって、**CFD を常微分方程式の各ステップで回すことはできない。** 業界の標準は次の 2 層構成。

1. **飛行計算の中（ミリ秒）**：Barrowman・拡張 Barrowman・抗力の積み上げで C_D(M, Re)、C_Nα(M)、x_cp(M) を求める。フィンだけなら事前の VLM でもよい。
2. **飛行計算の外（オフライン、時間単位）**：CFD で `C(M, α, 形状パラメータ)` の表を作る。または工学式の検証・補正係数づくりに使う。常微分方程式は表を補間するだけ。

### 4.2 段階ごとの推奨（このワークステーションでの所要時間は推定）

| 段階 | 流れの特徴 | 飛行計算の中 | オフライン CFD | 1 ケースの推定時間 |
| --- | --- | --- | --- | --- |
| bottle | V ≈ 30 m/s、d ≈ 0.09 m → M ≈ 0.1、Re ≈ 2×10⁵。非圧縮。鈍頭で剥離が支配的 | C_D の形状テーブル（流線形／鈍頭）。Barrowman で SM | Basilisk（centered NS＋`embed`、適応格子）または SU2 `INC_RANS` | 軸対称 2 次元で数分〜30 分、3 次元で 1〜数時間 |
| amateur | 例の設計で最高速度 337 m/s（≈ M 1.0、実測値）→ **遷音速に入る** | 拡張 Barrowman と抗力の積み上げ、Prandtl–Glauert 補正 | SU2 `EULER`（x_cp と造波抵抗）と `RANS`（C_D） | Euler で 10〜60 分、RANS で 1〜10 時間、40 スレッド |
| commercial・heavy | M 0〜25。抗力損失は全増速量の数 %（推定、`multistage` の増速量内訳で確認可） | 今の C_D(M) 表で十分（構想設計の粒度） | 不要（必要なら SU2 の Euler で数点） | — |

3 次元 RANS の係数表（M 10 点 × α 5 点 × 形状 10 種 = 500 ケース）は、1 ケース 2 時間とすると約 1000 時間（推定）。このマシン 1 台では 1.5 か月かかる。**現実的なのは、「工学式を CFD 数ケースで検証して補正係数を作る」か、「設計変数を 2〜3 個に絞った小さな表」**。ここで初めて、より大きな計算機を検討する意味が出る（§6）。

### 4.3 ライセンス上の注意（法的助言ではない）

- 本リポジトリは MIT。GPL のプログラム（OpenFOAM、Basilisk、AVL、gmsh）を**別プロセスとしてコマンドラインとファイルでやり取りする**のは、GNU の FAQ が「通常は別々のプログラム間の通信手段」と説明する形態であり、我々のコードを GPL にする必要は通常生じないと解釈されている。同じ FAQ は「共有アドレス空間でリンクして動くよう設計されたモジュールは、ほぼ確実に一つのプログラムになる」とも述べ、やり取りが「複雑な内部データ構造を交換するほど密接」なら別プロセスでも結合とみなされうる、としている[36]。
- したがって：GPL のバイナリやソースを**同梱しない**。**import しない**（`gmsh` や `optvl` の Python API は同一プロセスにライブラリを読み込むので、別プロセスのスクリプトに隔離する）。入出力はメッシュファイルと係数の CSV にとどめる。
- SU2 は LGPL-2.1 なので、動的リンクでも条件は緩い。ただし我々の用途なら別プロセスで十分。
- FluidX3D は商用利用・軍事研究・AI 学習を禁止する独自ライセンスで、MIT とは両立しない。使わない。
- 最終判断は人間（必要なら専門家）に委ねる。

### 4.4 最小パイプライン（提案。ハッカソン後に実装）

```
Design JSON (amateur: body_diameter_m, body_length_m, nose_shape/length, fins{count, root, tip, span, sweep})
  │  geometry.py（新規、MIT）：パラメータから閉じた表面を作り、STL（mm）で出力
  │  ※ examples/designs/README.md で提案中の STL 出力（未実装）を再利用
  ▼
mesh_job.py（別プロセス。gmsh の Python API を中で使う）
  │  OpenCASCADE で胴体・ノーズ・フィンを融合 → 遠方境界の箱 → Physical グループ（wall/farfield）
  │  → 四面体＋境界層 → out.su2（Physical を定義しないと marker が出ない既知の落とし穴あり）
  ▼
SU2_CFD config.cfg（別プロセス。SOLVER=EULER or RANS / INC_RANS、MACH_NUMBER、AOA を走査）
  │  history.csv の CD, CL(=C_N 近似), CMz を読む
  ▼
coeffs.py：C_A, C_Nα = ∂C_N/∂α（α = 0, 2, 4° の差分）、x_cp = x_ref − (C_m / C_N)·d
  ▼
catalog/aero/<design_hash>.csv（M, alpha, CA, CN_alpha, xcp_m）＋ source（SU2 版・メッシュ・設定）＋ provisional: true
  ▼
solid.py / stability.py：表があれば M で補間し、なければ従来の工学式（フォールバック）
```

- メッシャーの選択：gmsh は pip で入り、SU2 形式で直接出力できる（SU2 の文書に記載）[35]。`snappyHexMesh` は OpenFOAM 専用の六面体主体のメッシャーで、SU2 へは変換が必要。Basilisk はメッシュ不要（STL などを距離関数に変換して埋め込み境界にする）。
- **C だけで済む選択肢は Basilisk。** 限界は次のとおり。圧縮性は `compressible.h`（非粘性 Euler）と `all-mach.h` で、埋め込み境界との組み合わせの実績は未確認。RANS 乱流モデルは未確認。MPI は未確認（このマシンには MPI コンパイラがない）。したがって**低速のボトル・モデルロケットに限る。**
- **SU2** は C++ で、圧縮性 RANS・Euler と随伴による形状最適化（フィン形状の勾配）まで揃う。遷音速を扱う amateur の上位と多段式の本命。

### 4.5 実現性チェック（2026-11-04 に実施。何もインストールしていない）

| 項目 | 結果 |
| --- | --- |
| `gmsh` の pip wheel | PyPI に 4.15.2（GPLv2+、`manylinux_2_24_x86_64`）。uv の Python 3.12 で `uv pip install --dry-run gmsh` が解決した。wheel には CLI の `gmsh` と `libgmsh.so` が入っている（4.11.1 の wheel で確認） |
| AVL | Linux 64 ビットの実行ファイル 3.40b が配布されている（libX11 が必要）。3.52 はソースのみ。gfortran があるのでビルドも可能（未実施） |
| `optvl`（AVL を pip で） | 2.5.0 に cp312 の manylinux wheel がある。dry-run が解決した |
| `avlwrapper` | 0.6.0（GPL-3.0）。AVL 実行ファイルのラッパー |
| `openvsp` の pip | **PyPI にない。** 公式の .deb は Ubuntu 24.04・26.04 用。このマシンは 20.04 なので CMake でのビルドが必要 |
| SU2 | PyPI にない。公式サイトに Linux のシリアル版バイナリあり。MPI 版は MPICH が必要（このマシンには MPI コンパイラがない） |
| RocketPy | PyPI 1.13.0（MIT、純 Python） |

## 5. 自前モデルの現状

| モデル | 方程式 | 主な仮定（`# SIMPLIFICATION:`） |
| --- | --- | --- |
| `water` | 空気は断熱膨張 `p = p0 (V_air0/V_air)^γ`（γ = 1.4）。推力は `F = 2 Δp A_n`、`ṁ = ρ A_n √(2Δp/ρ)`。水がなくなったら空気の力積 `0.25·√(2 m_air W_isentropic)` を 1 回。その後は抗力つきの 3 次元弾道 | C_D = 0.8 で一定（フィンなしは 2 倍）。ランチチューブなし。ノズル損失なし。直径は容積から推定。迎角ゼロ。安定性の計算なし |
| `solid` | RASP `.eng` の推力曲線。レール上は 1 次元、その後は 3 次元質点（迎角ゼロ、風は一定） | C_D = 0.75 で一定（Estes 4 機で較正）。g は一定。**マッハ数・レイノルズ数への依存なし** |
| `stability` | Barrowman：ノーズ C_Nα = 2、フィン `C_Nα = (1 + R/(s+R))·4N(s/d)² / (1+√(1+(2l_m/(c_r+c_t))²))`、x_cp は加重平均。SM = (x_cp − x_cg)/d | 亜音速、α ≈ 0。3〜8 枚のフィンを補正なしで使う。胴体の揚力なし。重心は集中質量の概算。**離床時の 1 点だけで評価** |
| `multistage` | 鉛直面内の 2 次元質点、中心重力、球形地球。Isp は大気圧で補間。重力ターン＋コーストして円化 | 直径は推進剤質量から推定。C_D(M) は汎用の 8 点の表。J2 なし |
| `recovery` | 中間高度の密度での終端速度。風で一定に流される | パラシュートの C_D = 1.5（未較正）。開傘の過渡を無視 |
| `atmosphere` | USSA76 を 86 km まで。それより上は指数近似 | 熱圏の温度上昇と分子量の変化を無視 |

### 5.1 実機の再現精度（`uv run python scripts/check_references.py --no-tune`、2026-11-04 の実行結果）

| id | 段階 | 公表値 | シミュレーション | 誤差 | 許容 |
| --- | --- | --- | --- | --- | --- |
| estes_alpha_iii_c6 | amateur | 頂点 351 m | 350.7 m | −0.1 % | 15 % |
| estes_alpha_c6 | amateur | 305 m | 350.5 m | +14.9 % | 15 % |
| estes_big_bertha_c6 | amateur | 152 m | 164.0 m | +7.9 % | 15 % |
| estes_mean_machine_e12 | amateur | 213 m | 315.3 m | **+48.0 %** | 60 % |
| estes_hi_flier_c6 | amateur | 457 m | 495.6 m | +8.5 % | 15 % |
| estes_wizard_c6 | amateur | 488 m | 495.6 m | +1.6 % | 15 % |
| estes_viking_c6 | amateur | 488 m | 495.9 m | +1.6 % | 15 % |
| estes_baby_bertha_c6 | amateur | 175 m | 181.0 m | +3.4 % | 15 % |
| estes_der_red_max_c6 | amateur | 183 m | 174.4 m | −4.7 % | 15 % |
| estes_crossfire_isx_c6 | amateur | 351 m | 349.7 m | −0.4 % | 15 % |
| apte_2l_800ml_30psi | bottle | 19.0 m | 20.7 m | +8.8 % | 15 % |
| apte_2l_800ml_40psi | bottle | 22.0 m | 25.6 m | +16.5 % | 30 % |
| apte_2l_350ml_40psi | bottle | 18.4 m | 24.6 m | +33.4 % | 45 % |
| apte_2l_350ml_20psi | bottle | 15.1 m | 15.6 m | +3.2 % | 15 % |
| apte_2l_800ml_20psi | bottle | 17.0 m | 13.1 m | −23.3 % | 30 % |
| apte_2l_1250ml_40psi | bottle | 18.9 m | 11.7 m | **−38.2 %** | 45 % |
| fischer_1l_350ml_2p5bar | bottle | 17.5 m | 16.2 m | −7.5 % | 15 % |
| fischer_1l_255ml_2bar | bottle | 14.1 m | 11.8 m | −16.6 % | 30 % |
| fischer_1l_255ml_2p5bar | bottle | 17.4 m | 15.1 m | −13.0 % | 15 % |
| fischer_1l_325ml_2p5bar | bottle | 17.1 m | 16.2 m | −5.5 % | 15 % |
| electron | commercial | 積載 300 kg | 320.5 kg | +6.8 % | 15 % |
| vega | commercial | 1,963 kg | 2,286.2 kg | +16.5 % | 30 % |
| firefly_alpha | commercial | 1,030 kg | 1,099.7 kg | +6.8 % | 15 % |
| epsilon_enhanced | commercial | 1,200 kg | 1,246.5 kg | +3.9 % | 15 % |
| falcon_9_ft | heavy | 22,800 kg | 23,396.2 kg | +2.6 % | 15 % |
| atlas_v_551 | heavy | 18,814 kg | 24,005.6 kg | **+27.6 %** | 30 % |

26 件すべてが許容内。乾燥質量の誤差（Estes の重量の定義のばらつき）は README の表を参照。参照値はすべて `provisional`。

### 5.2 誤差の主な原因（大きい順）

1. **一定の C_D**（bottle・amateur）：Apte の鈍頭ボトルと Fischer の流線形ボトルを 1 つの C_D では両立できない。Mean Machine（全長 2 m）は摩擦抵抗が支配的で +48 %。amateur の例の設計は M ≈ 1.0 に達するのに、遷音速での C_D 上昇がない（頂点を過大評価する向き）。
2. **水ロケットの空気相と充填率依存**：充填率 1250 ml で −38 %、350 ml で +33 %。この符号の反転は、空気の力積の効率 0.25 という 1 定数では充填率への依存を表せないことを示す。ランチチューブ・ノズル損失・二相の噴出も未実装。
3. **安定余裕を 1 点でしか見ていない**：離床時だけで、マッハ数による x_cp の移動と飛行中の重心移動を見ていない。water には安定性の判定がない。
4. **多段式の構造の簡易化**：ブースタの残推進剤を捨てる（Atlas V 551 で +27.6 %）。直径の推定式。
5. 積分器・大気モデル・重力の簡易化は、上の 4 つに比べて桁違いに小さい（推定）。

## 6. 計算資源と言語の結論

- **我々の数字（実測、このワークステーション）**：1 回の飛行は bottle 13 ms、amateur 24 ms、commercial 29 ms、heavy 113 ms。n=100 の多数回試行（ProcessPool）は bottle 0.31 s、amateur 0.56 s、commercial 0.66 s、heavy 2.09 s。CLAUDE.md の要件「n=100 が 10 秒以内」を 5〜30 倍の余裕で満たす。エージェントの 40 回の試行でも、物理計算の時間より Claude API の応答時間が支配的。
- **このマシン**：40 スレッド、62 GB RAM、Quadro RTX 5000（16 GB）。gcc・g++・gfortran・cmake あり。MPI コンパイラなし。Ubuntu 20.04。
- **CFD に必要なもの（推定）**：3 次元 RANS で 5×10⁶ セルなら、メモリは数 GB〜10 GB 程度で、40 スレッドで数時間。このマシンで 1 晩に数ケース回せる。GPU の LBM なら 16 GB で 10⁸ セル級に届く（FluidX3D の公称 FP16 で約 1900 万セル/GB）が、ライセンスの問題がある。
- **富岳は不要。** 理由は 4 つ。(i) 飛行計算はミリ秒で、並列化の余地も CPU 1 台で足りる。(ii) CFD は係数表を作るオフライン作業で、数ケース〜数十ケースなら 1 台で回る。(iii) 富岳が意味を持つのは、10⁸〜10¹⁰ セルの LES や数千ケースの設計空間の網羅計算で、ハッカソンの構想設計の粒度には過剰。(iv) 利用には課題申請が必要（具体的な所要期間は未確認）で、締切 6 日前には間に合わない。
- **言語**：飛行計算・多数回試行・エージェントは Python のまま。理由は、決定的に動くこと、テスト資産、scipy のイベント処理、Claude のツール使用との統合。重い外部コード（SU2 は C++、AVL は Fortran、Basilisk は C）は**別プロセス**で呼び、ファイルで係数を受け取る。ボトルネックが本当に出た場合でも、まず numba か右辺のベクトル化を試す。C++ や Fortran への書き直しは不要。

## 7. 次の一手（優先順。締切 2026-11-08 20:00 JST）

| 優先 | 内容 | 工数（推定） | 効果 |
| --- | --- | --- | --- |
| P1 | **安定余裕を飛行中の最小値で評価する**：`stability.static_margin_cal` を離床・燃焼終了・最大マッハの 3 点で評価し、最小値で合否を判定。フィンの C_Nα に Prandtl–Glauert の 1/β を掛ける（M < 0.8 で打ち切り、それ以上は警告） | 0.5 日 | 安全側の判定。§2.3 の論点を正しく扱える |
| P1 | **amateur の C_D をマッハ数依存にする**：`multistage` と同じ方式で、遷音速で C_D が上がる小さな表を掛ける。出典つき、`provisional` | 0.5 日 | M ≈ 1 の設計の頂点の過大評価を抑える |
| P2 | **RocketPy でクロスチェック**（MIT、開発用の依存）：Estes の参照機 3〜4 機を RocketPy で飛ばし、我々の値・公表値と並べる `scripts/compare_rocketpy.py` | 0.5〜1 日 | 「独立した 6 自由度のコードとも一致」と言える。デモ映えする |
| P2 | **bottle の C_D を形状で分ける**（ノーズつき流線形とボトルのまま）：Fischer と Apte を別定数で較正 | 0.5 日 | bottle の RMS 18.9 % を改善する見込み（未検証） |
| P3 | AVL（別プロセス）で、フィン 3・4・6 枚の C_Nα と C_mq を Barrowman と照合する一回限りのスクリプト | 1 日 | 5 枚以上のフィンの補正の根拠 |
| ハッカソン後 | §4.4 のパイプライン（gmsh → SU2 → 係数表）、Basilisk によるボトルの抗力、6 自由度化、充填率に依存する空気相モデル（Barrio-Perotti 型） | 1〜3 週間 | 外形とフィンの設計変数を空力で評価できる |

## 8. 出典

1. Dean Wheeler, Sim Water Rocket — https://www.et.byu.edu/~wheeler/benchtop/sim.php
2. Clifford Heath, Water Rocket Simulation — https://cjh.polyplex.org/rockets/simulation
3. NASA Glenn, Water Rocket Simulator — https://www.grc.nasa.gov/WWW/K-12/VirtualAero/BottleRocket/sim.htm
4. Water Rocket Toolbox — https://waterrockettoolbox.readthedocs.io/en/latest/simulator.html
5. マイナビニュース「JAXA、iPad向け『水ロケットシミュレーター』」（2013） — https://news.mynavi.jp/techplus/article/20131011-jx/
6. Barrio-Perotti et al., Eur. J. Phys. 31 (2010) 1131, doi:10.1088/0143-0807/31/5/015 — https://portalinvestigacion.uniovi.es/documentos/5e8912652999520e7008cbb7 、要旨（二次資料）https://physicsandphysicists.blogspot.com/2010/07/theoretical-and-experimental-analysis.html
7. Fischer et al., arXiv:2001.08828 — https://arxiv.org/abs/2001.08828
8. Hortman, CWU thesis (2017) — https://digitalcommons.cwu.edu/etd/596
9. OpenRocket — https://github.com/openrocket/openrocket
10. OpenRocket technical documentation v13.05 (CC BY-SA 3.0) — https://openrocket.info/documentation.html 、PDF https://github.com/openrocket/openrocket/releases/download/OpenRocket_technical_documentation-v13.05/OpenRocket_technical_documentation-v13.05.pdf
11. RocketPy — https://github.com/RocketPy-Team/RocketPy （論文 doi:10.1061/(ASCE)AS.1943-5525.0001331）、https://pypi.org/project/rocketpy/
12. AeroVECTOR — https://github.com/GuidodiPasquo/AeroVECTOR
13. CamPyRoS — https://github.com/cuspaceflight/CamPyRoS
14. ForRocket — https://github.com/sus304/ForRocket
15. OpenTsiolkovsky — https://github.com/istellartech/OpenTsiolkovsky
16. TrajecSimu — https://github.com/PLANET-Q/TrajecSimu 、MatRockSim https://github.com/ina111/MatRockSim
17. JSBSim — https://github.com/JSBSim-Team/jsbsim
18. WRASP — https://sourceforge.net/projects/wrasp/
19. RASAero — http://www.rasaero.com/home.htm 、無料・非 OSS の記述 https://rit-its.atlassian.net/wiki/spaces/ritlaunch/pages/59212612/RasAero+Software+Access
20. Missile DATCOM — https://en.wikipedia.org/wiki/Missile_Datcom
21. AVL — https://web.mit.edu/drela/Public/web/avl/
22. OptVL — https://github.com/joanibal/OptVL 、https://pypi.org/project/optvl/
23. OpenVSP — https://github.com/OpenVSP/OpenVSP 、https://openvsp.org/download.php 、https://en.wikipedia.org/wiki/OpenVSP
24. VSPAERO の超音速と安定微係数（フォーラム） — https://groups.google.com/g/openvsp/c/1NJ_GVccZG8 、https://groups.google.com/g/openvsp/c/9UP6htxR6YI
25. SU2 — https://github.com/su2code/SU2 、ソルバーの種類 https://su2code.github.io/docs_v7/Solver-Setup/ 、ダウンロード https://su2code.github.io/download.html
26. SU2 のメッシュ形式（gmsh の出力に対応） — https://su2code.github.io/docs_v7/Mesh-File/
27. OpenFOAM のライセンス（GPL v3） — https://www.openfoam.com/documentation/licencing
28. OpenFOAM の超音速球（snappyHexMesh） — https://wiki.openfoam.com/AMR_supersonic_sphere_Re300_Ma1dot2_by_Michael_Alletto
29. Basilisk — http://basilisk.fr/ 、ソルバー一覧 http://basilisk.fr/src/README 、ライセンス http://basilisk.fr/src/COPYING
30. Basilisk `compressible.h` — http://basilisk.fr/src/compressible.h 、`all-mach.h`（Fuster & Popinet 2018） http://basilisk.fr/sandbox/fuster/README
31. Basilisk の埋め込み境界 — http://basilisk.fr/src/embed.h
32. FluidX3D のライセンス — https://raw.githubusercontent.com/ProjectPhysX/FluidX3D/master/LICENSE.md
33. FluidX3D の README — https://github.com/ProjectPhysX/FluidX3D
34. gmsh（PyPI） — https://pypi.org/project/gmsh/
35. gmsh の SU2 出力の注意（Physical グループ） — https://www.cfd-online.com/Forums/su2/173330-gmsh-does-not-ouput-su2-markers-physical-surfaces.html
36. GNU GPL FAQ（aggregate と別プログラム） — https://www.gnu.org/licenses/gpl-faq.html#MereAggregation
