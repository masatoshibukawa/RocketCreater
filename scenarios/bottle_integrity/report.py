"""Render actual numerical artifacts as standalone scientific figures and mobile HTML."""
# ruff: noqa: E501 -- HTML/CSS template lines are kept intact.

import argparse
import base64
import html
import json
from collections import Counter
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
from mpl_toolkits.mplot3d.art3d import Poly3DCollection  # noqa: E402

plt.rcParams.update(
    {
        "font.family": "Meiryo",
        "font.size": 10,
        "axes.spines.top": False,
        "axes.spines.right": False,
        "figure.facecolor": "#f5f7fa",
        "axes.facecolor": "#ffffff",
        "axes.grid": True,
        "grid.alpha": 0.2,
    }
)


def shape(ax, result, title, field="displacement"):
    geo = result["geometry"]
    nodes = {int(k): np.array(v) for k, v in geo["nodes"].items()}
    disp = {int(k): np.array(v) for k, v in result["node_displacements_m"].items()}
    faces = []
    owners = []
    for element_id, e in enumerate(geo["elements"]):
        for face in [
            (0, 1, 2, 3),
            (4, 5, 6, 7),
            (0, 1, 5, 4),
            (1, 2, 6, 5),
            (2, 3, 7, 6),
            (3, 0, 4, 7),
        ]:
            faces.append(tuple(e[j] for j in face))
            owners.append(element_id)
    counts = Counter(tuple(sorted(f)) for f in faces)
    outer = [(f, i) for f, i in zip(faces, owners, strict=True) if counts[tuple(sorted(f))] == 1]
    faces = [f for f, _ in outer]
    vertices = [[(nodes[i] + disp[i]) * 1000 for i in f] for f in faces]
    magnitude = np.array([np.mean([np.linalg.norm(disp[i]) * 1000 for i in f]) for f in faces])
    color_label = "変位の大きさ (mm)"
    if field == "stress":
        s = np.asarray(result["integration_stress_pa"])
        xx, yy, zz, xy, xz, yz = s.T
        vm = np.sqrt(
            0.5 * ((xx - yy) ** 2 + (yy - zz) ** 2 + (zz - xx) ** 2) + 3 * (xy**2 + xz**2 + yz**2)
        )
        per_element = vm.reshape(len(geo["elements"]), -1).mean(axis=1) / 1e6
        magnitude = np.array([per_element[i] for _, i in outer])
        color_label = "要素内平均ミーゼス応力 (MPa)"
    norm = matplotlib.colors.Normalize(vmin=0, vmax=max(magnitude.max(), 1e-9))
    poly = Poly3DCollection(
        vertices,
        facecolors=plt.cm.viridis(norm(magnitude)),
        edgecolor=(0.1, 0.2, 0.3, 0.1),
        linewidth=0.15,
    )
    ax.add_collection3d(poly)
    points = np.array([(nodes[i] + disp[i]) * 1000 for i in nodes])
    ax.auto_scale_xyz(points[:, 0], points[:, 1], points[:, 2])
    ax.set_box_aspect(np.maximum(np.ptp(points, axis=0), 5))
    ax.set(xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)", title=title)
    ax.xaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
    ax.yaxis.set_major_locator(matplotlib.ticker.MaxNLocator(3))
    if np.ptp(points[:, 2]) < 10:
        ax.set_zticks([])
        ax.text2D(
            0.03,
            0.86,
            f"Z: {min(points[:, 2]):.1f}–{max(points[:, 2]):.1f} mm",
            transform=ax.transAxes,
            fontsize=9,
        )
    plt.colorbar(
        plt.cm.ScalarMappable(norm=norm, cmap="viridis"),
        ax=ax,
        shrink=0.6,
        pad=0.1,
        label=color_label,
    )


def render(directory):
    directory = Path(directory)
    result_path = directory / "assessment_results.json"
    if not result_path.exists():
        result_path = directory / "results.json"
    data = json.loads(result_path.read_text(encoding="utf-8"))
    source = json.loads((directory / "input.json").read_text(encoding="utf-8"))
    images = []

    def save(fig, name, caption):
        fig.savefig(directory / f"{name}.png", dpi=150, bbox_inches="tight")
        plt.close(fig)
        encoded = base64.b64encode((directory / f"{name}.png").read_bytes()).decode()
        images.append((name, caption, f"data:image/png;base64,{encoded}"))

    f = data["flight"]["nominal"]
    tr = f["trace"]
    fig = plt.figure(figsize=(12, 8), layout="constrained")
    ax = fig.add_subplot(221, projection="3d")
    pos = np.asarray(tr["position_m"])
    ax.plot(*pos.T, color="#177e89", lw=2)
    ax.set(
        xlabel="東方向 (m)",
        ylabel="北方向 (m)",
        zlabel="高度 (m)",
        title="姿勢・回転を含む飛行シナリオ",
    )
    ax = fig.add_subplot(222)
    ax.plot(
        tr["time_s"],
        np.asarray(tr["omega_rad_s"]),
        label=["ロール軸に直交 X", "ロール軸に直交 Y", "ロール"],
    )
    ax.set(xlabel="時間 (s)", ylabel="角速度 (rad/s)", title="角速度の履歴")
    ax.legend(fontsize=8)
    ax = fig.add_subplot(223)
    for name, r in data["propulsion"].items():
        if isinstance(r, dict) and "trace" in r:
            ax.plot(
                r["trace"]["time_s"],
                r["trace"]["thrust_n"],
                label="通常" if name == "nominal" else "加熱条件",
            )
    ax.set(xlabel="時間 (s)", ylabel="推力 (N)", title="水噴出 → 有限時間の空気噴出")
    ax.legend()
    ax = fig.add_subplot(224)
    th = data["thermal"]["sealed"]["trace"]
    ax.plot(
        th["time_s"], th["temperature_c"], label=["気体", "外皮", "支持部", "ペイロード", "フィン"]
    )
    ax.set(xlabel="待機時間 (s)", ylabel="温度 (°C)", title="仮定した日射・熱接触による温度")
    ax.legend(ncol=2, fontsize=8)
    save(
        fig,
        "flight-thermal",
        "飛行係数・慣性・熱物性は仮定値です。高度や落下範囲は実機予測の保証値ではありません。",
    )

    fig, axes = plt.subplots(1, 3, figsize=(13, 4), layout="constrained")
    cases = [
        ("launch", "打上げ", data["contact"]["cases"]["launch"]),
        ("opening", "傘展開", data["contact"]["cases"]["opening"]),
        ("landing", "着地（停止距離5 mm）", data["contact"]["landing"][0]),
    ]
    for ax, (_, name, r) in zip(axes, cases, strict=True):
        t = r["trace"]["time_s"]
        ax.plot(t, r["trace"]["relative_mm"], color="#177e89", label="相対変位")
        ax.axhline(8, color="#bd5531", ls="--")
        ax.axhline(-8, color="#bd5531", ls="--", label="接触開始 ±8 mm")
        ax.set(xlabel="時間 (s)", ylabel="相対変位 (mm)", title=name)
        ax.legend(fontsize=8)
    save(
        fig,
        "payload-contact",
        "ストッパーとの接触後も非線形計算を継続。接触面積と破壊荷重の実測が必要です。",
    )

    structure = data.get("structure", {})
    if "cases" in structure:
        cases = structure["cases"]
        fig = plt.figure(figsize=(13, 5), layout="constrained")
        for j, key in enumerate(["fin-nominal", "fin-warm"]):
            result = cases[key]["meshes"][-1]
            field = result["fem"] | {"geometry": result["geometry"]}
            ax = fig.add_subplot(1, 2, j + 1, projection="3d")
            shape(ax, field, ("通常" if j == 0 else "加熱後") + "のフィン：変形倍率 1")
            ax.view_init(22, -70)
        save(
            fig,
            "fin-deformation",
            "実際の非線形FEMの変位を色で表示。変形による平均ねじれを空力荷重へ戻して反復しています。",
        )
        fig = plt.figure(figsize=(13, 5), layout="constrained")
        for j, key in enumerate(["collar-warm", "body-warm"]):
            ax = fig.add_subplot(1, 2, j + 1, projection="3d")
            shape(
                ax,
                cases[key]["meshes"][-1],
                ("加熱後の搭載部カラー" if j == 0 else "加圧胴体の形状近似") + "：変形倍率 1",
                field="stress",
            )
        save(
            fig,
            "structure-deformation",
            "色は要素内平均ミーゼス応力です。カラーは圧縮側の支持、胴体は形状近似。実ボトルのリブ・底部は未反映です。",
        )

    s = data.get("stability", {})
    if "flutter" in s:
        fig, axes = plt.subplots(1, 2, figsize=(12, 4), layout="constrained")
        for offset in [-0.25, 0, 0.25]:
            rows = np.array([r for r in s["flutter"]["trace"] if r[0] == offset and r[1] == 1.0])
            axes[0].plot(rows[:, 2], rows[:, 3], label=f"力の作用点ずれ {offset:+.2f} c")
        axes[0].axhline(0, color="#bd5531", ls="--")
        axes[0].set(
            xlabel="流速 (m/s)",
            ylabel="最大固有値の実部 (1/s)",
            title="仮定した空力遅れモデルの不安定化感度",
        )
        axes[0].legend(fontsize=8)
        pitch = s["pitch"]
        axes[1].plot(
            pitch["time_s"], [r["spectral_abscissa_per_s"] for r in pitch["local"]], color="#177e89"
        )
        axes[1].axhline(0, color="#bd5531", ls="--")
        axes[1].set(
            xlabel="時間 (s)", ylabel="局所固有値の実部 (1/s)", title="剛体ピッチの局所安定性"
        )
        save(
            fig,
            "stability",
            "フラッターの実測速度ではありません。局所安定性・弾性振動・飛行全体の安定性は別の判定です。",
        )

    labels = {
        "evidence": "実物・材料の根拠",
        "thermal": "温度と圧力",
        "propulsion": "水・空気の噴出",
        "flight": "飛行・姿勢・回転",
        "contact": "ペイロード接触",
        "structure": "変形・応力",
        "stability": "振動・安定性",
        "uncertainty": "条件のばらつき",
        "verdict": "総合判定",
    }
    cards = ""
    descriptions = {
        "evidence": (
            "実物・材料・造形・接合の記録",
            "測定条件、出典、ファイルの照合",
            "実測と仮定を区別し、適用範囲を確認",
        ),
        "thermal": (
            "気体、外皮、支持部、搭載物、フィン",
            "熱回路と密閉時の圧力変化",
            "熱収支、温度範囲、仮定した物性の影響",
        ),
        "propulsion": (
            "水と残留空気の噴出",
            "圧縮性ノズル流れとエネルギー方程式",
            "質量・熱収支、噴出終了、解析解との一致",
        ),
        "flight": (
            "位置、姿勢、角速度、回収荷重",
            "四元数6自由度と有限時間の傘展開",
            "時間刻み、飛行イベント、空力の適用範囲",
        ),
        "contact": (
            "緩衝材、ストッパー、搭載物",
            "非線形ばね・減衰・片側接触",
            "接触力、押込み量、仕事収支、破壊根拠の有無",
        ),
        "structure": (
            "フィン、カラー、胴体、搭載筒",
            "大変形FEM、温度依存材料、空力との反復",
            "格子精度、変形、応力、材料・支持の根拠",
        ),
        "stability": (
            "姿勢の復元と弾性振動",
            "リアプノフ評価、曲げねじりモード、空力遅れ",
            "局所安定性の範囲と不安定化への感度",
        ),
        "uncertainty": (
            "圧力、風、空力、傘展開の違い",
            "条件を層化して変えた飛行計算",
            "仮定した範囲での性能変化・適用外の数",
        ),
        "verdict": (
            "機体全体の根拠と適用範囲",
            "各層の判定を依存関係に沿って集約",
            "未確認や適用外を実機の合格に昇格させない",
        ),
    }
    for key, spec in source["pool"].items():
        result = data[key]
        state = result.get("execution_status", "未実行")
        target, method, evaluation = descriptions[key]
        cards += f'''<article class="pool-card" data-layer="{html.escape(spec["layer"])}">
        <span class="eyebrow">{html.escape(spec["layer"])} / {html.escape(spec["category"])}</span>
        <h3>{labels[key]}</h3><p>{target}</p>
        <dl><dt>解析手法</dt><dd>{method}</dd>
        <dt>評価方法</dt><dd>{evaluation}</dd>
        <dt>依存する結果</dt><dd>{" → ".join(labels[x] for x in spec["depends"]) or "入力データ"}</dd></dl>
        <span class="status">計算処理：{"完了" if state == "completed" else html.escape(state)}</span></article>'''
    rows = ""
    for name, case in structure.get("cases", {}).items():
        r = case["meshes"][-1]
        field = r.get("fem", r)
        change = case["mesh_check"]
        rows += f"""<tr><td>{html.escape(name)}</td><td>{field["nodes"]:,}</td>
        <td>{field["max_displacement_m"] * 1000:.3f}</td><td>{field["max_integration_vm_pa"] / 1e6:.2f}</td>
        <td>{"合格" if change["pass"] else "未収束"}</td></tr>"""
    chart_html = "".join(
        f'<figure id="{n}"><img src="{u}" alt="{html.escape(c)}"><figcaption>{c}</figcaption></figure>'
        for n, c, u in images
    )
    missing = {
        "geometry": "実物の寸法・肉厚分布・接合位置",
        "material": "材料・造形方向・温度別の変形と破壊",
        "mount": "緩衝材の圧縮・減衰・接触面積・搭載物の破壊荷重",
        "joint": "接着・固定・抜けの強度",
        "pressure": "容器・発射部の適用範囲と耐圧に関する適切な根拠",
        "thrust": "推力・圧力・温度の時間履歴",
        "aerodynamics": "独立した空力係数と作用点の検証",
        "inertia": "水量ごとの重心・慣性",
        "thermal": "熱容量・熱伝導・膨張・接触熱抵抗",
        "modes": "組立状態の振動モードと減衰",
        "recovery": "傘の展開・取付部荷重・着地の確認",
        "operations": "発射機構と運用条件の確認",
    }
    evidence_html = "".join(
        f"<li>{missing.get(x, html.escape(x))}</li>" for x in data["verdict"]["missing_evidence"]
    )
    maxforce = max(r["peak_payload_force_n"] for r in data["contact"]["landing"])
    fin_values = []
    for key in ("fin-nominal", "fin-warm"):
        field = structure.get("cases", {}).get(key, {}).get("meshes", [])
        fin_values.append(
            f"{field[-1]['fem']['max_displacement_m'] * 1000:.1f} mm" if field else "未計算"
        )
    local_stable = s.get("pitch", {}).get("all_frozen_points_hurwitz", False)
    pitch_message = (
        "剛体ピッチは調べた時刻ごとには局所安定でした。"
        if local_stable
        else "剛体ピッチの局所安定性には未確認または不安定な条件が残りました。"
    )
    common = s.get("pitch", {}).get("common_quadratic") or {}
    pitch_message += (
        "標本ごとの共通二次形式の条件も満たしましたが、全飛行の証明ではありません。"
        if common.get("sampled_common_certificate")
        else "試した共通リアプノフ関数では全体の安定性を確認できませんでした。"
    )
    page = f"""<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
    <title>ペトロケ 階層解析レポート</title><style>
    :root{{color-scheme:light;font-family:system-ui,"Meiryo",sans-serif;color:#18323a;background:#f5f7fa}}
    *{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1180px;margin:auto;padding:38px 24px 70px}}
    header{{border-bottom:1px solid #cad6dd;padding-bottom:28px}}h1{{font-size:clamp(27px,5vw,48px);line-height:1.25;margin:14px 0}}
    h2{{margin:48px 0 18px;font-size:25px}}h3{{margin:9px 0;font-size:19px}}p,li{{line-height:1.8}}.eyebrow{{font-size:12px;letter-spacing:.08em;color:#526d77}}
    nav{{display:flex;gap:10px;flex-wrap:wrap;margin:22px 0}}a,button{{color:#115f6a}}nav a,button{{border:1px solid #afc3cc;border-radius:24px;padding:9px 15px;text-decoration:none;background:white;font:inherit;font-size:13px;cursor:pointer}}
    .notice{{background:#fff2e9;border-left:4px solid #ba633c;padding:17px 20px;border-radius:4px}}
    .metrics,.pool{{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:16px;margin:24px 0}}
    .metric,.pool-card{{background:#fff;border:1px solid #d8e1e6;border-radius:14px;padding:22px;min-width:0}}
    .metric strong{{font-size:32px;display:block;margin:8px 0;color:#166f7a}}.metric small{{color:#62757c}}
    dl{{font-size:13px;line-height:1.6}}dt{{font-weight:700;margin-top:10px}}dd{{margin:3px 0;overflow-wrap:anywhere}}
    .status{{font-size:12px;background:#eef4f5;padding:5px 8px;border-radius:5px;display:inline-block}}
    figure{{margin:24px 0;background:white;padding:12px;border:1px solid #d8e1e6;border-radius:14px;overflow:hidden}}
    img{{width:100%;height:auto;display:block}}figcaption{{font-size:13px;line-height:1.7;margin:12px;color:#52656f}}
    .table-wrap{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:13px}}th,td{{padding:12px;text-align:left;border-bottom:1px solid #d8e1e6;white-space:nowrap}}
    .evidence{{columns:2;column-gap:35px;padding-left:20px}}.evidence li{{break-inside:avoid;margin-bottom:9px}}button[aria-pressed=true]{{background:#166f7a;color:white}}
    details{{margin:18px 0;padding:16px;border:1px solid #d8e1e6;border-radius:10px}}summary{{cursor:pointer;font-weight:600}}
    footer{{margin-top:40px;font-size:12px;color:#62757c}}@media(max-width:600px){{main{{padding:24px 16px}}.evidence{{columns:1}}.metrics{{grid-template-columns:1fr 1fr;gap:9px}}.metric{{padding:14px}}.metric strong{{font-size:25px}}}}
    </style><main><header><span class="eyebrow">ROCKETWRIGHT / INTEGRITY STUDY</span>
    <h1>ペトロケの変形・熱・飛行を<br>ひとつの解析につなぐ。</h1>
    <p>各層の解析結果から、次の対象・解析手法・評価方法を選ぶ。数値計算の収束と、実物の安全性を分けて確認します。</p>
    <nav><a href="https://rocketwright-bottle-design-guide.taichi-uchida-offici.chatgpt.site">設計ガイド</a><a href="#results">計算結果</a><a href="#pool">候補プール</a><a href="#evidence">残る実測項目</a></nav>
    <div class="notice"><strong>現在の総合判定：実機安全性は未確認</strong><br>
    実測の材料・接合・空力データがありません。以前の三次元CFDも抗力の検証を通過していません。以下は仮定条件で実行した解析結果です。</div></header>
    <div class="metrics"><div class="metric">条件付きの最高高度<strong>{f["apogee_m"]:.1f} m</strong><small>飛行係数・慣性は未検証</small></div>
    <div class="metric">打上げ時の接触力<strong>{data["contact"]["cases"]["launch"]["peak_contact_force_n"]:.1f} N</strong><small>仮定した緩衝材・ストッパー</small></div>
    <div class="metric">着地時の搭載物荷重<strong>{maxforce:.1f} N</strong><small>停止距離の感度解析の最大値</small></div>
    <div class="metric">不足している根拠<strong>{len(data["verdict"]["missing_evidence"])} 分類</strong><small>実物との照合が必要</small></div></div>
    <h2 id="results">連成解析の結果</h2>
    <p>フィンの最大変位は通常 {fin_values[0]}、加熱後 {fin_values[1]}。
    着地時の搭載物荷重は最大 {maxforce:.1f} Nで、緩衝材と搭載物の強度は実測待ちです。</p>
    <p>{pitch_message} 弾性振動も含め、実測に合わせた再評価が必要です。</p>{chart_html}
    <h2>構造解析の格子チェック</h2><p>指定した精度は {source["config"]["observable_relative_tolerance"] * 100:g}%。
    判定対象は最大変位と応力の95パーセンタイルです。表の最大応力は参考値で、局所ピークの強度判定には使いません。</p>
    <div class="table-wrap"><table><thead><tr><th>条件</th><th>節点数</th><th>最大変位 mm</th><th>最大応力 MPa</th><th>格子変化</th></tr></thead><tbody>{rows}</tbody></table></div>
    <h2 id="pool">対象・手法・評価の候補プール</h2><p>上流の入力が揃った解析だけを選べます。必要な精度を満たさなければ格子を細分化し、適用範囲や根拠が不足すれば保留にします。</p>
    <nav id="filters"><button data-filter="all" aria-pressed="true">すべて</button><button data-filter="low" aria-pressed="false">低層</button><button data-filter="middle" aria-pressed="false">中層</button><button data-filter="high" aria-pressed="false">高層</button></nav>
    <div class="pool">{cards}</div><h2 id="evidence">実機を判定するために残るもの</h2>
    <p>解析コードが動いても、実物の性能を証明したことにはなりません。次の実測・製品情報を、対象物・製造条件・温度範囲・出典を付けて入力します。</p><ul class="evidence">{evidence_html}</ul>
    <details><summary>この結果の適用範囲</summary><p>フィンの空力は小迎角の平均ねじれモデル、胴体は形状近似、支持部はばね近似です。
    液面運動・実物のリブや底部・傘布と索の詳細な運動は未解決です。安定性の図は仮定した低次元モデルの診断であり、実機のフラッター速度や全飛行の安定性の証明ではありません。</p></details>
    <footer>実行結果と入力条件は JSON、FEM 入力、ログに保存しています。図は解析結果から作図しました。</footer>
    </main><script>document.querySelectorAll('[data-filter]').forEach(b=>b.onclick=()=>{{document.querySelectorAll('[data-filter]').forEach(x=>x.setAttribute('aria-pressed',x===b));document.querySelectorAll('.pool-card').forEach(c=>c.hidden=b.dataset.filter!=='all'&&!c.dataset.layer.includes(b.dataset.filter));}});</script></html>"""
    (directory / "index.html").write_text(page, encoding="utf-8")
    print(directory / "index.html")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    render(parser.parse_args().directory)
