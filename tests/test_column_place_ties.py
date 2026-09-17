# -*- coding: utf-8 -*-
"""#118 -- the tie placer, run against stand-in Revit types.

Builds a small, realistic `ColumnPlan`-shaped fixture (real
`rft.core.column_layout`/`rft.core.column_ties` output, a hand-built
ladder for a deterministic level count) and drives
`rft.revit.column_place_ties.place_ties` against `FakeColumn` and
`FakeRebar`.

The host's bounding box below is the column's OWN concrete extent (a
450 x 600 section, centred on `Location.Point`), because that is what R21
means by "the host's extent" -- not a project bounding box.
"""

import pytest

from fake_revit_api import (
    FakeBoundingBox,
    FakeColumn,
    FakeRebarHookOrientation,
    FakeXYZ,
)

import rft.revit.column_place_ties as place_ties_module
from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_ties import (
    KIND_CLOSED_LOOP,
    KIND_CROSS_TIE,
    ResolvedTie,
    TieSubset,
    outer_perimeter_subset,
    resolve_tie,
)
from rft.core.column_tie_levels import TieLadder, TieLevel, ZONE_MIDDLE
from rft.revit.column_place_ties import TiePlacementError, place_ties

FT = 304.8

B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM = 450.0, 600.0, 40.0, 9.5, 15.9
BEND_DIAMETER_MM = 40.0          # 10M StirrupTieBendDiameter, per test_column_ties.py
MIN_BUILDABLE_MM = BEND_DIAMETER_MM + TIE_DIA_MM


def mm(value):
    return value / FT


class _Plan(object):
    """Only the attributes `place_ties` reads: `.ties`, `.ladder`,
    `.extent` (`.base_z_mm`), `.layout`. Not a real `ColumnPlan` -- that
    object is composed elsewhere (#110) and this ticket consumes it, never
    rebuilds it; a plain stand-in keeps this suite from depending on every
    field `bar_plan`/`complete_plan` also carry.
    """

    def __init__(self, ties, ladder, base_z_mm, layout):
        self.ties = ties
        self.ladder = ladder
        self.layout = layout

        class _Extent(object):
            pass

        self.extent = _Extent()
        self.extent.base_z_mm = base_z_mm


def _layout():
    return perimeter_bar_positions(
        B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM,
        count_b_face=3, count_h_face=4)


def _outer_tie(layout):
    return resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                       TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)


def _ladder(levels):
    """`levels` as a list of z_mm; zone/mirrored are irrelevant here --
    `place_ties` reads only `.index`/`.z_mm`."""
    return TieLadder(
        levels=[TieLevel(index=i, z_mm=z, zone=ZONE_MIDDLE, mirrored=False)
               for i, z in enumerate(levels)],
        bottom_count=0, middle_count=len(levels), top_count=0,
        middle_spacing_mm=0.0)


def _host_with_box(half_u_mm, half_v_mm):
    """A column whose bounding box IS its own concrete extent -- half
    `B_MM`/`H_MM` in world X/Y -- because R21's "host's extent" means the
    column's own solid, not a project bounding box.
    """
    col = FakeColumn()
    col._box = FakeBoundingBox(
        FakeXYZ(mm(-half_u_mm), mm(-half_v_mm), mm(0.0)),
        FakeXYZ(mm(half_u_mm), mm(half_v_mm), mm(9000.0)))
    return col


def _place(plan, host=None):
    doc = object()
    bar_type, hook_type = object(), object()
    return place_ties(doc, host or _host_with_box(B_MM / 2.0, H_MM / 2.0),
                      plan, bar_type, hook_type)


# --------------------------------------------------------------------- #
# Acceptance: ties created at every ladder level, using the plan's own
# spacings and topology.


def test_a_tie_is_created_for_every_level_times_every_tie():
    layout = _layout()
    outer = _outer_tie(layout)
    plan = _Plan(ties=[outer], ladder=_ladder([50.0, 150.0, 250.0]),
                base_z_mm=3000.0, layout=layout)

    created = _place(plan)

    assert len(created) == 3
    for rebar in created:
        assert rebar.args[1] is place_ties_module.RebarStyle.StirrupTie


def test_multiple_ties_are_all_built_at_every_level():
    layout = _layout()
    outer = _outer_tie(layout)
    # Bars 1 and 6, on this 3x4 layout, face each other across the WIDE
    # (h) direction -- a plausible inner subset, resolved as a real
    # ResolvedTie rather than hand-built, so its kind is whatever the
    # actual geometry says.
    inner = resolve_tie(TieSubset(indices=(1, 6)), layout,
                        TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    plan = _Plan(ties=[outer, inner], ladder=_ladder([50.0, 150.0]),
                base_z_mm=3000.0, layout=layout)

    created = _place(plan)

    assert len(created) == 4  # 2 levels x 2 ties


def test_the_z_used_is_the_plan_s_base_PLUS_the_ladder_s_own_offset():
    """`place_ties` must read `plan.ladder`'s BUILT levels, not recompute
    them -- the whole point of #110's composed plan.
    """
    layout = _layout()
    outer = _outer_tie(layout)
    plan = _Plan(ties=[outer], ladder=_ladder([777.0]),
                base_z_mm=3000.0, layout=layout)

    created = _place(plan)
    curves = created[0].args[7]
    # Every corner of the outer tie shares the same world Z.
    p0, p1 = curves[0].GetEndPoint(0), curves[0].GetEndPoint(1)
    assert p0.Z == pytest.approx(mm(3000.0 + 777.0))
    assert p1.Z == pytest.approx(mm(3000.0 + 777.0))


# --------------------------------------------------------------------- #
# R21: hooks turn inward, Left/Left, asserted on the geometry that comes
# back -- not merely on which constant was passed.


def test_every_created_tie_passes_Left_Left_to_CreateFromCurves():
    layout = _layout()
    outer = _outer_tie(layout)
    plan = _Plan(ties=[outer], ladder=_ladder([50.0]),
                base_z_mm=3000.0, layout=layout)

    rebar = _place(plan)[0]
    assert rebar.args[8] is FakeRebarHookOrientation.Left
    assert rebar.args[9] is FakeRebarHookOrientation.Left


def test_hook_tails_are_verified_by_reading_the_geometry_back():
    """Left/Left, on this module's own winding, must read back with both
    tails inside the host's own extent -- proven against the fake's
    winding-aware hook-tail model (see fake_revit_api.py's header for what
    it does and does not prove).
    """
    layout = _layout()
    outer = _outer_tie(layout)
    plan = _Plan(ties=[outer], ladder=_ladder([50.0]),
                base_z_mm=3000.0, layout=layout)

    rebar = _place(plan)[0]  # would have raised TiePlacementError otherwise
    curves = rebar.GetCenterlineCurves(False, False, False, None, 0.0)
    box = rebar.args[5].get_BoundingBox(None)
    start_tail = curves[0].GetEndPoint(0)
    end_tail = curves[len(curves) - 1].GetEndPoint(1)
    for point in (start_tail, end_tail):
        assert box.Min.X <= point.X <= box.Max.X
        assert box.Min.Y <= point.Y <= box.Max.Y


def test_a_hook_orientation_that_turns_the_tail_OUTWARD_is_caught(monkeypatch):
    """The mutation this ticket names explicitly: `Left` flipped to
    `Right`. Caught by the tail assertion reading the geometry back, not
    by grepping the module source for the word `Left`.
    """
    layout = _layout()
    outer = _outer_tie(layout)
    plan = _Plan(ties=[outer], ladder=_ladder([50.0]),
                base_z_mm=3000.0, layout=layout)

    monkeypatch.setattr(place_ties_module, "_HOOK_ORIENTATION",
                        FakeRebarHookOrientation.Right)
    with pytest.raises(TiePlacementError) as caught:
        _place(plan)
    assert "OUTSIDE" in str(caught.value)


def test_mixed_orientations_are_also_caught():
    """Belt and braces on the assertion itself, independent of
    `place_ties`: a start hook turned outward is caught even if the end
    hook is correct.
    """
    layout = _layout()
    outer = _outer_tie(layout)
    host = _host_with_box(B_MM / 2.0, H_MM / 2.0)
    doc, bar_type, hook_type = object(), object(), object()

    from rft.revit.column_place_ties import (
        _build_curves,
        _uv_segments_mm,
    )
    curves = _build_curves(host.Location.Point, host.HandOrientation,
                           host.FacingOrientation, mm(3050.0),
                           _uv_segments_mm(outer, layout))
    rebar = place_ties_module.Rebar.CreateFromCurves(
        doc, place_ties_module.RebarStyle.StirrupTie, bar_type, hook_type,
        hook_type, host, place_ties_module.XYZ.BasisZ, curves,
        FakeRebarHookOrientation.Right, FakeRebarHookOrientation.Left,
        True, True)
    with pytest.raises(TiePlacementError):
        place_ties_module._assert_hook_tails_inside_host_extent(host, rebar, outer)


# --------------------------------------------------------------------- #
# A1: the bend threshold is checked before ANYTHING is offered to Revit.


def test_a_subthreshold_loop_is_refused_before_any_element_is_created():
    layout = _layout()
    bad = ResolvedTie(
        subset=TieSubset(indices=(1, 2)), kind=KIND_CLOSED_LOOP,
        enclosed_indices=[1, 2], restrained_indices=[1, 2],
        centre_u_mm=0.0, centre_v_mm=0.0, half_u_mm=12.7, half_v_mm=12.7,
        narrow_mm=25.4, min_buildable_mm=MIN_BUILDABLE_MM, reason="",
        vertices=[])  # A1 refuses this tie before any geometry is read.
    plan = _Plan(ties=[bad], ladder=_ladder([50.0, 150.0]),
                base_z_mm=3000.0, layout=layout)

    with pytest.raises(TiePlacementError) as caught:
        _place(plan)
    message = str(caught.value)
    assert "1 2" in message
    assert "25.4" in message
    assert "%.1f" % MIN_BUILDABLE_MM in message


def test_the_refusal_does_not_trust_kind_ALONE(monkeypatch):
    """#109 Finding 3: the placer must not merely believe `tie.kind` --
    it recomputes narrow-vs-minimum itself. A `ResolvedTie` mislabelled
    `KIND_CLOSED_LOOP` with a failing narrow dimension must still be
    refused."""
    from rft.core.column_ties import minimum_buildable_narrow_mm

    bad = ResolvedTie(
        subset=TieSubset(indices=(0, 1, 2, 3)), kind=KIND_CLOSED_LOOP,
        enclosed_indices=[0, 1, 2, 3], restrained_indices=[0, 1, 2, 3],
        centre_u_mm=0.0, centre_v_mm=0.0, half_u_mm=12.0, half_v_mm=12.0,
        narrow_mm=24.0,
        min_buildable_mm=minimum_buildable_narrow_mm(BEND_DIAMETER_MM, TIE_DIA_MM),
        reason="", vertices=[])  # _ensure_buildable never reads geometry.
    with pytest.raises(TiePlacementError):
        place_ties_module._ensure_buildable(bad)


def test_a_cross_tie_is_never_gated_by_A1_its_geometry_is_not_a_loop():
    layout = _layout()
    cross = resolve_tie(TieSubset(indices=(1, 6)), layout, TIE_DIA_MM,
                        BAR_DIA_MM, BEND_DIAMETER_MM)
    # Whichever this layout produces, A1 must not block a CROSS_TIE --
    # only a mislabelled/failing CLOSED_LOOP triggers a refusal.
    place_ties_module._ensure_buildable(cross)  # must not raise


def test_no_element_at_all_is_created_when_A1_refuses():
    layout = _layout()
    bad = ResolvedTie(
        subset=TieSubset(indices=(1, 2)), kind=KIND_CLOSED_LOOP,
        enclosed_indices=[1, 2], restrained_indices=[1, 2],
        centre_u_mm=0.0, centre_v_mm=0.0, half_u_mm=12.7, half_v_mm=12.7,
        narrow_mm=25.4, min_buildable_mm=MIN_BUILDABLE_MM, reason="",
        vertices=[])  # A1 refuses this tie before any geometry is read.
    good = _outer_tie(layout)
    # The bad tie is SECOND: if the pre-check ran per-tie inside the loop
    # rather than over the whole plan up front, the good tie would already
    # have been created by the time the bad one is reached.
    plan = _Plan(ties=[good, bad], ladder=_ladder([50.0]),
                base_z_mm=3000.0, layout=layout)

    with pytest.raises(TiePlacementError):
        _place(plan)


# --------------------------------------------------------------------- #
# R25: this module owns no transaction at all.


def test_the_module_imports_no_Transaction_type():
    import inspect

    source = inspect.getsource(place_ties_module)
    assert "Transaction" not in source


def test_the_module_never_calls_Start_Commit_or_RollBack():
    import inspect

    source = inspect.getsource(place_ties_module)
    for forbidden in (".Start(", ".Commit(", ".RollBack("):
        assert forbidden not in source
