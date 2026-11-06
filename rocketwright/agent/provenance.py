"""Provenance check: every number in the agent's explanation must come from a tool result.

`find_unsourced_numbers(text, tool_results)` extracts numbers from free text (handles
1,234.5 / 1.2e3 / 100km / 95%) and checks each against the set of numeric values found
anywhere in the tool results. A written number matches a result value when the value, rounded
to the number of significant digits written, equals it, after trying unit scalings
(m <-> km, kg <-> t, fraction <-> %, JPY 万/億). Small integers (0-10, counts/ordinals), years
and digits glued to identifiers (toolu_01..., #7) are ignored. Numbers written inside the text
of a tool result (a design_stage candidate's `why`, a buildability message, a formula) are
code-produced too: quoting them (as written, or in another unit) counts as sourced.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "NumberMention",
    "collect_result_values",
    "collect_text_values",
    "extract_numbers",
    "find_unsourced_numbers",
]

# ASCII minus and plus, U+2212 MINUS SIGN and the full-width hyphen-minus of Japanese text.
_SIGNS = "-+\u2212\uff0d"
# The boundaries look at ASCII only: Japanese has no spaces, so "高度9999mです" must still
# give 9999 m, while "toolu_01AB", "H3" and "3U" stay identifiers.
_NUMBER_RE = re.compile(
    r"(?<![A-Za-z0-9_.#])"  # not glued to an identifier, decimal, or ordinal marker
    rf"(?P<num>[{_SIGNS}]?(?:\d{{1,3}}(?:,\d{{3}})+|\d+)(?:\.\d+)?(?:[eE][-+]?\d+)?)"
    r"(?!\.\d)"  # the decimal part was consumed; avoid matching "1" of "1.5"
    r"\s*(?P<unit>km/h|km|mps|m/s|m2|m3|m|kg|t|%|s|cal|円|万円|億円|jpy|yen|g)?"
    r"(?![A-Za-z0-9_])",
    re.IGNORECASE,
)

# Multiplicative factors to convert the written number into the tool-result unit.
_UNIT_SCALES: dict[str, tuple[float, ...]] = {
    "km": (1000.0, 1.0),
    "m": (1.0, 0.001),
    "kg": (1.0, 1000.0),
    "t": (1000.0, 1.0),
    "g": (0.001, 1.0),
    "%": (0.01, 1.0),
    "万円": (1e4, 1.0),
    "億円": (1e8, 1.0),
}
# Scalings tried for numbers written without a unit (or with one not listed above).
_GENERIC_SCALES: tuple[float, ...] = (1.0, 1000.0, 0.001, 0.01, 100.0)

_SMALL_INT_MAX = 10
_YEAR_RANGE = (1900, 2100)


@dataclass(frozen=True)
class NumberMention:
    text: str  # as written, including the unit when present
    value: float
    unit: str | None
    sig_digits: int
    is_integer: bool


def _significant_digits(num_text: str) -> int:
    mantissa = re.split(r"[eE]", num_text)[0].replace(",", "").lstrip(_SIGNS)
    digits = mantissa.replace(".", "").lstrip("0")
    if "." not in mantissa:
        digits = digits.rstrip("0")  # trailing zeros of an integer are not significant
    return max(1, len(digits))


def extract_numbers(text: str) -> list[NumberMention]:
    out: list[NumberMention] = []
    for m in _NUMBER_RE.finditer(text):
        raw = m.group("num")
        unit = m.group("unit")
        try:
            value = float(raw.replace(",", "").replace("\u2212", "-").replace("\uff0d", "-"))
        except ValueError:  # pragma: no cover - regex guarantees a float
            continue
        shown = raw if unit is None else m.group(0).strip()
        out.append(
            NumberMention(
                text=shown,
                value=value,
                unit=unit.lower() if unit and unit.isascii() else unit,
                sig_digits=_significant_digits(raw),
                is_integer="." not in raw and "e" not in raw.lower(),
            )
        )
    return out


def collect_result_values(obj: Any, acc: set[float] | None = None) -> set[float]:
    """All numeric leaves (bool excluded) anywhere inside nested dicts/lists."""
    if acc is None:
        acc = set()
    if isinstance(obj, bool):
        return acc
    if isinstance(obj, (int, float)):
        if math.isfinite(obj):
            acc.add(float(obj))
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_result_values(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_result_values(v, acc)
    return acc


def collect_text_values(obj: Any, acc: set[float] | None = None) -> set[float]:
    """Numbers written inside the string leaves of nested dicts/lists, as written and scaled to
    the tool-result unit of their written unit (e.g. "941 m", "+-10%" -> -10 and -0.1)."""
    if acc is None:
        acc = set()
    if isinstance(obj, str):
        for mention in extract_numbers(obj):
            acc.add(mention.value)
            for scale in _UNIT_SCALES.get(mention.unit or "", ()):
                acc.add(mention.value * scale)
    elif isinstance(obj, dict):
        for v in obj.values():
            collect_text_values(v, acc)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            collect_text_values(v, acc)
    return acc


def _round_sig(x: float, sig: int) -> float:
    if x == 0:
        return 0.0
    return round(x, sig - int(math.floor(math.log10(abs(x)))) - 1)


def _close(a: float, b: float) -> bool:
    return math.isclose(a, b, rel_tol=1e-9, abs_tol=1e-12)


def _matches(mention: NumberMention, values: set[float]) -> bool:
    # Magnitudes are compared: prose writes a negative result as "南緯 39.26°" or "不足 3 kg",
    # and a range as "0.80-0.93", so the sign of a written number says little about its source.
    scales = _UNIT_SCALES.get(mention.unit or "", _GENERIC_SCALES)
    for scale in scales:
        target = abs(mention.value * scale)
        for v in values:
            if _close(abs(v), target) or _close(abs(_round_sig(v, mention.sig_digits)), target):
                return True
    return False


def _ignorable(mention: NumberMention) -> bool:
    if not mention.is_integer or mention.unit is not None:
        return False
    v = mention.value
    if 0 <= v <= _SMALL_INT_MAX:
        return True
    return _YEAR_RANGE[0] <= v <= _YEAR_RANGE[1] and float(v).is_integer()


def find_unsourced_numbers(text: str, tool_results: list[dict[str, Any]]) -> list[str]:
    """Return the numbers (as written) in `text` that do not appear in any tool result."""
    values = collect_result_values(tool_results) | collect_text_values(tool_results)
    bad: list[str] = []
    for mention in extract_numbers(text):
        if _ignorable(mention):
            continue
        if not _matches(mention, values):
            bad.append(mention.text)
    return bad
