# 機種・材料・支持材を組み合わせる

各行は記載された製品と構成の範囲。**公式対応は今回の形状で成功したという意味ではない。** 製品改訂とスライサー/機械構成を都度照合する。不明を非対応と断定せず、不明のまま出力条件を確定しない。

## 機械と周辺品

| 組み合わせ例 | 判定・必要な確認 |
| --- | --- |
| S5 + UltiMaker Tough PLA 2.85mm + AA0.4 | 公式に用意された構成の範囲。現在のフィン失敗は接地・全高の安定の問題も残る。新材料が必要だと即断しない |
| S5のAA0.4構成にPA-CF/PET-CF等をそのまま装填 | そのまま採用不可。正確な製品、2.85mm、耐摩耗コア・給材、公式プロファイルを照合。CC等へ替えるだけで全複合材が使えるとは限らない |
| A1 mini + AMS lite + 普通のTPU 95A | 専用AMS対応製品と区別。AMS liteの可否を公式表で確認し、非対応なら許可された外部給材経路を検討 |
| A1 mini + 高温のPA/PC系 | ノズルの最高温度や耐摩耗化だけで対応にしない。機種の推奨、ベッド・庫内条件を満たすか確認 |
| PETG/TPU/PC + 滑面PEI等 | 過剰密着・表面損傷の可能性。プレート製品指定の表面と離型層を選ぶ。ブリム拡大や初層押し込みだけで直さない |
| 405nmレジン + 任意のMSLA/Form 4 | 波長だけでは不明。正確な材料世代・色と機種の対応、層高・液温・剥離・後処理を照合 |

根拠：[UltiMaker Sシリーズ](https://support.ultimaker.com/s/article/1667410778895)、[Tough PLA](https://ultimaker.com/materials/s-series-tough-pla/)、[Bambuの材料・ノズル・送り・プレート表](https://wiki.bambulab.com/en/general/filament-guide-material-table)、[Prusa PETG（日本語）](https://help.prusa3d.com/ja/article/petg_2059)、[Formlabsの第三者機種別検証](https://formlabs.com/materials/formlabs-resin-print-settings)。

## FDMの本体と支持・異材

| 製品と構成 | 公式資料の範囲・実行時の条件 |
| --- | --- |
| S5 + UltiMaker Tough PLA + UltiMaker PVA | 対応する組。Tough PLA側はAA、PVAはBB。両側の径/コア、乾燥、Curaの対になるプロファイルを確認 |
| S5 + UltiMaker Tough PLA + UltiMaker Breakaway | 対応する組。現行公式表はS5のBreakawayにAA0.4とBB0.4を記載。旧来の「BBは常にPVA専用」と決めつけない |
| UltiMaker PVA + UltiMaker PC/PP | 公式では非対応（界面の接着不足）。ABS等の実験扱いの組も正式対応と混ぜない |
| UltiMaker Breakaway + UltiMaker PP | 非対応（接着不足）。PC/TPU95Aは実験扱い。PVAとBreakawayの対応表は同じではない |
| Prusa XLのPLA/PETG支持 | 公式に利用例あり。支持の取り外し用途で、強く接合する構造部の保証ではない。公式の支持・塔・版の条件で小試験 |
| PLA/PETGを荷重がかかる継ぎ目に使用 | 上の支持用途から接合強度を推定しない。界面試験、かみ合わせ/分割等の設計を検討 |
| 普通のTPU + 硬質ポリマー | 送り・共通ベッド/庫内・界面接着が製品依存。不明の組は固定レシピにせず、支持除去/接合を目的別に試す |
| 異材 + 単一ノズル/複数ノズル | 単一ノズルは残留・パージ、複数ノズルは待機時の滴下・位置差を確認。どちらもプライム塔の接地と界面を確認 |

根拠：[UltiMaker PVAの製品別対応](https://support.ultimaker.com/s/article/1667337600656)、[Breakawayの製品別対応](https://support.ultimaker.com/s/article/1667337600384)、[Prusa XLでの複数材料](https://help.prusa3d.com/article/combining-materials-xl_498103)。

## レジンの混合と後処理

| 例 | 判断 |
| --- | --- |
| 水洗い + ABS-likeを任意に50/50で混合 | 両メーカーの製品別承認・比率基準・印刷/後処理条件がなければ不明。単品の露光・洗浄・強度を引き継がない |
| Siraya Tenacious 65Dを添加 | メーカーに混合用途の説明あり。ただし相手製品、比率、条件を確認する。全レジン・全世代の検証ではない |
| Formlabs Color Kit | 専用の基材・顔料・指定レシピと機種世代を使う仕組み。一般のレジン同士の混合とは分ける |
| 水洗いだから水道で洗って排水 | 洗浄槽で回収し、SDSと地域・施設の処理方法に従う。水洗い可能と洗浄水の排水可否を区別する |
| 別材料の洗浄液やタンクを共用 | 顔料/充填材・未硬化液の持ち込みを評価し、メーカー指定の清掃・分離を行う。洗浄・硬化時間を共通化しない |

根拠：[Tenacious 65D](https://siraya.tech/products/tenacious-resin-flexible-resin)、[Color Kit](https://formlabs.com/support/Using-Color-Kit/)、[洗浄と内部の排液](https://formlabs.com/support/Washing-Prints/)、[材料別洗浄・廃液の取り扱い](https://formlabs.com/support/Form-Wash-Time-Settings/)。実機で行う前には当該製品SDSと施設の運用を確認する。

## 多言語で差があったところ

[Prusa PP英語版](https://help.prusa3d.com/article/polypropylene-pp_167126)はPP専用シートを推奨し、[ドイツ語版](https://help.prusa3d.com/de/article/polypropylen-pp_167126)には滑面シート＋PPテープの説明がある。推奨温度の書き方も異なる。訳を独立実験として数えず、現在の製品・シート・公式プロファイルを優先する。

[Bambu中国語の発泡材説明](https://wiki.bambulab.com/zh/knowledge-sharing/studio-settings-for-rc-models)は能動発泡と既発泡を区別する。ここから全製品共通の流量比や飛行安定性の保証を導かない。
