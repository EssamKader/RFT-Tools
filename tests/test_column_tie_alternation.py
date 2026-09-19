# -*- coding: utf-8 -*-
"""#195 / R48 -- section 6.3's alternation, BUILT rather than only reported.

Before this, `TieLevel.mirrored` was computed, printed as an `M` in the
report, and read by nobody who built anything. Every tie at every level
was placed identically, hook in the same corner all the way up the column
-- the one thing section 6.3 exists to prevent -- while the report
asserted otherwise.

## The transform, and the one that was measured FAILING

The hook sits where the curve list closes, so moving the starting vertex
one place around the loop moves the hook to the ADJACENT corner. Winding,
corners and order are otherwise untouched.

A **reflection** is the wrong tool, and it was tried first. #78 proved a
reflection gives an adjacent corner -- but for `MoveBarInSet`, a
transform applied to a bar IN a set, which carries the hook with it.
Reflecting the input CURVES reverses the winding, and
`RebarHookOrientation.Left` is defined against each curve's own tangent,
so the hook turns OUTWARD. Measured on a live host: the reflected tie's
tail landed at `v = -351.4` against a 260 mm half-height -- 91 mm into
cover and air, the exact defect #78 recorded for the wrong orientation.
"""

import pytest

from rft.core.column_ties import alternated_vertices


#: Wound anticlockwise from the SW corner, the way
#: `_closed_loop_uv_segments_mm` builds it.
RECTANGLE = ((-185.0, -260.0), (185.0, -260.0), (185.0, 260.0), (-185.0, 260.0))


def test_the_loop_starts_one_corner_later():
    """SW -> SE: the adjacent corner, which is what the owner ruled for.
    A 180 degree move would give NE, the diagonal, and was rejected."""
    assert alternated_vertices(RECTANGLE) == (
        (185.0, -260.0), (185.0, 260.0), (-185.0, 260.0), (-185.0, -260.0))


def test_the_WINDING_is_untouched():
    """The load-bearing property, and the one a reflection breaks.

    Consecutive corners keep their order, so every segment runs the same
    way round the loop as before. `RebarHookOrientation.Left` is defined
    against each curve's own tangent -- reverse the winding and the hook
    turns outward, which was measured landing 91 mm outside the concrete.
    """
    rotated = alternated_vertices(RECTANGLE)
    for i in range(len(RECTANGLE)):
        here = RECTANGLE.index(rotated[i])
        nxt = RECTANGLE.index(rotated[(i + 1) % len(rotated)])
        assert nxt == (here + 1) % len(RECTANGLE), (
            "corner order changed: the winding is no longer the same")


def test_the_polygon_OCCUPIES_THE_SAME_SPACE():
    """An alternated tie wraps the same bars. Anything that moves the
    polygon is a different tie, not an alternated one."""
    assert set(alternated_vertices(RECTANGLE)) == set(RECTANGLE)


def test_a_full_cycle_returns_the_original():
    """Four rotations of a rectangle come back to the start, so levels 0
    and 4 carry the same hook corner -- alternation, not drift."""
    result = RECTANGLE
    for _ in range(len(RECTANGLE)):
        result = alternated_vertices(result)
    assert result == RECTANGLE


def test_TWO_rotations_give_the_DIAGONAL_which_is_why_it_is_only_one():
    """Recorded so the 'one place' is visibly deliberate: rotating twice
    is the diagonal corner the owner rejected on 2026-09-14."""
    twice = alternated_vertices(alternated_vertices(RECTANGLE))
    assert twice[0] == (185.0, 260.0)


def test_an_empty_polygon_is_returned_unchanged_rather_than_raising():
    assert alternated_vertices(()) == tuple()


@pytest.mark.parametrize("vertices", [RECTANGLE, ((0.0, 0.0), (10.0, 0.0))])
def test_the_vertex_COUNT_never_changes(vertices):
    assert len(alternated_vertices(vertices)) == len(vertices)
