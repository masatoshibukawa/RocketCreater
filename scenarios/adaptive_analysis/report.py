"""Render actual campaign evidence and an interactive three-shelf/selection guide."""
# ruff: noqa: E501 -- standalone HTML and chart captions.

import argparse
import base64
import html
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from rocketwright.adaptive import Pool  # noqa: E402
from scenarios.bottle_integrity.report import shape  # noqa: E402

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


def read(path):
    return json.loads(Path(path).read_text(encoding="utf-8"))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("campaign", type=Path)
    parser.add_argument("repair", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    out = args.output
    out.mkdir(parents=True, exist_ok=True)
    results, repaired = read(args.campaign / "results.json"), read(args.repair / "results.json")

    def get(key):
        return results[key]["value"]

    geo = repaired["geometry-candidates"]["value"]
    history = read(args.campaign / "history.json") + read(args.repair / "history.json")
    pool = Pool.load().model_dump()
    images = []

    def save(fig, name, caption):
        fig.savefig(out / (name + ".png"), dpi=150, bbox_inches="tight")
        plt.close(fig)
        images.append((name, caption))

    stencil = get("angle-stencil")["cases"]
    grid = get("angle-grid24")["cases"]
    fig, axs = plt.subplots(1, 3, figsize=(12, 3.9), layout="constrained")
    for ax, key, label in zip(
        axs, ("Cx", "Cy", "Cm_z"), ("軸力係数", "横力係数", "ピッチモーメント係数"), strict=True
    ):
        ax.plot(
            [r["angle"] for r in stencil],
            [r["case"]["mean"][key] for r in stencil],
            "o-",
            color="#187c80",
            label="直径16セル",
        )
        ax.plot(
            [r["angle"] for r in grid],
            [r["case"]["mean"][key] for r in grid],
            "s--",
            color="#d58c41",
            label="直径24セル",
        )
        ax.set(xlabel="迎角 (°)", ylabel=label, title=key)
        ax.legend(fontsize=8)
    save(
        fig,
        "aero-errors",
        "同じ24 m/sで迎角を1°刻みに変えた実計算。迎角10°→11°付近のモーメント段差は、補間と形状離散化を見直す判断材料です。",
    )

    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.5), layout="constrained")
    for profile, color, label in (
        ("reference_assumption", "#187c80", "仮定E=2 GPa"),
        ("stiff_assumption", "#d58c41", "仮定E=20 GPa"),
    ):
        rows = [r for r in geo["candidates"] if r["profile"] == profile]
        axs[0].scatter(
            [r["fin_mass_kg"] * 1000 for r in rows],
            [r["deflection_span_ratio"] * 100 for r in rows],
            s=18,
            alpha=0.5,
            c=color,
            label=label,
        )
    front = [r for r in geo["candidates"] if r["id"] in geo["pareto_ids"]]
    axs[0].scatter(
        [r["fin_mass_kg"] * 1000 for r in front],
        [r["deflection_span_ratio"] * 100 for r in front],
        s=55,
        facecolors="none",
        edgecolors="#193b46",
        label="比較対象として残った候補",
    )
    axs[0].axhline(5, ls="--", color="#9c4936", label="変形比の暫定基準 5%")
    axs[0].set(
        xlabel="フィン4枚の質量 (g)",
        ylabel="線形変形 / スパン (%)",
        yscale="log",
        title="形状を含む192候補",
    )
    axs[0].legend(fontsize=8)
    nonlinear = get("fin-confirm")["cases"]
    bars = [r["meshes"][-1]["max_displacement_m"] * 1000 for r in nonlinear]
    axs[1].bar(
        ["従来仮定\n1 mm", "高剛性仮定\n1.5 mm", "従来物性仮定\n3 mm"],
        bars,
        color=["#a24c39", "#187c80", "#d58c41"],
    )
    for i, v in enumerate(bars):
        axs[1].text(i, v + 1, f"{v:.1f} mm", ha="center")
    axs[1].set(
        ylabel="非線形FEMの最大変位 (mm)",
        title="同じ横風荷重・温間条件",
        ylim=(0, max(bars) * 1.18),
    )
    save(
        fig,
        "fin-tradeoffs",
        "全て仮定物性による比較です。線形梁で候補を絞り、非線形FEMで変形を再評価しました。荷重は迎角約15.1°の外挿を含み、材料強度の合格判定には使っていません。",
    )

    fin_dir = next(args.repair.glob("*-repair-fin-check"))
    fin_file = sorted(fin_dir.glob("mesh*/result.json"))[-1]
    fig = plt.figure(figsize=(11, 5.7))
    ax = fig.add_subplot(121, projection="3d")
    shape(ax, read(fin_file), "形状を見直したフィンの変形")
    ax.set_box_aspect((1, 1.5, 0.7))
    aero_dir = next(args.repair.glob("*-repair-aero-probe")) / "d16-a005"
    surface = np.load(aero_dir / "surface-loads.npz")
    xyz = surface["position_m"] * 1000
    ax = fig.add_subplot(122, projection="3d")
    points = ax.scatter(*xyz.T, c=surface["pressure_coeff"], s=2, cmap="coolwarm", linewidths=0)
    ax.set(
        xlabel="機首先端から (mm)",
        ylabel="横 (mm)",
        zlabel="高さ (mm)",
        title="同じ形状の数値風洞・迎角5°",
    )
    ax.set_box_aspect((2.5, 1, 1))
    ax.set_xticks([0, 200, 400, 600])
    ax.set_yticks([-150, 0, 150])
    ax.set_zticks([-150, 0, 150])
    ax.set_xlabel("機首先端から (mm)", labelpad=12)
    ax.set_ylabel("横 (mm)", labelpad=10)
    ax.set_zlabel("高さ (mm)", labelpad=9)
    ax.view_init(20, -72)
    fig.colorbar(points, ax=ax, shrink=0.45, pad=0.22, label="隣接流体セルの平均圧力係数")
    fig.subplots_adjust(left=0.03, right=0.98, wspace=0.22, top=0.91, bottom=0.13)
    save(
        fig,
        "new-geometry",
        "192候補から選んだ120 mmスパン案を追加の非線形FEMとCFDで計算。変位は計算値で、見やすさのため各軸の縮尺を変えています。有限厚さの構造と、ゼロ厚さの空力フィンを使うため、連成の適合性確認が残ります。",
    )

    fig, axs = plt.subplots(1, 2, figsize=(11.5, 4.2), layout="constrained")
    sensitivity = get("aero-sensitivity")
    labels = ["軸力", "横力", "モーメント"]
    axs[0].barh(
        labels, [c["derivative_10pct_m"] * 0.1 for c in sensitivity["components"]], color="#187c80"
    )
    axs[0].set(xlabel="係数+10%に対する局所高度変化 (m)", title="上位要求から誤差を配分")
    for row in get("trajectory-perturbation")["cases"]:
        if row["delta_tilt_deg"] == 2:
            axs[1].plot(
                row["time_s"],
                row["attitude_difference_deg"],
                label=f"仮定減衰係数 {row['damping']}",
            )
    axs[1].set(
        xlabel="発射からの時間 (s)",
        ylabel="基準軌道との機軸角度差 (°)",
        title="初期傾斜+2°の有限時間応答",
    )
    axs[1].legend()
    save(
        fig,
        "accuracy-stability",
        "高度感度では軸力の影響が支配的です。一方、姿勢差は頂点まで増加する条件があり、高度の誤差だけで姿勢の精度要求を緩めない選択ルールにしています。有限条件の軌道比較であり、指数安定性の証明ではありません。",
    )

    figures = "".join(
        f'<figure><img src="data:image/png;base64,{base64.b64encode((out / (name + ".png")).read_bytes()).decode()}" alt="{html.escape(caption)}" loading="lazy"><figcaption>{html.escape(caption)}</figcaption></figure>'
        for name, caption in images
    )
    merged = results | repaired
    data = json.dumps(
        dict(
            pool=pool,
            history=history,
            results={k: dict(execution_status=v["execution_status"]) for k, v in merged.items()},
            sensitivity=sensitivity["l1_sensitivity_m_per_relative_error"],
        ),
        ensure_ascii=False,
    ).replace("</", "<\\/")
    candidate = geo["lightest"]
    checks = repaired["repair-aero-probe"]["value"]["grid16_to24"]
    repair_fin = repaired["repair-fin-check"]["value"]
    new_disp = repair_fin["meshes"][-1]["max_displacement_m"] * 1000
    body = f"""<!doctype html><html lang="ja"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta name="description" content="ペトロケの追加CFD、フィン候補比較と、結果に応じた階層型解析の選択履歴。"><title>候補プールと追加解析 | RocketWright</title><style>
    :root{{--ink:#183943;--muted:#516970;--accent:#096d70;--line:#d5e2e3;--paper:#f3f7f7}}*{{box-sizing:border-box}}body{{margin:0;background:var(--paper);color:var(--ink);font:16px/1.85 Meiryo,sans-serif}}header{{background:#143c43;color:white;padding:18px max(20px,calc((100vw - 1100px)/2))}}header a{{color:white;margin-right:20px}}main{{max-width:1140px;margin:auto;padding:34px 22px 70px}}a{{color:var(--accent)}}h1{{font-size:clamp(27px,4vw,44px);line-height:1.5;margin:12px 0}}h2{{font-size:25px;margin:0 0 16px}}h3{{font-size:19px}}.eyebrow{{font-size:13px;letter-spacing:.13em;color:var(--accent)}}.intro{{max-width:760px}}section{{margin-top:46px;padding-top:25px;border-top:1px solid var(--line)}}.flow{{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:28px 0;padding:0;list-style:none}}.flow li{{padding:18px;border:1px solid var(--line);background:white;border-radius:8px}}.flow strong{{display:block}}.summary{{background:#e5f2f0;border-left:5px solid var(--accent);padding:16px 22px}}.table-wrap{{overflow:auto}}table{{width:100%;border-collapse:collapse;min-width:640px;font-size:14px}}th,td{{text-align:left;vertical-align:top;padding:12px;border-bottom:1px solid var(--line)}}th{{background:#e7efef}}.badge{{display:inline-block;background:#deeeec;padding:1px 8px;border-radius:4px;font-size:12px}}.muted{{color:var(--muted)}}label{{display:block;font-weight:bold;margin:12px 0 5px}}input,select,button{{font:inherit;max-width:100%;padding:10px;border:1px solid #9cb6ba;border-radius:5px;background:white;color:var(--ink);min-height:44px}}input[type=range]{{width:100%;max-width:540px}}select{{width:100%}}summary{{cursor:pointer;padding:13px 0;font-weight:bold}}details{{border-bottom:1px solid var(--line)}}.small{{font-size:13px}}figure{{margin:25px 0;background:white;border:1px solid var(--line);border-radius:8px;overflow:hidden}}figure img{{display:block;width:100%;height:auto}}figcaption{{padding:16px 20px;font-size:14px}}.two{{display:grid;grid-template-columns:1fr 1fr;gap:25px}}.choice{{background:white;padding:18px;border:1px solid var(--line);border-radius:8px;margin-top:16px}}.skip{{position:absolute;left:-10000px}}.skip:focus{{left:10px;top:10px;background:white;color:#123;padding:10px}}:focus-visible{{outline:3px solid #dd932f;outline-offset:3px}}footer{{margin-top:40px;font-size:13px}}code{{word-break:break-word;font-size:13px}}@media(max-width:700px){{main{{padding:24px 16px 50px}}.flow,.two{{grid-template-columns:1fr}}header{{padding:16px}}header nav{{display:flex;flex-wrap:wrap;gap:8px 14px}}header a{{margin:0}}h2{{font-size:22px}}section{{margin-top:30px}}}}
    </style></head><body><a class="skip" href="#main">本文へ移動</a><header><nav aria-label="設計ガイド"><a href="index.html">RocketWright</a><a href="selection.html">候補選択の設計</a><a href="integrity.html">連成解析</a><a href="flight-loads.html">飛行荷重</a></nav></header><main id="main">
    <p class="eyebrow">ADAPTIVE ANALYSIS / 2026.11.06</p><h1>候補プールと追加解析</h1><p class="intro">解析で見つかった精度不足と設計の弱点を、次に選ぶ変数・手法・評価へ戻します。空力の追加21条件、フィン246候補、非線形FEMと飛行計算の結果をまとめました。</p>
    <ol class="flow"><li><small>01 / 上位要求</small><strong>高度・姿勢・許容誤差</strong>何をどの精度で判断するかを定義。</li><li><small>02 / ハーネス</small><strong>使える組を絞る</strong>入力・精度・依存関係・計算資源を照合。</li><li><small>03 / 選択と解析</small><strong>候補IDと理由を記録</strong>登録済みの手法だけを実行。</li><li><small>04 / 結果を戻す</small><strong>次の層・変数へ切替</strong>変更の影響を受ける結果は失効。</li></ol>
    <div class="summary"><strong>今回の設計判断</strong><p>フィンを厚くすると変形は減りますが、質量が増えて高度が下がりました。この結果から低層の形状探索へ戻り、スパン・厚さ・剛性・取付剛性を同時に比較しています。新しい候補の実機設計はまだ確定していません。</p></div>
    <section><h2>どこまで分かったか</h2><div class="table-wrap"><table><thead><tr><th>評価</th><th>結果</th><th>次の判断</th></tr></thead><tbody>
    <tr><td>空力の迎角補間</td><td>独立検証の11°でモーメント誤差44.1%。6成分ノルムでは26.0%。</td><td>平均化時間だけでなく、壁面・形状の離散化を見直す。</td></tr>
    <tr><td>温間フィンの変形</td><td>従来仮定100.3 mm → 高剛性案2.73 mm／厚板案4.42 mm。</td><td>剛性と質量を一緒に比較。従来の3°荷重評価とは荷重条件が異なる。</td></tr>
    <tr><td>質量を更新した高度</td><td>従来21.67 m → 18.73 m／16.67 m。</td><td>厚さだけの変更を採用せず、形状を再探索。</td></tr>
    <tr><td>形状を含む192候補</td><td>{geo["metrics"]["geometry_screen_feasible_count"]}候補が暫定変形・静安定基準を満たし、{len(geo["pareto_ids"])}候補が質量・変形・余裕の比較対象に残る。</td><td>物性は仮定。新形状用のCFDと非線形FEMへ進む。</td></tr>
    <tr><td>有限時間の姿勢応答</td><td>初期傾斜+2°で頂点前の角度差が約5.77°、減衰を小さくすると9.69°。</td><td>高度感度だけでモーメントや姿勢の要求精度を緩めない。</td></tr></tbody></table></div>
    <p class="small muted">従来構造仮定のフィン質量38.64 gと部品表24 gの差を検出しました。材料の仮定を変更した候補は、部品名と費用見積もりも未確定へ戻します。全て条件付きのシミュレーションです。</p></section>
    <section id="catalog"><h2>3つの棚と、その組み合わせ</h2><p>各手法にメイン層・解析カテゴリ・適用フェーズ・必要入力・出力・評価を登録しています。棚の内容と、実際に許可する組み合わせを確認できます。</p><div class="two"><div><label for="shelf">表示する棚</label><select id="shelf"><option value="actions">許可する組み合わせ</option><option value="targets">解析対象</option><option value="methods">解析手法</option><option value="evaluations">評価方法</option><option value="variables">探索変数と変更の影響</option></select></div><div><label for="query">名前・変数で絞り込む</label><input id="query" type="search" placeholder="例：fin / フィン / CFD" style="width:100%"></div></div><p id="count" class="small" aria-live="polite"></p><div id="shelf-content"></div></section>
    <section><h2>実際の選択履歴</h2><p>今回の計算はホスト側の優先度・誤差超過・計算費用による順位で実行しました。LLMを接続する場合も、この時点で許可されたIDと選択理由だけを渡します。</p><label for="decision">解析の選択時点</label><select id="decision"></select><div id="decision-content"></div><p class="small muted">スコアは説明可能な試作ルールです。学習済みの情報獲得量や成功確率ではありません。予算は計画上の費用枠で、各ソルバーの実行時間上限とは別です。</p></section>
    <section><h2>上位の精度を変えると</h2><p>高度に許す数値誤差の半分を空力へ配分し、実際に計算した感度から係数の精度目安を求めます。ここでは初期の5%基準を上限にしています。</p><label for="accuracy">高度の数値誤差予算：<output id="budget-value">1.5 m</output></label><input id="accuracy" type="range" min="0.2" max="3" step="0.1" value="1.5"><p class="summary" id="accuracy-result" aria-live="polite"></p><p class="small muted">これは局所感度による配分例です。空力モデルそのものの誤差の保証ではありません。姿勢・応力・回収には別の評価基準を持ち、精度未達の結果を最終判定へ昇格させません。</p></section>
    <section><h2>追加計算の可視化</h2>{figures}</section>
    <section><h2>形状を戻して選んだ次の候補</h2><p>暫定基準を満たした中で最軽量の案は、スパン{candidate["span_mm"]} mm、根元{candidate["root_mm"]} mm、厚さ{candidate["thickness_mm"]} mm、仮定ヤング率20 GPa、仮定取付剛性5 MN/mです。特定の市販材や積層構成の性能を示す数値ではありません。</p><div class="table-wrap"><table><tr><th>フィン4枚</th><th>乾燥機体質量</th><th>温間FEM変形</th><th>水重心のずれを含む静安定余裕</th></tr><tr><td>{candidate["fin_mass_kg"] * 1000:.1f} g</td><td>{candidate["dry_mass_kg"] * 1000:.1f} g</td><td>{new_disp:.2f} mm</td><td>{candidate["wet_margin_with_water_shift_mm"]:.2f} mm</td></tr></table></div><p>新形状の数値風洞も5条件実行しました。16→24セルの差は、軸力{checks["Cx"] * 100:.1f}%、横力{checks["Cy"] * 100:.1f}%、モーメント{checks["Cm_z"] * 100:.1f}%です。新しい形状の高度は、空力表と荷重の再評価が完了してから判定します。</p></section>
    <section><h2>候補を選べない理由も残す</h2><ul><li>GPUメモリ：今回は8 GiBを上限に予約。40セルの計算は必要容量21.5 GiBのため選択対象外。</li><li>精度と適用範囲：格子差や補間誤差が大きいまま、解析完了を合格へ読み替えない。</li><li>依存関係：フィン形状を変えたら空力、質量、構造、飛行への影響を再評価する。</li><li>未実装手法：境界適合CFD、移動フィン連成、液体スロッシングなどは開発候補として保持し、実行済みにしない。</li><li>実機情報：材料・接合部の許容値が無ければ、計算した応力から実機安全を確定しない。</li></ul><details><summary>解析の適用範囲と出典</summary><p>今回の構造荷重は、既存の8飛行条件から取り出した横風時の同時刻q・迎角を使用しました。迎角約15.1°は低迎角荷重式の宣言範囲15°をわずかに超えるため、外挿を含む需要比較として記録しています。圧力は変形面に追従しますが、流体を再計算する連成ではありません。</p><p>格子差だけを厳密な誤差上限にせず、収束傾向・独立した誤差源・適用範囲を確認する方針は、<a href="https://www.grc.nasa.gov/www/wind/valid/tutorial/spatconv.html">NASAの格子収束ガイド</a>と<a href="https://www.grc.nasa.gov/www/wind/valid/tutorial/verassess.html">計算検証ガイド</a>を参照しています。5%・10%などの判定値は本プロジェクトの暫定値です。</p></details></section><footer>RocketWright / 条件付き設計研究。実機の製作・加圧・飛行承認を示すページではありません。</footer></main>
    <script type="application/json" id="data">{data}</script><script>
    const data=JSON.parse(document.getElementById('data').textContent), pool=data.pool;
    const esc=s=>String(s??'—').replace(/[&<>"']/g,c=>({{'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}}[c]));
    const pair=(k,v)=>'<p><strong>'+esc(k)+'</strong> '+esc(Array.isArray(v)?v.join(' / '):v)+'</p>';
    function renderShelf(){{const shelf=document.getElementById('shelf').value,q=document.getElementById('query').value.toLowerCase();const rows=Object.entries(pool[shelf]).filter(([id,v])=>(id+JSON.stringify(v)).toLowerCase().includes(q));document.getElementById('count').textContent=rows.length+' 件';document.getElementById('shelf-content').innerHTML=rows.map(([id,v])=>{{let title=v.label||id,content='';if(shelf==='actions'){{const m=pool.methods[v.method];title=pool.targets[v.target].label+' → '+m.label;content=pair('評価',pool.evaluations[v.evaluation].label)+pair('前提解析',v.depends)+pair('要求する品質',v.quality_requires)+pair('入力の依存範囲',v.uses)+pair('計算費用の目安',v.cost_s+' s')+pair('状態',data.results[id]?'今回実行済み':m.implementation==='planned'?'開発候補':'今回未実行');}}else if(shelf==='methods'){{content=pair('層 / カテゴリ',v.layer+' / '+v.category)+pair('フェーズ',v.phase)+pair('入力',v.inputs)+pair('出力',v.outputs)+pair('適用範囲',v.scope)+pair('実装',v.implementation==='planned'?'開発候補':'アダプターあり');}}else if(shelf==='targets')content=pair('変数',v.variables);else if(shelf==='variables')content=pair('単位',v.unit)+pair('役割',v.role)+pair('探索範囲（仮定）',v.bounds)+pair('変更の影響',v.invalidates);else content=pair('観測量',v.observables)+pair('判定',v.rule)+pair('根拠区分',v.evidence_level);return '<details><summary>'+esc(title)+'</summary><code>'+esc(id)+'</code>'+content+'</details>';}}).join('');}}
    document.getElementById('shelf').addEventListener('change',renderShelf);document.getElementById('query').addEventListener('input',renderShelf);renderShelf();
    const select=document.getElementById('decision');data.history.forEach((h,i)=>{{const o=document.createElement('option');o.value=i;o.textContent=(i+1)+'. '+pool.methods[pool.actions[h.action].method].label;select.append(o);}});
    const reasons={{adapter_not_available:'この実行環境ではアダプター未登録',missing_capability:'必要なソルバーがない',memory_budget:'メモリ予算を超える',compute_budget:'計算費用の残枠を超える',already_completed:'同じ入力で完了済み',attempt_limit:'試行回数の上限'}};
    function reason(s){{if(s.startsWith('dependency:'))return '前提解析が未完了：'+s.slice(11);if(s.startsWith('missing_input:'))return '入力不足：'+s.slice(14);if(s.startsWith('quality:'))return '品質条件が未成立：'+s.slice(8);return reasons[s]||s;}}
    function decision(){{const h=data.history[Number(select.value)],chosen=pool.actions[h.action];document.getElementById('decision-content').innerHTML='<div class="choice"><span class="badge">実際の選択</span><h3>'+esc(pool.methods[chosen.method].label)+'</h3>'+pair('対象',pool.targets[chosen.target].label)+pair('評価',pool.evaluations[chosen.evaluation].label)+pair('実行時間',h.elapsed_s.toFixed(1)+' s')+'</div><details><summary>この時点で選べた候補</summary>'+Object.entries(h.decision.offered).map(([id,v])=>pair(id,'スコア '+v.score.toFixed(1)+' / '+v.cost_s+' s')).join('')+'</details><details><summary>選べなかった候補と理由</summary>'+Object.entries(h.decision.rejected).map(([id,v])=>pair(id,v.map(reason))).join('')+'</details>';}}select.addEventListener('change',decision);decision();
    function accuracy(){{const v=Number(document.getElementById('accuracy').value),tol=Math.min(.05,.5*v/data.sensitivity);document.getElementById('budget-value').textContent=v.toFixed(1)+' m';document.getElementById('accuracy-result').textContent='空力への配分 '+(.5*v).toFixed(2)+' m → 係数の局所誤差目安 '+(100*tol).toFixed(2)+'% 以下';}}document.getElementById('accuracy').addEventListener('input',accuracy);accuracy();
    </script></body></html>"""
    (out / "index.html").write_text(body, encoding="utf-8")
    print(out / "index.html")


if __name__ == "__main__":
    main()
