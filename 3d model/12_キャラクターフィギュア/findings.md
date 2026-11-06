# 追加調査で分かったこと

確認日：2026-11-07。機能・版に依存する事実と、それを使う制作上の提案を分ける。以下の比較・確認手順は調査を踏まえた運用案で、全機種/全キャラクターの実験結果ではない。

## 1. 多視点は一貫した入力に絞る

Meshyの[英語](https://help.meshy.ai/en/articles/16102789-meshy-multi-view-best-practices-angles-and-images)と[中国語](https://help.meshy.ai/zh-CN/articles/16102789-meshy-multi-view-best-practices-angles-and-images)の案内は、同じ対象・ポーズ・光の一貫性を重視し、不整合な複数画像より良い単画像を選ぶケースを示す。1枚から生成する背面等は推定なので、独立した正解資料の代わりにはしない。

制作では、正面の顔・頭身、側面の厚み、耳/尻尾の接続などを比較点にし、単色表示でも似姿を確認する。目や模様を凹凸にするか塗装で表すかを選び、テクスチャだけの細部と形状の不足を混同しない。

## 2. AIの印刷解析・修復は対象サイズまで保存する

[Analyze Printability](https://docs.meshy.ai/en/api/analyze-printability)は閉じ方や面の問題に加え、最終サイズ/方式で薄壁を検査できる。[Repair Printability](https://docs.meshy.ai/en/api/repair-printability)はその設定を解析タスクから引き継ぐ場合があり、薄壁を厚くして形を変える。出力のテクスチャは除かれる仕様もある。

解析時のサイズと修復時のサイズ/方式を明示し、修復前後で顔、穴、ダボ、隙間、耳の根元を同じ視点から比較する。成功ステータスは支持・実機・嵌合・表情の保証ではない。Blenderの[メッシュ検査](https://docs.blender.org/manual/en/4.0/addons/mesh/3d_print_toolbox.html)もその範囲で使い、[現行拡張](https://extensions.blender.org/add-ons/print3d-toolbox)と古い同梱版の導入方法を混ぜない。

## 3. 自動分割のダボ寸法とテクスチャ保持に注意する

Meshy [Auto SplitのMarkdown仕様](https://docs.meshy.ai/api/auto-split.md)では、ダボの大きさ/高さは切断面に対する相対値。mm指定のCAD寸法ではない。`by_color`は入力モデルのテクスチャではなく元画像の領域を使う仕様があり、意図した色分割とは一致しないことがある。薄部補強/微小片除去も行われるため、原形と接合を実寸で再確認する。

取得した旧記述の[英語ページ](https://docs.meshy.ai/en/api/auto-split)はテクスチャ非保持と説明する一方、[2026-10-30更新履歴](https://docs.meshy.ai/en/api/changelog)とMarkdown版は`keep_texture: true`を追加している。指定しただけで保持済みと扱わず、対象版/設定と出力を照合する。Markdown仕様ではその指定でもSTL/3MF出力はテクスチャを持たず、GLB等とOBJ+MTL等は別扱い。これは当該サービスの出力仕様で、3MF一般の機能制限ではない。

精密な切断位置・キー形状が必要ならCAD/スライサーで管理する。[Prusa Cut](https://help.prusa3d.com/article/cut-tool_1779)は一体Plug、別体Dowel、Snapを区別する。寸法変更後、洗浄/硬化後、塗装後のどの状態で嵌合させるかを決める。

参照したCut説明はPrusaSlicer 2.9 Legacy系にも紐づく。使用中の版の画面・機能と出力を照合し、新版の操作を同じだと仮定しない。

## 4. テクスチャから多色印刷へ進む経路がある

[BambuのTexture-to-Color](https://wiki.bambulab.com/en/software/bambu-studio/texture-to-color)と[2.7.1の公開資料](https://wiki.bambulab.com/en/software/bambu-studio/release/release-note-2-7-1)では、2.7.1以降にテクスチャ付きOBJ/glTF/GLB/FBXを色塗りへ変換する機能を記載する。モデルは1つずつ読み込み、Draco圧縮glTF/GLBは非対応。macOSでは圧縮FBXの対応にも依存ライブラリ由来の制限がある。非対応入力はテクスチャを維持した非Dracoの対応形式などへ書き出し直し、再読込で形状・色・変換可否を確認する。拡張子を変えるだけでは圧縮方式は変わらない。

色を絞り実フィラメントへ割り当てる工程なので、元画像の色が無制限にそのまま印刷されるわけではない。細い瞳や頬、境界の欠け、暗色から明色へのパージを確認する。[パージの公式説明](https://wiki.bambulab.com/en/software/bambu-studio/reduce-wasting-during-filament-change)も色の遷移方向で必要量が異なるとしている。塗装・色別部品の組立・対応機の多色を、見た目と手間・材料消費で比較する。

## 5. 最小造形値と、扱える細部の強さは別

[Form 4世代の形状表](https://formlabs.com/global/support/Design-specifications-for-3D-models-Form-4-generation)は樹脂・層高等の条件付きの試験値。細い耳/爪は造形できても支持除去・洗浄・持ち運びで折れることがあり、根元、長さ、層方向、材料の靱性と仕上げ工程を含む原寸試片で確認する。

[Lychee吸盤検出](https://docs.mango3d.io/doc/resin-documentation/resin-holes/suction-cup-detector/)のDeleteは模様を消すだけで、空洞を修正しない。[3D穴の書出し](https://docs.mango3d.io/doc/resin-documentation/resin-export/export-3d/)は、参照版では中空モデルの外面と内面の2面を通す穴を想定し、複数面との交差や穴同士の重なりに制限がある。大きな穴プリミティブをBoolean切断の代用にはしない。Detect Holes in Errorで赤い不適合穴を修正し、Export 3Dの排液穴出力を有効にして加工済みSTL/OBJを再読込する。元のSTLをコピーする操作では準備内容は反映されない。版/プランによる機能差も照合する。

スライス生成と3Dモデル出力は別経路なので、3D穴の変換エラーだけでスライスの穴も同じだと決めず、実際の使用経路の出力を確認する。プロジェクトで穴を置いたことと、最終STL/スライスへ穴が反映されたことを分ける。[洗浄手順](https://formlabs.com/support/Washing-Prints/)も内部の流れと排液を確認する。

## 6. 仮組みと塗膜を設計工程へ戻す

[Prusa後処理](https://blog.prusa3d.com/postprocessing-of-3d-prints-step-by-step_29270/)は、仮組みで接着位置と別々に塗れる部分を見極める手順を示す。[タミヤ](https://tamiya.com/japan/scale/technique/87160/index.html)は厚い下地で細部が埋まる点、[Mr.Hobby](https://www.mr-hobby.com/ja/qa)は材質による塗膜密着の違いを説明する。

塗る前にダボを無理なく組めるか、接着面に塗膜を残すか、色別に塗った後でも組めるかを確認する。塗料・下地・接着剤は実際のPLA/光硬化樹脂で試し、プラモデル用PSやレジンキャストへの適合を全3Dプリント材へ移さない。
