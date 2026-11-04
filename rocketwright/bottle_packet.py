"""Print-scale patterns and a workshop handoff for a confirmed simulation candidate."""

import json
import math
from pathlib import Path

from rocketwright.bottle_assembly import catalog


def fin_pattern(g):
    span, root, tip, sweep, tab = (
        g[k] for k in ("fin_span", "fin_root", "fin_tip", "fin_sweep", "fin_tab")
    )
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="210mm" height="148mm"
 viewBox="0 0 210 148"><title>Fin face — print at 100%</title>
 <g font-family="sans-serif" font-size="4">
 <text x="10" y="10">フィン片面　8枚切出し・2枚で1翼　原寸印刷</text>
 <g transform="translate(25 20)" fill="none" stroke="black" stroke-width="0.35">
 <path d="M {-tab} 0 H 0 L {span} {sweep} v {tip} L 0 {root} H {-tab} Z"/>
 <path stroke-dasharray="2 2" d="M 0 0 V {root}"/></g>
 <text x="10" y="110">破線は折り線。2面のタブを左右に開く。</text>
 <path d="M 10 125 h 50 m -50 -2 v 4 m 50 -4 v 4" fill="none" stroke="black" stroke-width=".35"/>
 <text x="10" y="136">印刷後にこの線が 50 mm か確認</text></g></svg>"""


def side_view(plan):
    g = plan["dimensions_mm"]
    radius = g["body_diameter"] / 2
    end = g["overall"]
    root = end - g["fin_tail_inset"] - g["fin_root"]
    egg_end = g["nose_length"] + g["egg_bay_length"]
    base = egg_end + g["canopy_bay_length"]
    marks = [
        (plan["loaded_cg_mm"], "乾燥時重心（搭載込み）", "#154974", 190),
        (plan["wet_cg_mm"], "注水時重心", "#9f5100", 213),
        (plan["cp_mm"], "推定圧力中心", "#16603a", 236),
    ]
    labels = "".join(
        f'<path d="M {x:.2f} 0 V {y - 8}" stroke="{color}" stroke-dasharray="3 4"/>'
        f'<text x="{x - 3:.2f}" y="{y}" text-anchor="end" fill="{color}">{label}'
        f" {x:.1f} mm</text>"
        for x, label, color, y in marks
    )
    fins = "".join(
        f'<polygon points="{root},{s * radius} {root + g["fin_sweep"]},'
        f"{s * (radius + g['fin_span'])} {root + g['fin_sweep'] + g['fin_tip']},"
        f'{s * (radius + g["fin_span"])} {root + g["fin_root"]},{s * radius}" '
        f'fill="#d6e7ea" stroke="#38484a"/>'
        for s in (-1, 1)
    )
    return f'''<svg xmlns="http://www.w3.org/2000/svg" viewBox="-20 -205 {end + 60} 460">
 <title>組立配置図　先端を0 mmとして後方が正</title>
 <g font-family="sans-serif" font-size="12"><path d="M 0 0 L {g["nose_length"]} {-radius}
 H {end} V {radius} H {g["nose_length"]} Z" fill="#eef2ed" stroke="#38484a"/>
 <path d="M {egg_end} {-radius} v {2 * radius} M {base} {-radius} v {2 * radius}"
 stroke="#38484a"/>{fins}{labels}<text x="103" y="-6">搭載室</text>
 <text x="{egg_end + 7}" y="-6">傘室</text><text x="{base + 8}" y="-6">ボトル</text>
 <text x="0" y="-175">配置寸法 mm（ボトル輪郭は模式図）</text></g></svg>'''


def write_packet(directory, design, plan, history):
    g = plan["dimensions_mm"]
    sources = catalog()[0]["sources"]
    parts = "\n".join(
        f"| {r['name']} | {r['quantity']} | {r['mass_g']:.1f} | {r['allowance_jpy']} |"
        for r in plan["bill"]
    )
    checkout = [
        "現物の容器・ノズル・発射台の型式、説明書、使用条件、無加圧での着脱・スカートとの干渉",
        "卵と同寸・同質量のダミーで搭載室・ふたの保持、傘の収納・放出、テザーの保持",
        "組立後の乾燥質量と重心、注水時の重心、フィン位置・取付剛性",
        "固定状態の自由減衰の時系列、各モードの減衰比、開傘・着地時の荷重",
        "材料購入額・借用機材・実地で使用可能な条件と場所",
    ]
    plan["physical_status"] = "awaiting_bench_and_field_verification"
    plan["pending_evidence"] = checkout
    plan["holdout"] = history[-1]["result"]
    (directory / "assembly.json").write_text(
        json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    (directory / "fin-1to1.svg").write_text(fin_pattern(g), encoding="utf-8")
    (directory / "vehicle.svg").write_text(side_view(plan), encoding="utf-8")
    ratio = plan["canopy_side_mm"]
    square = ratio * (1 + math.sqrt(2))
    cone_r = math.hypot(g["body_diameter"] / 2, g["nose_length"])
    nozzle_text = (
        "ボトルの首を保持し、開口から直接排水する方式（D07 第3節 Design A）。"
        if plan["nozzle_interface"] == "open_neck"
        else "市販の噴射口と対応する発射台を一組で照合する方式（D02・P01）。"
    )
    template = Path(__file__).with_name("catalog") / "bottle_build_template.md"
    manual = template.read_text(encoding="utf-8").format(
        key=plan["key"],
        parts=parts,
        outlay=plan["estimated_outlay_jpy"],
        estimated_mass=plan["estimated_dry_mass_g"],
        mass=plan["dry_mass_g"],
        payload_g=design.payload_mass_kg * 1000,
        ground=", ".join(catalog()[1][r]["name"] for r in plan["ground"]),
        g=g,
        ratio=ratio,
        square=square,
        cone_r=cone_r,
        angle=180 * g["body_diameter"] / cone_r,
        corner=ratio / math.sqrt(2),
        bore_mm=design.nozzle_diameter_m * 1000,
        nozzle_text=nozzle_text,
    )

    manual += "\n" + "\n".join("- " + item for item in checkout)
    manual += "\n\n出典　" + " ・ ".join(f"[{k}]({v})" for k, v in sources.items()) + "\n"
    (directory / "build.md").write_text(manual, encoding="utf-8")
    worksheet = {
        "articles": {
            plan["key"]: {
                "article_id": "",
                "record": "",
                "dry_mass_g": None,
                "dry_cg_from_tip_mm": None,
                "modal_zeta_lower": None,
            }
        }
    }
    (directory / "bench-template.json").write_text(
        json.dumps(worksheet, indent=2) + "\n", encoding="utf-8"
    )
