# RocketWright

自然文でミッションを伝える（「1 kg を 2 km まで上げて回収したい」「150 kg の衛星を高度 400 km の軌道に入れたい」）と、
RocketWright は要求を 4 つの規模に分類し、その規模の物理モデルと部品カタログを使って Claude に設計案を作らせ、
すべての案を決定的なシミュレータ（シード付きの多数回試行を含む）で仮想打ち上げし、
合格した設計案だけを図面・部品表・飛行解析・成功率つきで返します。

**Built with Claude: Japan 2026** 向けに開発。すべてシミュレーション上で完結し、実機は打ち上げません。
ライセンスは MIT です。

## 何をするか

1. 要求を `bottle` / `amateur` / `commercial` / `heavy` のいずれかに分類する。
2. 定量要求を公式で計算する（`derive_requirements`：必要増速量と質量比、総力積とモーター級、ゲージ圧とパラシュート径など。
   式と代入値つきで返し、Claude はそれを最初の設計の「尺度」として引用する。結果ではない）。
3. 近い実機を種にして設計する（`find_reference_designs`：`catalog/references/` の実機から要求に最も近いものを選び、
   仮置きの縮尺規則で要求に合わせた `seed` 設計とそのシミュレーション結果を返す。合格した種は「試行 0」として UI に出る）。
4. その規模の物理モデルとカタログを使って、Claude が種を起点に設計を選び説明する。公式とシミュレーションが食い違えば
   シミュレーションを信じ、公式のどの仮定が差を生んだかを述べる。
5. 各設計案をシミュレートする（シード付きノイズで n 回の多数回試行も行う）。
6. 合格した設計案だけを、図面・部品表・飛行解析・成功率つきで返す。

| 規模 | 典型的な要求 | 推進 | 物理モデル |
| --- | --- | --- | --- |
| `bottle` ペットボトル | 数十 m、卵を割らずに着地 | 水＋圧縮空気 | `water` |
| `amateur` アマチュア | 数百 m〜数 km、積載 1 kg 前後 | 認定済み市販固体モーター（カタログ） | `solid` |
| `commercial` 企業級 | 高度 100 km、小型衛星を低軌道へ | 多段式（エンジンはカタログから） | `multistage` |
| `heavy` 重工級 | 数 t 級の積載を低軌道／静止トランスファ軌道へ | 多段式＋補助ブースタ | `multistage` |

## 原則

- **Claude は考える・選ぶ・説明する。数値はすべてコードが出す。** ユーザーに示す数値は必ずツール呼び出しの戻り値で、
  その呼び出し ID を出典として持ちます。最終出力の説明文に出典のない数値が含まれていないかをコードで検査します。
- **決定的に動く。** 乱数は必ずシードを受け取り、同じ入力とシードなら同じ結果を返します。`scenarios/` のデモ台本は回帰テストです。
- **端から端まで動くことを優先。** 簡易化した物理は `# SIMPLIFICATION:` コメントで印を付け、下に一覧しています。
- **出典のないデータを入れない。** カタログ値・規模の境界値・検証用の基準値は `source` URL を持つか、`provisional: true`
  （人間の確認待ち、下に一覧）を付けています。

## リポジトリ構成

```
rocketwright/        Python パッケージ（バックエンド）
  schema.py          pydantic モデル：Requirement, Env, Design（tier で判別）, SimResult, DispersionResult
  classify.py        規則ベースの規模分類
  derive.py          定量要求の公式計算（DERIVE_CONSTANTS はすべて provisional）
  references.py      実機カタログ（catalog/references/*.yaml）の検索・再現・縮尺（種設計）
  guard.py           スコープ外要求の検出
  physics/           atmosphere, water, solid, multistage, stability, recovery
  dispersion.py      全モデル共通の多数回試行（モンテカルロ）
  cost.py            部品表の積み上げ（bottle/amateur）または質量ベースの概算（commercial/heavy）
  catalog/           parts.yaml, motors/*.eng, engines.yaml（全項目が出典つきか provisional）
  drawing.py         寸法線つき SVG 側面図
  report.py          Markdown/JSON レポートと部品表 CSV
  agent/             Claude のツール定義、設計ループ、レビュアー、システムプロンプト
api/main.py          FastAPI。エージェントの進行を SSE で配信
web/                 Next.js（App Router, TypeScript）フロントエンド
config/tiers.yaml    規模の境界値（出典つきか provisional）
config/models.yaml   Claude のモデル ID、effort、試行上限、レビュアー設定
scenarios/           回帰テストに使う固定のデモ台本
scripts/             run_scenario.py（デモ実行）、check_scenarios.py（全台本の検査）、
                     check_references.py（実機再現の誤差表）、calibrate_small_rockets.py（Cd 較正）、調整用スクリプト
tests/               pytest
```

## セットアップ

バックエンド（Python 3.11 以上、[uv](https://docs.astral.sh/uv/) で管理）：

```bash
uv python install 3.12
uv sync --group dev
uv run pytest
uv run ruff check .
uv run uvicorn api.main:app --reload   # GET /health
```

エージェントの呼び出しには `ANTHROPIC_API_KEY` が必要です。`.env.example` を `.env` にコピーして設定してください。

フロントエンド（Node 18.18 以上。雛形は手書きで、この開発環境ではまだビルドしていません）：

```bash
cd web && npm install && npm run dev   # http://localhost:3000
```

UI の「設計を開始」は実際の Claude API を呼びます。使い方の詳細は `web/README.md` を参照してください。

## デモの実行

`scenarios/` の各ファイルが固定のデモ台本（要求文、シード、期待する規模）です。実行スクリプトはエージェントの
イベントを 1 行ずつ出力し、分類された規模が期待と違う場合やループがエラーで終わった場合は非ゼロで終了します。

```bash
# ネットワークも API キーも不要：台本どおりに応答する偽クライアント（レビュアーの応答も台本）
uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml --dummy

# 本番：実際の Claude API（ANTHROPIC_API_KEY が必要。.env.example 参照）
uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml
```

`scenarios/demo_amateur.yaml` と `scenarios/demo_bottle.yaml` も同じです。同じ実行を `tests/test_scenarios.py` が
偽クライアントで行います。`uv run python scripts/check_scenarios.py` は全シナリオを実行し、最終 JSON
（合格案の有無、出典、レビューと多数回試行のイベント、`derive_requirements` と `find_reference_designs` の結果、
最終 JSON の `reference_id` が実機カタログの id で `derived_targets` が derive の呼び出し ID であること、
引用されたツール ID の実在）を検査します。

台本の流れはどの規模でも同じです：分類 → 公式で定量要求を算出 → カタログ検索 → 近い実機から種設計
（企業級は種のピッチ指令を再調整するため数秒かかる）→ 種を起点に試行 1 → 失敗理由を読んで原因を直した試行 2〜3 →
合格案の多数回試行 → 最終 JSON（`reference_id`, `derived_targets`, 各数値の出典 ID）。

| 台本 | 種（実機） | 試行 0（種） | 試行 1 | 試行 2 | 試行 3 | 成功率（n=100） |
| --- | --- | --- | --- | --- | --- | --- |
| demo_bottle | Apte 2 L ボトル → 376 kPa、0.31 m 傘 | 合格 32.2 m | 1.5 L ボトルに収める：合格 29.7 m | 公式の 695 kPa に寄せて 500 kPa：36.5 m で不合格（公式のエネルギー効率が悲観的） | 400 kPa：合格 31.1 m | 0.99（試行 1） |
| demo_amateur | Estes Alpha III → J420、60 mm、傘 1.79 m | 2,208 m（+10 %）で不合格 | 種のまま：不合格（頂点 +10 %） | 66 mm 胴体・乾燥 500 g・傘 1.0 m：合格 1,935 m | 同じく傘 1.2 m：合格 | 0.94（試行 2） |
| demo_commercial | Electron → Rutherford 4+1 基、推進剤 4,625+1,025 kg、ピッチ再調整 | 合格 399.5 km | 種のまま：合格（余裕 37 kg、5.1 億円） | 1 段目を 4,000 kg に削減：近地点 -1.9 km で不合格 | 2 段目を 900 kg に削減：合格 400×498 km、5.0 億円 | 0.94（試行 1） |

モデルとレビュアーの設定は `config/models.yaml` にあります：

- `design_model`（`claude-opus-5-5`、adaptive thinking、`effort: high`）が設計判断を行い、
  `light_model`（`claude-haiku-5-5`）が軽い処理を担当します。
- `max_attempts`（40）は `simulate_design` の呼び出し回数の上限、`max_turns`（80）は API 往復回数の上限です。
- `reviewers`：安定性・回収・費用・安全の 4 観点のレビュアーが、合格した設計案ごとに並列で動きます
  （`enabled`, `model`, `effort`, `max_tokens`, `max_rounds_per_candidate`）。判定は `review` イベントとして
  配信され、major / blocker の指摘は設計役に返されます。blocker が付いた案は最終の合格一覧から外れます
  （`review_gate` 種別の `warning` イベントで通知）。ツール結果に無い数値を引用した指摘はコードで除外します。

## 進捗

| フェーズ | 期間 | 完了条件 |
| --- | --- | --- |
| 1 | 11/2–11/3 | schema・classify・guard・最小の multistage とテスト。エージェントがダミー物理で一周する |
| 2 | 11/4–11/5 | solid・stability・recovery。エージェント＋UI が commercial と amateur で端から端まで動く |
| 3 | 11/6–11/7 | water、全規模の多数回試行、レビュアー、図面・部品表の出力 |
| 4 | 11/8 | 機能凍結。scenarios の回帰テスト、UI の磨き込み、README |
| 5 | 11/9–11/10 | デモ動画、概要文、提出 |

現在：フェーズ 4（機能凍結）。4 つの規模すべてが実物理モデル（`water` / `solid` / `multistage`）で動き、
多数回試行、レビュアー、図面、レポート、部品表の出力まで繋がっています。

## 簡易化した箇所

各項目はコード中の `# SIMPLIFICATION:` コメントに対応します（`grep -rn SIMPLIFICATION rocketwright/`）。

`physics/atmosphere.py`：

- 86 km 以上は温度一定とし、圧力・密度は指数関数で減衰させる（実際の USSA76 の熱圏は約 1000 K まで上がる）。
- 空気の分子量は海面値で固定（USSA76 では 86 km 以上で下がる）。
- 温度オフセットは静水圧の圧力分布を再積分しない。

`physics/multistage.py`：

- 平均半径の球形地球、中心重力のみ（J2 なし）。
- フェアリング投棄は固定高度（110 km）。自由分子加熱の制限ではない。
- 機体直径は推進剤総質量から推定（`d = 0.05 m × m_prop^(1/3)`）。
- 抗力係数は細長いロケット向けの小さなマッハ数表で、機体固有ではない。
- エンジン質量は構造比に含まれると仮定（構造比でエンジンすら賄えない場合は警告）。
- 補助ブースタは最も燃焼時間が短いものが空になった時点で一斉投棄し、残推進剤は捨てる。1 段目より長持ちするブースタは 1 段目と一緒に投棄。
- 下段は分離と同時に次段を点火（アレージなし）。最終段の軌道投入（`target_perigee_m` 指定時、既定 `insertion="coast_circularize"`）は
  「接触軌道の遠地点が目標に達する（かつ近地点が −1000 km 以上）まで燃焼 → 無推力で遠地点までコースト（抗力は大気モデルに従い減衰）→
  接触軌道の近地点が目標に達するまで再燃焼」。3 つのカットオフは状態量に対する積分イベントで、推力方向は常に速度方向（迎角ゼロ）のまま。
  誘導則ではなく概念設計で通常使う「目標遠地点でのエンジン停止」であり、CLAUDE.md 4 の開ループの範囲内。
  遠地点に届かず燃え尽きた場合はそのまま遠地点までコーストして到達軌道を報告（不合格）。`insertion="direct"` で従来の単一燃焼に戻せる。
  指標に `coast_time_s`・`circularization_dv_mps`・`propellant_margin_kg` を追加。
- 地球自転オンのとき、共回転大気の面内成分は `ω × cos(緯度)`（軌道面が赤道面であるかのように扱う）。
- 音速は同じ大気モデルから計算し、極超音速の補正はない。
- ピッチキックは瞬時に対気速度ベクトルを回転させ、以後は推力が速度方向を向く（迎角ゼロの開ループ重力ターン）。
  このため到達軌道は `pitch_start_s` / `initial_pitch_deg` に非常に敏感で（0.1° で近地点が数十 km 動く）、
  楕円軌道になりやすい。`tune_pitch_program`（scipy）がこの 2 変数を探索する。
- 理想増速量の計算ではフェアリングを第 1 フェーズ後に投棄したものとする。
- 積載余裕（`payload_margin_kg`）：coast_circularize では最終段に残った推進剤（`propellant_margin_kg`）の理想増速量を
  「機体全体の理想増速量をその分だけ減らす積載増分」に換算する（損失は固定）。近地点が目標に届かなかった分は、
  到達した接触軌道から基準円軌道への 2 インパルス増速量として差し引く。direct モードでは燃焼終了高度から基準高度への
  上昇分を含めたエネルギー等価速度 `v_req² = v_circ(r_ref)² + 2μ(1/r_burnout − 1/r_ref)` に対して逆算する。
- 離昇推重比の合格閾値は 1.1（Atlas V 401 の実機は約 1.17）。1.2 未満は警告。
- 軌道目標ではエージェントのディスパッチ（`agent/tools.py`）が `earth_rotation` を自動で ON にする（東向き打上げを仮定、警告つき）。

`physics/stability.py`（Barrowman 法、`solid` が使用）：

- フィンの法線力係数は 3〜8 枚でそのまま使う（Barrowman の導出はどの面でも有効なフィンは最大 2 枚と仮定。OpenRocket は 5 枚以上で低減する）。
- 一定径の胴体は法線力を出さない（Barrowman）。
- 重心は集中質量の概算：機体乾燥質量は全長に一様分布（中央に重心）、積載はノーズ基部の点質量、モーターは後端に揃えたケース中央の点質量。

`physics/solid.py`（アマチュア）：

- 迎角ゼロの細長いフィン付きホビーロケットとして、前面投影面積に対する一定の抗力係数（`DEFAULT_CD = 0.75`）。
  Estes TR-10 系の高度予測が使う「典型的なモデルロケット」の値（ランチラグ・角のある balsa フィン）。
  `catalog/references/amateur.yaml` の Estes キット 4 機に対して `scripts/calibrate_small_rockets.py` で較正
  （頂点高度の RMS 誤差 15.4 %。全長 2 m の Mean Machine だけは摩擦抗力が支配的で +24 %）。
- 全飛行で `g` 一定。
- レール上ではレール方向（鉛直）の対気速度だけを数える。レールは鉛直（`Env` に発射角の項目はない）。
  レール離脱後は迎角ゼロの質点で、機体軸は対気速度に追従する。
- パラシュートはモーターの放出薬のタイミングに関わらず「頂点＋ `deploy_delay_s`」で開く
  （`deploy_delay_s` は**頂点から**の遅延で、燃焼終了からではない。schema のコメントとモデルは一致している）。

`physics/water.py`（ペットボトル）：

- フィン付きボトルがノーズを前にして飛ぶとして、断面積に対する一定の抗力係数（`DEFAULT_CD = 0.8`）。
  Apte & Apte 論文が 2 L ボトルに仮定する値で、Fischer らの風洞値 0.6 ± 0.2 の上端。
  `catalog/references/bottle.yaml` の実験飛行 5 件に対して `AIR_IMPULSE_EFFICIENCY` と同時に
  `scripts/calibrate_small_rockets.py` で較正（頂点高度の RMS 誤差 18.9 %）。
  鈍い Apte のボトルと流線形の Fischer のロケットを 1 つの Cd では両立できない（設計ごとの Cd は未実装）。
  フィンなしのボトルは転がるものとし、抗力係数を 2 倍にする（`TUMBLING_DRAG_FACTOR = 2.0`）。
- 水を使い切った後の空気噴出は、`AIR_IMPULSE_EFFICIENCY = 0.25` × `sqrt(2 m_air W_isentropic)` の瞬時インパルス 1 回で表す
  （先細オリフィスからの吹き出しと泡状の排出は理想ジェットに遠く及ばない。参照飛行の較正では
  どの Cd でも 0.25 が旧値 0.5 より良く、0.0 は質量不明の Apte 飛行だけに合う）。
- ボトル直径は容積から推定（1.5 L の PET ボトルは直径約 90 mm、容積の立方根でスケール）。
- 発射前のボトル内空気は周囲温度。
- レール／迎角の簡易化は `solid.py` と同じ（鉛直ランチャー、迎角ゼロ）。
- パラシュートは頂点でちょうど開く。

`physics/recovery.py`（パラシュート降下、`solid` と `water` が共用）：

- 平面型／半球型ホビーパラシュートの `Cd = 1.5`（クロス型は約 0.8）。
- 降下の中間高度の空気密度で計算した終端速度で降下する。開傘の過渡と途中の密度変化は無視。
  降下中はずっと風ベクトルそのままで流される（風は高度によらず一定）。

`cost.py`：

- 一律の仮置き価格（すべて provisional、下を参照）。補助ブースタの質量はカタログに載るまでの仮定数。

`drawing.py`（SVG 側面図）：

- ボトルは長さ／直径比 3.5 の円筒に、0.8 d のノーズと 0.3 d の首を付けて描く。
- アマチュアのモーターマウント長はモーターカタログから取り、読めない場合は胴長の 0.2 を仮置き。
  設計が `has_fins` だけを持つ場合は代表的な大きさ（スパン 0.8 d）のフィンを描く。
- 多段式の各段は、上記 `multistage` の直径規則と推進剤質量（かさ密度 1000 kg/m³）から長さを決めた円筒。
  フェアリングは直径の 2.5 倍、ブースタカタログが無い場合は直径 0.4 倍・1 段目長 0.6 倍の円筒。図は構想レベルで製造用ではない。

`report.py`：

- カタログに部品が無い場合、bottle/amateur の機体乾燥質量を固定比率で部品表の行に配分する
  （bottle：ボトル／ノズル／フィン／パラシュート = 45/10/25/20 %、amateur：ノーズ／胴体／フィン／パラシュート = 15/45/25/10 %。provisional）。
- すべてのレポートに「物理と費用は簡易化されている」旨の注記を付け、ここを参照させる。

## 設計精度 — 実機再現

`catalog/references/*.yaml` の実機（出典 URL つき、すべて provisional）を同じ物理モデルで再現した誤差です
（`uv run python scripts/check_references.py`、2026-11-02。軌道機はピッチ指令を再調整して積載能力を求める。
許容は各項目の `tolerance_frac`、既定 30 %）：

| id | 規模 | 指標 | 公表 | sim | 誤差 |
| --- | --- | --- | --- | --- | --- |
| estes_alpha_iii_c6 | amateur | 頂点高度 m | 351.0 | 345.5 | -1.6 % |
| estes_alpha_c6 | amateur | 頂点高度 m | 305.0 | 347.6 | +14.0 % |
| estes_big_bertha_c6 | amateur | 頂点高度 m | 152.0 | 171.9 | +13.1 % |
| estes_mean_machine_e12 | amateur | 頂点高度 m | 213.0 | 264.0 | +24.0 % |
| apte_2l_800ml_30psi | bottle | 頂点高度 m | 19.0 | 20.7 | +8.7 % |
| apte_2l_800ml_40psi | bottle | 頂点高度 m | 22.0 | 25.6 | +16.4 % |
| apte_2l_350ml_40psi | bottle | 頂点高度 m | 18.4 | 24.6 | +33.4 % |
| fischer_1l_350ml_2p5bar | bottle | 頂点高度 m | 17.5 | 16.2 | -7.5 % |
| fischer_1l_255ml_2bar | bottle | 頂点高度 m | 14.1 | 11.8 | -16.6 % |
| electron | commercial | 軌道投入能力 kg | 300 | 321.7 | +7.2 % |
| vega | commercial | 軌道投入能力 kg | 1,963 | 2,294.4 | +16.9 % |
| firefly_alpha | commercial | 軌道投入能力 kg | 1,030 | 1,099.7 | +6.8 % |
| epsilon_enhanced | commercial | 軌道投入能力 kg | 1,200 | 1,279.9 | +6.7 % |
| falcon_9_ft | heavy | 軌道投入能力 kg | 22,800 | 23,450.1 | +2.9 % |
| atlas_v_551 | heavy | 軌道投入能力 kg | 18,814 | 23,750.7 | +26.2 % |

軌道機の軌道高度は再調整により公表値の ±0.1 % 以内です。15 項目すべてが許容内（atlas_v_551 は 30 % の許容に対し +26 %：
固体ブースタの燃焼終了後の推進剤を捨てる簡易化が主因）。較正した定数：

- `solid.DEFAULT_CD = 0.75`（Estes 4 機に対し RMS 誤差 15.4 %）。
- `water.DEFAULT_CD = 0.8` と `water.AIR_IMPULSE_EFFICIENCY = 0.25`（ボトル 5 件に対し同時較正、RMS 誤差 18.9 %）。
- `recovery.DEFAULT_PARACHUTE_CD = 1.5` は未較正。

`scripts/calibrate_small_rockets.py` が Cd（と空気噴出効率）の走査表を出します。値をモジュールに書き戻すのは人間です。

種設計（`references.seed_design`）は最も近い実機をこの規則で縮尺します（すべて provisional、下の「要確認の値」も参照）：
企業級・重工級は各段の推進剤を積載比で線形に縮尺し、構造比とエンジン種は保ち、エンジン基数は同じ比で四捨五入
（同点は少ない側）、離床推力重量比が 1.2 未満なら 1 段目にエンジンを足し、ブースタは実機のまま、フェアリングは
積載比^(2/3)。アマチュアは「抗力なしの弾道則」（必要力積 ∝ 離床質量比 × √高度比）で最小の同梱モーターを選び、
それが収まるよう機体を幾何相似に拡大、パラシュートは着地質量比の平方根。ペットボトルはゲージ圧を頂点比で線形に
（安全上限でクリップ）、回収要求か積載があれば傘を追加。種はその場でシミュレートされ、合格すれば試行 0 として UI に出ます。

## 要確認の値

以下はすべてリポジトリ内で `provisional: true`（または出典のないハードコード定数）であり、人間の判断か出典が必要です。

`config/tiers.yaml`：

| 規模 | キー | 仮置き |
| --- | --- | --- |
| bottle | target_altitude_max | 100 m |
| bottle | payload_mass_max | 0.2 kg |
| bottle | budget_min | 1,000 円 |
| amateur | target_altitude_max | 5,000 m（国内のクラブ・法規の慣行による） |
| amateur | payload_mass_max | 5 kg |
| amateur | budget_min | 30,000 円 |
| commercial | target_altitude_min | 100 km（カーマンライン。FAI を出典にできる） |
| commercial | target_altitude_max | 2,000 km |
| commercial | payload_mass_max | 1,000 kg |
| commercial | budget_min | 10 億円（最も恣意的。予算矛盾デモの分岐を決める） |
| heavy | target_altitude_max | 上限なし |
| heavy | payload_mass_max | 上限なし |
| heavy | budget_min | 50 億円 |

`cost.py`（`COST_CONSTANTS`、すべて円、すべて provisional）：

| キー | 仮置き |
| --- | --- |
| bottle_base_jpy | 1,500（ボトル、ノズル、フィン、ランチャー） |
| bottle_parachute_jpy | 800 |
| amateur_airframe_jpy_per_kg | 12,000 |
| amateur_fin_jpy | 500／枚 |
| amateur_motor_jpy | 8,000（一律、ミッドパワーのリロード） |
| amateur_parachute_jpy_per_m2 | 6,000 |
| amateur_electronics_jpy | 10,000（高度計＋開傘） |
| commercial_jpy_per_kg_liftoff | 80,000 |
| heavy_jpy_per_kg_liftoff | 25,000 |
| booster_mass_kg_placeholder | 20,000 kg／本 |

`derive.py`（`DERIVE_CONSTANTS`、公式計算の経験定数。出典 URL があっても代表値の選び方は仮置き）：

| キー | 仮置き | 出典 |
| --- | --- | --- |
| orbit_loss_allowance_mps | 1,800 m/s（重力＋抗力＋操舵損失。本モデルの重力ターンでは約 2,800 m/s 出るため楽観的） | Wikipedia Delta-v budget |
| default_launch_latitude_deg | 31.25°（内之浦） | Wikipedia Uchinoura |
| representative_isp_s | 300 s（commercial / heavy とも） | Wikipedia Merlin |
| representative_structural_fraction | 0.08 | なし |
| typical_payload_fraction_frac | 0.02 | Wikipedia Payload fraction |
| amateur_airframe_mass_kg | 0.5 kg（空の機体） | なし |
| amateur_airframe_mass_per_payload_frac | 0.3（積載 1 kg あたりの追加機体質量） | なし |
| amateur_body_diameter_m | 0.054 m | なし |
| amateur_burn_time_s | 2.0 s | なし |
| motor_class_base_impulse_ns | 1.25 Ns（NAR の級の基準。これのみ出典確定） | Wikipedia Model rocket motor classification |
| bottle_volume_m3 | 1.5 L | なし |
| bottle_water_fill_frac | 0.4 | arXiv 2001.08828 |
| bottle_airframe_mass_kg | 0.12 kg | arXiv 2001.08828 |
| bottle_energy_efficiency_frac | 0.16（m g h / 等エントロピー膨張仕事。参照 5 件の中央値。デモでは悲観的） | catalog/references/bottle.yaml |

種設計の縮尺規則（`references.py`、すべて provisional）：

| 定数 | 仮置き |
| --- | --- |
| `_PAYLOAD_FLOOR_KG` | 1 kg（積載比の下駄） |
| `_SCALE_BOUNDS` | 0.02〜50（積載比のクランプ） |
| `SEED_MIN_LIFTOFF_TWR` | 1.2（`multistage.PASS_THRESHOLDS` の警告線） |
| `_MOTOR_CLEARANCE_M` | 6 mm（胴体はモーター径＋これ） |
| `_BODY_LENGTH_PER_MOTOR_LENGTH` | 1.5（胴長はモーター長のこれ以上） |
| `_PARACHUTE_SPEED_MARGIN` | 0.8（追加する傘は降下速度上限の 8 割で設計） |
| 推進剤の縮尺 | 積載比に線形。エンジン基数は同じ比で四捨五入、フェアリングは積載比^(2/3) |
| アマチュアの力積則 | 必要力積 = 実機の力積 × 離床質量比 × √高度比（抗力なし） |
| ボトルの圧力則 | ゲージ圧 ∝ 頂点高度（安全上限 1,000 kPa でクリップ） |

合否の閾値（`physics/solid.py` と `physics/water.py` の `PASS_THRESHOLDS`）：

| モデル | 規則 | 値 |
| --- | --- | --- |
| solid | レール離脱速度の下限 | 15 m/s（一般的なクラブの目安） |
| solid | 静安定余裕 | 1.5〜4.0 cal（4.0 超は警告のみ） |
| solid, water | 降下速度の上限 | 6 m/s（water：積載なしの空ボトルは 10 m/s） |
| solid | 開傘速度 | 40 m/s、警告のみ |
| solid, water | 目標指定時の頂点高度の許容 | ±10 % |
| water | 初期ゲージ圧の上限 | 1,000 kPa（PET ボトルの安全上限） |

多数回試行の σ（`dispersion.py` の `DISPERSION_SPEC`、すべて provisional。1 標準偏差、実行のシードからサンプルごとに適用）：

| 規模 | 量 | σ |
| --- | --- | --- |
| bottle | 初期ゲージ圧 | 5 %（相対） |
| bottle | 風速／風向 | 1.0 m/s ／ 20° |
| amateur | モーター推力（総力積） | 5 %（相対） |
| amateur | 乾燥質量 | 3 %（相対） |
| amateur | 風速／風向 | 1.5 m/s ／ 30° |
| amateur | 開傘遅延 | 0.5 s（0 でクリップ） |
| commercial, heavy | エンジン Isp | 1 %（相対） |
| commercial, heavy | エンジン推力 | 2 %（相対） |
| commercial, heavy | 段の構造比 | 5 %（相対） |

デモで示す成功率（`run_dispersion`、n=100）はこれらの σ から実行時に計算され、どこにも保存されません。σ を変えると変わります。
`multistage` の開ループ重力ターンのため、commercial の成功率はこれらの σ に非常に敏感です
（デモ設計は名目では合格するが、摂動したサンプルの多くは目標近地点に届かない）。これは上記の「誘導なし」の簡易化の帰結です。

出典のない物理定数：

- `solid.DEFAULT_CD = 0.75`（機体抗力）。暫定だが参照飛行 4 件
  （estes_alpha_iii_c6, estes_alpha_c6, estes_big_bertha_c6, estes_mean_machine_e12）に対して較正済み、RMS 誤差 15.4 %。
- `water.DEFAULT_CD = 0.8`（機体抗力）。暫定だが参照飛行 5 件
  （apte_2l_800ml_30psi, apte_2l_800ml_40psi, apte_2l_350ml_40psi, fischer_1l_350ml_2p5bar, fischer_1l_255ml_2bar）
  に対して較正済み、RMS 誤差 18.9 %。`water.TUMBLING_DRAG_FACTOR = 2.0`（フィンなしボトル）は未較正。
- `recovery.DEFAULT_PARACHUTE_CD = 1.5`（ホビーパラシュート）。
- `water.AIR_IMPULSE_EFFICIENCY = 0.25`（空気噴出インパルスの割合）。暫定だが上の 5 件に対して `water.DEFAULT_CD` と同時に較正済み
  （`uv run python scripts/calibrate_small_rockets.py` で表を再現できる）。apte_2l_350ml_40psi はなお +33 % で、
  乾燥質量の推定値と 1 インパルス近似の空気噴出モデルが残る原因。
- ボトル直径の規則：1.5 L で 90 mm、容積の立方根でスケール（`water.bottle_diameter_m`。図面は別途 3.5 の縦横比を使う）。
- `deploy_delay_s` の意味：遅延は**頂点から**数える（頂点＋遅延で開傘）。燃焼終了後の放出薬の遅延ではない。
  アマチュアのデモでこの意味でよいか確認してください。

カタログ（`rocketwright/catalog/`）：

- `motors/*.eng`：5 本の推力曲線（`dummy_F32`, `dummy_G80`, `dummy_H128`, `dummy_I200`, `dummy_J420`）はすべて
  **このリポジトリ用に作った合成の台形**で、実在のモーターではありません。出典とライセンスのある曲線に置き換えるまで、
  `solid` の結果には警告が付きます。
- `parts.yaml`：17 項目（ボトル、ノズル、ノーズコーン、胴体チューブ、フィンとフィン材、モーターマウント、パラシュート）は
  ホビーショップの代表的な質量と価格で、すべて provisional。
- `engines.yaml`：`merlin_1d_vacuum`, `rl10`（RL10C-1）, `le_9`, `rutherford`, `gem_63`, `ariane5_eap` は provisional
  （公開ページから読んだ値だが未確認）。その他の項目は出典つき。

人間が確認すべき文言：

- `report.py` の `CHECKLIST`：「要確認事項のチェックリスト（法的助言ではない）」は意図的に一般的な内容
  （射場の許可、気象制限、レンジ安全、保険。アマチュアではモーター認定と空域、企業級・重工級では打ち上げ許可、
  レンジ契約、周波数、輸出管理）。RocketWright は許可や合法性を判断しません（CLAUDE.md 4 章）。
- `agent/prompts.py` の費用レビュアー：`major` は「費用が予算の約 1 割以内に迫っている」、`blocker` は `cost_jpy` が
  予算超過のときのみ。レビュアーは閾値を数値ではなく言葉で表します。「1 割」の規則でよいか確認してください。

`CLAUDE.md` に明記されていないスキーマ上の決定：

- `Env` の既定値はすべて 0（実在の射場ではない）。デモ台本は緯度・標高・風を明示する。
- `AmateurDesign.dry_mass_kg`（モーターと積載を除く機体質量）を追加。`solid.py` が必要とする。
- `AmateurDesign.deploy_delay_s` は頂点からの遅延（上記）。
- `Env.rail_length_m`（既定 1.5 m）を `solid`／`water` のランチャー離脱速度のために追加。
- 指標のキーは `rocketwright.schema.UNIT_SUFFIXES` のいずれかの単位接尾辞で終わる。

## English summary

Describe a mission in plain language and RocketWright classifies it into one of four tiers
(`bottle`, `amateur`, `commercial`, `heavy`), lets Claude propose designs using that tier's
physics model and parts catalog, launches every candidate in a deterministic simulator
(including seeded Monte Carlo dispersion), and returns only the designs that pass, with
drawings, bill of materials, flight analysis and success rate. Before designing, the agent
derives quantitative targets by closed formulas (`derive_requirements`: required delta-v,
total impulse and motor class, gauge pressure, ...) and seeds the design from the nearest real
vehicle in `catalog/references/` (`find_reference_designs`: Electron, Atlas V, Estes kits,
published bottle-rocket flights), scaled by provisional rules and simulated on the spot; the
final answer cites the reference id and the derive call. When a formula and the simulation
disagree, the simulation wins and the agent names the assumption that explains the gap. The
reproduction table above (設計精度) shows every reference within its tolerance. Everything is
simulated; nothing is launched. Claude thinks, chooses and explains; every number comes from a
tool call and carries that call's id as provenance. Values without a source are marked `provisional: true`
and listed above under 要確認の値. Built for Built with Claude: Japan 2026, MIT licensed.

Quick start: `uv sync --group dev && uv run pytest`, then
`uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml --dummy` (no API key) or
without `--dummy` for the live Claude API (`ANTHROPIC_API_KEY`). The web UI (`web/`, Node >= 18.18)
talks to `uv run uvicorn api.main:app --port 8000`.
