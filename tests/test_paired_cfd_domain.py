import math

import numpy as np
import pytest

from rocketwright.analysis.runtime import Runtime
from scripts.prepare_paired_cfd import select_runtime, transverse_envelope


def assembly(length=700, cg=420, span=145):
    return dict(
        dimensions_mm=dict(body_diameter=90, overall=length, fin_span=span), loaded_cg_mm=cg
    )


def test_domain_covers_all_angles_and_preserves_precision():
    a = assembly()
    b = assembly(cg=425)
    initial = Runtime(cfd_cells_coarse=16, cfd_cells_fine=20, cfd_width=10)
    selected, evidence = select_runtime(initial, [a, b])
    assert selected.cfd_width == 12 and evidence["domain_audit_width_d"] == 14
    original = initial.model_dump(exclude={"cfd_width"})
    assert selected.model_dump(exclude={"cfd_width"}) == original
    for item in (a, b):
        values = [
            max(item["loaded_cg_mm"], 700 - item["loaded_cg_mm"]) / 90 * abs(math.sin(t))
            + (0.5 + 145 / 90) * abs(math.cos(t))
            for t in np.linspace(0, math.pi, 1001)
        ]
        assert max(values) <= transverse_envelope(item) <= 12 / 2 - 0.75


def test_unrepresentable_domain_is_not_silently_clipped():
    with pytest.raises(ValueError, match="cannot fit"):
        select_runtime(Runtime(), [assembly(length=2000, cg=1000), assembly()])


def test_domain_just_above_twelve_uses_a_representable_half_step():
    runtime, evidence = select_runtime(
        Runtime(cfd_cells_coarse=16, cfd_cells_fine=20), [assembly(cg=440), assembly()]
    )
    assert 12 < evidence["required_width_d"] < 12.5
    assert runtime.cfd_width == 12.5
    assert evidence["domain_audit_width_d"] == 14.5
