# -*- coding: utf-8 -*-
"""#110 -- the one object the report, the sketch and the placer read.

## These were source guards, and now they are tests

Four of the assertions below used to live in ``test_column_xaml.py``,
reading ``script.py`` as TEXT: the ladder is built from the built spacings,
the topology is entered and never derived, a tie typo does not discard the
spacing, the ties are resolved once. They had to be written that way
because ``script.py`` imports ``pyrevit`` and cannot be executed here.

Moving the composition into a pure module makes them **executable**. A
source guard says the right function name appears; running it says the
right number comes out. Where a property can be tested by execution, that
is what this file does, and the difference is not cosmetic -- a guard that
greps for ``tie_levels`` passes just as happily when the arguments are
wrong.
"""

import pytest

from rft.core.column_host_rules import (
    SOURCE_SUPPORT_FACE, ColumnExtent, section_from_dimensions,
)
from rft.core.column_inputs import perimeter_bars, splice_length
from rft.core.column_plan import bar_plan, complete_plan, is_blocked
from rft.core.column_spacing import MODE_AUTO, MODE_MANUAL
from rft.core.column_ties import KIND_CROSS_TIE

#: The live column, measured: 450 x 600, cover 40, 16M bars, 10M ties.
B, H, COVER, BAR, TIE, BEND = 450.0, 600.0, 40.0, 15.9, 9.5, 65.0
CLEAR_HEIGHT = 2700.0

#: The three cross-ties an engineer draws for this cage (R19/R20).
CONVENTIONAL = "1 6\n9 3\n8 4"


def host():
    """What ``read_column`` returns, reduced to what the plan reads."""
    return {
        "section": section_from_dimensions(B, H),
        "cover_mm": COVER,
        "extent": ColumnExtent(
            base_z_mm=3000.0, top_z_mm=3000.0 + CLEAR_HEIGHT,
            clear_height_mm=CLEAR_HEIGHT,
            base_source=SOURCE_SUPPORT_FACE, top_source=SOURCE_SUPPORT_FACE),
        "type_name": "450 x 600mm",
    }


def bars():
    return bar_plan(
        host(),
        perimeter_bars(3, 4),
        splice_length(55.0, "diameters", BAR),
        BAR, TIE, "16M", "10M")


def plan(text=CONVENTIONAL, mode=MODE_AUTO,
         confinement=None, middle=None):
    return complete_plan(bars(), mode, BEND, text,
                         manual_confinement_mm=confinement,
                         manual_middle_zone_mm=middle)


# --------------------------------------------------------------------- #
# It composes and decides nothing


def test_the_plan_carries_what_will_be_BUILT_beside_the_limits():
    """Section 8's single-source rule, as the shape of the object rather
    than as a convention two callers are asked to remember."""
    p = plan(mode=MODE_MANUAL, confinement=200.0, middle=400.0)
    assert p.spacing.confinement_spacing_mm == 200.0   # what gets built
    assert p.spacing.s0_mm == pytest.approx(127.2)     # the code limit
    assert p.spacing.flags, "200 exceeds 127 and must be flagged"


def test_the_layout_follows_the_counts_the_report_states():
    p = plan()
    assert p.counts.total_count == len(p.layout.bars) == 10
    assert list(p.layout.corner_indices) == [0, 2, 5, 7]


# --------------------------------------------------------------------- #
# Was a source guard: the ladder follows the BUILT spacing


def test_the_tie_ladder_is_built_from_the_BUILT_spacings():
    """Not from ``s0_mm`` and the middle-zone maximum, which are the CODE
    LIMITS. In Mode B they differ, and a ladder drawn from the maximums
    lists ties at positions nothing will occupy -- on the page an engineer
    reads to decide whether to place.

    As a source guard this checked that ``s0_mm`` did not appear in the
    call. Here the manual spacing is deliberately set TIGHTER than the
    limit, so a ladder built from the limit would have FEWER levels: the
    numbers separate the two, not the spelling.
    """
    tight = plan(mode=MODE_MANUAL, confinement=100.0, middle=150.0)
    assert tight.spacing.confinement_spacing_mm == 100.0
    assert tight.spacing.s0_mm == pytest.approx(127.2)

    # The CONFINEMENT zone specifically, because that is the value under
    # test. An earlier version of this compared total level counts against
    # Mode A, which the middle-zone spacing also moves -- so swapping the
    # confinement term for s0_mm left the totals still different and the
    # assertion still true. The mutation prover caught that: the guard was
    # written, not tested.
    bottom = [level.z_mm for level in tight.ladder.levels
              if level.zone.startswith("confinement (bottom)")]
    steps = [round(b - a, 6) for a, b in zip(bottom, bottom[1:])]
    assert steps and all(step == pytest.approx(100.0) for step in steps), (
        "the confinement zone must step at the 100 mm that will be BUILT, "
        "not at the 127 mm code limit -- got %s" % steps)


def test_the_first_tie_sits_at_the_spec_s_offset_not_at_the_face():
    assert plan().ladder.levels[0].z_mm == pytest.approx(50.0)


# --------------------------------------------------------------------- #
# Was a source guard: stated, never derived


def test_the_topology_is_ENTERED_never_derived():
    """R4 and R17. Section 6.1 admits many valid coverings and the spec has
    no rule to choose between them, so deriving would mean inventing one.

    Stating nothing yields exactly ONE tie -- the implied outer perimeter
    -- and a refusal, rather than a topology the tool picked.
    """
    empty = plan(text="")
    assert len(empty.ties) == 1, "only the implied outer tie"
    assert is_blocked(empty), (
        "a bare perimeter on this cage leaves six bars unrestrained; if "
        "this passes, something derived a covering")


def test_what_is_stated_is_what_is_resolved():
    p = plan()
    assert len(p.ties) == 4                      # outer + the three stated
    assert [t.kind for t in p.ties[1:]] == [KIND_CROSS_TIE] * 3
    assert [sorted(t.restrained_indices) for t in p.ties[1:]] == [
        [1, 6], [3, 9], [4, 8]]


def test_the_conventional_cross_tie_cage_PASSES():
    """R19 and R20 together, on the real column. Before them this
    arrangement could not be stated, and would not have passed if it
    could."""
    assert not is_blocked(plan())


# --------------------------------------------------------------------- #
# Was a source guard: order, and one resolution


def test_a_tie_typo_does_not_discard_the_spacing():
    """The spacing is resolved BEFORE the topology, so a typo in the tie
    box does not throw away numbers just entered.

    The source guard compared the position of two function names in the
    file. This asserts the consequence: the spacing is computed, then the
    parse raises -- so the error names the tie line, never a spacing
    problem.
    """
    with pytest.raises(ValueError) as caught:
        plan(text="1 6\nnonsense")
    message = str(caught.value)
    assert "Line 2" in message
    assert "spacing" not in message.lower(), (
        "a tie typo must not surface as a spacing failure")


def test_a_spacing_error_is_raised_before_the_ties_are_touched():
    """The other direction: an impossible spacing fails as a spacing
    problem even when the tie box is also nonsense."""
    with pytest.raises(ValueError) as caught:
        plan(text="nonsense", mode=MODE_MANUAL,
             confinement=-5.0, middle=200.0)
    assert "spacing" in str(caught.value).lower()


def test_the_findings_belong_to_the_ties_the_plan_CARRIES():
    """One resolution, shared. Resolving twice is how the page and the
    picture come to disagree about which tie is a cross-tie -- the beam
    tool's ZONE_LAYOUT_FLAGS defect, exactly.

    Asserted by re-deriving: section 6.1's verdict on the plan's own ties
    and layout must equal the verdict the plan is carrying. A consumer
    that re-resolved from the same inputs would get this; one that
    re-resolved from its OWN inputs is what this forbids.
    """
    from rft.core.column_ties import validate
    p = plan()
    assert validate(p.layout, p.ties) == p.findings


def test_the_ties_were_resolved_against_the_layout_the_plan_carries():
    """Not merely an equal layout -- the same one. The sketch draws
    ``plan.layout`` and the ties' corner positions were computed from it;
    if they came from a second, equal-but-separate layout, a later change
    to how a layout is built would move one and not the other.
    """
    b = bars()
    p = complete_plan(b, MODE_AUTO, BEND, CONVENTIONAL)
    assert p.layout is b.layout


def test_is_blocked_is_the_ONE_test_of_section_6_1_s_verdict():
    """The placer's gate and the report's wording must agree, and the
    cheapest way to guarantee that is to leave them nothing to disagree
    with."""
    assert is_blocked(plan(text="")) is True
    assert is_blocked(plan()) is False


def test_the_plan_carries_the_tie_LINES_the_report_prints():
    """The report's import set is guarded to hold nothing it could compute
    with, so the lines describing each tie are formatted here, from the
    ties this object carries.

    Asserted on content, not merely on presence: an empty tuple is exactly
    what the mutation prover substitutes, and a test checking only that
    the field exists would not notice the page losing its topology.
    """
    p = plan()
    assert len(p.tie_lines) >= len(p.ties)
    joined = " ".join(p.tie_lines)
    assert "Outer perimeter tie" in joined
    assert "cross-tie" in joined
    for stated in ("1 6", "9 3", "8 4"):
        assert stated in joined, (
            "the report must name the tie the engineer typed: %s" % stated)
