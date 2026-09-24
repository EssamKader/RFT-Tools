# -*- coding: utf-8 -*-
"""The composing module, spec Ref: specs/isolated-footing.md Sec 4;
docs/token-efficient-expansion.md Sec 7 ("build the single-source-of-truth
module BEFORE the second consumer exists").
"""

import io
import math
import os

import pytest

from rft.core.footing_mesh import (
    DIRECTION_X,
    MAT_SHAPE_L_ALTERNATING,
    MAT_SHAPE_U,
    SHAPE_L,
    SHAPE_U,
    bar_hook_plan_for_mat,
    bottom_mesh_bar_geometry,
    local_mesh_bar_endpoints,
    local_top_mesh_bar_endpoints,
    mesh_bar_lengths,
    top_mesh_bar_geometry,
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
    DowelColumnSection,
    DowelArrayLayoutError,
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


def test_bottom_mesh_bar_array_is_none_by_default():
    """#232 (R11): every caller that predates this ticket -- no
    mesh_bar_x_spacing_mm/mesh_bar_y_spacing_mm supplied -- keeps building
    a plan with no array, unchanged."""
    plan = build_footing_plan(_inputs())
    assert plan.bottom_mesh.bar_x_array is None
    assert plan.bottom_mesh.bar_y_array is None


def test_build_footing_plan_builds_the_bottom_mesh_array_when_spacing_is_given():
    """Hand-computed counts, per R11's own axis convention: mesh_bar_x is
    spaced across Z2=1100mm (bottom_cover=50, mesh dia 16/12, cover=50,
    a=1800, b=1200 -> Z2 = 1200 - 100 = 1100) at 200mm -> 7 bars; mesh_bar_y
    is spaced across Z=1700mm at 200mm -> ceil(1700/200)=9 spaces, 10 bars.
    """
    plan = build_footing_plan(_inputs(
        mesh_bar_x_spacing_mm=200.0, mesh_bar_y_spacing_mm=200.0))
    assert len(plan.bottom_mesh.bar_x_array) == 7
    assert len(plan.bottom_mesh.bar_y_array) == 10


def test_build_footing_plan_builds_the_array_only_for_the_direction_given_spacing():
    plan = build_footing_plan(_inputs(mesh_bar_x_spacing_mm=200.0))
    assert plan.bottom_mesh.bar_x_array is not None
    assert plan.bottom_mesh.bar_y_array is None


def test_top_mesh_never_gets_a_bottom_style_array():
    """#232's own scope: the array builder is bottom-mat-only (Story 4's
    top mat has no placement adapter yet, same reasoning #229's bent
    geometry stayed bottom-only)."""
    plan = build_footing_plan(_inputs(
        top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM,
        mesh_bar_x_spacing_mm=200.0, mesh_bar_y_spacing_mm=200.0))
    assert plan.top_mesh.bar_x_array is None
    assert plan.top_mesh.bar_y_array is None
    assert plan.bottom_mesh.bar_x_array is not None


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


def test_the_plan_carries_bar_geometry_matching_bottom_mesh_bar_geometry():
    """#229: the composing module must be the ONE place
    bottom_mesh_bar_geometry is called from, so its output matches calling
    it directly with the SAME lengths/hook plan the plan itself carries."""
    inputs = _inputs()
    plan = build_footing_plan(inputs)

    expected_bar_x, expected_bar_y = bottom_mesh_bar_geometry(
        plan.bottom_mesh.lengths, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        plan.bottom_mesh.bar_x_hooks, plan.bottom_mesh.bar_y_hooks)
    assert plan.bottom_mesh.bar_x_geometry == expected_bar_x
    assert plan.bottom_mesh.bar_y_geometry == expected_bar_y


def test_the_top_mesh_now_gets_its_own_bent_geometry_per_r13():
    """#233 (R13, docs/footing/spec-amendments.md): the top mat's hook
    direction is now resolved (DOWNWARD, toward the bottom mat), so
    ``top_mesh.bar_x_geometry``/``bar_y_geometry`` must be populated by
    the SAME composing module that populates the bottom mat's own
    geometry -- the ``None`` this test used to require is exactly what
    R13 was raised to fix."""
    inputs = _inputs(top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM)
    plan = build_footing_plan(inputs)

    expected_bar_x, expected_bar_y = top_mesh_bar_geometry(
        plan.top_mesh.lengths, inputs.top_cover_mm,
        inputs.footing_thickness_mm, inputs.mesh_bar_x_dia_mm,
        inputs.mesh_bar_y_dia_mm, plan.top_mesh.bar_x_hooks,
        plan.top_mesh.bar_y_hooks)
    assert plan.top_mesh.bar_x_geometry == expected_bar_x
    assert plan.top_mesh.bar_y_geometry == expected_bar_y


def test_the_top_mesh_array_stays_none_array_is_separate_follow_up_scope():
    """#233's own scope: only the single representative bar per direction
    is built for the top mat -- the array (many parallel bars, mirroring
    #232's bottom-mesh array) is deliberately left unbuilt."""
    plan = build_footing_plan(_inputs(
        top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM,
        mesh_bar_x_spacing_mm=200.0, mesh_bar_y_spacing_mm=200.0))
    assert plan.top_mesh.bar_x_array is None
    assert plan.top_mesh.bar_y_array is None


def test_the_top_mesh_hook_leg_is_subtracted_not_added():
    """R13's own reason for existing: a hooked top-mat bar's own vertical
    leg must go DOWN (toward the bottom mat), the opposite direction from
    the bottom mat's own hook leg at the SAME (mirrored) base elevation."""
    inputs = _inputs(top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM)
    plan = build_footing_plan(inputs)

    assert plan.top_mesh.bar_x_hooks.start.needs_hook
    base_z = plan.top_mesh.bar_x_geometry.points[1].z_mm
    hooked_z = plan.top_mesh.bar_x_geometry.points[0].z_mm
    assert hooked_z < base_z


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


def test_dowel_splice_length_defaults_to_none_and_stops_at_the_footing_top():
    """R12 (docs/footing/spec-amendments.md), append-only field: every
    caller that predates this ticket (this file's own ``_inputs`` helper)
    keeps building the SAME dowel top elevation as before -- exactly
    ``footing_thickness_mm``."""
    inputs = _inputs(dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0)
    assert inputs.dowel_splice_length_mm is None
    plan = build_footing_plan(inputs)
    assert plan.dowel.bars[0].vertical.end.z_mm == pytest.approx(
        inputs.footing_thickness_mm)


def test_dowel_splice_length_extends_the_one_bar_fallback_past_the_top():
    """R12: the composing module (``build_footing_plan``/
    ``_build_dowel_plan``) is the ONE place ``inputs.dowel_splice_
    length_mm`` is read from -- threaded straight to ``local_dowel_bar_
    geometry`` for the no-array fallback path."""
    inputs = _inputs(
        dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_splice_length_mm=600.0)
    plan = build_footing_plan(inputs)
    assert plan.dowel.bars[0].vertical.end.z_mm == pytest.approx(
        inputs.footing_thickness_mm + 600.0)


def test_dowel_splice_length_extends_every_bar_in_a_real_array():
    """R12: every bar in a real N-position array shares the SAME splice
    length (Sec 8 gives no per-bar variation) -- threaded through
    ``positioned_dowel_bar_geometry`` for each bar ``perimeter_bar_
    positions`` produced."""
    inputs, column_section = _array_inputs()
    inputs = inputs._replace(dowel_splice_length_mm=350.0)
    plan = build_footing_plan(inputs, column_section=column_section)

    assert len(plan.dowel.bars) == 4
    for bar in plan.dowel.bars:
        assert bar.vertical.end.z_mm == pytest.approx(
            inputs.footing_thickness_mm + 350.0)


def test_supplying_dowel_inputs_with_no_array_counts_falls_back_to_one_bar():
    """#222: when the two count-per-face inputs (and column_section) are
    not supplied, ``DowelArrayPlan.bars`` must carry exactly the SAME
    single representative bar #202 always built -- every caller that
    predates #222 keeps building a plan with no dowel array unchanged, per
    the addendum spec Sec 3 Story 3's own trailing-defaults wording."""
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


def _array_inputs():
    """Every one of the array's own four gating inputs (column_section as
    a whole, dowel_count_b_face, dowel_count_h_face, dowel_tie_dia_mm)
    supplied, with column_section's own three sub-fields also set -- the
    fixture every "one missing" permutation test below starts from and
    knocks a single value out of."""
    inputs = _inputs(
        dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=2, dowel_count_h_face=2)
    column_section = DowelColumnSection(
        Cw_mm=450.0, Cd_mm=600.0, Ccover_mm=40.0)
    return inputs, column_section


def _independent_outward_direction(u_mm, v_mm, half_u_mm, half_v_mm,
                                   is_corner):
    """R10's rule, restated independently of ``rft.core.footing_dowels.
    dowel_outward_direction`` -- comparing the geometry the plan actually
    built against THIS, not against the production function's own output,
    so the test cannot pass merely because a defect in that function
    agrees with itself."""
    if is_corner:
        sign_u = 1.0 if u_mm >= 0.0 else -1.0
        sign_v = 1.0 if v_mm >= 0.0 else -1.0
        return sign_u / math.sqrt(2.0), sign_v / math.sqrt(2.0)
    if abs(abs(v_mm) - half_v_mm) < 1.0e-6:
        return 0.0, (1.0 if v_mm >= 0.0 else -1.0)
    assert abs(abs(u_mm) - half_u_mm) < 1.0e-6
    return (1.0 if u_mm >= 0.0 else -1.0), 0.0


def _assert_bar_positioned_and_bent_outward(
        expected_bar, actual_geometry, representative, half_u_mm,
        half_v_mm, hook_length_mm):
    """Position (vertical leg + bend corner) at the bar's own (u, v);
    hook bent OUTWARD per R10 (docs/footing/spec-amendments.md), not
    translated from the representative's own fixed +X direction."""
    assert actual_geometry.vertical.end.x_mm == pytest.approx(
        representative.vertical.end.x_mm + expected_bar.u_mm)
    assert actual_geometry.vertical.end.y_mm == pytest.approx(
        representative.vertical.end.y_mm + expected_bar.v_mm)
    assert actual_geometry.vertical.end.z_mm == pytest.approx(
        representative.vertical.end.z_mm)
    # The bend corner (vertical.start == bottom_hook.end) sits at the
    # bar's own (u, v) regardless of hook direction.
    assert actual_geometry.bottom_hook.end.x_mm == pytest.approx(
        expected_bar.u_mm)
    assert actual_geometry.bottom_hook.end.y_mm == pytest.approx(
        expected_bar.v_mm)

    direction_u, direction_v = _independent_outward_direction(
        expected_bar.u_mm, expected_bar.v_mm, half_u_mm, half_v_mm,
        expected_bar.is_corner)
    assert actual_geometry.bottom_hook.start.x_mm == pytest.approx(
        expected_bar.u_mm + direction_u * hook_length_mm)
    assert actual_geometry.bottom_hook.start.y_mm == pytest.approx(
        expected_bar.v_mm + direction_v * hook_length_mm)


def test_supplying_the_full_dowel_array_inputs_positions_and_bends_every_bar_outward():
    """#222 (Sec 3 Story 3) positions every bar at its own ``(u, v)``; R10
    (docs/footing/spec-amendments.md) bends each bar's own hook OUTWARD
    from the column centroid, not along the representative's own fixed
    +X. Corner de-duplication/count is ``perimeter_bar_positions``' OWN
    behaviour, already proven by ``tests/test_column_layout.py::
    test_the_four_corner_bars_appear_ONCE_each`` -- not re-derived here
    (Essam's own Test volume rule). This fixture (2x2-per-face) has ONLY
    corner bars -- see the next test for a face-interior bar."""
    inputs, column_section = _array_inputs()
    plan = build_footing_plan(inputs, column_section=column_section)

    expected_layout = perimeter_bar_positions(
        b_mm=column_section.Cw_mm, h_mm=column_section.Cd_mm,
        cover_mm=column_section.Ccover_mm,
        tie_dia_mm=inputs.dowel_tie_dia_mm,
        bar_dia_mm=inputs.dowel_bar_dia_mm,
        count_b_face=inputs.dowel_count_b_face,
        count_h_face=inputs.dowel_count_h_face)

    assert isinstance(plan.dowel, DowelArrayPlan)
    # Pinned to the spec's own worked example (a 2x2-per-face column: 4
    # corner bars, none in the middle) -- found in review (PR #227): a
    # bare self-comparison against expected_layout.bars would stay green
    # even if a future fixture change silently broke the real count.
    assert len(plan.dowel.bars) == 4
    assert len(plan.dowel.bars) == len(expected_layout.bars)
    assert all(bar.is_corner for bar in expected_layout.bars)

    expected_embedment = dowel_embedment(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.dowel_bar_dia_mm, inputs.dowel_ld_multiplier)
    representative = local_dowel_bar_geometry(
        expected_embedment, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm)
    half_u_mm = column_section.Cw_mm / 2.0 - expected_layout.bar_offset_mm
    half_v_mm = column_section.Cd_mm / 2.0 - expected_layout.bar_offset_mm

    for expected_bar, actual_geometry in zip(expected_layout.bars,
                                              plan.dowel.bars):
        _assert_bar_positioned_and_bent_outward(
            expected_bar, actual_geometry, representative, half_u_mm,
            half_v_mm, expected_embedment.b_dowel_mm)


def test_a_face_interior_bar_bends_straight_outward_not_diagonally():
    """R10's other half: a bar in the MIDDLE of a face (not a corner)
    bends perpendicular to that face, never at the corner's 45 degrees.
    ``count_b_face=3`` puts one bar at the midpoint of each b-face, in
    addition to the 4 shared corners."""
    inputs, column_section = _array_inputs()
    inputs = inputs._replace(dowel_count_b_face=3)
    plan = build_footing_plan(inputs, column_section=column_section)

    expected_layout = perimeter_bar_positions(
        b_mm=column_section.Cw_mm, h_mm=column_section.Cd_mm,
        cover_mm=column_section.Ccover_mm,
        tie_dia_mm=inputs.dowel_tie_dia_mm,
        bar_dia_mm=inputs.dowel_bar_dia_mm,
        count_b_face=inputs.dowel_count_b_face,
        count_h_face=inputs.dowel_count_h_face)
    face_bars = [bar for bar in expected_layout.bars if not bar.is_corner]
    assert len(face_bars) == 2  # one per b-face (bottom, top)

    expected_embedment = dowel_embedment(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.dowel_bar_dia_mm, inputs.dowel_ld_multiplier)
    representative = local_dowel_bar_geometry(
        expected_embedment, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm)
    half_u_mm = column_section.Cw_mm / 2.0 - expected_layout.bar_offset_mm
    half_v_mm = column_section.Cd_mm / 2.0 - expected_layout.bar_offset_mm

    for expected_bar, actual_geometry in zip(expected_layout.bars,
                                              plan.dowel.bars):
        _assert_bar_positioned_and_bent_outward(
            expected_bar, actual_geometry, representative, half_u_mm,
            half_v_mm, expected_embedment.b_dowel_mm)

    # The direct statement, on the two face-interior bars specifically:
    # the hook's own u-component is EXACTLY zero (straight along v, not
    # diagonal) -- a 45-degree hook here would be the corner-bar bug this
    # ticket exists to prevent.
    for bar in face_bars:
        geometry = plan.dowel.bars[bar.index]
        hook_dx = (geometry.bottom_hook.start.x_mm
                  - geometry.bottom_hook.end.x_mm)
        assert hook_dx == pytest.approx(0.0, abs=1e-9)


@pytest.mark.parametrize("missing_field", [
    "column_section", "Cw_mm", "Cd_mm", "Ccover_mm",
    "dowel_count_b_face", "dowel_count_h_face", "dowel_tie_dia_mm"])
def test_the_dowel_array_requires_every_one_of_its_own_gating_inputs(
        missing_field):
    """Missing ANY single one of the array's four conceptual gating
    inputs -- column_section as a whole (or one of its own three
    sub-fields, seven `is not None` checks total, found miscounted as
    "five"/"six" in review, PR #227) plus dowel_count_b_face/dowel_count_
    h_face/dowel_tie_dia_mm -- must fall back to the single-bar plan,
    never a partial or guessed array. dowel_tie_dia_mm is the field found
    missing from this guard in review (PR #225): it is an independently
    opt-in #203 field that can legitimately be None while the other
    array inputs are set, and perimeter_bar_positions itself still
    requires it as tie_dia_mm -- omitting it from the guard previously
    produced a bare TypeError instead of this fallback."""
    inputs, column_section = _array_inputs()

    if missing_field == "column_section":
        column_section = None
    elif missing_field in ("Cw_mm", "Cd_mm", "Ccover_mm"):
        column_section = column_section._replace(**{missing_field: None})
    else:
        inputs = inputs._replace(**{missing_field: None})

    plan = build_footing_plan(inputs, column_section=column_section)
    assert len(plan.dowel.bars) == 1


def test_a_column_section_too_small_for_the_array_raises_a_footing_error():
    """#222 (PR #225 review): perimeter_bar_positions' own ValueError
    (section too small to fit a dowel at cover+tie+half-bar) must surface
    as a footing-domain error, the same wrap-and-relabel pattern
    footing_dowel_ties.DowelTieRunTooShortError already establishes for a
    reused function's own ValueError -- never a bare ValueError in
    column-cross-section wording leaking out of a footing module."""
    inputs, _ = _array_inputs()
    tiny_column = DowelColumnSection(Cw_mm=10.0, Cd_mm=10.0, Ccover_mm=40.0)
    with pytest.raises(DowelArrayLayoutError):
        build_footing_plan(inputs, column_section=tiny_column)


# --------------------------------------------------------------------- #
# Issue #230 -- a footing whose column-face clear offset leaves less room
# than the LD-driven b_dowel hook produces a hook that lands past the
# footing's own plan edge on the narrower axis. Hand-computed by this
# ticket's own investigation: a 400x400 column, footing_thickness=450,
# bottom_cover=50, mesh dia 15.9mm both directions, dowel bar dia 15.9mm,
# dowel_ld_multiplier=40 (the tool's own default), x_offset=300/
# y_offset=150 (also the tool's own defaults) -> a=1000mm, b=700mm ->
# a v-face bar's hook (far end y = -411.85mm) lands past half_b=350mm,
# while a u-face bar's hook (far end x = 411.85mm) stays inside
# half_a=500mm -- confirms this is Sec 8's own formula colliding with a
# small edge offset, not a placement/geometry bug (the vertical leg still
# lands exactly at footing_thickness, per test_footing_dowels.py).

def _small_edge_offset_inputs():
    inputs = _inputs(
        a_mm=1000.0, b_mm=700.0, x_offset_mm=300.0, y_offset_mm=150.0,
        mesh_bar_x_dia_mm=15.9, mesh_bar_y_dia_mm=15.9,
        dowel_bar_dia_mm=15.9, dowel_ld_multiplier=40.0,
        dowel_tie_dia_mm=8.0, dowel_count_b_face=3, dowel_count_h_face=3)
    column_section = DowelColumnSection(
        Cw_mm=400.0, Cd_mm=400.0, Ccover_mm=40.0)
    return inputs, column_section


def test_a_small_column_face_clear_offset_produces_an_overshoot_warning():
    inputs, column_section = _small_edge_offset_inputs()
    plan = build_footing_plan(inputs, column_section=column_section)

    assert plan.dowel.overshoot_bar_indices
    for index in plan.dowel.overshoot_bar_indices:
        bar = plan.dowel.bars[index]
        assert (abs(bar.bottom_hook.start.x_mm) > inputs.a_mm / 2.0
                or abs(bar.bottom_hook.start.y_mm) > inputs.b_mm / 2.0)


def test_the_vertical_leg_still_lands_exactly_at_the_footing_top_even_when_the_hook_overshoots():
    """The exact claim in issue #230 that needed checking against real
    numbers: the hook overshooting the plan edge must NOT also mean the
    vertical leg overshoots the footing's own top face -- it is fixed by
    a separate, unaffected identity (bend_z + a_dowel == footing_
    thickness_mm, see footing_dowels.positioned_dowel_bar_geometry)."""
    inputs, column_section = _small_edge_offset_inputs()
    plan = build_footing_plan(inputs, column_section=column_section)

    assert plan.dowel.overshoot_bar_indices  # the fixture DOES overshoot
    for bar in plan.dowel.bars:
        assert bar.vertical.end.z_mm == pytest.approx(
            inputs.footing_thickness_mm)


def test_a_footing_large_enough_for_the_hook_has_no_overshoot():
    """A more modest dowel bar/LD multiplier on the SAME 1800x1200 footing
    stays entirely inside the plan edge -- the warning is conditional on
    the real numbers, not always on (contrast with ``_array_inputs``'s own
    dowel_bar_dia_mm=25/dowel_ld_multiplier=55, which DOES overshoot on
    this footing, per the next test)."""
    inputs, column_section = _array_inputs()
    inputs = inputs._replace(dowel_bar_dia_mm=16.0, dowel_ld_multiplier=40.0)
    plan = build_footing_plan(inputs, column_section=column_section)
    assert plan.dowel.overshoot_bar_indices == []


def test_array_inputs_fixtures_own_large_ld_multiplier_does_overshoot():
    """The reverse check on the SAME footing: ``_array_inputs``' own
    dowel_bar_dia_mm=25/dowel_ld_multiplier=55 (LD=1375mm) produces a
    b_dowel of 1128mm on a 1800x1200 footing with a 450x600 column --
    large enough to land past the plan edge even on this bigger footing,
    confirming the warning genuinely depends on the LD/offset combination
    rather than being a fixed pass/fail."""
    inputs, column_section = _array_inputs()
    plan = build_footing_plan(inputs, column_section=column_section)
    assert plan.dowel.overshoot_bar_indices != []


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


def test_the_plan_defaults_dowel_ties_loop_to_none_with_no_bend_diameter():
    """#242: predates-#242 callers (dowel_tie_dia_mm/dowel_tie_spacing_mm
    supplied, but no dowel_tie_bend_diameter_mm) keep building a
    ladder-only DowelTiePlan unchanged."""
    inputs, column_section = _array_inputs()
    inputs = inputs._replace(dowel_tie_spacing_mm=100.0)
    plan = build_footing_plan(inputs, column_section=column_section)

    assert plan.dowel_ties is not None
    assert plan.dowel_ties.loop is None


def test_supplying_a_bend_diameter_over_a_real_array_builds_the_loop_matching_the_core_call():
    """The composing module must be the ONE place ``footing_dowel_ties.
    dowel_tie_loop_mm`` is called from -- so its output must match calling
    it directly with the SAME dowel bars/inputs (Sec 4's own rule)."""
    from rft.core.footing_dowel_ties import dowel_tie_loop_mm

    inputs, column_section = _array_inputs()
    inputs = inputs._replace(dowel_tie_spacing_mm=100.0)
    plan = build_footing_plan(
        inputs, column_section=column_section,
        dowel_tie_bend_diameter_mm=60.0)

    assert plan.dowel_ties.loop is not None
    expected_loop = dowel_tie_loop_mm(
        plan.dowel.bars, inputs.dowel_tie_dia_mm, inputs.dowel_bar_dia_mm,
        60.0)
    assert plan.dowel_ties.loop == expected_loop


def test_a_single_representative_dowel_bar_keeps_the_loop_none_even_with_a_bend_diameter():
    """No real array (no column_section/count fields) -- ``dowel.bars``
    still holds the single-representative-bar fallback, which
    ``dowel_tie_loop_mm`` itself refuses (fewer than 2 bars). The plan
    must not raise -- it degrades to ``loop=None``, the SAME graceful
    fallback every other opt-in field in this plan already uses."""
    inputs = _inputs(
        dowel_bar_dia_mm=16.0, dowel_ld_multiplier=40.0,
        dowel_tie_dia_mm=8.0, dowel_tie_spacing_mm=100.0)
    plan = build_footing_plan(inputs, dowel_tie_bend_diameter_mm=60.0)

    assert len(plan.dowel.bars) == 1
    assert plan.dowel_ties.loop is None


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
