# -*- coding: utf-8 -*-
"""Thin, hand-computed tests for #204's genuinely new math (Essam's
velocity rule 3, per the ticket's own "Test volume rule"): `inner_a`/
`inner_b`/`perimeter_tie_length`, the 12m splice decision, and the
footing-specific plan-corner geometry (new math, since it is not a call
into `rft.core.column_ties` -- see `footing_perimeter_tie`'s own
docstring for why). specs/isolated-footing.md Sec 3 (Story 7), Sec 10.

Also covers R4 (vertical starting offset) and R5 (splice cut-length
split), both added to `docs/footing/spec-amendments.md` after #204
merged.
"""

import pytest

from rft.core.footing_perimeter_tie import (
    PERIMETER_TIE_START_OFFSET_ABOVE_BOTTOM_MESH_MM,
    PERIMETER_TIE_STOCK_LENGTH_MM,
    PerimeterTieArcLengthRangeError,
    PerimeterTieBarLengthMismatchError,
    PerimeterTieBarLengthsNotApplicableError,
    PerimeterTieBarLengths,
    PerimeterTieLadderExceedsFootingError,
    PerimeterTieLapRequiredError,
    PerimeterTieSplice,
    PerimeterTieSplitLengthError,
    PerimeterTieSplitNotApplicableError,
    bottom_mesh_top_z_mm,
    inner_dimensions_mm,
    local_perimeter_tie_corners_mm,
    perimeter_tie_bar_lengths_mm,
    perimeter_tie_geometry,
    perimeter_tie_ladder_mm,
    perimeter_tie_length_mm,
    perimeter_tie_point_at_arc_length_mm,
    perimeter_tie_split_bar_points_mm,
    perimeter_tie_splice,
    perimeter_tie_start_z_mm,
    perimeter_tie_unrolled_points_mm,
)


def test_inner_dimensions_offset_inward_by_cover_on_both_axes():
    inner = inner_dimensions_mm(a_mm=1800.0, b_mm=1200.0, cover_mm=50.0)
    assert inner.inner_a_mm == pytest.approx(1700.0)
    assert inner.inner_b_mm == pytest.approx(1100.0)


def test_perimeter_tie_length_is_the_hand_computed_perimeter():
    # 2 * (1700 + 1100) = 5600
    assert perimeter_tie_length_mm(1700.0, 1100.0) == pytest.approx(5600.0)


def test_length_at_or_under_12m_is_one_continuous_bar():
    splice = perimeter_tie_splice(PERIMETER_TIE_STOCK_LENGTH_MM)
    assert splice.bar_count == 1
    assert splice.lap_mm is None
    assert splice.total_length_mm == pytest.approx(
        PERIMETER_TIE_STOCK_LENGTH_MM)


def test_length_just_over_12m_splits_into_two_bars_with_the_given_lap():
    splice = perimeter_tie_splice(
        PERIMETER_TIE_STOCK_LENGTH_MM + 1.0, lap_mm=600.0)
    assert splice.bar_count == 2
    assert splice.lap_mm == pytest.approx(600.0)
    assert splice.total_length_mm == pytest.approx(
        PERIMETER_TIE_STOCK_LENGTH_MM + 1.0 + 600.0)


def test_a_split_without_a_lap_length_refuses_rather_than_guesses():
    with pytest.raises(PerimeterTieLapRequiredError):
        perimeter_tie_splice(PERIMETER_TIE_STOCK_LENGTH_MM + 1.0)


def test_a_split_with_a_non_positive_lap_length_also_refuses():
    with pytest.raises(PerimeterTieLapRequiredError):
        perimeter_tie_splice(PERIMETER_TIE_STOCK_LENGTH_MM + 1.0, lap_mm=0.0)


def test_the_geometry_builder_refuses_the_same_way_end_to_end():
    # a=7000, b=7000, cover=50 -> inner_a=inner_b=6900,
    # length = 2*(6900+6900) = 27600 > 12000 -- needs a lap.
    with pytest.raises(PerimeterTieLapRequiredError):
        perimeter_tie_geometry(a_mm=7000.0, b_mm=7000.0, cover_mm=50.0)


def test_corners_are_centred_on_the_footing_centroid_and_wound_sw_se_ne_nw():
    corners = local_perimeter_tie_corners_mm(inner_a_mm=1700.0, inner_b_mm=1100.0)
    assert len(corners) == 4
    sw, se, ne, nw = corners
    assert sw == pytest.approx((-850.0, -550.0))
    assert se == pytest.approx((850.0, -550.0))
    assert ne == pytest.approx((850.0, 550.0))
    assert nw == pytest.approx((-850.0, 550.0))


def test_the_geometry_builder_carries_everything_the_pieces_would_compute():
    geometry = perimeter_tie_geometry(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0)
    inner = inner_dimensions_mm(1800.0, 1200.0, 50.0)
    length = perimeter_tie_length_mm(inner.inner_a_mm, inner.inner_b_mm)
    splice = perimeter_tie_splice(length)
    corners = local_perimeter_tie_corners_mm(
        inner.inner_a_mm, inner.inner_b_mm)

    assert geometry.inner_a_mm == pytest.approx(inner.inner_a_mm)
    assert geometry.inner_b_mm == pytest.approx(inner.inner_b_mm)
    assert geometry.length_mm == pytest.approx(length)
    assert geometry.splice == splice
    assert geometry.corners == corners


# --- R4: vertical starting offset -------------------------------------

def test_bottom_mesh_top_z_matches_footing_dowels_own_bend_corner_datum():
    # bottom_cover=50, mesh_bar_x_dia=16, mesh_bar_y_dia=12 -> 50+16+12=78,
    # the same hand-computed value footing_dowels' own bend corner uses.
    assert bottom_mesh_top_z_mm(50.0, 16.0, 12.0) == pytest.approx(78.0)


def test_perimeter_tie_start_z_is_250mm_above_the_bottom_mesh():
    # bottom_mesh_top_z = 78 -> start_z = 78 + 250 = 328.
    start_z = perimeter_tie_start_z_mm(50.0, 16.0, 12.0)
    assert start_z == pytest.approx(78.0 + 250.0)
    assert start_z == pytest.approx(
        78.0 + PERIMETER_TIE_START_OFFSET_ABOVE_BOTTOM_MESH_MM)


def test_ladder_first_level_is_the_start_z_and_steps_by_spacing():
    ladder = perimeter_tie_ladder_mm(
        footing_thickness_mm=1500.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        spacing_mm=200.0, quantity=3)
    assert ladder.levels_mm == pytest.approx((328.0, 528.0, 728.0))
    assert ladder.start_z_mm == pytest.approx(328.0)
    assert ladder.spacing_mm == pytest.approx(200.0)


def test_a_single_quantity_ladder_has_just_the_starter_level():
    ladder = perimeter_tie_ladder_mm(
        footing_thickness_mm=1500.0, bottom_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
        spacing_mm=200.0, quantity=1)
    assert ladder.levels_mm == pytest.approx((328.0,))


def test_a_ladder_that_would_exceed_the_footing_refuses():
    # thickness=450: start=328, spacing=200, quantity=3 -> last=728 > 450.
    with pytest.raises(PerimeterTieLadderExceedsFootingError):
        perimeter_tie_ladder_mm(
            footing_thickness_mm=450.0, bottom_cover_mm=50.0,
            mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
            spacing_mm=200.0, quantity=3)


def test_ladder_with_no_spacing_refuses_rather_than_guesses():
    with pytest.raises(ValueError):
        perimeter_tie_ladder_mm(
            footing_thickness_mm=1500.0, bottom_cover_mm=50.0,
            mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
            spacing_mm=None, quantity=3)


def test_ladder_with_no_quantity_refuses_rather_than_guesses():
    with pytest.raises(ValueError):
        perimeter_tie_ladder_mm(
            footing_thickness_mm=1500.0, bottom_cover_mm=50.0,
            mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0,
            spacing_mm=200.0, quantity=None)


# --- R5: splice cut-length split (engineer's own two-field input) -----

def test_matching_bar_lengths_build_the_r5_result():
    splice = perimeter_tie_splice(
        PERIMETER_TIE_STOCK_LENGTH_MM + 1.0, lap_mm=600.0)
    # total = 12000 + 1 + 600 = 12601 -- engineer picks any split, e.g. 7000 + 5601.
    result = perimeter_tie_bar_lengths_mm(splice, 7000.0, 5601.0)
    assert result.first_bar_length_mm == pytest.approx(7000.0)
    assert result.second_bar_length_mm == pytest.approx(5601.0)


def test_bar_lengths_that_do_not_sum_to_the_total_refuse():
    splice = perimeter_tie_splice(
        PERIMETER_TIE_STOCK_LENGTH_MM + 1.0, lap_mm=600.0)
    with pytest.raises(PerimeterTieBarLengthMismatchError):
        perimeter_tie_bar_lengths_mm(splice, 7000.0, 5000.0)


def test_bar_lengths_are_not_applicable_to_a_single_continuous_bar():
    splice = perimeter_tie_splice(PERIMETER_TIE_STOCK_LENGTH_MM)
    with pytest.raises(PerimeterTieBarLengthsNotApplicableError):
        perimeter_tie_bar_lengths_mm(splice, 6000.0, 6000.0)


# --- R14: the split shape's own arc-length unroll ----------------------
#
# Hand-computed on a square inner_a_mm=inner_b_mm=6900.0 rectangle
# (a_mm=b_mm=7000.0, cover_mm=50.0 -- the same fixture the existing
# "geometry builder refuses" test above uses). Corners (SW/SE/NE/NW),
# half_a=half_b=3450.0:
#   SW=(-3450,-3450) s=0        SE=(3450,-3450) s=6900
#   NE=(3450,3450)   s=13800    NW=(-3450,3450) s=20700
#   back to SW               s=27600 (=length_mm)

_SQUARE_CORNERS = local_perimeter_tie_corners_mm(
    inner_a_mm=6900.0, inner_b_mm=6900.0)
_SQUARE_SW, _SQUARE_SE, _SQUARE_NE, _SQUARE_NW = _SQUARE_CORNERS


def test_point_at_arc_length_zero_is_the_fixed_sw_start_corner():
    point = perimeter_tie_point_at_arc_length_mm(
        _SQUARE_CORNERS, 6900.0, 6900.0, 0.0)
    assert point == pytest.approx(_SQUARE_SW)


def test_point_at_arc_length_total_wraps_back_to_the_same_sw_corner():
    point = perimeter_tie_point_at_arc_length_mm(
        _SQUARE_CORNERS, 6900.0, 6900.0, 27600.0)
    assert point == pytest.approx(_SQUARE_SW)


def test_point_at_arc_length_mid_edge_interpolates():
    # s=200 into the first edge (SW->SE, length 6900): 200/6900 of the way.
    point = perimeter_tie_point_at_arc_length_mm(
        _SQUARE_CORNERS, 6900.0, 6900.0, 200.0)
    assert point == pytest.approx((-3450.0 + 200.0, -3450.0))


def test_point_at_arc_length_past_a_later_corner_lands_on_the_next_edge():
    # s=14000: 200mm past NE (s=13800), on the NE->NW edge.
    point = perimeter_tie_point_at_arc_length_mm(
        _SQUARE_CORNERS, 6900.0, 6900.0, 14000.0)
    assert point == pytest.approx((3450.0 - 200.0, 3450.0))


def test_point_at_arc_length_outside_the_single_lap_refuses():
    with pytest.raises(PerimeterTieArcLengthRangeError):
        perimeter_tie_point_at_arc_length_mm(
            _SQUARE_CORNERS, 6900.0, 6900.0, 27601.0)
    with pytest.raises(PerimeterTieArcLengthRangeError):
        perimeter_tie_point_at_arc_length_mm(
            _SQUARE_CORNERS, 6900.0, 6900.0, -1.0)


def _flattened(points):
    # pytest.approx only supports ONE level of nesting -- flatten each
    # (x, y) point pair into a single flat sequence so a list of points
    # compares cleanly against another list of points.
    flat = []
    for point in points:
        flat.append(point[0])
        flat.append(point[1])
    return tuple(flat)


def test_unrolled_points_include_every_interior_corner_in_walking_order():
    # s=0 to s=14000: passes SW(0), SE(6900), NE(13800), ends 200mm past NE.
    points = perimeter_tie_unrolled_points_mm(
        _SQUARE_CORNERS, 6900.0, 6900.0, 0.0, 14000.0)
    assert _flattened(points) == pytest.approx(
        _flattened((_SQUARE_SW, _SQUARE_SE, _SQUARE_NE, (3250.0, 3450.0))))


def test_unrolled_points_end_requires_start_less_than_end():
    with pytest.raises(PerimeterTieArcLengthRangeError):
        perimeter_tie_unrolled_points_mm(
            _SQUARE_CORNERS, 6900.0, 6900.0, 5000.0, 5000.0)


def test_split_bar_points_match_r14s_own_hand_computed_example():
    """a_mm=b_mm=7000, cover_mm=50 -> inner_a=inner_b=6900,
    length_mm=27600 (over the 12m stock length), lap_mm=600.0 ->
    total_length_mm=28200. Engineer types first_bar_length_mm=14000.0,
    second_bar_length_mm=14200.0 (14000 + 14200 = 28200, R5's own sum
    check). Per R14: bar 1 spans s=0..14000, bar 2 spans
    s=(14000-600)=13400..27600.
    """
    geometry = perimeter_tie_geometry(
        a_mm=7000.0, b_mm=7000.0, cover_mm=50.0, lap_mm=600.0)
    assert geometry.splice == PerimeterTieSplice(
        bar_count=2, lap_mm=600.0, total_length_mm=28200.0)

    bar_lengths = perimeter_tie_bar_lengths_mm(
        geometry.splice, first_bar_length_mm=14000.0,
        second_bar_length_mm=14200.0)

    split = perimeter_tie_split_bar_points_mm(geometry, bar_lengths)

    assert _flattened(split.bar1_points) == pytest.approx(
        _flattened((_SQUARE_SW, _SQUARE_SE, _SQUARE_NE, (3250.0, 3450.0))))
    assert _flattened(split.bar2_points) == pytest.approx(
        _flattened(((3450.0, 3050.0), _SQUARE_NE, _SQUARE_NW, _SQUARE_SW)))

    # The two arc-length spans equal each typed cut length exactly (R14's
    # own algebraic check, this module's docstring "The split shape --
    # RESOLVED (R14)"): bar 1's span is first_bar_length_mm, bar 2's span
    # is second_bar_length_mm.
    def _polyline_length(points):
        total = 0.0
        for i in range(len(points) - 1):
            x0, y0 = points[i]
            x1, y1 = points[i + 1]
            total += ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5
        return total

    assert _polyline_length(split.bar1_points) == pytest.approx(14000.0)
    assert _polyline_length(split.bar2_points) == pytest.approx(14200.0)


def test_split_bar_points_refuses_for_a_single_continuous_loop():
    geometry = perimeter_tie_geometry(a_mm=1800.0, b_mm=1200.0, cover_mm=50.0)
    bar_lengths = PerimeterTieBarLengths(
        first_bar_length_mm=1.0, second_bar_length_mm=1.0)
    with pytest.raises(PerimeterTieSplitNotApplicableError):
        perimeter_tie_split_bar_points_mm(geometry, bar_lengths)


def test_split_bar_points_refuses_a_first_bar_shorter_than_the_lap():
    geometry = perimeter_tie_geometry(
        a_mm=7000.0, b_mm=7000.0, cover_mm=50.0, lap_mm=600.0)
    bar_lengths = PerimeterTieBarLengths(
        first_bar_length_mm=500.0, second_bar_length_mm=27700.0)
    with pytest.raises(PerimeterTieSplitLengthError):
        perimeter_tie_split_bar_points_mm(geometry, bar_lengths)


def test_split_bar_points_refuses_a_first_bar_longer_than_the_full_length():
    geometry = perimeter_tie_geometry(
        a_mm=7000.0, b_mm=7000.0, cover_mm=50.0, lap_mm=600.0)
    bar_lengths = PerimeterTieBarLengths(
        first_bar_length_mm=27700.0, second_bar_length_mm=500.0)
    with pytest.raises(PerimeterTieSplitLengthError):
        perimeter_tie_split_bar_points_mm(geometry, bar_lengths)
