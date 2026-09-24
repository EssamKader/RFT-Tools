# -*- coding: utf-8 -*-
"""Mutation-proving tests for #202's genuinely new math (Essam's velocity
rule 3, per the ticket's own "Test volume rule"): ``a_dowel``, ``b_dowel``
and the ``LD`` comparison. specs/isolated-footing.md Sec 3 (Story 5),
Sec 8.

These assert concrete, hand-computed numbers, the same style
``test_footing_mesh.py`` already uses for #198's formulas, so a mutated
operator (+ for -, a swapped term, a flipped comparison) changes the
expected result and the test fails.
"""

import math

import pytest

from rft.core.footing_dowels import (
    DEFAULT_B_DOWEL_MM,
    a_dowel,
    dowel_embedment,
    dowel_hook_exceeds_footing_edge,
    dowel_outward_direction,
    local_dowel_bar_geometry,
    positioned_dowel_bar_geometry,
)


def test_a_dowel_matches_the_spec_formula_by_hand():
    # footing_thickness=450, bottom_cover=50, mesh_bar_x_dia=16,
    # mesh_bar_y_dia=12 -> a_dowel = 450 - 50 - 16 - 12 = 372.
    assert a_dowel(450.0, 50.0, 16.0, 12.0) == pytest.approx(372.0)


def test_a_dowel_a_different_footing_still_matches_by_hand():
    # thickness=600, bottom_cover=75, dia_x=20, dia_y=16
    # -> a_dowel = 600 - 75 - 20 - 16 = 489.
    assert a_dowel(600.0, 75.0, 20.0, 16.0) == pytest.approx(489.0)


def test_a_dowel_subtracts_both_mesh_diameters_not_just_one():
    """Guards against a mutation that drops either ⌀mesh_bar_x or
    ⌀mesh_bar_y from the subtraction -- independently perturbing each
    diameter must change the result by exactly that diameter's delta.
    """
    base = a_dowel(450.0, 50.0, 16.0, 12.0)
    only_x_changed = a_dowel(450.0, 50.0, 20.0, 12.0)
    only_y_changed = a_dowel(450.0, 50.0, 16.0, 20.0)
    assert base - only_x_changed == pytest.approx(4.0)
    assert base - only_y_changed == pytest.approx(8.0)


def test_ld_within_default_embedment_keeps_a_dowel_and_default_b_dowel():
    # a_dowel = 450-50-16-12 = 372; default b_dowel = 200 -> threshold 572.
    # db=16, ld_multiplier=30 -> LD = 480 <= 572 -> keep default.
    result = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    assert result.a_dowel_mm == pytest.approx(372.0)
    assert result.ld_mm == pytest.approx(480.0)
    assert result.b_dowel_mm == pytest.approx(DEFAULT_B_DOWEL_MM)


def test_ld_exactly_at_the_threshold_still_keeps_the_default():
    # threshold = a_dowel + 200 = 572 exactly; LD == threshold -> spec's
    # own "LD <= a_dowel + b_dowel" wording includes equality on the
    # "keep default" side (no R2-style gap here -- see the module
    # docstring).
    result = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=20.0, ld_multiplier=28.6)
    assert result.ld_mm == pytest.approx(572.0)
    assert result.b_dowel_mm == pytest.approx(DEFAULT_B_DOWEL_MM)


def test_ld_over_the_threshold_increases_the_hook_to_ld_minus_a_dowel():
    # a_dowel = 372; db=25, ld_multiplier=60 -> LD = 1500 > 572
    # -> b_dowel = 1500 - 372 = 1128.
    result = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=25.0, ld_multiplier=60.0)
    assert result.ld_mm == pytest.approx(1500.0)
    assert result.b_dowel_mm == pytest.approx(1128.0)
    assert result.b_dowel_mm != pytest.approx(DEFAULT_B_DOWEL_MM)


def test_ld_over_threshold_result_still_sums_to_ld_with_a_dowel():
    """The whole point of the upgrade: once triggered, a_dowel + b_dowel
    must equal LD exactly (Sec 8's own "b_dowel = LD - a_dowel"), not some
    other split."""
    result = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=32.0, ld_multiplier=55.0)
    assert result.a_dowel_mm + result.b_dowel_mm == pytest.approx(
        result.ld_mm)


def test_a_custom_b_dowel_default_shifts_the_comparison_threshold():
    """The 200mm default is Sec 8's OWN default, not a hardcoded
    constant -- a caller may supply a different one and the comparison
    threshold moves with it."""
    result = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0, b_dowel_default_mm=50.0)
    # a_dowel=372, LD=480 -> threshold with the custom default is 422,
    # and 480 > 422 now triggers the upgrade where the 200mm default
    # (threshold 572) would not have.
    assert result.b_dowel_mm == pytest.approx(480.0 - 372.0)


def test_local_dowel_bar_geometry_bend_sits_on_top_of_the_bottom_mesh():
    """Per #201's own review lesson: check the actual numeric Z-position
    against a hand-computed expectation, not just that a function ran.

    bottom_cover=50, mesh_bar_x_dia=16, mesh_bar_y_dia=12 -> the bend
    corner (top of the y-bar, per footing_mesh.local_mesh_bar_endpoints's
    own datum) sits at z = 50 + 16 + 12 = 78.
    """
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    geometry = local_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)

    assert geometry.bottom_hook.end.z_mm == pytest.approx(78.0)
    assert geometry.vertical.start.z_mm == pytest.approx(78.0)


def test_local_dowel_bar_geometry_vertical_leg_top_is_top_of_footing():
    """a_dowel is measured so the vertical leg's top lands exactly at the
    footing's own top face (footing_thickness): 78 + 372 = 450.
    """
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    geometry = local_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)

    assert geometry.vertical.end.z_mm == pytest.approx(450.0)


def test_local_dowel_bar_geometry_hook_leg_length_matches_b_dowel():
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=32.0, ld_multiplier=55.0)
    geometry = local_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)

    hook_length = abs(
        geometry.bottom_hook.start.x_mm - geometry.bottom_hook.end.x_mm)
    assert hook_length == pytest.approx(embedment.b_dowel_mm)


def test_local_dowel_bar_geometry_is_centred_on_the_footing_plan_centroid():
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    geometry = local_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)

    assert geometry.vertical.start.x_mm == pytest.approx(0.0)
    assert geometry.vertical.start.y_mm == pytest.approx(0.0)
    assert geometry.vertical.end.x_mm == pytest.approx(0.0)
    assert geometry.vertical.end.y_mm == pytest.approx(0.0)
    assert geometry.bottom_hook.end.x_mm == pytest.approx(0.0)


# --------------------------------------------------------------------- #
# R10 (docs/footing/spec-amendments.md) -- dowel_outward_direction:
# corner bars bend 45 degrees diagonal, face bars bend straight out
# perpendicular to their own face, never toward the column centroid.

HALF_U_MM, HALF_V_MM = 150.0, 300.0


def test_a_corner_bar_bends_along_the_45_degree_diagonal():
    direction_u, direction_v = dowel_outward_direction(
        HALF_U_MM, HALF_V_MM, HALF_U_MM, HALF_V_MM, is_corner=True)
    assert direction_u == pytest.approx(1.0 / math.sqrt(2.0))
    assert direction_v == pytest.approx(1.0 / math.sqrt(2.0))
    # A unit vector -- CreateFromCurves' norm argument, like every other
    # direction this module hands to the Revit adapter.
    assert math.hypot(direction_u, direction_v) == pytest.approx(1.0)


def test_all_four_corners_bend_outward_never_toward_the_centroid():
    """The direct statement of R10's own finding: every corner's hook
    direction must point AWAY from (0, 0), the column centroid -- a dot
    product with the corner's own position must be positive."""
    for sign_u in (-1.0, 1.0):
        for sign_v in (-1.0, 1.0):
            u_mm, v_mm = sign_u * HALF_U_MM, sign_v * HALF_V_MM
            direction_u, direction_v = dowel_outward_direction(
                u_mm, v_mm, HALF_U_MM, HALF_V_MM, is_corner=True)
            dot_with_position = (direction_u * u_mm) + (direction_v * v_mm)
            assert dot_with_position > 0.0


def test_a_bottom_face_bar_bends_straight_down_v_not_diagonally():
    """v = -half_v (the bottom face), u strictly interior -- must bend
    along (0, -1) ONLY, never picking up a u-component the way a corner
    bar's 45-degree diagonal would."""
    direction_u, direction_v = dowel_outward_direction(
        0.0, -HALF_V_MM, HALF_U_MM, HALF_V_MM, is_corner=False)
    assert direction_u == pytest.approx(0.0)
    assert direction_v == pytest.approx(-1.0)


def test_a_right_face_bar_bends_straight_out_u_not_toward_the_column():
    """u = +half_u (the right face), v strictly interior -- the bug R10
    fixes: the OLD fixed +X direction happened to be correct for THIS
    one face by coincidence; every other face needs its own direction."""
    direction_u, direction_v = dowel_outward_direction(
        HALF_U_MM, 0.0, HALF_U_MM, HALF_V_MM, is_corner=False)
    assert direction_u == pytest.approx(1.0)
    assert direction_v == pytest.approx(0.0)


def test_a_left_face_bar_bends_away_from_the_column_not_into_it():
    """The exact scenario Essam's screenshot showed wrong: a bar on the
    LEFT face (u = -half_u) must bend further NEGATIVE (away), not
    toward +u (back into the column's own core)."""
    direction_u, direction_v = dowel_outward_direction(
        -HALF_U_MM, 0.0, HALF_U_MM, HALF_V_MM, is_corner=False)
    assert direction_u == pytest.approx(-1.0)
    assert direction_v == pytest.approx(0.0)


def test_a_position_matching_neither_face_nor_corner_refuses():
    """A defensive guard, not a reachable production path -- a bar this
    module is handed must always be a genuine perimeter_bar_positions
    output (on a face or a corner); anything else is refused rather than
    given an arbitrary direction."""
    with pytest.raises(ValueError):
        dowel_outward_direction(10.0, 10.0, HALF_U_MM, HALF_V_MM,
                                is_corner=False)


def test_positioned_dowel_bar_geometry_places_the_bend_at_u_v():
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    geometry = positioned_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, u_mm=92.0, v_mm=-242.0,
        direction_u=0.0, direction_v=-1.0)

    assert geometry.vertical.start.x_mm == pytest.approx(92.0)
    assert geometry.vertical.start.y_mm == pytest.approx(-242.0)
    assert geometry.vertical.end.x_mm == pytest.approx(92.0)
    assert geometry.vertical.end.y_mm == pytest.approx(-242.0)
    assert geometry.bottom_hook.end.x_mm == pytest.approx(92.0)
    assert geometry.bottom_hook.end.y_mm == pytest.approx(-242.0)


def test_positioned_dowel_bar_geometry_bends_the_hook_along_direction():
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    geometry = positioned_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, u_mm=92.0, v_mm=-242.0,
        direction_u=0.0, direction_v=-1.0)

    assert geometry.bottom_hook.start.x_mm == pytest.approx(92.0)
    assert geometry.bottom_hook.start.y_mm == pytest.approx(
        -242.0 - embedment.b_dowel_mm)


# --------------------------------------------------------------------- #
# Issue #230 -- dowel_hook_exceeds_footing_edge: Sec 8's own b_dowel
# formula has no clamp against the footing's own plan size, so a hook far
# end can land outside the footing's own plan edge for realistic inputs.

def test_a_hook_far_end_inside_both_half_extents_does_not_exceed():
    assert not dowel_hook_exceeds_footing_edge(
        hook_far_end_x_mm=400.0, hook_far_end_y_mm=300.0,
        half_a_mm=500.0, half_b_mm=350.0)


def test_a_hook_far_end_past_the_x_half_extent_exceeds():
    assert dowel_hook_exceeds_footing_edge(
        hook_far_end_x_mm=500.1, hook_far_end_y_mm=0.0,
        half_a_mm=500.0, half_b_mm=350.0)


def test_a_hook_far_end_past_the_y_half_extent_exceeds():
    """Confirms this checks BOTH axes independently -- x well inside,
    y past its own half-extent must still exceed (found in this ticket's
    own hand-computation against the UI's own default offsets: a 400x400
    column with y_offset=150mm produces exactly this asymmetric case)."""
    assert dowel_hook_exceeds_footing_edge(
        hook_far_end_x_mm=0.0, hook_far_end_y_mm=411.85,
        half_a_mm=500.0, half_b_mm=350.0)


def test_a_hook_far_end_exactly_at_the_edge_does_not_exceed():
    """Read literally: "outside the footing's own plan edge" -- landing
    exactly ON the edge is not yet past it (no R2-style ambiguity here,
    the same "<=" convention dowel_embedment's own threshold uses)."""
    assert not dowel_hook_exceeds_footing_edge(
        hook_far_end_x_mm=500.0, hook_far_end_y_mm=350.0,
        half_a_mm=500.0, half_b_mm=350.0)


def test_a_hook_far_end_on_the_negative_side_is_checked_by_magnitude():
    """Both directions off either half-extent must be caught -- a mutation
    dropping the abs() would silently pass negative overshoot."""
    assert dowel_hook_exceeds_footing_edge(
        hook_far_end_x_mm=-500.1, hook_far_end_y_mm=0.0,
        half_a_mm=500.0, half_b_mm=350.0)


def test_local_dowel_bar_geometry_matches_positioned_at_origin_legacy_direction():
    """local_dowel_bar_geometry is now a thin call into
    positioned_dowel_bar_geometry -- pinned equal, so a future edit to
    either cannot silently drift the fallback single-bar shape #202's own
    tests already trust."""
    embedment = dowel_embedment(
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        db_mm=16.0, ld_multiplier=30.0)
    via_legacy = local_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)
    via_positioned = positioned_dowel_bar_geometry(
        embedment, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, u_mm=0.0, v_mm=0.0,
        direction_u=1.0, direction_v=0.0)
    assert via_legacy == via_positioned
