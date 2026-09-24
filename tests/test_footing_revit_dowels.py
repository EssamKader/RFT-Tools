# -*- coding: utf-8 -*-
"""Mock-object verification of the footing dowel placement adapter (#202)
-- runs the actual adapter source against tests/fake_revit_api.py's
stand-in Revit types (see that module's own header for what a green run
here does and does not prove).

Spec Ref: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 (footing host, no cast/wrapper) and Sec 2 (a bar may extend beyond
the footing's own geometry while hosted on it).
"""

import math

import pytest

from fake_revit_api import FakeBoundingBox, FakeRebar, FakeXYZ

from rft.core.footing_plan import (
    DowelColumnSection, FootingInputs, build_footing_plan,
)
from rft.revit.footing_dowels import place_dowel_bar, place_dowel_bars
from rft.revit.footing_mesh import FootingRotationUnsupportedError
from rft.revit.units import mm_to_internal


class _FakeLocation(object):
    def __init__(self, rotation_rad):
        self.Rotation = rotation_rad


class _FakeFootingHost(object):
    """Same stand-in shape as test_footing_revit_mesh.py's own -- only
    ``get_BoundingBox(view)`` and ``Location.Rotation`` are read by this
    adapter too (via the shared ``_footing_origin`` it imports)."""

    def __init__(self, min_xyz, max_xyz, rotation_rad=0.0):
        self._box = FakeBoundingBox(min_xyz, max_xyz)
        self.Location = _FakeLocation(rotation_rad)

    def get_BoundingBox(self, _view):
        return self._box


class _FakeBarType(object):
    def __init__(self, name):
        self.name = name


@pytest.fixture
def footing():
    min_xyz = FakeXYZ(0.0, 0.0, 0.0)
    max_xyz = FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                       mm_to_internal(450.0))
    return _FakeFootingHost(min_xyz, max_xyz)


@pytest.fixture
def plan():
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0)
    return build_footing_plan(inputs)


def test_the_dowel_bar_is_created_hosted_on_the_footing(footing, plan):
    document = object()
    bar_type = _FakeBarType("25M")

    bar = place_dowel_bar(document, footing, plan.dowel, bar_type)

    assert bar.args[5] is footing
    assert bar.args[2] is bar_type
    assert bar.args[0] is document


def test_the_dowel_bar_carries_two_connected_curves_not_a_hook_type(
        footing, plan):
    bar = place_dowel_bar(
        object(), footing, plan.dowel, _FakeBarType("25M"))

    curves = bar.args[7]
    assert len(curves) == 2
    assert bar.args[3] is None  # startHook -- shape built from curves
    assert bar.args[4] is None  # endHook

    # The chain is continuous: the hook leg's end is the vertical leg's
    # start (the bend corner).
    hook_end = curves[0].GetEndPoint(1)
    vertical_start = curves[1].GetEndPoint(0)
    assert hook_end.X == pytest.approx(vertical_start.X)
    assert hook_end.Y == pytest.approx(vertical_start.Y)
    assert hook_end.Z == pytest.approx(vertical_start.Z)


def test_the_norm_argument_is_perpendicular_to_the_bend_plane(footing, plan):
    """The dowel's bend plane is local X-Z (hook leg along X, vertical leg
    along Z, both at Y=0). Per column_place_bars.py's own #183 measurement,
    a bent bar's `normal` must be PERPENDICULAR to its bend plane, so this
    is BasisY -- NOT the straight mesh bars' BasisZ, which lies IN this
    bend plane instead of perpendicular to it."""
    bar = place_dowel_bar(
        object(), footing, plan.dowel, _FakeBarType("25M"))
    norm = bar.args[6]
    assert (norm.X, norm.Y, norm.Z) == (0.0, 1.0, 0.0)


def test_the_vertical_leg_top_reaches_the_footing_top_face(footing, plan):
    """Per #201's own review lesson: check the actual Z-position, not
    just that a curve exists. footing_thickness=450mm -> the top of the
    vertical leg must land there, in internal units, measured from the
    footing's own bottom-face origin (z=0 -> 0 internal, since the fixture
    footing's own bounding box starts at Z=0)."""
    bar = place_dowel_bar(
        object(), footing, plan.dowel, _FakeBarType("25M"))
    curves = bar.args[7]
    vertical_top_z = curves[1].GetEndPoint(1).Z
    assert vertical_top_z == pytest.approx(mm_to_internal(450.0))


def test_the_bend_corner_sits_on_top_of_the_bottom_mesh(footing, plan):
    """bottom_cover=50, mesh_bar_x_dia=16, mesh_bar_y_dia=12 -> bend
    corner at z = 50+16+12 = 78mm, matching the core geometry's own
    hand-computed expectation (tests/test_footing_dowels.py)."""
    bar = place_dowel_bar(
        object(), footing, plan.dowel, _FakeBarType("25M"))
    curves = bar.args[7]
    bend_z = curves[0].GetEndPoint(1).Z
    assert bend_z == pytest.approx(mm_to_internal(78.0))


def test_the_dowel_is_centred_on_the_footing_plan_centroid(footing, plan):
    bar = place_dowel_bar(
        object(), footing, plan.dowel, _FakeBarType("25M"))
    curves = bar.args[7]
    centre_x_internal = mm_to_internal(1800.0) / 2.0
    centre_y_internal = mm_to_internal(1200.0) / 2.0

    vertical_top = curves[1].GetEndPoint(1)
    assert vertical_top.X == pytest.approx(centre_x_internal)
    assert vertical_top.Y == pytest.approx(centre_y_internal)


@pytest.mark.parametrize("rotation_deg", [0.0, 90.0, 180.0, 270.0, 360.0])
def test_axis_aligned_rotations_still_place_the_dowel(rotation_deg, plan):
    footing = _FakeFootingHost(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                mm_to_internal(450.0)),
        rotation_rad=math.radians(rotation_deg))

    bar = place_dowel_bar(
        object(), footing, plan.dowel, _FakeBarType("25M"))
    assert bar.args[5] is footing


def test_a_rotated_footing_refuses_instead_of_placing_the_dowel_wrong(plan):
    """Same rotation guard the mesh adapter already enforces -- reused,
    not reimplemented (this adapter imports ``_footing_origin`` from
    ``rft.revit.footing_mesh`` directly)."""
    footing = _FakeFootingHost(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                mm_to_internal(450.0)),
        rotation_rad=math.radians(30.0))

    with pytest.raises(FootingRotationUnsupportedError):
        place_dowel_bar(
            object(), footing, plan.dowel, _FakeBarType("25M"))


# --------------------------------------------------------------------- #
# place_dowel_bars (#223, Story 4) -- the array-loop wiring ONLY. The
# bent-bar shape itself (curve chain, norm, embedment Z, centring) is
# already covered above via place_dowel_bar / #202's own tracer bullet and
# is not re-tested here, per this ticket's own "Test volume rule".


@pytest.fixture
def array_plan(footing):
    """A real N-bar array (not the single-representative-bar fallback):
    a live-shaped ``DowelColumnSection`` plus the count/tie inputs
    ``_build_dowel_plan``'s own seven-field gate requires (#222/#227)."""
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=55.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=3)
    column_section = DowelColumnSection(
        Cw_mm=450.0, Cd_mm=600.0, Ccover_mm=40.0)
    plan = build_footing_plan(inputs, column_section=column_section)
    assert len(plan.dowel.bars) > 1  # a real array, not the 1-bar fallback
    return plan.dowel


def test_every_bar_in_the_array_is_placed(footing, array_plan):
    bar_type = _FakeBarType("25M")
    bars = place_dowel_bars(object(), footing, array_plan, bar_type)
    assert len(bars) == len(array_plan.bars)
    for bar in bars:
        assert bar.args[5] is footing
        assert bar.args[2] is bar_type


def test_the_array_bars_are_NOT_all_at_the_same_position(footing, array_plan):
    """The loop wiring, not just its call count: each bar must come from
    its OWN ``array_plan.bars`` entry, not the same one repeated."""
    bars = place_dowel_bars(
        object(), footing, array_plan, _FakeBarType("25M"))
    tops = set()
    for bar in bars:
        top = bar.args[7][1].GetEndPoint(1)
        tops.add((round(top.X, 6), round(top.Y, 6)))
    assert len(tops) == len(bars)


def test_a_mid_loop_failure_propagates_and_places_nothing_further(
        monkeypatch, footing, array_plan):
    """This function opens no transaction of its own (module docstring) --
    a failure must simply propagate, not be swallowed or partially
    retried, so the CALLER's transaction (the pushbutton script) is the one
    thing standing between a raised exception and a partially-placed array
    left in the model."""
    original_create = FakeRebar.CreateFromCurves
    calls = []

    def flaky_create(*args, **kwargs):
        calls.append(args)
        if len(calls) == 2:
            raise RuntimeError("simulated placement failure")
        return original_create(*args, **kwargs)

    monkeypatch.setattr(FakeRebar, "CreateFromCurves",
                        staticmethod(flaky_create))

    with pytest.raises(RuntimeError):
        place_dowel_bars(object(), footing, array_plan, _FakeBarType("25M"))
    assert len(calls) == 2
