# -*- coding: utf-8 -*-
"""``perimeter_tie`` closed-loop/split placement for the isolated footing
tool (#244).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 7), Sec 10; R14
(``docs/footing/spec-amendments.md``).

Converts ``rft.core.footing_plan.PerimeterTiePlan`` geometry (mm,
footing-local, centroid at x=y=0, bottom face at z=0) to Revit internal
units at the mm/feet boundary (``rft.revit.units``, REUSE_GUIDELINES.md
Sec 1) and calls ``Rebar.CreateFromCurves`` once per ladder level -- ONE
closed-loop ``Rebar`` per level in the common case
(``PerimeterTieSplice.bar_count == 1``), or TWO open ``Rebar`` elements
per level in the split case (``bar_count == 2``, R14).

## Reuse plan (per issue #244's own ticket body -- do not re-derive)

- Footing-local-to-world conversion reuses ``rft.revit.footing_mesh.
  _footing_origin``/``_to_world_point`` AS-IS -- the SAME convention every
  other footing placement adapter in this tool uses (``footing_mesh.py``,
  ``footing_dowels.py``, ``footing_dowel_ties.py``), NOT column-host
  conventions (a footing ``FamilyInstance`` is not proven to expose a
  column's own ``HandOrientation``/``FacingOrientation``).
- The common (single-loop) case is mechanically identical to
  ``footing_dowel_ties.place_dowel_ties``'s own closed-loop placement
  (#242): same corner-to-corner ``Line.CreateBound`` chain, closing back
  to the first point, same ``norm = XYZ.BasisZ`` (a horizontal loop
  plane), same ``RebarStyle.StirrupTie``/hook-orientation call shape.
  ``_loop_curves``/``_create_loop_rebar`` below mirror that module's own
  ``_loop_curves``/``_create_dowel_tie_rebar`` closely, built from
  ``PerimeterTieGeometry.corners`` instead of a dowel array's own loop.
- The split case (R14) places each bar as an OPEN multi-segment polyline
  (``rft.core.footing_perimeter_tie.PerimeterTieSplitBars.bar1_points``/
  ``bar2_points``, already built by ``rft.core.footing_plan``'s own
  ``_build_perimeter_tie_plan``) -- a connected chain of ``Line``s, NOT
  closed back to its own start (unlike the single-loop case above). Each
  split bar uses ``RebarStyle.Standard`` with NO hook type (``None``,
  ``None``), matching ``footing_dowels.py``'s own ``_create_dowel_rebar``
  precedent for an open, non-hooked, multi-segment bar shape -- a split
  bar is a straight run turning at corners, lap-spliced with its
  neighbour (R14), not a closed tie needing a hook at either end. This
  is a DELIBERATE style difference from the closed-loop case (``RebarStyle.
  StirrupTie`` plus a real hook type), not an inconsistency: the closed
  loop is still one continuous tie shape needing a hook to close itself
  structurally, while an open bar has two free, lap-spliced ends instead.

## The open-bar ``norm`` question (flagged, not guessed, per the ticket's
own instruction)

The whole ``perimeter_tie`` shape -- both the closed loop and each split
open bar -- lies entirely in ONE horizontal plane (a single Z level per
``PerimeterTieLadder`` level; R14's own arc-length unroll never changes
Z). ``rft.revit.footing_dowel_ties``'s own reasoning for
``norm = XYZ.BasisZ`` is that ``norm`` must be perpendicular to the
loop's own (horizontal) plane for a CLOSED rectangular loop -- and an
open multi-segment polyline confined to that SAME horizontal plane is
still, geometrically, planar with the same normal direction, so
``XYZ.BasisZ`` is used here for the open-bar case too. This is NOT the
same question ``rft.revit.footing_dowels``'s own ``_dowel_norm`` answers
(a BENT bar whose two legs lie in a VERTICAL plane, where ``norm`` must
be perpendicular to that vertical bend plane instead) -- conflating the
two would be exactly the mistake this ticket's own body warns against.
Reasoning is sound but UNVERIFIED against a live host for an open,
multi-segment, planar-horizontal curve chain specifically (see "SHAPE
UNVERIFIED" below).

## SHAPE UNVERIFIED

None of the combinations this module calls have been run against a live
host. ``docs/footing/verification/issue-197-footing-tracer-bullet.md``
Sec 4 ("Still unverified") already names closed-loop shapes on a footing
host as untested -- the split, open-bar case is a further, even less
tested combination:

1. **A closed-loop shape on a footing host** -- same unverified status
   ``footing_dowel_ties.py`` already carries; not re-proven here, this
   module reuses that exact reasoning, not a new one.
2. **An OPEN multi-segment ``Rebar.CreateFromCurves`` call on a footing
   host, with ``norm = XYZ.BasisZ`` for a horizontal (not vertical) bend
   plane.** ``footing_dowels.py``'s own multi-curve call (SHAPE
   UNVERIFIED there too) is the closest existing precedent, but that
   bar's own two curves lie in a VERTICAL plane with a DIFFERENT,
   per-bar ``norm`` -- an open chain confined to a HORIZONTAL plane, with
   a FIXED ``norm``, is a new combination, not proven by that precedent
   either. Flagged rather than claimed proven -- do not run this against
   a live host and then cite this module's own docstring as if it were a
   verification; write a new tracer-bullet doc first (the #236 lesson
   this ticket's own body names explicitly).
3. **Two separate ``Rebar`` elements overlapping in space at the same Z
   level** (the two bars' own middle overlap, ``lap_mm`` long, per R14) --
   no verification exists that Revit accepts two independently-hosted
   ``Rebar`` elements whose curves geometrically coincide/overlap over
   part of their own run; this is a materially different question from
   either bar existing alone.

Per this repo's hard rule, this module does not open, commit or roll back
a transaction -- the caller owns the one transaction for the whole footing
(so a failure here leaves the model exactly as it was).
"""

from Autodesk.Revit.DB import Line, XYZ
from Autodesk.Revit.DB.Structure import Rebar, RebarHookOrientation, RebarStyle

from ..core.footing_mesh import LocalPoint
from .footing_mesh import _footing_origin, _to_world_point

#: Same hook orientation ``footing_dowel_ties.py`` reuses from
#: ``rft.revit.column_place_ties``'s own R21 measurement -- see that
#: module's own "SHAPE UNVERIFIED" note, point 2, for the winding
#: reasoning this reuses unchanged.
_HOOK_ORIENTATION = RebarHookOrientation.Left

#: ``Rebar.CreateFromCurves``'s own defaults, matching every other
#: placement module in this repo.
_USE_EXISTING_SHAPE_IF_POSSIBLE = True
_CREATE_NEW_SHAPE = True


class PerimeterTieNotPlaceableError(Exception):
    """``perimeter_tie_plan`` has no ladder to place from -- the caller
    must build ``perimeter_tie_plan`` via
    ``rft.core.footing_plan.build_footing_plan`` (the one composing
    module rule) before calling this module.
    """


class PerimeterTieSplitBarsMissingError(Exception):
    """``perimeter_tie_plan.geometry.splice.bar_count == 2`` (a split
    loop is required) but ``perimeter_tie_plan.split_bars`` is ``None`` --
    the engineer has not yet typed both
    ``perimeter_tie_first_bar_length_mm``/``perimeter_tie_second_bar_
    length_mm`` (R5), so there is no two-bar shape to place. Refused here
    rather than silently placing nothing or falling back to an
    (incorrect, over-length) single closed loop.
    """


def _world_points(origin, z_mm, points):
    origin_x, origin_y, origin_z = origin
    return [
        _to_world_point(
            origin_x, origin_y, origin_z, LocalPoint(point.x_mm, point.y_mm, z_mm))
        for point in points]


def _loop_curves(origin, z_mm, corners):
    """The closed loop's own footing-local corners, at ONE level's Z, as a
    chain of connected world ``Line``s -- the last one closing back to the
    first (a closed polygon) -- mirrors ``footing_dowel_ties._loop_
    curves`` exactly, built from ``PerimeterTieGeometry.corners`` instead
    of a dowel-array loop's own corners.
    """
    world_points = _world_points(origin, z_mm, corners)
    count = len(world_points)
    return [Line.CreateBound(world_points[i], world_points[(i + 1) % count])
            for i in range(count)]


def _open_chain_curves(origin, z_mm, points):
    """An OPEN multi-segment polyline's own connected world ``Line``s --
    NOT closed back to the first point, unlike ``_loop_curves`` above
    (R14: each split bar is an open bar, not a closed shape).
    """
    world_points = _world_points(origin, z_mm, points)
    return [Line.CreateBound(world_points[i], world_points[i + 1])
            for i in range(len(world_points) - 1)]


def _create_loop_rebar(document, footing, curves, bar_type, hook_type):
    """The closed-loop shape -- ``RebarStyle.StirrupTie`` plus a real hook
    type, exactly mirroring ``footing_dowel_ties._create_dowel_tie_rebar``.
    """
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


def _create_open_bar_rebar(document, footing, curves, bar_type):
    """One split bar -- ``RebarStyle.Standard``, no hook type (shape is
    built entirely from ``curves``), exactly mirroring
    ``footing_dowels._create_dowel_rebar``'s own open, non-hooked,
    multi-segment bar call.
    """
    return Rebar.CreateFromCurves(
        document,
        RebarStyle.Standard,
        bar_type,
        None,  # startHook -- shape is built from curves, not a hook type
        None,  # endHook
        footing,
        XYZ.BasisZ,
        curves,
        _HOOK_ORIENTATION,
        _HOOK_ORIENTATION,
        _USE_EXISTING_SHAPE_IF_POSSIBLE,
        _CREATE_NEW_SHAPE,
    )


def place_perimeter_ties(document, footing, perimeter_tie_plan, bar_type,
                          hook_type):
    """Places one ``perimeter_tie`` shape per level in
    ``perimeter_tie_plan.ladder.levels_mm``, hosted directly on
    ``footing`` -- the SAME footing every other placement adapter in this
    tool hosts on.

    When ``perimeter_tie_plan.geometry.splice.bar_count == 1`` (the
    common case), places ONE closed-loop ``Rebar`` per level, from
    ``perimeter_tie_plan.geometry.corners``. When ``bar_count == 2``
    (R14), places TWO open ``Rebar`` elements per level instead, from
    ``perimeter_tie_plan.split_bars.bar1_points``/``bar2_points``.

    ``perimeter_tie_plan`` is a ``rft.core.footing_plan.PerimeterTiePlan``
    -- the caller must build it via
    ``rft.core.footing_plan.build_footing_plan``, never by calling
    ``rft.core.footing_perimeter_tie`` directly (the one composing module
    rule, docs/token-efficient-expansion.md Sec 7).

    Raises :class:`PerimeterTieNotPlaceableError` if
    ``perimeter_tie_plan.ladder`` is ``None``, and
    :class:`PerimeterTieSplitBarsMissingError` if a split is required but
    ``perimeter_tie_plan.split_bars`` has not been built yet (R5's two
    bar lengths not both typed).

    Returns the list of created ``Rebar`` elements, in level order; for a
    split loop, each level contributes TWO elements (bar 1 then bar 2).
    """
    if perimeter_tie_plan.ladder is None:
        raise PerimeterTieNotPlaceableError(
            "This footing's perimeter_tie plan has no vertical ladder to "
            "place -- perimeter_tie_spacing_mm/perimeter_tie_quantity "
            "must both be supplied before build_footing_plan can build "
            "one (see rft.core.footing_plan.PerimeterTiePlan's own "
            "docstring).")

    bar_count = perimeter_tie_plan.geometry.splice.bar_count
    if bar_count == 2 and perimeter_tie_plan.split_bars is None:
        raise PerimeterTieSplitBarsMissingError(
            "This perimeter_tie's own length (%.1f mm) exceeds the 12m "
            "stock length, so R14 requires two open bars, but "
            "perimeter_tie_first_bar_length_mm/perimeter_tie_second_bar_"
            "length_mm (R5) have not both been typed yet -- there is no "
            "two-bar shape to place."
            % (perimeter_tie_plan.geometry.length_mm,))

    origin = _footing_origin(footing)
    rebars = []
    for level in perimeter_tie_plan.ladder.levels_mm:
        if bar_count == 1:
            curves = _loop_curves(
                origin, level, perimeter_tie_plan.geometry.corners)
            rebars.append(
                _create_loop_rebar(
                    document, footing, curves, bar_type, hook_type))
        else:
            bar1_curves = _open_chain_curves(
                origin, level, perimeter_tie_plan.split_bars.bar1_points)
            bar2_curves = _open_chain_curves(
                origin, level, perimeter_tie_plan.split_bars.bar2_points)
            rebars.append(
                _create_open_bar_rebar(document, footing, bar1_curves, bar_type))
            rebars.append(
                _create_open_bar_rebar(document, footing, bar2_curves, bar_type))
    return rebars
