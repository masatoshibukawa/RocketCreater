# RocketWright — プロジェクト仕様（Claude Code 用）

このファイルはリポジトリ直下に置き、Claude Code が毎回読む前提で書いている。作業を始める前に必ず全体を読むこと。

## 1. 何を作るか

**ペットボトルロケットの設計ツール**。ユーザーが自然文で要求（どこまで飛ばすか・何を載せるか・回収するか・予算）を伝えると、

1. 範囲を超える要求には「できません」と返し、
2. 部品カタログから Claude が設計案を作り、
3. シミュレータで仮想打ち上げ（ばらつきを入れた多数回試行を含む）して検証し、
4. 合格した設計案だけを、3D モデル・飛行解析・流体解析・製作票・部品表つきで返す

Web アプリ。実機は打ち上げない。すべてシミュレーション上で完結する。

- ハッカソン：Built with Claude: Japan 2026（提出締切 2026-11-08 20:00 JST、チームの提出目標は 11/7 土）
- 提出物：公開 GitHub リポジトリ、3分以内のデモ動画、短い概要文
- デモに映るものはすべてオープンソースで公開する（ライセンス：MIT）

## 2. 最重要の原則

1. **Claude は考える・選ぶ・説明する。数値はコードが出す。**
   エージェントがユーザーに示す数値（高度、速度、安定余裕、費用、成功率など）は、必ずこのリポジトリのツール関数の戻り値から取る。Claude が暗算や推測で数値を書いてはいけない。最終結果の数値と合否はコードが照合する（第 8 節）。
2. **決定的に動くこと。** 乱数は必ずシードを受け取る。同じ入力とシードなら同じ結果を返す。デモの台本は回帰テストとして固定する。
3. **締切から逆算する。** 精度より「端から端まで動く」を優先する。簡易モデルで割り切った箇所は `# SIMPLIFICATION:` コメントと README に明記する。
4. **出典のない数値をデータに入れない。** カタログ値・段階の境界値・検証用の基準値は、出典 URL を持つか、`provisional: true` を付けて人間の確認待ちにする。

## 3. 対象はペットボトルだけ

開いている規模は `config/models.yaml` の `allowed_tiers: [bottle]` で決まる。アマチュア・企業級・重工級のコードとテストは残っているが、設定で閉じている。動かせるのは、テストと台本のスクリプトだけ。

「できません」は次の順に効く。

| 順 | 場所 | 止めるもの |
| --- | --- | --- |
| 1 | `guard.py` の `check_bottle_limit` | 文章で明らかな要求：衛星、軌道、企業級、固体モーター、範囲を超える高度と荷物。**API を呼ばない** |
| 2 | `loop.py` の `_tier_refusal` | `classify_requirement` の結果が範囲を超える要求。文章からは読めなかったもの |
| 3 | `tools.py` の `get_tool_definitions(tiers)`、`prompts.py` の `BOTTLE_ONLY_NOTE` | Claude に渡すツールの型とプロンプトを、ボトルだけにする |

範囲は `config/tiers.yaml` にある。高度は `design_reach_max`（40 m）、荷物は `payload_mass_max`（0.2 kg）。`design_reach_max` は今の部品カタログで届く高さの実測値で、規模の境界の `target_altitude_max`（100 m）とは別物。カタログを変えて届く高さが変わると、`tests/test_guard.py` が落ちる。

ボトルの合否：到達高度が目標の ±10 % 以内、荷物つきの降下速度 6 m/s 以下、費用が予算以下、回収の要求があればパラシュートが要る。部品から組んだ案は、静安定余裕が注水時と空のときに 0 cal を超え、圧力はボトルの 500 kPa とランチャーの定格の小さい方まで。

## 4. スコープ外（安全上の線引き。エージェントのシステムプロンプトとコードの両方で強制する）

- 推進剤の配合・製造、エンジンやモーターの内部設計。
- 誘導制御ソフトウェア・姿勢制御の設計。
- 地上の特定地点を狙う弾道、再突入体、弾頭のような積載物。目標は「高度」のみ。地上の落下点は回収と安全区域の確認にだけ使う。
- 法規・許可の判断はしない。「要確認事項と確認先」のチェックリストに留める。

これらに該当する要求は、`guard.py` の `check_scope` が Claude に渡す前に止める。返す文は「できません。」で始める。

## 5. リポジトリ構成

```
rocketwright/                 # Python パッケージ（バックエンド本体）
  schema.py                   # pydantic モデル：Requirement, Design, Env, SimResult, DispersionResult
  classify.py                 # 規模分類（規則ベース）
  guard.py                    # スコープ外と範囲外の要求の検出
  parts.py build.py           # 部品カタログと、部品から機体を組む処理
  design_chain.py             # 段階を順に決める設計（auto_design, design_stage）
  derive.py                   # 要求から定量目標を公式で算出
  physics/                    # water（ボトル）、stability、recovery、atmosphere ほか
  dispersion.py cost.py drawing.py report.py summary.py
  catalog/                    # YAML：parts.yaml ほか（全項目に source/license）
  aero/                       # 流体解析：openfoam_pipeline, live, flow_frames, flow_images, loop
  agent/
    tools.py                  # Claude に渡す 13 のツールと実装の対応
    loop.py                   # 設計探索ループ（ツール使用・ストリーミング）
    prompts.py                # システムプロンプト（安全方針を含む）
    provenance.py             # 説明文の数値の検査
    final_check.py            # 最終結果の出典・数値・合否の検査
    review.py                 # 4 観点のレビュアー
    design_aero.py            # 流体解析のジョブ
    design_sheet.py           # 製作票
api/                          # FastAPI。main.py がエージェントの進行を SSE で配信
web/                          # Next.js (App Router, TypeScript) フロントエンド
config/
  models.yaml                 # 開いている規模、モデル、上限
  tiers.yaml                  # 規模の境界値（source または provisional）
scenarios/                    # デモ台本の固定シナリオ。回帰テストに使う
tests/
```

## 6. 共通インターフェース

```python
def simulate(design: Design, env: Env, seed: int | None = None) -> SimResult: ...
def dispersion(design: Design, env: Env, n: int, seed: int) -> DispersionResult: ...
```

- `Design` は `tier` と規模ごとの設計変数を持つ判別共用体。ボトルは `BottleDesign`。
- `SimResult` の共通項目：`success`, `failure_reasons`, `metrics`（キー名に単位を付ける：`apogee_m`, `max_speed_mps` など）, `cost_jpy`, `trace`, `warnings`, `source_id`。
- 合否は要求を満たすかをコードで判定する。
- 単位は内部ですべて SI。変数名に単位の接尾辞を付ける（`_m`, `_s`, `_kg`, `_n`, `_pa`）。表示時だけ変換する。

## 7. 物理モデル

### `water`（ペットボトル）
- 設計変数：ボトル容量、水の充填率、初期圧（ゲージ圧）、ノズル径、機体質量、羽根の有無、パラシュートの有無。すべて部品の選択から決まり、質量や径を手で打たない。決める順は bottle → nozzle → water_fill → pressure → fins → parachute。
- 力学：空気の断熱膨張（γ=1.4）、水噴射の推力はベルヌーイ式、空気噴射は簡易、その後は抗力つき弾道。
- 較正：`DEFAULT_CD=0.8` と `AIR_IMPULSE_EFFICIENCY=0.25` は組で実測に合わせた値。片方だけ変えない。

### 多数回試行（`dispersion.py`）
- ボトルでは初期圧と風をばらつかせる。出力：成功率、主要指標の分位点（5/50/95 %）、着地点の散布と 95 % 楕円。

### 流体解析（`rocketwright/aero/`）
- OpenFOAM を Docker イメージ `rocketwright/openfoam-pipeline:2412` で動かす。中の `rocketcfd` はライセンスのない外部のコードで、**リポジトリに入れない。コードを写さない**。
- 飛行計算と流体計算を交互に回し、抗力係数が収まるまで続ける（`aero/loop.py`）。
- 実行中の様子は、解析が書くファイルから読む（`aero/live.py`）。流れの動画は、`system/controlDict` の `slices` を実行中に書き換えて `FRAME_EVERY` 反復ごとに断面を出させ、1 枚ずつ絵にする（`aero/flow_frames.py`）。
- 格子収束はしておらず、実測との照合もない。「流体解析で精度が上がった」とは言わない。

## 8. エージェント（`rocketwright/agent/`）

- Claude API のツール使用で実装する。既定は `config/models.yaml`：`claude-haiku-5-5`、`effort: low`、`max_tokens: 16000`、試行 8 回、往復 24 回。この設定で端から端まで確かめた。モデルを変えるときは、このファイルの値も直す。
- ツール：`classify_requirement`, `derive_requirements`, `find_reference_designs`, `search_catalog`, `list_parts`, `auto_design`, `design_stage`, `design_from_parts`, `simulate_design`, `run_dispersion`, `estimate_cost`, `render_drawing`, `export_report`。ツール定義の長さは毎ターン費用になるので、テストで上限を見ている。
- ループ：要求の不足を最大3問まで聞き返す → 分類 → 定量要求を公式で算出 → `auto_design` で基準案 → 必要なら `design_stage` で上流から直す → `design_from_parts` で確定 → `run_dispersion`。
- 4 観点のレビュアー（安定性・回収・費用・安全）を並列に呼び、指摘を設計役に返す。blocker の付いた案は合格一覧から外す。
- 最終出力は JSON：設計案ごとに設計変数、主要指標、合否、費用、成功率、各数値の出典ツール呼び出し ID、説明文。
- 最終結果の検査は 2 つある。`provenance.py` は説明文の数値がツール結果にあるかを見る。`final_check.py` は `designs[]` の出典 ID が実在するか、数値と合否が出典の結果と合うかを見る。合わなければ Claude に 1 度だけ直させ、それでも合わない案は `rejected_by_check` へ移す。
- 利用者が読む文章は、すべて利用者の言語で書く（日本語の要求なら日本語）。
- 途中経過を SSE で UI に流す。

## 9. フロントエンド（`web/`）

- Next.js + TypeScript。画面は 1 枚で、工程は 設計／解析／出力 の 3 つ。左に相談、右に結果（設計の工程だけ）、中央が作業場。欄の境界はドラッグで動かせる。
- 背景は黒。中央の作業場の絵が黒い背景を前提にしている。
- 解析の工程は、計算中の流れの動画と、残差・力のグラフを出す。経過秒数は出さない。
- 選択肢はペットボトルの例だけを置く。範囲を超える要求の返事は、エラーではなく相手の返事として出す。
- 見た目より安定を優先する。

## 10. 開発の進め方

- 小さく作って毎回動かす。新しい関数には先にテストを書く（`pytest`）。
- コミットは小さく、メッセージは英語で何をしたか一行。
- 外部への通信は Claude API のみ。商用サイトのスクレイピングはしない。
- コード内のコメントは英語。README は日本語。
- 迷ったら：デモ台本（`scenarios/`）が動くことを最優先し、それ以外は後回しにする。
- 作業の最後に、変更点・未解決点・人間に確認してほしい値を短く報告する。
