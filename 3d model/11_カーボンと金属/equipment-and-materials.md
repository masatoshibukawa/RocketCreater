# 機器と対応材料の比較

確認日：2026-11-07。代表的な掲載機器を選んだ。材料名の列は例であり、製品・世代・炉・ソフトまで無条件の互換リストではない。発表予定、研究用パラメーター、現行の公式対応を分ける。

| 掲載機器 | 方式・材料の例 | 一緒に確認するもの |
| --- | --- | --- |
| [UltiMaker Factor 4 / Factor 4+](https://support.ultimaker.com/s/article/How-to-print-with-UltiMaker-PPS-CF) | 短繊維FFF。UltiMaker PPS CF/PET CF等 | PPS CFはFactor 4でHT0.6、4+でCC+0.6優先。4+のHT0.6は実験扱い。S5の耐摩耗コア交換だけでPPS CF対応にはならない |
| [Raise3D E2CF](https://www.raise3d.com/E2CF) | IDEX・短繊維FFF。PA12 CF/CF+等の製品別プロファイル | 耐摩耗給材/ノズル、ドライボックス、ideaMaker、支持材の組。[PA12 CF Support](https://www.raise3d.com/materials/pa12-cf-support)は剥離用で水溶性とは別 |
| [Markforged Mark Two](https://markforged.com/3d-printers/mark-two) | 樹脂＋連続繊維。Onyx/Nylonと対応するCarbon/Fiberglass等 | Gen1/2・旧Standard/Professional/Enterpriseを区別。樹脂・繊維を任意に組み合わせない |
| [Markforged FX10](https://markforged.com/3d-printers/fx10) | CFRまたはMetal Kitで金属FFF。Onyx系＋対応繊維、17-4PH v2/316L/H13 v2等 | ヘッド/供給系/シート/校正の構成変更、金属はWash-1・焼結炉と後工程が必要 |
| [Anisoprint Composer A4/A3](https://support.anisoprint.com/composer/manual) | CFC。専用連続繊維＋CFC用樹脂、外周用樹脂 | マトリックス/外周用材料を区別、給材、繊維カッターとZオフセット、専用スライサーの経路 |
| [Raise3D Forge1 / MetalFuse](https://www.raise3d.com/metalfuse) | 間接金属FFF。掲載例はUltrafuse 316L/17-4PH | ideaMaker Metal、D200-E触媒脱脂、S200-C焼結等の指定構成。現行の素材供給・処理受入を再確認 |
| [Markforged Metal X](https://markforged.com/de/3d-printers/metal-x) | 金属FFF。17-4PH、H13、D2、Copper、Inconel等は製品世代別 | Wash-1・Sinter-1/2、界面材、後処理。現行表では316LはMetal X非対応、FX10対応 |
| [EOS M 290](https://www.eos.info/metal-solutions/metal-printers/eos-m-290) | レーザー粉末床。鋼/Ti/Al/Ni等の装置・層厚別プロセス | 粉末管理、ガス、造形板、粉抜き、指定の熱処理/加工と計測。全EOS粉末が無条件で使えるわけではない |
| [HP Metal Jet S100 Platform](https://www.hp.com/us-en/printers/3d-printers/products/metal-jet.html) | 金属バインダージェット。316L/17-4PH等の検証区分付き材料 | S100/S100P/S100Dで構成・硬化方法・有効高さが異なる。粉末/硬化/除粉/炉と生産能力を一式で見る |
| [Colibrium Spectra L](https://www.colibriumadditive.com/printers/eb-pbf-printers/spectra-l) | EB-PBF。Ti6Al4V Grade 5/23の掲載 | 真空・予熱/冷却、粉末ケーキ回収、ソフト/Point Melt版、Gradeと試験状態 |
| [Meltio M600](https://meltio3d.com/wp-content/uploads/2025/08/Meltio_M600_Datasheet.pdf) | ワイヤーレーザーDED。機種用パラメーターのある合金ワイヤー | 基板/固定、冷却、ガス、経路ソフトと加工。多線材オプションは任意の異材接合の証明ではない |
| [DMG MORI LASERTEC 65 DED hybrid 2nd Generation](https://us.dmgmori.com/products/machines/additive-manufacturing/powder-nozzle) | 粉末DED＋5軸切削。鋼/Ni系等の検証された粉末 | ノズル/粉末送りの校正、加工と溶着の順序、到達性・衝突、母材との適合 |

## 現行対応で特に確認した差

2026-11-07に確認したMarkforgedの当該製品の表を、参照不能時の判断用にも残す。機種/素材の改訂時は原表へ再照合する。

| Markforged製品 | Metal X Gen1/2 | FX10 Metal Kit |
| --- | --- | --- |
| 17-4PH v1 | 対応 | 非対応 |
| 17-4PH v2 | 対応 | 対応 |
| 316L | 非対応 | 対応 |
| H13 v1 | 対応 | 非対応 |
| H13 v2 | 対応 | 対応 |
| Copper / Inconel / A2 / D2 v1・v2 | 対応 | 非対応 |

UltiMaker PET CFのS5用構成は、2.85mm製品とCC0.4またはCC0.6。Tough PLA用AA0.4や、PPS CFのFactor専用条件と混ぜない。基材・処理の入口は[PET](../3d-model-skills/materials/3d-material-pet/SKILL.md)と[PPS](../3d-model-skills/materials/3d-material-pps/SKILL.md)。

[Markforgedの公式対応表](https://support.markforged.com/portal/s/article/Material-Compatibility-Matrix)では、金属FFFの316LはFX10のみ、17-4PH/H13はv1/v2でFX10の可否が異なる。旧PDFや発売記事の対応予定より現在の製品別表を使う。FX10にCopperやInconelをMetal Xの一覧から追加しない。

[PPS CF公式手順](https://support.ultimaker.com/s/article/How-to-print-with-UltiMaker-PPS-CF)と[PET CF公式手順](https://support.ultimaker.com/s/article/pet-cf-instructions)は、Factorの世代とコアを別に列記する。PET CFがS5で使えることからPPS CFの可否を推定しない。

[Ultrafuse Metal Solutionのガイド](https://forward-am.com/gain-knowledge/ultrafuse-metal-solution-quick-start-guide)にはDiscontinued表示がある一方、Raise3Dの掲載にはその材料が残る。サービス全体の契約・供給・受入が現在も成立するかは不明として、内製/外注計画の前に確認する。機器自体の販売終了まで一括して断定しない。

価格比較は本体・周辺設備・設備工事・ガス/消耗材・契約・加工/検査・保守を分けた見積で行う。カタログの最速造形速度だけで完成品の納期や単価を比較しない。
