# -*- coding: utf-8 -*-
"""Column dowel placement adapter -- the tracer-bullet vertical slice for
#202, spec Ref: specs/isolated-footing.md Sec 3 (Story 5), Sec 8, Sec 11
item 6.

Converts ``rft.core.footing_plan.DowelArrayPlan`` geometry (mm, footing-
local, centroid at x=y=0, bottom face at z=0) to Revit internal units at the
mm/feet boundary (``rft.revit.units``, the repo's single designated
boundary -- REUSE_GUIDELINES.md Sec 1) and calls
``Rebar.CreateFromCurves`` once, with the bent bar's two connected curves,
per dowel.

API shape, reused rather than re-derived:

- ``docs/footing/verification/issue-197-footing-tracer-bullet.md`` Sec 1
  is a KEPT WRITE proving an isolated footing ``FamilyInstance`` is a
  valid, direct host for ``Rebar.CreateFromCurves`` -- reused here exactly
  as ``rft.revit.footing_mesh`` already does (``_footing_origin``,
  ``_to_world_point`` and the axis-alignment refusal are IMPORTED from
  that module, not duplicated, since they are the same footing-host-origin
  math regardless of which bar is being placed).
- The same tracer bullet's Sec 2 is a KEPT WRITE proving a bar hosted on a
  footing may extend beyond the footing's own top face while still hosted
  on it -- directly relevant here since the dowel's vertical leg runs from
  inside the footing up to the footing's own top face (this ticket's
  scope stops there; continuing the bar up into the column above is the
  column tool's own concern, not this one's).

**SHAPE UNVERIFIED** -- passing TWO connected curves (the horizontal hook
leg, then the vertical leg) to ONE ``Rebar.CreateFromCurves`` call, on a
FOOTING host. Issue #197's own tracer bullet only exercised a single
straight curve on a footing host. A multi-curve bent-bar call IS proven
live -- ``RFT.lib/rft/revit/column_place_bars.py``'s roof-termination path
(#173/#183) -- but only on a COLUMN host. Composing "footing accepts
CreateFromCurves" with "CreateFromCurves accepts multiple connected
curves" is not itself a new invented API shape (no argument here has a
signature this module is guessing at -- every argument position matches
``rft.revit.footing_mesh``'s already-proven single-curve call, only the
``curves`` list itself is longer), but the COMBINATION has not been run
against a live footing host. Flag before this runs on a live host, the
same way #197 Sec 4 flags hook types and closed-loop shapes as its own
"still unverified" items.

**Found and fixed in review:** the ``norm`` argument for a bent bar is NOT
the same value as the straight mesh bars' ``XYZ.BasisZ``.
``column_place_bars.py``'s own #183 measurement (see that module's "SHAPE
MEASURED" section) established that ``normal`` must be PERPENDICULAR to
the bend's own plane for the bend to actually be carried by the created
``Rebar`` -- that is the whole reason #183 called it out as one of
``normal``'s two roles.

R10 (docs/footing/spec-amendments.md): each dowel's own hook now bends
OUTWARD from the column centroid, a direction that differs PER BAR (a
face bar bends along one plan axis, a corner bar along the 45-degree
diagonal) -- so the bend plane differs per bar too, and ``norm`` can no
longer be the single fixed ``XYZ.BasisY`` #202's own tracer bullet used
(correct ONLY for that bullet's arbitrary fixed ``+X`` hook direction).
``_dowel_norm`` below derives it per bar instead: a 90-degree in-plane
rotation of the hook's own ``(x, y)`` direction, which is always
perpendicular to both that direction and the vertical (``Z``) axis --
the same #183 measurement, applied per bar rather than once for the
whole array. For the legacy fixed ``+X`` case this reduces to exactly
``(0, 1, 0)`` = the original ``XYZ.BasisY``, so the ONE live-host
verification this repo has for a bent dowel's ``normal``
(`docs/footing/verification/issue-223-footing-dowel-array-loop.md`) still
covers that case; the per-bar generalisation itself is unverified until
its own tracer bullet runs.

Per this repo's hard rule, this module does not open, commit or roll back
a transaction -- the caller owns the one transaction for the whole footing
(so a failure here leaves the model exactly as it was).
"""

import math

from Autodesk.Revit.DB import Line, XYZ
from Autodesk.Revit.DB.Structure import Rebar, RebarHookOrientation, RebarStyle

from .footing_mesh import _footing_origin, _to_world_point


def _dowel_curves(origin_x, origin_y, origin_z, geometry):
    """The dowel's two connected curves, world XYZ (internal units):
    the horizontal hook leg first (far end -> bend corner), then the
    vertical leg (bend corner -> top) -- one continuous bent-bar path,
    the same curve-chain shape
    ``rft.revit.column_place_bars._place_run`` already builds for a bent
    column bar (``p0 -> p_bend`` then ``p_bend -> p_bend_end``).
    """
    hook_start = _to_world_point(
        origin_x, origin_y, origin_z, geometry.bottom_hook.start)
    hook_end = _to_world_point(
        origin_x, origin_y, origin_z, geometry.bottom_hook.end)
    vertical_end = _to_world_point(
        origin_x, origin_y, origin_z, geometry.vertical.end)
    return [
        Line.CreateBound(hook_start, hook_end),
        Line.CreateBound(hook_end, vertical_end),
    ]


def _dowel_norm(geometry):
    """R10: the bend-plane-perpendicular ``norm`` for THIS bar's own hook
    direction -- a 90-degree in-plane rotation of the hook vector
    (``bottom_hook.start - bottom_hook.end``, i.e. far end -> bend
    corner reversed), which is always perpendicular to both the hook's
    own direction and the vertical (Z) axis (this module's own docstring,
    "Found and fixed in review" -> R10). Reduces to exactly
    ``XYZ.BasisY`` for the legacy fixed ``+X`` hook direction, matching
    the one live-verified case (#223).
    """
    hook = geometry.bottom_hook
    dx = hook.start.x_mm - hook.end.x_mm
    dy = hook.start.y_mm - hook.end.y_mm
    length = math.sqrt(dx * dx + dy * dy)
    unit_x, unit_y = dx / length, dy / length
    return XYZ(-unit_y, unit_x, 0.0)


def _create_dowel_rebar(document, footing, origin, bar_geometry, bar_type):
    """The single ``Rebar.CreateFromCurves`` call shared by
    ``place_dowel_bar`` and ``place_dowel_bars`` -- one bent bar, at
    ``bar_geometry``'s own footing-local position. Not called directly by
    anything outside this module; both public functions exist so a caller
    building a plan with no real array (``dowel_plan.bars`` still one
    representative entry, per ``footing_plan.DowelArrayPlan``'s own
    docstring) keeps working through either name.
    """
    origin_x, origin_y, origin_z = origin
    curves = _dowel_curves(origin_x, origin_y, origin_z, bar_geometry)
    return Rebar.CreateFromCurves(
        document,
        RebarStyle.Standard,
        bar_type,
        None,  # startHook -- shape is built from curves, not a hook type
        None,  # endHook
        footing,
        _dowel_norm(bar_geometry),
        curves,
        RebarHookOrientation.Left,
        RebarHookOrientation.Left,
        True,
        True,
    )


def place_dowel_bar(document, footing, dowel_plan, bar_type):
    """Places ONE dowel bar (straight-vertical-plus-horizontal-hook,
    centred on the footing's own plan centroid), hosted directly on
    ``footing`` -- the tracer-bullet vertical slice (spec Sec 11 item 6).

    No array, no stirrup/tie wiring (Story 6 / #203's own scope): this
    proves the placement mechanics for a single representative dowel,
    matching #198's own "one representative bar per direction" precedent
    for the mesh. #222 (specs/isolated-footing-dowel-array.md Sec 3 Story
    3) reshaped ``rft.core.footing_plan``'s dowel plan into a
    ``DowelArrayPlan`` carrying ``bars`` (a list); this tracer bullet still
    places only the FIRST entry. Placing every bar in the array is
    ``place_dowel_bars`` below (#223, Story 4) -- kept as its own function,
    not a behaviour change here, since a caller with no real array still
    wants exactly one bar, not a one-item loop.

    ``dowel_plan`` is a ``rft.core.footing_plan.DowelArrayPlan`` -- the
    caller must build it via ``rft.core.footing_plan.build_footing_plan``,
    never by calling ``rft.core.footing_dowels`` directly (the one
    composing module rule, docs/token-efficient-expansion.md Sec 7).

    Returns the created ``Rebar`` element.
    """
    origin = _footing_origin(footing)
    return _create_dowel_rebar(
        document, footing, origin, dowel_plan.bars[0], bar_type)


def place_dowel_bars(document, footing, dowel_plan, bar_type):
    """Places EVERY dowel bar in ``dowel_plan.bars`` (#223, spec Ref:
    specs/isolated-footing-dowel-array.md Sec 3 Story 4) -- the same
    ``_create_dowel_rebar`` call ``place_dowel_bar`` makes for its one
    representative bar, looped once per array position. Not a new shape:
    #202's own tracer bullet already proved this call is a KEPT write on a
    footing host; an N-bar array repeats it N times, so this function's own
    verification only needs to confirm the LOOP -- no cross-bar
    interference, no partial array left behind on a mid-loop failure (that
    second half is the caller's job: this function raises on the first
    failure and places nothing further, same as any other loop with no
    try/except of its own -- the pushbutton script's existing one-
    transaction pattern is what rolls the partial set back, not this
    function).

    Works unchanged whether ``dowel_plan.bars`` holds the one representative
    bar (no live column section / array inputs supplied --
    ``footing_plan.DowelArrayPlan``'s own fallback) or a real N-position
    array (``footing_plan._build_dowel_plan``'s ``perimeter_bar_positions``
    call) -- this function does not know or care which, it only iterates
    ``bars``.

    Returns the list of created ``Rebar`` elements, one per ``dowel_plan.
    bars`` entry, in the same order.
    """
    origin = _footing_origin(footing)
    return [_create_dowel_rebar(document, footing, origin, bar_geometry,
                                bar_type)
            for bar_geometry in dowel_plan.bars]
