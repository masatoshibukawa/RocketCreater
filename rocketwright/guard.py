"""Out-of-scope request detection (CLAUDE.md section 4).

Keyword/regex screening in Japanese and English, run BEFORE the request reaches the model
(the system prompt repeats the same policy). Categories that are refused:

  propellant        propellant formulation / manufacture
  engine_internals  engine or motor internal design (nozzle, grain, chamber, injector)
  guidance_control  guidance / attitude-control software
  weapon_target     ground targets, warheads, re-entry vehicles

`legal_approval` (asking us to obtain permits or rule on legality) is NOT refused: the request
passes but is flagged so the agent answers with a checklist of items and offices to confirm.

`check_bottle_limit` is the second screen, for a deployment that designs bottle rockets only: a
request for a satellite, an orbit or a target past the bottle range is answered 「できません」
before any model call. It only catches what is plain from the text; classify_requirement
catches the rest through `tier_limit_refusal`.

False positives are costly (a refused demo is a dead demo), so the patterns are deliberately
narrow: 回収 / パラシュート / 軌道 / 衛星 / recovery / orbit / satellite never trigger.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from rocketwright.classify import load_tiers

__all__ = [
    "CATEGORY_PATTERNS",
    "GuardResult",
    "TIER_LIMIT",
    "check_bottle_limit",
    "check_scope",
    "requirement_in_reach",
    "tier_limit_refusal",
]

TIER_LIMIT = "tier_limit"


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    category: str | None
    reason: str
    suggestion: str


def _rx(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# "Hit the target altitude" names a goal, not a place.
_NOT_A_GOAL = r"(?!\s+(altitude|apogee|height|orbit|perigee|mass|speed))"

# Order matters: the first matching category is reported.
CATEGORY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "propellant": _rx(
        r"推進(剤|薬)[のを]?(配合|製造|調合|作|つく|合成)",
        r"燃料[のを]?(配合|製造|調合|作|つく|合成)",
        r"(火薬|固体燃料|液体燃料|酸化剤)[のを]?(配合|製造|調合|作|つく)",
        r"propellant\s+(recipe|formulation|mix(ture|ing)?|composition|manufactur\w*|synthesis)",
        r"(make|mix|manufacture|brew|cook|synthesi[sz]e)\s+(my\s+own\s+|your\s+own\s+|the\s+|some\s+|rocket\s+)?(fuel|propellant|oxidi[sz]er)",
        r"\bapcp\b.*\b(mix|ratio|recipe|formula)",
        r"\b(mix|ratio|recipe|formula)\b.*\bapcp\b",
        r"\b(sugar|candy|black\s*powder|kno3|potassium\s+nitrate)\s+(rocket\s+)?(propellant|fuel|motor\s+recipe)",
    ),
    "engine_internals": _rx(
        r"(エンジン|モータ[ー]?)[の]?内部(設計|構造)",
        r"(燃焼室|グレイン|インジェクタ[ー]?)[の]?(設計|形状|寸法)",
        r"(ターボポンプ|ガスジェネレータ[ー]?|燃焼器)[をの]?(設計|開発|自作|製作)",
        r"(エンジン|モータ[ー]?)[をの]?(自作|手作り|自分で(作|つく))",
        r"\bturbo\s*pump\s+(design|sizing)|\bdesign\s+(a|the|my)\s+turbo\s*pump",
        r"\bnozzle\b.*\bcombustion\b",
        r"\bgrain\s+(geometry|design|shape|core)",
        r"\b(combustion\s+chamber|injector|throat)\s+(design|sizing|geometry)",
        r"\bdesign\s+(the|an?|my\s+own)\s+(rocket\s+)?(engine|motor)\s+(internals?|from\s+scratch)",
        r"\b(engine|motor)\s+internal\s+design",
    ),
    "guidance_control": _rx(
        r"誘導制御",
        r"誘導(ソフト|プログラム|アルゴリズム|則)",
        r"姿勢制御(ソフト|プログラム|アルゴリズム|の設計|設計|系の設計|ループ)",
        r"\bguidance\s+(software|code|algorithm|law|loop|program)",
        r"\bguidance\s+(and|&)\s+control",
        r"\battitude[\s-]+control\s+(software|code|algorithm|loop|design|system\s+design)",
        r"\bpid\b.*\b(attitude|pitch|roll|yaw|gimbal|tvc)",
        r"\b(attitude|pitch|roll|yaw)\s+(control(ler)?\s+)?(pid|loop\s+tuning)",
        r"\b(autopilot|flight\s+control\s+software|tvc\s+controller)",
    ),
    "weapon_target": _rx(
        r"地上の(特定の)?(地点|目標|場所|建物)[をに](狙|当|落と|命中)",
        r"(?<!着)(?<!落下)(?<!回収)(?<!着水)(地点|目標|建物|場所)[をに]?(狙|命中)",
        r"弾頭",
        r"再突入(体|機|ビークル|カプセル)",
        r"(爆薬|爆発物|爆弾|ミサイル|兵器|武器|大陸間弾道)",
        r"(?<![a-z])icbm(?![a-z])",
        r"(駅|ビル|建物|都市|市街|首都|基地|大使館|官邸|国会|空港|家|人|車)[にへを]"
        r"(落と(?!さな|さず)|当て|ぶつけ|命中|着弾|狙)",
        r"\bhit\s+(a|the)\s+target" + _NOT_A_GOAL,
        r"\b(strike|hit|impact)\s+(a|the|some)?\s*(ground\s+)?"
        r"(target" + _NOT_A_GOAL + r"|location|coordinates?|building|city|town)",
        r"\bwarhead",
        r"\bre-?entry\s+(vehicle|body|capsule)",
        r"\b(missile|explosive|munition|weapon)",
        r"\btarget\s+at\s+-?\d+(\.\d+)?\s*°?\s*[ns]\b[\s,]*-?\d+(\.\d+)?\s*°?\s*[ew]\b",
        r"\btarget\s+at\s+-?\d+(\.\d+)?\s*,\s*-?\d+(\.\d+)?",
    ),
}

# A water rocket's nozzle is a catalog part and its diameter a design variable, so nozzle
# sizing is refused only outside that context.
_BOTTLE_CONTEXT = re.compile(r"ペットボトル|水ロケット|ペトロケ|ボトル|water\s*rocket|bottle", re.I)
_NOZZLE_PATTERNS = _rx(
    r"ノズル[の]?(設計|形状|寸法)",
    r"\bnozzle\s+(design|geometry|contour|throat)",
    r"\b(design|size|shape)\s+(the|an?|my)\s+(rocket\s+|motor\s+|engine\s+)?nozzle",
)

# Flagged, not refused.
_LEGAL_PATTERNS = _rx(
    r"許可[をの]?(取|とっ|申請|代行)",
    r"申請[をの]?(代行|して|お願い)",
    r"(合法|違法|法的|法律|法規|規制|届出)",
    r"許可[がはを]?(要|必要|い[るり])",
    r"\b(get|obtain|secure|file|apply\s+for)\s+(the\s+|a\s+)?(launch\s+)?(permit|permission|approval|licen[cs]e|waiver)",
    r"\bis\s+(it|this)\s+legal",
    r"\b(legal(ity|ly)?|lawful|regulat(ion|ory))\b",
)

_REASONS: dict[str, str] = {
    "propellant": "できません。推進薬の配合や製造は扱いません。",
    "engine_internals": "できません。エンジンの内部設計は扱いません。",
    "guidance_control": "できません。誘導や姿勢制御のソフトは扱いません。",
    "weapon_target": "できません。地上の目標、弾頭、再突入体は扱いません。",
}

_SUGGESTION = "水と空気で飛ぶペットボトルロケットの設計なら、お手伝いできます。"

_LEGAL_SUGGESTION = (
    "I do not decide on permits or legality; I will add a checklist of items to confirm and the "
    "offices to contact instead."
)


def check_scope(text: str) -> GuardResult:
    """Screen a free-text request. Refused categories return allowed=False."""
    for category, patterns in CATEGORY_PATTERNS.items():
        if category == "engine_internals" and not _BOTTLE_CONTEXT.search(text):
            patterns = [*patterns, *_NOZZLE_PATTERNS]
        for pattern in patterns:
            if pattern.search(text):
                return GuardResult(
                    allowed=False,
                    category=category,
                    reason=_REASONS[category],
                    suggestion=_SUGGESTION,
                )
    for pattern in _LEGAL_PATTERNS:
        if pattern.search(text):
            return GuardResult(
                allowed=True,
                category="legal_approval",
                reason="legal/permit decisions are answered as a checklist only",
                suggestion=_LEGAL_SUGGESTION,
            )
    return GuardResult(allowed=True, category=None, reason="in scope", suggestion="")


# --------------------------------------------------------------------------- bottle only

_NUMBER = r"(\d+(?:,\d{3})*(?:\.\d+)?)"
_LENGTH_UNITS = {"km": 1000.0, "キロメートル": 1000.0, "キロ": 1000.0, "m": 1.0, "メートル": 1.0}
_MASS_UNITS = {
    "kg": 1.0,
    "キログラム": 1.0,
    "g": 0.001,
    "グラム": 0.001,
    "トン": 1000.0,
    "ton": 1000.0,
    "tons": 1000.0,
    "tonne": 1000.0,
    "tonnes": 1000.0,
}
_LENGTH = rf"{_NUMBER}\s*(km|キロメートル|キロ(?!グラム)|メートル|m(?![a-zA-Z/²³]))"
_HEIGHT_RX = re.compile(
    rf"(?:高度|高さ|上空|altitude|apogee|height)[^、。,.\d]{{0,10}}{_LENGTH}"
    rf"|{_LENGTH}\s*(?:まで|の高さ|の高度|上空|上げ|飛ば|に到達|届|altitude|apogee|high\b)"
    rf"|(?:\bto|\breach)\s+{_LENGTH}",
    re.IGNORECASE,
)
# Any distance in km is past a bottle rocket, but only the height counts as a target.
_KM_RX = re.compile(rf"{_NUMBER}\s*(km|キロメートル)(?!\s*(?:/\s*h|毎時))", re.IGNORECASE)
_NOT_HEIGHT_NEARBY = re.compile(r"半径|以内|離|時速|距離|範囲")
_MASS_RX = re.compile(
    rf"{_NUMBER}\s*(kg|キログラム|グラム|トン|tonnes?|tons?|g(?![a-zA-Z]))", re.IGNORECASE
)
# Water, the airframe and limits are masses too, but not what is carried.
_NOT_PAYLOAD_BEFORE = re.compile(r"水|機体|全備|総重量|総質量|全体|本体|空虚|自重")
_NOT_PAYLOAD_AFTER = re.compile(r"\s*(以下|未満|以内|の水)")

_OTHER_VEHICLES: tuple[tuple[re.Pattern[str], str], ...] = (
    (
        re.compile(r"衛星|\bcubesat\b|\bsatellite", re.I),
        "人工衛星の打ち上げは設計できません。",
    ),
    (
        re.compile(r"軌道[にへ]|軌道投入|周回軌道|低軌道|静止軌道|\b(LEO|GTO|SSO|orbit)\b", re.I),
        "軌道への投入は設計できません。",
    ),
    (
        re.compile(r"企業級|重工級|多段|ブースター|\bmultistage\b|\bbooster", re.I),
        "企業級や重工級のロケットは設計できません。",
    ),
    (
        re.compile(
            r"モデルロケット|アマチュア|固体モーター|固体ロケット|液体エンジン|液体燃料"
            r"|ハイパワー|\bmodel\s+rocket|\bsolid\s+motor|\bhigh[\s-]power",
            re.I,
        ),
        "火薬や燃料を使うロケットは設計できません。",
    ),
    (re.compile(r"\d\s*億円"), "この規模の予算のロケットは設計できません。"),
)


def _value(number: str, unit: str, units: dict[str, float]) -> float:
    return float(number.replace(",", "")) * units[unit.lower()]


def _heights(text: str) -> list[float]:
    found: list[float] = []
    for match in _HEIGHT_RX.finditer(text):
        number, unit = (group for group in match.groups() if group is not None)
        found.append(_value(number, unit, _LENGTH_UNITS))
    for match in _KM_RX.finditer(text):
        nearby = text[max(0, match.start() - 6) : match.end() + 6]
        if not _NOT_HEIGHT_NEARBY.search(nearby):
            found.append(_value(match[1], match[2], _LENGTH_UNITS))
    return found


def _payloads(text: str) -> list[float]:
    found: list[float] = []
    for match in _MASS_RX.finditer(text):
        before = text[max(0, match.start() - 6) : match.start()]
        if _NOT_PAYLOAD_BEFORE.search(before) or _NOT_PAYLOAD_AFTER.match(text, match.end()):
            continue
        found.append(_value(match[1], match[2], _MASS_UNITS))
    return found


def _length_text(metres: float) -> str:
    return f"{metres / 1000:g} km" if metres >= 1000 else f"{metres:g} m"


def _mass_text(kg: float) -> str:
    return f"{kg:g} kg" if kg >= 1 else f"{kg * 1000:g} g"


def _bottle_limits() -> tuple[float, float]:
    bottle = load_tiers()["tiers"]["bottle"]
    return bottle["design_reach_max"]["value"], bottle["payload_mass_max"]["value"]


def _refusal(detail: str) -> GuardResult:
    reach, payload = _bottle_limits()
    return GuardResult(
        allowed=False,
        category=TIER_LIMIT,
        reason=f"できません。このツールはペットボトルロケット専用です。{detail}",
        suggestion=(
            f"高度 {_length_text(reach)} まで、荷物 {_mass_text(payload)} までの"
            "ペットボトルロケットなら設計できます。"
        ),
    )


def _limit_detail(height_m: float, payload_kg: float) -> str | None:
    reach, payload = _bottle_limits()
    if height_m > reach:
        return f"高度 {_length_text(height_m)} は届きません。"
    if payload_kg > payload:
        return f"荷物 {_mass_text(payload_kg)} は重すぎます。"
    return None


def check_bottle_limit(text: str) -> GuardResult:
    """Refuse what the text plainly asks of something other than a bottle rocket."""
    plain = unicodedata.normalize("NFKC", text)
    if not _BOTTLE_CONTEXT.search(plain):
        for pattern, detail in _OTHER_VEHICLES:
            if pattern.search(plain):
                return _refusal(detail)
    detail = _limit_detail(max(_heights(plain), default=0.0), max(_payloads(plain), default=0.0))
    if detail:
        return _refusal(detail)
    return GuardResult(allowed=True, category=None, reason="in scope", suggestion="")


def requirement_in_reach(requirement: dict[str, Any]) -> bool:
    height = float(requirement.get("target_altitude_m") or 0.0)
    payload = float(requirement.get("payload_mass_kg") or 0.0)
    return _limit_detail(height, payload) is None


def tier_limit_refusal(requirement: dict[str, Any], required_tier: str) -> GuardResult:
    """The refusal for a normalised Requirement the bottle tier cannot cover."""
    height = float(requirement.get("target_altitude_m") or 0.0)
    payload = float(requirement.get("payload_mass_kg") or 0.0)
    if requirement.get("goal_kind") == "orbit":
        return _refusal("軌道への投入は設計できません。")
    detail = _limit_detail(height, payload)
    return _refusal(detail or f"{required_tier} の規模のロケットは設計できません。")
