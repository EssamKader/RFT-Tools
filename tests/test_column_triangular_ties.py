# -*- coding: utf-8 -*-
"""#141 -- triangular ties: a genuine three-sided closed tie through three
bars, in addition to the closed loop and cross-tie #89/R19 already give.

Builds on #140's ``ResolvedTie.vertices`` rather than inventing a second
way to describe a tie's geometry (the ticket's own instruction): a
triangle is dispatched from the SAME ``resolve_tie`` entry point, keyed
off ``TieSubset.triangle``, and comes back as an ordinary ``ResolvedTie``
whose ``kind`` is ``KIND_TRIANGLE`` and whose ``vertices`` are its own
three (grown) corners.

The buildability test is A1 generalised, not replaced -- see
``test_tangent_length_reduces_to_A1_at_90_degrees``, which is the entire
argument (per the ticket's second comment) for using it without a new
citation.
"""

import math

import pytest

from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_ties import (
    KIND_TRIANGLE,
    TieSubset,
    format_tie_subsets,
    is_buildable,
    minimum_buildable_narrow_mm,
    parse_tie_subsets,
    resolve_tie,
    resolve_ties,
    tangent_length_mm,
    tie_report_lines,
)

B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM = 450.0, 600.0, 40.0, 9.5, 15.9
BEND_DIAMETER_MM = 40.0  # 10M StirrupTieBendDiameter, measured live


def layout(count_b=3, count_h=4):
    return perimeter_bar_positions(
        B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM, count_b, count_h)


def triangle_tie(indices, lay=None, bend_diameter_mm=BEND_DIAMETER_MM):
    return resolve_tie(TieSubset(indices, triangle=True), lay or layout(),
                       TIE_DIA_MM, BAR_DIA_MM, bend_diameter_mm)


# --------------------------------------------------------------------- #
# The generalised bend test: A1 stated for any polygon vertex.


def test_tangent_length_reduces_to_A1_at_90_degrees():
    """The whole argument for using the generalised formula without a new
    citation (#141, ticket comment 2): at theta = 90 degrees, twice the
    tangent length plus the tie diameter is EXACTLY today's
    ``minimum_buildable_narrow_mm``.
    """
    bend, tie = 40.0, 9.5
    t = tangent_length_mm(bend, math.radians(90.0))
    assert t == pytest.approx(bend / 2.0)
    assert 2.0 * t + tie == pytest.approx(
        minimum_buildable_narrow_mm(bend, tie))

    bend, tie = 115.0, 19.1
    t = tangent_length_mm(bend, math.radians(90.0))
    assert 2.0 * t + tie == pytest.approx(
        minimum_buildable_narrow_mm(bend, tie))


def test_tangent_length_grows_as_the_angle_sharpens():
    """A sharper corner needs a longer tangent to the same bend -- the
    geometric fact that makes an acute triangle vertex the harder case,
    never the easier one.
    """
    bend = 40.0
    t_90 = tangent_length_mm(bend, math.radians(90.0))
    t_60 = tangent_length_mm(bend, math.radians(60.0))
    t_30 = tangent_length_mm(bend, math.radians(30.0))
    assert t_30 > t_60 > t_90


# --------------------------------------------------------------------- #
# A genuine three-sided closed tie -- not a diamond, not a bounding box.


def test_a_triangle_is_KIND_TRIANGLE_with_three_vertices():
    tie = triangle_tie((0, 1, 9))
    assert tie.kind == KIND_TRIANGLE
    assert len(tie.vertices) == 3
    assert tie.reason == ""


def test_a_triangle_restrains_exactly_its_three_bars():
    """The ticket's own words: 'a triangle restrains the three bars at
    its vertices' -- no more, no fewer, unlike a rectangle's bounding-box
    corner scan which can catch a bar the subset never named.
    """
    tie = triangle_tie((0, 1, 9))
    assert tie.restrained_indices == [0, 1, 9]


def test_a_triangle_needs_exactly_three_bars():
    """Not a bounding box: two bars have no interior angle to bend
    through, and four is a different (unrequested) shape."""
    for bad in ((0, 1), (0, 1, 2, 3)):
        with pytest.raises(ValueError) as caught:
            triangle_tie(bad)
        assert "exactly three" in str(caught.value)


def test_a_repeated_bar_is_refused():
    with pytest.raises(ValueError) as caught:
        triangle_tie((0, 1, 1))
    assert "twice" in str(caught.value)


def test_an_out_of_range_bar_is_refused():
    with pytest.raises(ValueError):
        triangle_tie((0, 1, 99))


def test_collinear_bars_are_refused_not_silently_degenerate():
    """Bars 0, 1, 2 sit on the same face (same v) -- a straight line, not
    a triangle. There is no bisector to offset a vertex along at a
    180-degree angle, so this must raise rather than divide by zero or
    silently draw a spike.
    """
    with pytest.raises(ValueError) as caught:
        triangle_tie((0, 1, 2))
    assert "collinear" in str(caught.value)


def test_the_vertices_are_pushed_outward_along_the_bisector():
    """Per the ticket's geometry: each vertex moves outward from the raw
    bar centre by grow / sin(theta / 2), grow = bar/2 + tie/2. Checked
    against the corner bar (0) of a right-angle-ish triangle, where the
    outward direction is unambiguous (away from the other two bars).
    """
    lay = layout()
    bar0 = lay.bars[0]
    tie = triangle_tie((0, 1, 9), lay)
    grown = tie.vertices[0]
    grow = BAR_DIA_MM / 2.0 + TIE_DIA_MM / 2.0
    moved = math.hypot(grown[0] - bar0.u_mm, grown[1] - bar0.v_mm)
    # The move is at least `grow` (theta <= 180 => 1/sin(theta/2) >= 1) and
    # bounded well short of the column's own half-width, ruling out a sign
    # or axis error that would fling the vertex off the section.
    assert grow <= moved < B_MM


# --------------------------------------------------------------------- #
# On failure, refuse -- do not degrade (ticket comment 2, verbatim).


def test_an_unbuildable_triangle_is_refused_by_name():
    """A huge bend diameter makes the same geometry unbendable -- the same
    trick ``test_column_ties.py`` uses to force A1's rectangle case."""
    with pytest.raises(ValueError) as caught:
        triangle_tie((0, 1, 9), bend_diameter_mm=900.0)
    message = str(caught.value)
    assert "0 1 9" in message
    assert "vertex angle" in message
    assert "degrees" in message
    assert "legs measure" in message
    assert "mm" in message


def test_an_unbuildable_triangle_never_becomes_a_cross_tie_or_anything_else():
    """The ticket's explicit prohibition: no fallback detail, because no
    source has been offered for one. A ValueError is the only outcome --
    there is no ResolvedTie of any KIND to inspect.
    """
    with pytest.raises(ValueError):
        triangle_tie((0, 1, 9), bend_diameter_mm=900.0)
    # (if this constructed a ResolvedTie instead of raising, the test
    # above would already have failed -- this second call documents the
    # intent: nothing recoverable is returned.)


def test_is_buildable_trusts_a_resolved_triangle():
    """Every triangle that survives ``resolve_tie`` is already proven
    buildable -- the refusal happens at construction, exactly like a
    cross-tie's A1 threshold not applying a second time downstream."""
    tie = triangle_tie((0, 1, 9))
    assert is_buildable(tie)


# --------------------------------------------------------------------- #
# Notation: a T-marked line, an unmarked line is unchanged.


def test_a_T_marked_line_parses_as_a_triangle():
    subsets = parse_tie_subsets("T 1 3 5")
    assert len(subsets) == 1
    assert subsets[0].indices == (1, 3, 5)
    assert subsets[0].triangle is True


def test_T_is_case_insensitive():
    assert parse_tie_subsets("t 1 3 5")[0].triangle is True


def test_an_unmarked_line_is_still_a_loop_or_cross_tie():
    subsets = parse_tie_subsets("1 6\n0 1 2 3")
    assert all(s.triangle is False for s in subsets)


def test_a_T_line_still_needs_at_least_two_numbers():
    with pytest.raises(ValueError) as caught:
        parse_tie_subsets("T 5")
    assert "Line 1" in str(caught.value)


def test_triangle_notation_round_trips():
    text = "1 6\nT 1 3 5\n0 1 2 3"
    assert format_tie_subsets(parse_tie_subsets(text)) == text


# --------------------------------------------------------------------- #
# Report: named as a triangle, never printed as a loop.


def test_the_report_names_it_a_triangle_never_a_loop():
    lay = layout()
    ties = resolve_ties([TieSubset((0, 1, 9), triangle=True)], lay,
                        TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    lines = "\n".join(tie_report_lines(ties))
    assert "triangle" in lines
    assert "Tie 0 1 9: triangle" in lines
    assert "closed loop" not in lines.split("Tie 0 1 9")[1]
