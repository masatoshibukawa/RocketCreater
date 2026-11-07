# GA・DEの適応化とNNによる候補の絞り込み

旧GA・SciPy DEを比較用に残し、`ga-adaptive` と `de-adaptive` を追加した。
両方式は従来と同じ12変数、同じ要求・圧力上限・概算目的関数を使う。
探索対象や合格条件を変えず、候補の作り方を比較できる。

- GA：SBX交叉、成功率に応じた変異幅、親子集団からのエリート保持。
- DE：current-to-pbestとrandの混合、置換された個体のアーカイブ、成功したF/CRの反映。
- 共通：材料の離散操作、境界での反射、停滞・多様性低下時の新規候補投入、完全一致候補の回避。
- 昇格：各初期機体の進化探索で実際に計算した最良個体を優先し、その後に要求違反度で補充。

これは小規模な独自実装で、JADEやNSGA-IIの準拠実装ではない。
1世代の実計算回数を集団数に固定し、従来方式との予算を合わせる。
停止要求や不正な非有限目的値は握りつぶさない。

NNは3初期機体ごとに、単位区間の11連続変数と材料のone-hot表現から、保守側高度・
初期静安定余裕・梁たわみ比を予測する64→32のMLP。学習は任意の追加依存
`scripts/requirements-search-ml.txt`、推論はJSON重みとNumPyのみを使う。
候補は既存の熱・推進・軸方向飛行・梁の概算計算でラベル付けし、実機データとは区別する。

データの70%を学習、15%を有効化判断、残り15%を独立評価に事前配分する。
同じ設計ハッシュを分割間で重複させない。正規化は学習部分のみ。
評価用ラベルで学習・方式選択は行わない。未知の初期機体への汎化は未検証。
高度と静安定余裕の検証誤差が平均値予測より良い場合だけNNを有効にする。

NN利用時は3倍の候補を生成し、約30%を予測順位に依存しない探索に残す。
生存選択と最良値には、必ず実際に計算した目的値を使う。NNの予測で合格にはしない。
学習データの計算費用は探索の追加費用として別に報告し、無料の高速化として扱わない。

参照：[SciPy DE](https://docs.scipy.org/doc/scipy/reference/generated/scipy.optimize.differential_evolution.html)、
[pymoo DEのF/CRと変異方式](https://pymoo.org/algorithms/soo/de.html)、
[MLPRegressor](https://scikit-learn.org/stable/modules/generated/sklearn.neural_network.MLPRegressor.html)、
[データ漏洩を防ぐ分割](https://scikit-learn.org/stable/common_pitfalls.html)。
参照実装を実行したという意味ではなく、今回の独自実装・利用ライブラリは上記の通り。

実測した探索比較は別途結果を追記する。これらの候補生成改善は空力精度や実機安全性の証明ではない。
