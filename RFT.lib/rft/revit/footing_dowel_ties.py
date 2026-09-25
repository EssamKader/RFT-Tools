# -*- coding: utf-8 -*-
"""``dowel_tie`` closed-loop placement for the isolated footing tool (#242).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 6), Sec 9.

Converts ``rft.core.footing_plan.DowelTiePlan`` geometry (mm, footing-
local, centroid at x=y=0, bottom face at z=0) to Revit internal units at
the mm/feet boundary (``rft.revit.units``, REUSE_GUIDELINES.md Sec 1) and
calls ``Rebar.CreateFromCurves`` once per ladder level, one closed-loop
``Rebar`` per level.

## Reuse plan (per issue #242's own ticket body -- do not re-derive)

- The rectangle's own footing-local corners (``DowelTiePlan.loop.
  corners``) are ``rft.core.column_ties.resolve_tie``'s own output,
  already built by ``rft.core.footing_dowel_ties.dowel_tie_loop_mm`` --
  this module only converts them to world points and builds curves, the
  same division of labour ``rft.revit.footing_mesh``/``footing_dowels``
  already keep between "the core decides the shape" and "the adapter
  places it".
- #247 (R15): ``DowelTiePlan.inner_ties`` are placed at the SAME ladder
  levels as the outer loop -- ``for level: for tie:``, mirroring
  ``rft.revit.column_place_ties.place_ties``'s own loop structure exactly
  (the ticket's own instruction: "do not invent a separate level scheme").
  A cross-tie (``column_ties.KIND_CROSS_TIE``) is one straight leg between
  its two named points, never a closed loop's hook-closing rectangle --
  see ``column_place_ties._cross_tie_uv_segments_mm``/
  ``_closed_loop_uv_segments_mm``'s own drawing distinction, mirrored here
  as :func:`_cross_tie_curves`/:func:`_loop_curves`.
- Footing-local-to-world conversion reuses ``rft.revit.footing_mesh.
  _footing_origin``/``_to_world_point`` AS-IS -- the SAME footing-
  bounding-box-centre convention every other footing placement adapter in
  this tool uses (``footing_mesh.py``, ``footing_dowels.py``), NOT
  ``rft.revit.column_place_ties.place_ties``'s own ``host_element.
  Location.Point``/``HandOrientation``/``FacingOrientation`` convention --
  a footing ``FamilyInstance`` is not proven to expose those the way a
  column does (unverified either way, per the ticket's own instruction:
  flag, don't guess). Building a SEPARATE footing-specific placement
  function (this module) rather than adapting ``place_ties`` is the
  ticket's own explicit instruction, not a judgement call made here.
- ``norm = XYZ.BasisZ`` for the closed loop -- the ONE detail the ticket
  says IS safe to reuse from ``column_place_ties``, since a `dowel_tie`
  sits in a horizontal plane exactly like a column tie does (perpendicular
  to the loop's own plane). This is DIFFERENT from ``rft.revit.
  footing_dowels``'s own per-bar ``norm`` (perpendicular to a BENT bar's
  vertical bend plane) -- the two are not the same question, and this
  repo's own history (issue #202's original review) already caught this
  exact class of mistake once.

## SHAPE UNVERIFIED

Two combinations neither of this repo's two existing footing-host kept
writes (``docs/footing/verification/issue-197-footing-tracer-bullet.md``)
covers:

1. **A closed-loop shape on a footing host at all.** Issue #197 Sec 4
   ("Still unverified") names closed-loop shapes explicitly as untested --
   only straight, unhooked curves (Sec 1) and a bar extending beyond the
   footing's own top face (Sec 2) are kept writes. This module's own
   ``Rebar.CreateFromCurves`` call, with ``RebarStyle.StirrupTie`` and a
   real hook type, is therefore a new combination on a footing host, not
   yet run live. #247's own inner cross-ties are the SAME unverified
   combination, one leg instead of four.
2. **The winding-sensitive hook orientation.** ``rft.core.column_ties``'s
   own ``_RECTANGLE_WINDING_SIGN``/R21 (``RebarHookOrientation.Left``,
   both ends) was measured live on a COLUMN host, where a column's own
   ``HandOrientation``/``FacingOrientation`` map the rectangle's ``(u, v)``
   into world space. This module instead maps footing-local ``(x, y)``
   directly onto world ``(X, Y)`` with no rotation (the SAME convention
   ``footing_mesh``/``footing_dowels`` already use, not a new assumption)
   -- since that mapping never flips either axis, the SAME winding
   ``resolve_tie`` computed transfers unchanged into world space, so
   ``Left``/``Left`` is reused here on that reasoning. The reasoning is
   sound but the COMBINATION (a footing host, this exact winding, this
   hook orientation) has not itself been observed on a live host --
   flagged, not assumed proven.

Per this repo's hard rule, this module does not open, commit or roll back
a transaction -- the caller owns the one transaction for the whole footing
(so a failure here leaves the model exactly as it was).
"""

from Autodesk.Revit.DB import Line, XYZ
from Autodesk.Revit.DB.Structure import Rebar, RebarHookOrientation, RebarStyle

from ..core.column_ties import KIND_CROSS_TIE
from ..core.footing_mesh import LocalPoint
from .footing_mesh import _footing_origin, _to_world_point

#: R21's own hook orientation (`rft.revit.column_place_ties`), reused for
#: the SAME reason: it is the ONE combination whose 135deg hook tails turn
#: INTO the rectangle for the winding `resolve_tie`/`dowel_tie_loop_mm`
#: build (see this module's own "SHAPE UNVERIFIED" note, point 2).
_HOOK_ORIENTATION = RebarHookOrientation.Left

#: `Rebar.CreateFromCurves`'s own defaults, matching every other placement
#: module in this repo.
_USE_EXISTING_SHAPE_IF_POSSIBLE = True
_CREATE_NEW_SHAPE = True


class DowelTieNotPlaceableError(Exception):
    """``dowel_tie_plan.loop`` is ``None`` -- no real dowel array (or no
    tie bend diameter) was supplied when the plan was built, so there is
    no rectangle to place. See ``rft.core.footing_plan.DowelTiePlan``'s
    own docstring for exactly which inputs are missing.
    """


def _loop_curves(origin_x, origin_y, origin_z, z_mm, tie):
    """A closed polygon's own footing-local corners (``tie.corners``), at
    ONE level's Z, as a chain of connected world ``Line``s -- the last one
    closing back to the first, since this is a closed polygon, not an open
    chain (unlike ``rft.revit.footing_dowels``'s own bent-bar curves).

    Used for the #242 outer loop AND (#247) any inner tie whose ``kind``
    is a closed loop or triangle -- both carry the SAME ``.corners`` shape
    (``footing_dowel_ties.DowelTieLoop``/``DowelInnerTie``), so one chain
    builder serves both.
    """
    corners = tie.corners
    count = len(corners)
    points = [
        _to_world_point(
            origin_x, origin_y, origin_z,
            LocalPoint(corner.x_mm, corner.y_mm, z_mm))
        for corner in corners]
    return [Line.CreateBound(points[i], points[(i + 1) % count])
            for i in range(count)]


def _cross_tie_curves(origin_x, origin_y, origin_z, z_mm, tie):
    """#247: an inner cross-tie's own single straight leg between its two
    named points -- NOT a closed loop's hook-closing rectangle, mirroring
    ``rft.revit.column_place_ties._cross_tie_uv_segments_mm``'s own
    one-leg distinction (do not invent a new drawing convention).
    """
    corners = tie.corners
    points = [
        _to_world_point(
            origin_x, origin_y, origin_z,
            LocalPoint(corner.x_mm, corner.y_mm, z_mm))
        for corner in corners]
    return [Line.CreateBound(points[0], points[-1])]


def _curves_for_tie(origin, z_mm, tie):
    """Dispatches on ``tie.kind`` -- a cross-tie gets one leg
    (:func:`_cross_tie_curves`), everything else (a closed loop/triangle)
    gets the full chain (:func:`_loop_curves`), mirroring
    ``column_place_ties._uv_segments_mm``'s own dispatch.
    """
    origin_x, origin_y, origin_z = origin
    if tie.kind == KIND_CROSS_TIE:
        return _cross_tie_curves(origin_x, origin_y, origin_z, z_mm, tie)
    return _loop_curves(origin_x, origin_y, origin_z, z_mm, tie)


def _create_rebar_from_curves(document, footing, curves, bar_type, hook_type):
    return Rebar.CreateFromCurves(
        document,
        RebarStyle.StirrupTie,
        bar_type,
        hook_type,
        hook_type,
        footing,
        XYZ.BasisZ,
        curves,
        _HOOK_ORIENTATION,
        _HOOK_ORIENTATION,
        _USE_EXISTING_SHAPE_IF_POSSIBLE,
        _CREATE_NEW_SHAPE,
    )


def _create_dowel_tie_rebar(document, footing, origin, z_mm, loop, bar_type,
                            hook_type):
    origin_x, origin_y, origin_z = origin
    curves = _loop_curves(origin_x, origin_y, origin_z, z_mm, loop)
    return _create_rebar_from_curves(
        document, footing, curves, bar_type, hook_type)


def _create_inner_tie_rebar(document, footing, origin, z_mm, tie, bar_type,
                            hook_type):
    """#247: one inner tie (cross-tie, closed loop or triangle), at ONE
    ladder level -- see :func:`_curves_for_tie` for the kind dispatch.
    """
    curves = _curves_for_tie(origin, z_mm, tie)
    return _create_rebar_from_curves(
        document, footing, curves, bar_type, hook_type)


def place_dowel_ties(document, footing, dowel_tie_plan, bar_type, hook_type):
    """Places one closed-loop ``Rebar`` per level in
    ``dowel_tie_plan.ladder.levels``, at ``dowel_tie_plan.loop``'s own
    footing-local rectangle, hosted directly on ``footing`` -- the SAME
    footing every other placement adapter in this tool hosts on.

    #247 (R15): also places every ``dowel_tie_plan.inner_ties`` entry at
    the SAME ladder level as the outer loop -- ``for level: for tie:``,
    mirroring ``rft.revit.column_place_ties.place_ties``'s own loop
    structure (the ticket's own instruction; see this module's own "Reuse
    plan" docstring section). ``inner_ties`` is read with ``getattr``
    defaulting to an empty tuple so a caller passing a plan object built
    before #247 (no ``inner_ties`` attribute at all) still places the
    outer loop unchanged.

    ``dowel_tie_plan`` is a ``rft.core.footing_plan.DowelTiePlan`` -- the
    caller must build it via ``rft.core.footing_plan.build_footing_plan``,
    never by calling ``rft.core.footing_dowel_ties`` directly (the one
    composing module rule, docs/token-efficient-expansion.md Sec 7).

    Raises :class:`DowelTieNotPlaceableError` if ``dowel_tie_plan.loop``
    is ``None`` -- refused here rather than silently placing nothing, so
    a caller cannot mistake "no ties were built" for "no ties were
    needed".

    Returns the list of created ``Rebar`` elements, in level order; within
    a level, the outer loop first, then every inner tie in the order
    ``dowel_tie_plan.inner_ties`` carries them.
    """
    if dowel_tie_plan.loop is None:
        raise DowelTieNotPlaceableError(
            "This footing's dowel_tie plan has no loop geometry to place "
            "-- a real dowel array (column_section plus dowel_count_"
            "b_face/dowel_count_h_face/dowel_tie_dia_mm) and the tie bar "
            "type's own bend diameter must both be supplied before "
            "build_footing_plan can build one (see "
            "rft.core.footing_plan.DowelTiePlan's own docstring).")

    inner_ties = getattr(dowel_tie_plan, "inner_ties", tuple())
    origin = _footing_origin(footing)
    created = []
    for level in dowel_tie_plan.ladder.levels:
        created.append(_create_dowel_tie_rebar(
            document, footing, origin, level.z_mm, dowel_tie_plan.loop,
            bar_type, hook_type))
        for tie in inner_ties:
            created.append(_create_inner_tie_rebar(
                document, footing, origin, level.z_mm, tie, bar_type,
                hook_type))
    return created
