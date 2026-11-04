# RocketWright

自然文でミッションを伝える（「1 kg を 2 km まで上げて回収したい」「150 kg の衛星を高度 400 km の軌道に入れたい」）と、
RocketWright は要求を 4 つの規模に分類し、その規模の物理モデルと部品カタログを使って Claude に設計案を作らせ、
すべての案を決定的なシミュレータ（シード付きの多数回試行を含む）で仮想打ち上げし、
合格した設計案だけを図面・部品表・飛行解析・成功率つきで返します。

**Built with Claude: Japan 2026** 向けに開発。すべてシミュレーション上で完結し、実機は打ち上げません。
ライセンスは MIT です。

## 何をするか

1. 要求を `bottle` / `amateur` / `commercial` / `heavy` のいずれかに分類する。
2. その規模の物理モデルとカタログを使って、Claude が設計を選び説明する。
3. 各設計案をシミュレートする（シード付きノイズで n 回の多数回試行も行う）。
4. 合格した設計案だけを、図面・部品表・飛行解析・成功率つきで返す。

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
scripts/             run_scenario.py（デモ実行）と調整用スクリプト
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

1.5 L・卵60 g・高度30 m・予算3,000円のペトロケは、文献2機体と新規1機体を
出発点に、部品の概算、公称飛行、ばらつき試験を順に選べます。
[生成した機体・再実行手順・実測との比較](scenarios/bottle_generation.md)。

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
（合格案の有無、出典、レビューと多数回試行のイベント、引用されたツール ID の実在）を検査します。

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
- 上段は分離と同時に点火（コーストもアレージもなし）。
- 地球自転オンのとき、共回転大気の面内成分は `ω × cos(緯度)`（軌道面が赤道面であるかのように扱う）。
- 音速は同じ大気モデルから計算し、極超音速の補正はない。
- ピッチキックは瞬時に対気速度ベクトルを回転させ、以後は推力が速度方向を向く（迎角ゼロの開ループ重力ターン）。
  このため到達軌道は `pitch_start_s` / `initial_pitch_deg` に非常に敏感で（0.1° で近地点が数十 km 動く）、
  楕円軌道になりやすい。`tune_pitch_program`（scipy）がこの 2 変数を探索する。
- 理想増速量の計算ではフェアリングを第 1 フェーズ後に投棄したものとする。
- 積載余裕は、シミュレートした損失を固定したまま、基準近地点の円軌道速度に対して理想ロケット方程式を逆算して求める。

`physics/stability.py`（Barrowman 法、`solid` が使用）：

- フィンの法線力係数は 3〜8 枚でそのまま使う（Barrowman の導出はどの面でも有効なフィンは最大 2 枚と仮定。OpenRocket は 5 枚以上で低減する）。
- 一定径の胴体は法線力を出さない（Barrowman）。
- 重心は集中質量の概算：機体乾燥質量は全長に一様分布（中央に重心）、積載はノーズ基部の点質量、モーターは後端に揃えたケース中央の点質量。

`physics/solid.py`（アマチュア）：

- 迎角ゼロの細長いフィン付きホビーロケットとして、前面投影面積に対する一定の抗力係数（`DEFAULT_CD = 0.5`）。
- 全飛行で `g` 一定。
- レール上ではレール方向（鉛直）の対気速度だけを数える。レールは鉛直（`Env` に発射角の項目はない）。
  レール離脱後は迎角ゼロの質点で、機体軸は対気速度に追従する。
- パラシュートはモーターの放出薬のタイミングに関わらず「頂点＋ `deploy_delay_s`」で開く
  （`deploy_delay_s` は**頂点から**の遅延で、燃焼終了からではない。schema のコメントとモデルは一致している）。

`physics/water.py`（ペットボトル）：

- フィン付きボトルがノーズを前にして飛ぶとして、断面積に対する一定の抗力係数（`DEFAULT_CD = 0.5`）。
  フィンなしのボトルは転がるものとし、抗力係数を 2 倍にする（`TUMBLING_DRAG_FACTOR = 2.0`）。
- 水を使い切った後の空気噴出は、`AIR_IMPULSE_EFFICIENCY = 0.5` × `sqrt(2 m_air W_isentropic)` の瞬時インパルス 1 回で表す。
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

- `solid.DEFAULT_CD = 0.5` と `water.DEFAULT_CD = 0.5`（機体抗力）、`water.TUMBLING_DRAG_FACTOR = 2.0`（フィンなしボトル）。
- `recovery.DEFAULT_PARACHUTE_CD = 1.5`（ホビーパラシュート）。
- `water.AIR_IMPULSE_EFFICIENCY = 0.5`（空気噴出インパルスの割合）。
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
drawings, bill of materials, flight analysis and success rate. Everything is simulated; nothing
is launched. Claude thinks, chooses and explains; every number comes from a tool call and
carries that call's id as provenance. Values without a source are marked `provisional: true`
and listed above under 要確認の値. Built for Built with Claude: Japan 2026, MIT licensed.

Quick start: `uv sync --group dev && uv run pytest`, then
`uv run python scripts/run_scenario.py scenarios/demo_commercial.yaml --dummy` (no API key) or
without `--dummy` for the live Claude API (`ANTHROPIC_API_KEY`). The web UI (`web/`, Node >= 18.18)
talks to `uv run uvicorn api.main:app --port 8000`.
