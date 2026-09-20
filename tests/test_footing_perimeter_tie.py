# -*- coding: utf-8 -*-
"""Thin, hand-computed tests for #204's genuinely new math (Essam's
velocity rule 3, per the ticket's own "Test volume rule"): `inner_a`/
`inner_b`/`perimeter_tie_length`, the 12m splice decision, and the
footing-specific plan-corner geometry (new math, since it is not a call
into `rft.core.column_ties` -- see `footing_perimeter_tie`'s own
docstring for why). specs/isolated-footing.md Sec 3 (Story 7), Sec 10.
"""

import pytest

from rft.core.footing_perimeter_tie import (
    PERIMETER_TIE_STOCK_LENGTH_MM,
    PerimeterTieLapRequiredError,
    inner_dimensions_mm,
    local_perimeter_tie_corners_mm,
    perimeter_tie_geometry,
    perimeter_tie_length_mm,
    perimeter_tie_splice,
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
