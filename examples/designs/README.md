# 3D モデル担当への受け渡し

RocketWright の設計案は `Design` という JSON です（`rocketwright/schema.py`、JSON Schema は
`design.schema.json`）。`tier` で 3 種類に分かれます。すべて SI 単位（m, kg, s, Pa）。

| tier | 例 | 主な寸法 |
| --- | --- | --- |
| `bottle` | `bottle.json` | ボトル容積 `bottle_volume_m3`、ノズル径、フィン有無、パラシュート有無 |
| `amateur` | `amateur.json` | 胴径・胴長、ノーズ形状（conical / ogive / elliptical）と長さ、フィン（枚数・翼根・翼端・スパン・後退・厚さ）、モーター ID |
| `commercial` / `heavy` | `commercial.json`, `heavy.json` | 段ごとの推進剤質量・構造比・エンジン ID と基数、ブースタ（heavy）、フェアリング質量 |

`commercial` / `heavy` には直径や長さが無いので、`rocketwright/drawing.py` と同じ規則で決めてください：
直径 `d = 0.05 × (推進剤総質量 kg)^(1/3)` m、段の長さ = 推進剤質量 ÷ (1000 kg/m³ × 断面積)、
フェアリング長 = 2.5 d。概念設計レベルで、製造用の図面ではありません。

## 受け渡し形式（提案）

- 入力：上の `Design` JSON（ファイルまたは標準入力）
- 出力：**バイナリ STL**（`.stl`、単位 mm）。ブラウザ表示（three.js の STLLoader）にも 3D プリンタにも使えます
- 呼び出し方：`python <your_tool> design.json out.stl` の CLI、または `build_model(design: dict) -> bytes` の Python 関数。どちらでも
  `rocketwright/model3d.py` から呼んで、`GET /artifacts/<id>.stl` で配信し、UI で表示します

モーター ID（`motor_id`）やエンジン ID の実寸は `rocketwright/catalog/motors/*.eng`（ヘッダに径・長さ）と
`rocketwright/catalog/engines.yaml` にあります。
