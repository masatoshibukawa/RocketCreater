# parts.yaml v2 — 部品カタログの形式

設計は「部品の選択」で表す。質量・寸法・費用は部品から計算し、エージェントは決めない。
各部品は `source` URL か `provisional: true` を必ず持つ（CLAUDE.md 2 章）。

```yaml
version: 2
parts:
  - id: estes_bt50            # [a-z0-9_]+、一意
    kind: body_tube           # 下の一覧
    tier: amateur             # amateur | bottle
    name: "Estes BT-50 body tube"
    mass_kg: 0.0125           # kind ごとの基準（body_tube は stock 長での質量）
    price_jpy: 400
    source: "https://..."     # 無ければ provisional: true
    provisional: true
    notes: ""
    # 以下 kind 固有
```

| kind | tier | 固有フィールド |
| --- | --- | --- |
| `body_tube` | amateur | `outer_diameter_m`, `inner_diameter_m`, `length_m`（stock 長。設計の胴長 ≤ これ、質量は長さ比例）|
| `nose_cone` | amateur | `fits_tube_id`, `shape` (conical/ogive/elliptical), `length_m`（露出長）, `shoulder_length_m` |
| `motor_mount` | amateur | `motor_diameter_m` (0.018/0.024/0.029/0.038/0.054), `fits_tube_id`, `length_m` |
| `fin_material` | amateur | `thickness_m`, `areal_mass_kgpm2`, `sheet_width_m`, `sheet_height_m`（1 枚のフィンがこの板に収まること）|
| `parachute` | amateur, bottle | `diameter_m`, `packed_diameter_m`（収納先の内径 ≥ これ）, `cd` |
| `recovery_hardware` | amateur | （ショックコード・ワディング等の一式）|
| `launch_lug` | amateur | `fits_rod_diameter_m` |
| `bottle` | bottle | `volume_m3`, `body_diameter_m`, `length_m`, `neck_diameter_m`（PET 規格 0.0217 など）, `max_gauge_pressure_pa`（安全上限・出典）|
| `nozzle` | bottle | `diameter_m`, `fits_neck_diameter_m` |
| `bottle_fin_set` | bottle | `count`, `span_m`, `mass_kg`（材料：段ボール/PP 板など）|
| `launcher` | bottle | `max_gauge_pressure_pa`, `rail_length_m`（ポンプ／ランチャーの上限）|

モーターは従来どおり `motors/*.eng`（ヘッダに `; diameter_m`, `; length_m`, `; delays: 3,5,7`, `; source`, `; provisional`）。

## 追記（2026-11-03、カタログ再構築時に追加したフィールド）

- トップレベル `price_jpy_basis`（文字列）：`price_jpy` の算出根拠。現在は「USD × 150 JPY（固定・provisional）」。円建ての出典が無いため、全 `price_jpy` は暫定値として扱う。
- トップレベル `items`：`parts` の YAML エイリアス（`*parts`）。v1 の読み手（`_load_yaml_list(..., "items")`, `report.py`）の互換用。新しいコードは `parts` を読む。
- `motor_mount.fits_tube_ids`（list）：キットのリングが合う胴体 id の一覧。`fits_tube_id` は主たる胴体で、常に `fits_tube_ids` に含まれる。
- `motor_mount.motor_diameter_m` に `0.013`（ミニモーター）を追加。
- `source` を持つ部品でも、質量・収納径などが推定なら `provisional: true` を併記し、推定方法を `notes` に書く（CLAUDE.md 2 章 4）。
- `.eng` ヘッダの追加行：`; propellant_mass_kg`, `; total_mass_kg`, `; price_jpy`（換算・暫定）。`solid.load_motor` は RASP 行から直径・長さ・遅延・質量を読む（コメント行の `; delays:` は読み手向けの情報）。

## 追記（2026-11-03、現実性の強化で追加したフィールド・種類）

- `body_tube.max_motor_impulse_ns`（float、任意）／`body_tube.rating_note`（文字列）：その胴体が想定するモーターの総力積の上限（NAR/TRA 等級の上限値：A 2.5、C 10、E 40、F 80、G 160、I 640、J 1280 Ns）。`rating_note` に根拠（その胴体を使うキットの推奨モーター、メーカーのページ）を書く。モーターの総力積がこれを超えると `check_buildability` のエラー `tube_power_rating`。未設定は警告（同じコード）。Estes の紙胴体は低出力（BT-20/50 は C、BT-55 は E、BT-60/80 は F）、LOC の胴体は J まで。
- `fin_material.max_motor_impulse_ns`／`fin_material.rating_note`：同じ意味のフィン材の上限。超えるとエラー `fin_power_rating`（設計チェーンの旧「柔らかい材料」ヒューリスティックを置き換え）。
- `recovery_hardware.max_rocket_mass_kg`／`rating_note`：ショックコードと取付金具が売られている機体質量（打ち上げ時）の上限（LOC の表示：ゴム 24 oz、3/16 in ナイロン 32 oz、3/8 in ナイロン 7 lb）。超えるとエラー `recovery_hardware_rating`。
- 新しい種類 `coupler`（tier amateur）：`fits_tube_id`, `length_m`。胴長が stock 長を超えると、胴体本数 − 1 個のカプラーを部品表に載せ、乾燥質量に含める。その胴体に合うカプラーがカタログに無ければエラー `no_coupler`。
- `AmateurBuild.payload_length_m`（任意）：積載物の収納長。未指定なら積載質量 ÷ 600 kg/m³（provisional）÷ 胴体内径の断面積。胴長 ≥ モーター区画（モーターとマウントの長い方）＋ パラシュート区画（傘面積 × 0.50 mm ÷ 内径断面積 ＋ ショックコード 1 口径）＋ 積載区画、を満たさないとエラー `body_length_min`（`build.min_body_length_m`）。
- `.eng` ヘッダの `; price_jpy:`（先頭の数値を読む）は部品表のモーター価格になる（無い場合だけ従来の 25 JPY/Ns の暫定レート）。再装填式は `; hardware:`（ケース名）と `; hardware_price_jpy:`（再使用ケースの価格、初回に一度買う）を持ち、部品表に別行（質量 0：ケースはモーターの装填質量に含まれる）で載る。
