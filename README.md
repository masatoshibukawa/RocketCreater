# RocketWright

自然文でミッションを伝える（「1 kg を 2 km まで上げて回収したい」「150 kg の衛星を高度 400 km の軌道に入れたい」）と、
RocketWright は要求を 4 つの規模に分類し、その規模の物理モデルと部品カタログを使って Claude に設計案を作らせ、
すべての案を決定的なシミュレータ（シード付きの多数回試行を含む）で仮想打ち上げし、
合格した設計案だけを図面・部品表・飛行解析・成功率つきで返します。

**Built with Claude: Japan 2026** 向けに開発。すべてシミュレーション上で完結し、実機は打ち上げません。
ライセンスは MIT です。

ペットボトルロケットの設計変数・解析手法・評価指標は、[ブラウザで読める設計ガイド](UI/bottle-pool/README.md)にまとめています。

1.5 L ペットボトル機の[試作手順](scenarios/bottle_prototype.md)では、手持ちゼロからの購入表、等倍フィン型紙、3Dプリント用ホルダーと治具を生成できます。

## 画面

画面は「自由な要求から設計」の1つです。チャットに要求を書くと、Claudeが出した案を3列で見られます。中央のタブで次を切り替えます。

- 3D モデルと費用
- シミュレーション：合格案の飛行の再生
- 流体解析：表示中の案で飛行計算と流体計算を交互に回す（ボトルとアマチュア）
- 製作データ：製作票PDF・設計レポート・部品表・側面図、ボトルの3Dプリント用データ（ボトルとアマチュア）
- 設計例と資料：2 L試作の参照機体と文献の検索

右の欄に飛行の結果があります。ボトルの静安定余裕は、部品のフィンを選んだ案で注水時と空のときの2つを出します。企業級・重工級は構想設計に留めるので、流体解析と製作データのタブは出ません。

Claudeの案は機体の構成を定めないため、1.5 Lの製作例にある組立手順の文章・原寸型紙・購入計画はこの画面からは出ません。出せないものは「製作データ」に理由と一緒に示します。

1工程ずつ確かめるペットボトルの製作例と動画制作は、画面をなくし、API（`/workbench/*`）とスクリプトとして残しました。[ローカル試験の起動と操作](docs/workbench.md)を参照してください。

**課金APIの設計実行は既定で無効です。** `ROCKETWRIGHT_ENABLE_CLOUD_DESIGN=0` のままだと、画面では設計を始められず「設計例と資料」だけを使えます。キーを設定するだけでは `/design` は実行されません。クラウド接続は最後の確認段階まで保留します。

- [統合した資料・決定事項と担当範囲](docs/integration.md)
- [ローカル試験の起動と操作](docs/workbench.md)
- [空力レイヤー（Barrowman・OpenFOAM・GPU LBM の差し替え、ビルド手順と実測）](docs/aero.md)
- [既存Gemmaの再利用](AIvideo/local-director/README.md)
- [ピッチとプレゼンテーションのテクニック](presentation-techniques/README.md)

これは開発・試験用の統合です。製作部品のスライス、現物の寸法・強度・回収・飛行の確認、および最終提出チェックは別工程です。

## 何をするか

1. 要求を `bottle` / `amateur` / `commercial` / `heavy` のいずれかに分類する。
2. 定量要求を公式で計算する（`derive_requirements`：必要増速量と質量比、総力積とモーター級、ゲージ圧とパラシュート径など。
   式と代入値つきで返し、Claude はそれを最初の設計の「尺度」として引用する。結果ではない）。
3. 設計する。
   - **ペットボトル・アマチュア：段階チェーン。** 部品を決まった順（モーター → マウント → 胴体チューブ → … → 開傘遅延）で
     選ぶ。各段階の候補はコードがカタログから列挙し、組立可否を検査し、シミュレートして順位を付ける（`auto_design` が
     全段階を通した基準案、`design_stage` が 1 段階ぶんの候補と絞り込みの内訳）。Claude は基準案を説明し、ユーザーの
     優先事項（安く・軽く・資格なし・手持ちの部品）に合わせて**最も上流の変える必要がある段階から**選び直し、
     `design_from_parts` で最終構成を確かめる。近い実機キット（`find_reference_designs`）は「どのキットに近いか」の文脈として引用する。
   - **企業級・重工級：近い実機を種にする。** `find_reference_designs` が `catalog/references/` から最も近い実機を選び、
     仮置きの縮尺規則で要求に合わせた `seed` 設計とそのシミュレーション結果を返す（合格した種は「試行 0」として UI に出る）。
4. 公式とシミュレーションが食い違えばシミュレーションを信じ、公式のどの仮定が差を生んだかを述べる。
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
presentation-techniques/ ピッチ・プレゼン・デモの調査資料、制作ワークシート、発表方針
rocketwright/        Python パッケージ（バックエンド）
  schema.py          pydantic モデル：Requirement, Env, Design（tier で判別）, SimResult, DispersionResult
  classify.py        規則ベースの規模分類
  derive.py          定量要求の公式計算（DERIVE_CONSTANTS はすべて provisional）
  references.py      実機カタログ（catalog/references/*.yaml）の検索・再現・縮尺（種設計）
  parts.py, build.py 部品カタログの読み込みと、部品の構成 → 設計・部品表・組立可否の検査（定格、室の長さ、カプラ、資格）
  design_chain.py    段階チェーン：段階ごとの候補の列挙・検証・順位付け（design_stage）と基準案（auto_design）
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

画面の設計はClaudeを使います。Claude接続は既定で無効で、そのときチャットに「Claude の設計は今オフです」と表示します。使い方の詳細は `web/README.md` を参照してください。

## デモの実行

1.5 L・卵60 g・高度20 m・予算3,000円のペトロケは、文献2機体と新規1機体を
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

`scenarios/` には 4 本の台本があります（`demo_bottle`, `demo_amateur`, `demo_model_rocket`, `demo_commercial`）。
同じ実行を `tests/test_scenarios.py` が偽クライアントで行います。`uv run python scripts/check_scenarios.py` は全シナリオを実行し
（各 10 秒以内）、最終 JSON（合格案の有無、出典、レビューと多数回試行のイベント、`derive_requirements` と
`find_reference_designs` の結果、最終 JSON の `reference_id` が実機カタログの id で `derived_targets` が derive の呼び出し ID
であること、引用されたツール ID の実在）を検査します。台本の各選択は実行時にツールの戻り値から読み取ります（数値の手書きなし）。
シナリオ YAML の `story:` で台本を選びます（省略時は規模の既定の台本）。

ペットボトルとアマチュアの台本は段階チェーンです：分類 → 公式で定量要求を算出＋最も近い実機キット（文脈）→
`auto_design`（基準案、試行 1）→ `design_stage` で選び直し（各呼び出しは、変える段階のうち最も上流から。テストで検査）→
`design_from_parts` で最終構成を確認（試行 2）→ 多数回試行（部品表の費用で予算判定）→ 最終 JSON。
企業級の台本は従来どおり実機の種から：分類 → 定量要求 → 近い実機から種設計（ピッチ指令を再調整するため数秒）→
試行 1〜3 → 多数回試行 → 最終 JSON。

| 台本（要求） | 基準案（auto_design） | 選び直し（design_stage、上流から） | 最終（design_from_parts） | 成功率（n=100） |
| --- | --- | --- | --- | --- |
| demo_bottle（卵、30 m、3,000 円、1.5 L） | 1.0 L ボトル・15 mm ノズル・水 25 %・500 kPa（上限）：29.9 m、730 円、合格 | ① `bottle`：ユーザーの 1.5 L（合格 29.9 m、364 kPa）② `pressure`：合格する最低圧 350 kPa（29.1 m、上限まで余裕） | 1.5 L・22 mm ノズル・350 kPa・30 cm 傘：29.1 m、1,150 円、合格 | 0.98 |
| demo_amateur（1 kg、2 km、5 万円） | J435WS（24 本列挙、13 本検証、1 本合格）・LOC 54 mm・胴 1,363 mm＝2 本＋カプラ・5.5 cal（過安定警告）・Level 2 警告：1,871 m、33,930 円、合格 | ① `mount`：カプラを避ける 98 mm 一本胴（motor_mount_38mm_98）は 948 m で不合格 → 上位候補（54 mm）を維持 ② `fins`：合格する翼のうち余裕が最小の後退翼 5.3 cal（胴が長く 2〜3 cal には届かない） | 同構成・後退翼：1,871 m、33,930 円、合格（Level 2・カプラ・過安定を明示） | 0.71 |
| demo_model_rocket（200 g、500 m、2 万円、資格なし） | F32T（57 Ns、低出力・資格不要）・Estes BT-60・2 本＋カプラ：502 m、9,340 円、合格 | 資格：高出力警告なし → 選び直し不要 ① `body_tube`：一本胴の BT-80 は 301 m で不合格、BT-55 は F 級に非対応 → BT-60 を維持 | 基準案を確認：502 m、9,340 円、合格 | 0.87 |
| demo_commercial（150 kg、400 km、20 億円） | （実機の種）Electron を縮尺、ピッチ再調整：合格 399.5 km | 試行 2：1 段目を 4,000 kg に削減 → 近地点 -1.9 km で不合格／試行 3：2 段目を 900 kg に削減 | 400×498 km、5.0 億円、合格 | 0.94（試行 1） |

成功率は `scripts/check_scenarios.py` の実行値（2026-11-03）。σ や部品を変えると変わります。

モデルとレビュアーの設定は `config/models.yaml` にあります：

- `design_model`（`claude-opus-5-5`、adaptive thinking、`effort: high`）が設計判断を行い、
  `light_model`（`claude-haiku-5-5`）が軽い処理を担当します。
- `max_attempts`（40）は試行（`simulate_design` / `design_from_parts` / `auto_design`）の呼び出し回数の上限、
  `max_turns`（80）は API 往復回数の上限です。`design_stage` は探索で、試行に数えません（候補は UI の「設計の決定順」に出ます）。
- `reviewers`：安定性・回収・費用・安全の 4 観点のレビュアーが、合格した設計案ごとに並列で動きます
  （`enabled`, `model`, `effort`, `max_tokens`, `max_rounds_per_candidate`）。判定は `review` イベントとして
  配信され、major / blocker の指摘は設計役に返されます。blocker が付いた案は最終の合格一覧から外れます
  （`review_gate` 種別の `warning` イベントで通知）。ツール結果に無い数値を引用した指摘はコードで除外します。

## 段階チェーン（ペットボトル・アマチュアの設計の決定順）

ペットボトルとアマチュアの設計は「部品の選択」で、決まった順に決めます。各段階はそれより前の段階だけに依存し、
ある段階を変えるとそれより後の段階はすべて既定の規則でやり直しになります（`rocketwright/design_chain.py`）。

| 規模 | 段階の順序 |
| --- | --- |
| amateur | `motor` → `mount` → `body_tube` → `nose_cone` → `body_length` → `fins`（材料＋平面形）→ `parachute` → `deploy_delay` |
| bottle | `bottle` → `nozzle` → `water_fill` → `pressure` → `fins` → `parachute` |

**候補の絞り込み（funnel）。** 1 段階ぶんの候補（`design_stage`）は、上流の決定と両立するカタログの全選択肢を列挙し、
それぞれを下流の既定の規則で完全な構成に仕上げ、`design_from_parts` と同じ手順（部品の解決 → 組立可否の検査 →
エラーが無ければシミュレーション → 要求との照合 → 採点）で評価します。結果は「列挙 → 適合 → 検証 → 合格」の件数と
除外理由の内訳（「頂点高度が目標外」「予算超過」「非認定の代替モーター」など）として返り、UI の「設計の決定順」に並びます。
候補が多い段階（フィンの平面形は 1,800 通り）は、シミュレーション前の安価な順位で上位だけを検証します。
`auto_design` は各段階の最良候補を順に採る貪欲な歩みで、決定的です（同じ入力なら同じ基準案）。

既定の規則（`CHAIN_RULES`、すべて provisional）：

| 段階 | 既定の規則 |
| --- | --- |
| motor | `derive_requirements` の総力積以上で、取り付けられるマウントがある最小の**認定モーター**（`dummy_*` の合成代替は、認定モーターが 1 本も合格しない時だけ候補になり警告が付く） |
| mount / body_tube / fin material | 小さなビーム探索：両立するマウント × 入るチューブ × モーターに対応する軽いフィン材 2 種を、下の規則で仕上げてシミュレートし採点 |
| nose_cone | チューブに合う最軽量 |
| body_length | 組立可能な最小長（モーター室＋畳んだパラシュート＋ショックコード＋積載室）＋1 径。最小長が在庫チューブ 1 本に収まるなら 1 本に切り詰め |
| fins | 選んだ材料で、静安定余裕 2.0 cal 以上になる最小の平面形（`FIN_GRID`） |
| parachute | 畳んで胴に収まり、降下速度 5 m/s 以下になる最小の傘 |
| deploy_delay | 0 s（頂点で開傘。滑空時間に最も近い遅延グレインを説明に示す） |
| bottle | `derive` の 1.5 L に最も近いボトル |
| nozzle / water_fill | 首に入る最大のノズル／`derive` の 40 % |
| pressure | 目標頂点高度に対して `brentq` で解いた圧（kPa 単位、ボトルと物理の上限でクリップ）＋切りの良い 50 kPa 刻みの候補 |
| fins / parachute (bottle) | 最軽量のフィン／積載か回収要求があれば降下 5 m/s 以下の最小の傘（なければなし） |

採点（辞書式、小さいほど良い）：組立エラーなし ＞ 要求を満たす（頂点 ±10 %、降下速度、安定余裕、レール離脱速度、予算）＞
在庫チューブ 1 本（カプラ不要）＞ derive のモーター級 ±1 級（motor 段のみ。公式が合格したシミュレーションに勝たないように）＞
失敗理由が少ない ＞ 頂点高度の誤差（1 % 刻み）＞ 費用 ＞ 離床質量 ＞ 選択肢 id（決定性のため）。

**現実性の規則（`build.check_buildability`）。** 机上で飛ぶだけの機体を避けるため、組立可否の検査が次を強制します：

- **定格**：胴体チューブとフィン材はカタログに対応できる最大総力積（`max_motor_impulse_ns`、根拠は `rating_note`）を持ち、
  超えるとエラー（`tube_power_rating` / `fin_power_rating`）。例：Estes BT-55 は 40 Ns（E 級）、BT-60/BT-80 は 80 Ns（F 級）、
  LOC 54/75/98 mm は 1,280 Ns、合板 3 mm は 1,280 Ns、G-10 1.6 mm は 640 Ns、バルサ 3.2 mm は 80 Ns。
  回収金具（ショックコード）は機体質量の上限を持つ（エラスティック 0.68 kg、ナイロン 3/16 in 0.91 kg、3/8 in 3.18 kg）。
- **室の長さ**：胴はモーター室（モーター長とマウント長の長い方）＋畳んだパラシュート（傘面積 × 0.50 mm）＋ショックコード 1 径＋
  積載室（積載質量を 600 kg/m³ で内径に詰めた長さ、または `payload_length_m`）を収める（エラー `body_length_min`）。
- **カプラ**：在庫チューブより長い胴は、チューブを継ぎ手（カプラ）でつないで作る。部品表に本数分のチューブとカプラが載り、
  警告 `body_length_stock` が付く（カタログに合うカプラが無ければエラー）。
- **認定モーター**：実在のモーター 19 本（AeroTech 14、Estes 5）は公表値（総力積・寸法・質量・遅延・価格）に合わせた推力曲線を持つ。
  `dummy_*` の合成代替は認定モーターで合格しない時だけ使い、警告が付く。
- **資格**：160 Ns（G 級）を超えるモーターは高出力で、NAR/Tripoli の **Level 1**（H, I）または **Level 2**（J〜L、640 Ns 超）
  の資格と高出力の打ち上げ会が必要（警告 `high_power_motor`）。エージェントは最終回答でユーザーに必ず伝える。

**予算に正直に。** 予算内に合格案が無いとき、`auto_design` は定数を曲げずにそう言います（`feasibility`）：予算を外した
費用優先の歩みで見つけた「最も安い合格案」とその超過額、予算内で最も良い案とその失敗理由。エージェントはその数値を
そのまま伝え、最も安い合格案か要求の緩和（高度・積載・予算）を提案します（聞き返しは 3 問まで）。

**UI。** 「詳細」の「設計の決定順」に、基準案の各段階（段階 → 採用部品 → 理由 → 絞り込みの件数 → 次点 3 件）と、
各 `design_stage` の結果（段階、合否つきの候補と理由、やり直しになった下流の段階）を時系列で表示します。表示中の機体に
資格（Level 1/2）やカプラの警告があれば、3D 表示の上部に琥珀色の注記を出します。

## Design direction: hierarchical exploration / 階層的な設計探索

**Proposal, not an implemented capability or a commitment for the competition deadline.**
The current implementation uses tier-specific schemas and Python simulation tools. The
following describes a direction for extending that loop; MATLAB integration and a general
multi-level shape/material optimizer are not claimed to be available.

日本語の要点：設計変数は一列の入力項目ではなく、ミッション・機体全体・各部の形状や材質が
相互に制約を与える階層として整理します。候補生成→解析→評価→上位要求へのフィードバックを
繰り返し、設計と検証を一体で進める構想です。MATLAB等の解析手法も選択肢ですが、未実装です。

### Coupled levels, rather than a one-way pipeline

| Level | Decisions and variables to represent | Feedback to exchange |
| --- | --- | --- |
| Mission / requirements | Purpose, payload, target altitude or orbit, recovery needs, budget, and acceptance criteria | Feasibility, uncertainty, and trade-offs may require revisiting the requirements |
| System / architecture | Tier, overall configuration, interfaces, and allocations of mass, cost, and performance | Lower-level results update system feasibility and available margins |
| Subsystem / geometry / materials | Allowed external geometry, material choices and their properties, structural assumptions, and component selection | Mass, compatibility, uncertainty, and verification needs constrain the system-level choices |
| Analysis / evidence | Model fidelity, solver, assumptions, input/output units, and validation references | Results and model limits determine which candidates can be compared and which need further investigation |

Higher and lower levels should be co-designed through iterative feedback, rather than
permanently fixing all upper-level choices before exploring lower-level alternatives.
This does not require every solver to run at the same time: dependencies, model cost, and
available evidence determine the order. A change in geometry or material must invalidate
the dependent results rather than leave stale evaluations attached to a candidate.

### Co-design the intermediate design space

**Future direction:** the middle layer's search space is itself a design decision, not a
fixed list of variables supplied once at the start. Design its variable set,
parameterization, bounds, and constraints using both upstream requirements and downstream
realizability. Optimizing values inside a fixed space and revising that space are different
operations; the loop needs to support both explicitly.

- Upstream requirements determine which distinctions matter, what must remain fixed, and
  which objectives or constraints the middle layer must expose.
- Downstream component, geometry, material, and model feasibility determines which
  combinations can actually be represented and evaluated.
- When either side changes, reconsider whether to add, remove, split, combine, or
  reparameterize variables; revise justified bounds and coupling constraints accordingly.
- Keep design variables separate from derived quantities and uncertainty parameters.
  Do not make an infeasible design appear feasible by silently relaxing a requirement.
- Version each design-space definition and its rationale. Map retained candidates to the
  new representation where valid, invalidate incompatible results, and rerun affected
  analyses before comparison.
- Validate the revised representation with both neighboring layers. If feasibility or
  parameter bounds lack evidence, record that uncertainty and request review rather than
  inventing precise limits.

日本語の補足：中間レイヤーでは値を探すだけでなく、**何を変数にするか、どう表現するか、
どの範囲・制約で探索するか**も上位要求と下位の実現可能性に合わせて更新する構想です。

### Match methods to variables within each level

A layer should not be assigned one universal simulator. Within the same layer, different
variables need different models, evaluation criteria, and search strategies. The examples
below are **options to assess**, not implemented integrations or validated predictions.

| Variable or decision | Candidate calculation / analysis method | Evaluation and constraints | Exploration and fidelity considerations |
| --- | --- | --- | --- |
| External shape and dimensions | Geometric checks and simplified aerodynamic estimates; higher-fidelity flow analysis only if justified | Packaging, model applicability, drag estimates, and uncertainty | Screen inexpensive geometric alternatives first; re-evaluate selected candidates with consistent assumptions |
| Material choice and structural dimensions | Material-property lookup, mass accounting, simplified structural/thermal checks; finite-element analysis as a possible later tool | Mass, stiffness, strength/thermal margins, compatibility, and evidence quality | Discrete material choices and continuous dimensions require different handling; retain property sources and applicable conditions |
| Catalog propulsion choice and system mass allocation | Catalog lookup, mass/energy budgets, and the existing simplified ascent models | Mission compatibility, estimated performance, mass/cost constraints, and provisional-data warnings | Compare catalog-level alternatives only; no internal engine or propellant design |
| Recovery configuration | Simplified descent model and sensitivity/dispersion analysis | Recovery requirements, descent metrics, and uncertainty under environmental variation | Use nominal checks to screen candidates before more expensive robustness evaluation |
| Mission target and architecture | Requirements consistency checks and system-level feasibility models | Whether the supported mission can be represented and evaluated at all | Unsupported missions require a scope decision, not a more detailed-looking result from an unsuitable solver |

Separate the **analysis model** from the **search algorithm** and the **execution platform**.
MATLAB, for example, could host an analysis or search routine, but its use alone does not
specify the physics, fidelity, validation, or appropriate optimizer.

Track a dependency map from each variable to affected models, outputs, constraints, and other
variables. For example, a material change can alter mass and structural assumptions, while a
shape change can alter both mass and aerodynamic inputs. Recompute the affected chain and
propagate its consequences upward and sideways before comparing candidates.

Use multiple fidelities deliberately: inexpensive screening, targeted refinement, and
validation against independent references answer different questions. Record model cost and
uncertainty, compare candidates on a compatible basis, and avoid treating a higher-fidelity
solver as automatically more trustworthy without suitable inputs and validation.

### Context-dependent analysis modes

**Proposed architecture:** choose an analysis mode from both the current variables and the
state of adjacent levels, rather than mapping each variable permanently to one solver.
A mode packages the model, numerical method, fidelity, assumptions, and evaluation rules
appropriate to the current question.

Selection inputs should include upstream mission/configuration choices, downstream geometry
and material values, the relevant flight/environment regime, design maturity, required
accuracy, available evidence, and compute budget. An updated value at any linked level can
make the current mode invalid and require reselection and reevaluation.

Illustrative hypotheses to validate, not implemented switching rules:

- Early architecture exploration may use inexpensive aggregate models; selected candidates
  may justify more detailed subsystem analysis once the needed inputs exist.
- A change in configuration, geometry, material, or operating regime may invalidate a
  model's assumptions even when the variable names are unchanged.
- A nominal comparison and an uncertainty/robustness assessment may require different
  evaluation modes; neither replaces the other.

Each mode should declare its supported input domain, required inputs, limitations, expected
cost, validation evidence, and output contract. Selection should produce a traceable record
of the input context, chosen mode/version, selection reason, rejected alternatives, and
uncertainty. Never invent numerical switching thresholds without evidence.

An AI agent may propose a mode, but applicability checks and validation against references
must verify that choice. If no validated mode applies, report the analysis as unsupported or
request human review instead of silently extrapolating. Test boundary cases, transitions,
cross-mode consistency, and recomputation after changed inputs before relying on automatic
mode selection. This is a future design goal, not a claim about the current tier selector.

#### Select tools within an analysis domain, and ask when context is missing

**Proposed behavior, not implemented:** "vibration analysis", "aerodynamics", or "thermal
analysis" is not enough information to select a tool or library. Selection should use the
physical applicability of a model as well as the software's supported capabilities.
The following are illustrative context checks, not validated solver recommendations.

| Analysis domain | Context and required inputs to resolve | Selection and constraint checks |
| --- | --- | --- |
| Vibration | Characteristic size, geometry, material properties, supports/connections, mass distribution, excitation, operating conditions, and the response of interest | Check whether the candidate model's dimensionality, linearity, boundary conditions, and frequency range suit the question; justify a reduced-order model or a more detailed method rather than selecting solely by the domain label |
| Aerodynamics | Speed and environment, characteristic size, shape, relevant flow regime, and required outputs | Match the model and implementation to the applicable flow regime and geometry; speed or size changes can require revisiting assumptions, tool/library choice, and evidence |
| Thermal | The specific part and material, mission destination/environment, operating phase and duration, heat inputs, interfaces, and the temperature quantity being evaluated | Establish relevant thermal processes and boundary conditions; check whether the intended model/tool can represent them and whether steady or transient evaluation answers the question |

For thermal constraints, distinguish a component's operating limits, survival/storage limits,
material limits, and any validated exposure-duration conditions. Upper and lower temperature
limits must come from applicable component specifications, material data, mission
requirements, or an explicitly reviewed assumption, with source, version, and conditions
recorded. A destination or part name alone is not evidence for a numerical limit. Missing
limits remain unknown; do not invent universal temperature thresholds.

The LLM's role is to **propose a supported selection or ask the user**, not to silently fill
critical gaps:

1. Identify which missing inputs could change applicability, tool choice, or acceptance.
   Ask focused questions about those inputs (for example, which component and operating
   phase, what environment/speed range, or what specification supplies the limits).
2. Use the confirmed context to propose a model, calculation method, and available
   tool/library. Explain the selection reason, alternatives, required inputs, known
   limitations, and unresolved uncertainty.
3. Verify the tool/version capabilities and model assumptions against their documentation
   and suitable validation evidence. A plausible LLM explanation is not validation, and
   a runnable tool is not proof that its physics applies.
4. Record the context, sources, assumptions, selected mode/tool/version, and validation
   status with the result. Reopen the selection when the part, mission, scale, speed,
   environment, or adjacent-layer decisions change.
5. If necessary inputs or applicable evidence remain unavailable, label the result
   exploratory or unsupported and ask for review. Human reviewers retain final judgment
   on the modeling choice and whether the evidence supports the design decision.

日本語の補足：同じ振動・空力解析でも、速度・大きさ・環境・境界条件によって適切なモデルや
ツール／ライブラリを選び直す構想です。熱設計も部品・飛行先・運用段階に応じて必要な解析と
温度制約の根拠を確認します。LLMは根拠付きで選択案を示すか、不足情報を人に質問し、
適用範囲・不確かさ・検証状況を明示した上で、最終判断を人に委ねます。

### Candidate-generation and evaluation loop

1. **Define the design space.** Separate requirements, hard constraints, controllable
   variables, derived quantities, and uncertain assumptions. Identify which level owns
   each decision and which other levels depend on it.
2. **Generate alternatives.** Choose an exploration method suited to the variables and
   model cost. Catalog selection, parameter sweeps, or constrained search are possible
   approaches to assess, not a claim that all are implemented.
3. **Analyze each candidate.** Use the appropriate model and fidelity for the question.
   Existing Python tools are the starting point; a MATLAB simulation adapter is a future
   option. Any adapter needs a defined input/output contract, units, model/version identity,
   reproducibility settings, and failure reporting before its results can be compared.
4. **Evaluate constraints and trade-offs.** First check required constraints, then compare
   objectives such as mission fit, mass, cost, robustness, and confidence in the evidence.
   Report trade-offs or non-dominated alternatives instead of hiding them in an unexplained
   single score. Model uncertainty is distinct from candidate performance.
5. **Feed results back across levels.** An infeasible or weak lower-level choice can trigger
   changes to allocations, architecture, or an explicitly reconsidered mission requirement.
   Record what changed, why, and which analyses must be rerun.
6. **Stop and review.** Define an evaluation budget and completion criteria; retain candidate
   lineage, assumptions, model provenance, and reasons for rejection for human review.

The evaluation method must evolve with the design question: a visual geometry preview,
a simplified system simulation, and a higher-fidelity material/structural analysis are not
interchangeable evidence. A successful model run alone does not establish feasibility.

For the competition, first document the design variables and interfaces actually supported
by the existing demo. Broader hierarchical optimization, MATLAB coupling, and 3D export need
separate scope decisions and validation. All extensions must preserve the project limits in
`CLAUDE.md`: simulation/concept design only, no propulsion internals, manufacturing-ready
vehicle design, targeting, or guidance/control implementation.

## Progress and submission plan / 進捗・提出計画

**Submission deadline: 2026-11-08 (Sun) 20:00 JST / 11:00 UTC.**
This follows the organizer's November 2 update for **Built with Claude: Japan 2026**.
The previous November 9–10 submission schedule is obsolete; do not use the final judging
date as the submission deadline. The team's target is to submit on Saturday, November 7,
keeping November 8 as a buffer.

日本語の要点：**提出締切は2026年11月8日（日）20:00（日本時間）**です。
旧記載の「11月9〜10日に動画・概要文を作成して提出」では間に合いません。
チームの提出目標は11月7日（土）で、11月8日は予備日です。
以下は公開済みコードの実装状況と、提出に向けた確認事項・計画案を分けて記載しています。

### Repository status (reviewed 2026-11-03)

The following describes code present on `main`, not a claim that live API calls, the web
build, or every user input have passed end-to-end validation. Unpushed work is not covered.

| Area | Present in the repository | Verification boundary |
| --- | --- | --- |
| Design and simulation | Four tiers, `water` / `solid` / `multistage` models, seeded dispersion, and reviewer integration | Simplifications and provisional data remain documented below; simulation results are not real-world flight certification |
| API and UI | FastAPI SSE design endpoint and Next.js candidate/review/flight displays | Live Claude API → browser → artifact download must be checked on the submission build |
| Exports | SVG side view, Markdown/JSON report, and BOM CSV | These are the formats exposed by `api/main.py` and `rocketwright/agent/store.py`; do not present them as completed 3D/STL export |
| Regression tests | `tests/test_scenarios.py` exercises physics and the agent loop with a scripted fake Claude client | A fake-client test pass is not evidence of live Claude behavior; this documentation update does not establish a new test pass |
| Frontend build | `web/package.json` provides `npm run build` | `web/README.md` still notes an unverified build; record a successful build against the final submission commit |

Artifact downloads are held in backend memory and expire after a restart or store eviction.
Save the files needed for the demo before stopping the API.

### Proposed workback plan (not completed milestones)

These are working targets to review with the team, not organizer requirements or additional
commitments. Prioritize a reproducible existing end-to-end demo over adding unverified scope.

| Target (JST) | Work | Exit criterion |
| --- | --- | --- |
| November 3–5 | Agree on the design inputs, supported mission scope, candidate comparison, and UI/backend interface; verify the existing end-to-end path | One documented live-API demo reaches the UI and downloads the expected artifacts; open issues are recorded |
| November 6 | Stabilize the demo and provisionally freeze submission scope | Regression/lint/build results and remaining limitations are recorded against a commit; unresolved extras are explicitly deferred |
| November 7 | Prepare the demo video (within 3 minutes), short summary, and public GitHub repository; recheck the package and submit | All required items are submitted and the confirmation is retained |
| November 8, before 20:00 | Buffer only: fix and resubmit if needed | Everything is in by **20:00 JST / 11:00 UTC**, not merely prepared |

### Submission readiness checklist

Unchecked items are verification tasks, not claims that the implementation is missing or broken.

- [ ] Run `uv run pytest`, `uv run ruff check .`, and `uv run python scripts/check_scenarios.py`; record results and any skipped tests.
- [ ] Run `npm run build` in `web/`; verify the browser flow against the same backend commit.
- [ ] Check live Claude behavior on supported demo inputs, including rejected/out-of-scope requests, unsuccessful candidates, and retry/error handling.
- [ ] Review candidate geometry, labels, units, and download contents; agree on whether 3D visualization/export is in submission scope before describing it as available.
- [ ] Ensure the video and summary distinguish simulated results, provisional values, and unverified capabilities.
- [ ] Check the public repository, video, and summary links; exclude credentials and private development data.
- [ ] Submit by the organizer's deadline and retain confirmation.

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
（`uv run python scripts/check_references.py`、2026-11-03。軌道機はピッチ指令を再調整して積載能力を求める。
許容は各項目の `tolerance_frac`（頂点高度）と `mass_tolerance_frac`（乾燥質量）、既定 30 %）。

**ペットボトルとアマチュアの基準値はキット単位になりました。** 各項目は `build:`（`catalog/parts.yaml` の部品 id と
モーター id）を持ち、再現では部品を解決して得た乾燥質量を公表重量と比べ、その解決済み設計を飛ばして頂点高度を比べます
（手書きの `design` は `build` が無いときの予備）。このキット群が組立規則と段階チェーンの検証データで、エージェントは
最も近いキットを「どのキットに近いか」の文脈として引用します（ペットボトル・アマチュアの設計の起点は `auto_design`）。
フィン寸法とノーズ長はキットの公表値に無いため推定（各項目の `notes` に明記）。

| id | 規模 | 公表 頂点高度 / 乾燥質量 | sim 頂点高度 / 乾燥質量 | 誤差 (高度 / 質量) | 許容 (高度 / 質量) |
| --- | --- | --- | --- | --- | --- |
| estes_alpha_iii_c6 | amateur | 351 m / 34.0 g | 350.7 m / 31.1 g | -0.1 % / -8.5 % | 15 % / 15 % |
| estes_alpha_c6 | amateur | 305 m / 22.7 g | 350.5 m / 31.6 g | +14.9 % / +39.4 % | 15 % / 45 % |
| estes_big_bertha_c6 | amateur | 152 m / 70.9 g | 164.0 m / 82.7 g | +7.9 % / +16.6 % | 15 % / 30 % |
| estes_mean_machine_e12 | amateur | 213 m / 241 g | 325.2 m / 184.2 g | +52.7 % / -23.6 % | 60 % / 30 % |
| estes_hi_flier_c6 | amateur | 457 m / 31.2 g | 495.6 m / 18.9 g | +8.5 % / -39.4 % | 15 % / 45 % |
| estes_wizard_c6 | amateur | 488 m / 14.2 g | 495.6 m / 18.8 g | +1.6 % / +32.4 % | 15 % / 45 % |
| estes_viking_c6 | amateur | 488 m / 17.0 g | 495.9 m / 19.3 g | +1.6 % / +13.7 % | 15 % / 15 % |
| estes_baby_bertha_c6 | amateur | 175 m / 53.9 g | 181.0 m / 60.1 g | +3.4 % / +11.5 % | 15 % / 15 % |
| estes_der_red_max_c6 | amateur | 183 m / 68.0 g | 174.4 m / 69.9 g | -4.7 % / +2.7 % | 15 % / 15 % |
| estes_crossfire_isx_c6 | amateur | 351 m / 37.0 g | 349.7 m / 33.0 g | -0.4 % / -10.9 % | 15 % / 15 % |
| apte_2l_800ml_30psi | bottle | 19.0 m / （未公表） | 20.7 m / 100 g | +8.8 % / — | 15 % / — |
| apte_2l_800ml_40psi | bottle | 22.0 m / （未公表） | 25.6 m / 100 g | +16.5 % / — | 30 % / — |
| apte_2l_350ml_40psi | bottle | 18.4 m / （未公表） | 24.6 m / 100 g | +33.4 % / — | 45 % / — |
| apte_2l_350ml_20psi | bottle | 15.1 m / （未公表） | 15.6 m / 100 g | +3.2 % / — | 15 % / — |
| apte_2l_800ml_20psi | bottle | 17.0 m / （未公表） | 13.1 m / 100 g | -23.3 % / — | 30 % / — |
| apte_2l_1250ml_40psi | bottle | 18.9 m / （未公表） | 11.7 m / 100 g | -38.2 % / — | 45 % / — |
| fischer_1l_350ml_2p5bar | bottle | 17.5 m / 143 g | 16.2 m / 143 g | -7.5 % / 0 % | 15 % / 15 % |
| fischer_1l_255ml_2bar | bottle | 14.1 m / 143 g | 11.8 m / 143 g | -16.6 % / 0 % | 30 % / 15 % |
| fischer_1l_255ml_2p5bar | bottle | 17.4 m / 143 g | 15.1 m / 143 g | -13.0 % / 0 % | 15 % / 15 % |
| fischer_1l_325ml_2p5bar | bottle | 17.1 m / 143 g | 16.2 m / 143 g | -5.5 % / 0 % | 15 % / 15 % |
| electron | commercial | 300 kg（軌道投入能力） | 321.7 kg | +7.2 % | 30 % |
| vega | commercial | 1,963 kg | 2,294.4 kg | +16.9 % | 30 % |
| firefly_alpha | commercial | 1,030 kg | 1,099.7 kg | +6.8 % | 30 % |
| epsilon_enhanced | commercial | 1,200 kg | 1,279.9 kg | +6.7 % | 30 % |
| falcon_9_ft | heavy | 22,800 kg | 23,450.1 kg | +2.9 % | 30 % |
| atlas_v_551 | heavy | 18,814 kg | 23,750.7 kg | +26.2 % | 30 % |

Fischer の質量 0 % は、論文の 143 g を閉じるよう部品 `bottle_fin_set_fischer_1l` を置いた整合性確認で予測ではありません
（Apte の論文は質量を公表していないため、`bottle_fin_set_apte_2l` が 0.10 kg の推定を閉じます）。
キット重量の誤差が大きい項目（Alpha +39 %、Hi-Flier -39 %、Wizard +32 %）は Estes の「重量」の定義が揃っていないことを示します
（同じ BT-20 キットで 14 g と 31 g）。Mean Machine は部品だけでは 241 g に届かず（カプラ・長いショックコードが未収録）、
軽くなった分 2 m の胴の摩擦抵抗を捉えない Cd 0.75 の過大予測がさらに増えます（+53 %、許容 60 %、既知の限界）。
軌道機の軌道高度は再調整により公表値の ±0.1 % 以内です。すべての項目が許容内（atlas_v_551 は 30 % の許容に対し +26 %：
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

`build.py`（部品設計の組立規則 `BUILD_THRESHOLDS` と手当 `ALLOWANCES`、すべて provisional。キット単位の基準値
`catalog/references/amateur.yaml` が規則の検証データで、実キットが規則に反したときは規則の側を直した）：

| キー | 仮置き | 根拠・変更理由 |
| --- | --- | --- |
| body_length_margin_calibers | 2.0（胴長 ≥ モーター室 + 2 径） | モーター室は max(モーター長, マウント長)。旧「モーター長 + マウント長」は Baby Bertha（胴 204 mm）を不可としたため修正 |
| 胴長 > 在庫チューブ長 | 警告（旧：エラー） | Mean Machine は BT-60 3 本をカプラで継ぐ。部品表は本数分を買い、カプラ質量は未計上 |
| deploy_delay_s = 0 | 常に許可 | 「頂点で開傘＝燃焼終了から頂点までの遅延グレイン」。E12 には 0 秒品が無いが Mean Machine は E12-4 でそう飛ぶ |
| error_static_margin_cal | 1.0 cal（エラー） | 1.0〜1.5 cal は警告のみ（旧：1.5 未満でエラー）。Baby Bertha が Barrowman 法で ~1.3 cal |
| min_static_margin_cal / max | 1.5 / 4.0 cal（飛行モデルと同じ） | 飛行判定は従来どおり 1.5 cal |
| fin_span_max_calibers | 2.5 | 警告のみ |
| liftoff_twr_error / warn | 3.0 / 5.0 | NAR の 5:1 目安 |
| fill_frac_min / max | 0.2 / 0.6 | 警告のみ（Apte 1250 mL = 62.5 % は実飛行） |
| adhesive_paint_mass_frac | 10 % | Estes の公表重量は塗装込みか不明 |
| motor_price_jpy_per_ns | 25 円/Ns（旧 60） | 米国小売 × 150 円/USD（G80 約 $30、H128 リロード約 $40、J420 リロード約 $80）。旧値は J を 5.6 万円と見積もり実売の 3〜4 倍 |
| motor_price_min_jpy | 600 円 | Estes C6 |
| payload_packing_density_kgpm3 | 600 kg/m³ | 積載（電子機器・電池・錘・緩衝材）を内径いっぱいの円柱に詰めた密度。ノーズの肩は使わない（SIMPLIFICATION） |
| parachute_packed_thickness_m | 0.50 mm（傘面積あたり） | Fruity Chutes の畳んだ体積（36/48 in で 0.52〜0.53 mm）と Estes BT-20 キットの傘室から上限 0.52 mm |
| shock_cord_bay_calibers | 1.0 径 | ショックコードと耐熱紙の室 |
| high_power_min_impulse_ns / level2_min_impulse_ns | 160 / 640 Ns | NAR/Tripoli の区分（G 以下は資格不要、H・I は Level 1、J〜L は Level 2）。出典は AeroTech 注文書 |
| 定格 `max_motor_impulse_ns`（parts.yaml） | チューブ・フィン材ごと（上の「現実性の規則」） | 各部品の `rating_note`（キットの最大モーターから推定、provisional） |
| 定格 `max_rocket_mass_kg`（回収金具） | 0.68 / 0.91 / 3.18 kg | LOC のショックコードの対応重量 |

`design_chain.py`（`CHAIN_RULES`、段階チェーンの既定の規則と列挙の制御、すべて provisional）：

| キー | 仮置き |
| --- | --- |
| default_static_margin_cal | 2.0 cal（フィンの既定：これ以上になる最小の平面形） |
| default_descent_speed_mps | 5.0 m/s（傘の既定：これ以下になる最小の傘） |
| default_body_extra_calibers | 1.0 径（胴長の既定：組立可能な最小長＋これ） |
| fill_min/max/step_frac | 0.25 / 0.55 / 0.05（水量の候補） |
| pressure_round_pa / pressure_lattice_pa | 50 kPa 刻みの候補 / 解いた圧は 1 kPa 単位 |
| apogee_error_bin_frac | 1 %（頂点誤差はこの刻みで比べ、次に費用） |
| max_sims_per_stage / max_sims_fins_stage | 16 / 10（これを超える候補はシミュレーション前の順位で間引く） |
| motor_class_window | ±1 級 |
| beam_fin_materials / beam_class_window / beam_max_sims | 2 / ±1 級 / 12 |

`config/tiers.yaml`：

| 規模 | キー | 仮置き |
| --- | --- | --- |
| bottle | target_altitude_max | 100 m |
| bottle | payload_mass_max | 0.2 kg |
| bottle | budget_min | 1,000 円 |
| amateur | target_altitude_max | 5,000 m（国内のクラブ・法規の慣行による） |
| amateur | payload_mass_max | 5 kg |
| amateur | budget_min | 5,000 円（旧 30,000 円。部品表では 200 g を 500 m に上げる低出力機が約 9,000 円で、旧値はこれをペットボトルに落とした） |
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

- `motors/*.eng`：実在のモーター 19 本（AeroTech F32T〜J435WS の 14 本、Estes A8〜E12 の 5 本）は、総力積・平均推力・
  寸法・質量・遅延・価格を公表値（thrustcurve.org の認定要約、Estes の製品ページ、AeroTech 注文書）に合わせた
  **合成の推力曲線**（曲線データは複製していない）で、provisional。`dummy_F32`〜`dummy_J420` の 5 本は実在しない合成の代替で、
  認定モーターが合格しない時だけ候補になります。出典とライセンスのある曲線に置き換えるまで、`solid` の結果には警告が付きます。
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
(`bottle`, `amateur`, `commercial`, `heavy`), lets Claude design with that tier's physics model
and parts catalog, launches every candidate in a deterministic simulator (including seeded
Monte Carlo dispersion), and returns only the designs that pass, with drawings, bill of
materials, flight analysis and success rate. Before designing, the agent derives quantitative
targets by closed formulas (`derive_requirements`: required delta-v, total impulse and motor
class, gauge pressure, ...).

Bottle and amateur rockets are designed by a **staged design chain**: parts are decided in a
fixed order (amateur: motor -> mount -> body tube -> nose cone -> body length -> fins ->
parachute -> deploy delay; bottle: bottle -> nozzle -> water fill -> pressure -> fins ->
parachute). For each stage the code enumerates every compatible catalog option, completes it
into a full build with default rules, checks buildability and simulates it; the candidate
funnel (enumerated / compatible / simulated / passed, with rejection reasons) is shown to the
user. `auto_design` walks all stages greedily for a deterministic baseline; the agent then
revises with `design_stage` starting at the most upstream stage that must change (motor before
tube before fins), quotes each candidate's `why`, and confirms the final build with
`design_from_parts`. Realism rules reject paper rockets: power ratings of tubes, fin stock and
shock cords, motor / parachute / payload bays, joined tubes with couplers, certified motors
only (synthetic placeholders as a last resort), and NAR/Tripoli Level 1/2 certification
warnings above 160 Ns. When nothing passes within the budget the agent says so with the
cheapest passing design and the best one within budget. Commercial and heavy designs are seeded
from the nearest real vehicle in `catalog/references/` (Electron, Atlas V, ...), scaled by
provisional rules; for the small tiers the nearest real kit is cited as context.

Four demo scenarios run end to end without an API key (`scenarios/`): a 1.5 L bottle lifting
an egg to 30 m, 1 kg to 2 km on a 50,000 JPY budget (J motor, Level 2), a 200 g / 500 m
model rocket without certification (F motor), and a 150 kg smallsat to a 400 km orbit.
When a formula and the simulation disagree, the simulation wins and the agent names the
assumption that explains the gap. The reproduction table above (設計精度) shows every reference
within its tolerance. Everything is simulated; nothing is launched. Claude thinks, chooses and
explains; every number comes from a tool call and carries that call's id as provenance. Values
without a source are marked `provisional: true` and listed above under 要確認の値 (including the
chain rules, payload packing density 600 kg/m3, parachute packing 0.50 mm per unit canopy area
and the part ratings). Built for Built with Claude: Japan 2026, MIT licensed.

Quick start: `uv sync --group dev && uv run pytest`, then
`uv run python scripts/run_scenario.py scenarios/demo_amateur.yaml --dummy` (no API key) or
without `--dummy` for the live Claude API (`ANTHROPIC_API_KEY`); `uv run python
scripts/check_scenarios.py` checks all four scenarios. The web UI (`web/`, Node >= 18.18)
talks to `uv run uvicorn api.main:app --port 8000`.
