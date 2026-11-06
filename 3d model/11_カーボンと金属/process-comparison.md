# 方式と完成までの工程

確認日：2026-11-07。以下は方式の判断表。精度・速度・強度の固定ランキングにはしない。最終寸法、加工・検査、数量と施設条件で比べる。

| 方式 | 主な供給材 | 最終部品までの工程 | 設計・印刷で困る点 |
| --- | --- | --- | --- |
| 短繊維入りFFF | PA/PET/PPS等＋短いCF/GF | 乾燥→FFF→支持除去→製品によって熱処理/加工 | 摩耗、吸湿、ノズル詰まり、反り、Z方向/根元。CFを入れれば全方向に強いとは限らない |
| 連続繊維CFR/CFC | 樹脂マトリックス＋連続繊維 | 専用経路設計→樹脂/繊維を配置→除去/仕上げ→荷重試験 | 最低幅/曲率、切断、配置できない層、層間、繊維を入れた実際の荷重経路 |
| 結合材入り金属押出 | 金属粉末＋樹脂/ワックス等 | グリーン品→脱脂→ブラウン品→焼結→熱処理/加工/検査 | 脱脂経路、焼結収縮・垂れ、セッター、脆い中間品、後処理受入 |
| 金属LPBF | 機種向け合金粉末 | 粉末床でレーザー溶融→粉抜き→材料指定の応力除去/切離し→支持除去/加工等 | 熱応力、支持の熱/拘束、下向き面、リコーター、残粉と加工代 |
| 金属EB-PBF | 機種向け合金粉末 | 真空/予熱下で電子ビーム溶融→冷却→粉末ケーキから回収→仕上げ/検査 | 高温/真空条件、半焼結粉末、内部粉抜き、支持と表面の制約 |
| 金属バインダージェット | 金属粉末＋バインダー | 噴射→硬化→粉抜き→脱脂/焼結→必要な仕上げ/検査 | グリーン強度、焼結治具/垂れ、収縮・密度、粉抜きと炉の生産能力 |
| DED/WAAM | ワイヤー/金属粉末＋基板/母材 | レーザー/アークで肉盛り→指定の熱処理→切削/仕上げ/検査 | 溶接的な熱履歴・希釈、角と層間の熱、基板、加工代、異材界面 |

材料とエネルギー源の説明例：[連続繊維](https://markforged.com/materials/continuous-fibers/continuous-carbon-fiber)、[金属押出](https://markforged.com/resources/learn/design-for-additive-manufacturing-metals/metal-additive-manufacturing-introduction/metal-additive-manufacturing-process)、[LPBF機](https://www.eos.info/metal-solutions/metal-printers/eos-m-290)、[EB-PBF機](https://www.colibriumadditive.com/printers/eb-pbf-printers/spectra-l)、[バインダージェット](https://h20195.www2.hp.com/v2/GetDocument.aspx?docname=4AA7-3333ENW)、[粉末DED](https://us.dmgmori.com/products/machines/additive-manufacturing/powder-nozzle)。

## 間違えやすい呼び方

- PA-CFは通常、短繊維入り樹脂の名称。完成品が純カーボンでも連続繊維積層でもない。
- 金属入り・金属色の樹脂は、脱脂/焼結用製品だと確認できなければ樹脂部品として扱う。耐熱や導電率を金属の値で計算しない。
- FX10のカーボン/金属対応は、指定の構成へ切り替えて別工程で作る能力。[日本語の発表資料](https://markforged.com/jp/resources/blog/meet-the-fx10-the-first-industrial-metal-and-composite-3d-printer)を同一部品中の任意のカーボン＋金属同時造形と読まない。材料の現行対応は発売時の記事より現行の表を優先する。
- [Carbon社DLS](https://www.carbon3d.com/carbon-dls-technology)は液体レジンの光造形。材質としての炭素繊維の意味ではない。

## 収縮と完成状態

焼結工程がある方式の拡大補正と、LPBF/DEDの熱変形補正は別に扱う。縮みが最終寸法に対しどう定義されるかを確認し、スライサーが補正している場合は二重に拡大しない。方向別の原寸試験片を同じ炉・配置・処理で測る。

プリンター内に入る寸法、グリーン品の寸法、炉/セッターに入る寸法、最終寸法、加工後の寸法を別の列で管理する。焼結・熱処理・HIP・機械加工は同じ工程名ではない。必要なものと順序は材料/用途へ照合する。
