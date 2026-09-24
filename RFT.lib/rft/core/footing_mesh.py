# -*- coding: utf-8 -*-
"""Bottom-mesh bar length geometry for the isolated footing tool, plus the
per-bar-end hook/development-length decision (#199) and the per-mat
U-shape/L-shape-alternating user override on top of it (#200).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 1, Story 2 and Story 3),
Sec 4, Sec 5, Sec 6, Sec 2 (naming).
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").
"""

import math
from collections import namedtuple

#: Spec Ref: Sec 2/3, "Primary Reinforcement" / "Secondary Reinforcement".
DIRECTION_X = "X"
DIRECTION_Y = "Y"

#: Spec Ref: Sec 3 (Story 2/3) -- the only two bar shapes the spec names.
#: U-shape is the default (both ends hooked); L-shape is what a bar
#: switches to once Sec 5's per-end comparison finds an end that does not
#: need a hook.
SHAPE_U = "U"
SHAPE_L = "L"

#: Spec Ref: Sec 3 (Story 3), Sec 6 -- the direct, per-mat user input that
#: OVERRIDES Story 2's per-end LD comparison for that mat. This is a
#: distinct concept from ``SHAPE_U``/``SHAPE_L`` above (a bar's own
#: *computed result*): ``MAT_SHAPE_U`` is the user's *choice* of policy for
#: the whole mat, which happens to resolve to the same ``SHAPE_U`` result
#: every bar gets. ``MAT_SHAPE_L_ALTERNATING`` has no equivalent single-bar
#: shape constant -- it is a mat-wide policy ("consecutive bars alternate
#: which end is hooked"), not a per-bar shape by itself.
MAT_SHAPE_U = SHAPE_U
MAT_SHAPE_L_ALTERNATING = "L_ALTERNATING"


#: Spec Ref: Sec 3 (Story 1). Z/Z2 are the straight lengths inside cover;
#: N/N2 are the vertical hook legs of the first and second mat
#: respectively; mesh_bar_x/mesh_bar_y are the two bars' overall lengths.
MeshBarLengths = namedtuple(
    "MeshBarLengths",
    ["z_mm", "z2_mm", "n_mm", "n2_mm", "mesh_bar_x_mm", "mesh_bar_y_mm"],
)

#: A footing-local point, in mm, with the footing's own plan centroid at
#: (0, 0) and its bottom face at z = 0. The Revit adapter is the only place
#: this gets translated to a real host and converted to internal units.
LocalPoint = namedtuple("LocalPoint", ["x_mm", "y_mm", "z_mm"])

#: The two endpoints (LocalPoint) of one straight bar's centreline.
BarEndpoints = namedtuple("BarEndpoints", ["start", "end"])


class HookDevelopmentLengthTieError(ValueError):
    """The required development length exactly equals the available
    straight offset at a bar end.

    Spec Ref: Sec 5 defines only "LD > offset" (hook) and "offset > LD"
    (no hook, switch to L-shape) -- it does not say what happens when
    they are exactly equal. Per Essam's revised ruling (R2,
    docs/footing/spec-amendments.md), this is not resolved by a silent
    default: the automatic per-end comparison refuses, and the caller is
    expected to give the engineer the SAME explicit choice #200 already
    built for exactly this situation -- an explicit ``mat_shape_mode``
    (``MAT_SHAPE_U`` or ``MAT_SHAPE_L_ALTERNATING``) via
    ``bar_hook_plan_for_mat``, which never calls this comparison at all.
    REUSE_GUIDELINES.md Sec 3 ("Explicit Refusals") requires a raise here,
    not a guessed tie-break.
    """


#: One bar end's hook decision. ``ld_mm`` is Sec 5's ``LD = multiplier *
#: db`` for the bar this end belongs to; ``needs_hook`` is the Sec 5
#: comparison result for this end alone.
BarEndHook = namedtuple("BarEndHook", ["ld_mm", "needs_hook"])

#: A whole bar's hook plan: its two ends' ``BarEndHook`` and the
#: resulting overall ``shape`` (``SHAPE_U``/``SHAPE_L``).
BarHookPlan = namedtuple("BarHookPlan", ["start", "end", "shape"])

#: #229: one mesh bar's actual bent centreline, footing-local mm, as an
#: ORDERED chain of connected points (2 points for a straight run with no
#: hooked end, 3 for one hooked end, 4 for both -- Sec 3 Story 1's "a U in
#: elevation"). Unlike the dowel array (R10), the hook direction here is
#: fixed (always straight up, Sec 5's "bend the bar up") -- there is no
#: per-bar outward-direction question, only per-END presence.
MeshBarGeometry = namedtuple("MeshBarGeometry", ["points"])


def mesh_bar_lengths(a_mm, b_mm, cover_mm, footing_thickness_mm,
                      bottom_cover_mm, top_cover_mm, mesh_bar_x_dia_mm):
    """Straight-case bottom-mesh bar lengths.

    Spec Ref: Sec 3 (Story 1) / Sec 4:
        Z = a - 2*cover; Z2 = b - 2*cover
        N = footing_thickness - bottom_cover - top_cover
        N2 = footing_thickness - bottom_cover - mesh_bar_x_dia - top_cover
        mesh_bar_x = Z + 2*N; mesh_bar_y = Z2 + 2*N2

    ``cover`` here is the single side-cover value the spec's own Sec 3
    naming table uses for BOTH Z and Z2 -- there is no separate a-side/
    b-side cover in the spec, so none is invented here.
    """
    z_mm = a_mm - 2.0 * cover_mm
    z2_mm = b_mm - 2.0 * cover_mm
    n_mm = footing_thickness_mm - bottom_cover_mm - top_cover_mm
    n2_mm = (footing_thickness_mm - bottom_cover_mm
             - mesh_bar_x_dia_mm - top_cover_mm)
    mesh_bar_x_mm = z_mm + 2.0 * n_mm
    mesh_bar_y_mm = z2_mm + 2.0 * n2_mm
    return MeshBarLengths(
        z_mm=z_mm, z2_mm=z2_mm, n_mm=n_mm, n2_mm=n2_mm,
        mesh_bar_x_mm=mesh_bar_x_mm, mesh_bar_y_mm=mesh_bar_y_mm)


def primary_reinforcement_direction(x_offset_mm, y_offset_mm):
    """Spec Ref: Sec 2/3 -- "if X > Y => Primary Reinforcement in X
    direction". Whichever column-face offset is larger becomes Primary and
    sits lowest within its mesh; the other is Secondary, stacked above it.

    This is fixed geometry, decided the same way for every mesh (Sec 2:
    "the same X-vs-Y comparison decides the Primary direction identically
    for both meshes"), even though only the bottom mesh exists yet (#199
    is what consumes this for hook decisions).

    ``docs/footing/spec-amendments.md`` R1: when X == Y, Primary defaults
    to ``DIRECTION_X`` -- Essam's ruling, since the spec's own formulas
    (Sec 4-Sec 10) never depend on WHICH direction is Primary when the two
    offsets are equal, only on treating both meshes' Primary consistently
    (Sec 2). This is a recorded decision, not a guess: the LOCKED spec
    left it open and the project owner was asked directly rather than the
    code picking one silently.
    """
    if y_offset_mm > x_offset_mm:
        return DIRECTION_Y
    return DIRECTION_X


def local_mesh_bar_endpoints(lengths, bottom_cover_mm, mesh_bar_x_dia_mm,
                              mesh_bar_y_dia_mm):
    """The two straight bars' centreline endpoints, footing-local mm.

    Spec Ref: Sec 2 naming table -- "mesh_bar_y ... stacked above
    mesh_bar_x" is unconditional (not gated on which direction is
    Primary), so mesh_bar_x always sits on the lower layer here. The
    vertical offset between the two layers is mesh_bar_x's own diameter --
    the same ``⌀mesh_bar_x`` term Sec 4's N2 formula already introduces
    for exactly this stacking, not a newly invented quantity.

    Both bars are centred on the footing's own plan centroid (local
    x = y = 0), each running the full length ``mesh_bar_lengths`` computed
    for its own direction -- the straight case (#199 adds hook legs and
    L-shape alternation on top of this).
    """
    half_x = lengths.mesh_bar_x_mm / 2.0
    half_y = lengths.mesh_bar_y_mm / 2.0
    z_x_mm = bottom_cover_mm + mesh_bar_x_dia_mm / 2.0
    z_y_mm = bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm / 2.0

    bar_x = BarEndpoints(
        start=LocalPoint(-half_x, 0.0, z_x_mm),
        end=LocalPoint(half_x, 0.0, z_x_mm))
    bar_y = BarEndpoints(
        start=LocalPoint(0.0, -half_y, z_y_mm),
        end=LocalPoint(0.0, half_y, z_y_mm))
    return bar_x, bar_y


def _mesh_bar_hook_points(z_mm, hook_leg_mm, elevation_mm, hook_plan,
                          along_x, offset_mm=0.0):
    """One bar's bent centreline (:class:`MeshBarGeometry`'s own
    ``points``), footing-local mm.

    Spec Ref: Sec 3 Story 1, Sec 4 -- the straight middle run spans
    ``z_mm`` alone (Sec 3's ``Z``/``Z2``, NOT ``mesh_bar_x_mm``/
    ``mesh_bar_y_mm``, which already fold both hook legs into one total
    length for Sec 4's bookkeeping formula, not into one straight run).
    Each end whose ``hook_plan`` says ``needs_hook`` gets a VERTICAL leg
    of length ``hook_leg_mm`` (Sec 3's ``N``/``N2``), bent straight UP
    (Sec 5: "bend the bar up") from that end's own elevation -- never
    sideways, so unlike the dowel array (R10) there is no per-bar outward
    direction to derive, only a fixed +Z.

    #232 (R11, docs/footing/spec-amendments.md): ``offset_mm`` is this
    bar's own position along the axis PERPENDICULAR to its run (Y for a
    ``mesh_bar_x`` bar, X for a ``mesh_bar_y`` bar) -- defaults to 0.0 so
    every caller that predates #232 (the one representative bar, centred
    on the footing's own plan centroid) is unchanged. Parametrizing this
    existing single-bar builder is the array; the hook-point logic itself
    is not duplicated anywhere for the array (this ticket's own
    instruction).
    """
    half = z_mm / 2.0
    if along_x:
        start_xy = (-half, offset_mm)
        end_xy = (half, offset_mm)
    else:
        start_xy = (offset_mm, -half)
        end_xy = (offset_mm, half)

    def _point(xy, z_mm_value):
        return LocalPoint(xy[0], xy[1], z_mm_value)

    points = []
    if hook_plan.start.needs_hook:
        points.append(_point(start_xy, elevation_mm + hook_leg_mm))
    points.append(_point(start_xy, elevation_mm))
    points.append(_point(end_xy, elevation_mm))
    if hook_plan.end.needs_hook:
        points.append(_point(end_xy, elevation_mm + hook_leg_mm))
    return MeshBarGeometry(points=tuple(points))


def bottom_mesh_bar_geometry(lengths, bottom_cover_mm, mesh_bar_x_dia_mm,
                             mesh_bar_y_dia_mm, bar_x_hooks, bar_y_hooks):
    """#229: ``mesh_bar_x``/``mesh_bar_y``'s own bent centrelines for the
    BOTTOM mat, honouring each bar's own :class:`BarHookPlan` (#199/#200).

    Same elevations ``local_mesh_bar_endpoints`` already uses (unchanged --
    only the horizontal span and the added vertical legs differ, not the
    bars' own Z datum or stacking order).

    Deliberately bottom-mat-only: the top mat's own hook direction (would
    it bend up, toward the bottom mat, or down, toward the top face?) is
    not stated anywhere in the spec and the top mat has no placement
    adapter yet (`IsolatedFooting.extension/CONTEXT.md`'s own "Not yet
    in" list) -- guessing that direction now, with no consumer to verify
    it against, is exactly the guessing REUSE_GUIDELINES.md Sec 3 refuses.
    """
    z_x_mm = bottom_cover_mm + mesh_bar_x_dia_mm / 2.0
    z_y_mm = bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm / 2.0
    bar_x = _mesh_bar_hook_points(
        lengths.z_mm, lengths.n_mm, z_x_mm, bar_x_hooks, along_x=True)
    bar_y = _mesh_bar_hook_points(
        lengths.z2_mm, lengths.n2_mm, z_y_mm, bar_y_hooks, along_x=False)
    return bar_x, bar_y


def mesh_bar_offsets_mm(width_mm, spacing_mm):
    """R11 (docs/footing/spec-amendments.md): how many bars fit across
    ``width_mm`` at (at most) ``spacing_mm`` apart, evenly redistributed
    so the width is filled exactly with no remainder -- a direct user
    spacing, count derived, per R11's own ruling. Returns the list of
    centreline offsets (mm), symmetric about the mat's own centreline
    (0.0), first and last exactly at the width's own two edges.

    This is a fresh, footing-specific "how many fit at this spacing
    across this width" computation, deliberately NOT
    ``column_layout.perimeter_bar_positions`` -- that function solves a
    perimeter-LOOP problem (bars shared between two adjacent faces); this
    is a parallel-array-across-a-RECTANGLE problem, with no shared
    corners to de-duplicate (R11's own ticket text).

    ``n_spaces = ceil(width / spacing)``, at least 1 (so two bars --
    one at each edge -- is the minimum a footing this narrow still
    gets); ``achieved_spacing = width / n_spaces`` (<= ``spacing_mm``,
    same "redistribute to fill exactly" shape this repo's beam tool uses
    for `SetLayoutAsMaximumSpacing` zones -- an independently-derived
    match, not a reuse, per element isolation).
    """
    if width_mm <= 0:
        raise ValueError(
            "width_mm must be positive, got %r." % (width_mm,))
    if spacing_mm <= 0:
        raise ValueError(
            "spacing_mm must be positive, got %r." % (spacing_mm,))
    n_spaces = int(math.ceil(width_mm / spacing_mm))
    if n_spaces < 1:
        n_spaces = 1
    achieved_spacing_mm = width_mm / n_spaces
    half = width_mm / 2.0
    return [-half + index * achieved_spacing_mm
            for index in range(n_spaces + 1)]


def bottom_mesh_bar_array_geometry(lengths, bottom_cover_mm, mesh_bar_x_dia_mm,
                                   mesh_bar_y_dia_mm, bar_x_hooks, bar_y_hooks,
                                   bar_x_spacing_mm, bar_y_spacing_mm):
    """#232 (R11): the FULL bottom-mesh array, per direction -- every bar
    reuses ``_mesh_bar_hook_points`` (the SAME per-bar hook logic
    ``bottom_mesh_bar_geometry`` already builds for the one representative
    bar), only each bar's own offset along the axis perpendicular to its
    run differs. The hook decision itself (``bar_x_hooks``/``bar_y_hooks``)
    is IDENTICAL for every bar in a direction's array -- this ticket does
    not recompute a per-bar-index hook plan (that would be new
    ``MAT_SHAPE_L_ALTERNATING`` scope over a real array, not named by this
    ticket).

    Per R11's own reading of ``local_mesh_bar_endpoints``'s axis
    convention: ``mesh_bar_x`` bars run along local X (straight run =
    Sec 3's ``Z``, the a-direction) and are spaced along Y across
    ``Z2``/``b``'s own extent; ``mesh_bar_y`` bars run along local Y
    (straight run = ``Z2``, the b-direction) and are spaced along X
    across ``Z``/``a``'s own extent.

    Returns ``(bar_x_array, bar_y_array)``, each a tuple of
    :class:`MeshBarGeometry` when its own ``spacing_mm`` is supplied, or
    ``None`` when it is not (that direction keeps using the single
    representative bar -- ``BottomMeshPlan.bar_x_geometry``/
    ``bar_y_geometry`` -- every caller that predates #232 already reads).
    """
    z_x_mm = bottom_cover_mm + mesh_bar_x_dia_mm / 2.0
    z_y_mm = bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm / 2.0

    bar_x_array = None
    if bar_x_spacing_mm is not None:
        y_offsets = mesh_bar_offsets_mm(lengths.z2_mm, bar_x_spacing_mm)
        bar_x_array = tuple(
            _mesh_bar_hook_points(lengths.z_mm, lengths.n_mm, z_x_mm,
                                 bar_x_hooks, along_x=True, offset_mm=y_mm)
            for y_mm in y_offsets)

    bar_y_array = None
    if bar_y_spacing_mm is not None:
        x_offsets = mesh_bar_offsets_mm(lengths.z_mm, bar_y_spacing_mm)
        bar_y_array = tuple(
            _mesh_bar_hook_points(lengths.z2_mm, lengths.n2_mm, z_y_mm,
                                 bar_y_hooks, along_x=False, offset_mm=x_mm)
            for x_mm in x_offsets)

    return bar_x_array, bar_y_array


def local_top_mesh_bar_endpoints(lengths, top_cover_mm, footing_thickness_mm,
                                  mesh_bar_x_dia_mm, mesh_bar_y_dia_mm):
    """The top mat's two straight bars' centreline endpoints, footing-local
    mm -- found missing in review (PR #214): #201 originally reused
    ``local_mesh_bar_endpoints`` unchanged for the top mat, which measures
    Z from ``bottom_cover_mm`` regardless of which mat is being built, so
    the "top mat" landed at the exact same elevation as the bottom mat
    instead of near the top face.

    ``docs/footing/spec-amendments.md`` R3: spec Sec 7 names a TOP+BTM
    toggle but never gives an explicit top-mat vertical formula the way
    Sec 4's N/N2 do for the bottom mat -- this mirrors
    ``local_mesh_bar_endpoints`` exactly, measured from the TOP face
    downward instead of from the bottom face upward (``mesh_bar_x``
    nearest the top face, ``mesh_bar_y`` one ``mesh_bar_x`` diameter
    further into the footing), and Essam confirmed this convention is
    correct ("yes this is right") before it shipped, not assumed silently.
    """
    half_x = lengths.mesh_bar_x_mm / 2.0
    half_y = lengths.mesh_bar_y_mm / 2.0
    z_x_mm = footing_thickness_mm - top_cover_mm - mesh_bar_x_dia_mm / 2.0
    z_y_mm = (footing_thickness_mm - top_cover_mm
              - mesh_bar_x_dia_mm - mesh_bar_y_dia_mm / 2.0)

    bar_x = BarEndpoints(
        start=LocalPoint(-half_x, 0.0, z_x_mm),
        end=LocalPoint(half_x, 0.0, z_x_mm))
    bar_y = BarEndpoints(
        start=LocalPoint(0.0, -half_y, z_y_mm),
        end=LocalPoint(0.0, half_y, z_y_mm))
    return bar_x, bar_y


def bar_end_hook_decision(offset_mm, db_mm, ld_multiplier):
    """One bar end's hook/development-length decision.

    Spec Ref: Sec 3 (Story 2), Sec 5: ``LD = multiplier * db``; compare
    ``LD`` to the straight length available outside the column footprint
    at this end (``offset_mm`` -- Sec 2/3's ``X`` for an a-direction end,
    ``Y`` for a b-direction end):
        LD > offset -> this end needs a hook.
        offset > LD -> this end stays straight (no hook needed here).

    One function, parametrized by ``offset_mm``/``db_mm`` -- reused as-is
    for both mesh_bar_x ends (with X) and mesh_bar_y ends (with Y), never
    duplicated per direction (this ticket's own instruction).

    ``docs/footing/spec-amendments.md`` R2 (revised): when ``LD ==
    offset`` exactly, this raises ``HookDevelopmentLengthTieError``
    rather than picking a side. Essam's ruling here is not a silent
    default but a redirect: the engineer should get an explicit choice
    between U-shape and L-shape-alternating for that mat, via the SAME
    per-mat override #200 already built (``bar_hook_plan_for_mat`` with
    ``mat_shape_mode`` set) -- not a new third option invented for this
    boundary alone.
    """
    ld_mm = ld_multiplier * db_mm
    if ld_mm == offset_mm:
        raise HookDevelopmentLengthTieError(
            "Required development length equals the available straight "
            "offset exactly (LD=offset=%r mm); specs/isolated-footing.md "
            "Sec 5 does not define this end's shape when they are equal. "
            "Set an explicit mat_shape_mode (MAT_SHAPE_U or "
            "MAT_SHAPE_L_ALTERNATING) for this mat instead of leaving it "
            "on automatic." % (offset_mm,))
    return BarEndHook(ld_mm=ld_mm, needs_hook=ld_mm > offset_mm)


def bar_hook_plan(start_offset_mm, end_offset_mm, db_mm, ld_multiplier):
    """The whole-bar hook plan: both ends' decisions plus the resulting
    shape.

    Spec Ref: Sec 3 (Story 2), Sec 5: U-shape is the default (both ends
    hooked); as soon as either end's own comparison finds
    ``offset > LD``, that end stays straight and the bar "switches ...
    from U-shape to L-shape -- hook only the end(s) where LD > offset
    still applies". So the bar is U-shape only when BOTH ends still need
    a hook; any other outcome is the L-shape this rule switches to.

    ``start_offset_mm``/``end_offset_mm`` are independent per end (a
    future non-symmetric footing could differ end to end -- spec Sec 0
    F4 -- even though today's symmetric ``a = 2*X + Cw`` model gives both
    ends of one bar the same offset).
    """
    start = bar_end_hook_decision(start_offset_mm, db_mm, ld_multiplier)
    end = bar_end_hook_decision(end_offset_mm, db_mm, ld_multiplier)
    shape = SHAPE_U if (start.needs_hook and end.needs_hook) else SHAPE_L
    return BarHookPlan(start=start, end=end, shape=shape)


def bar_hook_plan_for_mat(bar_index, mat_shape_mode, start_offset_mm,
                           end_offset_mm, db_mm, ld_multiplier):
    """The whole-bar hook plan, honouring a mat-wide user override.

    Spec Ref: Sec 3 (Story 3), Sec 6: "Whichever the user picks for a
    given mat overrides Story 2's per-end LD comparison for that mat.
    Story 2's comparison only applies if/when the tool needs to decide
    the shape itself -- this input makes that unnecessary."

    ``mat_shape_mode`` is ``None``, ``MAT_SHAPE_U`` or
    ``MAT_SHAPE_L_ALTERNATING``:

    - ``None`` -- no override given; delegate to ``bar_hook_plan`` so
      Story 2's own LD-vs-offset comparison decides, exactly as #199
      already does. ``bar_index`` is unused in this branch.
    - ``MAT_SHAPE_U`` -- every bar hooked at both ends, unconditionally.
      ``LD``/offset are never compared here at all -- the override makes
      that comparison "unnecessary" per Sec 6, not merely pre-empted.
    - ``MAT_SHAPE_L_ALTERNATING`` -- every bar is L-shaped (one hook);
      "consecutive bars alternate which end is hooked" (Sec 6): the start
      end is hooked on even ``bar_index`` (0, 2, 4, ...) and the end end
      is hooked on odd ``bar_index`` (1, 3, 5, ...), so the mat is
      anchored at both edges overall.

    ``ld_mm`` is still reported on both ends in every branch (Sec 5's
    ``LD = multiplier * db`` is informational bookkeeping, not itself
    what decides ``needs_hook`` once a mat-wide override is set).
    """
    if mat_shape_mode is None:
        return bar_hook_plan(
            start_offset_mm, end_offset_mm, db_mm, ld_multiplier)

    ld_mm = ld_multiplier * db_mm

    if mat_shape_mode == MAT_SHAPE_U:
        return BarHookPlan(
            start=BarEndHook(ld_mm=ld_mm, needs_hook=True),
            end=BarEndHook(ld_mm=ld_mm, needs_hook=True),
            shape=SHAPE_U)

    if mat_shape_mode == MAT_SHAPE_L_ALTERNATING:
        hook_start = (bar_index % 2 == 0)
        return BarHookPlan(
            start=BarEndHook(ld_mm=ld_mm, needs_hook=hook_start),
            end=BarEndHook(ld_mm=ld_mm, needs_hook=not hook_start),
            shape=SHAPE_L)

    raise ValueError(
        "Unknown mat_shape_mode %r; expected None, MAT_SHAPE_U or "
        "MAT_SHAPE_L_ALTERNATING" % (mat_shape_mode,))
