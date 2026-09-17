# -*- coding: utf-8 -*-
"""Issue #118 -- the tie placer: 2 of 4 in the column's placement pipeline.

Builds every tie a ``ColumnPlan`` (#110) carries, at every level of its
ladder, in the host column. **Creates elements only.** It never opens,
commits or rolls back a transaction -- R25 makes the caller own the whole
cage's transaction, deletions and rebuild together, so a single tie loop
cannot leave the model half built.

Spec: `specs/column-rft-detailing.md` Sec.4-6; `docs/column/spec-amendments.md`
A1, R21.

## Two rules this module exists to enforce, not merely apply

**R21 -- hooks turn inward, ``Left``/``Left``, asserted, not assumed.**
`docs/column/verification/issue-109-kept-write-tracer-bullet.md` Finding 4:
`RebarHookOrientation.Right` on both ends builds without complaint and
throws both 135deg hook tails OUTSIDE the concrete. Only `Left`/`Left`
turns them into the core, for the winding this module builds -- and the
orientation enum is interpreted against that winding, not an absolute
sense, so the constant is right only as long as the winding below does not
change without this module changing with it (#78's own caveat). The
assertion in :func:`_assert_hook_tails_inside_host_extent` is therefore on
the GEOMETRY that comes back, never on which constant was passed.

**A1 -- the bend threshold is checked before ANYTHING is offered to
Revit.** #109 Finding 3: a closed loop narrower than
``bend diameter + tie diameter`` fails ABOVE `Rebar.CreateFromCurves`,
uncatchable at the call site -- no null, no exception a `try`/`except`
here could see. So :func:`_ensure_buildable` runs for every tie in the
plan BEFORE the first element is created, and it does not trust
``tie.kind`` alone: it recomputes the same narrow-vs-minimum comparison
``rft.core.column_ties.resolve_tie`` already made, so a plan whose label
and numbers ever disagree is still refused here.

## Read-back discipline (#109 Finding 1, Finding 2 corrected)

Reading geometry back in the SAME transaction as the write returns the
REQUESTED curves, not the as-built ones -- true of POSITION, which drifts
a couple of millimetres on regeneration. It is not true of which side of
the tie a hook tail lands on: that is a topological fact fixed by which
`RebarHookOrientation` was passed and the winding of the curve list, and
that value does not depend on regeneration having happened. Reading it
back immediately is exactly what R21 asks for, and is safe for the
question this module asks. A genuine as-built check belongs to a later
execution and must compare LEGS, never the extremes of the curve array
(Finding 2, withdrawn and corrected) -- this module never claims to do
that here.
"""

from Autodesk.Revit.DB import Line, XYZ
from Autodesk.Revit.DB.Structure import (
    MultiplanarOption,
    Rebar,
    RebarHookOrientation,
    RebarStyle,
)

from ..core.column_ties import KIND_CLOSED_LOOP, describe_subset
from .units import mm_to_internal


class TiePlacementError(Exception):
    """A tie this placer refuses to build, or a tie Revit built wrong.

    Raised rather than logged so a caller sharing one transaction (R25)
    cannot mistake a refusal for a success and commit a partial cage.
    """


#: R21. The ONLY `RebarHookOrientation` combination whose 135deg hook
#: tails turn INTO the core, for the winding `_closed_loop_uv_segments_mm`
#: and `_cross_tie_uv_segments_mm` build below (#109 Finding 4, #78). Never
#: trusted alone -- see `_assert_hook_tails_inside_host_extent`.
_HOOK_ORIENTATION = RebarHookOrientation.Left

#: `Rebar.CreateFromCurves`'s own defaults, matching #109's kept write and
#: every other placement module in this repo (`rft.revit.stirrups`,
#: `rft.revit.placement`): let Revit reuse a matching `RebarShape` or
#: author a new one, never author one by hand.
_USE_EXISTING_SHAPE_IF_POSSIBLE = True
_CREATE_NEW_SHAPE = True

#: VERIFIED LIVE (Revit 2024 build 24.3.40.26, RevitAPI 24.3.40.0, tie
#: 423209 in `ColumnRFT.Trail.rvt`). Both flag settings were called on the
#: same element in one execution:
#:
#:     (False, False, False, IncludeOnlyPlanarCurves, 0) -> 11 curves, 5 arcs
#:     (False, True,  True,  IncludeOnlyPlanarCurves, 0) ->  4 curves, 0 arcs
#:
#: and the hooks-included read returned the tails R21 was decided on. This
#: module wants hooks and bend radii INCLUDED, so both flags are `False`.
#: The 5-argument signature, the tolerance argument and
#: `MultiplanarOption.IncludeOnlyPlanarCurves` are confirmed, not assumed.
#: What remains unverified is the FAKE's hook-tail math, not the API --
#: see tests/fake_revit_api.py's header.
_READBACK_TOLERANCE = 0.0


def _tie_label(tie):
    return "%s (%s)" % (describe_subset(tie.subset), tie.kind)


def _ensure_buildable(tie):
    """A1's bend threshold, checked before this tie is offered to Revit.

    Recomputes the comparison rather than reading ``tie.kind`` alone: a
    ``ResolvedTie`` that says ``KIND_CLOSED_LOOP`` while its own numbers
    fail the test is refused here exactly as one that never got that far
    would be. #109 Finding 3 is why this cannot be "try it and see" --
    Revit's own refusal for an unbendable loop is not catchable at the
    call site.
    """
    if tie.kind != KIND_CLOSED_LOOP:
        return
    if tie.narrow_mm < tie.min_buildable_mm:
        raise TiePlacementError(
            "Tie %s: narrow dimension %.1f mm is below the %.1f mm A1 "
            "threshold (bend diameter + tie diameter) and cannot be bent. "
            "Refused before any element was offered to Revit -- issue #109 "
            "Finding 3 found this fails above the call site, uncatchable, "
            "so it must never be reached."
            % (_tie_label(tie), tie.narrow_mm, tie.min_buildable_mm))


def _closed_loop_uv_segments_mm(tie):
    """The tie's rectangle as 4 consecutive-corner segments, local (u, v)
    mm, wound so ``curves[0]``'s start and ``curves[-1]``'s end coincide --
    the hook-overlap corner both hooks attach to.
    """
    cu, cv, hu, hv = tie.centre_u_mm, tie.centre_v_mm, tie.half_u_mm, tie.half_v_mm
    corners = [
        (cu - hu, cv - hv),
        (cu + hu, cv - hv),
        (cu + hu, cv + hv),
        (cu - hu, cv + hv),
    ]
    n = len(corners)
    return [(corners[i], corners[(i + 1) % n]) for i in range(n)]


def _cross_tie_uv_segments_mm(tie, layout):
    """A1's fallback: one leg between the subset's two named ends -- the
    same two bars `rft.core.column_ties.resolve_tie` credits as restrained
    for a cross-tie (its first and last named indices).
    """
    start_bar = layout.bars[tie.enclosed_indices[0]]
    end_bar = layout.bars[tie.enclosed_indices[-1]]
    return [((start_bar.u_mm, start_bar.v_mm), (end_bar.u_mm, end_bar.v_mm))]


def _uv_segments_mm(tie, layout):
    if tie.kind == KIND_CLOSED_LOOP:
        return _closed_loop_uv_segments_mm(tie)
    return _cross_tie_uv_segments_mm(tie, layout)


def _build_curves(origin_point, hand_dir, facing_dir, z_internal, uv_segments_mm):
    """3D curve list for one tie at one level: maps the core's local
    (u, v) mm points into the world, at `origin_point`'s (X, Y) and
    `z_internal` -- never `origin_point.Z`, which a structural column
    reports as 0 regardless of storey (see `rft.revit.column_host`).
    """
    level_origin = XYZ(origin_point.X, origin_point.Y, z_internal)

    def to_point(uv):
        u_mm, v_mm = uv
        return (level_origin
                + hand_dir.Multiply(mm_to_internal(u_mm))
                + facing_dir.Multiply(mm_to_internal(v_mm)))

    return [Line.CreateBound(to_point(a), to_point(b)) for a, b in uv_segments_mm]


def _within(value, lo, hi):
    return lo <= value <= hi


def _assert_hook_tails_inside_host_extent(host_element, rebar, tie):
    """R21's assertion: read the centreline back WITH hooks and bend radii,
    and require both hook tails to fall inside the host's own extent.

    On the geometry that came back, never on the orientation constant that
    was passed -- the enum is interpreted against the curve winding this
    module builds, and #78 warns that winding is free to change. A
    constant that is right today because of an unstated convention
    elsewhere is exactly the coupling this project has already paid for.
    """
    box = host_element.get_BoundingBox(None)
    if box is None:
        raise TiePlacementError(
            "Tie %s: the host has no bounding box to verify its hook "
            "tails against (R21)." % _tie_label(tie))

    curves = rebar.GetCenterlineCurves(
        False, False, False, MultiplanarOption.IncludeOnlyPlanarCurves,
        _READBACK_TOLERANCE)
    if not curves:
        raise TiePlacementError(
            "Tie %s: Revit returned no centreline curves to verify hook "
            "tails against (R21)." % _tie_label(tie))

    _, start_tail, _ = curves[0]
    _, _, end_tail = curves[-1]
    for end_label, point in (("start", start_tail), ("end", end_tail)):
        if not (_within(point.X, box.Min.X, box.Max.X)
                and _within(point.Y, box.Min.Y, box.Max.Y)):
            raise TiePlacementError(
                "Tie %s: the %s hook tail falls OUTSIDE the host's extent "
                "(R21). Both 135deg hook tails must turn into the concrete "
                "core; check the hook orientation passed to "
                "Rebar.CreateFromCurves." % (_tie_label(tie), end_label))


def _place_one_tie(doc, host_element, layout, tie, bar_type, hook_type,
                   origin_point, hand_dir, facing_dir, z_internal, norm):
    curves = _build_curves(origin_point, hand_dir, facing_dir, z_internal,
                           _uv_segments_mm(tie, layout))
    rebar = Rebar.CreateFromCurves(
        doc,
        RebarStyle.StirrupTie,
        bar_type,
        hook_type,
        hook_type,
        host_element,
        norm,
        curves,
        _HOOK_ORIENTATION,
        _HOOK_ORIENTATION,
        _USE_EXISTING_SHAPE_IF_POSSIBLE,
        _CREATE_NEW_SHAPE,
    )
    _assert_hook_tails_inside_host_extent(host_element, rebar, tie)
    return rebar


def place_ties(doc, host_element, plan, bar_type, hook_type):
    """Every tie in `plan.ties`, at every level of `plan.ladder`, in
    `host_element`.

    `bar_type`/`hook_type` are the resolved `RebarBarType`/`RebarHookType`
    Revit objects -- selection lives with the caller (mirroring how the
    beam pushbuttons resolve their own bar/hook types before calling into
    `rft.revit.placement`/`rft.revit.stirrups`), not with this module.

    Opens, commits and rolls back NOTHING (R25) -- the caller owns one
    transaction for the whole cage, so a refusal here (A1) or a failed
    assertion (R21) leaves the model exactly as it was before this call,
    once the caller's `except` rolls it back.

    Returns every `Rebar` element created, in level-then-tie order.
    """
    for tie in plan.ties:
        _ensure_buildable(tie)

    origin_point = host_element.Location.Point
    hand_dir = host_element.HandOrientation
    facing_dir = host_element.FacingOrientation
    norm = XYZ.BasisZ

    created = []
    for level in plan.ladder.levels:
        z_mm = plan.extent.base_z_mm + level.z_mm
        z_internal = mm_to_internal(z_mm)
        for tie in plan.ties:
            created.append(_place_one_tie(
                doc, host_element, plan.layout, tie, bar_type, hook_type,
                origin_point, hand_dir, facing_dir, z_internal, norm))
    return created
