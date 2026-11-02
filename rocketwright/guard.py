"""Out-of-scope request detection (CLAUDE.md section 4).

Keyword/regex screening in Japanese and English, run BEFORE the request reaches the model
(the system prompt repeats the same policy). Categories that are refused:

  propellant        propellant formulation / manufacture
  engine_internals  engine or motor internal design (nozzle, grain, chamber, injector)
  guidance_control  guidance / attitude-control software
  weapon_target     ground targets, warheads, re-entry vehicles

`legal_approval` (asking us to obtain permits or rule on legality) is NOT refused: the request
passes but is flagged so the agent answers with a checklist of items and offices to confirm.

False positives are costly (a refused demo is a dead demo), so the patterns are deliberately
narrow: 回収 / パラシュート / 軌道 / 衛星 / recovery / orbit / satellite never trigger.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["GuardResult", "check_scope", "CATEGORY_PATTERNS"]


@dataclass(frozen=True)
class GuardResult:
    allowed: bool
    category: str | None
    reason: str
    suggestion: str


def _rx(*patterns: str) -> list[re.Pattern[str]]:
    return [re.compile(p, re.IGNORECASE) for p in patterns]


# Order matters: the first matching category is reported.
CATEGORY_PATTERNS: dict[str, list[re.Pattern[str]]] = {
    "propellant": _rx(
        r"推進剤[のを]?(配合|製造|調合|作|つく|合成)",
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
        r"(ノズル|燃焼室|グレイン|インジェクタ[ー]?)[の]?(設計|形状|寸法)",
        r"\bnozzle\s+(design|geometry|contour|throat)",
        r"\b(design|size|shape)\s+(the|an?|my)\s+(rocket\s+|motor\s+|engine\s+)?nozzle",
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
        r"(地点|目標|建物|場所)[をに]?(狙|命中)",
        r"弾頭",
        r"再突入(体|機|ビークル|カプセル)",
        r"(爆薬|爆発物|ミサイル)",
        r"\bhit\s+(a|the)\s+target",
        r"\b(strike|hit|impact)\s+(a|the|some)?\s*(ground\s+)?(target|location|coordinates?|building|city|town)",
        r"\bwarhead",
        r"\bre-?entry\s+(vehicle|body|capsule)",
        r"\b(missile|explosive|munition|weapon)",
        r"\btarget\s+at\s+[\d.]+\s*[ns]?\s*,?\s*[\d.]+\s*[ew]?",
    ),
}

# Flagged, not refused.
_LEGAL_PATTERNS = _rx(
    r"許可[をの]?(取|とっ|申請|代行)",
    r"申請[をの]?(代行|して|お願い)",
    r"(合法|違法|法的|法律)",
    r"\b(get|obtain|secure|file|apply\s+for)\s+(the\s+|a\s+)?(launch\s+)?(permit|permission|approval|licen[cs]e|waiver)",
    r"\bis\s+(it|this)\s+legal",
    r"\b(legal(ity|ly)?|lawful|regulat(ion|ory))\b",
)

_REASONS: dict[str, str] = {
    "propellant": "propellant formulation or manufacture is out of scope",
    "engine_internals": "engine/motor internal design is out of scope",
    "guidance_control": "guidance and attitude-control software is out of scope",
    "weapon_target": "ground targets, warheads and re-entry vehicles are out of scope",
}

_SUGGESTIONS: dict[str, str] = {
    "propellant": (
        "I can select a certified commercial motor or a representative engine from the catalog "
        "and size the vehicle around it."
    ),
    "engine_internals": (
        "I can pick an engine/motor from the catalog by thrust, Isp and mass and design the rest "
        "of the vehicle (stages, mass budget, fins, recovery) around it."
    ),
    "guidance_control": (
        "I can run an open-loop gravity-turn pitch program for concept design and report the "
        "resulting trajectory and static stability margin."
    ),
    "weapon_target": (
        "I can design for an altitude or orbit goal; landing points are only computed for "
        "recovery and safety-zone checks."
    ),
}

_LEGAL_SUGGESTION = (
    "I do not decide on permits or legality; I will add a checklist of items to confirm and the "
    "offices to contact instead."
)


def check_scope(text: str) -> GuardResult:
    """Screen a free-text request. Refused categories return allowed=False."""
    for category, patterns in CATEGORY_PATTERNS.items():
        for pattern in patterns:
            if pattern.search(text):
                return GuardResult(
                    allowed=False,
                    category=category,
                    reason=f"{_REASONS[category]} (matched /{pattern.pattern}/)",
                    suggestion=_SUGGESTIONS[category],
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
