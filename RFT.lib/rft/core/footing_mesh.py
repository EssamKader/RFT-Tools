# -*- coding: utf-8 -*-
"""Bottom-mesh bar length geometry for the isolated footing tool, plus the
per-bar-end hook/development-length decision (#199).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 1 and Story 2), Sec 4,
Sec 5, Sec 2 (naming).
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


class FootingDirectionTieError(ValueError):
    """X and Y column-face offsets are exactly equal.

    Spec Ref: Sec 2/3 states the rule only as "if X > Y => Primary
    Reinforcement in X direction". It does not say what happens when
    X == Y, and that is a genuine gap in the LOCKED spec, not a case to
    guess at -- REUSE_GUIDELINES.md Sec 3, "Explicit Refusals: do not
    guess missing edge cases".
    """


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
    they are exactly equal. Same discipline as ``FootingDirectionTieError``
    above: REUSE_GUIDELINES.md Sec 3 ("Explicit Refusals") requires a
    raise here, not a guessed tie-break.
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

    Raises ``FootingDirectionTieError`` when the two offsets are exactly
    equal -- see that class's docstring.
    """
    if x_offset_mm > y_offset_mm:
        return DIRECTION_X
    if y_offset_mm > x_offset_mm:
        return DIRECTION_Y
    raise FootingDirectionTieError(
        "X and Y column-face offsets are exactly equal (%r mm); "
        "specs/isolated-footing.md Sec 2/3 does not define which "
        "direction is Primary when X == Y" % (x_offset_mm,))


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
