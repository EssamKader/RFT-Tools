# -*- coding: utf-8 -*-
"""#205 -- the footing window's own Review report. Values in, lines of
text out; nothing here is recomputed, only the objects
``build_footing_plan``/``footing_batch`` already produce, read.
"""

from rft.core.footing_batch import BatchExisting, BatchGroup, Exclusion, GroupKey
from rft.core.footing_plan import DowelColumnSection, FootingInputs, build_footing_plan
from rft.core.footing_report import (
    ReportSection,
    batch_exclusion_section,
    batch_group_section,
    batch_replacement_section,
    column_section_section,
    dowel_array_section,
    footing_geometry_section,
    mesh_section,
    not_yet_placed_section,
    render,
)
from rft.revit.footing_host import FootingGeometry


def _geometry():
    return FootingGeometry(
        a_mm=1800.0, b_mm=1200.0, footing_thickness_mm=450.0,
        cover_mm=50.0, bottom_cover_mm=50.0, top_cover_mm=50.0)


def _column_section():
    return DowelColumnSection(Cw_mm=300.0, Cd_mm=600.0, Ccover_mm=40.0)


def _plan():
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=16.0, dowel_ld_multiplier=40.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=4)
    return build_footing_plan(inputs, column_section=_column_section())


def test_footing_geometry_section_names_every_dimension():
    lines = "\n".join(footing_geometry_section(_geometry()).lines)
    assert "1800" in lines and "1200" in lines
    assert "450" in lines
    assert "50" in lines


def test_column_section_section_names_cw_cd_and_cover():
    lines = "\n".join(column_section_section(_column_section()).lines)
    assert "300" in lines and "600" in lines and "40" in lines


def test_mesh_section_names_both_bar_lengths():
    plan = _plan()
    lines = "\n".join(mesh_section(plan).lines)
    assert "mesh_bar_x" in lines and "mesh_bar_y" in lines


def test_mesh_section_states_each_bars_hook_shape():
    """#229: the Review page must say U or L -- #199/#200 always computed
    this, but nothing reported it before now (Essam's own live-host
    finding, 2026-09-24)."""
    plan = _plan()
    lines = "\n".join(mesh_section(plan).lines)
    assert plan.bottom_mesh.bar_x_hooks.shape in lines
    assert plan.bottom_mesh.bar_y_hooks.shape in lines
    assert "hooked" in lines


def test_mesh_section_reports_the_actual_shorter_length_for_an_l_shape_bar():
    """Issue #236 (review of #229): mesh_bar_lengths()'s own
    mesh_bar_x_mm/mesh_bar_y_mm is the FIXED U-shape total (Z + 2*N),
    computed before the per-end hook decision is known -- it must NOT be
    what the report prints once a bar is actually L-shaped (one end
    straight), since #229 places that bar with only ONE hook leg, not
    two. x_offset=700 (> LD_x=640) means the mesh_bar_x end needs no
    hook there, while y_offset=150 (< LD_y=480) still hooks both
    mesh_bar_y ends -- an L-shape bar_x next to a U-shape bar_y in the
    SAME plan, so the report's own per-bar wording must differ too."""
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=700.0, y_offset_mm=150.0,
        ld_multiplier=40.0)
    plan = build_footing_plan(inputs)
    lengths = plan.bottom_mesh.lengths

    assert not plan.bottom_mesh.bar_x_hooks.start.needs_hook
    assert not plan.bottom_mesh.bar_x_hooks.end.needs_hook
    lines = "\n".join(mesh_section(plan).lines)

    fixed_u_total = "%.1f mm" % lengths.mesh_bar_x_mm
    actual_l_total = "%.1f mm" % lengths.z_mm
    assert fixed_u_total not in lines
    assert actual_l_total in lines
    assert "neither end hooked, straight bar" in lines
    assert "both ends hooked" in lines  # bar_y is still U-shape


def test_dowel_array_section_names_the_real_bar_count():
    plan = _plan()
    section = dowel_array_section(plan)
    lines = "\n".join(section.lines)
    assert "%d dowel bar" % len(plan.dowel.bars) in lines
    assert len(plan.dowel.bars) > 1  # a real array, not the 1-bar fallback


def _overshooting_plan():
    """Issue #230's own hand-computed reproduction -- see
    test_footing_plan.py's ``_small_edge_offset_inputs`` for the numeric
    write-up."""
    inputs = FootingInputs(
        a_mm=1000.0, b_mm=700.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=15.9,
        mesh_bar_y_dia_mm=15.9, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=15.9, dowel_ld_multiplier=40.0,
        dowel_tie_dia_mm=8.0, dowel_count_b_face=3, dowel_count_h_face=3)
    column_section = DowelColumnSection(
        Cw_mm=400.0, Cd_mm=400.0, Ccover_mm=40.0)
    return build_footing_plan(inputs, column_section=column_section)


def test_dowel_array_section_warns_when_a_hook_overshoots_the_footing_edge():
    plan = _overshooting_plan()
    assert plan.dowel.overshoot_bar_indices  # the fixture must overshoot
    lines = "\n".join(dowel_array_section(plan).lines)
    assert "WARNING" in lines
    assert str(len(plan.dowel.overshoot_bar_indices)) in lines


def test_dowel_array_section_has_no_warning_when_nothing_overshoots():
    plan = _plan()
    assert plan.dowel.overshoot_bar_indices == []
    lines = "\n".join(dowel_array_section(plan).lines)
    assert "WARNING" not in lines


def test_dowel_array_section_states_no_splice_when_none_given():
    """R12 (docs/footing/spec-amendments.md): the default ``FootingInputs.
    dowel_splice_length_mm=None`` case must say so explicitly and state the
    (unchanged) top elevation, footing_thickness_mm."""
    plan = _plan()
    assert plan.inputs.dowel_splice_length_mm is None
    lines = "\n".join(dowel_array_section(plan).lines)
    assert "No splice length" in lines
    assert "450.0 mm" in lines


def test_dowel_array_section_states_the_splice_length_and_top_elevation():
    """R12: a supplied Ls must be named, along with the real total top
    elevation (footing_thickness_mm + Ls)."""
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=16.0, dowel_ld_multiplier=40.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=4,
        dowel_splice_length_mm=600.0)
    plan = build_footing_plan(inputs, column_section=_column_section())
    lines = "\n".join(dowel_array_section(plan).lines)
    assert "Splice length Ls = 600.0 mm" in lines
    assert "1050.0 mm" in lines  # 450 + 600


def test_not_yet_placed_section_names_the_three_unwired_pieces():
    lines = "\n".join(not_yet_placed_section().lines)
    assert "Top mesh" in lines
    assert "dowel-tie" in lines
    assert "perimeter-tie" in lines


def test_batch_group_section_names_each_group_its_key_and_its_footings():
    groups = [
        BatchGroup(key=GroupKey(1800.0, 1200.0, 450.0, 50.0, 50.0, 50.0,
                                300.0, 600.0, 40.0),
                  element_ids=[1, 2]),
    ]
    lines = "\n".join(batch_group_section(groups).lines)
    assert "1" in lines and "2" in lines
    assert "1800" in lines and "300" in lines


def test_batch_group_section_with_no_groups_says_so():
    lines = batch_group_section([]).lines
    assert any("excluded" in line for line in lines)


def test_batch_exclusion_section_names_every_exclusion_and_its_reason():
    exclusions = [Exclusion(element_id=42, reason="no column attached")]
    lines = "\n".join(batch_exclusion_section(exclusions).lines)
    assert "42" in lines
    assert "no column attached" in lines


def test_batch_exclusion_section_when_empty_says_so():
    lines = batch_exclusion_section([]).lines
    assert any("No footings were excluded" in line for line in lines)


def test_batch_replacement_section_names_every_footing_and_its_count():
    rows = [
        BatchExisting(element_id=1, replaced_count=8, foreign_ids=[]),
        BatchExisting(element_id=2, replaced_count=0, foreign_ids=[55]),
    ]
    lines = "\n".join(batch_replacement_section(rows).lines)
    assert "Footing 1" in lines and "8" in lines
    assert "Footing 2" in lines
    assert "55" in lines and "left untouched" in lines


def test_batch_replacement_section_with_no_rows_says_nothing_is_replaced():
    lines = batch_replacement_section([]).lines
    assert any("nothing will be replaced" in line for line in lines)


def test_render_produces_a_heading_per_section():
    sections = [
        ReportSection("First", ["line one"]),
        ReportSection("Second", ["line two"]),
    ]
    text = render(sections)
    assert "FIRST" in text and "SECOND" in text
    assert "line one" in text and "line two" in text
