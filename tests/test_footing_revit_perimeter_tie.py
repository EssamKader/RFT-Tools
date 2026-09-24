# -*- coding: utf-8 -*-
"""Mock-object verification of the `perimeter_tie` closed-loop/split
placement adapter (#244) -- runs the actual adapter source against
tests/fake_revit_api.py's stand-in Revit types.

Spec Ref: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 (footing host, no cast/wrapper); R14 (`docs/footing/spec-
amendments.md`). See `rft.revit.footing_perimeter_tie`'s own "SHAPE
UNVERIFIED" docstring note -- this test proves only the WIRING (the right
host, the right curves, the right per-level count, the right shape/norm
per case), not a live host acceptance.
"""

import pytest

from fake_revit_api import FakeBoundingBox, FakeXYZ

from rft.core.footing_plan import FootingInputs, build_footing_plan
from rft.revit.footing_perimeter_tie import (
    PerimeterTieNotPlaceableError,
    PerimeterTieSplitBarsMissingError,
    place_perimeter_ties,
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
                       mm_to_internal(1500.0))
    return _FakeFootingHost(min_xyz, max_xyz)


def _unsplit_plan(**overrides):
    kwargs = dict(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=1500.0, bottom_cover_mm=50.0, top_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0,
        y_offset_mm=150.0, ld_multiplier=40.0,
        perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
        perimeter_tie_quantity=2)
    kwargs.update(overrides)
    return build_footing_plan(FootingInputs(**kwargs)).perimeter_tie


def _split_plan(**overrides):
    kwargs = dict(
        a_mm=7000.0, b_mm=7000.0, cover_mm=50.0,
        footing_thickness_mm=1500.0, bottom_cover_mm=50.0, top_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0,
        y_offset_mm=150.0, ld_multiplier=40.0,
        perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
        perimeter_tie_quantity=2, perimeter_tie_lap_mm=600.0,
        perimeter_tie_first_bar_length_mm=15000.0,
        perimeter_tie_second_bar_length_mm=13200.0)
    kwargs.update(overrides)
    return build_footing_plan(FootingInputs(**kwargs)).perimeter_tie


def _big_footing():
    min_xyz = FakeXYZ(0.0, 0.0, 0.0)
    max_xyz = FakeXYZ(mm_to_internal(7000.0), mm_to_internal(7000.0),
                       mm_to_internal(1500.0))
    return _FakeFootingHost(min_xyz, max_xyz)


# --- Common case: one closed loop per level -----------------------------

def test_no_ladder_refuses_rather_than_placing_nothing_silently(footing):
    empty_plan = build_footing_plan(FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=1500.0, bottom_cover_mm=50.0, top_cover_mm=50.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0,
        y_offset_mm=150.0, ld_multiplier=40.0)).perimeter_tie

    assert empty_plan is None
    # A None plan is refused before place_perimeter_ties would even be
    # able to read .ladder off it -- this test documents that the caller
    # (script.py) must gate on inputs.perimeter_tie_dia_mm the same way
    # every other optional element already does, not that this function
    # itself tolerates a None plan.
    with pytest.raises(AttributeError):
        place_perimeter_ties(
            object(), footing, empty_plan, _FakeBarType("10M"),
            _FakeHookType("Stirrup/Tie - 135 deg."))


def test_one_closed_loop_rebar_is_created_per_ladder_level(footing):
    plan = _unsplit_plan()
    bar_type = _FakeBarType("10M")
    hook_type = _FakeHookType("Stirrup/Tie - 135 deg.")

    ties = place_perimeter_ties(object(), footing, plan, bar_type, hook_type)

    assert len(ties) == len(plan.ladder.levels_mm)
    for tie in ties:
        assert tie.args[5] is footing
        assert tie.args[2] is bar_type
        assert tie.args[3] is hook_type
        assert tie.args[4] is hook_type


def test_each_loops_curves_form_a_closed_four_sided_loop(footing):
    plan = _unsplit_plan()
    ties = place_perimeter_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))

    for tie in ties:
        curves = tie.args[7]
        assert len(curves) == 4
        for index in range(len(curves)):
            end = curves[index].GetEndPoint(1)
            start = curves[(index + 1) % len(curves)].GetEndPoint(0)
            assert end.X == pytest.approx(start.X)
            assert end.Y == pytest.approx(start.Y)
            assert end.Z == pytest.approx(start.Z)


def test_norm_is_basis_z_for_the_horizontal_closed_loop(footing):
    plan = _unsplit_plan()
    ties = place_perimeter_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    for tie in ties:
        norm = tie.args[6]
        assert (norm.X, norm.Y, norm.Z) == (0.0, 0.0, 1.0)


def test_each_levels_own_z_matches_the_ladder(footing):
    plan = _unsplit_plan()
    ties = place_perimeter_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    for tie, level_z_mm in zip(ties, plan.ladder.levels_mm):
        curves = tie.args[7]
        z_internal = curves[0].GetEndPoint(0).Z
        assert z_internal == pytest.approx(mm_to_internal(level_z_mm))


def test_the_loops_own_corners_are_placed_relative_to_the_footing_origin(
        footing):
    """inner_a=1700, inner_b=1100 (a=1800,b=1200,cover=50) -> SW corner at
    (-850, -550) footing-local -- the footing's own bounding-box centre
    (900mm, 600mm on this fixture) plus that offset."""
    plan = _unsplit_plan()
    ties = place_perimeter_ties(
        object(), footing, plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))

    curves = ties[0].args[7]
    corner_x = curves[0].GetEndPoint(0).X
    corner_y = curves[0].GetEndPoint(0).Y
    expected_x = mm_to_internal(900.0) + mm_to_internal(-850.0)
    expected_y = mm_to_internal(600.0) + mm_to_internal(-550.0)
    assert corner_x == pytest.approx(expected_x)
    assert corner_y == pytest.approx(expected_y)


# --- Split case (R14): two open bars per level ---------------------------

def test_a_required_split_with_no_bar_lengths_typed_refuses():
    plan = _split_plan(
        perimeter_tie_first_bar_length_mm=None,
        perimeter_tie_second_bar_length_mm=None)
    assert plan.geometry.splice.bar_count == 2
    assert plan.split_bars is None

    with pytest.raises(PerimeterTieSplitBarsMissingError):
        place_perimeter_ties(
            object(), _big_footing(), plan, _FakeBarType("10M"),
            _FakeHookType("Stirrup/Tie - 135 deg."))


def test_two_open_bar_rebars_are_created_per_ladder_level():
    plan = _split_plan()
    bar_type = _FakeBarType("10M")
    hook_type = _FakeHookType("Stirrup/Tie - 135 deg.")

    footing = _big_footing()
    ties = place_perimeter_ties(
        object(), footing, plan, bar_type, hook_type)

    assert len(ties) == 2 * len(plan.ladder.levels_mm)
    for tie in ties:
        assert tie.args[5] is footing
        assert tie.args[2] is bar_type
        # Open bars carry NO hook type (shape built from curves, not a
        # hook) -- unlike the closed-loop case above.
        assert tie.args[3] is None
        assert tie.args[4] is None


def test_open_bars_are_not_closed_back_to_their_own_start():
    plan = _split_plan()
    ties = place_perimeter_ties(
        object(), _big_footing(), plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))

    for tie in ties:
        curves = tie.args[7]
        start = curves[0].GetEndPoint(0)
        end = curves[-1].GetEndPoint(1)
        assert not (
            start.X == pytest.approx(end.X)
            and start.Y == pytest.approx(end.Y))


def test_the_two_bars_own_curve_counts_match_the_core_plans_own_points():
    plan = _split_plan()
    ties = place_perimeter_ties(
        object(), _big_footing(), plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))

    bar1_curves = ties[0].args[7]
    bar2_curves = ties[1].args[7]
    assert len(bar1_curves) == len(plan.split_bars.bar1_points) - 1
    assert len(bar2_curves) == len(plan.split_bars.bar2_points) - 1


def test_norm_is_basis_z_for_the_open_bars_too():
    """The whole shape stays in ONE horizontal plane (R14's own arc-length
    unroll never changes Z), so norm=XYZ.BasisZ is reused for the open-bar
    case too -- see this module's own docstring, "The open-bar norm
    question", for why this is NOT the same question footing_dowels'
    per-bar norm answers."""
    plan = _split_plan()
    ties = place_perimeter_ties(
        object(), _big_footing(), plan, _FakeBarType("10M"),
        _FakeHookType("Stirrup/Tie - 135 deg."))
    for tie in ties:
        norm = tie.args[6]
        assert (norm.X, norm.Y, norm.Z) == (0.0, 0.0, 1.0)
