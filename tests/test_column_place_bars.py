# -*- coding: utf-8 -*-
"""#119 -- R22: every longitudinal bar is pinned to a host FACE, never
handed a coordinate and trusted to stay there.

The layout numbers are the live 450 x 600 column
(``docs/column/verification/issue-92-bar-snap-and-constraints.md``,
``issue-67-q9-inner-subset-tie.md``): cover 40, tie 9.5, bar 15.9, offset
``40 + 9.5 + 15.9/2 = 57.45`` -- the exact number #92 measured a pinned bar
landing at, ``face + 57.45``.

``rft.core.column_plan.ColumnPlan`` is a large namedtuple carrying fields
this module never reads (spacing, the tie ladder, findings...). The plan
double built here (``_plan``) carries only what ``place_bars`` actually
touches -- ``host``, ``extent``, ``splice``, ``layout``, ``counts`` -- built
from the REAL ``perimeter_bar_positions`` so the face-run slicing is
exercised against genuine geometry, not a hand-typed stand-in of it.
"""

from collections import namedtuple

import pytest

from fake_revit_api import (
    FakeColumn,
    FakePlanarFace,
    FakeRebar,
    FakeRebarConstraintCandidate,
    FakeRebarConstraintsManager,
    FakeRebarHandle,
    FakeXYZ,
)

from rft.core.column_inputs import PerimeterBars
from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_plan import RoofTerminationPlan
from rft.core.column_roof import RoofBendDirection, RoofTermination
import rft.revit.column_place_bars as place_bars_module
from rft.revit.column_place_bars import place_bars

FT = 304.8


def mm(value):
    return value / FT


B, H, COVER, TIE, BAR = 450.0, 600.0, 40.0, 9.5, 15.9
OFFSET_MM = 57.45  # 40 + 9.5 + 15.9 / 2, the live-measured value
COUNT_B, COUNT_H = 3, 4

_Extent = namedtuple("_Extent", "base_z_mm top_z_mm")
_Splice = namedtuple("_Splice", "length_mm")
_Plan = namedtuple("_Plan", "host extent splice layout counts roof_termination")

HOST_ID_VALUE = 422078


def _plan(count_b=COUNT_B, count_h=COUNT_H, base_z_mm=3000.0, top_z_mm=6000.0,
         splice_mm=600.0, roof_termination=None):
    layout = perimeter_bar_positions(B, H, COVER, TIE, BAR, count_b, count_h)
    counts = PerimeterBars(count_b_face=count_b, count_h_face=count_h,
                          total_count=len(layout.bars),
                          corner_count=len(layout.corner_indices))
    host = {"hand": (1.0, 0.0, 0.0), "facing": (0.0, 1.0, 0.0)}
    return _Plan(host=host,
                extent=_Extent(base_z_mm=base_z_mm, top_z_mm=top_z_mm),
                splice=_Splice(length_mm=splice_mm),
                layout=layout,
                counts=counts,
                roof_termination=roof_termination)


def _roof_termination_plan(direction="+Hand", a_mm=175.0, b_mm=805.0):
    """A stand-in `RoofTerminationPlan` (#172), matching
    `tests/test_column_plan.py`'s own -- only the fields this module reads
    (`termination.a_mm`/`b_mm`/`direction`) are given values that matter
    here; the rest exist only because the real namedtuple requires them."""
    termination = RoofTermination(
        direction=direction, a_mm=a_mm, b_mm=b_mm, ld_mm=a_mm + b_mm,
        achieved_mm=a_mm + b_mm, shortfall_mm=0.0, free_edge=False,
        bend_loss_mm=0.0, run_limited=False)
    directions = (
        RoofBendDirection(name="+Hand", has_slab=True, available_run_mm=5000.0),
        RoofBendDirection(name="-Hand", has_slab=True, available_run_mm=5000.0),
        RoofBendDirection(name="+Facing", has_slab=True, available_run_mm=5000.0),
        RoofBendDirection(name="-Facing", has_slab=True, available_run_mm=5000.0),
    )
    return RoofTerminationPlan(
        termination=termination, directions=directions,
        floor_label="Floor 424637", thickness_mm=300.0, cover_mm=25.0,
        cover_provenance="read")


def _host():
    col = FakeColumn(element_id=HOST_ID_VALUE)
    col.Location.Point = FakeXYZ(mm(-100.0), mm(200.0), 0.0)
    return col


def _reset_pending_managers():
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = []


def _host_face_candidate(normal, host_id, to_cover=False, label="ok"):
    return FakeRebarConstraintCandidate(
        to_host_face_or_cover=True, to_cover=to_cover,
        target_element_id=host_id,
        planar_face=FakePlanarFace(FakeXYZ(*normal)), label=label)


# --------------------------------------------------------------------- #
# Every bar is created, as SETS, and no more than four elements


def test_every_bar_of_the_layout_is_placed_exactly_once():
    _reset_pending_managers()
    plan = _plan()
    bars = place_bars(doc=None, host_element=_host(), bar_type=object(),
                      plan=plan)

    total_placed = 0
    for bar in bars:
        if bar.layout_calls:
            assert len(bar.layout_calls) == 1
            total_placed += bar.layout_calls[0]["number_of_bar_positions"]
        else:
            total_placed += 1  # a single-bar run
    assert total_placed == len(plan.layout.bars)


def test_bars_are_created_as_four_FACE_RUNS_not_one_element_per_bar():
    """#92 Q2, superseded by R22: sets stay. 3 bars/b-face and 4/h-face
    perimeter is 10 unique bars (test_column_layout.py) across the four
    runs of length 2, 3, 2, 3 -- four ``Rebar`` elements, not ten."""
    _reset_pending_managers()
    plan = _plan()
    bars = place_bars(doc=None, host_element=_host(), bar_type=object(),
                      plan=plan)
    assert len(bars) == 4
    counts = sorted(call["number_of_bar_positions"]
                    for bar in bars for call in bar.layout_calls)
    assert counts == [2, 2, 3, 3]


def test_each_run_is_arrayed_ALONG_its_own_face_not_across_it():
    """A set distributes along the NORMAL its bar was created with, so the
    normal must be the run's own step direction.

    This is the test that was missing when #131 shipped. The placer handed
    `CreateFromCurves` the PERPENDICULAR of the step direction, on the
    stated belief that the normal did not matter. Every run was then
    arrayed ACROSS its own face and picked up the neighbouring face's
    spacing: on the live column two 16M bars landed 11.7 mm apart at two
    corners -- centres closer than one bar diameter, so the steel
    intersected -- in a cage that otherwise looked correct.

    Asserted as a relationship between the normal and the spacing, which
    is what actually has to agree:

      - the 450 face steps 167.55 mm and runs along `hand`
      - the 600 face steps 161.70 mm and runs along `facing`

    A perpendicular normal swaps those, and this fails.
    """
    _reset_pending_managers()
    plan = _plan()
    bars = place_bars(doc=None, host_element=_host(), bar_type=object(),
                      plan=plan)

    hand, facing = plan.host["hand"], plan.host["facing"]
    b_step = (B - 2 * OFFSET_MM) / (COUNT_B - 1)     # 167.55
    h_step = (H - 2 * OFFSET_MM) / (COUNT_H - 1)     # 161.70

    seen = []
    for bar in bars:
        assert len(bar.layout_calls) == 1
        spacing_mm = bar.layout_calls[0]["spacing"] * FT
        normal = bar.args[6]
        axis = (normal.X, normal.Y, normal.Z)
        along_hand = abs(sum(a * b for a, b in zip(axis, hand)))
        along_facing = abs(sum(a * b for a, b in zip(axis, facing)))

        if abs(spacing_mm - b_step) < 1e-6:
            assert along_hand == pytest.approx(1.0), (
                "a run stepping %.2f mm belongs to the %.0f face and must "
                "be arrayed along `hand`; got normal %r"
                % (spacing_mm, B, axis))
            seen.append("b")
        elif abs(spacing_mm - h_step) < 1e-6:
            assert along_facing == pytest.approx(1.0), (
                "a run stepping %.2f mm belongs to the %.0f face and must "
                "be arrayed along `facing`; got normal %r"
                % (spacing_mm, H, axis))
            seen.append("h")
        else:
            raise AssertionError(
                "a run stepped %.2f mm, which is neither face's spacing "
                "(%.2f / %.2f)" % (spacing_mm, b_step, h_step))

    assert sorted(seen) == ["b", "b", "h", "h"]


def test_no_two_bars_are_placed_closer_than_one_bar_diameter():
    """The symptom #131 produced, asserted directly on the layout the
    placer is handed: overlapping steel is never a detailing choice, so if
    two positions come within a bar diameter something upstream is wrong.
    """
    plan = _plan()
    points = [(bar.u_mm, bar.v_mm) for bar in plan.layout.bars]
    for i, a in enumerate(points):
        for b in points[i + 1:]:
            gap = ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5
            assert gap >= BAR, (
                "bars at %r and %r are %.2f mm apart, closer than the "
                "%.2f mm bar diameter" % (a, b, gap, BAR))


# --------------------------------------------------------------------- #
# R22 -- the offset is NEGATIVE, and mutation-proven


def test_the_face_offset_is_signed_NEGATIVE():
    """#92: a POSITIVE offset landed the bar 57 mm OUTSIDE the column. The
    value handed to ``SetDistanceToTargetHostFace`` must be negative.

    MUTATION-PROVEN: flipping the sign in
    ``rft.revit.column_place_bars._pin_to_host_faces`` (removing the
    leading ``-`` on ``offset_internal``) was applied by hand and this
    test failed with ``57.45 !=  approx(-57.45)`` before being reverted --
    see the PR description for the transcript.
    """
    handle = FakeRebarHandle("RebarPlane")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    candidate = _host_face_candidate((0.0, -1.0, 0.0), host_id)
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [candidate]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)  # one bar per corner, 4 runs of 1
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert candidate.distance_to_target_host_face == pytest.approx(-mm(OFFSET_MM))
    assert manager.preferred[handle] is candidate


# --------------------------------------------------------------------- #
# R45 -- the bent bar's FIFTH handle is never pinned


def test_a_SECOND_handle_on_the_same_axis_is_left_alone():
    """R45, measured in #173's probe: a straight bar has 4 handles, a bent
    bar has 5, and the extra one is the horizontal leg's FAR END offering
    the same axis the leg runs along (face normals (0, -1, 0) / (0, 1, 0)
    for a bend along Facing).

    Pinning it would set that far end to cover distance from the near
    face, using the SEED's coordinate -- which belongs to the vertical leg
    hundreds of millimetres away. The horizontal leg would collapse back
    onto the bar's own line and `b` would be gone, in a cage that still
    looked placed.
    """
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    vertical_leg = FakeRebarHandle("RebarPlane")
    far_end = FakeRebarHandle("RebarPlane")
    first = _host_face_candidate((0.0, -1.0, 0.0), host_id)
    second = _host_face_candidate((0.0, -1.0, 0.0), host_id)
    manager = FakeRebarConstraintsManager(
        handles=[vertical_leg, far_end],
        candidates={vertical_leg: [first], far_end: [second]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert manager.preferred[vertical_leg] is first
    assert far_end not in manager.preferred
    # And it was never touched at all -- not merely unpreferred.
    assert second.distance_to_target_host_face is None


def test_both_horizontal_axes_are_still_pinned():
    """R45 skips a REPEAT of an axis, never a different one. A straight
    bar's u and v handles must both still be pinned, or R22's whole
    correction is halved."""
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    u_handle = FakeRebarHandle("RebarPlane")
    v_handle = FakeRebarHandle("RebarPlane")
    u_candidate = _host_face_candidate((-1.0, 0.0, 0.0), host_id)
    v_candidate = _host_face_candidate((0.0, -1.0, 0.0), host_id)
    manager = FakeRebarConstraintsManager(
        handles=[u_handle, v_handle],
        candidates={u_handle: [u_candidate], v_handle: [v_candidate]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert manager.preferred[u_handle] is u_candidate
    assert manager.preferred[v_handle] is v_candidate


# --------------------------------------------------------------------- #
# R22 -- the ToCover candidate is never chosen, and the check is a
# POSITION check, not merely a label


def test_the_ToCover_candidate_is_rejected_even_when_offered_first():
    """#92's dangerous near-miss: ``ToCover`` re-points the constraint and
    the bar does not move -- afterwards it reads as fixed and is not. The
    correct candidate must be chosen and pinned; the ``ToCover`` one must
    never have ``SetDistanceToTargetHostFace`` called on it at all.

    MUTATION-PROVEN together with its companion below: commenting out the
    ``if candidate.IsToCover(): continue`` line in ``_host_face_candidate``
    was applied by hand. This ordering (``ToCover`` first) still passes
    under the mutation -- the loop keeps the LAST matching candidate, so
    the correct one being listed second wins anyway -- which is exactly
    why the companion test lists them the other way round. Together they
    close the loophole a "did the check merely never run" test would miss;
    reverted afterwards.
    """
    handle = FakeRebarHandle("RebarPlane")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    to_cover = _host_face_candidate((0.0, -1.0, 0.0), host_id,
                                    to_cover=True, label="ToCover")
    correct = _host_face_candidate((0.0, -1.0, 0.0), host_id,
                                   to_cover=False, label="host face")
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [to_cover, correct]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert manager.preferred[handle] is correct
    assert correct.distance_to_target_host_face == pytest.approx(-mm(OFFSET_MM))
    # The dangerous half of the near-miss: the rejected candidate's
    # POSITION must be untouched, since its constraint TYPE alone would
    # still read correctly afterwards (the ticket's own wording).
    assert to_cover.distance_to_target_host_face is None


def test_the_ToCover_candidate_is_rejected_when_offered_last():
    """Order must not matter -- a filter that merely picks "the last one
    seen" would pass the previous test by accident."""
    handle = FakeRebarHandle("RebarPlane")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    correct = _host_face_candidate((0.0, -1.0, 0.0), host_id,
                                   to_cover=False, label="host face")
    to_cover = _host_face_candidate((0.0, -1.0, 0.0), host_id,
                                    to_cover=True, label="ToCover")
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [correct, to_cover]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert manager.preferred[handle] is correct
    assert to_cover.distance_to_target_host_face is None


def test_the_FIRST_matching_candidate_is_taken_not_the_last():
    """Two candidates BOTH pass the filter. Which one is chosen is then
    purely a question of how the loop terminates, and nothing else in this
    file can tell the two apart -- the ToCover tests pass either way,
    because first-match and last-match both reject ToCover.

    The live column returned 47-49 candidates for a single handle, in an
    order Revit does not document. Taking the last is picking by an
    ordering nobody specified; taking the first is at least a stated rule.
    """
    handle = FakeRebarHandle("RebarPlane")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    first = _host_face_candidate((0.0, -1.0, 0.0), host_id, label="first")
    second = _host_face_candidate((0.0, -1.0, 0.0), host_id, label="second")
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [first, second]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert manager.preferred[handle] is first, (
        "the first matching candidate must win; got %r" %
        (manager.preferred[handle],))
    assert second.distance_to_target_host_face is None, (
        "a candidate the loop passed over must never be written to")


# --------------------------------------------------------------------- #
# R22 -- SetPreferredConstraintForHandle is what makes the pin stick


def test_removing_the_preferred_constraint_call_would_leave_it_unset():
    """Direct coverage of the third guard the ticket names. If
    ``mgr.SetPreferredConstraintForHandle`` were never called, ``manager.
    preferred`` stays empty -- this test would fail on that mutation
    without needing to inspect ``distance_to_target_host_face`` at all."""
    handle = FakeRebarHandle("Edge 1")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    # The bottom run's seed corner sits at (-half_u, -half_v) (count_b=2,
    # count_h=2 makes every bar a corner) -- ``-hand`` is its near face.
    candidate = _host_face_candidate((-1.0, 0.0, 0.0), host_id)
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [candidate]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert handle in manager.preferred


# --------------------------------------------------------------------- #
# A handle with no matching host-face candidate is left alone, not guessed


def test_a_handle_with_no_matching_candidate_is_left_unpinned():
    handle = FakeRebarHandle("RebarPlane")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    # Targets a DIFFERENT element -- a tie, say -- never the host.
    foreign = FakeRebarConstraintCandidate(
        to_host_face_or_cover=True, to_cover=False,
        target_element_id="some other element",
        planar_face=FakePlanarFace(FakeXYZ(0.0, -1.0, 0.0)))
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [foreign]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert handle not in manager.preferred
    assert foreign.distance_to_target_host_face is None


def test_a_candidate_on_the_FAR_face_is_never_chosen():
    """The bottom run's seed corner sits at (-half_u, -half_v)
    (count_b=2, count_h=2 makes every bar a corner) -- its near face on
    the `u` axis is ``-hand``. Offering BOTH the near and the far `u`-face
    candidate for the same handle must still choose the near one, in
    either order."""
    handle = FakeRebarHandle("Edge 1")
    host_id = FakeColumn(element_id=HOST_ID_VALUE).Id
    near = _host_face_candidate((-1.0, 0.0, 0.0), host_id, label="near (-u)")
    far = _host_face_candidate((1.0, 0.0, 0.0), host_id, label="far (+u)")
    manager = FakeRebarConstraintsManager(
        handles=[handle], candidates={handle: [far, near]})
    FakeRebar.PENDING_CONSTRAINTS_MANAGERS = [manager]

    plan = _plan(count_b=2, count_h=2)
    host = _host()
    host.Id = host_id
    place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)

    assert manager.preferred[handle] is near
    assert far.distance_to_target_host_face is None


# --------------------------------------------------------------------- #
# R22 -- never a bounding box


def test_the_host_bounding_box_is_never_consulted():
    """R22's rule stated plainly: a placer computing absolute XY from a
    bounding box inherits the host's own coordinate noise. This module
    reads only ``Location.Point`` and the plan's ``hand``/``facing`` --
    proven here by making ``get_BoundingBox`` explode if it is ever
    called."""
    _reset_pending_managers()
    host = _host()

    def _boom(_view):
        raise AssertionError("get_BoundingBox must never be called")

    host.get_BoundingBox = _boom
    place_bars(doc=None, host_element=host, bar_type=object(), plan=_plan())


def test_the_seed_point_comes_from_LOCATION_POINT_not_a_bounding_box():
    _reset_pending_managers()
    host = _host()
    plan = _plan(count_b=2, count_h=2)
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)

    # The first run created is "bottom": corner at (-half_u, -half_v).
    seed = plan.layout.bars[0]
    curve_args = bars[0].args
    curves = curve_args[7]
    p0 = curves[0].GetEndPoint(0)
    expected_x = host.Location.Point.X + mm(seed.u_mm)
    expected_y = host.Location.Point.Y + mm(seed.v_mm)
    assert p0.X == pytest.approx(expected_x)
    assert p0.Y == pytest.approx(expected_y)


def test_the_bar_runs_from_the_floor_level_through_the_splice_protrusion():
    """Spec section 9: base_z_mm to top_z_mm + L_s."""
    _reset_pending_managers()
    host = _host()
    plan = _plan(base_z_mm=3000.0, top_z_mm=6000.0, splice_mm=600.0)
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)
    curves = bars[0].args[7]
    p0, p1 = curves[0].GetEndPoint(0), curves[0].GetEndPoint(1)
    assert p0.Z == pytest.approx(mm(3000.0))
    assert p1.Z == pytest.approx(mm(6600.0))


# --------------------------------------------------------------------- #
# No transaction is opened, committed or rolled back here (R25)


def test_no_transaction_verb_appears_in_this_module():
    import inspect

    source = inspect.getsource(place_bars_module)
    for verb in ("Transaction(", ".Commit(", ".RollBack(", ".Start()"):
        assert verb not in source, \
            "R25: the caller owns the transaction, not this module"


# --------------------------------------------------------------------- #
# #173 -- a plan carrying a top-floor termination builds TWO curves


def test_an_ORDINARY_column_is_still_ONE_curve_byte_for_byte():
    """No `roof_termination`: every bar must be exactly what it was before
    #173 -- one straight `Line`, base to top plus the splice protrusion.
    This is the regression #173's ticket demands be ASSERTED, not assumed.
    """
    _reset_pending_managers()
    host = _host()
    plan = _plan(base_z_mm=3000.0, top_z_mm=6000.0, splice_mm=600.0)
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)
    for bar in bars:
        curves = bar.args[7]
        assert len(curves) == 1
        p0, p1 = curves[0].GetEndPoint(0), curves[0].GetEndPoint(1)
        assert p0.Z == pytest.approx(mm(3000.0))
        assert p1.Z == pytest.approx(mm(6600.0))


def test_a_roof_terminated_bar_is_built_from_TWO_curves():
    _reset_pending_managers()
    host = _host()
    plan = _plan(count_b=2, count_h=2, base_z_mm=3000.0, top_z_mm=6000.0,
                roof_termination=_roof_termination_plan(
                    direction="+Hand", a_mm=175.0, b_mm=805.0))
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)
    for bar in bars:
        assert len(bar.args[7]) == 2


def test_the_vertical_leg_runs_from_base_to_the_bend_at_top_plus_a():
    """Section 1: the bend sits at the host's own top `z` plus `a_mm` --
    never the splice protrusion, which does not apply at the roof."""
    _reset_pending_managers()
    host = _host()
    plan = _plan(count_b=2, count_h=2, base_z_mm=3000.0, top_z_mm=6000.0,
                splice_mm=600.0,
                roof_termination=_roof_termination_plan(
                    direction="+Hand", a_mm=175.0, b_mm=805.0))
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)
    vertical = bars[0].args[7][0]
    p0, p_bend = vertical.GetEndPoint(0), vertical.GetEndPoint(1)
    assert p0.Z == pytest.approx(mm(3000.0))
    assert p_bend.Z == pytest.approx(mm(6175.0))
    # The bend does not move the bar in plan -- only the horizontal leg
    # (the second curve) does that.
    assert p_bend.X == pytest.approx(p0.X)
    assert p_bend.Y == pytest.approx(p0.Y)


def test_the_horizontal_leg_runs_b_mm_along_the_stated_direction():
    _reset_pending_managers()
    host = _host()
    plan = _plan(count_b=2, count_h=2, base_z_mm=3000.0, top_z_mm=6000.0,
                roof_termination=_roof_termination_plan(
                    direction="+Hand", a_mm=175.0, b_mm=805.0))
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)
    horizontal = bars[0].args[7][1]
    p_bend, p_end = horizontal.GetEndPoint(0), horizontal.GetEndPoint(1)
    hand = plan.host["hand"]
    assert p_end.X == pytest.approx(p_bend.X + mm(805.0) * hand[0])
    assert p_end.Y == pytest.approx(p_bend.Y + mm(805.0) * hand[1])
    # `+Hand` bends in-plane; the bend does not lift or drop the bar.
    assert p_end.Z == pytest.approx(p_bend.Z)


def test_a_MINUS_facing_bend_moves_the_opposite_way_from_facing():
    _reset_pending_managers()
    host = _host()
    plan = _plan(count_b=2, count_h=2, base_z_mm=3000.0, top_z_mm=6000.0,
                roof_termination=_roof_termination_plan(
                    direction="-Facing", a_mm=175.0, b_mm=400.0))
    bars = place_bars(doc=None, host_element=host, bar_type=object(),
                      plan=plan)
    horizontal = bars[0].args[7][1]
    p_bend, p_end = horizontal.GetEndPoint(0), horizontal.GetEndPoint(1)
    facing = plan.host["facing"]
    assert p_end.X == pytest.approx(p_bend.X - mm(400.0) * facing[0])
    assert p_end.Y == pytest.approx(p_bend.Y - mm(400.0) * facing[1])


def test_an_unknown_bend_direction_is_refused_not_guessed():
    _reset_pending_managers()
    host = _host()
    bad = _roof_termination_plan(direction="+Up", a_mm=175.0, b_mm=400.0)
    plan = _plan(count_b=2, count_h=2, roof_termination=bad)
    with pytest.raises(ValueError):
        place_bars(doc=None, host_element=host, bar_type=object(), plan=plan)
