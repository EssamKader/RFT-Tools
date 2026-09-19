# -*- coding: utf-8 -*-
"""Bottom-mesh bar length geometry for the isolated footing tool, straight
case only (no hooks, no L-shape alternation -- that is #199).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 1), Sec 4, Sec 2 (naming).
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").
"""

from collections import namedtuple

#: Spec Ref: Sec 2/3, "Primary Reinforcement" / "Secondary Reinforcement".
DIRECTION_X = "X"
DIRECTION_Y = "Y"


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
