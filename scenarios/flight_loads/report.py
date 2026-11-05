"""Plot simulated data and publish a standalone, mobile-readable load report."""
# ruff: noqa: E501 -- keep the self-contained HTML template legible.

import argparse
import base64
import html
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

plt.rcParams.update(
    {
        "font.family": "Meiryo",
        "font.size": 10,
        "figure.facecolor": "#f4f7f8",
        "axes.spines.top": False,
        "axes.spines.right": False,
        "axes.grid": True,
        "grid.alpha": 0.18,
        "axes.axisbelow": True,
    }
)

LABELS = {
    "nominal": "通常",
    "calm": "無風",
    "crosswind": "横風",
    "warm": "加熱後",
    "aero_upper": "空力増",
    "aero_lower": "空力減",
    "low_damping": "減衰小",
    "delayed_canopy": "開傘遅れ",
    "axial_landing_5mm": "軸方向着地 5 mm",
    "axial_landing_15mm": "軸方向着地 15 mm",
    "axial_landing_30mm": "軸方向着地 30 mm",
}
METRICS = {
    "compression_n": ("圧縮", "N"),
    "tension_n": ("引張", "N"),
    "shear_n": ("せん断", "N"),
    "bending_nm": ("曲げ", "N·m"),
    "torsion_nm": ("ねじり", "N·m"),
}


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("results", type=Path)
    parser.add_argument("tunnel", type=Path)
    args = parser.parse_args()
    out, tunnel = args.results, args.tunnel
    summary = read(out / "summary.json")
    design = read(out / "design-loads.json")
    images = []

    def save(fig, name, caption):
        fig.savefig(out / (name + ".png"), dpi=155, bbox_inches="tight")
        plt.close(fig)
        images.append((name, caption))

    surface = np.load(tunnel / "v18-a005/surface-loads.npz")
    xyz, cp = surface["position_m"] * 1000, surface["pressure_coeff"]
    fig = plt.figure(figsize=(11, 8))
    ax = fig.add_axes([0.05, 0.50, 0.80, 0.45], projection="3d")
    keep = np.arange(0, len(xyz), max(1, len(xyz) // 18000))
    dots = ax.scatter(*xyz[keep].T, c=cp[keep], cmap="coolwarm", s=3, linewidths=0)
    ax.set(
        xlabel="先端からの距離 (mm)",
        ylabel="横 (mm)",
        zlabel="高さ (mm)",
        title="数値風洞：18 m/s・迎角5° ／ 壁面隣接セルの平均圧力係数",
    )
    ax.set_box_aspect((2.8, 1, 0.8), zoom=1.12)
    ax.set_xticks([0, 200, 400, 600])
    ax.set_yticks([-180, 0, 180])
    ax.set_zticks([-180, 0, 180])
    ax.set_xlabel("先端からの距離 (mm)", labelpad=12)
    ax.view_init(18, -75)
    fig.colorbar(dots, cax=fig.add_axes([0.88, 0.58, 0.022, 0.30]), label="圧力係数 Cp")
    ax = fig.add_axes([0.08, 0.08, 0.76, 0.35])
    plane = np.load(tunnel / "v18-a005/slice.npz")
    case = read(tunnel / "v18-a005/case.json")
    ny, nx = plane["ux_U"].shape
    d = case["d"]
    dx = 90 / d
    extent = [-270, nx * dx - 270, -ny * dx / 2, ny * dx / 2]
    im = ax.imshow(
        np.ma.masked_where(plane["solid"], plane["ux_U"]),
        origin="lower",
        extent=extent,
        cmap="turbo",
        vmin=-0.2,
        vmax=1.3,
        aspect="equal",
    )
    ax.set(
        xlim=(-80, 850),
        ylim=(-250, 250),
        xlabel="計算領域の x (mm)",
        ylabel="計算領域の y (mm)",
        title="最終時刻の中央速度断面 ／ 機体は流れに対して5°回転",
    )
    fig.colorbar(im, cax=fig.add_axes([0.88, 0.08, 0.022, 0.35]), label="流れ方向速度 / 主流速度")
    save(
        fig,
        "numerical-tunnel",
        "圧力は平均した壁面隣接セル値、速度断面は最終時刻です。固定剛体・平底の理想形状を計算しています。",
    )

    table_config = (
        read(tunnel / "table-config.json") if (tunnel / "table-config.json").exists() else {}
    )
    angles = table_config.get("angles_deg", [0, 5, 15, 45, 90, 135, 180])
    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    for speed in [8, 18, 30]:
        rows = [read(tunnel / f"v{speed:02}-a{angle:03}/case.json")["mean"] for angle in angles]
        for ax, key, label in zip(
            axes.flat,
            ["Cx", "Cy", "Cm_z"],
            ["軸力係数 CA", "横力係数 CN", "乾燥重心まわり Cm"],
            strict=False,
        ):
            ax.plot(angles, [r[key] for r in rows], "o-", label=f"{speed} m/s", ms=4)
            ax.set(xlabel="迎角 (°)", ylabel=label)
    for angle in [0, 5, 90]:
        names = [f"v18-a{angle:03}", f"mesh24-a{angle:03}", f"mesh32-a{angle:03}"]
        axes[1, 1].plot(
            [16, 24, 32],
            [read(tunnel / name / "case.json")["mean"]["Cd"] for name in names],
            "o-",
            label=f"迎角{angle}°",
        )
    axes[1, 1].set(xlabel="胴径あたりの格子数", ylabel="抗力係数 CD", title="格子を変えた比較")
    for ax in axes.flat:
        ax.legend(fontsize=8)
    save(
        fig,
        "aero-database",
        "数値風洞の生の平均係数です。飛行への補間時は対称形状の横方向の平均ノイズを除去し、元の値も保存しています。",
    )

    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    for name in ["nominal", "crosswind", "warm", "aero_upper", "aero_lower"]:
        f = read(out / f"{name}-flight.json")
        t = np.asarray(f["trace"]["time_s"])
        samples = f["load_samples"]
        arrays = [
            np.asarray(f["trace"]["position_m"])[:, 2],
            f["trace"]["q_pa"],
            [np.linalg.norm(s["proper_body_mps2"]) / 9.80665 for s in samples],
            [np.linalg.norm(s["air_velocity_body_mps"]) / 343 for s in samples],
        ]
        for ax, values, label in zip(
            axes.flat, arrays, ["高度 (m)", "動圧 (Pa)", "固有加速度 (g)", "マッハ数"], strict=True
        ):
            ax.plot(t, values, label=LABELS[name], lw=1.3)
            ax.set(xlabel="離床開始からの時刻 (s)", ylabel=label)
    axes[0, 0].legend(fontsize=8)
    save(
        fig,
        "flight-history",
        "数値風洞係数を用いて再計算した軌道です。以前の簡易係数による高度とは入力モデルが異なります。",
    )

    section = np.load(out / "nominal-sections.npz")
    r, t, x = section["resultants"], section["time_s"], section["cuts_m"] * 1000
    # Interpolate only for regular plotting; extrema use original samples.
    regular = np.linspace(t[0], t[-1], 500)
    fields = [r[:, :, 2], np.linalg.norm(r[:, :, :2], axis=2), np.linalg.norm(r[:, :, 3:5], axis=2)]
    fig, axes = plt.subplots(3, 1, figsize=(11, 9), layout="constrained")
    for ax, field, label in zip(
        axes, fields, ["軸力 N（圧縮＋／引張−）", "せん断力 N", "曲げモーメント N·m"], strict=True
    ):
        regular_field = np.array([np.interp(regular, t, row) for row in field.T])
        im = ax.pcolormesh(
            x,
            regular,
            regular_field.T,
            shading="auto",
            cmap="coolwarm" if ax is axes[0] else "viridis",
        )
        ax.set(xlabel="先端からの断面位置 (mm)", ylabel="時刻 (s)")
        fig.colorbar(im, ax=ax, label=label)
    save(
        fig,
        "section-history",
        "通常条件の荷重履歴です。容器区間の大きな引張荷重には内圧の端面力が含まれます。色の補間は表示用で、最大値は元の計算標本から求めています。",
    )

    fig, axes = plt.subplots(2, 2, figsize=(11, 8), layout="constrained")
    for ax, key in zip(
        axes.flat, ["compression_n", "tension_n", "shear_n", "bending_nm"], strict=True
    ):
        values = design["envelopes"][key]
        xx = [r["station_m"] * 1000 for r in values]
        ax.plot(xx, [r["limit"] for r in values], label="条件内の最大値", color="#16766c")
        ax.plot(
            xx,
            [r["design"] for r in values],
            "--",
            label=f"指定倍率 {design['factor']:g}",
            color="#a96323",
        )
        label, unit = METRICS[key]
        ax.set(xlabel="先端からの断面位置 (mm)", ylabel=f"{label} ({unit})")
        ax.legend(fontsize=8)
    save(
        fig,
        "design-envelope",
        "条件ごとの最大値を包絡し、仮定した設計倍率を適用しました。軸方向着地を含みます。異なる成分の最大値を一つの同時荷重と扱いません。",
    )

    quality = summary["tunnel_checks"]
    quality_rows = [
        (f"格子24→32：迎角{angle}°", value, 0.05) for angle, value in quality["grid24_to32"].items()
    ]
    quality_rows += [
        ("領域幅10→14胴径", quality["width10_to14"], 0.05),
        ("計算時間40→80 D/U", quality["duration40_to80"], 0.03),
        ("未使用条件の補間", quality["held_out_interpolation"], 0.1),
    ]
    quality_html = "".join(
        f"<tr><td>{label}</td><td>{100 * value:.2f}%</td><td>{100 * limit:g}%</td><td>{'達成' if value < limit else '未達'}</td></tr>"
        for label, value, limit in quality_rows
    )
    max_rows = "".join(
        f"<tr><th>{METRICS[k][0]}</th><td>{v['limit']:.2f} {METRICS[k][1]}</td><td>{v['design']:.2f} {METRICS[k][1]}</td><td>{html.escape(LABELS.get(v['case'], v['case']))}<br>{1000 * v['station_m']:.0f} mm</td></tr>"
        for k, v in summary["maxima"].items()
    )
    figures = "".join(
        f"<figure><a href='data:image/png;base64,{base64.b64encode((out / (name + '.png')).read_bytes()).decode()}' download='{name}.png'><img loading='lazy' src='data:image/png;base64,{base64.b64encode((out / (name + '.png')).read_bytes()).decode()}' alt='{html.escape(caption)}'></a><figcaption>{html.escape(caption)}</figcaption></figure>"
        for name, caption in images
    )
    residual = max(max(v.get("max_equilibrium_residual", [0])) for v in summary["cases"].values())
    cases_html = "".join(
        f"<tr><th>{LABELS[k]}</th><td>{v['apogee_m']:.2f}</td><td>{v['max_q_pa']:.1f}</td><td>{v['max_mach']:.3f}</td><td>{v['max_acceleration_g']:.1f}</td></tr>"
        for k, v in summary["cases"].items()
        if "apogee_m" in v
    )
    page = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>数値風洞から設計荷重へ | RocketWright</title><meta name="description" content="ペトロケのCFD、空力特性、飛行経路、断面荷重、設計荷重をつないだシミュレーション結果。"><style>
:root{{color-scheme:light;--ink:#193731;--teal:#176b60;--line:#cfded8;--paper:#f4f7f4}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font-family:system-ui,'Meiryo',sans-serif;line-height:1.8}}main{{max-width:1120px;margin:auto;padding:32px 22px 70px}}a{{color:var(--teal)}}nav{{display:flex;gap:20px;flex-wrap:wrap;margin:12px 0 28px}}h1{{font-size:clamp(28px,4vw,48px);line-height:1.35;max-width:900px}}h2{{font-size:clamp(23px,3vw,32px);margin:45px 0 14px}}.eyebrow{{letter-spacing:.13em;font-size:12px;font-weight:700;color:var(--teal)}}.intro{{max-width:800px;font-size:18px}}.notice{{border-left:4px solid #b57732;background:#fff4e4;padding:18px 22px;margin:25px 0}}.pipeline{{display:grid;grid-template-columns:repeat(5,1fr);gap:12px;list-style:none;padding:0}}.pipeline li{{background:#fff;border:1px solid var(--line);border-top:4px solid var(--teal);padding:16px}}.pipeline b{{display:block}}.pipeline span{{display:block;font-size:13px;margin-top:10px}}.table-scroll{{overflow:auto;background:white;border:1px solid var(--line);border-radius:8px}}table{{border-collapse:collapse;width:100%;min-width:560px;font-size:14px}}th,td{{padding:13px;text-align:left;border-bottom:1px solid var(--line)}}th{{font-weight:650}}figure{{margin:25px 0;background:white;border:1px solid var(--line);border-radius:12px;overflow:hidden}}img{{display:block;width:100%;height:auto}}figcaption{{padding:16px 22px;font-size:14px}}details{{padding:16px 20px;background:white;border:1px solid var(--line);margin:12px 0}}summary{{cursor:pointer;font-weight:650}}.small{{font-size:13px;color:#4a625c}}.chips{{display:flex;gap:12px;flex-wrap:wrap}}.chips span{{padding:10px 18px;background:#dfece7;border-radius:5px}}@media(max-width:700px){{main{{padding:20px 14px 50px}}.pipeline{{grid-template-columns:1fr}}.pipeline li{{padding:12px 16px}}.pipeline span{{margin-top:3px}}.intro{{font-size:16px}}figcaption{{padding:12px}}}}
</style></head><body><main><p class="eyebrow">ROCKETWRIGHT / NUMERICAL FLIGHT LOADS</p><nav><a href="index.html">設計ガイド</a><a href="integrity.html">先行する熱・構造解析</a><a href="#loads">設計荷重</a><a href="#quality">精度確認</a></nav><h1>数値風洞から、<br>機体の設計荷重まで。</h1><p class="intro">空気が機体のどこを押すのか。その力が飛行中にどう変わり、各断面へどう伝わるのかを、ひとつの計算につなぎました。</p><div class="chips"><span>CFD 24条件＋10の比較計算</span><span>飛行8条件・着地3条件</span><span>単位 N / N·m</span></div><div class="notice"><strong>計算処理は完了。実機安全性は未確認です。</strong><br>実物の風洞試験を数値風洞に置き換えた結果です。格子などの数値精度に未達項目があり、係数・荷重は条件付きです。材料・接合・実物の強度を合格とする結果ではありません。</div><ol class="pipeline"><li><b>01 数値風洞</b><span>壁面付近の圧力<br>3分力・3モーメント</span></li><li><b>02 空力特性</b><span>速度・迎角で変わる<br>係数と分布荷重</span></li><li><b>03 飛行経路</b><span>動圧・加速度<br>マッハ数・高度</span></li><li><b>04 断面荷重</b><span>軸力・せん断力<br>曲げ・ねじり</span></li><li><b>05 設計荷重</b><span>条件の包絡<br>支配時刻と同時荷重</span></li></ol><h2 id="loads">どこに、どれだけの荷重が出たか</h2><p>64区間の空力を断面へ渡し、内圧・推力・慣性・ガイド・開傘を合成しています。指定倍率 <strong>{design["factor"]:g}</strong> は今回の仮定であり、規格が保証する安全率ではありません。</p><div class="table-scroll"><table><thead><tr><th>成分</th><th>条件内の最大値</th><th>指定倍率後</th><th>支配条件・位置</th></tr></thead><tbody>{max_rows}</tbody></table></div><p class="small">ねじりのゼロは今回の無カント・対称性の仮定によるものです。実機でねじりが起きないという意味ではありません。着地荷重は衝突速度を機軸方向に停止させた感度条件です。</p><h2>計算をたどる</h2>{figures}<h2>飛行条件の比較</h2><div class="table-scroll"><table><thead><tr><th>条件</th><th>最高高度 m</th><th>最大動圧 Pa</th><th>最大Mach</th><th>最大固有加速度 g</th></tr></thead><tbody>{cases_html}</tbody></table></div><h2 id="quality">数値精度を別に確認する</h2><p>表は係数6成分のノルムによる差です。精度不足を、計算が終了したことだけで合格扱いしません。</p><div class="table-scroll"><table><thead><tr><th>比較</th><th>差</th><th>目安</th><th>状態</th></tr></thead><tbody>{quality_html}</tbody></table></div><p>分布荷重と全体荷重の相対残差は最大 <strong>{quality["max_surface_integration_residual"]:.2e}</strong>。飛行と断面荷重の力・モーメントの釣合い残差は最大 <strong>{residual:.2e}</strong>（SI）です。これらは受け渡しと数値整合の検査で、CFDの実物に対する誤差ではありません。</p><details><summary>今回の仮定と、計算していない連成</summary><p>剛体・平底・厚さゼロの4枚フィン、固定密度、部材表に基づく仮の慣性を使っています。速度8〜30 m/sの範囲外では端点の無次元係数を使い、実速度の動圧で荷重を計算します。低速域の係数、方位角による4枚フィンの違い、回転減衰、傘の展開、地面との接触は近似です。</p><p>断面荷重は準静的な回復です。変形する機体と流れの完全連成、乱流による過渡振動、液面動揺、材料・接合の破壊進展は、この計算では解いていません。設計荷重の各成分の最大値は異なる時刻に発生するため、同時に作用する荷重ベクトルも記録しています。</p></details><details><summary>低層・中層・高層のつながり</summary><p>低層で幾何形状・部材質量・圧力分布を扱い、中層で係数・分布荷重・慣性・断面釣合いを計算し、高層で飛行条件と設計荷重を包絡します。精度不足ならCFD格子・領域・平均時間へ戻り、条件が範囲外なら数値風洞の条件を追加します。</p></details><p class="small">図は計算出力から作図しています。参考画像は掲載していません。入力、実装、CFDケースのハッシュと全時刻の荷重は解析出力へ保存しています。手法の参考：<a href="https://www.nas.nasa.gov/SC18/demos/demo9.html">NASAの分布空力データベース</a>。大型機の荷重値は流用していません。</p></main></body></html>"""
    (out / "index.html").write_text(page, encoding="utf-8")
    print(out / "index.html")


if __name__ == "__main__":
    main()
