# -*- coding: utf-8 -*-
"""The composing module, spec Ref: specs/isolated-footing.md Sec 4;
docs/token-efficient-expansion.md Sec 7 ("build the single-source-of-truth
module BEFORE the second consumer exists").
"""

import io
import os

import pytest

from rft.core.footing_mesh import (
    DIRECTION_X,
    MAT_SHAPE_L_ALTERNATING,
    MAT_SHAPE_U,
    SHAPE_L,
    SHAPE_U,
    bar_hook_plan_for_mat,
    local_mesh_bar_endpoints,
    local_top_mesh_bar_endpoints,
    mesh_bar_lengths,
)
from rft.core.footing_dowels import dowel_embedment, local_dowel_bar_geometry
from rft.core.column_layout import perimeter_bar_positions
from rft.core.footing_perimeter_tie import (
    PerimeterTieBarLengthMismatchError,
    PerimeterTieLadderExceedsFootingError,
    perimeter_tie_geometry,
    perimeter_tie_ladder_mm,
)
from rft.core.footing_plan import (
    TOP_REINFORCEMENT_BTM_ONLY,
    TOP_REINFORCEMENT_TOP_AND_BTM,
    DowelArrayPlan,
    FootingInputs,
    PerimeterTiePlan,
    TopMeshPlan,
    build_footing_plan,
)

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOTING_SCRIPT = os.path.join(
    REPO_ROOT, "IsolatedFooting.extension", "RFT-Tools.tab",
    "Footings.panel", "IsolatedFootingRFT.pushbutton", "script.py")


def _inputs(**overrides):
    values = dict(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0)
    values.update(overrides)
    return FootingInputs(**values)


def test_the_plan_carries_exactly_what_mesh_bar_lengths_would_compute():
    inputs = _inputs()
    plan = build_footing_plan(inputs)

    expected_lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    assert plan.bottom_mesh.lengths == expected_lengths


def test_the_plan_carries_the_primary_direction_from_the_given_offsets():
    plan = build_footing_plan(_inputs(x_offset_mm=300.0, y_offset_mm=150.0))
    assert plan.bottom_mesh.primary_direction == DIRECTION_X


def test_the_plan_carries_the_same_tie_default_the_core_function_applies():
    """R1: equal offsets default to DIRECTION_X, not a raise."""
    plan = build_footing_plan(_inputs(x_offset_mm=200.0, y_offset_mm=200.0))
    assert plan.bottom_mesh.primary_direction == DIRECTION_X


def test_the_plan_carries_bar_endpoints_matching_local_mesh_bar_endpoints():
    inputs = _inputs()
    plan = build_footing_plan(inputs)

    lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    expected_bar_x, expected_bar_y = local_mesh_bar_endpoints(
        lengths, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
        inputs.mesh_bar_y_dia_mm)

    assert plan.bottom_mesh.bar_x_endpoints == expected_bar_x
    assert plan.bottom_mesh.bar_y_endpoints == expected_bar_y


def test_the_plan_keeps_the_inputs_it_was_built_from():
    inputs = _inputs()
    plan = build_footing_plan(inputs)
    assert plan.inputs == inputs


def test_the_plan_carries_bar_hooks_matching_bar_hook_plan():
    """#199/#200: the composing module must be the ONE place
    bar_hook_plan_for_mat is called from, same as the #198 fields above --
    so its own output must match calling bar_hook_plan_for_mat directly
    with the same inputs (default inputs carry no #200 override, so this
    is exactly #199's own decision).
    """
    inputs = _inputs(x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=40.0)
    plan = build_footing_plan(inputs)

    expected_x_hooks = bar_hook_plan_for_mat(
        0, inputs.bottom_mat_shape_mode,
        inputs.x_offset_mm, inputs.x_offset_mm, inputs.mesh_bar_x_dia_mm,
        inputs.ld_multiplier)
    expected_y_hooks = bar_hook_plan_for_mat(
        0, inputs.bottom_mat_shape_mode,
        inputs.y_offset_mm, inputs.y_offset_mm, inputs.mesh_bar_y_dia_mm,
        inputs.ld_multiplier)
    assert plan.bottom_mesh.bar_x_hooks == expected_x_hooks
    assert plan.bottom_mesh.bar_y_hooks == expected_y_hooks


def test_the_plan_defaults_bottom_mat_shape_mode_to_none():
    """#200: FootingInputs must default the new field so every #198/#199
    call site (this test file's own ``_inputs`` helper, and script.py)
    that predates #200 keeps building without passing it.
    """
    inputs = _inputs()
    assert inputs.bottom_mat_shape_mode is None


def test_the_plan_honours_a_mat_shape_u_override_over_the_ld_comparison():
    # x_offset=300, ld_multiplier=10 -> LD_x=160 < 300 would be L-shape
    # under #199 alone; the MAT_SHAPE_U override must force U regardless.
    inputs = _inputs(
        x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=10.0,
        bottom_mat_shape_mode=MAT_SHAPE_U)
    plan = build_footing_plan(inputs)
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_U
    assert plan.bottom_mesh.bar_x_hooks.start.needs_hook is True
    assert plan.bottom_mesh.bar_x_hooks.end.needs_hook is True
    assert plan.bottom_mesh.bar_y_hooks.shape == SHAPE_U


def test_the_plan_honours_a_mat_shape_l_alternating_override():
    inputs = _inputs(
        x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=40.0,
        bottom_mat_shape_mode=MAT_SHAPE_L_ALTERNATING)
    plan = build_footing_plan(inputs)
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_L
    assert plan.bottom_mesh.bar_y_hooks.shape == SHAPE_L
    # bar_index=0 (both directions' one representative bar) -> start end
    # hooked, matching bar_hook_plan_for_mat's own even/odd rule.
    assert plan.bottom_mesh.bar_x_hooks.start.needs_hook is True
    assert plan.bottom_mesh.bar_x_hooks.end.needs_hook is False
    assert plan.bottom_mesh.bar_y_hooks.start.needs_hook is True
    assert plan.bottom_mesh.bar_y_hooks.end.needs_hook is False


def test_the_plan_picks_up_a_u_shape_when_both_directions_still_need_hooks():
    # LD_x = 40*16 = 640 > 300; LD_y = 40*12 = 480 > 150 -> both U.
    plan = build_footing_plan(
        _inputs(x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=40.0))
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_U
    assert plan.bottom_mesh.bar_y_hooks.shape == SHAPE_U


def test_the_plan_switches_only_the_direction_whose_offset_wins_to_l_shape():
    # One shared ld_multiplier (Sec 5), but different db/offset per
    # direction can still split the outcome: LD_x = 15*16 = 240 < 300
    # -> mesh_bar_x switches to L. LD_y = 15*12 = 180 > 150 -> mesh_bar_y
    # stays U.
    plan = build_footing_plan(
        _inputs(x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=15.0))
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_L
    assert plan.bottom_mesh.bar_y_hooks.shape == SHAPE_U


def test_the_plan_defaults_top_reinforcement_to_btm_only_with_no_top_mesh():
    """#201: predates-#201 callers (this file's own ``_inputs`` helper,
    and script.py) keep building a bottom-only plan unchanged."""
    inputs = _inputs()
    assert inputs.top_reinforcement == TOP_REINFORCEMENT_BTM_ONLY
    plan = build_footing_plan(inputs)
    assert plan.top_mesh is None


def test_top_and_btm_toggles_a_second_mat_instance_on():
    """#201's own test-volume rule: only confirm the toggle wires a
    second mat instance on/off -- no new formula math is being tested
    here, #198/#199/#200's own suites already cover the formulas this
    reuses."""
    inputs = _inputs(top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM)
    plan = build_footing_plan(inputs)
    assert isinstance(plan.top_mesh, TopMeshPlan)
    assert plan.top_mesh.lengths == plan.bottom_mesh.lengths


def test_the_top_mat_sits_near_the_top_face_not_on_top_of_the_bottom_mat():
    """Found missing in review (PR #214): the top mat must NOT reuse the
    bottom mat's Z-elevation. footing_thickness=450, top_cover=50,
    mesh_bar_x_dia=16, mesh_bar_y_dia=12 -> top z_x = 450-50-8 = 392,
    top z_y = 450-50-16-6 = 378 (mirrored local_top_mesh_bar_endpoints,
    measured down from the top face) -- neither equal to the bottom mat's
    z_x=58/z_y=72 (measured up from the bottom face).
    """
    inputs = _inputs(top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM)
    plan = build_footing_plan(inputs)

    bottom_z_x = plan.bottom_mesh.bar_x_endpoints.start.z_mm
    bottom_z_y = plan.bottom_mesh.bar_y_endpoints.start.z_mm
    top_z_x = plan.top_mesh.bar_x_endpoints.start.z_mm
    top_z_y = plan.top_mesh.bar_y_endpoints.start.z_mm

    assert bottom_z_x == pytest.approx(58.0)
    assert bottom_z_y == pytest.approx(72.0)
    assert top_z_x == pytest.approx(392.0)
    assert top_z_y == pytest.approx(378.0)
    assert top_z_x != pytest.approx(bottom_z_x)
    assert top_z_y != pytest.approx(bottom_z_y)


def test_top_mat_endpoints_match_local_top_mesh_bar_endpoints_directly():
    inputs = _inputs(top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM)
    plan = build_footing_plan(inputs)

    lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    expected_x, expected_y = local_top_mesh_bar_endpoints(
        lengths, inputs.top_cover_mm, inputs.footing_thickness_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm)

    assert plan.top_mesh.bar_x_endpoints == expected_x
    assert plan.top_mesh.bar_y_endpoints == expected_y


def test_top_mat_shape_mode_is_independent_of_the_bottom_mats():
    """Sec 7: 'Independent of Story 3 ... set separately, never
    coupled.' A bottom U override must not leak into an L-alternating
    top mat."""
    inputs = _inputs(
        top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM,
        bottom_mat_shape_mode=MAT_SHAPE_U,
        top_mat_shape_mode=MAT_SHAPE_L_ALTERNATING)
    plan = build_footing_plan(inputs)
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_U
    assert plan.top_mesh.bar_x_hooks.shape == SHAPE_L


def test_the_plan_defaults_dowel_fields_to_none_with_no_dowel_plan():
    """#202: predates-#202 callers (this file's own ``_inputs`` helper,
    and script.py) keep building a dowel-free plan unchanged."""
    inputs = _inputs()
    assert inputs.dowel_bar_dia_mm is None
    assert inputs.dowel_ld_multiplier is None
    plan = build_footing_plan(inputs)
    assert plan.dowel is None


def test_supplying_dowel_inputs_with_no_array_counts_falls_back_to_one_bar():
    """#222: when the two count-per-face inputs (and Cw/Cd/Ccover) are not
    supplied, ``DowelArrayPlan.bars`` must carry exactly the SAME single
    representative bar #202 always built -- every caller that predates
    #222 keeps building a plan with no dowel array unchanged, per the
    addendum spec Sec 3 Story 3's own trailing-defaults wording."""
    inputs = _inputs(dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0)
    assert inputs.dowel_count_b_face is None
    assert inputs.dowel_count_h_face is None
    plan = build_footing_plan(inputs)

    expected_embedment = dowel_embedment(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.dowel_bar_dia_mm, inputs.dowel_ld_multiplier)
    expected_geometry = local_dowel_bar_geometry(
        expected_embedment, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm)

    assert isinstance(plan.dowel, DowelArrayPlan)
    assert plan.dowel.embedment == expected_embedment
    assert plan.dowel.bars == [expected_geometry]


def test_supplying_the_full_dowel_array_inputs_positions_every_bar():
    """#222 (specs/isolated-footing-dowel-array.md Sec 3 Story 3): a
    2x2-per-face column layout (4 corner bars, none in the middle) must
    produce exactly 4 ``DowelArrayPlan.bars`` entries, each the
    representative bar's own bent-bar geometry translated to that bar's
    ``perimeter_bar_positions`` ``(u, v)`` -- corner bars de-duplicated
    between the two faces, not counted twice."""
    inputs = _inputs(
        dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=2, dowel_count_h_face=2)
    Cw_mm, Cd_mm, Ccover_mm = 450.0, 600.0, 40.0
    plan = build_footing_plan(inputs, Cw_mm=Cw_mm, Cd_mm=Cd_mm,
                              Ccover_mm=Ccover_mm)

    expected_layout = perimeter_bar_positions(
        b_mm=Cw_mm, h_mm=Cd_mm, cover_mm=Ccover_mm,
        tie_dia_mm=inputs.dowel_tie_dia_mm,
        bar_dia_mm=inputs.dowel_bar_dia_mm,
        count_b_face=inputs.dowel_count_b_face,
        count_h_face=inputs.dowel_count_h_face)

    assert isinstance(plan.dowel, DowelArrayPlan)
    assert len(expected_layout.bars) == 4
    assert len(plan.dowel.bars) == 4

    expected_embedment = dowel_embedment(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.dowel_bar_dia_mm, inputs.dowel_ld_multiplier)
    representative = local_dowel_bar_geometry(
        expected_embedment, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm)

    for expected_bar, actual_geometry in zip(expected_layout.bars,
                                              plan.dowel.bars):
        assert actual_geometry.vertical.end.x_mm == pytest.approx(
            representative.vertical.end.x_mm + expected_bar.u_mm)
        assert actual_geometry.vertical.end.y_mm == pytest.approx(
            representative.vertical.end.y_mm + expected_bar.v_mm)
        assert actual_geometry.vertical.end.z_mm == pytest.approx(
            representative.vertical.end.z_mm)
        assert actual_geometry.bottom_hook.start.x_mm == pytest.approx(
            representative.bottom_hook.start.x_mm + expected_bar.u_mm)
        assert actual_geometry.bottom_hook.start.y_mm == pytest.approx(
            representative.bottom_hook.start.y_mm + expected_bar.v_mm)


def test_the_dowel_array_requires_every_one_of_its_own_five_inputs():
    """Missing any single one of Cw_mm/Cd_mm/Ccover_mm/count_b_face/
    count_h_face must fall back to the single-bar plan, never a partial
    or guessed array."""
    inputs = _inputs(
        dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=2, dowel_count_h_face=2)
    plan = build_footing_plan(inputs, Cw_mm=450.0, Cd_mm=600.0,
                              Ccover_mm=None)
    assert len(plan.dowel.bars) == 1


def test_the_plan_defaults_perimeter_tie_fields_to_none_with_no_perimeter_tie_plan():
    """#204: predates-#204 callers keep building a perimeter-tie-free plan
    unchanged."""
    inputs = _inputs()
    assert inputs.perimeter_tie_dia_mm is None
    assert inputs.perimeter_tie_spacing_mm is None
    assert inputs.perimeter_tie_quantity is None
    assert inputs.perimeter_tie_lap_mm is None
    assert inputs.perimeter_tie_first_bar_length_mm is None
    assert inputs.perimeter_tie_second_bar_length_mm is None
    plan = build_footing_plan(inputs)
    assert plan.perimeter_tie is None


def test_supplying_perimeter_tie_inputs_builds_a_plan_matching_the_core_call():
    """The composing module must be the ONE place
    ``footing_perimeter_tie.perimeter_tie_geometry``/``perimeter_tie_
    ladder_mm`` are called from -- so its output must match calling them
    directly with the same inputs."""
    inputs = _inputs(
        footing_thickness_mm=1500.0,
        perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
        perimeter_tie_quantity=3)
    plan = build_footing_plan(inputs)

    expected_geometry = perimeter_tie_geometry(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.perimeter_tie_lap_mm)
    expected_ladder = perimeter_tie_ladder_mm(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.perimeter_tie_spacing_mm, inputs.perimeter_tie_quantity)

    assert isinstance(plan.perimeter_tie, PerimeterTiePlan)
    assert plan.perimeter_tie.geometry == expected_geometry
    assert plan.perimeter_tie.dia_mm == pytest.approx(10.0)
    assert plan.perimeter_tie.spacing_mm == pytest.approx(200.0)
    assert plan.perimeter_tie.quantity == 3
    assert plan.perimeter_tie.ladder == expected_ladder
    # This footing's perimeter (5600mm) is under the 12m stock length, so
    # there is nothing to split and bar_lengths stays None (R5).
    assert plan.perimeter_tie.bar_lengths is None


def test_a_split_perimeter_tie_with_matching_bar_lengths_builds_the_r5_plan():
    """R5: a large-enough footing needs a lap, and the engineer's own two
    typed bar lengths (summing to the total) build a ``PerimeterTieBarLengths``."""
    inputs = _inputs(
        a_mm=7000.0, b_mm=7000.0, footing_thickness_mm=1500.0,
        perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
        perimeter_tie_quantity=1, perimeter_tie_lap_mm=600.0,
        perimeter_tie_first_bar_length_mm=15000.0,
        perimeter_tie_second_bar_length_mm=13200.0)
    plan = build_footing_plan(inputs)

    # inner_a=inner_b=6900 -> length=2*(6900+6900)=27600; +600 lap = 28200.
    assert plan.perimeter_tie.geometry.splice.bar_count == 2
    assert plan.perimeter_tie.geometry.splice.total_length_mm == pytest.approx(
        28200.0)
    assert plan.perimeter_tie.bar_lengths.first_bar_length_mm == pytest.approx(
        15000.0)
    assert plan.perimeter_tie.bar_lengths.second_bar_length_mm == pytest.approx(
        13200.0)


def test_a_split_perimeter_tie_with_mismatched_bar_lengths_refuses():
    with pytest.raises(PerimeterTieBarLengthMismatchError):
        build_footing_plan(_inputs(
            a_mm=7000.0, b_mm=7000.0, footing_thickness_mm=1500.0,
            perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
            perimeter_tie_quantity=1, perimeter_tie_lap_mm=600.0,
            perimeter_tie_first_bar_length_mm=15000.0,
            perimeter_tie_second_bar_length_mm=10000.0))


def test_a_perimeter_tie_ladder_that_exceeds_the_footing_refuses():
    with pytest.raises(PerimeterTieLadderExceedsFootingError):
        build_footing_plan(_inputs(
            perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
            perimeter_tie_quantity=3))


def test_the_pushbutton_script_reads_the_composing_plan_not_bare_footing_mesh():
    """docs/token-efficient-expansion.md Sec 7: the placer must call
    ``footing_plan.build_footing_plan``, never ``rft.core.footing_mesh``
    directly -- exactly the beam tool's ``ZONE_LAYOUT_FLAGS`` drift this
    rule exists to rule out one element earlier. Text-checked because
    script.py imports ``pyrevit`` and cannot be imported by this suite;
    proven by mutation in tools/prove_guards.py.
    """
    source = io.open(FOOTING_SCRIPT, encoding="utf-8").read()
    assert "from rft.core.footing_plan import" in source
    assert "build_footing_plan" in source
    assert "from rft.core.footing_mesh import" not in source
    assert "footing_mesh.mesh_bar_lengths" not in source
