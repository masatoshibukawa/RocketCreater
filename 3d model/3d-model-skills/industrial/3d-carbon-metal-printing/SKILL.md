---
name: 3d-carbon-metal-printing
description: "カーボン系と金属の3Dプリンター、材料、造形方式、周辺設備、後処理を整理して専門スキルへ案内する。短繊維と連続繊維、金属風樹脂と実金属を区別する。"
---

# カーボン・金属3Dプリントの索引


まず完成物の用途、最終寸法・質量、荷重方向、温度/環境、個数、内製/外注を確認する。機種が未定でも方式の比較と見積仕様は作れる。[方式比較](../../../11_カーボンと金属/process-comparison.md)を使い、製品名の印象から方式を決めない。

| 入力・目的 | 読むスキル |
| --- | --- |
| PA-CF、PET-CF等の短繊維入りフィラメント | [既存の繊維入り材料](../../materials/3d-material-fiber-filled/SKILL.md)と基材スキル |
| 連続カーボン/ガラス/アラミドで荷重経路を補強 | [連続繊維](../3d-print-continuous-fiber/SKILL.md) |
| 金属粉末を含むフィラメント/バインダーから焼結品へ | [結合材を使う金属押出](../3d-print-metal-bound/SKILL.md) |
| レーザーで金属粉末床を溶融 | [LPBF](../3d-print-metal-lpbf/SKILL.md) |
| 電子ビームで金属粉末床を溶融 | [EB-PBF](../3d-print-metal-eb-pbf/SKILL.md) |
| 金属粉末へバインダーを噴射し、後で焼結 | [バインダージェット](../3d-print-metal-binder-jet/SKILL.md) |
| ワイヤー/粉末を溶着、肉盛り・修理、大型部品 | [DED・WAAM](../3d-print-metal-ded/SKILL.md) |

機器と掲載材料の実例は[機器表](../../../11_カーボンと金属/equipment-and-materials.md)。購入・外注の比較には本体だけでなく、素材、消耗品、ソフト/利用契約、乾燥/ガス/炉、設置、後処理、加工、検査、保守と不良時の費用を含める。見積金額と納期は日付・地域・構成付きで取得し、この資料の掲載を在庫・販売継続の確認へ読み替えない。

「カーボン」は材質/補強方式か社名かも確認する。[Carbon社DLS](https://www.carbon3d.com/carbon-dls-technology)は液体レジンを使う光造形で、連続炭素繊維の方式とは別。社名を指すなら[レジンのスキル](../../materials/3d-material-engineering-resin/SKILL.md)と当該機種・製品の指定工程へ振り分ける。

材料対応は商品・世代・装置構成・プロファイルごとに「公式対応/条件付き試作/非対応/不明」で返す。メーカーの金属並みという比較から等方性・耐熱・寿命を補完しない。[施設と品質の条件](../../../11_カーボンと金属/facility-and-quality.md)を必要な方式だけ読み、[記録JSON](../../../11_カーボンと金属/industrial-record.example.json)へ根拠と残る条件を残す。
