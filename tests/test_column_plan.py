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
from rft.core.column_plan import (
    RUN_STEP_AXES, RoofTerminationPlan, bar_plan, complete_plan, is_blocked,
    roof_termination_plan,
)
from rft.core.column_roof import RoofBendDirection, RoofTermination, RunTermination
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
         confinement=None, middle=None, roof_termination=None):
    return complete_plan(bars(), mode, BEND, text,
                         manual_confinement_mm=confinement,
                         manual_middle_zone_mm=middle,
                         roof_termination=roof_termination)


def _stub_roof_plan():
    # Renamed from `roof_termination_plan` (#176): the real assembler now
    # has that name, and this helper was SHADOWING the import of it.
    """A stand-in `RoofTerminationPlan` (#172, R44), for the composition
    tests below -- not a re-derivation of `column_roof`'s own math, which
    `tests/test_column_roof.py` already covers on its own terms.

    Bottom/top step along Hand and bend along Facing; right/left step
    along Facing and bend along Hand (R44) -- so bottom and top share one
    `RunTermination`, and right and left the other.
    """
    hand_run = RunTermination(
        termination=RoofTermination(
            direction="+Hand", a_mm=175.0, b_mm=805.0, ld_mm=960.0,
            achieved_mm=960.0, shortfall_mm=0.0, free_edge=False,
            bend_loss_mm=19.87, run_limited=False),
        directions=(
            RoofBendDirection(name="+Hand", has_slab=True, available_run_mm=5000.0),
            RoofBendDirection(name="-Hand", has_slab=False, available_run_mm=220.0),
        ))
    facing_run = RunTermination(
        termination=RoofTermination(
            direction="+Facing", a_mm=175.0, b_mm=805.0, ld_mm=960.0,
            achieved_mm=960.0, shortfall_mm=0.0, free_edge=False,
            bend_loss_mm=19.87, run_limited=False),
        directions=(
            RoofBendDirection(name="+Facing", has_slab=True, available_run_mm=5000.0),
            RoofBendDirection(name="-Facing", has_slab=True, available_run_mm=5000.0),
        ))
    return RoofTerminationPlan(
        bottom=facing_run, right=hand_run, top=facing_run, left=hand_run,
        floor_label="Floor 424637", thickness_mm=300.0, cover_mm=25.0,
        cover_provenance="read")


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


# --------------------------------------------------------------------- #
# #172: the OPTIONAL top-floor termination (R36)


def test_an_ordinary_column_carries_no_roof_termination():
    """R36: an unticked box means section 9's ordinary splice. Absent must
    be the default EVERYWHERE, so this is asserted directly rather than
    assumed from the signature.

    Calls ``complete_plan`` directly WITHOUT naming ``roof_termination`` at
    all -- this file's own ``plan()`` fixture always passes it explicitly
    (even as ``None``), which would let ``complete_plan``'s own default
    value change without this test ever exercising it.
    """
    p = complete_plan(bars(), MODE_AUTO, BEND, CONVENTIONAL)
    assert p.roof_termination is None


def test_omitting_roof_termination_leaves_every_other_field_UNCHANGED():
    """The ordinary column's plan must be byte-for-byte what it is today.
    Compared field by field rather than by the object's identity, because a
    plan built with the new optional argument omitted must equal one built
    without the argument existing at all."""
    without_arg = plan()
    with_default = plan(roof_termination=None)
    assert without_arg == with_default


def test_a_stated_roof_termination_is_carried_through_unexamined():
    roof = _stub_roof_plan()
    p = plan(roof_termination=roof)
    assert p.roof_termination is roof


# --------------------------------------------------------------------- #
# #176: the assembler -- four runs from one slab read


#: The column's own four measured directions (R41/R42), the shape
#: `rft.revit.column_roof_slab.read_top_floor_slab` returns. Deliberately
#: asymmetric: +Hand has the room, -Hand is a short flagged free edge,
#: +Facing is a MEASURED short run and -Facing has room. A symmetric
#: fixture would let a wrong axis mapping pass.
_MEASURED = (
    RoofBendDirection(name="+Hand", has_slab=True, available_run_mm=5000.0),
    RoofBendDirection(name="-Hand", has_slab=False, available_run_mm=220.0),
    RoofBendDirection(name="+Facing", has_slab=True, available_run_mm=300.0),
    RoofBendDirection(name="-Facing", has_slab=True, available_run_mm=5000.0),
)


def _assembled(directions=_MEASURED, ld_mm=960.0):
    return roof_termination_plan(
        ld_mm=ld_mm, thickness_mm=300.0, cover_mm=25.0,
        cover_provenance="read", floor_label="Floor 424637",
        directions=directions, bend_radius_mm=46.3)


def test_each_run_bends_PERPENDICULAR_to_the_axis_it_steps_along():
    """R44, as the assembler's whole reason to exist: a b-face run steps
    along Hand and must bend along Facing, an h-face run the reverse. A
    run bending along its own step axis is the call that raised an
    internal error in #173's part 3.
    """
    roof = _assembled()
    assert roof.bottom.termination.direction.endswith("Facing")
    assert roof.top.termination.direction.endswith("Facing")
    assert roof.right.termination.direction.endswith("Hand")
    assert roof.left.termination.direction.endswith("Hand")


def test_a_run_is_never_offered_a_direction_it_cannot_take():
    """Not only the winner: the two CANDIDATES a run was narrowed to are
    carried for section 4, and a run must never carry its own step axis
    among them even as a rejected option.
    """
    roof = _assembled()
    for run in (roof.bottom, roof.top):
        assert [d.name for d in run.directions] == ["+Facing", "-Facing"]
    for run in (roof.right, roof.left):
        assert [d.name for d in run.directions] == ["+Hand", "-Hand"]


def test_the_run_with_the_MOST_ROOM_wins_within_each_run_s_own_two():
    """R41 is unchanged by R44 -- it just chooses from two instead of
    four. -Facing has the room and +Facing is capped at 300, so both
    b-face runs go -Facing; +Hand has the room against a 220 free edge,
    so both h-face runs go +Hand.
    """
    roof = _assembled()
    assert roof.bottom.termination.direction == "-Facing"
    assert roof.right.termination.direction == "+Hand"


def test_the_slab_facts_are_stated_ONCE_not_once_per_run():
    """A reviewer must never be able to read two different slab covers off
    one report, so thickness/cover/provenance live on the plan, not on a
    run."""
    roof = _assembled()
    assert roof.thickness_mm == 300.0
    assert roof.cover_mm == 25.0
    assert roof.cover_provenance == "read"
    assert roof.floor_label == "Floor 424637"
    for run in (roof.bottom, roof.right, roof.top, roof.left):
        assert not hasattr(run, "cover_mm")


def test_the_two_runs_on_the_SAME_axis_agree_and_that_is_not_a_bug():
    """Documented in `roof_termination_plan`'s own docstring: both b-face
    runs choose between the same two measured directions and therefore
    reach the same answer. Asserted so that a future change making them
    differ is a deliberate change with a failing test, not a surprise.
    """
    roof = _assembled()
    assert roof.bottom == roof.top
    assert roof.right == roof.left


def test_the_assembler_states_the_axis_mapping_in_the_PERIMETER_order():
    """The mapping must stay in the order
    `rft.revit.column_place_bars._face_run_slices` slices the perimeter,
    because that module looks its run up BY INDEX -- a reordering here
    would silently give a run another run's bend.
    """
    assert [name for name, _ in RUN_STEP_AXES] == [
        "bottom", "right", "top", "left"]
    assert [axis for _, axis in RUN_STEP_AXES] == [
        "Hand", "Facing", "Hand", "Facing"]


def test_a_shortfall_on_one_run_does_not_touch_another():
    """Each run develops what ITS OWN two directions allow. With every
    Facing direction short, the b-face runs fall short while the h-face
    runs still reach full L_D -- the per-run split's whole point.
    """
    short_facing = (
        RoofBendDirection(name="+Hand", has_slab=True, available_run_mm=5000.0),
        RoofBendDirection(name="-Hand", has_slab=True, available_run_mm=5000.0),
        RoofBendDirection(name="+Facing", has_slab=True, available_run_mm=300.0),
        RoofBendDirection(name="-Facing", has_slab=True, available_run_mm=280.0),
    )
    roof = _assembled(directions=short_facing)
    assert roof.bottom.termination.shortfall_mm > 0.0
    assert roof.right.termination.shortfall_mm == 0.0
