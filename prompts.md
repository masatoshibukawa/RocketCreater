# Claude Code に投げるプロンプト集

前提：リポジトリ直下に `CLAUDE.md` を置いてから使う。各プロンプトはそのまま貼り付けられる形にしてある。

---

## 0. 初回（どちらか1人が最初に実行）

```
CLAUDE.md を最後まで読んで、このプロジェクトの骨組みを作ってください。

やること:
1. CLAUDE.md の「5. リポジトリ構成」どおりにディレクトリと空のモジュールを作る
2. Python は uv で管理（Python 3.11+）。依存：numpy, scipy, pydantic v2, pyyaml, fastapi, uvicorn, anthropic, pytest
3. web/ に Next.js (App Router, TypeScript) の雛形を作る。まだ中身は不要
4. rocketwright/schema.py に Requirement, Env, Design（tier で判別する共用体：BottleDesign / AmateurDesign / MultistageDesign）, SimResult, DispersionResult を定義する
5. config/tiers.yaml を作る。境界値は仮置きでよいが、全項目に provisional: true を付ける
6. LICENSE (MIT), .gitignore, README.md（英語＋日本語概要、「要確認の値」セクションつき）
7. pytest が通る状態（スキーマの往復テストだけでよい）でコミット

終わったら、作ったものと、人間が決めるべき値の一覧を報告してください。コードを書く前に、作るファイルの一覧を先に見せて確認を取ってください。
```

---

## 1A. 物理担当（初日〜2日目）

```
CLAUDE.md を読んだうえで、rocketwright/physics/multistage.py と atmosphere.py を実装してください（CLAUDE.md の 7 章「multistage」の仕様どおり）。

進め方:
1. まず tests/test_multistage.py にテストを書く
   - 真空・重力なし・抵抗なしの単段で、燃焼終了速度がツィオルコフスキーの式と 0.1% 以内で一致
   - 2段式で、段間分離後に質量が正しく減る
   - 同じ入力なら同じ結果（決定性）
   - 既存機の再現テストは tests/reference/ に基準値がなければ pytest.skip（理由を書く）
2. atmosphere.py：US Standard Atmosphere 1976（〜86 km）＋それ以上は指数近似
3. multistage.py：2次元質点、球形地球、抵抗、比推力の高度補正、開ループ重力ターン
4. simulate(design, env, seed) -> SimResult の共通インターフェースに合わせる
5. ピッチ開始時刻と角度を scipy.optimize で探して投入条件を満たす補助関数 tune_pitch_program を用意
6. engines.yaml にサンプルのエンジンを3〜5種。数値は公開資料の代表値で、出典 URL がないものは provisional: true

簡易化した箇所には # SIMPLIFICATION: コメントを付けてください。数値の出典が確認できないものを確定値として書かないでください。
最後に、テスト結果と、私（軌道力学の専門家）に確認してほしい仮定を箇条書きで報告してください。
```

## 1B. エージェント／UI担当（初日〜2日目）

```
CLAUDE.md を読んだうえで、設計探索エージェントの骨組みを作ってください。物理モデルはまだ未完成なので、ダミー関数で一周させます。

やること:
1. rocketwright/classify.py：CLAUDE.md 3章の規則で Requirement から tier を判定。矛盾時は required_tier と fallback を返す。テストを先に書く（軌道目標→commercial以上、明示指定の優先、予算矛盾のケース）
2. rocketwright/guard.py：CLAUDE.md 4章のスコープ外要求を検出。テストを書く（推進剤の製造、誘導制御、地上目標などは拒否、通常の要求は通す）
3. rocketwright/agent/tools.py：7つのツール定義（JSON Schema）と実装の対応表。simulate_design と run_dispersion は今はダミー（tier に応じてそれらしい形の SimResult を返す。値はダミーと明記）
4. rocketwright/agent/prompts.py：システムプロンプト。「数値はツール結果のみ」「スコープ外は一文で断る」「不足情報は最大3問」を含める
5. rocketwright/agent/loop.py：Claude API のツール使用ループ。モデル名は設定から（設計判断は claude-opus-5-5、軽い処理は claude-haiku-5-5）。試行上限 40。各ステップをイベントとして yield する
6. 最終出力の説明文に、ツール結果にない数値が含まれていないか検査する関数と、そのテスト
7. api/main.py：POST /design で要求を受け、SSE で進行イベントを流す
8. scenarios/demo_amateur.yaml と scenarios/demo_commercial.yaml（CLAUDE.md のデモ台本の要求文）を置き、CLI から実行できるスクリプト

API キーは環境変数 ANTHROPIC_API_KEY から読む。最後に、ダミー物理で一周したログの要約を報告してください。
```

---

## 2. 統合（11/4〜11/5、関門）

```
物理担当の multistage と、エージェントの骨組みを統合してください。

1. tools.py の simulate_design / run_dispersion を、tier が commercial/heavy のとき本物の multistage に差し替える
2. web/ に1画面のUIを作る（CLAUDE.md 9章）。左：対話、右：段階バッジ・設計案カード・飛行グラフ。SSE で試行の進行をリアルタイム表示
3. scenarios/demo_commercial.yaml が端から端まで通ることを確認し、回帰テストにする

関門は「11/5夜に commercial と amateur が UI で端から端まで動く」です。amateur（solid）は物理担当が並行で作っているので、インターフェースだけ先に合わせておいてください。
```

## 3. 以降のフェーズで使う短いプロンプト

- solid：`CLAUDE.md 7章「solid」と stability.py, recovery.py を実装。テストを先に。OpenRocket 比較の基準値は tests/reference/ にあれば使い、なければ skip。`
- water：`CLAUDE.md 7章「water」を実装。式は簡単でよいので半日で終わらせる。`
- dispersion：`CLAUDE.md 7章「多数回試行」を全段階に実装。n=100 が amateur で10秒以内。UI に着地分布と投入誤差の図を追加。`
- レビュアー：`安定性・回収・費用・安全の4観点のレビュアーを並列サブエージェントとして loop.py に追加。指摘を設計役に返して再設計させる。`
- 出力：`drawing.py（側面図SVG、寸法線つき）と report.py（Markdown レポートと部品表CSV）を実装し、UI からダウンロードできるようにする。`
- 凍結前の点検：`scenarios/ の全シナリオを実行し、失敗・遅い・表示崩れを一覧にして。新機能は追加しないで修正だけ。`
