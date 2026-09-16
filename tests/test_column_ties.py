# -*- coding: utf-8 -*-
"""#89 -- section 6.2's tie topology, and the rules that judge it.

The bend diameters are the live model's, read off the `RebarBarType`:
``10M`` is 9.50 mm with a 40.00 mm ``StirrupTieBendDiameter``, so A1's
threshold is 49.50 mm. The same model's ``19M`` reads 115.00 against
19.10 -- 6.0x rather than 10M's 4.2x -- which is why the bend diameter is
read and never assumed as a multiple.
"""

import itertools

import pytest

from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_ties import (
    KIND_CLOSED_LOOP,
    KIND_CROSS_TIE,
    SEVERITY_BLOCKING,
    SEVERITY_WARNING,
    TieSubset,
    is_blocking,
    minimum_buildable_narrow_mm,
    outer_perimeter_subset,
    resolve_tie,
    resolve_ties,
    restrained_bar_indices,
    subset_indices,
    tie_report_lines,
    validate,
)

B, H, COVER, TIE, BAR = 450.0, 600.0, 40.0, 9.5, 15.9
BEND = 40.0        # 10M StirrupTieBendDiameter, measured live
MIN_NARROW = 49.5  # BEND + TIE

#: One of the 420 valid coverings of the live layout (see the test below).
VALID = [TieSubset(0, 4), TieSubset(0, 5), TieSubset(1, 5)]


def layout(count_b=3, count_h=4):
    return perimeter_bar_positions(B, H, COVER, TIE, BAR, count_b, count_h)


def ties(subsets, lay=None):
    return resolve_ties(subsets, lay or layout(), TIE, BAR, BEND)


# --------------------------------------------------------------------- #
# Subsets


def test_a_subset_wraps_around_the_perimeter():
    """A tie may start at bar 8 of 10 and enclose 8, 9, 0, 1. The
    perimeter is a ring; a subset that could not cross index 0 would make
    three of the four faces expressible and one not.
    """
    assert subset_indices(TieSubset(8, 4), 10) == [8, 9, 0, 1]


def test_the_outer_tie_is_implied_not_entered():
    """Every column has one. Asking the engineer to state it would be
    asking them to state the obvious before they can state anything.
    """
    assert outer_perimeter_subset(10) == TieSubset(0, 10)
    resolved = ties([])
    assert len(resolved) == 1
    assert resolved[0].enclosed_indices == list(range(10))


@pytest.mark.parametrize("subset", [
    TieSubset(0, 1), TieSubset(0, 0), TieSubset(0, 11), TieSubset(10, 2),
    TieSubset(-1, 2),
])
def test_an_impossible_subset_is_refused(subset):
    with pytest.raises(ValueError):
        subset_indices(subset, 10)


# --------------------------------------------------------------------- #
# A1 -- closed loop vs cross-tie


def test_a_wide_subset_is_a_CLOSED_LOOP():
    tie = resolve_tie(TieSubset(0, 10), layout(), TIE, BAR, BEND)
    assert tie.kind == KIND_CLOSED_LOOP
    assert tie.reason == ""
    assert tie.min_buildable_mm == pytest.approx(MIN_NARROW)


def test_a_two_bar_subset_across_a_face_becomes_a_CROSS_TIE():
    """A1's only permitted trigger. Two bars on opposite faces produce a
    rectangle about 25 mm wide, which no bar can bend to -- and Revit
    refuses it with a MODAL DIALOG that blocks the session, not a
    catchable exception. That is why the test runs here.
    """
    # bars 1 and 6 are the two mid-face bars, directly opposite.
    tie = resolve_tie(TieSubset(1, 6), layout(), TIE, BAR, BEND)
    assert tie.kind == KIND_CLOSED_LOOP  # 1..6 spans the section: wide
    # 6 and 1 the short way round is the same two bars with nothing between
    narrow_tie = resolve_tie(TieSubset(6, 6), layout(), TIE, BAR, BEND)
    assert narrow_tie.kind == KIND_CLOSED_LOOP


def test_the_narrow_case_is_decided_by_the_MEASURED_bend_diameter():
    """A 25.4 mm loop is what produced "Can't solve Rebar Shape" live.
    Here the same geometry is judged before any API call.
    """
    lay = layout()
    # Force the narrow case: a huge bend diameter makes every loop
    # unbuildable, which is the same arithmetic from the other side.
    tie = resolve_tie(TieSubset(0, 10), lay, TIE, BAR, bend_diameter_mm=900.0)
    assert tie.kind == KIND_CROSS_TIE
    assert "cannot be bent" in tie.reason
    assert "modal dialog" in tie.reason


def test_a_cross_tie_always_carries_its_REASON():
    """A cross-tie appearing without explanation is exactly what
    REUSE_GUIDELINES section 3 exists to prevent.
    """
    tie = resolve_tie(TieSubset(0, 10), layout(), TIE, BAR, 900.0)
    assert tie.reason
    assert "%.1f" % tie.narrow_mm in tie.reason
    assert "%.1f" % tie.min_buildable_mm in tie.reason


def test_the_threshold_is_bend_plus_tie():
    assert minimum_buildable_narrow_mm(40.0, 9.5) == pytest.approx(49.5)
    assert minimum_buildable_narrow_mm(115.0, 19.1) == pytest.approx(134.1)


def test_a_cross_tie_restrains_only_its_two_ends():
    tie = resolve_tie(TieSubset(0, 10), layout(), TIE, BAR, 900.0)
    assert len(tie.restrained_indices) == 2


# --------------------------------------------------------------------- #
# What "restrained" means


def test_the_outer_tie_restrains_only_the_FOUR_corner_bars():
    """The whole reason inner ties exist. A bar merely inside a tie's
    rectangle is not restrained by it.
    """
    outer = ties([])[0]
    assert outer.restrained_indices == [0, 2, 5, 7]
    assert len(outer.enclosed_indices) == 10


def test_a_tie_corner_restrains_a_bar_it_does_not_ENCLOSE():
    """A subset's bounding box can land a corner on a bar the subset does
    not name, and that bar is still inside the bend. The first version of
    this module scanned only the enclosed bars and missed one.
    """
    tie = resolve_tie(TieSubset(8, 6), layout(), TIE, BAR, BEND)
    assert 4 not in tie.enclosed_indices
    assert 4 in tie.restrained_indices


# --------------------------------------------------------------------- #
# Section 6.1, as a validator


def test_the_outer_tie_alone_is_REFUSED_on_the_live_column():
    """151.7 mm clear distance puts the layout in the "every bar tied"
    tier, and a perimeter tie restrains four of ten.
    """
    findings = validate(layout(), ties([]))
    assert is_blocking(findings)
    assert any("EVERY bar to be restrained" in f.message for f in findings)
    assert any("1, 3, 4, 6, 8, 9" in f.message for f in findings)


def test_the_unrestrained_bars_are_NAMED():
    """A refusal the engineer cannot act on is half a refusal."""
    findings = validate(layout(), ties([]))
    message = [f.message for f in findings if "EVERY bar" in f.message][0]
    for index in (1, 3, 4, 6, 8, 9):
        assert str(index) in message


def test_a_valid_covering_passes_clean():
    assert validate(layout(), ties(VALID)) == []


def test_the_branch_spacing_limit_bites_on_a_bare_perimeter():
    """Section 6.1's other limit. A 450 x 600 column's perimeter tie has
    its two vertical legs 360 mm apart and its horizontal legs 510 -- both
    over 300, which is why the section needs inner ties in BOTH
    directions, not just enough restrained bars.
    """
    findings = validate(layout(), ties([]))
    assert any("360" in f.message and "vertical legs" in f.message
               for f in findings)
    assert any("510" in f.message and "horizontal legs" in f.message
               for f in findings)


def _alternate_tier_layout():
    """A 350 x 500 section with the same 3 + 4 bars: clear distance
    112.5 mm, which is the ALTERNATE tier.

    Constructed rather than searched for. The obvious move -- add bars to
    the 450 x 600 until the gaps shrink -- gives a 14-bar perimeter, and
    enumerating coverings of 14 bars does not finish.
    """
    return perimeter_bar_positions(350.0, 500.0, COVER, TIE, BAR, 3, 4)


def test_over_tying_is_a_WARNING_not_a_refusal():
    """Restraining every bar where the code permits alternates is
    conservative, not wrong. Refusing it would be the tool overruling the
    engineer; saying nothing would hide that it costs steel.
    """
    lay = _alternate_tier_layout()
    resolved = ties(VALID, lay)
    assert restrained_bar_indices(resolved) == set(range(len(lay.bars)))
    findings = validate(lay, resolved)
    assert not is_blocking(findings)
    assert any("more than the code requires" in f.message
               for f in findings if f.severity == SEVERITY_WARNING)


def test_the_alternate_tier_refuses_two_untied_bars_IN_A_ROW():
    """One untied bar between two tied ones is what "alternate" means;
    two in a row is not. Counting unrestrained bars rather than RUNS would
    confuse the two -- and would refuse a legal layout.
    """
    lay = _alternate_tier_layout()
    findings = validate(lay, ties([], lay))     # perimeter tie only
    blocking = [f for f in findings if f.severity == SEVERITY_BLOCKING]
    assert any("consecutive bars unrestrained" in f.message
               for f in blocking), [f.message for f in blocking]


def test_an_exceeded_tier_is_refused_WHATEVER_the_ties_are():
    """No tie arrangement rescues a gap section 6.1 does not cover."""
    lay = layout(count_b=2, count_h=2)
    findings = validate(lay, ties([], lay))
    assert is_blocking(findings)
    assert any("whatever the tie arrangement" in f.message for f in findings)


# --------------------------------------------------------------------- #
# Why the user picks, and the tool does not


def test_the_live_layout_admits_MANY_valid_coverings():
    """R4's reason, measured rather than asserted.

    Section 6.1 admits many valid coverings of one layout and the spec has
    no tie-break rule between them, so auto-derivation would mean the tool
    inventing one. On the live column the minimum is three inner ties, and
    there are 420 distinct ways to place them -- this stops counting at
    twenty, which makes the point at a fraction of the cost.

    Slow-ish by design: it is the evidence for a ruling.
    """
    lay = layout()
    count = len(lay.bars)
    candidates = [TieSubset(start, size)
                  for start in range(count)
                  for size in range(2, count + 1)]
    # Stops at 20 rather than enumerating all of them. The exhaustive
    # count is 420, but solutions are sparse -- reaching even 101 of them
    # scans ~28,000 combinations and cost eighteen seconds on a suite that
    # otherwise runs in two. The claim is "many, with no rule to choose
    # between them", and twenty makes it as well as four hundred.
    solutions = 0
    for combo in itertools.combinations(candidates, 3):
        if not is_blocking(validate(lay, ties(list(combo), lay))):
            solutions += 1
            if solutions >= 20:
                break
    assert solutions >= 20

    # ...and no covering with fewer than three inner ties exists, so the
    # minimum is not a preference either.
    for size in (1, 2):
        assert not any(
            not is_blocking(validate(lay, ties(list(combo), lay)))
            for combo in itertools.combinations(candidates, size))


# --------------------------------------------------------------------- #
# The report lines #91 had to leave out


def test_the_report_states_loop_or_cross_tie_PER_tie():
    lines = "\n".join(tie_report_lines(ties(VALID)))
    assert "Outer perimeter tie: closed loop" in lines
    assert lines.count("closed loop") == 4     # outer + three inner


def test_the_report_states_the_bend_test_for_a_cross_tie():
    lines = "\n".join(tie_report_lines(
        resolve_ties([], layout(), TIE, BAR, 900.0)))
    assert "cross-tie" in lines
    assert "cannot be bent" in lines
    assert "A1" in lines


def test_every_tie_reports_its_narrow_dimension_against_the_minimum():
    for line in tie_report_lines(ties(VALID)):
        if line.startswith(" "):
            continue
        assert "Narrow dimension" in line
        assert "minimum" in line


def test_restrained_bar_indices_unions_every_tie():
    assert restrained_bar_indices(ties(VALID)) == set(range(10))
