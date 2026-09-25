# -*- coding: utf-8 -*-
"""Mock-object verification of the `dowel_tie` closed-loop placement
adapter (#242) -- runs the actual adapter source against
tests/fake_revit_api.py's stand-in Revit types.

Spec Ref: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 (footing host, no cast/wrapper). Sec 4's own "still unverified"
list names closed-loop shapes explicitly -- see
``rft.revit.footing_dowel_ties``'s own "SHAPE UNVERIFIED" docstring note;
this test proves only the WIRING (the right host, the right curves, the
right per-level count), not a live host acceptance.
"""

import pytest

from fake_revit_api import FakeBoundingBox, FakeXYZ

from rft.core.footing_dowel_ties import DowelTieCorner, DowelTieLoop
from rft.core.footing_plan import (
    DowelColumnSection, FootingInputs, build_footing_plan,
)
from rft.revit.footing_dowel_ties import (
    DowelTieNotPlaceableError, place_dowel_ties,
)
from rft.revit.units import mm_to_internal


class _FakeLocation(object):
    def __init__(self, rotation_rad):
        self.Rotation = rotation_rad


class _FakeFootingHost(object):
    def __init__(self, min_xyz, max_xyz, rotation_rad=0.0):
        self._box = FakeBoundingBox(min_xyz, max_xyz)
        self.Location = _FakeLocation(rotation_rad)

    def get_BoundingBox(self, _view):
        return self._box


class _FakeBarType(object):
    def __init__(self, name):
        self.name = name


class _FakeHookType(object):
    def __init__(self, name):
        self.name = name


@pytest.fixture
def footing():
    min_xyz = FakeXYZ(0.0, 0.0, 0.0)
    max_xyz = FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                       mm_to_internal(450.0))
    return _FakeFootingHost(min_xyz, max_xyz)


@pytest.fixture
def array_plan():
    """A real N-bar array plus a real dowel_tie loop -- the SAME fixture
    shape test_footing_revit_dowels.py's own ``array_plan`` uses, extended
    with the tie inputs #242 needs (spacing + a bend diameter)."""
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=3,
        dowel_tie_spacing_mm=100.0)
    column_section = DowelColumnSection(
        Cw_mm=450.0, Cd_mm=600.0, Ccover_mm=40.0)
    plan = build_footing_plan(
        inputs, column_section=column_section,
        dowel_tie_bend_diameter_mm=60.0)
    assert len(plan.dowel.bars) > 1
    assert plan.dowel_ties.loop is not None
    return plan.dowel_ties


def test_no_loop_geometry_refuses_rather_than_placing_nothing_silently(
        footing):
    empty_plan = build_footing_plan(FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0, top_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0,
        y_offset_mm=150.0, ld_multiplier=40.0,
        dowel_tie_dia_mm=10.0, dowel_tie_spacing_mm=100.0)).dowel_ties

    with pytest.raises(DowelTieNotPlaceableError):
        place_dowel_ties(
            object(), footing, empty_plan, _FakeBarType("10M"),
            _FakeHookType("Stirrup/Tie - 135 deg."))


def test_one_rebar_is_created_per_ladder_level(footing, array_plan):
    bar_type = _FakeBarType("10M")
    hook_type = _FakeHookType("Stirrup/Tie - 135 deg.")

    ties = place_dowel_ties(object(), footing, array_plan, bar_type, hook_type)

    assert len(ties) == len(array_plan.ladder.levels)
    for tie in ties:
        assert tie.args[5] is footing
        assert tie.args[2] is bar_type
        assert tie.args[3] is hook_type
        assert tie.args[4] is hook_type


def test_each_ties_curves_form_a_closed_four_sided_loop(footing, array_plan):
    ties = place_dowel_ties(
        object(), footing, array_plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))

    for tie in ties:
        curves = tie.args[7]
        assert len(curves) == 4
        # Closed: each curve's end is the next curve's start, and the
        # last curve's end is the first curve's start.
        for index in range(len(curves)):
            end = curves[index].GetEndPoint(1)
            start = curves[(index + 1) % len(curves)].GetEndPoint(0)
            assert end.X == pytest.approx(start.X)
            assert end.Y == pytest.approx(start.Y)
            assert end.Z == pytest.approx(start.Z)


def test_norm_is_basis_z_for_the_horizontal_loop(footing, array_plan):
    """Per the ticket's own instruction: the ONE detail safe to reuse from
    ``column_place_ties`` -- a closed HORIZONTAL loop uses
    ``norm = XYZ.BasisZ``, unlike ``footing_dowels``'s own per-bar
    ``BasisY``/direction-aware norm for a bent bar in a VERTICAL plane."""
    ties = place_dowel_ties(
        object(), footing, array_plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    for tie in ties:
        norm = tie.args[6]
        assert (norm.X, norm.Y, norm.Z) == (0.0, 0.0, 1.0)


def test_each_levels_own_z_matches_the_ladder(footing, array_plan):
    ties = place_dowel_ties(
        object(), footing, array_plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    levels = array_plan.ladder.levels
    for tie, level in zip(ties, levels):
        curves = tie.args[7]
        z_internal = curves[0].GetEndPoint(0).Z
        assert z_internal == pytest.approx(mm_to_internal(level.z_mm))


@pytest.fixture
def array_plan_with_inner_ties():
    """#247 (R15): the SAME array fixture as ``array_plan``, plus an
    engineer-typed inner cross-tie between dowels 0 and 1."""
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=3,
        dowel_tie_spacing_mm=100.0, dowel_tie_subsets_text="0 1")
    column_section = DowelColumnSection(
        Cw_mm=450.0, Cd_mm=600.0, Ccover_mm=40.0)
    plan = build_footing_plan(
        inputs, column_section=column_section,
        dowel_tie_bend_diameter_mm=60.0)
    assert len(plan.dowel.bars) > 1
    assert plan.dowel_ties.loop is not None
    assert len(plan.dowel_ties.inner_ties) == 1
    return plan.dowel_ties


def test_no_subsets_text_places_only_the_outer_loop_unchanged_from_242(
        footing, array_plan):
    """#247 must not change #242's own existing behaviour when no inner
    ties were typed."""
    assert array_plan.inner_ties == tuple()
    ties = place_dowel_ties(
        object(), footing, array_plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    assert len(ties) == len(array_plan.ladder.levels)


def test_every_level_gets_the_outer_loop_plus_every_inner_tie(
        footing, array_plan_with_inner_ties):
    plan = array_plan_with_inner_ties
    ties = place_dowel_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    per_level = 1 + len(plan.inner_ties)
    assert len(ties) == per_level * len(plan.ladder.levels)


def test_the_inner_cross_tie_is_a_single_leg_not_a_closed_four_sided_loop(
        footing, array_plan_with_inner_ties):
    plan = array_plan_with_inner_ties
    ties = place_dowel_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    # Order within a level: outer loop first (4 curves), then each inner
    # tie (see place_dowel_ties' own docstring).
    outer_curves = ties[0].args[7]
    inner_curves = ties[1].args[7]
    assert len(outer_curves) == 4
    assert len(inner_curves) == 1


def test_both_the_outer_loop_and_the_inner_tie_ride_the_same_ladder_level(
        footing, array_plan_with_inner_ties):
    plan = array_plan_with_inner_ties
    ties = place_dowel_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    outer_z = ties[0].args[7][0].GetEndPoint(0).Z
    inner_z = ties[1].args[7][0].GetEndPoint(0).Z
    assert outer_z == pytest.approx(inner_z)


def test_the_loops_own_corners_are_placed_relative_to_the_footing_origin(
        footing):
    """Two known corners, one level -- the world XY must be the footing's
    own bounding-box centre (900mm, 600mm on this fixture) plus the loop's
    own footing-local (x, y)."""
    from rft.core.footing_dowel_ties import DowelTieLadder, DowelTieRun
    from rft.core.column_tie_levels import TieLevel

    loop = DowelTieLoop(corners=(
        DowelTieCorner(x_mm=-100.0, y_mm=-50.0),
        DowelTieCorner(x_mm=100.0, y_mm=-50.0),
        DowelTieCorner(x_mm=100.0, y_mm=50.0),
        DowelTieCorner(x_mm=-100.0, y_mm=50.0),
    ))
    ladder = DowelTieLadder(
        run=DowelTieRun(start_z_mm=50.0, end_z_mm=400.0),
        levels=(TieLevel(index=0, z_mm=50.0, zone="start", mirrored=False),),
        spacing_mm=100.0)

    class _FakeDowelTiePlan(object):
        def __init__(self, ladder, loop):
            self.ladder = ladder
            self.loop = loop

    plan = _FakeDowelTiePlan(ladder=ladder, loop=loop)
    ties = place_dowel_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))

    curves = ties[0].args[7]
    corner_x = curves[0].GetEndPoint(0).X
    corner_y = curves[0].GetEndPoint(0).Y
    expected_x = mm_to_internal(900.0) + mm_to_internal(-100.0)
    expected_y = mm_to_internal(600.0) + mm_to_internal(-50.0)
    assert corner_x == pytest.approx(expected_x)
    assert corner_y == pytest.approx(expected_y)
