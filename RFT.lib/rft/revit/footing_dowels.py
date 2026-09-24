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
``normal``'s two roles. This dowel's bend plane is the local X-Z plane
(the hook leg runs along local X, the vertical leg along local Z, both at
constant Y=0), so the perpendicular axis is Y, not Z -- ``XYZ.BasisZ``
would lie IN the bend plane instead of perpendicular to it. Fixed to
``XYZ.BasisY``. Still unverified against a live host (this ticket's own
scope, per the SHAPE UNVERIFIED note above), but now consistent with the
one live measurement this repo has for a bent bar's ``normal``, rather
than silently reusing the straight-bar value.

Per this repo's hard rule, this module does not open, commit or roll back
a transaction -- the caller owns the one transaction for the whole footing
(so a failure here leaves the model exactly as it was).
"""

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
    places only the FIRST entry -- placing every bar in the array is
    Story 4's own scope (#223), not built here.

    ``dowel_plan`` is a ``rft.core.footing_plan.DowelArrayPlan`` -- the
    caller must build it via ``rft.core.footing_plan.build_footing_plan``,
    never by calling ``rft.core.footing_dowels`` directly (the one
    composing module rule, docs/token-efficient-expansion.md Sec 7).

    Returns the created ``Rebar`` element.
    """
    origin_x, origin_y, origin_z = _footing_origin(footing)
    curves = _dowel_curves(
        origin_x, origin_y, origin_z, dowel_plan.bars[0])
    return Rebar.CreateFromCurves(
        document,
        RebarStyle.Standard,
        bar_type,
        None,  # startHook -- shape is built from curves, not a hook type
        None,  # endHook
        footing,
        # norm -- perpendicular to the bend's own local X-Z plane, per
        # column_place_bars.py's #183 measurement (see this module's own
        # "Found and fixed in review" note above), NOT #197's XYZ.BasisZ,
        # which was only ever measured for a single straight curve.
        XYZ.BasisY,
        curves,
        RebarHookOrientation.Left,
        RebarHookOrientation.Left,
        True,
        True,
    )
