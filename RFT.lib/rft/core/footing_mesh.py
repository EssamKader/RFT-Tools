# -*- coding: utf-8 -*-
"""Bottom-mesh bar length geometry for the isolated footing tool, plus the
per-bar-end hook/development-length decision (#199) and the per-mat
U-shape/L-shape-alternating user override on top of it (#200).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 1, Story 2 and Story 3),
Sec 4, Sec 5, Sec 6, Sec 2 (naming).
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").
"""

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
    they are exactly equal. Same discipline the X == Y gap hit before
    R1 resolved it (docs/footing/spec-amendments.md): REUSE_GUIDELINES.md
    Sec 3 ("Explicit Refusals") requires a raise here, not a guessed
    tie-break, until the project owner rules on this one too.
    """


#: One bar end's hook decision. ``ld_mm`` is Sec 5's ``LD = multiplier *
#: db`` for the bar this end belongs to; ``needs_hook`` is the Sec 5
#: comparison result for this end alone.
BarEndHook = namedtuple("BarEndHook", ["ld_mm", "needs_hook"])

#: A whole bar's hook plan: its two ends' ``BarEndHook`` and the
#: resulting overall ``shape`` (``SHAPE_U``/``SHAPE_L``).
BarHookPlan = namedtuple("BarHookPlan", ["start", "end", "shape"])


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

    Raises ``HookDevelopmentLengthTieError`` when ``LD == offset`` -- see
    that class's docstring.
    """
    ld_mm = ld_multiplier * db_mm
    if ld_mm == offset_mm:
        raise HookDevelopmentLengthTieError(
            "Required development length equals the available straight "
            "offset exactly (LD=offset=%r mm); specs/isolated-footing.md "
            "Sec 5 does not define this end's shape when they are equal"
            % (offset_mm,))
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
      ``LD``/offset are never compared, so this never raises
      ``HookDevelopmentLengthTieError`` -- the override makes that
      comparison "unnecessary" per Sec 6, not merely pre-empted.
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
