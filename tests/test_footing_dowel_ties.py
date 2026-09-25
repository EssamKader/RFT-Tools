# -*- coding: utf-8 -*-
"""Thin, focused tests for #203's genuinely new math (Essam's velocity
rule 3, per the ticket's own "Test volume rule"): the starter/end vertical
offset wiring for `dowel_tie`. specs/isolated-footing.md Sec 3 (Story 6),
Sec 9.

Tie SHAPE generation (the closed loop itself) is NOT tested here -- it is
inherited from `rft.core.column_ties`/`column_tie_levels`, already tested
in `tests/test_column_ties.py`/`test_column_tie_levels.py`, and not called
by this ticket at all (see `docs/footing/reuse-audit.md` Sec 1, "Blocked,
not guessed"). Re-testing it here would violate the velocity rule.

#242 adds `dowel_tie_loop_mm` -- the genuinely NEW code is the adapter
that bridges `footing_dowels.DowelBarGeometry` into `resolve_tie`'s own
`layout.bars` shape and the whole-array refusal rules (fewer than 2 bars,
a rectangle too narrow to bend). `resolve_tie`'s own rectangle ARITHMETIC
is not re-tested here (same "Blocked, not guessed" discipline, now that
the array exists) -- these tests only check that this module wires it
correctly and refuses when it should.
"""

import pytest

import rft.core.footing_dowel_ties as footing_dowel_ties
from rft.core.column_ties import KIND_CROSS_TIE
from rft.core.footing_dowel_ties import (
    END_OFFSET_BELOW_TOF_MM,
    START_OFFSET_FROM_FOOTING_BOTTOM_MM,
    DowelTieArrayTooSmallError,
    DowelTieNotBuildableError,
    DowelTieRunTooShortError,
    dowel_tie_ladder,
    dowel_tie_loop_mm,
    dowel_tie_run_mm,
    dowel_ties_mm,
)
from rft.core.footing_dowels import BarEndpoints, DowelBarGeometry, LocalPoint


def _bar_at(u_mm, v_mm):
    """A minimal `DowelBarGeometry` whose own plan position (`vertical.
    start`) is `(u_mm, v_mm)` -- the only field `dowel_tie_loop_mm` reads.
    `bottom_hook`/the rest of `vertical` are never read by this function,
    so they are filled with harmless placeholder points.
    """
    bend = LocalPoint(u_mm, v_mm, 0.0)
    return DowelBarGeometry(
        bottom_hook=BarEndpoints(start=bend, end=bend),
        vertical=BarEndpoints(start=bend, end=bend))


def test_starter_tie_is_50mm_from_the_bottom_of_the_footing():
    run = dowel_tie_run_mm(450.0)
    assert run.start_z_mm == pytest.approx(50.0)
    assert run.start_z_mm == pytest.approx(START_OFFSET_FROM_FOOTING_BOTTOM_MM)


def test_end_tie_is_50mm_below_top_of_footing():
    # T.O.F. == footing_thickness_mm (footing-local, bottom face at z=0).
    run = dowel_tie_run_mm(450.0)
    assert run.end_z_mm == pytest.approx(450.0 - 50.0)
    assert run.end_z_mm == pytest.approx(
        450.0 - END_OFFSET_BELOW_TOF_MM)


def test_end_tie_offset_tracks_a_different_footing_thickness():
    run = dowel_tie_run_mm(900.0)
    assert run.end_z_mm == pytest.approx(850.0)


def test_a_footing_too_thin_for_both_offsets_refuses_rather_than_guesses():
    # start=50, end=90 (thickness=140) -- crosses (50 >= 90 is false here,
    # so use a genuinely-crossing case: thickness=90 -> end=40 < start=50).
    with pytest.raises(DowelTieRunTooShortError):
        dowel_tie_run_mm(90.0)


def test_ladder_first_level_sits_exactly_at_the_starter_offset():
    ladder = dowel_tie_ladder(450.0, tie_spacing_mm=100.0)
    assert ladder.levels[0].z_mm == pytest.approx(50.0)


def test_ladder_last_level_sits_exactly_at_the_end_offset():
    ladder = dowel_tie_ladder(450.0, tie_spacing_mm=100.0)
    assert ladder.levels[-1].z_mm == pytest.approx(400.0)


def test_ladder_never_steps_further_apart_than_the_user_spacing():
    """Sec 9: spacing is a direct user input. Every consecutive pair of
    levels must be at or under it -- never over, whatever the reused
    zone-based ladder's equal-division rounding does in the middle."""
    ladder = dowel_tie_ladder(733.0, tie_spacing_mm=125.0)
    zs = [level.z_mm for level in ladder.levels]
    for lower, upper in zip(zs, zs[1:]):
        assert upper - lower <= 125.0 + 1.0e-6


def test_ladder_run_matches_dowel_tie_run_mm():
    ladder = dowel_tie_ladder(600.0, tie_spacing_mm=150.0)
    run = dowel_tie_run_mm(600.0)
    assert ladder.run == run


def test_ladder_reports_the_spacing_it_was_given():
    ladder = dowel_tie_ladder(600.0, tie_spacing_mm=150.0)
    assert ladder.spacing_mm == pytest.approx(150.0)


def test_no_default_spacing_is_ever_assumed():
    """Sec 9: tie diameter and spacing are direct user inputs, with no
    default -- omitting spacing must refuse, never silently pick one."""
    with pytest.raises(ValueError):
        dowel_tie_ladder(450.0, tie_spacing_mm=None)


def test_asymmetric_offsets_refuse_rather_than_silently_misplace_the_end_tie(
        monkeypatch):
    """The `tie_levels` reuse only works because Sec 9's own start/end
    offsets are the same 50mm value. If a future amendment ever makes them
    differ, this must refuse loudly rather than keep calling `tie_levels`
    with only one of the two offsets."""
    monkeypatch.setattr(
        footing_dowel_ties, "END_OFFSET_BELOW_TOF_MM", 75.0)
    with pytest.raises(NotImplementedError):
        dowel_tie_ladder(450.0, tie_spacing_mm=100.0)


def test_a_run_too_short_for_even_one_spacing_step_refuses():
    # start=50, end=100 (thickness=150) -> clear_height=50, which is
    # shorter than 2 * spacing (200) -- tie_levels' own zone model has no
    # middle zone here, surfaced as the SAME DowelTieRunTooShortError this
    # module raises for its own too-short check.
    with pytest.raises(DowelTieRunTooShortError):
        dowel_tie_ladder(150.0, tie_spacing_mm=100.0)


# --------------------------------------------------------------------- #
# #242 -- dowel_tie_loop_mm: the closed-loop rectangle wrapping the whole
# dowel array.


def test_fewer_than_two_bars_refuses_rather_than_guesses():
    with pytest.raises(DowelTieArrayTooSmallError):
        dowel_tie_loop_mm(
            [_bar_at(0.0, 0.0)], tie_dia_mm=8.0, bar_dia_mm=16.0,
            bend_diameter_mm=60.0)


def test_zero_bars_refuses_too():
    with pytest.raises(DowelTieArrayTooSmallError):
        dowel_tie_loop_mm(
            [], tie_dia_mm=8.0, bar_dia_mm=16.0, bend_diameter_mm=60.0)


def test_a_rectangle_of_four_corner_bars_wraps_all_four_grown_by_half_bar_plus_half_tie():
    # Four bars at the corners of a 300 x 400 mm rectangle (u in
    # +/-150, v in +/-200). grow = bar_dia/2 + tie_dia/2 = 8 + 4 = 12mm,
    # so the loop's own half-dimensions are 150+12=162 and 200+12=212 --
    # the SAME bounding-box-plus-grow arithmetic resolve_tie's own tests
    # already prove; this only checks the adapter reads the right bar
    # positions and returns the right numbers, not resolve_tie's own
    # formula (see this file's own module docstring).
    bars = [
        _bar_at(-150.0, -200.0), _bar_at(150.0, -200.0),
        _bar_at(150.0, 200.0), _bar_at(-150.0, 200.0),
    ]
    loop = dowel_tie_loop_mm(
        bars, tie_dia_mm=8.0, bar_dia_mm=16.0, bend_diameter_mm=60.0)

    expected = set([(-162.0, -212.0), (162.0, -212.0),
                    (162.0, 212.0), (-162.0, 212.0)])
    actual = set((round(c.x_mm, 6), round(c.y_mm, 6)) for c in loop.corners)
    assert actual == expected
    assert len(loop.corners) == 4


def test_bar_order_does_not_matter_only_the_bounding_box_does():
    bars_forward = [
        _bar_at(-150.0, -200.0), _bar_at(150.0, -200.0),
        _bar_at(150.0, 200.0), _bar_at(-150.0, 200.0),
    ]
    bars_shuffled = [bars_forward[2], bars_forward[0],
                     bars_forward[3], bars_forward[1]]
    loop_a = dowel_tie_loop_mm(
        bars_forward, tie_dia_mm=8.0, bar_dia_mm=16.0, bend_diameter_mm=60.0)
    loop_b = dowel_tie_loop_mm(
        bars_shuffled, tie_dia_mm=8.0, bar_dia_mm=16.0, bend_diameter_mm=60.0)
    assert set(loop_a.corners) == set(loop_b.corners)


def test_a_rectangle_too_narrow_to_bend_refuses_rather_than_placing_a_cross_tie():
    # Two bars only 10mm apart on the v axis -> narrow dimension well
    # below bend_diameter + tie_diameter -- resolve_tie would normally
    # degrade to a cross-tie (A1), which this module refuses for a
    # whole-array loop (see DowelTieNotBuildableError's own docstring).
    bars = [_bar_at(0.0, 0.0), _bar_at(10.0, 0.0)]
    with pytest.raises(DowelTieNotBuildableError):
        dowel_tie_loop_mm(
            bars, tie_dia_mm=8.0, bar_dia_mm=16.0, bend_diameter_mm=60.0)


# --------------------------------------------------------------------- #
# #247 (R15) -- dowel_ties_mm: engineer-stated inner ties (crossties),
# additive to the #242 whole-array outer loop. Reuses column_ties.
# parse_tie_subsets/resolve_ties unchanged (tested in test_column_ties.py);
# these tests only check this module's own wiring: empty text keeps #242
# behaviour unchanged, a valid subset returns one resolved inner tie
# alongside the outer loop, and an invalid subset's ValueError propagates.

_FOUR_CORNER_BARS = [
    _bar_at(-150.0, -200.0), _bar_at(150.0, -200.0),
    _bar_at(150.0, 200.0), _bar_at(-150.0, 200.0),
]


def test_no_subsets_text_returns_the_outer_loop_only_unchanged_from_242():
    for empty in (None, ""):
        ties = dowel_ties_mm(
            _FOUR_CORNER_BARS, empty, tie_dia_mm=8.0, bar_dia_mm=16.0,
            bend_diameter_mm=60.0)
        expected_loop = dowel_tie_loop_mm(
            _FOUR_CORNER_BARS, tie_dia_mm=8.0, bar_dia_mm=16.0,
            bend_diameter_mm=60.0)
        assert ties.outer_loop == expected_loop
        assert ties.inner_ties == tuple()


def test_blank_and_comment_only_text_is_also_no_inner_ties():
    ties = dowel_ties_mm(
        _FOUR_CORNER_BARS, "\n# just a comment\n\n",
        tie_dia_mm=8.0, bar_dia_mm=16.0, bend_diameter_mm=60.0)
    assert ties.inner_ties == tuple()


def test_a_two_bar_subset_returns_one_cross_tie_alongside_the_outer_loop():
    # Bars 0 and 1 share v=-200 -- the "opposite bars on one face" shape
    # the UI's own help text describes ("1 6" is a cross-tie), which
    # degrades to KIND_CROSS_TIE under A1 (see this module's own "Inner
    # ties" docstring section for why a diagonal 2-bar subset would NOT).
    ties = dowel_ties_mm(
        _FOUR_CORNER_BARS, "0 1", tie_dia_mm=8.0, bar_dia_mm=16.0,
        bend_diameter_mm=60.0)
    assert ties.outer_loop is not None
    assert len(ties.inner_ties) == 1
    inner = ties.inner_ties[0]
    assert inner.kind == KIND_CROSS_TIE
    actual = set((round(c.x_mm, 6), round(c.y_mm, 6)) for c in inner.corners)
    assert actual == set([(-150.0, -200.0), (150.0, -200.0)])


def test_multiple_lines_return_multiple_inner_ties_in_order():
    ties = dowel_ties_mm(
        _FOUR_CORNER_BARS, "0 1\n1 2", tie_dia_mm=8.0, bar_dia_mm=16.0,
        bend_diameter_mm=60.0)
    assert len(ties.inner_ties) == 2


def test_an_invalid_subset_line_propagates_parse_tie_subsets_own_value_error():
    # A single bar number is not a tie (parse_tie_subsets' own "at least
    # two" rule) -- its ValueError must propagate unmodified, not be
    # swallowed or re-wrapped.
    with pytest.raises(ValueError):
        dowel_ties_mm(
            _FOUR_CORNER_BARS, "5", tie_dia_mm=8.0, bar_dia_mm=16.0,
            bend_diameter_mm=60.0)
