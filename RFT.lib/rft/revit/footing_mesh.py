# -*- coding: utf-8 -*-
"""Bottom-mesh placement adapter -- the tracer-bullet vertical slice, spec
Ref: specs/isolated-footing.md Sec 11 item 2.

Converts ``rft.core.footing_plan`` geometry (mm, footing-local, centroid at
x=y=0, bottom face at z=0) to Revit internal units at the mm/feet boundary
(``rft.revit.units``, the repo's single designated boundary -- REUSE_
GUIDELINES.md Sec 1) and calls ``Rebar.CreateFromCurves`` once per bar.

API shape: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 confirms, by a KEPT write, that an isolated footing ``FamilyInstance``
is a valid, direct host for ``Rebar.CreateFromCurves`` -- "no cast, no
wrapper, no intermediate analytical element" -- and that call passed
``XYZ.BasisZ`` as the ``norm`` argument, exactly as used below. The
trailing ``RebarHookOrientation``/boolean arguments are NOT shown by
#197's write-up (truncated with "..."); rather than invent them, they are
copied from the one place in this repo that already calls
``Rebar.CreateFromCurves`` for a straight, unhooked bar --
``RFT.lib/rft/revit/placement.py``'s ``place_anchored_bar`` (RebarStyle.
Standard, no start/end hook, ``RebarHookOrientation.Left`` both ends,
``useExistingShapeIfPossible``/``createNewShape`` both True) -- which
itself is flagged there as "UNVERIFIED AGAINST A LIVE HOST" for those same
two boolean flags. Reusing that already-recorded uncertainty is not new
guessing; each call site does not need to guess again independently.

Per this repo's hard rule, this module does not open, commit or roll back
a transaction -- the caller owns the one transaction for the whole footing
(so a failure here leaves the model exactly as it was).

**Known limitation, found in review, not silently left in:** ``_footing_
origin``/``_to_world_point`` translate footing-local mm coordinates into
world XYZ using only the footing's bounding-box centre -- no rotation
transform is applied. Issue #69 already documented this exact trap for
columns: "``get_BoundingBox(null)`` is axis-aligned in model coordinates
and degenerates to the correct answer only at rotations of 0/90/180/270
deg" -- but that degeneracy only actually maps the footing's own a/b axes
onto world X/Y at 0/180 deg. At 90/270 deg the footing's Length (a_mm)
axis runs along world Y, not X, so ``_to_world_point``'s unconditional
local-x -> world-X / local-y -> world-Y mapping is WRONG there too, not
safe -- issue #246 confirmed this live (rebar placed outside the footing
solid at 90 deg from world axes). Rather than repeat that silently,
``_footing_origin`` REFUSES (``FootingRotationUnsupportedError``) at
ANY rotation that is not a multiple of 180 deg -- 0 and 180 deg are the
only angles this module accepts; 90 and 270 deg now raise the same
refusal as any other non-axis-aligned angle, per REUSE_GUIDELINES.md
Sec 3's "Explicit Refusals" rule. Supporting a 90/270-deg (or any other)
rotated footing needs a live-host check of ``footing.GetTransform()``
against the plan centroid and the family's own a/b axes, including an
actual axis swap in ``_to_world_point`` -- unverified, and out of this
ticket's scope (follow-up, not guessed at here).
"""

import math

from Autodesk.Revit.DB import Line, XYZ
from Autodesk.Revit.DB.Structure import Rebar, RebarHookOrientation, RebarStyle

from .units import mm_to_internal

#: How close to an exact half turn counts as "axis-aligned" -- Revit
#: rotation reads (per issue #69's column measurements) are exact doubles
#: for an intentionally-set 0 deg, so a tight tolerance catches genuine
#: rotation without false-refusing on floating-point noise.
_AXIS_ALIGNED_TOLERANCE_RAD = 1e-6


class FootingRotationUnsupportedError(NotImplementedError):
    """Raised by ``_footing_origin`` when the footing host is not
    axis-aligned (0/180 deg only -- issue #246 tightened this from the
    original, WRONG 0/90/180/270 acceptance: ``_to_world_point`` has no
    rotation transform, and that mapping is only actually correct at
    0/180 deg). See this module's own docstring, "Known limitation", for
    why this refuses rather than guesses.
    """


def _is_axis_aligned(rotation_rad):
    """Issue #246: only 0/180 deg (mod 180) is "safe" -- 90/270 deg used
    to pass this check, but ``_to_world_point`` maps footing-local x/y
    onto world X/Y unconditionally, which is only correct when the
    footing's own a/b axes actually line up with world X/Y (0/180 deg).
    At 90/270 deg the footing's Length (a_mm) axis runs along world Y,
    not X, so this must now refuse there too -- see the module docstring,
    "Known limitation".
    """
    half_turn = math.pi
    remainder = rotation_rad % half_turn
    return (remainder <= _AXIS_ALIGNED_TOLERANCE_RAD
            or (half_turn - remainder) <= _AXIS_ALIGNED_TOLERANCE_RAD)


def _footing_origin(footing):
    """(centre_x, centre_y, bottom_z), internal units, from the footing
    host's own bounding box -- the same Min/Max-bounding-box datum issue
    #197 Sec 2 measured a dowel's z-range against ("z = footing.Min.Z +
    ..."), and the same ``get_BoundingBox(None)`` call already used
    elsewhere in this repo for a structural host's vertical extent.

    Raises ``FootingRotationUnsupportedError`` if the footing is rotated --
    see this module's docstring, "Known limitation".
    """
    location = getattr(footing, "Location", None)
    rotation_rad = getattr(location, "Rotation", 0.0) if location is not None else 0.0
    if not _is_axis_aligned(rotation_rad):
        raise FootingRotationUnsupportedError(
            "Footing is rotated %.6f rad; only axis-aligned footings "
            "(0/180 deg) are supported -- 90/270 deg is REFUSED, not "
            "silently placed wrong (issue #246) -- see "
            "rft.revit.footing_mesh's module docstring, "
            "'Known limitation'." % rotation_rad)

    box = footing.get_BoundingBox(None)
    centre_x = (box.Min.X + box.Max.X) / 2.0
    centre_y = (box.Min.Y + box.Max.Y) / 2.0
    return centre_x, centre_y, box.Min.Z


def _to_world_point(origin_x, origin_y, origin_z, local_point):
    """One ``rft.core.footing_mesh.LocalPoint`` (mm) -> world ``XYZ``
    (internal units), translated by the footing's own origin.
    """
    return XYZ(
        origin_x + mm_to_internal(local_point.x_mm),
        origin_y + mm_to_internal(local_point.y_mm),
        origin_z + mm_to_internal(local_point.z_mm),
    )


def _bent_bar_curves(origin_x, origin_y, origin_z, geometry):
    """#229: one mesh bar's REAL bent centreline
    (``rft.core.footing_mesh.MeshBarGeometry.points``, 2-4 connected
    footing-local points) -> a chain of connected world ``Line``s, the
    same "list of connected curves into ONE ``Rebar.CreateFromCurves``
    call" shape ``rft.revit.footing_dowels._dowel_curves`` already uses
    for the dowel array's own bent bars.
    """
    points = [_to_world_point(origin_x, origin_y, origin_z, point)
              for point in geometry.points]
    return [Line.CreateBound(points[i], points[i + 1])
            for i in range(len(points) - 1)]


def _norm_for_bar(hooks, bent_axis_norm):
    """Found in review (issue #236): a bar with NEITHER end hooked has no
    bend at all, so it must keep issue #197 Sec 1's own live-verified
    ``XYZ.BasisZ`` rather than switch to the bent-case's per-axis norm --
    that switch is only valid, and only needed, once the bar actually
    bends (see ``place_straight_bottom_mesh``'s own docstring).
    """
    if hooks.start.needs_hook or hooks.end.needs_hook:
        return bent_axis_norm
    return XYZ.BasisZ


def _place_one_bar(document, footing, curves, norm, bar_type):
    return Rebar.CreateFromCurves(
        document,
        RebarStyle.Standard,
        bar_type,
        None,  # startHook -- shape is built from curves, not a hook type
        None,  # endHook
        footing,
        norm,
        curves,
        RebarHookOrientation.Left,
        RebarHookOrientation.Left,
        True,
        True,
    )


def place_straight_bottom_mesh(document, footing, bottom_mesh,
                                bar_x_type, bar_y_type):
    """Places ONE ``mesh_bar_x`` bar and ONE ``mesh_bar_y`` bar (each the
    real bent U/L shape #229 built, centred on the footing's own plan
    centroid), hosted directly on ``footing`` -- the tracer-bullet
    vertical slice (spec Sec 11 item 2), now carrying #199/#200's hook
    decision instead of ignoring it.

    No array, no spacing/quantity: this proves the placement mechanics
    end to end for a single representative bar per direction; full mesh
    spacing/quantity is separate, later ticket scope (#229's own scope
    note), not named by this one's formulas.

    ``norm`` differs per axis, not per bar (unlike the dowel array's R10,
    where it varies per bar's own outward direction), and ONLY when the
    bar actually has a hooked end: ``mesh_bar_x`` bends in the X-Z plane
    (its straight run is along local X, its hook legs along Z), so its
    bend-plane-perpendicular ``norm`` is ``XYZ.BasisY``; ``mesh_bar_y``
    bends in the Y-Z plane, so its ``norm`` is ``XYZ.BasisX`` -- the same
    #183 measurement (``norm`` must be perpendicular to the bend's own
    plane). A bar with NEITHER end hooked has no bend at all -- issue
    #197 Sec 1's own kept-write tracer bullet is the only live-host proof
    this repo has for a straight bar on a footing host, and it used
    ``XYZ.BasisZ``; ``_norm_for_bar`` below keeps that exact, already-
    verified value for the still-straight case rather than switching to
    the bent-case norm for a bar that isn't bent (found in review: #229's
    first draft used the bent-axis norm unconditionally, an untested
    combination for the common no-hook footing).

    ``bottom_mesh`` is a ``rft.core.footing_plan.BottomMeshPlan`` -- the
    caller must build it via ``rft.core.footing_plan.build_footing_plan``,
    never by calling ``rft.core.footing_mesh`` directly (the one composing
    module rule, docs/token-efficient-expansion.md Sec 7) -- that is also
    the only place ``bar_x_geometry``/``bar_y_geometry`` get populated.

    Returns ``(bar_x, bar_y)``, the two created ``Rebar`` elements.

    Found in review (#232): this is now a thin wrapper around
    ``place_bottom_mesh_bars`` -- that function already handles the no-
    array case by falling back to a one-item list per direction, so
    duplicating its origin/norm derivation and per-bar placement call
    here risked exactly the kind of drift #229's own norm regression
    already demonstrated (two call sites for the same mechanics, kept in
    sync by hand instead of by construction).
    """
    bars_x, bars_y = place_bottom_mesh_bars(
        document, footing, bottom_mesh, bar_x_type, bar_y_type)
    return bars_x[0], bars_y[0]


def place_bottom_mesh_bars(document, footing, bottom_mesh, bar_x_type,
                           bar_y_type):
    """#232 (R11, docs/footing/spec-amendments.md): places EVERY bar in
    ``bottom_mesh.bar_x_array``/``bar_y_array`` -- the same
    ``_place_one_bar`` call ``place_straight_bottom_mesh`` makes for its
    one representative bar per direction, looped once per array position.
    Not a new shape: #229's own tracer bullet already proved this call is
    a KEPT write on a footing host for a bent bar's connected curves; an
    N-bar array repeats it N times per direction, mirroring exactly the
    "loop the existing single-bar call" precedent #223 already set for
    the dowel array (``rft.revit.footing_dowels.place_dowel_bars`` over
    #202's one representative dowel).

    Works unchanged whether ``bottom_mesh.bar_x_array``/``bar_y_array``
    holds a real N-position array (``inputs.mesh_bar_x_spacing_mm``/
    ``mesh_bar_y_spacing_mm`` supplied) or is ``None`` (no spacing
    supplied -- every caller that predates #232) -- that direction then
    falls back to the SAME single ``bar_x_geometry``/``bar_y_geometry``
    bar ``place_straight_bottom_mesh`` always placed, wrapped in a
    one-item list so this function's own return shape never depends on
    which path a given footing took.

    ``norm`` is derived per axis, not per bar (unchanged from
    ``place_straight_bottom_mesh`` -- every bar sharing a direction bends
    in the SAME plane, only its own Y/X offset differs, per R11).

    Returns ``(bars_x, bars_y)`` -- two lists of the created ``Rebar``
    elements, in array order.
    """
    origin_x, origin_y, origin_z = _footing_origin(footing)
    norm_x = _norm_for_bar(bottom_mesh.bar_x_hooks, XYZ.BasisY)
    norm_y = _norm_for_bar(bottom_mesh.bar_y_hooks, XYZ.BasisX)

    bar_x_geometries = bottom_mesh.bar_x_array
    if bar_x_geometries is None:
        bar_x_geometries = (bottom_mesh.bar_x_geometry,)
    bar_y_geometries = bottom_mesh.bar_y_array
    if bar_y_geometries is None:
        bar_y_geometries = (bottom_mesh.bar_y_geometry,)

    bars_x = [
        _place_one_bar(
            document, footing,
            _bent_bar_curves(origin_x, origin_y, origin_z, geometry),
            norm_x, bar_x_type)
        for geometry in bar_x_geometries]
    bars_y = [
        _place_one_bar(
            document, footing,
            _bent_bar_curves(origin_x, origin_y, origin_z, geometry),
            norm_y, bar_y_type)
        for geometry in bar_y_geometries]
    return bars_x, bars_y


def place_straight_top_mesh(document, footing, top_mesh, bar_x_type,
                            bar_y_type):
    """#233 (R13, docs/footing/spec-amendments.md): places ONE
    ``mesh_bar_x`` bar and ONE ``mesh_bar_y`` bar for the TOP mat, hosted
    on the SAME ``footing`` element as the bottom mesh -- there is no
    separate top-mat host.

    Mirrors ``place_straight_bottom_mesh``'s own pre-#232 shape (single
    representative bar per direction) rather than ``place_bottom_mesh_
    bars``'s array-loop shape: ``rft.core.footing_plan.TopMeshPlan`` never
    carries a ``bar_x_array``/``bar_y_array`` (this ticket's own scope --
    the top mat's own array is separate, unbuilt follow-up), so there is
    nothing to loop over yet.

    ``norm`` derivation reuses ``_norm_for_bar`` exactly as the bottom mat
    does -- ``mesh_bar_x`` still bends in the X-Z plane (``norm =
    XYZ.BasisY``), ``mesh_bar_y`` still bends in the Y-Z plane (``norm =
    XYZ.BasisX``); R13 changes which way (up/down) a hooked end's leg
    points, not which PLANE it bends in, so the same #183 measurement
    (``norm`` perpendicular to the bend's own plane) still applies
    unchanged. A bar with neither end hooked keeps the #197-verified
    ``XYZ.BasisZ`` for the same reason ``_norm_for_bar`` already gives the
    bottom mat's own straight case that value.

    ``top_mesh`` is a ``rft.core.footing_plan.TopMeshPlan`` -- the caller
    must build it via ``build_footing_plan``, never by calling
    ``rft.core.footing_mesh`` directly (the one composing module rule).

    Returns ``(bar_x, bar_y)``, the two created ``Rebar`` elements.

    SHAPE UNVERIFIED: the same footing-host bent-multi-curve
    ``Rebar.CreateFromCurves`` combination #229's own docstring already
    flags as unverified for the bottom mat (issue #236) -- this places at
    the top mat's own (different) elevation, which is not a new API
    shape, but has not itself been run against a live host either.
    """
    origin_x, origin_y, origin_z = _footing_origin(footing)
    norm_x = _norm_for_bar(top_mesh.bar_x_hooks, XYZ.BasisY)
    norm_y = _norm_for_bar(top_mesh.bar_y_hooks, XYZ.BasisX)

    bar_x = _place_one_bar(
        document, footing,
        _bent_bar_curves(origin_x, origin_y, origin_z, top_mesh.bar_x_geometry),
        norm_x, bar_x_type)
    bar_y = _place_one_bar(
        document, footing,
        _bent_bar_curves(origin_x, origin_y, origin_z, top_mesh.bar_y_geometry),
        norm_y, bar_y_type)
    return bar_x, bar_y
