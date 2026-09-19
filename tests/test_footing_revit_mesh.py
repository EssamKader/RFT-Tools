# -*- coding: utf-8 -*-
"""Mock-object verification of the footing bottom-mesh placement adapter
(runs the actual adapter source against tests/fake_revit_api.py's stand-in
Revit types -- see that module's own header for what a green run here
does and does not prove).

Spec Ref: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 (footing host, no cast/wrapper) and Sec 2 (norm = XYZ.BasisZ).
"""

import pytest

from fake_revit_api import FakeBoundingBox, FakeXYZ

from rft.core.footing_plan import FootingInputs, build_footing_plan
from rft.revit.footing_mesh import place_straight_bottom_mesh
from rft.revit.units import mm_to_internal


class _FakeFootingHost(object):
    """Stand-in for the footing FamilyInstance -- only what this adapter
    reads: ``get_BoundingBox(view)``. Not ``fake_revit_api.FakeColumn``
    (that fixture is the column tool's own; this ticket's element
    isolation rule is to build the footing's own stand-in rather than
    widen or borrow a column-shaped one).
    """

    def __init__(self, min_xyz, max_xyz):
        self._box = FakeBoundingBox(min_xyz, max_xyz)

    def get_BoundingBox(self, _view):
        return self._box


class _FakeBarType(object):
    def __init__(self, name):
        self.name = name


@pytest.fixture
def footing():
    # A 1800x1200 footing (internal units = feet, matching mm_to_internal's
    # own conversion so this test's expected math cross-checks the exact
    # boundary the adapter uses).
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
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0)
    return build_footing_plan(inputs)


def test_two_bars_are_created_hosted_on_the_footing(footing, plan):
    document = object()
    bar_x_type = _FakeBarType("16M")
    bar_y_type = _FakeBarType("12M")

    bar_x, bar_y = place_straight_bottom_mesh(
        document, footing, plan.bottom_mesh, bar_x_type, bar_y_type)

    assert bar_x.args[5] is footing
    assert bar_y.args[5] is footing
    assert bar_x.args[2] is bar_x_type
    assert bar_y.args[2] is bar_y_type
    assert bar_x.args[0] is document
    assert bar_y.args[0] is document


def test_each_bar_gets_exactly_one_curve_not_hooked(footing, plan):
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))

    assert len(bar_x.args[7]) == 1
    assert len(bar_y.args[7]) == 1
    assert bar_x.args[3] is None  # startHook -- straight case, no hooks
    assert bar_x.args[4] is None  # endHook


def test_the_norm_argument_is_XYZ_basis_z(footing, plan):
    """issue #197 Sec 1's call passed ``XYZ.BasisZ`` as ``norm`` -- the one
    argument its write-up shows explicitly (everything after ``curves`` is
    "...").
    """
    bar_x, _bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    norm = bar_x.args[6]
    assert (norm.X, norm.Y, norm.Z) == (0.0, 0.0, 1.0)


def test_bar_x_curve_is_centred_on_the_footing_and_the_right_length(footing, plan):
    bar_x, _bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    curve = bar_x.args[7][0]

    centre_x_internal = mm_to_internal(1800.0) / 2.0
    centre_y_internal = mm_to_internal(1200.0) / 2.0
    half_length_internal = mm_to_internal(
        plan.bottom_mesh.lengths.mesh_bar_x_mm / 2.0)

    p0 = curve.GetEndPoint(0)
    p1 = curve.GetEndPoint(1)
    assert p0.X == pytest.approx(centre_x_internal - half_length_internal)
    assert p1.X == pytest.approx(centre_x_internal + half_length_internal)
    assert p0.Y == pytest.approx(centre_y_internal)
    assert p1.Y == pytest.approx(centre_y_internal)


def test_bar_y_sits_above_bar_x_by_the_mesh_bar_x_diameter(footing, plan):
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    z_x = bar_x.args[7][0].GetEndPoint(0).Z
    z_y = bar_y.args[7][0].GetEndPoint(0).Z

    expected_gap_internal = mm_to_internal(16.0 / 2.0 + 12.0 / 2.0)
    assert (z_y - z_x) == pytest.approx(expected_gap_internal)
