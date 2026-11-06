# 採用v4の写真調動画・生成時間の確認

対象は保存案件 `0bcc8b763a464e42b031011401bb1269:v4`。1.5 L、搭載60 g、
最低高度15 mの同じ採用入力から、設計説明16秒と飛行12秒を新規に生成する。
写真由来の環境・材料を使った物理ベースCGであり、実写撮影やWanの生成結果ではない。

## 計測条件

- 1920×1080、24 fps、Cycles GPU、32 samples、計672フレーム。
- Windows、NVIDIA GeForce RTX 4090（24 GB）、Blender 5.2.2 LTS。
- 既存のローカルGemma `gemma4:12b` が有限の演出選択肢を選び、
  固定したスクリプトが採用CADと計算軌跡を描画する。課金APIは使用しない。
- 描画フレーム未生成からの1回の計測。固定した素材は既存キャッシュを検証して使用。
  インストール・素材取得・設計/CADの再計算は計測範囲外。
- 総時間は演出案の要求開始から、動画化・全復号検査・保存案件への登録まで。
  資源待ち、Blender起動と描画、MP4化と自動検査を別に記録する。
  完成後の目視確認は生成時間に加算しない。
- 同じPCの他のローカル処理がある通常の環境での実測であり、専有環境のベンチマークや
  他の機材・モデル・設定での所要時間を保証するものではない。

## 初回の実測と完成確認

2026年11月7日05:24:20〜05:52:24（日本時間）の実測。

| 工程 | 時間 |
| --- | ---: |
| ローカルGemmaの演出案 | 6.7秒 |
| 描画資源の待ち | 0.001秒未満 |
| Blender起動・描画 | 27分31.7秒 |
| MP4化と全フレーム検査 | 25.2秒 |
| 登録・入出力照合など残りの処理 | 約0.6秒 |
| **合計** | **28分4.2秒** |

フレーム単位の描画時間の合計は、設計説明15分46.4秒、飛行11分27.5秒。
Blenderの起動等を含む上段の時間とは集計範囲が違う。再利用フレームは0。
[生の計測記録](../assets/product-demo/production-plan/photographic-v4/measurement.json)。

技術検査は合格。設計説明384枚・飛行288枚をすべて復号でき、1080p/24 fps、
長さ16秒/12秒、採用入力と元CAD/製作資料の不変を確認した。
保存シーンの5個のCADオブジェクトは全頂点・面が一致し、印刷姿勢への変換後の
寸法誤差は0 mm。動画の機体位置の読戻しと計算軌跡の補間値の最大差は
約0.000000918 mで、独立した画像追跡ではない。
統合画面で2本とも終端へ到達し、取得したコンソールエラーは0件。

**写実品質の承認は保留**。符号化後の22時刻と原寸画像、再生画面を確認したところ、
飛行映像の約1〜9秒で透明胴体の輪郭が明るい空に溶け込み、ノーズとフィンが
離れているように見える。CAD配置の不一致ではないが、背景・光・カメラの
コントラストを改善し、再描画後に再検査する必要がある。全フレームを連続で
目視したとは扱わない。これを残したまま写実映像の品質まで完了とはしない。

- [設計説明MP4](../assets/product-demo/production-plan/photographic-v4/design-explanation.mp4)
- [飛行MP4](../assets/product-demo/production-plan/photographic-v4/launch-cg.mp4)
- [時刻付き設計一覧](../assets/product-demo/production-plan/photographic-v4/design-explanation-contact.jpg)
- [時刻付き飛行一覧](../assets/product-demo/production-plan/photographic-v4/launch-cg-contact.jpg)
- [技術検査](../assets/product-demo/production-plan/photographic-v4/automated-verification.json)・
  [CAD照合](../assets/product-demo/production-plan/photographic-v4/mesh-verification.json)・
  [目視レビューとファイルハッシュ](../assets/product-demo/production-plan/photographic-v4/visual-review.json)

生の計測・自動検査は目視レビュー前の `visual_review=pending` をそのまま保持する。
目視の実際の結果は、別のレビュー記録に保存している。

## 検証方法

生成元のコミットは `74971ca49896417e878ffe23a6d5ae46e80d01c6`。
[計測スクリプト](../scripts/verify_photographic_project.py)は既存の制作経路を呼び、
入力仕様とCAD/製作資料のSHA256が生成前後で変わらないことを検査する。
フレーム単位のチェックポイントから、再利用数とクリップ別描画時間も集計する。

[シーン監査](../scripts/audit_workbench_scene.py)は保存した `assembly.blend` を読み取り、
ノーズ1個とフィン4枚の全頂点・面を採用STLの再読込と比較する。
印刷用フィンの45度回転と最小座標の平行移動を適用して寸法検査表と照合し、
mm→mの縮尺、90度間隔、ノーズ/フィンの取付位置も検査する。
元のシーンや登録済み動画・検査ファイルを変更しない。

```text
python scripts/verify_photographic_project.py ROOT PROJECT_ID NEW_REPORT.json
blender --background --python-exit-code 1 --python scripts/audit_workbench_scene.py -- V4_DIR REPORT.json
```

## 範囲と限界

CADと計算軌跡への対応、自動的な全復号と目視確認は分けて記録する。
PET胴体の細部・姿勢・撮影環境は未実測の表現。飛行は時間を圧縮した計算結果の再生で、
無音。形状の表示成功から、印刷成功・保持強度・飛行の安全性を判定しない。
P12の精度/安定性の未達と、利用者がスキップしたP13/P14はそのまま保持する。

環境素材はPoly HavenのCC0。固定URLとSHA256は
[素材マニフェスト](../AIvideo/pet-rocket/realism/asset-manifest.json)に記録されている。
コードと生成物の必要な出典・ライセンスを保持する。

検証中にmainは `267e22d` へ進んだ。この結果は固定した生成元に対するもので、
新しいmainを統合した実行ではない。[PR #58](https://github.com/masatoshibukawa/RocketCreater/pull/58)は
`rocketwright/analysis/service.py`・`rocketwright/analysis/worker.py`・
`tests/test_analysis_harness.py` に内容競合があり、取り込みを保留している。

## 胴体の視認性を改善する再制作

初回の空を背景にした構図から、地面を背景にする固定俯瞰のCGカメラへ変更した。
カメラ位置は計算された頂点高度より上で固定し、向きと焦点距離だけを変える。
機体位置・採用STL・取付位置・寸法・質量・計算軌跡には変更を加えない。
透明PETには仮定した薄い青み、粗さ0.06〜0.12、光の吸収を使い、透過は維持する。
材質値と俯瞰位置は表現用で、実測した材料光学特性や撮影条件ではない。
選択した設定では反射調整板は使っていない。

初期・中間・最終の比較描画で胴体の輪郭を確認した。
制作ソース `d8494ac` から1080p/24 fps・32 samples・672枚の全編を再生成中。
前のGemma演出案を使い、課金API・新しいLLM呼出し・新しい形状生成は行わない。
完成後の全復号、CAD照合、目視確認、所要時間の結果は完走後に追記する。

画面の「元の動画を残して再制作」は、既存動画と同じ設計版に別の制作フォルダーを作る。
全検査を通るまで以前の動画を通常表示に残し、成功時に新作を表示して以前のものを
履歴へ移す。旧ファイルのURLとハッシュは変えない。失敗/中断した再制作は
保留フォルダーを使って再試行し、同じ入力・描画コードの検証済みフレームだけを再利用する。

```text
python scripts/verify_photographic_project.py ROOT PROJECT_ID NEW_REPORT.json --regenerate
blender --background --python-exit-code 1 --python scripts/audit_workbench_scene.py -- V4_DIR REPORT.json VIDEO_DIR
```

旧動画保持・再制作失敗・再試行・APIフラグ受渡しを含む関連26試験、Ruff、TypeScript、
Next本番ビルドが成功。実APIでも進行中の重複要求を409で拒否し、同じジョブを保持した。
これらのソフトウェア試験を、完成動画の画質や物理検証の合格とは扱わない。
