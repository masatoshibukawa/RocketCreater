"""Render a portable Japanese HTML report from the actually computed MATLAB outputs."""
# ruff: noqa: E501 -- Keep the embedded HTML template readable.

from __future__ import annotations

import argparse
import base64
import html
import json
from pathlib import Path


def number(value: float | None, digits: int = 2) -> str:
    return "対象外" if value is None else f"{value:.{digits}f}"


def report(folder: Path) -> Path:
    status = json.loads((folder / "run-status.json").read_text(encoding="utf-8"))
    if status["state"] != "complete":
        raise ValueError("The current MATLAB run is incomplete; do not display stale results.")
    r = json.loads((folder / "results.json").read_text(encoding="utf-8"))
    source = json.loads((folder / "input.json").read_text(encoding="utf-8"))
    thermal, fin, payload, body, collar = (
        r[k] for k in ("thermal", "fin", "payload", "body", "collar")
    )
    hot = thermal["sun"][-1]
    fin_names = {
        "bonded": "一体の板",
        "two_slipping_plies": "２枚の板が滑る",
        "warm_bonded": "温度で剛性低下",
        "stiffer_root": "取付剛性を10倍",
    }
    types = {"launch": "発射", "landing": "着地", "opening_sensitivity": "開傘の感度"}

    def picture(name: str, alt: str) -> str:
        data = base64.b64encode((folder / name).read_bytes()).decode("ascii")
        return f'<figure><img src="data:image/png;base64,{data}" alt="{html.escape(alt)}"></figure>'

    def table(headings: list[str], rows: list[list[str]]) -> str:
        head = "".join(f"<th>{html.escape(x)}</th>" for x in headings)
        items = "".join(
            "<tr>" + "".join(f"<td>{html.escape(x)}</td>" for x in row) + "</tr>" for row in rows
        )
        return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{items}</tbody></table></div>'

    fin_rows = []
    for a in fin["cases"]:
        tip = a["tip_deflection_m"]
        decision = "局所姿勢解析へ" if a["applicable"] else "微小変形の範囲外"
        if not a["static_equilibrium_exists"]:
            decision = "仮定モデルでねじり発散"
        fin_rows.append(
            [
                fin_names[a["case_name"]],
                number(a["dynamic_pressure_pa"], 0),
                number(a["offset_chord_fraction"]),
                number(None if tip is None else tip * 1000),
                number(a["root_bending_stress_MPa"]),
                decision,
            ]
        )
    payload_rows = [
        [
            types[a["kind"]],
            number(a["duration_s"] * 1000, 1),
            number(a["peak_pad_travel_mm"]),
            "線形計算内" if a["linear_response_applicable"] else "底付き解析が必要",
        ]
        for a in payload["cases"]
    ]
    body_rows = [
        [number(t * 1000), number(h, 1), number(ax, 1)]
        for t, h, ax in zip(
            body["wall"]["thickness_m"],
            body["wall"]["hoop_MPa"],
            body["wall"]["axial_MPa"],
            strict=True,
        )
    ]
    meshes = [
        [
            number(a["hmax_m"] * 1000, 2),
            str(a["nodes"]),
            number(a["max_displacement_mm"], 4),
            number(a["combined_vm_away_MPa"], 3),
            number(a["force_balance_relative"] * 100, 2),
        ]
        for a in collar["mesh"]
    ]
    cooling = [
        [
            number(a["polytropic_exponent"], 1),
            number(a["water_end_s"], 3),
            number(a["gas_end_C"], 1),
            number(a["wall_inner_end_C"], 2),
        ]
        for a in thermal["cooling"]
    ]
    pitch_rows = [
        [
            fin_names[a["case_name"]],
            number(a["dynamic_pressure_pa"], 0),
            number(a["pitch"]["dry_local_decay_per_s"], 3),
            number(a["pitch"]["wet_static_margin_m"] * 1000),
        ]
        for a in fin["cases"]
        if a["pitch"]
    ]
    method_rows = [
        [
            "低層",
            "板・接着・リング・胴体",
            "剛性、厚さ、熱物性、強度",
            "今回すべて仮定。強度の合否は保留",
        ],
        [
            "中層",
            "フィン",
            "梁＋ねじり、空力の作用点を比較",
            "変位・回転・発散の判定で上位利用を制限",
        ],
        [
            "中層",
            "搭載部・胴体",
            "２自由度応答、膜応力、３次元FEM",
            "可動域、接触、荷重、メッシュ収束",
        ],
        ["中層", "温度場", "壁の有限体積法、搭載室の熱回路", "温度を剛性と熱膨張に渡す"],
        [
            "高層",
            "局所ピッチ・全飛行",
            "有効なケースだけ線形化＋Lyapunov",
            "局所減衰は条件付き。全飛行は未判定",
        ],
    ]
    valid = sum(a["applicable"] for a in fin["cases"])
    stops = sum(not a["linear_response_applicable"] for a in payload["cases"])
    document = f"""<!doctype html><html lang="ja"><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>ペットボトルロケット｜熱・構造・姿勢の連成解析</title>
<style>
:root{{font-family:system-ui,"Meiryo",sans-serif;color:#172d38;background:#f4f6f5;line-height:1.8}}
*{{box-sizing:border-box}}body{{margin:0}}main{{max-width:1120px;margin:auto;padding:36px 24px 80px}}
h1{{font-size:clamp(28px,4vw,44px);line-height:1.35;margin:12px 0}}h2{{margin:0 0 12px;line-height:1.5}}
h3{{font-size:18px}}p{{max-width:84ch}}small,.muted{{color:#52656d}}a{{color:#056579}}
nav{{display:flex;flex-wrap:wrap;gap:12px;margin:28px 0}}nav a{{padding:6px 12px;border:1px solid #c8d6d7;border-radius:30px;text-decoration:none}}
section{{background:white;padding:28px;border-radius:16px;margin:20px 0;scroll-margin-top:16px}}
.badge{{display:inline-block;background:#f7e2cf;color:#813d16;padding:4px 12px;border-radius:6px;font-weight:650}}
.cards{{display:grid;grid-template-columns:repeat(3,1fr);gap:14px;margin:24px 0}}.card{{padding:20px;background:#163d4a;color:white;border-radius:12px}}
.card b{{display:block;font-size:30px;line-height:1.5}}.card small{{color:#d1e2e6}}.note{{border-left:4px solid #b66a30;padding:12px 18px;background:#fff4e8}}
figure{{margin:20px 0}}img{{display:block;width:100%;height:auto}}.scroll{{overflow-x:auto}}table{{border-collapse:collapse;width:100%;font-size:14px}}
th,td{{text-align:left;padding:12px;border-bottom:1px solid #dbe4e4;vertical-align:top}}th{{background:#eaf0f0;white-space:nowrap}}
details{{border-top:1px solid #dbe4e4;padding-top:12px}}summary{{cursor:pointer;font-weight:600}}code{{word-break:break-all}}li{{margin:8px 0}}
@media(max-width:640px){{main{{padding:22px 12px 40px}}section{{padding:18px 14px}}.cards{{grid-template-columns:1fr}}.card b{{font-size:26px}}}}
</style><main><small>実計算レポート · MATLAB R2025b · D02 / carton_wide</small>
<h1>熱と荷重が、<br>変形と姿勢へどう伝わるか。</h1>
<span class="badge">条件付き解析・実機の安全性は未確認</span>
<p>既存の試作機から荷重を取り出し、フィン・搭載部・胴体・保持リングを解析しました。
材料と接合部の物性は未測定です。適用範囲を超えた解析は、上位層の合格根拠に使いません。</p>
<div class="cards"><div class="card"><small>局所姿勢解析に進めたフィン条件</small><b>{valid} / {len(fin["cases"])}</b><small>最大動圧での判定はすべて保留</small></div>
<div class="card"><small>搭載部の仮の可動域を超えた条件</small><b>{stops} / {len(payload["cases"])}</b><small>底付き・接触モデルが必要</small></div>
<div class="card"><small>日なたで10分後の露出フィン</small><b>{thermal["hot_fin_C"]:.1f} °C</b><small>日射・吸収率・熱伝達率の仮定に依存</small></div></div>
<nav><a href="#flow">階層のつながり</a><a href="#fin">フィンと姿勢</a><a href="#payload">搭載部</a><a href="#body">胴体</a><a href="#thermal">熱</a><a href="#fem">3D FEM</a></nav>
<section id="flow"><h2>下位の結果と限界を、上位へ渡す</h2>
<p><strong>温度・物性 → 荷重と変形 → 空力の変化 → 局所姿勢</strong>を計算しました。
同時に、<strong>飛行荷重 → 搭載物の変位 → 接触の有無</strong>を調べます。
接触や大変形が必要になったら、その地点で線形モデルによる合格判定を止めます。</p>
{table(["層", "解析対象", "手法・入力", "評価と判定"], method_rows)}
<p class="note">今回のハーネスは再現用の解析スクリプト内で動きます。既存のWebアプリの探索器へはまだ接続していません。</p></section>
<section id="fin"><h2>フィンの変形を、姿勢評価の前提にする</h2>
<p>迎角3°、総厚1 mm、弾性率2 GPaを仮定。板の接着状態、取付ばね、温度による剛性低下、
空力作用点とねじり軸の距離を変えました。最大動圧は既存の飛行モデルから {source["max_dynamic_pressure_pa"]:.1f} Pa です。</p>
{picture("fin-coupling.png", "フィンの曲げとねじりを比較した実計算図")}
<p>低動圧の有効なケースでは、変形を考慮した空力勾配から局所ピッチの減衰を計算できました。
固定した流れ・乾燥質量・仮の減衰比に対する結果です。全飛行の安定性やフラッターを証明するものではありません。</p>
{table(["条件", "動圧 Pa", "局所減衰率 /s", "湿潤重心との静余裕 mm"], pitch_rows)}
<details><summary>全24条件と適用範囲</summary><p>「範囲外」の変位・応力は線形外挿の診断値です。発散後の有限変位は表示しません。</p>
{table(["条件", "動圧 Pa", "偏心 / 弦長", "先端変位 mm", "根元曲げ MPa", "判定"], fin_rows)}</details></section>
<section id="payload"><h2>搭載部は、自由振動と衝撃を分けて評価</h2>
<p>60 gの搭載物と20 gの支持部を２自由度で計算。壁ばね2500 N/m、パッド600 N/m、減衰比6%、可動域8 mmを仮定しました。
発射時の空気噴出時間、着地停止距離、開傘時間を変えて応答を比較しています。</p>
{picture("payload.png", "発射と着地の搭載部変位と胴体荷重。適用範囲外は破線")}
<p class="note">発射・着地の全ケースで可動域を超えました。表の最大変位は、接触を無視した線形モデルの要求ストロークです。
実際にその距離まで動くという予測ではありません。卵の破損、底付き後の加速度、ふたの抜け、接着剥離は未判定です。</p>
{table(["荷重ケース", "仮のパルス時間 ms", "線形モデルの要求変位 mm", "判定"], payload_rows)}</section>
<section id="body"><h2>胴体の内圧と、非加圧部の荷重</h2>
<p>直径90 mm、既存案のゲージ圧400 kPaで直円筒の膜応力を計算。肉厚を変えるだけで周方向応力は大きく変わります。
この圧力を実物に使用できるという意味ではありません。</p>{table(["仮の肉厚 mm", "周方向 MPa", "軸方向 MPa"], body_rows)}
{picture("body.png", "胴体の肉厚感度と非加圧スリーブの公称応力")}
<p>肩・底・口部の応力集中、実際の肉厚分布、傷、温度依存強度、クリープは未解析。
非加圧スリーブでは軸力と偏心曲げ、接着面の平均せん断を別に計算しました。許容値がないため安全率は算出していません。</p></section>
<section id="thermal"><h2>気体・外装・保持部・搭載物の温度を分ける</h2>
{picture("thermal.png", "水噴射時の冷却と日射による部位別温度上昇")}
{table(["膨張指数", "水噴射終了 s", "気体温度 °C", "内壁温度 °C"], cooling)}
<p>気体が急に冷えても、短い噴射時間では壁全体が同じ温度まで冷えるわけではありません。
気体から壁への一方向熱伝達モデルで、湿度・凝縮・液体側の熱伝達・空気だけの噴出は未解決です。</p>
<p>別の未加圧待機ケースでは、気温35°C、日射800 W/m²、吸収率0.8、初期25°Cとして、10分後の外装は
{hot["skin_C"][-1]:.1f}°C、保持リングは{thermal["hot_mount_C"]:.1f}°C、搭載物は{hot["payload_C"][-1]:.1f}°C。
この温度をフィンの仮の剛性低下則と保持リングの熱膨張へ渡しました。</p></section>
<section id="fem"><h2>保持リングを三次元FEMで確認</h2>
<p>内径63 mm・外径82 mm・厚さ2.4 mmの中実リングに、外周完全固定と上面の一様荷重
{collar["load_n"]:.1f} Nを仮定。荷重は搭載質量×胴体の最大入力加速度で設定した感度ケースであり、接触力の上限ではありません。
温度{collar["temperature_C"]:.1f}°Cを与え、機械荷重・熱荷重・両者を計算しました。</p>
{picture("collar-fem.png", "保持リングの三次元応力と変位。変形倍率100倍")}
{table(["最大要素 mm", "節点数", "最大変位 mm", "固定端付近を除く相当応力 MPa", "反力誤差 %"], meshes)}
<p>表の反力誤差は、有限要素に積分した荷重に対する節点反力の誤差です。
解析式の円環面積から設定した荷重との差は {collar["mesh"][-1]["load_integration_error_relative"] * 100:.2f}% です。
固定端の局所ピークと、境界の応力から再積分した反力は未収束です。実物の接触形状で見直す必要があります。</p>
<p>温度と最大荷重の組合せは仮の包絡ケースです。実際の同時発生は確認していません。
造形方向・充填率・接触面・取付部の柔らかさ・剥離を含まないため、実物の安全性は未確認です。</p></section>
<section><h2>数値の確認と、次に必要な解析</h2>
<p>熱の12→24分割、フィンの80→160分割、搭載部の時間刻み半減、保持リングのメッシュ細分化を確認。
静止熱平衡、梁の閉形式解、膜応力の力の釣り合い、FEMの反力と重ね合わせも確認しました。</p>
<ol><li>実物の材料・厚さ・取付剛性・温度依存性を同定し、低層の仮定を置き換える。</li>
<li>フィンの大変形・ねじりと取付部を、非線形の板／シェルと空力で解析する。</li>
<li>搭載部の底付き・接触・パッドの非線形圧縮を扱い、保持具と搭載物へ伝わる力を評価する。</li>
<li>有効な空力・質量・剛性を上位の姿勢運動へ渡し直す。既存CFDの抗力検証も未通過。</li></ol>
<details><summary>仮定と参照文献</summary><p>すべての材料物性・熱条件・荷重時間は未測定の仮定です。</p>
<ul><li><a href="https://arxiv.org/abs/1211.1923">Romanelli et al. — 水ロケットの空気膨張</a></li>
<li><a href="https://www1.grc.nasa.gov/beginners-guide-to-aeronautics/isentrophic-compression/">NASA — 断熱変化</a></li>
<li><a href="https://aeresources.gatech.edu/aeroelasticity/Webpage/Divergence/Theory/Theory.php">Georgia Tech — ねじり発散</a></li>
<li><a href="https://www.mathworks.com/help/pde/ug/thermal-stress-analysis-of-jet-engine-turbine-blade.html">MathWorks — 熱応力解析</a></li></ul></details></section>
<footer class="muted">計算結果の図を埋め込んだ単一HTMLです。実機の破損試験・飛行試験は実施していません。</footer></main></html>"""
    path = folder / "index.html"
    path.write_text(document, encoding="utf-8")
    return path


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folder", type=Path)
    print(report(parser.parse_args().folder))
