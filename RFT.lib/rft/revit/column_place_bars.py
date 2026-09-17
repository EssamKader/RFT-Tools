# -*- coding: utf-8 -*-
"""Issue #119 -- R22: a longitudinal bar is pinned to a host FACE, and is
never handed a coordinate and trusted to stay there.

Creates the longitudinal bars of a ``rft.core.column_plan.ColumnPlan`` in a
host column. Builds elements only -- **opens, commits and rolls back no
transaction** (R25); the caller owns it.

## The rule this module exists for -- R22

``docs/column/verification/issue-92-bar-snap-and-constraints.md`` measured a
4-bar set placed by ``Rebar.CreateFromCurves`` landing at
``dx +4.75 / dy +12.05`` from the coordinate it was given -- the corner bar
bound itself to the nearest TIE HOOK BEND (R21 turns that bend inward,
straight into where the corner bar sits) and the whole set translated with
it. Explicitly pinning each bar's in-plane handles to the host's own faces
after creation removed the drift completely and landed the bar on the exact
coordinate, not a near one.

So this module never relies on the coordinate it hands ``CreateFromCurves``.
The curve it builds is only ever a plausible STARTING guess -- R22 says the
placer must not compute an absolute XY from a bounding box, and this reads
its starting point from the host's own ``Location.Point`` plus its
``hand``/``facing`` orientation instead (both exact, unlike a bounding box
rounded for display -- #92's own residual turned out to be exactly that:
"the target came from a bounding box printed to one decimal"). Correctness
comes entirely from :func:`_pin_to_host_faces`, run on every bar regardless
of where its seed curve landed.

## Sets, not single bars (#92 Q2, superseded by R22)

#92 proposed single-bar sets to buy predictability at 19 elements instead of
8. R22 supersedes that: a PINNED 4-bar set is exact on all four bars, so
this module creates one ``Rebar`` per perimeter FACE RUN and lays the rest
out with ``SetLayoutAsNumberWithSpacing`` rather than one element per bar.

## Reading ``rft.core.column_layout``'s own structure, not recomputing it

``perimeter_bar_positions`` (#90) already returns ``layout.bars`` as four
face runs concatenated -- bottom (+u), right (+v), top (-u), left (-v) --
each run EXCLUDING its own trailing corner because that corner is the next
run's first bar (its own docstring: "four faces, four corners, each counted
once"). ``_face_run_slices`` re-slices that existing list by the counts
``plan.counts`` already carries; it does not call back into
``column_layout`` or recompute a position -- CONTEXT.md's "read ColumnPlan
once" rule.

## SHAPE UNVERIFIED

- ``Rebar.CreateFromCurves``'s ``normal`` argument for a straight,
  unhooked ``RebarStyle.Standard`` bar. #109's tracer bullet confirmed the
  call's signature for a ``StirrupTie`` loop, where ``normal`` is the axis
  the closed loop's plane turns around (``XYZ.BasisZ``). What the same
  argument means for a single vertical line has never been probed live.
  This module passes the horizontal direction perpendicular to the run's
  own spacing direction -- a defensible guess, not a confirmed one. R22's
  correctness does not depend on it: the subsequent explicit face-pin
  overrides whatever plane the bar was born on.
- ``Rebar.SetLayoutAsNumberWithSpacing(numberOfBarPositions, spacing,
  barsOnNormalSide, includeFirstBar, includeLastBar)`` -- the ticket names
  this method; its exact parameter order/types are this module's own
  reading of published Revit API documentation, not a live confirmation.
  Which direction the array grows in is entirely up to Revit's own
  handling of the seed bar's shape -- untested, and orthogonal to R22.
VERIFIED LIVE by reflection over ``RebarConstraint`` and
``RebarConstraintsManager`` (Revit 2024 build 24.3.40.26, RevitAPI
24.3.40.0): ``GetAllHandles()``, ``GetConstraintCandidatesForHandle``,
``SetPreferredConstraintForHandle``, ``IsToHostFaceOrCover()``,
``IsToCover()``, ``GetTargetElement()``,
``GetTargetHostFaceAndTransform(index, transform)`` and
``SetDistanceToTargetHostFace(offset)`` all exist with these names.

  **``GetTargetElementId()`` and a ``PlanarFace`` property do NOT exist**
  and an earlier draft of this module called both. They came from reading
  #92's write-up, which described the recipe in prose that reads like API
  names. The write-up now gives the literal calls. The lesson is the
  cheaper half: *a fake written from prose will happily match the
  invention, and a green suite then proves nothing about the host.*
"""

from System.Collections.Generic import List

from Autodesk.Revit import DB
from Autodesk.Revit.DB.Structure import Rebar, RebarHookOrientation, RebarStyle

from .units import mm_to_internal

#: Two directions are "the same axis" when their dot product with a unit
#: vector is at least this close to +-1 -- tessellation/roundoff tolerance,
#: not a real angular allowance (every face this module reasons about is
#: exactly perpendicular or exactly parallel by construction).
_AXIS_ALIGNED_TOL = 1.0e-3


def _face_run_slices(counts):
    """Index ranges into ``layout.bars`` for the four perimeter RUNS this
    module places as sets -- bottom, right, top, left, in that order.

    Reads the split back out of the deduplicated list ``perimeter_bar_
    positions`` already built (each run excludes its own trailing corner,
    which is the next run's first bar) rather than recomputing it.
    """
    n_b = counts.count_b_face - 1
    n_h = counts.count_h_face - 1
    i0 = 0
    i1 = i0 + n_b
    i2 = i1 + n_h
    i3 = i2 + n_b
    i4 = i3 + n_h
    return [(i0, i1), (i1, i2), (i2, i3), (i3, i4)]


def _dot(a, b):
    return a[0] * b[0] + a[1] * b[1] + a[2] * b[2]


def _horizontal_unit(hand, facing, delta_u_mm, delta_v_mm):
    """The unit XYZ a run's bars step along, from consecutive ``Bar``s' own
    ``(u, v)`` -- never assumed to be ``+hand``/``+facing``: the top and
    left runs step BACKWARDS (``perimeter_bar_positions`` walks the
    perimeter anticlockwise; see its own docstring).
    """
    vec = (hand[0] * delta_u_mm + facing[0] * delta_v_mm,
          hand[1] * delta_u_mm + facing[1] * delta_v_mm,
          hand[2] * delta_u_mm + facing[2] * delta_v_mm)
    length = (vec[0] ** 2 + vec[1] ** 2 + vec[2] ** 2) ** 0.5
    return (vec[0] / length, vec[1] / length, vec[2] / length)


def _perp_horizontal(direction):
    """90-degree rotation of a horizontal unit vector about Z.

    Used only as the ``normal`` handed to ``CreateFromCurves`` -- see the
    module docstring's SHAPE UNVERIFIED note. Never used for anything R22
    depends on for correctness.
    """
    return (-direction[1], direction[0], 0.0)


def _point_internal(origin, hand, facing, u_mm, v_mm, z_internal):
    """A seed point for ``CreateFromCurves`` -- the host's own
    ``Location.Point`` plus its ``hand``/``facing`` orientation, in internal
    units. R22: never a bounding box. This point is a starting guess only;
    :func:`_pin_to_host_faces` is what makes the built bar exact.
    """
    x_mm = hand[0] * u_mm + facing[0] * v_mm
    y_mm = hand[1] * u_mm + facing[1] * v_mm
    z_mm_component = hand[2] * u_mm + facing[2] * v_mm
    return DB.XYZ(origin.X + mm_to_internal(x_mm),
                 origin.Y + mm_to_internal(y_mm),
                 z_internal + mm_to_internal(z_mm_component))


def _is_near_face_normal(normal, u_mm, v_mm, hand, facing):
    """Whether ``normal`` is the OUTWARD normal of the face nearest this
    bar on the axis ``normal`` runs along.

    A face normal is (within tolerance) parallel to exactly one of
    ``hand``/``facing`` -- the column's four vertical faces are axis
    aligned in the section-local frame by construction (#69). "Near" means
    the face on the same side as the bar's own coordinate on that axis: a
    bar at positive ``u`` is nearer the ``+hand`` face than the ``-hand``
    one. A bar sitting exactly on the centreline of an axis (``u_mm`` or
    ``v_mm`` of 0) has no nearer face on that axis, and this returns
    ``False`` -- there is nothing to pin on that axis, not a coin to flip.
    """
    dot_hand = _dot(normal, hand)
    dot_facing = _dot(normal, facing)
    if abs(dot_hand) >= 1.0 - _AXIS_ALIGNED_TOL:
        return u_mm != 0.0 and (dot_hand > 0.0) == (u_mm > 0.0)
    if abs(dot_facing) >= 1.0 - _AXIS_ALIGNED_TOL:
        return v_mm != 0.0 and (dot_facing > 0.0) == (v_mm > 0.0)
    return False


def _host_face_candidate(mgr, handle, host_id, u_mm, v_mm, hand, facing):
    """R22's candidate filter for one handle: ``IsToHostFaceOrCover()``,
    **not** ``IsToCover()``, targets the host, and whose target host
    face's normal is the near face on the axis it governs.

    The ``ToCover`` candidate is deliberately excluded (#92): it re-points
    the constraint and the bar itself does not move, so accepting it would
    leave the drift R22 exists to remove while the constraint *reports* as
    fixed. Returns ``None`` when no candidate matches -- a handle with no
    matching host face (a mid-face bar's free axis) offers none, and this
    leaves it alone rather than guessing.
    """
    for candidate in mgr.GetConstraintCandidatesForHandle(handle):
        if not candidate.IsToHostFaceOrCover():
            continue
        if candidate.IsToCover():
            continue
        target = candidate.GetTargetElement()
        if target is None or target.Id != host_id:
            continue
        # The live surface offers no PlanarFace property. The face comes
        # back from GetTargetHostFaceAndTransform, and may be curved --
        # a column's own four faces are planar, anything else is not ours.
        face = candidate.GetTargetHostFaceAndTransform(
            0, DB.Transform.Identity)
        normal = getattr(face, "FaceNormal", None)
        if normal is None:
            continue
        if _is_near_face_normal(
                (normal.X, normal.Y, normal.Z), u_mm, v_mm, hand, facing):
            # FIRST match, not last. Revit returned 47-49 candidates for a
            # single handle on the live column, in an order it does not
            # document. A loop that kept going and took the last one would
            # be picking by an ordering nobody specified.
            return candidate
    return None


def _pin_to_host_faces(bar, host_id, seed, hand, facing, offset_internal):
    """R22: after creation, pin every in-plane handle to the host's own
    face -- never trust the coordinate handed to ``CreateFromCurves``.

    ``offset_internal`` is passed to ``SetDistanceToTargetHostFace``
    **negated**: #92 measured a positive offset landing the bar 57 mm
    OUTSIDE the column -- the distance is signed against the face's
    OUTWARD normal, so moving the bar INWARD from the face is negative.
    """
    mgr = bar.GetRebarConstraintsManager()
    for handle in mgr.GetAllHandles():
        candidate = _host_face_candidate(
            mgr, handle, host_id, seed.u_mm, seed.v_mm, hand, facing)
        if candidate is None:
            continue
        candidate.SetDistanceToTargetHostFace(-offset_internal)
        mgr.SetPreferredConstraintForHandle(handle, candidate)


def _place_run(doc, host_element, bar_type, run, hand, facing, origin,
              z_base_internal, z_top_internal, offset_internal):
    """One perimeter face run, as a single ``Rebar`` -- a set when the run
    holds more than one bar (R22 supersedes #92's single-bar-set proposal).
    """
    seed = run[0]
    p0 = _point_internal(origin, hand, facing, seed.u_mm, seed.v_mm,
                         z_base_internal)
    p1 = _point_internal(origin, hand, facing, seed.u_mm, seed.v_mm,
                         z_top_internal)
    curves = List[DB.Curve]()
    curves.Add(DB.Line.CreateBound(p0, p1))

    if len(run) > 1:
        direction = _horizontal_unit(
            hand, facing, run[1].u_mm - seed.u_mm, run[1].v_mm - seed.v_mm)
    else:
        # A single-bar run has no direction of its own to derive a normal
        # from; `hand` is as good a horizontal reference as any, and R22's
        # correctness never depends on this value (see the module's SHAPE
        # UNVERIFIED note).
        direction = hand
    normal = _perp_horizontal(direction)

    bar = Rebar.CreateFromCurves(
        doc, RebarStyle.Standard, bar_type, None, None, host_element,
        DB.XYZ(normal[0], normal[1], normal[2]), curves,
        RebarHookOrientation.Left, RebarHookOrientation.Left,
        True, False)

    if len(run) > 1:
        spacing_mm = ((run[1].u_mm - seed.u_mm) ** 2
                     + (run[1].v_mm - seed.v_mm) ** 2) ** 0.5
        bar.SetLayoutAsNumberWithSpacing(
            len(run), mm_to_internal(spacing_mm), True, True, True)

    _pin_to_host_faces(bar, host_element.Id, seed, hand, facing,
                       offset_internal)
    return bar


def place_bars(doc, host_element, bar_type, plan):
    """Creates every bar of ``plan.layout`` as a host-face-pinned run
    (R22). Builds elements only -- opens, commits and rolls back no
    transaction (R25); the caller owns it.

    ``bar_type`` is the ``RebarBarType`` the engineer picked. ``plan``
    never carries the Revit object itself, only ``bar_type_name`` --
    ``rft.core.column_plan`` is pure Python and holds no live references.

    Per spec section 9: the bar runs from the CURRENT floor level
    (``plan.extent.base_z_mm``) through the column's clear height and
    through the top support, protruding ``plan.splice.length_mm`` above it.
    """
    host = plan.host
    hand = host["hand"]
    facing = host["facing"]
    origin = host_element.Location.Point

    z_base_internal = mm_to_internal(plan.extent.base_z_mm)
    z_top_internal = mm_to_internal(
        plan.extent.top_z_mm + plan.splice.length_mm)
    offset_internal = mm_to_internal(plan.layout.bar_offset_mm)

    created = []
    for start, end in _face_run_slices(plan.counts):
        run = plan.layout.bars[start:end]
        if not run:
            continue
        created.append(_place_run(
            doc, host_element, bar_type, run, hand, facing, origin,
            z_base_internal, z_top_internal, offset_internal))
    return created
