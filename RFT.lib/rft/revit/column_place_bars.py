# -*- coding: utf-8 -*-
"""Issue #119 -- R22: a longitudinal bar is pinned to a host FACE, and is
never handed a coordinate and trusted to stay there.

Issue #173 extends this to the top-floor case: a bar whose plan carries a
``rft.core.column_plan.RoofTerminationPlan`` is built from TWO curves --
the vertical leg up to the bend, then the horizontal leg bent into the
slab -- instead of one. Everything about WHERE the bend happens and how
long each leg is comes from ``rft.core.column_roof.RoofTermination``,
already decided by the plan (section 4's own object, per
``docs/token-efficient-expansion.md`` section 7): this module reads
``termination.a_mm``/``b_mm``/``direction`` and places them, and decides
nothing about the split itself. R40's fillet allowance is already folded
into those two lengths -- "the plan's legs are already the NOMINAL ones
with the allowance in them" -- so this module does not add or subtract it
again.

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

- **(#173) A bent bar's SET normal is unmeasured against an ARRAYED run.**
  #161 measured ``normal = Facing`` accepted for ONE bar bending in the
  Z/Hand plane -- not arrayed, not a set. This module still passes the
  run's own step ``direction`` as ``normal`` (R131's proven rule --
  #131 shipped overlapping steel from getting that argument wrong for a
  STRAIGHT set, and that fix is not given up here). For a run whose step
  direction and whose bend direction are the SAME axis (e.g. a bottom-face
  run, stepping along Hand, bending toward ``+Hand``), that is the exact
  combination #161 tried on a single bar, just now arrayed. For a run
  bending ACROSS its own step axis (e.g. a left/right-face run, stepping
  along Facing, bending toward ``+Hand``) nothing has ever confirmed that
  ``SetLayoutAsNumberWithSpacing`` still arrays correctly AND each bar's
  bend still lands in its own plane at the same time -- the two roles
  ``normal`` plays (array axis, bend-plane normal) have only ever been
  tested separately. **Proposed live probe**: build a bent, multi-bar
  SET on a face whose step axis differs from its bend direction and read
  back both ``GetCenterlineCurves`` (to see whether the bend rendered) and
  the array spacing (to see whether the bars still landed at the requested
  pitch) on each bar the set produced.
- **(#173) ``_pin_to_host_faces`` is unproven for a bent bar's extra
  handle(s).** It was written, and mutation-proven, against a straight
  bar's handles, all of which sit at the SAME ``(u_mm, v_mm)`` for the
  bar's whole length -- #92's own finding. A bent bar's horizontal leg
  introduces at least one more handle (the bend itself, if not the
  horizontal leg's own end), and this function has no way to know that
  handle should NOT be tested against the seed's vertical-leg ``(u_mm,
  v_mm)``: it would either find no matching host face (left alone, safe)
  or -- unverified -- match one it should not, on a bar whose horizontal
  leg genuinely sits at a different in-plane position once bent. No fake
  can prove which happens, because the fake's ``GetAllHandles()`` only
  ever returns what a test arms it with. **Proposed live probe**: place a
  single bent bar on the live host used for #161/#92, call
  ``GetRebarConstraintsManager().GetAllHandles()`` on it, and compare the
  handle count and each handle's constraint candidates against the
  straight-bar baseline #92 already measured.
- ``Rebar.CreateFromCurves``'s ``normal`` argument for a straight,
  unhooked ``RebarStyle.Standard`` bar. #109's tracer bullet confirmed the
  call's signature for a ``StirrupTie`` loop, where ``normal`` is the axis
  the closed loop's plane turns around (``XYZ.BasisZ``). What the same
  argument means for a single vertical line has never been probed live.
  This module passes the horizontal direction perpendicular to the run's
  own spacing direction -- a defensible guess, not a confirmed one. R22's
  correctness does not depend on it: the subsequent explicit face-pin
  overrides whatever plane the bar was born on.
- VERIFIED LIVE: the layout method is
  ``Rebar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
  numberOfBarPositions, spacing, barsOnNormalSide, includeFirstBar,
  includeLastBar)`` -- that exact parameter order, confirmed by reflection
  over ``RebarShapeDrivenAccessor`` on Revit 2024 build 24.3.40.26.
  ``Rebar`` itself has no such member, and the whole sequence was then run
  live in an aborted transaction.
- (superseded) ``Rebar.SetLayoutAsNumberWithSpacing(numberOfBarPositions, spacing,
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


def _bend_direction_vector(name, hand, facing):
    """The unit XYZ (as a plain tuple) a top-floor bend's horizontal leg
    runs along, from ``rft.core.column_roof_slab.BEND_DIRECTION_NAMES``'
    own four names -- the same names ``rft.core.column_roof.terminate_bar``
    chose among (#173). Never re-derived from geometry: ``hand``/``facing``
    are the host's own orientation, exactly as every other seed point in
    this module reads them.
    """
    if name == "+Hand":
        return hand
    if name == "-Hand":
        return (-hand[0], -hand[1], -hand[2])
    if name == "+Facing":
        return facing
    if name == "-Facing":
        return (-facing[0], -facing[1], -facing[2])
    raise ValueError(
        "Unknown bend direction %r; expected one of +Hand, -Hand, "
        "+Facing, -Facing." % (name,))


def _offset_point_internal(point, direction, distance_mm):
    """``point`` (internal units) moved ``distance_mm`` along ``direction``
    (a plain unit ``(x, y, z)`` tuple) -- the top-floor bend's horizontal
    leg (#173), built the same way :func:`_point_internal` builds the
    vertical seed: convert at the boundary, never store a value in feet.
    """
    return DB.XYZ(point.X + mm_to_internal(direction[0] * distance_mm),
                 point.Y + mm_to_internal(direction[1] * distance_mm),
                 point.Z + mm_to_internal(direction[2] * distance_mm))


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


def _axis_of_normal(normal, hand, facing):
    """Which horizontal axis a face normal runs along -- ``"u"``, ``"v"``,
    or ``None`` for a vertical face. R45 needs it to notice that two
    handles govern the SAME axis."""
    if abs(_dot(normal, hand)) >= 1.0 - _AXIS_ALIGNED_TOL:
        return "u"
    if abs(_dot(normal, facing)) >= 1.0 - _AXIS_ALIGNED_TOL:
        return "v"
    return None


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
            return candidate, _axis_of_normal(
                (normal.X, normal.Y, normal.Z), hand, facing)
    return None, None


def _pin_to_host_faces(bar, host_id, seed, hand, facing, offset_internal):
    """R22: after creation, pin every in-plane handle to the host's own
    face -- never trust the coordinate handed to ``CreateFromCurves``.

    ``offset_internal`` is passed to ``SetDistanceToTargetHostFace``
    **negated**: #92 measured a positive offset landing the bar 57 mm
    OUTSIDE the column -- the distance is signed against the face's
    OUTWARD normal, so moving the bar INWARD from the face is negative.
    """
    mgr = bar.GetRebarConstraintsManager()
    # R45: at most ONE handle per horizontal axis, the first offered.
    #
    # A straight bar has four handles -- one governing u, one v, and two
    # vertical ones that offer no horizontal face and are already left
    # alone. A BENT bar has FIVE (#173's probe, measured): the extra one
    # is the horizontal leg's far end, and it offers the SAME axis as the
    # leg runs along.
    #
    # Pinning that fifth handle would set the leg's far END to cover
    # distance from the near face -- using the SEED's own coordinate,
    # which belongs to the vertical leg hundreds of millimetres away. The
    # horizontal leg would be dragged back to the bar's own line and
    # `b` would be destroyed, in a cage that still looked placed.
    pinned_axes = set()
    for handle in mgr.GetAllHandles():
        candidate, axis = _host_face_candidate(
            mgr, handle, host_id, seed.u_mm, seed.v_mm, hand, facing)
        if candidate is None:
            continue
        if axis in pinned_axes:
            continue
        candidate.SetDistanceToTargetHostFace(-offset_internal)
        mgr.SetPreferredConstraintForHandle(handle, candidate)
        pinned_axes.add(axis)


def _place_run(doc, host_element, bar_type, run, hand, facing, origin,
              z_base_internal, top_z_mm, splice_length_mm, offset_internal,
              termination):
    """One perimeter face run, as a single ``Rebar`` -- a set when the run
    holds more than one bar (R22 supersedes #92's single-bar-set proposal).

    ``termination`` is ``plan.roof_termination.termination`` (a
    ``rft.core.column_roof.RoofTermination``) or ``None``. ``None`` is the
    ordinary column -- one straight ``Line`` from the floor level through
    the splice protrusion, unchanged since #119. A stated termination
    (#173) builds TWO curves instead: the vertical leg up to the bend,
    read from the host's own top ``z`` plus ``termination.a_mm``, then the
    horizontal leg of ``termination.b_mm`` along ``termination.direction``.
    Both legs are the NOMINAL corner-to-corner lengths the plan already
    carries with R40's fillet allowance folded in -- this function does not
    add or subtract it again.
    """
    seed = run[0]
    p0 = _point_internal(origin, hand, facing, seed.u_mm, seed.v_mm,
                         z_base_internal)
    curves = List[DB.Curve]()

    if termination is None:
        z_top_internal = mm_to_internal(top_z_mm + splice_length_mm)
        p1 = _point_internal(origin, hand, facing, seed.u_mm, seed.v_mm,
                             z_top_internal)
        curves.Add(DB.Line.CreateBound(p0, p1))
    else:
        z_bend_internal = mm_to_internal(top_z_mm + termination.a_mm)
        p_bend = _point_internal(origin, hand, facing, seed.u_mm, seed.v_mm,
                                 z_bend_internal)
        curves.Add(DB.Line.CreateBound(p0, p_bend))
        bend_vector = _bend_direction_vector(termination.direction,
                                             hand, facing)
        p_bend_end = _offset_point_internal(
            p_bend, bend_vector, termination.b_mm)
        curves.Add(DB.Line.CreateBound(p_bend, p_bend_end))

    if len(run) > 1:
        direction = _horizontal_unit(
            hand, facing, run[1].u_mm - seed.u_mm, run[1].v_mm - seed.v_mm)
    else:
        # A single-bar run never has `SetLayoutAsNumberWithSpacing`
        # applied, so nothing is distributed and any horizontal reference
        # perpendicular to the bar will do.
        direction = hand

    # THE NORMAL IS THE RUN'S OWN STEP DIRECTION.
    #
    # `SetLayoutAsNumberWithSpacing` arrays the set ALONG the normal the
    # bar was created with. This module used to hand it the PERPENDICULAR
    # of the step direction, on the stated belief that the normal was
    # "never used for anything R22 depends on". It is load-bearing: every
    # run was arrayed ACROSS its own face, picking up the neighbouring
    # face's spacing, and two bars landed 11.7 mm apart at two corners --
    # overlapping steel, in a cage that otherwise looked right (#131).
    normal = direction

    bar = Rebar.CreateFromCurves(
        doc, RebarStyle.Standard, bar_type, None, None, host_element,
        DB.XYZ(normal[0], normal[1], normal[2]), curves,
        RebarHookOrientation.Left, RebarHookOrientation.Left,
        True, False)

    if len(run) > 1:
        spacing_mm = ((run[1].u_mm - seed.u_mm) ** 2
                     + (run[1].v_mm - seed.v_mm) ** 2) ** 0.5
        # On the ACCESSOR, not on the Rebar. `Rebar` has no such member
        # -- reflection over the live type confirms it -- and calling it
        # directly raised AttributeError on a host while every test
        # passed, because the fake offered it both ways (#130).
        bar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(
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

    Per the roof-termination addendum section 1 (#173): a
    ``plan.roof_termination`` states no such splice exists to protrude
    into -- the bar bends into the roof slab instead, and
    :func:`_place_run` reads that decision off
    ``plan.roof_termination.termination``.
    """
    host = plan.host
    hand = host["hand"]
    facing = host["facing"]
    origin = host_element.Location.Point

    z_base_internal = mm_to_internal(plan.extent.base_z_mm)
    offset_internal = mm_to_internal(plan.layout.bar_offset_mm)
    roof = plan.roof_termination
    termination = None if roof is None else roof.termination

    created = []
    for start, end in _face_run_slices(plan.counts):
        run = plan.layout.bars[start:end]
        if not run:
            continue
        created.append(_place_run(
            doc, host_element, bar_type, run, hand, facing, origin,
            z_base_internal, plan.extent.top_z_mm, plan.splice.length_mm,
            offset_internal, termination))
    return created
