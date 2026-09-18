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
    MIN_BEND_LEG_MM, RoofBendDirection, development_length_mm,
    free_edge_run_mm, terminate_bar, vertical_leg_mm,
)

BAR_DIA_MM = 16.0
MULTIPLIER = 60.0
LD_MM = 960.0                 # 60 x 16
SLAB_THICKNESS_MM = 200.0
SLAB_COVER_MM = 25.0
COLUMN_COVER_MM = 40.0
WIDE_FACE_MM = 600.0
NARROW_FACE_MM = 300.0


def _slab(name="+Hand"):
    return RoofBendDirection(name=name, has_slab=True, available_run_mm=0.0)


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
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM, [_slab()])

    assert result.a_mm == 175.0
    assert result.b_mm == LD_MM - 175.0
    assert result.a_mm + result.b_mm == LD_MM
    assert result.achieved_mm == LD_MM
    assert result.shortfall_mm == 0.0
    assert result.free_edge is False


# --------------------------------------------------------------- the cap


def test_the_bend_leg_never_falls_below_the_minimum():
    """Section 2.3's discipline, restated here: a thick slab and a short
    L_D would otherwise leave a bend of a few millimetres."""
    result = terminate_bar(300.0, 400.0, 25.0, [_slab()])

    assert result.b_mm == MIN_BEND_LEG_MM
    assert result.a_mm == 100.0            # capped: 300 - 200, not 375
    assert result.a_mm + result.b_mm == 300.0


def test_an_LD_below_the_minimum_bend_leg_is_refused():
    """The beam tool shipped this once (#14 finding 3): the cap goes
    negative and the straight segment reverses direction."""
    with pytest.raises(ValueError):
        terminate_bar(150.0, SLAB_THICKNESS_MM, SLAB_COVER_MM, [_slab()])


# --------------------------------------------------------------- section 2


def test_a_free_edge_caps_the_bend_to_what_fits_inside_the_column():
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           [_edge("-Facing", NARROW_FACE_MM)])

    # 300 - 40 x 2 = 220, which is far less than the 785 mm a full LD wants.
    assert result.b_mm == 220.0
    assert result.free_edge is True
    assert result.achieved_mm == 175.0 + 220.0
    assert result.shortfall_mm == LD_MM - result.achieved_mm


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
        [_edge("-Hand", NARROW_FACE_MM), _slab("+Facing")])

    assert result.direction == "+Facing"
    assert result.free_edge is False
    assert result.achieved_mm == LD_MM
    assert result.shortfall_mm == 0.0


def test_with_every_direction_a_free_edge_the_LONGEST_run_is_taken():
    """A stated default, not a rule: section 2 caps each free edge and does
    not choose between two. The longest run develops the most bar, so a
    default that picked the first-listed would throw away anchorage that
    was available."""
    result = terminate_bar(
        LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
        [_edge("-Facing", NARROW_FACE_MM), _edge("-Hand", WIDE_FACE_MM)])

    assert result.direction == "-Hand"
    assert result.b_mm == 520.0


def test_the_shortfall_is_reported_not_left_to_be_subtracted():
    """Section 4 makes the report name what a free edge costs. A reviewer
    must not have to recompute it to notice one."""
    result = terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM,
                           [_edge("-Facing", NARROW_FACE_MM)])

    assert result.shortfall_mm == pytest.approx(565.0)
    assert result.achieved_mm + result.shortfall_mm == LD_MM


def test_a_bar_with_nowhere_to_bend_is_refused():
    with pytest.raises(ValueError):
        terminate_bar(LD_MM, SLAB_THICKNESS_MM, SLAB_COVER_MM, [])


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
