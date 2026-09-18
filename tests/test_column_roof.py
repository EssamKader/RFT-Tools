# -*- coding: utf-8 -*-
"""Issue #160 -- ``specs/column-roof-termination.md`` sections 1 and 2.

Pure module, pure tests: numbers in, numbers out, no Revit stand-in at all.

The fixture is the live model's own roof-ish case rather than round numbers:
a 300 x 600 column, 40 mm cover, a 16 mm bar at 60 diameters (R35's own
example, "like 60 column bar diameter"), under a 200 mm slab with 25 mm
cover.
"""

import pytest

from rft.core.column_roof import (
    MIN_BEND_LEG_MM, STEP_AXIS_FACING, STEP_AXIS_HAND, RoofBendDirection,
    candidate_directions_for_step_axis, development_length_mm,
    fillet_loss_mm, free_edge_run_mm, tangent_mm, terminate_bar,
    terminate_run, vertical_leg_mm,
)

BAR_DIA_MM = 16.0
MULTIPLIER = 60.0
LD_MM = 960.0                 # 60 x 16
SLAB_THICKNESS_MM = 200.0
SLAB_COVER_MM = 25.0
COLUMN_COVER_MM = 40.0
WIDE_FACE_MM = 600.0
NARROW_FACE_MM = 300.0
#: The bend radius #161 measured on the live host: legs of 500 and 400 came
#: back as 453.7 + arc 72.8 + 353.7, so each leg lost 46.3 mm -- the tangent,
#: which at 90 degrees IS the radius.
BEND_RADIUS_MM = 46.3
LOSS_MM = 19.87            # 46.3 x (2 - pi/2)


#: Deep interior: slab in that direction with more room than any L_D here
#: needs. Under R41 the run ALWAYS governs, so a "has slab" direction with
#: a zero run would now cap the bend to nothing -- which is the whole
#: point of the change.
def _slab(name="+Hand", run_mm=5000.0):
    return RoofBendDirection(name=name, has_slab=True,
                             available_run_mm=run_mm)


def _edge(name, width_mm=NARROW_FACE_MM):
    return RoofBendDirection(
        name=name, has_slab=False,
        available_run_mm=free_edge_run_mm(width_mm, COLUMN_COVER_MM))


# --------------------------------------------------------------- R35


def test_LD_is_the_multiplier_times_the_diameter():
    assert development_length_mm(MULTIPLIER, BAR_DIA_MM) == LD_MM


def test_there_is_no_default_multiplier_to_call_this_with():
    """R35: the tool never picks the multiplier. A signature with a default
    would let a caller omit it and get the beam spec's number by accident,
    which is the exact thing the ruling forbids."""
    with pytest.raises(TypeError):
        development_length_mm(BAR_DIA_MM)


def test_a_nonpositive_multiplier_is_refused():
    with pytest.raises(ValueError):
        development_length_mm(0.0, BAR_DIA_MM)


# --------------------------------------------------------------- section 1


def test_the_vertical_leg_is_the_slab_thickness_less_its_cover():
    assert vertical_leg_mm(SLAB_THICKNESS_MM, SLAB_COVER_MM) == 175.0


def test_a_cover_at_or_above_the_thickness_is_refused_not_negative():
    """Both numbers are READ from the slab (R37), so both can be wrong
    together. A negative leg must never reach the Revit API."""
    with pytest.raises(ValueError):
        vertical_leg_mm(200.0, 200.0)
    with pytest.raises(ValueError):
        vertical_leg_mm(200.0, 250.0)


def test_a_and_b_add_up_to_LD_where_slab_continues():
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM, [_slab()],
                           BEND_RADIUS_MM)

    assert result.a_mm == 175.0
    # R40: the NOMINAL legs overshoot L_D by exactly what the fillet eats...
    assert result.b_mm == pytest.approx(LD_MM - 175.0 + LOSS_MM, abs=0.01)
    assert result.a_mm + result.b_mm == pytest.approx(LD_MM + LOSS_MM,
                                                     abs=0.01)
    # ...so the BUILT bar develops L_D, which is what L_D means.
    assert result.achieved_mm == pytest.approx(LD_MM, abs=0.01)
    assert result.shortfall_mm == 0.0
    assert result.free_edge is False


# --------------------------------------------------------------- the cap


def test_the_bend_leg_never_falls_below_the_minimum():
    """Section 2.3's discipline, restated here: a thick slab and a short
    L_D would otherwise leave a bend of a few millimetres."""
    result = terminate_bar(300.0, 400.0, 25.0, [_slab()],
                           BEND_RADIUS_MM)

    assert result.b_mm == MIN_BEND_LEG_MM
    # capped at (L_D + loss) - 200, not the slab's own 375
    assert result.a_mm == pytest.approx(119.87, abs=0.01)


def test_an_LD_below_the_minimum_bend_leg_is_refused():
    """The beam tool shipped this once (#14 finding 3): the cap goes
    negative and the straight segment reverses direction.

    The MESSAGE is asserted, not just the exception. Without the L_D check
    a negative `a` falls through to R40's own tangent refusal, which raises
    the same ValueError for a different reason -- so a bare `raises` would
    pass with this guard deleted.
    """
    with pytest.raises(ValueError, match="below the 200"):
        terminate_bar(150.0, SLAB_THICKNESS_MM, SLAB_COVER_MM, [_slab()],
                      BEND_RADIUS_MM)


# --------------------------------------------------------------- section 2


def test_a_free_edge_caps_the_bend_to_what_fits_inside_the_column():
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           [_edge("-Facing", NARROW_FACE_MM)],
                           BEND_RADIUS_MM)

    # 300 - 40 x 2 = 220, far less than the 805 mm a full L_D now wants.
    assert result.b_mm == 220.0
    assert result.free_edge is True
    # R40: the fillet costs its 19.87 here TOO -- a short bar loses it as
    # surely as a long one, and the shortfall must carry that.
    assert result.achieved_mm == pytest.approx(175.0 + 220.0 - LOSS_MM,
                                              abs=0.01)
    assert result.shortfall_mm == pytest.approx(LD_MM - result.achieved_mm,
                                               abs=0.01)


def test_the_free_edge_run_is_the_face_width_less_cover_BOTH_sides():
    assert free_edge_run_mm(NARROW_FACE_MM, COLUMN_COVER_MM) == 220.0
    assert free_edge_run_mm(WIDE_FACE_MM, COLUMN_COVER_MM) == 520.0


def test_a_face_narrower_than_its_two_covers_is_refused():
    with pytest.raises(ValueError):
        free_edge_run_mm(70.0, COLUMN_COVER_MM)


def test_a_corner_bar_bends_where_the_SLAB_is_not_where_it_was_listed():
    """Section 2: a bar with more than one open direction "may bend into
    whichever available direction has slab", achieving full L_D -- it is
    never forced into a direction that happens to face a free edge."""
    result = terminate_bar(
        LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
        [_edge("-Hand", NARROW_FACE_MM), _slab("+Facing")], BEND_RADIUS_MM)

    assert result.direction == "+Facing"
    assert result.free_edge is False
    assert result.achieved_mm == LD_MM
    assert result.shortfall_mm == 0.0


def test_with_every_direction_a_free_edge_the_LONGEST_run_is_taken():
    """R41 makes this the same rule as every other direction choice: most
    room wins. It was a stated default when free edges were their own
    branch; it is now simply what the rule does."""
    result = terminate_bar(
        LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
        [_edge("-Facing", NARROW_FACE_MM), _edge("-Hand", WIDE_FACE_MM)],
        BEND_RADIUS_MM)

    assert result.direction == "-Hand"
    assert result.b_mm == 520.0


def test_the_shortfall_is_reported_not_left_to_be_subtracted():
    """Section 4 makes the report name what a free edge costs. A reviewer
    must not have to recompute it to notice one."""
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           [_edge("-Facing", NARROW_FACE_MM)],
                           BEND_RADIUS_MM)

    assert result.shortfall_mm == pytest.approx(565.0 + LOSS_MM, abs=0.01)
    assert result.achieved_mm + result.shortfall_mm == pytest.approx(
        LD_MM, abs=0.01)


def test_a_bar_with_nowhere_to_bend_is_refused():
    with pytest.raises(ValueError):
        terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM, [],
                      BEND_RADIUS_MM)


# --------------------------------------------------------------- R41


def test_an_interior_column_NEAR_the_slab_edge_is_capped_too():
    """The owner's case: an interior column about 500 mm from the edge.

    The slab continues, so the old binary rule took the full-L_D branch and
    asked for a 705 mm leg into 475 mm of room -- putting roughly 230 mm of
    bar outside the concrete. R41: the run governs whatever limits it.
    """
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           [_slab("+Hand", run_mm=475.0)], BEND_RADIUS_MM)

    assert result.b_mm == 475.0
    assert result.run_limited is True
    # Not a free edge: the slab IS there, it is just short. The report has
    # to tell those apart.
    assert result.free_edge is False
    assert result.shortfall_mm == pytest.approx(
        LD_MM - (175.0 + 475.0 - LOSS_MM), abs=0.01)


def test_a_deep_interior_bar_is_not_flagged_as_limited():
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           [_slab("+Hand")], BEND_RADIUS_MM)

    assert result.run_limited is False
    assert result.shortfall_mm == 0.0


def test_the_bend_goes_where_the_MOST_room_is_not_merely_where_slab_is():
    """R41 strengthens section 2's corner rule: a direction with slab but a
    short run loses to one with more room, even a free edge, because what
    matters is how much bar can be developed."""
    result = terminate_bar(
        LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
        [_slab("+Hand", run_mm=120.0), _edge("-Facing", WIDE_FACE_MM)],
        BEND_RADIUS_MM)

    assert result.direction == "-Facing"
    assert result.b_mm == 520.0


def test_with_room_everywhere_the_first_stated_direction_still_wins():
    """Section 2's "no preferred direction" is untouched where it applies:
    with room everywhere every direction achieves full L_D, so the tie-break
    stays a stated default rather than becoming a rule."""
    result = terminate_bar(
        LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
        [_slab("+Hand"), _slab("+Facing")], BEND_RADIUS_MM)

    assert result.direction == "+Hand"
    assert result.shortfall_mm == 0.0


# --------------------------------------------------------------- R40


def test_the_fillet_loss_reproduces_the_LIVE_measurement():
    """#161 handed CreateFromCurves 500 + 400 and got back 453.7 + arc 72.8
    + 353.7 = 880.2 -- a 19.8 mm loss. The formula is not fitted to that
    number; it agrees with it."""
    assert fillet_loss_mm(BEND_RADIUS_MM) == pytest.approx(19.87, abs=0.01)
    # The transcript prints each curve to ONE decimal, and 453.7 + 72.8 +
    # 353.7 sums two rounded-up values -- so the printed 880.2 is worth
    # about +/-0.2, not +/-0.01. Asserting tighter than the measurement was
    # printed would be false precision.
    assert 900.0 - fillet_loss_mm(BEND_RADIUS_MM) == pytest.approx(880.2,
                                                                  abs=0.2)


def test_the_loss_scales_with_the_BAR_TYPE_s_radius():
    """R40: r is read from the bar type, never hardcoded. A bigger bar bends
    on a bigger radius and loses more -- so a constant would be right for
    13M and wrong for everything else in the schedule."""
    assert fillet_loss_mm(2.0 * BEND_RADIUS_MM) == pytest.approx(
        2.0 * fillet_loss_mm(BEND_RADIUS_MM), abs=0.01)
    assert fillet_loss_mm(0.0) == 0.0


def test_the_tangent_at_90_degrees_IS_the_radius():
    """A1 generalised: t = r / tan(theta/2), which at 90 degrees is t = r --
    and #161 measured exactly that, 46.3 off each leg."""
    assert tangent_mm(BEND_RADIUS_MM) == pytest.approx(BEND_RADIUS_MM,
                                                       abs=0.001)


def test_a_leg_shorter_than_the_tangent_is_refused():
    """Section 2's free-edge cap can drive the horizontal leg below what the
    bend needs to turn through. That is not a tight bend -- it is a corner
    that cannot be built."""
    with pytest.raises(ValueError):
        terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                      [RoofBendDirection(name="-Facing", has_slab=False,
                                        available_run_mm=30.0)],
                      BEND_RADIUS_MM)


# --------------------------------------------------------------- #180, R44


#: Four full directions, one per axis -- the column's own full set, before
#: a run narrows it to its own two (R44).
_ALL_FOUR = (
    RoofBendDirection(name="+Hand", has_slab=True, available_run_mm=5000.0),
    RoofBendDirection(name="-Hand", has_slab=True, available_run_mm=220.0),
    RoofBendDirection(name="+Facing", has_slab=True, available_run_mm=5000.0),
    RoofBendDirection(name="-Facing", has_slab=True, available_run_mm=475.0),
)


def test_a_run_stepping_along_Hand_may_bend_only_along_Facing():
    result = candidate_directions_for_step_axis(STEP_AXIS_HAND, _ALL_FOUR)
    assert [d.name for d in result] == ["+Facing", "-Facing"]


def test_a_run_stepping_along_Facing_may_bend_only_along_Hand():
    result = candidate_directions_for_step_axis(STEP_AXIS_FACING, _ALL_FOUR)
    assert [d.name for d in result] == ["+Hand", "-Hand"]


def test_an_unknown_step_axis_is_refused_not_guessed():
    with pytest.raises(ValueError):
        candidate_directions_for_step_axis("Up", _ALL_FOUR)


def test_terminate_run_never_hands_terminate_bar_its_OWN_step_axis():
    """The collision R44 exists to prevent: `normal` cannot be both the
    array's step axis and perpendicular to the bend plane at once, so a
    run must never even be OFFERED a direction along its own axis to bend
    into -- not merely steered away from choosing it."""
    result = terminate_run(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           STEP_AXIS_HAND, _ALL_FOUR, BEND_RADIUS_MM)
    assert result.termination.direction in ("+Facing", "-Facing")
    assert all(d.name in ("+Facing", "-Facing") for d in result.directions)


def test_terminate_run_still_picks_the_MOST_ROOM_between_its_two():
    """R41 unchanged: of the two candidates a run actually has, the one
    with more room wins. -Hand has only 220 mm here; +Hand has 5000."""
    result = terminate_run(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           STEP_AXIS_FACING, _ALL_FOUR, BEND_RADIUS_MM)
    assert result.termination.direction == "+Hand"
    assert result.termination.shortfall_mm == 0.0


def test_terminate_run_can_still_be_capped_by_its_OWN_two():
    """Give a run two candidates that are BOTH short, so even the winner
    falls short of full L_D -- proves the narrowing actually removes the
    other axis' room rather than merely relabelling the same four."""
    narrow = (
        RoofBendDirection(name="+Facing", has_slab=False,
                          available_run_mm=free_edge_run_mm(
                              NARROW_FACE_MM, COLUMN_COVER_MM)),
        RoofBendDirection(name="-Facing", has_slab=False,
                          available_run_mm=free_edge_run_mm(
                              NARROW_FACE_MM, COLUMN_COVER_MM)),
        RoofBendDirection(name="+Hand", has_slab=True,
                          available_run_mm=5000.0),
        RoofBendDirection(name="-Hand", has_slab=True,
                          available_run_mm=5000.0),
    )
    result = terminate_run(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           STEP_AXIS_HAND, narrow, BEND_RADIUS_MM)
    assert result.termination.direction in ("+Facing", "-Facing")
    assert result.termination.shortfall_mm > 0.0


# --------------------------------------------------------------- CONTEXT.md


def test_this_module_does_NOT_import_anchorage():
    """CONTEXT.md: "This tool does NOT call or reuse `rft.core.anchorage`."

    #99 is open because ``column_inputs`` violates that transitively while
    its guard walks one file's own imports. This check asks the RESOLVED
    graph -- import the module alone and look at what actually loaded --
    so it cannot pass the way that one does.
    """
    import os
    import subprocess
    import sys

    import rft

    # A SUBPROCESS, because this test suite has already imported half the
    # library by the time it runs: `anchorage` would be in this process's
    # sys.modules whatever column_roof does.
    lib_root = os.path.dirname(os.path.dirname(os.path.abspath(rft.__file__)))
    environment = dict(os.environ)
    environment["PYTHONPATH"] = lib_root
    # The module KEY is 'rft.core.anchorage', not 'anchorage' -- checking
    # the bare name is a guard that can never fire, which is how this one
    # was first written and what its own mutation case caught.
    program = (
        "import sys; import rft.core.column_roof; "
        "print(any('anchorage' in name for name in sys.modules))")
    output = subprocess.check_output([sys.executable, "-c", program],
                                     env=environment)
    assert output.decode().strip() == "False", (
        "rft.core.column_roof pulled in rft.core.anchorage -- CONTEXT.md "
        "forbids it, and #99 is the open bug about exactly this happening "
        "transitively")
