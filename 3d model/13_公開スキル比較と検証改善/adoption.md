# 公開手法から採用したこと

2026-11-07に下記コミットの本文と補助コードを再読した。これは静的レビュー。公開作者の説明・コードから読み取れる挙動と、ここでの改善案を区別する。スター数や自動点数から印刷成功率を推定しない。

| 出典 | 読み取れた点 | 今回の採用と変更 |
| --- | --- | --- |
| [ModelRiftのOpenSCAD手順](https://github.com/ModelRift/openscad-skill/blob/b0f0c041cec60af7e7e62f5694e5e05d16e1eed4/SKILL.md) | 実出力を戻した断面、同じ座標でのSTL差分、ねじの原寸試片を扱う | 実出力と修正前後を比較する。開発版の要求やファイル命名を全案件へ強制しない |
| [print-studioの検証工程](https://github.com/KvashaIhor/print-studio/blob/bda70052d8d9494ff5cec1d5b4eee3e3735eba33/skills/print-studio/SKILL.md) | メッシュ・詳細画像・試しスライスを組み合わせる | 検査の対象と未実施項目を残す。Bambuや特定のローカルAI環境を全機種の条件にしない |
| [同・メッシュ判定](https://github.com/KvashaIhor/print-studio/blob/bda70052d8d9494ff5cec1d5b4eee3e3735eba33/skills/print-studio/scripts/check_mesh.py) | 外形と造形範囲を軸長のソート後に比較。重心と底面凸包で安定を判定 | 現在のXYZで範囲を照合する。静的な重心判定は造形途中の質量・支持・ヘッドの力を検証しないと明記 |
| [同・スライス検査](https://github.com/KvashaIhor/print-studio/blob/bda70052d8d9494ff5cec1d5b4eee3e3735eba33/skills/print-studio/scripts/slice_check.py) | G-codeの機能コメントと移動から支持の生成を報告 | 設定ONと実経路を区別する。Eモード、フィラメント径/密度、コメント規約を確認せず一般化しない |
| [therynamoの準備処理](https://github.com/therynamo/3d-print-skill/blob/eafb7e981de161db4ac91cbf70742f386ca90e5b/scripts/prepare.py) | 造形範囲へ自動的に一様縮小する | 嵌合や指定寸法を保ち、縮小の代わりに回転・分割・機種を比較。変更した寸法は再検証 |
| [同・プロファイルと知見の適用](https://github.com/therynamo/3d-print-skill/blob/eafb7e981de161db4ac91cbf70742f386ca90e5b/scripts/slice.py) | プロファイル名はTina 2S固定。機種＋材料で取得した知見の調整値を順次適用 | 表示機種と有効プロファイルを照合。知見は現在の症状・モデル・工程等も照合し、関連しない調整を重ねない |
| [text-to-cadの適性検査](https://github.com/earthtojake/text-to-cad/blob/4099cac3ddc56a5e696138c53fd7bee685e8ad9d/skills/dfam-check/SKILL.md) | 測定と方式別評価を分け、未測定を部分結果として残す | 検査項目ごとの確認状態を使う。数値が出なかった項目を0/合格へ変換しない |
| [同・スライス手順](https://github.com/earthtojake/text-to-cad/blob/4099cac3ddc56a5e696138c53fd7bee685e8ad9d/skills/gcode/SKILL.md) | 継承を解決したプロファイルを使い、生成後の設定を確認 | 設定名・継承後の値・対象ファイルを記録し、実機の構成へ対応させる |

上記の問題は対象コミットでの読み取り結果で、現在の最新版や全経路の不具合を断定するものではない。ライセンスが不明な資料のコード・画像・参照部品は複製していない。自作の寸法補助は独立に実装し、閉じ方・薄壁・支持・強度の検査を装わない。

## 既存スキルとの分担

新しい出力検証は機種や材料を選ぶスキルの代わりではない。FDM、光造形、金属、連続繊維で最終データと確認すべき現象が違う。接地と速度の既存手順を呼び、初層・全高・後処理を別の結果として残す。

固定の壁厚、45度、ブリッジ長、公差、ブリム幅、速度を万能設定として追加しない。追加するのは、実出力を測る経路、検証を省略したときの状態、変更前後の比較、条件を伴う改善知見である。
