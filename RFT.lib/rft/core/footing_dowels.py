# -*- coding: utf-8 -*-
"""Column dowel embedment/hook sizing for the isolated footing tool (#202).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 5), Sec 8.
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").

``⌀mesh_bar_x``/``⌀mesh_bar_y`` in Sec 8's ``a_dowel`` formula are read
from the SAME ``FootingInputs.mesh_bar_x_dia_mm``/``mesh_bar_y_dia_mm``
fields #198's mesh geometry already carries -- never hardcoded, never
re-derived independently here (this ticket's own instruction).

R10 (docs/footing/spec-amendments.md, found by Essam on a live-model
screenshot): a dowel's hook must bend OUTWARD from the column's own
centroid, never toward it -- a face bar straight out perpendicular to
its face, a corner bar along the 45-degree diagonal, the same
"outward-from-centroid" reasoning ``rft.core.column_ties.
_outward_bisector`` already uses for triangular ties (read as a pattern,
not imported -- that function solves the harder three-arbitrary-points
case; a rectangle's own faces are axis-aligned, so the direction is
derived directly from each bar's own ``(u, v)`` against the column's own
``half_u``/``half_v``, not via a bisector construction).
"""

import math
from collections import namedtuple

from .footing_mesh import BarEndpoints, LocalPoint

#: How close a bar's own coordinate must sit to a face's half-dimension
#: to count as "on that face" for :func:`dowel_outward_direction` -- the
#: two values are computed by the exact same deterministic arithmetic
#: (``column_layout.perimeter_bar_positions``' own ``half_u``/``half_v``,
#: recomputed here from the same inputs), so this only absorbs floating-
#: point noise, never a genuine ambiguity.
_FACE_TOLERANCE_MM = 1.0e-6

#: Sec 8's default b_dowel before any LD-driven hook upgrade.
DEFAULT_B_DOWEL_MM = 200.0

#: One dowel bar's embedment sizing. ``ld_mm`` is Sec 8's
#: ``LD = multiplier * db`` for the dowel bar itself (``db`` = the dowel
#: bar's OWN diameter, distinct from the mesh bar diameters ``a_dowel``
#: reads).
DowelEmbedment = namedtuple(
    "DowelEmbedment", ["a_dowel_mm", "b_dowel_mm", "ld_mm"])

#: The dowel bar's footing-local geometry (mm), centred on the footing's
#: own plan centroid (x = y = 0), as two connected ``BarEndpoints``
#: (footing_mesh's own LocalPoint/BarEndpoints types -- reused, not
#: redefined, since both describe the same footing-local mm frame):
#: ``bottom_hook`` runs from the hook's far end back to the bend corner,
#: then ``vertical`` continues from that SAME corner straight up -- one
#: continuous bent-bar path, matching the two-curve chain
#: ``rft.revit.column_place_bars._place_run`` already builds for a
#: bent column bar (vertical leg then a second connected curve), not a
#: newly invented shape.
DowelBarGeometry = namedtuple("DowelBarGeometry", ["bottom_hook", "vertical"])


def a_dowel(footing_thickness_mm, bottom_cover_mm, mesh_bar_x_dia_mm,
            mesh_bar_y_dia_mm):
    """Spec Ref: Sec 8 --
    ``a_dowel = footing_thickness - bottom_cover - dia(mesh_bar_x) -
    dia(mesh_bar_y)``.

    This is also, geometrically, the vertical clear distance from the top
    of the bottom mesh (``footing_mesh.local_mesh_bar_endpoints``'s own
    ``bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm`` datum, the
    top face of ``mesh_bar_y``) up to the top of the footing -- matching
    Sec 8's "resting on top of the bottom mesh" wording exactly, not
    coincidentally.
    """
    return (footing_thickness_mm - bottom_cover_mm
            - mesh_bar_x_dia_mm - mesh_bar_y_dia_mm)


def dowel_embedment(footing_thickness_mm, bottom_cover_mm,
                     mesh_bar_x_dia_mm, mesh_bar_y_dia_mm, db_mm,
                     ld_multiplier,
                     b_dowel_default_mm=DEFAULT_B_DOWEL_MM):
    """Spec Ref: Sec 8, the whole Story 5 sizing decision.

    ``a_dowel`` is fixed by the footing's own geometry (see :func:`a_dowel`).
    ``LD = ld_multiplier * db_mm`` (``db_mm`` = the DOWEL bar's own
    diameter -- Sec 8 names it explicitly as a distinct quantity from the
    mesh bar diameters ``a_dowel`` reads). Comparing ``LD`` to
    ``a_dowel + b_dowel_default_mm``:

    - ``LD <= a_dowel + b_dowel_default_mm`` -> keep ``a_dowel``, default
      ``b_dowel = b_dowel_default_mm`` (200mm per spec, unless a caller
      names a different default -- Sec 8 states 200mm as ITS default, not
      as a hardcoded constant no caller may vary).
    - ``LD > a_dowel + b_dowel_default_mm`` -> increase the hook:
      ``b_dowel = LD - a_dowel``.

    Sec 8 gives no explicit tie-break for ``LD == a_dowel +
    b_dowel_default_mm`` the way Sec 5 does for its own comparison (R2,
    docs/footing/spec-amendments.md) -- read literally, "LD <= a_dowel +
    b_dowel" already covers equality on the "keep default" side, so there
    is no ambiguous gap here to raise on; this is not a silent guess, it
    is the comparison the spec's own wording states.
    """
    a_mm = a_dowel(footing_thickness_mm, bottom_cover_mm,
                    mesh_bar_x_dia_mm, mesh_bar_y_dia_mm)
    ld_mm = ld_multiplier * db_mm

    if ld_mm <= a_mm + b_dowel_default_mm:
        b_mm = b_dowel_default_mm
    else:
        b_mm = ld_mm - a_mm

    return DowelEmbedment(a_dowel_mm=a_mm, b_dowel_mm=b_mm, ld_mm=ld_mm)


def positioned_dowel_bar_geometry(embedment, bottom_cover_mm,
                                  mesh_bar_x_dia_mm, mesh_bar_y_dia_mm,
                                  u_mm, v_mm, direction_u, direction_v):
    """The dowel bar's footing-local centreline geometry (mm), at real
    footing-local position ``(u_mm, v_mm)``, with the hook bending along
    ``(direction_u, direction_v)`` -- a unit vector, R10's own per-bar
    outward direction (:func:`dowel_outward_direction`).

    Spec Ref: Sec 8 -- "hooked horizontally at the bottom, resting on top
    of the bottom mesh". The bend corner sits at the SAME elevation
    ``footing_mesh.local_mesh_bar_endpoints`` already uses as the top of
    ``mesh_bar_y`` (``bottom_cover_mm + mesh_bar_x_dia_mm +
    mesh_bar_y_dia_mm``) -- read from the same three inputs, not
    re-derived from the mesh plan object, since only the diameters/cover
    (already in ``FootingInputs``) are needed, matching how ``a_dowel``
    itself is computed from the same fields.

    Only the PLAN position and hook direction vary between bars; ``z_mm``
    (the bend-corner/top elevation) and every embedment length are the
    same for every bar in the array (#222 Sec 3 Story 3: "this story
    changes WHERE dowels are and HOW MANY there are, not how any single
    dowel's own vertical geometry is sized").
    """
    bend_z_mm = bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm
    bend = LocalPoint(u_mm, v_mm, bend_z_mm)
    hook_far_end = LocalPoint(
        u_mm + direction_u * embedment.b_dowel_mm,
        v_mm + direction_v * embedment.b_dowel_mm,
        bend_z_mm)
    top = LocalPoint(u_mm, v_mm, bend_z_mm + embedment.a_dowel_mm)

    bottom_hook = BarEndpoints(start=hook_far_end, end=bend)
    vertical = BarEndpoints(start=bend, end=top)
    return DowelBarGeometry(bottom_hook=bottom_hook, vertical=vertical)


def local_dowel_bar_geometry(embedment, bottom_cover_mm, mesh_bar_x_dia_mm,
                              mesh_bar_y_dia_mm):
    """The single-representative-bar shape #202 always built, centred on
    the footing's own plan centroid -- unchanged output, now a thin call
    into :func:`positioned_dowel_bar_geometry` at the origin with the
    legacy ``+X`` hook direction.

    This fallback path (no live column/array inputs supplied, #202's own
    tracer-bullet scope) has no column shape to be "outward" relative to
    -- there is no real perimeter, so R10's per-bar direction rule does
    not apply here, and the original, already-tested `+X` direction is
    kept exactly as before.
    """
    return positioned_dowel_bar_geometry(
        embedment, bottom_cover_mm, mesh_bar_x_dia_mm, mesh_bar_y_dia_mm,
        u_mm=0.0, v_mm=0.0, direction_u=1.0, direction_v=0.0)


def dowel_hook_exceeds_footing_edge(hook_far_end_x_mm, hook_far_end_y_mm,
                                    half_a_mm, half_b_mm):
    """Issue #230 finding: Sec 8's own ``b_dowel`` formula (``dowel_
    embedment``) has no clamp against the footing's own plan size -- for a
    realistic ``dowel_ld_multiplier``/``dowel_bar_dia_mm`` and a footing
    whose column-face clear offset (``x_offset_mm``/``y_offset_mm``) is
    small relative to the resulting hook, the hook's far end can land
    outside the footing's own plan edge. Confirmed by hand-computation
    against this repo's own UI defaults (x_offset=300mm, y_offset=150mm,
    dowel_ld_multiplier=40, a 400x400 column): the hook on a v-face bar
    (150mm offset) lands past the footing's own half-``b`` edge while the
    same hook on a u-face bar (300mm offset) does not -- see
    ``docs/footing/verification/`` for the numeric write-up this ticket's
    investigation produced.

    This is Sec 8's own formula working as specified, not a placement
    bug (the vertical leg still always lands exactly at ``footing_
    thickness_mm``, proven by ``test_footing_dowels.
    test_local_dowel_bar_geometry_vertical_leg_top_is_top_of_footing``) --
    so this function exists to WARN, not to silently reshape the hook.
    ``half_a_mm``/``half_b_mm`` are the footing's own plan half-extents
    (``a_mm``/2, ``b_mm``/2), in the SAME footing-local frame (centroid at
    x=y=0) the hook's far end (``bottom_hook.start``) already uses --
    never re-derived from a column-relative frame, since #222's own
    ``_build_dowel_plan`` places every bar's ``(u, v)`` directly as this
    footing's own local ``(x, y)`` with no rotation transform (see that
    function's own docstring for the same assumption).
    """
    return (abs(hook_far_end_x_mm) > half_a_mm
            or abs(hook_far_end_y_mm) > half_b_mm)


def dowel_outward_direction(u_mm, v_mm, half_u_mm, half_v_mm, is_corner):
    """R10's own rule, as a unit ``(direction_u, direction_v)``:

    - **Corner bar** (``is_corner``): the 45-degree diagonal away from the
      centroid -- ``normalize(sign(u), sign(v))``.
    - **Face bar**: straight outward, perpendicular to whichever face its
      own coordinate sits at (``|v| == half_v`` -> the top/bottom face,
      direction along v only; ``|u| == half_u`` -> the left/right face,
      direction along u only). Exactly one of the two is true for a
      genuine face-interior bar -- the definition of "not a corner".

    ``half_u_mm``/``half_v_mm`` are the BAR's own half-dimensions
    (``Cw_mm/2 - offset``/``Cd_mm/2 - offset``, the same ``half_u``/
    ``half_v`` ``column_layout.perimeter_bar_positions`` computes
    internally) -- recomputed by the caller from ``PerimeterLayout.
    bar_offset_mm`` and the column's own ``Cw_mm``/``Cd_mm``, never
    guessed, since ``perimeter_bar_positions`` does not return them
    directly (only the TIE's own, different, half-dimensions).
    """
    if is_corner:
        sign_u = 1.0 if u_mm >= 0.0 else -1.0
        sign_v = 1.0 if v_mm >= 0.0 else -1.0
        length = math.sqrt(2.0)
        return sign_u / length, sign_v / length
    if abs(abs(v_mm) - half_v_mm) <= _FACE_TOLERANCE_MM:
        return 0.0, (1.0 if v_mm >= 0.0 else -1.0)
    if abs(abs(u_mm) - half_u_mm) <= _FACE_TOLERANCE_MM:
        return (1.0 if u_mm >= 0.0 else -1.0), 0.0
    raise ValueError(
        "Bar at (u=%.6f, v=%.6f) is not a corner and sits at neither face "
        "(half_u=%.6f, half_v=%.6f) -- this is not a valid perimeter_bar_"
        "positions output; the outward direction cannot be determined."
        % (u_mm, v_mm, half_u_mm, half_v_mm))
