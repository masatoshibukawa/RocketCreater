# RocketWright / 水ロケットの出力内容見本

対象版：r00。内容設計用の下書き。部品・寸法・条件・作業手順は未確定で、製作・打ち上げに使える完成設計ではありません。

## 最初に確認すること

1. design/requirements.json で目的と不足している条件を確認する。
2. design/equipment.json と parts/bom.csv で機材・部品の未選定項目を確認する。
3. assembly/instructions.md で手順書の読み方と工程ごとの不足を確認する。
4. verification/technical-status.json で未評価・未実施の項目を確認する。

PDFの組立手順書は標準の出力対象です。この見本ではレイアウト検討用と実機用を区別し、実機用は必要条件がそろうまで未生成として目録に記録します。

## ファイルの役割

| 場所 | 内容 |
| --- | --- |
| manifest.json | ファイル一覧、状態、対象版、バイト数、SHA-256、依存関係 |
| design/ | 要求・機材・構成。値の単位と未確定を保持 |
| parts/bom.csv | 部品ID・版・名前・調達・数量。空欄は未確定 |
| assembly/steps.json | Web・PDF・動画で共有する工程の正データ |
| assembly/instructions.md | 人が読める手順書の文章表示 |
| analysis/results.json | 未実行・未評価を含む解析の状態 |
| provenance/sources.json | 条件と説明の出典。見本ではユーザーの要求を記録 |
| verification/technical-status.json | 幾何・作業・実物の確認状態 |
| history/decisions.md | 決めたこと、保留したこと、変更の理由 |
| scripts/ | 読み取り専用の確認・要約スクリプト |

## スクリプトの実行

必要な環境はPython 3.11以降。追加ライブラリーは不要です。自動では実行しません。

パッケージ直下で実行：

    python scripts/verify_package.py
    python scripts/verify_package.py --json
    python scripts/inspect_design.py

別のフォルダーから確認：

    python /path/to/package/scripts/verify_package.py --root /path/to/package --json

どちらのスクリプトもファイルの書き換え、ネットワーク接続、外部プログラム起動、プリンター操作、解析の再実行を行いません。
verify_package.py の終了コード0は、確認対象のファイルと参照関係が整っている意味です。製作可能性・強度・組立性・飛行性能の合格ではありません。
終了コード1は整合の不一致、2は引数の指定不備です。内容を編集すると目録のハッシュと合わなくなります。確認スクリプトはそれを自動で修復しません。

## 不明な値と未生成のもの

JSONのnullは不明、未入力、未評価を表し、0や無制限には置き換えません。意味はstatusと理由で区別します。
CSVの未確定値は空欄とし、数量の状態を別の列に残します。値がないことを数量0として扱いません。
未生成のCAD・図面・解析CSV・実機用PDF・動画をダミーで格納せず、manifest.jsonに状態と不足理由を残します。
目録のハッシュは破損や差分の検出用です。署名による発行者の証明や、技術的な承認を保証しません。
