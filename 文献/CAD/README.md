# ペットボトル水ロケットのCAD・3Dモデル

4つの設計資料から形状ファイル107点（OpenSCAD 9、STL 58、FreeCAD 2、Alibre部品35・組立3）と、寸法を変更するためのマクロ2点を保存した。以下のリンクはこのPCのファイルを開く。109点それぞれの取得URLとSHA-256は[ファイル目録](ファイル目録.json)にある。[文献総合索引](../README.md)

| 部位・目的 | 開くファイル |
| --- | --- |
| 尾翼の枚数や翼幅を比較する | [細幅3枚](D09-RocketFins/PN1_3_narrow_fins.scad) · [広幅3枚](D09-RocketFins/PN2_3_broad_fins.scad) · [細幅5枚](D09-RocketFins/PN3_5_narrow_fins.scad) |
| ボトル口と尾翼の接続を見る | [PCO-1881ボトル口](D09-RocketFins/pco-1881.scad) · [機体の組立モデル](D09-RocketFins/rocket.scad) · [作者の組立図](D09-RocketFins/docs/imgs/assembly.png) |
| 発射台の解除方式を比較する | [結束バンド式の台座](D21-ESP-Controlled-Rocket/3d-designs/Launch%20Platform%20Base%20Air%20pressure%20Cable%20Tie.stl) · [クイックリリース式の台座](D21-ESP-Controlled-Rocket/3d-designs/Launch%20Platform%20Base%20Air%20pressure%20Quick%20release.stl) |
| 回収装置と搭載部を見る | [ノーズハッチ](D21-ESP-Controlled-Rocket/3d-designs/Nose%20Cone%20Ejection%20Hatch.stl) · [開傘トリガー](D21-ESP-Controlled-Rocket/3d-designs/Parachute%20Mechanical%20Trigger%20Part%201.stl) · [ペイロード胴体](D21-ESP-Controlled-Rocket/3d-designs/Payload%20Body.stl) |
| 実測したボトルに合わせる | [ノーズのFreeCAD文書](D22-FreeCAD/water-rocket-nose-ring.FCStd) · [尾部リングのFreeCAD文書](D22-FreeCAD/water-rocket-tail-ring.FCStd) · [ボトルの測定写真](D22-FreeCAD/bottle-measurements-1.jpeg) |

## D09　RocketFins

Adrian Schlatter のねじ込み式尾翼。OpenSCAD原図9点、作者の説明・組立図、リリース版のSTLを収録した。スライサーで完成形を開くには [1A](D09-RocketFins/releases/1A.stl)、[2B](D09-RocketFins/releases/2B.stl)、[3B](D09-RocketFins/releases/3B.stl) を使う。リリース名は作者の版名。原図の固定版は `57f2c9f`。[作者の原図](https://github.com/adrianschlatter/RocketFins/tree/57f2c9fd475be499aafb2655b12f20a75f135e60) · [BSD-2-Clause](D09-RocketFins/LICENSE)

原図を開く際は、OpenSCADのライブラリ検索パス（`OPENSCADPATH`）に [D09-RocketFins/libraries](D09-RocketFins/libraries/) の絶対パスを加える。このフォルダにはねじ形状用の threadlib（`dce1967`）、scad-utils（`26f8c2c`）、list-comprehension-demos の skin（`dec3fc3`）、thread_profile.scad を保存し、原図からの参照先を照合した。[threadlib](https://github.com/adrianschlatter/threadlib/tree/dce1967dfb40c18a3405861f6ae661369275d3eb) · [scad-utils](https://github.com/openscad/scad-utils/tree/26f8c2cf8124cdafe2fc21f9f9bbf2514e404834) · [skin](https://github.com/openscad/list-comprehension-demos/tree/dec3fc3037f0107e5d9da79cb5b36b3e1ad9ce22) · [thread_profile.scad](https://github.com/MisterHW/IoP-satellite/blob/master/OpenSCAD%20bottle%20threads/thread_profile.scad)

## D21　ESP-Controlled-Rocket

作者 zerneo85 の公開版 `7308214` から[機械部品のSTL 35点](D21-ESP-Controlled-Rocket/3d-designs/)を保存した。尾翼とリング、発射台とトリガー、ノーズ、搭載部、開傘用サーボアーム、レールガイドなどを個別に開ける。対応する部品の組み合わせは作者の説明「3D Parts & Downloads」を参照。[作者の説明](D21-ESP-Controlled-Rocket/README.md) · [固定版の配布元](https://github.com/zerneo85/ESP-Controlled-Rocket/tree/7308214caad006f6e669f08e432c7419ee9cb096/3d-designs) · [GPL-3.0](D21-ESP-Controlled-Rocket/LICENSE)

## D22　0.5 L 水ロケットのFreeCAD文書と生成マクロ

Original project by Julius Grimm. 版 `c047014` のFCStd 2点には、それぞれ単一のメッシュが保存されている。寸法を変えたいときは、[ノーズ用マクロ](D22-FreeCAD/physics-water-rocket-nose-macroFCMacro.FCMacro)または[尾部リング用マクロ](D22-FreeCAD/physics-water-rocket-tail-ring-macro.FCMacro)の先頭のパラメータを参照する。作者は寸法をcmで入力し、内部でmmに換算している。尾部の首長には仮置きと明記された値もある。[測定写真1](D22-FreeCAD/bottle-measurements-1.jpeg) · [測定写真2](D22-FreeCAD/bottle-measurements-2.jpeg)

作者の Educational License は教育・個人利用を対象とし、商用利用には書面での許可を求めている。図面、マクロ、測定写真、ライセンスをローカルに保存した。[配布元](https://github.com/JustThatRandomCoder/physics-water-rocket-project/tree/c047014fdfa9b1004959c10a114613ec0f1979e8) · [利用条件](D22-FreeCAD/LICENSE)

## D23　Water Bottle Rocket Launcher

The Shoulders of Giants, Inc. が2019年の教育番組で設計した発射台。2020年3月の版を丸ごと参照できるよう、Alibreの組立3点と、その参照先となる部品35点を元のディレクトリ構成で保存した。印刷用のSTL 20点、部品表、作者の説明、CC BY-SA 4.0の利用条件も収録。部品形状を変更する場合は AD_PRT、配置を調べる場合は AD_ASM を開く。[全体組立](D23-TSoGiants/CAD/__Assemblies/Full_Assembly.AD_ASM) · [ノズル組立](D23-TSoGiants/CAD/__Assemblies/Nozzle_Assembly.AD_ASM) · [トリガー組立](D23-TSoGiants/CAD/__Assemblies/Trigger_Assembly.AD_ASM) · [部品表](D23-TSoGiants/BOM.csv) · [作者の固定版・利用条件](https://github.com/TSoGiants/Water-Bottle-Rocket-Launcher/tree/b73d27ca0ef081e64c4c870241b8b8f07fae703c)

この一式はローカル保存。GitHub側から各ファイルを取得する場合は、ファイル目録の D23 にある固定URLを使える。全58点を配布元Git blobと照合し、Alibreファイルのコンテナ形式とSTLの三角形数・データ長を確認した。
