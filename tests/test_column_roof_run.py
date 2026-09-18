# -*- coding: utf-8 -*-
"""Issue #167 -- ``rft.core.column_roof_run.nearest_crossing_mm``, pure.

A 5000 x 6000 mm rectangular slab boundary, column at plan centre (2500,
3000), matches the shape of R42's live probe well enough to exercise the
same four directions without claiming to reproduce its exact numbers
(the live column sits off-centre; this fixture is a clean rectangle).
"""

import pytest

from rft.core.column_roof_run import nearest_crossing_mm

#: A closed rectangle, 0..5000 in X, 0..6000 in Y, as a flat segment list --
#: exactly what the adapter is expected to hand this function after reading
#: every edge out of every ``CurveLoop``.
RECTANGLE_MM = [
    ((0.0, 0.0), (5000.0, 0.0)),
    ((5000.0, 0.0), (5000.0, 6000.0)),
    ((5000.0, 6000.0), (0.0, 6000.0)),
    ((0.0, 6000.0), (0.0, 0.0)),
]


def test_the_nearest_edge_wins_in_every_axis_direction():
    origin = (2500.0, 3000.0)
    assert nearest_crossing_mm(origin, (1.0, 0.0), RECTANGLE_MM) == \
        pytest.approx(2500.0)
    assert nearest_crossing_mm(origin, (-1.0, 0.0), RECTANGLE_MM) == \
        pytest.approx(2500.0)
    assert nearest_crossing_mm(origin, (0.0, 1.0), RECTANGLE_MM) == \
        pytest.approx(3000.0)
    assert nearest_crossing_mm(origin, (0.0, -1.0), RECTANGLE_MM) == \
        pytest.approx(3000.0)


def test_an_off_centre_origin_finds_the_NEAREST_edge_not_the_first_listed():
    """The segment list is in a fixed order (bottom, right, top, left); a
    naive "first crossing found" would return whichever edge happens to be
    listed first rather than the nearest one."""
    origin = (500.0, 500.0)
    assert nearest_crossing_mm(origin, (-1.0, 0.0), RECTANGLE_MM) == \
        pytest.approx(500.0)


def test_a_diagonal_probe_still_finds_the_nearest_wall():
    """#103 proved a rotated column's own axes are exact at 45 and 315
    degrees; this is the geometry that claim rests on."""
    origin = (2500.0, 3000.0)
    distance = nearest_crossing_mm(origin, (1.0, 1.0), RECTANGLE_MM)
    # Travels along (1,1)/sqrt(2) until x=5000 (the nearer wall in this
    # fixture): dx=2500, so t = 2500 * sqrt(2).
    assert distance == pytest.approx(2500.0 * 2 ** 0.5)


def test_a_direction_that_never_meets_the_boundary_is_None():
    """A probe fired PARALLEL to a wall it starts on crosses nothing."""
    origin = (0.0, 3000.0)
    assert nearest_crossing_mm(origin, (0.0, 1.0), [RECTANGLE_MM[0]]) is None


def test_every_loop_is_considered_not_only_the_first():
    """R42: "take the loop count seriously" -- an opening's edge must be
    found even when it is not the first segment in the list."""
    hole = ((3000.0, 3000.0), (3000.0, 3100.0))
    segments = [hole] + RECTANGLE_MM
    origin = (2500.0, 3000.0)
    assert nearest_crossing_mm(origin, (1.0, 0.0), segments) == \
        pytest.approx(500.0)


def test_the_direction_need_not_be_a_unit_vector():
    origin = (2500.0, 3000.0)
    assert nearest_crossing_mm(origin, (10.0, 0.0), RECTANGLE_MM) == \
        pytest.approx(2500.0)


def test_the_zero_vector_is_refused_not_silently_returned_as_None():
    with pytest.raises(ValueError):
        nearest_crossing_mm((0.0, 0.0), (0.0, 0.0), RECTANGLE_MM)
