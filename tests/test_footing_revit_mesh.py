# -*- coding: utf-8 -*-
"""Mock-object verification of the footing bottom-mesh placement adapter
(runs the actual adapter source against tests/fake_revit_api.py's stand-in
Revit types -- see that module's own header for what a green run here
does and does not prove).

Spec Ref: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 (footing host, no cast/wrapper). #229 replaced the straight-only
placement this file originally covered with the real bent U/L geometry
(#199/#200's own hook decision, never wired to placement until now) --
see this file's git history for the pre-#229 straight-case assertions.
"""

import math

import pytest

from fake_revit_api import FakeBoundingBox, FakeXYZ

from rft.core.footing_plan import (
    TOP_REINFORCEMENT_TOP_AND_BTM, FootingInputs, build_footing_plan,
)
from rft.revit.footing_mesh import (
    FootingRotationUnsupportedError,
    place_bottom_mesh_bars,
    place_straight_bottom_mesh,
    place_straight_top_mesh,
)
from rft.revit.units import mm_to_internal


class _FakeLocation(object):
    def __init__(self, rotation_rad):
        self.Rotation = rotation_rad


class _FakeFootingHost(object):
    """Stand-in for the footing FamilyInstance -- only what this adapter
    reads: ``get_BoundingBox(view)`` and ``Location.Rotation``. Not
    ``fake_revit_api.FakeColumn`` (that fixture is the column tool's own;
    this ticket's element isolation rule is to build the footing's own
    stand-in rather than widen or borrow a column-shaped one).
    """

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
    # A 1800x1200 footing (internal units = feet, matching mm_to_internal's
    # own conversion so this test's expected math cross-checks the exact
    # boundary the adapter uses).
    min_xyz = FakeXYZ(0.0, 0.0, 0.0)
    max_xyz = FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                       mm_to_internal(450.0))
    return _FakeFootingHost(min_xyz, max_xyz)


def _plan(x_offset_mm, y_offset_mm, mesh_bar_x_spacing_mm=None,
         mesh_bar_y_spacing_mm=None):
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=x_offset_mm,
        y_offset_mm=y_offset_mm, ld_multiplier=40.0,
        mesh_bar_x_spacing_mm=mesh_bar_x_spacing_mm,
        mesh_bar_y_spacing_mm=mesh_bar_y_spacing_mm)
    return build_footing_plan(inputs)


@pytest.fixture
def plan():
    # LD_x = 40*16 = 640mm > 300mm offset, LD_y = 40*12 = 480mm > 150mm
    # offset -- BOTH ends of BOTH bars need a hook (U-shape) with these
    # inputs.
    return _plan(x_offset_mm=300.0, y_offset_mm=150.0)


@pytest.fixture
def straight_plan():
    # LD_x = 640mm < 700mm offset, LD_y = 480mm < 500mm offset -- NEITHER
    # end of either bar needs a hook, so the placed bar is one plain
    # straight line, same shape #198's own tracer bullet always built.
    return _plan(x_offset_mm=700.0, y_offset_mm=500.0)


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


def test_a_bar_needing_no_hook_gets_exactly_one_curve(footing, straight_plan):
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, straight_plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))

    assert len(bar_x.args[7]) == 1
    assert len(bar_y.args[7]) == 1
    assert bar_x.args[3] is None  # startHook -- shape comes from curves
    assert bar_x.args[4] is None  # endHook


def test_a_bar_hooked_at_both_ends_gets_three_connected_curves(footing, plan):
    """#229, Sec 3 Story 1's "a U in elevation": leg up, straight run,
    leg up -- ONE continuous connected chain, the same "list of connected
    curves into one Rebar.CreateFromCurves call" shape the dowel array's
    own bent bars already use (R10)."""
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))

    curves_x = bar_x.args[7]
    assert len(curves_x) == 3
    # Connected: each curve's end is the next curve's start.
    assert curves_x[0].GetEndPoint(1).X == pytest.approx(
        curves_x[1].GetEndPoint(0).X)
    assert curves_x[1].GetEndPoint(1).X == pytest.approx(
        curves_x[2].GetEndPoint(0).X)


def test_the_norm_argument_is_basis_y_for_bar_x_and_basis_x_for_bar_y(
        footing, plan):
    """#229: mesh_bar_x bends in the X-Z plane (norm = BasisY);
    mesh_bar_y bends in the Y-Z plane (norm = BasisX) -- fixed per axis,
    since (unlike the dowel array's R10) the hook direction here is
    always straight up, never per-bar."""
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    norm_x = bar_x.args[6]
    norm_y = bar_y.args[6]
    assert (norm_x.X, norm_x.Y, norm_x.Z) == (0.0, 1.0, 0.0)
    assert (norm_y.X, norm_y.Y, norm_y.Z) == (1.0, 0.0, 0.0)


def test_a_bar_with_no_hooked_end_keeps_the_197_verified_basis_z_norm(
        footing, straight_plan):
    """Issue #236 (review of #229): a bar with NEITHER end hooked has no
    bend at all -- issue #197 Sec 1's own kept-write tracer bullet is the
    only live-host proof this repo has for a straight bar on a footing
    host, and it used XYZ.BasisZ, not the per-axis bent norm. Switching
    an un-bent bar to an unverified norm value would be exactly the kind
    of untested combination this repo's own zero-API-guessing rule
    exists to catch."""
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, straight_plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    norm_x = bar_x.args[6]
    norm_y = bar_y.args[6]
    assert (norm_x.X, norm_x.Y, norm_x.Z) == (0.0, 0.0, 1.0)
    assert (norm_y.X, norm_y.Y, norm_y.Z) == (0.0, 0.0, 1.0)


def test_bar_x_straight_run_is_centred_on_the_footing_and_spans_Z(
        footing, straight_plan):
    """The straight case: horizontal extent is Sec 3's own ``Z`` (the
    straight length alone), NOT ``mesh_bar_x_mm`` (which already bakes in
    two hook legs #198's old straight-only geometry wrongly folded into
    one horizontal run -- the defect #229 fixes)."""
    bar_x, _bar_y = place_straight_bottom_mesh(
        object(), footing, straight_plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    curve = bar_x.args[7][0]

    centre_x_internal = mm_to_internal(1800.0) / 2.0
    centre_y_internal = mm_to_internal(1200.0) / 2.0
    half_z_internal = mm_to_internal(
        straight_plan.bottom_mesh.lengths.z_mm / 2.0)

    p0 = curve.GetEndPoint(0)
    p1 = curve.GetEndPoint(1)
    assert p0.X == pytest.approx(centre_x_internal - half_z_internal)
    assert p1.X == pytest.approx(centre_x_internal + half_z_internal)
    assert p0.Y == pytest.approx(centre_y_internal)
    assert p1.Y == pytest.approx(centre_y_internal)


def test_a_hooked_bar_x_spans_only_Z_horizontally_not_the_full_length(
        footing, plan):
    """Same check as above, but for the hooked (U-shape) case: the
    horizontal extent across ALL of bar_x's points must still be exactly
    Z, with the two extra hook-leg points adding height, not width."""
    bar_x, _bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    xs = [point.X for curve in bar_x.args[7]
          for point in (curve.GetEndPoint(0), curve.GetEndPoint(1))]
    span_internal = max(xs) - min(xs)
    expected_internal = mm_to_internal(plan.bottom_mesh.lengths.z_mm)
    assert span_internal == pytest.approx(expected_internal)


def test_hook_legs_rise_by_N_above_the_bars_own_base_elevation(footing, plan):
    """Sec 3's ``N`` (bar_x) -- the vertical hook leg length -- must show
    up as the gap between the highest and lowest Z among bar_x's own
    points (the base elevation, present regardless of which end(s) are
    hooked, plus the raised hook end(s))."""
    bar_x, _bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    zs = [point.Z for curve in bar_x.args[7]
          for point in (curve.GetEndPoint(0), curve.GetEndPoint(1))]
    rise_internal = max(zs) - min(zs)
    expected_internal = mm_to_internal(plan.bottom_mesh.lengths.n_mm)
    assert rise_internal == pytest.approx(expected_internal)


def test_bar_y_sits_above_bar_x_by_the_mesh_bar_x_diameter(footing, plan):
    """The two bars' own BASE elevations (the lowest Z each bar reaches --
    robust to which end(s) are hooked, since hooks only ever add height)
    differ by mesh_bar_x's own diameter, the same stacking #198 always
    built."""
    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    z_x = min(point.Z for curve in bar_x.args[7]
              for point in (curve.GetEndPoint(0), curve.GetEndPoint(1)))
    z_y = min(point.Z for curve in bar_y.args[7]
              for point in (curve.GetEndPoint(0), curve.GetEndPoint(1)))

    expected_gap_internal = mm_to_internal(16.0 / 2.0 + 12.0 / 2.0)
    assert (z_y - z_x) == pytest.approx(expected_gap_internal)


@pytest.mark.parametrize("rotation_deg", [0.0, 180.0, 360.0])
def test_axis_aligned_rotations_still_place_bars(rotation_deg, plan):
    """Regression: the rotation guard must not false-refuse an
    axis-aligned footing at 0/180 deg (or a full turn, numerically 0 mod
    180 deg). Issue #246: 90/270 deg moved OUT of this accepted set --
    see the dedicated refusal test below.
    """
    footing = _FakeFootingHost(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                mm_to_internal(450.0)),
        rotation_rad=math.radians(rotation_deg))

    bar_x, bar_y = place_straight_bottom_mesh(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))

    assert bar_x.args[5] is footing
    assert bar_y.args[5] is footing


@pytest.mark.parametrize("rotation_deg", [30.0, 90.0, 270.0])
def test_a_rotated_footing_refuses_instead_of_placing_bars_wrong(
        rotation_deg, plan):
    """Spec has no rotation model, and _to_world_point has no rotation
    transform -- a rotated footing must REFUSE (Explicit Refusals,
    REUSE_GUIDELINES.md Sec 3), never silently place bars along world
    X/Y instead of the footing's own a/b directions. Issue #246: 90/270
    deg used to be wrongly accepted as "axis-aligned" -- this now must
    refuse there exactly the same as any other non-multiple-of-180 angle
    (30 deg, kept as a regression check for that pre-existing case).
    """
    footing = _FakeFootingHost(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm_to_internal(1800.0), mm_to_internal(1200.0),
                mm_to_internal(450.0)),
        rotation_rad=math.radians(rotation_deg))

    with pytest.raises(FootingRotationUnsupportedError):
        place_straight_bottom_mesh(
            object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
            _FakeBarType("12M"))


# --------------------------------------------------------------------------
# #232 (R11) -- place_bottom_mesh_bars, the array-loop wiring ONLY. The
# per-bar bent-geometry/norm mechanics are already covered above via
# place_straight_bottom_mesh / #229's own tracer bullet; this section only
# proves the LOOP.
# --------------------------------------------------------------------------


def test_place_bottom_mesh_bars_falls_back_to_one_bar_per_direction_with_no_array(
        footing, plan):
    """No spacing supplied (every caller that predates #232) -- the SAME
    single-bar-per-direction shape place_straight_bottom_mesh always
    placed, now returned as one-item lists."""
    bars_x, bars_y = place_bottom_mesh_bars(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    assert len(bars_x) == 1
    assert len(bars_y) == 1


def test_place_bottom_mesh_bars_places_every_bar_in_a_real_array(footing):
    """Z2=1100mm at 200mm spacing -> 7 mesh_bar_x bars (same hand-computed
    count tests/test_footing_mesh.py's own array tests already prove)."""
    plan = _plan(x_offset_mm=300.0, y_offset_mm=150.0,
                mesh_bar_x_spacing_mm=200.0)
    bars_x, bars_y = place_bottom_mesh_bars(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    assert len(bars_x) == 7
    assert len(bars_y) == 1  # no mesh_bar_y_spacing_mm -> fallback


def test_place_bottom_mesh_bars_hosts_every_bar_on_the_same_footing(footing):
    plan = _plan(x_offset_mm=300.0, y_offset_mm=150.0,
                mesh_bar_x_spacing_mm=200.0, mesh_bar_y_spacing_mm=200.0)
    document = object()
    bars_x, bars_y = place_bottom_mesh_bars(
        document, footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    for bar in bars_x + bars_y:
        assert bar.args[5] is footing
        assert bar.args[0] is document


def _top_plan(x_offset_mm=300.0, y_offset_mm=150.0):
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=x_offset_mm,
        y_offset_mm=y_offset_mm, ld_multiplier=40.0,
        top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM,
        # #253 (R16): the top mat's own bar diameters are REQUIRED once
        # TOP+BTM is chosen.
        top_mesh_bar_x_dia_mm=16.0, top_mesh_bar_y_dia_mm=12.0)
    return build_footing_plan(inputs)


def test_place_straight_top_mesh_hosts_both_bars_on_the_footing(footing):
    """#233 (R13): hosted on the SAME footing element as the bottom
    mesh -- there is no separate top-mat host."""
    document = object()
    plan = _top_plan()

    bar_x, bar_y = place_straight_top_mesh(
        document, footing, plan.top_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))

    assert bar_x.args[5] is footing
    assert bar_y.args[5] is footing
    assert bar_x.args[0] is document
    assert bar_y.args[0] is document


def test_place_straight_top_mesh_hooked_bar_bends_down_not_up(footing):
    """R13's own reason for existing: the top mat's hook leg must go
    DOWN toward the bottom mat, so the base elevation (the middle of the
    curve chain) must be HIGHER than the hooked end's own Z, the mirror
    image of the bottom mat's own rise."""
    plan = _top_plan()  # both ends of both bars hooked, same offsets as
    # the module's own `plan` fixture above (U-shape).
    bar_x, _bar_y = place_straight_top_mesh(
        object(), footing, plan.top_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))

    zs = [point.Z for curve in bar_x.args[7]
          for point in (curve.GetEndPoint(0), curve.GetEndPoint(1))]
    base_z = max(zs)
    hooked_z = min(zs)
    assert hooked_z < base_z
    drop_internal = base_z - hooked_z
    expected_internal = mm_to_internal(plan.top_mesh.lengths.n_mm)
    assert drop_internal == pytest.approx(expected_internal)


def test_place_straight_top_mesh_uses_the_same_per_axis_norm_as_the_bottom_mat(
        footing):
    """R13 changes which way a hooked end's leg points, not which PLANE
    it bends in -- so mesh_bar_x keeps norm = BasisY and mesh_bar_y keeps
    norm = BasisX, exactly as the bottom mat's own #229 rule."""
    plan = _top_plan()
    bar_x, bar_y = place_straight_top_mesh(
        object(), footing, plan.top_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    norm_x = bar_x.args[6]
    norm_y = bar_y.args[6]
    assert (norm_x.X, norm_x.Y, norm_x.Z) == (0.0, 1.0, 0.0)
    assert (norm_y.X, norm_y.Y, norm_y.Z) == (1.0, 0.0, 0.0)


def test_place_straight_top_mesh_straight_bar_keeps_the_verified_basis_z_norm(
        footing):
    plan = _top_plan(x_offset_mm=700.0, y_offset_mm=500.0)  # neither end
    # of either bar needs a hook with these offsets (same LD math as the
    # module's own straight_plan fixture above).
    bar_x, bar_y = place_straight_top_mesh(
        object(), footing, plan.top_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    norm_x = bar_x.args[6]
    norm_y = bar_y.args[6]
    assert (norm_x.X, norm_x.Y, norm_x.Z) == (0.0, 0.0, 1.0)
    assert (norm_y.X, norm_y.Y, norm_y.Z) == (0.0, 0.0, 1.0)


def test_place_bottom_mesh_bars_gives_each_bar_x_a_distinct_y_offset(footing):
    """The array's own reason for existing: consecutive bars must not sit
    on top of each other."""
    plan = _plan(x_offset_mm=300.0, y_offset_mm=150.0,
                mesh_bar_x_spacing_mm=200.0)
    bars_x, _bars_y = place_bottom_mesh_bars(
        object(), footing, plan.bottom_mesh, _FakeBarType("16M"),
        _FakeBarType("12M"))
    ys = [bar.args[7][0].GetEndPoint(0).Y for bar in bars_x]
    assert len(set(ys)) == len(ys)
