import pytest

from rocketwright.manufacturing import PrintRequest, prepare_geometry, tools
from tests.test_analysis_record import spec


@pytest.mark.skipif(not tools()["blender"].is_file(), reason="Native Blender required")
def test_repeated_root_reduction_preserves_solid_geometry(tmp_path):
    s = spec()
    s.geometry = s.geometry.model_copy(
        update=dict(
            body_diameter_mm=90,
            body_height_mm=400,
            nose_length_mm=80,
            fin_root_mm=90 * 0.85 * 0.85,
            fin_tip_mm=30,
            fin_span_mm=80,
            fin_sweep_mm=35,
            fin_tail_inset_mm=5,
            fin_count=4,
            fin_thickness_mm=1.36,
            nose_wall_mm=1.2,
        )
    )
    _, report = prepare_geometry(
        PrintRequest(design=s.design, geometry=s.geometry), tmp_path / "cad"
    )
    assert set(report) == {"fin", "nose", "fit-ring"}
    for row in report.values():
        assert row["connected_components"] == 1
        assert all(
            row[key] == 0
            for key in (
                "non_manifold_edges",
                "boundary_edges",
                "zero_area_triangles",
                "nonadjacent_intersection_pairs",
            )
        )
    # The failed native mesh had six degenerate triangles and this finite volume.
    assert report["fin"]["volume_mm3"] == pytest.approx(8015.4246504058165, abs=0.001)
