"""Figures and a phone-readable guide from the executed concrete-candidate artifacts."""
# ruff: noqa: E501

import argparse
import hashlib
import json
import shutil
import sys
from pathlib import Path

import matplotlib
import numpy as np
from matplotlib.figure import Figure
from skimage.measure import marching_cubes

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from scenarios.cfd.flow_preview import body_faces, wake_view  # noqa: E402

matplotlib.use("Agg")
matplotlib.rcParams.update({"font.family": "Meiryo", "font.size": 10})


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def mounted_geometry(g):
    # Retain the exact conical/cylindrical body and replace zero-thickness preview fins.
    groups = body_faces(g, "flat", 0)[:-1]
    start = g["overall"] - g["fin_tail_inset"] - g["fin_root"]
    radius, offset, thickness = g["body_diameter"] / 2, g["fin_root_offset"], g["fin_thickness"]
    shapes = [
        (
            np.array(
                [
                    [start, radius + offset],
                    [start + g["fin_sweep"], radius + offset + g["fin_span"]],
                    [start + g["fin_sweep"] + g["fin_tip"], radius + offset + g["fin_span"]],
                    [start + g["fin_root"], radius + offset],
                ]
            ),
            thickness,
            "#bf8b37",
        ),
        (
            np.array(
                [
                    [start, radius],
                    [start, radius + offset],
                    [start + g["fin_root"], radius + offset],
                    [start + g["fin_root"], radius],
                ]
            ),
            g["fin_shoe_width"],
            "#455965",
        ),
    ]
    for polygon, thick, color in shapes:
        triangles = []
        for a in np.arange(4) * np.pi / 2:
            vertices = []
            for side in (-0.5, 0.5):
                for x, r in polygon:
                    vertices.append(
                        [
                            x,
                            r * np.cos(a) - side * thick * np.sin(a),
                            r * np.sin(a) + side * thick * np.cos(a),
                        ]
                    )
            vertices = np.array(vertices)
            faces = [(0, 1, 2), (0, 2, 3), (4, 6, 5), (4, 7, 6)]
            for j in range(4):
                n = (j + 1) % 4
                faces += [(j, n, n + 4), (j, n + 4, j + 4)]
            triangles.extend(vertices[list(face)] for face in faces)
        groups.append((np.array(triangles), color, 1))
    return groups


def flow_plot(folder, out, packet):
    case_folder = folder / "tunnel/v30-a005"
    case = read(case_folder / "case.json")
    vol, section = np.load(case_folder / "volume.npz"), np.load(case_folder / "slice.npz")
    g = packet["assembly"]["dimensions_mm"]
    dx = g["body_diameter"] / case["d"]
    stride = int(vol["stride"])
    field = vol["ux_U"].copy()
    fluid = ~vol["solid"]
    field[~fluid] = 1
    xyz, faces, _, _ = marching_cubes(field, 0.8, mask=fluid, allow_degenerate=False)
    domain = xyz[:, ::-1] * stride * dx + [
        (0.5 - case["upstream_D"] * case["d"]) * dx,
        (0.5 - case["grid"][1] / 2) * dx,
        (0.5 - case["grid"][2] / 2) * dx,
    ]
    angle = np.deg2rad(case["angle_deg"])
    rotation = np.array(
        [[np.cos(angle), -np.sin(angle), 0], [np.sin(angle), np.cos(angle), 0], [0, 0, 1]]
    )
    cg = np.array([case["cg_mm"], 0, 0])
    body = (domain - cg) @ rotation.T + cg
    keep = (body[faces][:, :, 0].mean(1) > -45) & (
        body[faces][:, :, 0].mean(1) < g["overall"] + 300
    )
    groups = mounted_geometry(g) + [(body[faces[keep]], "#459eb0", 0.28)]
    fig = Figure(figsize=(10, 6.6), dpi=145, layout="constrained", facecolor="#fbfcfb")
    grid = fig.add_gridspec(2, 2, height_ratios=[1.5, 1])
    ax = fig.add_subplot(grid[0, :])
    wake_view(ax, groups)
    ax.set_xlim(-60, 900)
    ax.set_ylim(-230, 230)
    ax.set_title("30 m/s・迎角5° / 青は流れ方向速度が主流の80%になる瞬間の面", loc="left")
    ax = fig.add_subplot(grid[1, 0])
    # The saved section uses domain coordinates; do not label it body-axis distance.
    fields = list(section.files)
    speed_field = section["ux_U"] if "ux_U" in fields else section["velocity"][0]
    inside = section["solid"]
    cmap = matplotlib.colormaps["viridis"].with_extremes(bad="#3f4e56")
    im = ax.imshow(
        np.ma.array(speed_field, mask=inside),
        origin="lower",
        cmap=cmap,
        vmin=-0.2,
        vmax=1.25,
        aspect="equal",
        extent=[-270, case["grid"][0] * dx - 270, -450, 450],
    )
    ax.set(
        xlim=(-50, 900),
        ylim=(-230, 230),
        xlabel="計算領域の x (mm)",
        ylabel="y (mm)",
        title="速度断面（瞬間値）",
    )
    fig.colorbar(im, ax=ax, label="u / U", shrink=0.75)
    ax = fig.add_subplot(grid[1, 1])
    for key, label in [("Cx", "軸力"), ("Cy", "横力"), ("Cm_z", "姿勢モーメント")]:
        cases = [read(folder / f"grid-d{d}-a005/case.json") for d in (16, 24, 28)]
        ax.plot([16, 24, 28], [c["mean"][key] for c in cases], "o-", label=label)
    ax.set(xlabel="胴径あたりの格子数", ylabel="係数", title="18 m/s・5°の格子比較")
    ax.grid(alpha=0.2)
    ax.legend(fontsize=8)
    fig.savefig(out / "flow.png")


def figures(folder, out, packet, summary):
    flow_plot(folder, out, packet)
    fig = Figure(figsize=(10, 4.2), dpi=145, layout="constrained")
    left, right = fig.subplots(1, 2)
    names = {
        "nominal": "標準風",
        "calm": "無風",
        "crosswind": "横風増加",
        "low_damping": "減衰小",
        "tilt_plus2": "傾き+2°",
    }
    for name, label in names.items():
        flight = read(folder / f"assessment/{name}-flight.json")
        trace = flight["trace"]
        time = np.array(trace["time_s"])
        keep = time <= flight["apogee_s"]
        left.plot(time[keep], np.array(trace["position_m"])[keep, 2], label=label)
        right.plot(time[keep], np.array(trace["incidence_deg"])[keep], label=label)
    left.axhline(30, color="#a96232", linestyle="--", label="目標30 m")
    left.set(xlabel="時間 (s)", ylabel="高度 (m)", title="同じ機体の上昇軌道")
    right.set(xlabel="時間 (s)", ylabel="相対風に対する迎角 (°)", title="飛行中の姿勢")
    for ax in (left, right):
        ax.grid(alpha=0.2)
    left.legend(fontsize=8)
    fig.savefig(out / "flight.png")
    fig = Figure(figsize=(10, 4.2), dpi=145, layout="constrained")
    left, right = fig.subplots(1, 2)
    for i, result in enumerate(summary["structure"]):
        levels = np.arange(2, 2 + len(result["meshes"]))
        left.plot(
            levels,
            [r["max_displacement_m"] * 1000 for r in result["meshes"]],
            "o-",
            label=f"荷重事象{i + 1}",
        )
        right.plot(levels, [r["p95_integration_vm_pa"] / 1e6 for r in result["meshes"]], "o-")
    left.axhline(
        packet["assembly"]["dimensions_mm"]["fin_span"] * 0.05,
        color="#a96232",
        linestyle="--",
        label="スパンの5%",
    )
    left.set(xlabel="メッシュ段階", ylabel="最大変位 (mm)", title="フィンと根元ばねの温間FEM")
    right.set(
        xlabel="メッシュ段階",
        ylabel="95百分位の相当応力 (MPa)",
        title="応力需要（破壊判定ではない）",
    )
    left.legend(fontsize=8)
    for ax in (left, right):
        ax.grid(alpha=0.2)
    fig.savefig(out / "structure.png")
    stability = summary["stability"]
    fig = Figure(figsize=(10, 4.2), dpi=145, layout="constrained")
    left, right = fig.subplots(1, 2)
    rows = stability["frozen_checks"]
    left.plot([r["time_s"] for r in rows], [r["stiffness_nm_rad"] for r in rows], color="#166e65")
    left.axhline(0, color="#a96232", linestyle="--")
    left.set(xlabel="時間 (s)", ylabel="復元剛性 (N m/rad)", title="固定条件の復元剛性")
    bound = stability["gronwall"]
    right.plot(bound["time_s"], bound["log10_homogeneous_gain"], color="#166e65")
    right.axhline(0, color="#a96232", linestyle="--")
    right.set(
        xlabel="時間 (s)", ylabel="誤差倍率の上限 log₁₀", title="Grönwall：時変2状態モデル"
    )
    for ax in (left, right):
        ax.grid(alpha=0.2)
    fig.savefig(out / "stability.png")


def html(summary, packet):
    flights, structure, stability = summary["flights"], summary["structure"], summary["stability"]
    deflection = max(r["meshes"][-1]["max_displacement_m"] for r in structure) * 1000
    stress = max(r["meshes"][-1]["p95_integration_vm_pa"] for r in structure) / 1e6
    material = packet["specification"]["fin"]
    perturbation = summary["finite_perturbation"]
    first_modes = [r["first_modes_hz"][0] for r in summary["modes"]["cases"]]
    tr = "".join(
        f"<tr><td>{name}</td><td>{r['apogee_m']:.2f}</td><td>{r['ascent_incidence_deg']:.1f}</td><td>{r['impact_speed_mps']:.2f}</td></tr>"
        for name, r in flights.items()
    )
    return f'''<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1">
<title>材料・取付を決めた機体の再評価 | RocketWright</title><meta name="description" content="ガラスエポキシ製フィンと外付けクランプを持つ水ロケットの空力・飛行・構造・安定性の解析結果。">
<style>
:root{{font-family:system-ui,-apple-system,"Meiryo",sans-serif;color:#213b38;background:#f6f8f4;line-height:1.8}}*{{box-sizing:border-box}}body{{margin:0}}a{{color:#12685e}}header{{background:#fff;border-bottom:1px solid #d9e1d7}}nav,main{{max-width:1100px;margin:auto;padding:22px}}nav{{display:flex;gap:22px;flex-wrap:wrap}}nav a{{text-decoration:none}}h1{{font-size:clamp(28px,5vw,48px);line-height:1.35;margin:12px 0}}h2{{font-size:25px;line-height:1.4;margin:0 0 16px}}h3{{font-size:18px}}p{{max-width:75ch}}section{{margin:42px 0}}.eyebrow{{letter-spacing:.12em;font-size:12px;color:#466b61}}.lead{{font-size:18px}}.badge{{display:inline-block;background:#f5e8cf;color:#79551b;padding:4px 12px;border-radius:20px}}.stats,.cols{{display:grid;grid-template-columns:repeat(3,1fr);gap:18px}}.stats article,.card{{background:#fff;border:1px solid #dbe4d8;border-radius:12px;padding:24px}}.stats strong{{font-size:32px;display:block;line-height:1.5}}.stats small{{display:block;color:#5a6f67}}figure{{margin:22px 0;background:white;border:1px solid #dbe4d8;border-radius:12px;overflow:hidden}}figure img{{display:block;width:100%;height:auto}}figcaption{{padding:15px 22px;font-size:14px;color:#48635a}}.table-scroll{{overflow:auto}}table{{border-collapse:collapse;width:100%;min-width:560px}}th,td{{text-align:left;padding:13px;border-bottom:1px solid #dce3d8}}th{{background:#edf2e9}}.formula{{font-family:ui-monospace,monospace;background:#edf3e9;padding:16px;border-radius:8px;overflow:auto}}label{{display:block;font-weight:600}}select{{min-height:44px;padding:9px;font:inherit;max-width:100%;margin:8px 0}}.note{{padding:18px;border-left:4px solid #ad7839;background:#fff8e9}}details{{padding:18px;background:white;border:1px solid #dbe4d8;border-radius:8px;margin:15px 0}}summary{{cursor:pointer;font-weight:600}}.sources a{{overflow-wrap:anywhere}}footer{{border-top:1px solid #dbe4d8;padding:24px;font-size:13px}}:focus-visible{{outline:3px solid #c57c26;outline-offset:4px}}@media(max-width:700px){{.cols,.stats{{grid-template-columns:1fr}}main,nav{{padding:18px}}.stats article{{padding:18px}}section{{margin:32px 0}}}}
</style></head><body><header><nav><a href="index.html"><b>RocketWright</b></a><a href="adaptive-analysis.html">候補プール</a><a href="#candidate">今回の機体</a><a href="#flight">飛行と強度</a><a href="#theorems">安定性の判定</a></nav></header>
<main><p class="eyebrow">数値試作案 D02-G10-120-C1 · 2026.11.06</p><h1>材料と取付方法を決めて、<br>機体を再評価する</h1><p class="lead">ガラスエポキシ板のフィン、外付けクランプ、金具の重さを同じ機体に反映。三次元空力から姿勢・高度・フィンの変形までつなげました。</p><span class="badge">空力の精度基準は未達・実機安全性は未確定</span>
<section class="stats" aria-label="今回の計算値"><article><small>標準風での予測高度 / 目標30 m</small><strong>{flights["nominal"]["apogee_m"]:.2f} m</strong><small>未検証CFDを使った条件付き予測</small></article><article><small>フィンの温間最大変位</small><strong>{deflection:.2f} mm</strong><small>取付剛性は形状からの推定</small></article><article><small>推定乾燥質量 / ペイロード別</small><strong>{packet["design"]["dry_mass_kg"] * 1000:.1f} g</strong><small>前案152.8 g・ペイロード60 g</small></article></section>
<section id="candidate"><h2>購入する板材と、印刷する取付部</h2><div class="cols"><article class="card"><h3>フィン：購入・切削</h3><p>Iten Resiten G10FR4。板厚1.0 mm、自由スパン120 mm、翼根70 mm、翼端35 mm、後退35 mmを4枚。</p><p>メーカーの密度1,960 kg/m³、弾性率17.24 GPaを採用。元の試験板厚は3.175 mmで、1 mm材の入手・公差・適用物性は要照合です。</p></article><article class="card"><h3>取付部：3Dプリント</h3><p>Prusament PETGのクランプを各フィンに配置。外形70 × 12 × 7 mm、左右の顎は各3 mm。フィンの10.5 mmタブを保持します。</p><p>M2ねじ8組と外部バンド2本を計上。圧力ボトルには穴を開けず、非加圧のスカート側へ取り付ける案です。</p></article><article class="card"><h3>同じ計算に含めたもの</h3><p>取付部の突出12 mm、フィンの厚さ、全追加質量、重心、フィンの慣性を更新しました。クランプ剛性は温間の顎曲げモデルで約{packet["joint_model"]["warm_root_k_n_m"] / 1e6:.3f} MN/mです。</p><p>1.5 L・水25%・9 mmノズル・圧力400 kPaは比較用の解析仮定です。運用条件の認定ではありません。</p></article></div><details><summary>製作・材料条件の詳しい範囲</summary><p>Prusamentは1.75 mm材料に対応したプリンターが必要です。研究室の2.85 mm UltiMaker用設定には流用しません。ボトル・発射台との嵌合、バンドの滑り、ねじ締付け、層間強度、クリープは未照合です。メーカーの代表強度を設計許容値としては扱っていません。</p></details></section>
<section id="aero"><h2>薄いフィンと曲面の位置を、空力計算へ反映</h2><p>壁までの距離を使う補間境界を加えました。球の検証では抗力誤差が細分化に伴い減少しましたが、この機体の24→28分割では、姿勢モーメントが{summary["aero_checks"]["grid24_to28"][2] * 100:.1f}%変わり、5%基準には届いていません。</p><figure><img src="concrete-assets/flow.png" width="1450" height="957" alt="機体まわりの速度低下域、速度断面、格子変更による空力係数の変化"><figcaption>上と左下は30 m/s・5°での瞬間の流れ。右下は18 m/s・5°の時間平均係数。流れの可視化と数値精度の検査を分けて見ます。</figcaption></figure></section>
<section id="flight"><h2>質量増加を含めた高度と姿勢</h2><figure><img src="concrete-assets/flight.png" width="1450" height="609" alt="五つの条件の高度と迎角の時系列"><figcaption>同一形状のCFD表で五つの条件を再計算。風・減衰・初期傾きに対する感度です。</figcaption></figure><div class="table-scroll"><table><thead><tr><th>条件</th><th>高度 m</th><th>最大迎角 ° ※</th><th>着地速度 m/s</th></tr></thead><tbody>{tr}</tbody></table></div><p>nominal＝標準風、calm＝無風、crosswind＝横風増加、low_damping＝減衰小、tilt_plus2＝初期傾き+2°。※最大迎角はレール離脱後・動圧10 Pa超の上昇区間。図は低動圧時も含む全上昇区間です。着地速度は傘の展開モデルにも依存します。</p></section>
<section id="structure"><h2>CFDの力とモーメントをフィンへ渡す</h2><p>各フィンの面外力と根元の二方向モーメントを取り出し、合力と作用点を保持した圧力へ変換しました。荷重が最大の瞬間と、曲げが最大の瞬間をそれぞれ評価しています。</p><figure><img src="concrete-assets/structure.png" width="1450" height="609" alt="構造メッシュを細かくしたときの変位と応力の変化"><figcaption>相当応力の95百分位は最大{stress:.2f} MPa。積層板・継手の破壊許容値が未確定のため、この値だけで強度合格とはしません。変形後に空力を解き直す連成解析は含みません。</figcaption></figure></section>
<section id="theorems"><p class="eyebrow">安定性の初期チェック</p><h2>式の種類と、知りたい結論から定理を選ぶ</h2><p>原点は姿勢角と角速度の「基準からのずれがゼロ」の状態です。飛行中は基準自体が動くため、固定条件の安定性をそのまま飛行全体へ広げません。</p><div class="card"><label for="model-choice">調べるモデル</label><select id="model-choice"><option value="frozen">条件を固定した姿勢のずれ</option><option value="scheduled">飛行中に係数が変わる姿勢のずれ</option><option value="asymptotic">無限時間での収束</option></select><div id="theorem-result" aria-live="polite"></div></div>
<div class="cols"><article class="card"><h3>LaSalle</h3><p>自律系で、不変な閉じた有界領域と V̇ ≤ 0 を確認。V̇ = 0 の中で、動き続けられる最大の不変集合が原点だけかを調べます。</p><div class="formula">I ë + c ė + k e = 0<br>V = (I ė² + k e²) / 2<br>V̇ = −c ė²</div><p>I・k・cが正なら、この固定線形モデルの原点へ収束します。復元力ゼロ、減衰ゼロは同じ判定になりません。</p></article><article class="card"><h3>Grönwall–Bellman</h3><p>「初期のずれが、いつまでに何倍になるか」を上から押さえます。増幅上限が計算できることと、誤差が減衰することは別です。</p><div class="formula">‖e(t)‖ₚ ≤ G(t)‖e(0)‖ₚ<br>＋ 外乱による誤差上限</div><p>今回は区分的に線形補間した2状態モデルに適用。非線形残差・質量放出・開傘時の切替えは別の上限評価が必要です。</p></article><article class="card"><h3>Barbalat</h3><p>W = −V̇ の積分が有限で、Wが一様連続なら W → 0 を示せます。さらに状態を原点へ結びつける条件が必要です。</p><p>有限時間の飛行波形だけでは、無限時間の条件を確認できません。今回のハーネスは適用条件が不足するため選択を拒否しました。</p></article></div>
<figure><img src="concrete-assets/stability.png" width="1450" height="609" alt="復元剛性と、定義した時変姿勢モデルに対する誤差上限"><figcaption>固定条件のLaSalle判定は{stability["analyzed_points"]}点中{stability["frozen_asymptotic_count"]}点で成立。右図は時変2状態モデルの有限時間上限で、実機や全6自由度系の安定性証明ではありません。</figcaption></figure><p class="note">ハーネスは「モデルの型・原点・時間範囲を確認 → 適用できる定理を限定 → 計算 → 結論の対象を記録」の順で進みます。条件不足をLLMの推測で補いません。</p></section>
<section><h2>固定条件の判定と、実際の飛行の差</h2><p>初期傾きを2°変えた非線形飛行では、共通の上昇区間の終わりに姿勢軸の差が{perturbation["final_difference_deg"]:.2f}°へ広がりました。固定モデルでLaSalleの条件を満たしても、この飛行全体で初期差が減るとは言えません。重み付きノルムのGrönwall上限と姿勢角の差は、モデルも評価量も異なります。</p><p>温間のフィン曲げモデルでは、根元剛性を基準の0.25〜4倍にすると一次固有振動数は{min(first_modes):.1f}〜{max(first_modes):.1f} Hzでした。機体全体の曲げ・ねじり、液体の揺れ、空力弾性の安定性はこの値では評価していません。</p></section>
<section><h2>この1案の判断</h2><p>材料と取付方法を明示した数値試作案まで進みました。現条件では高度30 mに未達で、空力精度も未達です。フィンFEMのメッシュ比較は5%以内でしたが、材料・継手の許容値が未確定のため、製作・発射可能な完成設計とは判定していません。</p><p><a href="concrete-assets/results.json" download>今回の数値と判定をダウンロード</a> · <a href="adaptive-analysis.html">候補プールの前回比較</a></p></section>
<section class="sources"><h2>採用した資料</h2><p><a href="{material["source"]}">Iten Resiten G10FR4のメーカー資料</a> · <a href="{packet["specification"]["mount"]["source"]}">Prusament PETGのメーカー資料</a></p><p><a href="https://doi.org/10.1063/1.1399290">補間境界の原論文</a> · <a href="https://www.egr.msu.edu/~khalil/NonlinearSystems/Sample/Lect_10.pdf">Khalil：LaSalleの不変原理</a> · <a href="https://people.math.sc.edu/howard/Notes/gronwall.pdf">Howard：Grönwallの不等式</a> · <a href="https://engineering.purdue.edu/~byao/Research/Supplements/Lyapunov.pdf">Yao：LyapunovとBarbalat</a></p></section>
</main><footer>RocketWright · シミュレーションによる設計比較資料</footer><script>
const text={{frozen:'<h3>LaSalleを選択</h3><p>固定・無外力の姿勢モデルとして、正の復元剛性と減衰、Vの不変な劣位集合、最大不変集合を確認します。結論の対象はこの固定モデルです。</p>',scheduled:'<h3>Grönwallによる有限時間上限を選択</h3><p>時間変化する係数を保持し、同じ座標とノルムで誤差上限を計算します。各時刻の固有値が安定でも、飛行全体の安定性は結論できません。</p>',asymptotic:'<h3>Barbalatの前提を先に確認</h3><p>無限時間の解、Vの下界、V̇の符号、一様連続性、状態を検出する条件が必要です。今回の有限飛行データでは不足するため、収束証明へ進めません。</p>'}};
const choice=document.getElementById('model-choice');function show(){{document.getElementById('theorem-result').innerHTML=text[choice.value]}}choice.addEventListener('change',show);show();
</script></body></html>'''


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--site", type=Path)
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    packet = read(args.folder / "input.json")
    summary = dict(
        candidate=packet["assembly"]["key"],
        design=packet["design"],
        flights=read(args.folder / "assessment/flights.json"),
        structure=read(args.folder / "assessment/structure.json"),
        stability=read(args.folder / "assessment/stability-theorems.json"),
        aero_checks=read(args.folder / "assessment/aero-checks.json"),
        status=read(args.folder / "assessment/status.json"),
        modes=read(args.folder / "assessment/modal-screen.json"),
        finite_perturbation=read(args.folder / "assessment/finite-perturbation.json"),
        source_hashes={
            str(p.relative_to(args.folder)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in [args.folder / "input.json", *args.folder.glob("tunnel/*/case.json")]
        },
    )
    (args.output / "results.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    figures(args.folder, args.output, packet, summary)
    (args.output / "concrete-design.html").write_text(html(summary, packet), encoding="utf-8")
    if args.site:
        assets = args.site / "concrete-assets"
        assets.mkdir(exist_ok=True)
        for path in args.output.glob("*.png"):
            shutil.copy2(path, assets / path.name)
        shutil.copy2(args.output / "results.json", assets / "results.json")
        shutil.copy2(args.output / "concrete-design.html", args.site / "concrete-design.html")


if __name__ == "__main__":
    main()
