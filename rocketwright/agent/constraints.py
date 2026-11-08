"""What the user stated that the code keeps, whatever the model does.

Today that is the bottle size. The prompt asks the model to keep it too, but the light model
picked a 500 mL bottle for a 1.5 L request. `read_constraints` reads the size from the request,
and `constrain` makes the part-choosing tools start from that bottle, offers only that bottle
when the bottle stage is revisited, and turns away a design with another one, so no attempt is
spent on it.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any

from rocketwright.parts import load_parts

__all__ = ["UserConstraints", "constrain", "read_constraints"]

_VOLUME = re.compile(
    r"(\d+(?:\.\d+)?)\s*(ミリリットル|リットル|ml|l|ℓ)(?![a-z])", re.IGNORECASE
)
_LITRES = {"ml": 0.001, "ミリリットル": 0.001, "l": 1.0, "ℓ": 1.0, "リットル": 1.0}
_BOTTLE_NEAR = re.compile(r"ボトル|bottle", re.IGNORECASE)
_WATER_BEFORE = re.compile(r"水")
NEAR_CHARS = 12
SAME_SIZE = 0.05  # a stated size matches a bottle within this fraction


@dataclass(frozen=True)
class UserConstraints:
    bottle_id: str | None = None
    said: str = ""  # the size as the user wrote it, for the messages


def _bottles() -> list[Any]:
    return load_parts().by_kind("bottle", "bottle")


def read_constraints(text: str) -> UserConstraints:
    """The bottle the request names by its size, when it names exactly one the catalog has."""
    plain = unicodedata.normalize("NFKC", text)
    sizes: dict[float, str] = {}
    for match in _VOLUME.finditer(plain):
        near = plain[max(0, match.start() - NEAR_CHARS) : match.end() + NEAR_CHARS]
        before = plain[max(0, match.start() - 4) : match.start()]
        if not _BOTTLE_NEAR.search(near) or _WATER_BEFORE.search(before):
            continue
        litres = float(match[1]) * _LITRES[match[2].lower()]
        sizes[round(litres, 4)] = match[0]
    if len(sizes) != 1:
        return UserConstraints()
    (litres, said), = sizes.items()
    for bottle in _bottles():
        if abs(bottle.volume_m3 * 1000 - litres) <= SAME_SIZE * litres:
            return UserConstraints(bottle_id=bottle.id, said=said)
    return UserConstraints()


def _volume_of(bottle_id: str) -> float | None:
    return next((b.volume_m3 for b in _bottles() if b.id == bottle_id), None)


def _refusal(held: UserConstraints, found: str) -> str:
    return (
        f"the user asked for a {held.said} bottle ({held.bottle_id}); this uses {found}. "
        f"Keep {held.bottle_id}, or say plainly that the requirement cannot be met with it."
    )


def constrain(
    tool: str, tool_input: dict[str, Any], held: UserConstraints
) -> tuple[dict[str, Any], str | None]:
    """The input to run (a copy when changed) and, when the call breaks what the user stated,
    the reason to send back instead of running it."""
    if held.bottle_id is None:
        return tool_input, None
    if tool == "auto_design":
        fixed = {**(tool_input.get("fixed") or {}), "bottle": held.bottle_id}
        return {**tool_input, "fixed": fixed}, None
    if tool == "design_stage":
        if tool_input.get("stage") == "bottle":
            return {**tool_input, "only_option": held.bottle_id}, None
        chosen = [p for p in tool_input.get("chosen") or [] if p.get("stage") != "bottle"]
        chosen = [{"stage": "bottle", "value": held.bottle_id}, *chosen]
        return {**tool_input, "chosen": chosen}, None
    if tool == "design_from_parts":
        bottle = (tool_input.get("build") or {}).get("bottle_id")
        if bottle is not None and bottle != held.bottle_id:
            return tool_input, _refusal(held, bottle)
        return tool_input, None
    if tool in ("simulate_design", "run_dispersion"):
        volume = (tool_input.get("design") or {}).get("bottle_volume_m3")
        wanted = _volume_of(held.bottle_id)
        if volume is not None and wanted and abs(volume - wanted) > SAME_SIZE * wanted:
            return tool_input, _refusal(held, f"a {volume * 1000:g} L bottle")
    return tool_input, None
