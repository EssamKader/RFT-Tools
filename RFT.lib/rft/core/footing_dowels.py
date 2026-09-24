# -*- coding: utf-8 -*-
"""Column dowel embedment/hook sizing for the isolated footing tool (#202).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 5), Sec 8.
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").

``⌀mesh_bar_x``/``⌀mesh_bar_y`` in Sec 8's ``a_dowel`` formula are read
from the SAME ``FootingInputs.mesh_bar_x_dia_mm``/``mesh_bar_y_dia_mm``
fields #198's mesh geometry already carries -- never hardcoded, never
re-derived independently here (this ticket's own instruction).
"""

from collections import namedtuple

from .footing_mesh import BarEndpoints, LocalPoint

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


def local_dowel_bar_geometry(embedment, bottom_cover_mm, mesh_bar_x_dia_mm,
                              mesh_bar_y_dia_mm):
    """The dowel bar's footing-local centreline geometry (mm), centred on
    the footing's own plan centroid.

    Spec Ref: Sec 8 -- "hooked horizontally at the bottom, resting on top
    of the bottom mesh". The bend corner sits at the SAME elevation
    ``footing_mesh.local_mesh_bar_endpoints`` already uses as the top of
    ``mesh_bar_y`` (``bottom_cover_mm + mesh_bar_x_dia_mm +
    mesh_bar_y_dia_mm``) -- read from the same three inputs, not
    re-derived from the mesh plan object, since only the diameters/cover
    (already in ``FootingInputs``) are needed, matching how ``a_dowel``
    itself is computed from the same fields.

    Placement direction (which horizontal axis the hook leg runs along)
    is NOT stated anywhere in Sec 8 -- the spec names only the two
    lengths, not a plan direction for the hook. This picks +X arbitrarily
    and documents it as an engineering placement choice, the same way
    #201's top-mat elevation formula was flagged rather than silently
    assumed to be settled: **flag to Essam before this runs against a
    live host** if a specific hook direction (e.g. toward the column's
    own Primary Reinforcement direction) is intended instead.
    """
    bend_z_mm = bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm
    bend = LocalPoint(0.0, 0.0, bend_z_mm)
    hook_far_end = LocalPoint(embedment.b_dowel_mm, 0.0, bend_z_mm)
    top = LocalPoint(0.0, 0.0, bend_z_mm + embedment.a_dowel_mm)

    bottom_hook = BarEndpoints(start=hook_far_end, end=bend)
    vertical = BarEndpoints(start=bend, end=top)
    return DowelBarGeometry(bottom_hook=bottom_hook, vertical=vertical)


def translate_dowel_bar_geometry(geometry, u_mm=0.0, v_mm=0.0):
    """Shift a ``DowelBarGeometry`` (built by :func:`local_dowel_bar_geometry`
    at the footing's own plan centroid, ``x_mm == y_mm == 0``) sideways to a
    real footing-local ``(u, v)`` dowel position.

    #222 (specs/isolated-footing-dowel-array.md Sec 3 Story 3): "this story
    changes WHERE dowels are and HOW MANY there are, not how any single
    dowel's own vertical geometry is sized." Only the plan (x/y) coordinates
    move; ``z_mm`` (the bend-corner/top elevation :func:`local_dowel_bar_
    geometry` already computed) and every embedment length are untouched,
    so this is a translation, never a re-sizing.

    This module owns ``DowelBarGeometry``'s own field structure, so it is
    the one place that reaches into ``bottom_hook``/``vertical`` -- callers
    (``rft.core.footing_plan``) only ever assemble the result into a plan,
    never touch the namedtuple's own fields directly (found in review,
    PR #225).

    Defaults to a no-op shift (``u_mm=v_mm=0.0``) so the single
    representative bar #202 always built can be produced by the same call
    shape a real array position uses.
    """
    def _shift(point):
        return LocalPoint(point.x_mm + u_mm, point.y_mm + v_mm, point.z_mm)

    return DowelBarGeometry(
        bottom_hook=BarEndpoints(
            start=_shift(geometry.bottom_hook.start),
            end=_shift(geometry.bottom_hook.end)),
        vertical=BarEndpoints(
            start=_shift(geometry.vertical.start),
            end=_shift(geometry.vertical.end)))
