# -*- coding: utf-8 -*-
"""Issue #167 -- reading the top-floor slab above a roof-condition column.

THE ADAPTER for `specs/column-roof-termination.md` sections 1 and 2, R37,
R38, R39, R41 and R42. Everything here touches Revit and decides nothing:
the slab element, its thickness, its cover (with R38's read-or-typed
provenance) and one :class:`~rft.core.column_roof.RoofBendDirection` per
face come out as plain values, and `rft.core.column_roof.terminate_bar`
rules on them. No UI, no report line, no placement -- separate tickets.

## Finding the slab -- R37, R39

**`JoinGeometryUtils.GetJoinedElements` is the sole mechanism used here.**
#161 measured it returning Floor 424637 with no view, no category list and
no ray; the ray (`ReferenceIntersector` through `find_search_view` and
`SUPPORT_CATEGORIES`, already how `column_host.find_support_face_z_mm`
finds this same slab's soffit) agreed exactly on the same host. The
ticket's own reading is that the joined query is the better primary for
that reason, and this module does not also fire the ray: a candidate this
module cannot cross-check cannot disagree with itself, and re-deriving
`find_support_face_z_mm`'s extent here is explicitly out of scope (#167).
A future ticket that wants the ray as an independent cross-check adds it
back at that call site rather than this one growing a second mechanism no
one asked to compare.

**Disambiguating which joined Floor is the TOP one** is this adapter's own
addition, not a measured rule: #161's host had exactly one joined Floor, so
"more than one candidate" was never observed. A Floor is accepted only if
the column's own top elevation falls inside that Floor's own vertical
extent (`Min.Z <= column_top <= Max.Z`, both from `get_BoundingBox(None)`)
-- which is what #161's numbers show (floor 2700..3000 mm, column top
3000 mm). No candidates -> R37's stated default (refuse, naming what was
looked for) and R39's architectural-Roof case. More than one -> refuse
rather than pick a favourite, matching the disagreement discipline the
ticket asks for even though a genuine second candidate has never been
measured.

## Thickness -- R37

**`FLOOR_ATTR_THICKNESS_PARAM` only.** #161 measured it,
`STRUCTURAL_FLOOR_CORE_THICKNESS` and the type's compound structure all
agreeing at 300.0 mm; the ticket allows reading one, so no second source is
read here and there is nothing to disagree.

## Cover -- R38

**`CLEAR_COVER_OTHER` is read as *the* slab cover**, mirroring
`column_host.read_cover_mm`'s own choice for a column's vertical faces:
"Other Faces" is this codebase's established name for a side/edge cover, and
R42 explicitly reuses the SAME cover value R37/R38 read for the vertical
leg as the one it subtracts from the measured horizontal run --
"That floor's cover reads 0.0 (R38), so the two happen to coincide" is R42's
own words for there being exactly one number, not two. This is a stated
adapter decision, not a live measurement of which BuiltInParameter is
canonical: #161's transcript printed `CLEAR_COVER_TOP`, `CLEAR_COVER_BOTTOM`
and `CLEAR_COVER_OTHER` side by side, all reading zero, without singling one
out.

Per R38: a cover type that resolves and reads a NON-zero distance is READ
and returned as such; a cover parameter that is unset, or set but reading
exactly zero, opens the typed field -- and an empty typed field is a
refusal, never a default.

## The run -- R41, R42

The floor's top face, `GetEdgesAsCurveLoops()`, and the nearest crossing of
a 20 m probe line fired from the column's own face, along the column's own
`Hand`/`Facing` -- never world X/Y (#103). `rft.core.column_roof_run` does
the pure 2D ray/segment math; this module only extracts the segments and
the probe origin/direction. The result is **subtracted by the slab's own
cover** (R42) before it becomes an `available_run_mm` -- R42's own
transcript numbers are to the boundary, and this module does not inherit
the accidental coincidence that this floor's cover happens to read zero.

`has_slab` is an INPUT here (`free_edge_names`), not a derivation: §3's
pick-the-exception is a later ticket, so every direction defaults to
`has_slab=True` with its MEASURED run, and only a name the caller passes in
`free_edge_names` switches a direction to the free-edge cap
(`rft.core.column_roof.free_edge_run_mm`) instead.

**A flagged free edge's own cap width is this adapter's own mapping, not a
measured or ruled one:** `+Hand`/`-Hand` use the column's own extent along
Hand (`section.b_mm`, per `column_host`'s docstring: "b lies along
HandOrientation"), `+Facing`/`-Facing` use `section.h_mm`. Spec §2 states
only "column width at that face"; no verification transcript or amendment
names which of the column's two dimensions that is for each face, and this
mapping is worth an owner's confirmation before it is trusted with a real
free edge.

SHAPE UNVERIFIED (see also `tests/fake_revit_api.py`'s header):
- `JoinGeometryUtils.GetJoinedElements(document, element)` and
  `JoinGeometryUtils.IsCuttingElementInJoin(element, element)` -- #161
  measured the OUTPUT (Floor 424637, `IsCuttingElementInJoin` False) but no
  transcript records the exact call signature used to get there. Assumed
  to be the standard two-argument static methods.
- `HostObjectUtils.GetTopFaces(floor) -> IList<Reference>` -- #161/#170
  describe reading "the floor's top `PlanarFace`" but neither transcript
  names the API call that produced it. This is the documented, idiomatic
  way to get a host object's top face and is used here instead of
  re-deriving it from raw solid geometry, which would stack a second guess
  (whether `Floor.get_Geometry()` wraps its solids the way a
  `FamilyInstance`'s does, which `column_host.py` already flags as
  unverified for a column) on top of this one.
- `Face.GetEdgesAsCurveLoops() -> IList<CurveLoop>` and iterating a
  `CurveLoop` as `IEnumerable<Curve>` -- named in both R42 and its
  verification note, never reflected or enumerated live in this repo.
- `Floor.get_Parameter` returning `FLOOR_ATTR_THICKNESS_PARAM` and
  `CLEAR_COVER_OTHER` the same way `FamilyInstance.get_Parameter` does --
  #161 confirms the VALUES, not that a `Floor` is queried through the same
  `get_Parameter`/`AsElementId`/`RebarCoverType` chain `column_host.py`
  already relies on for a column.
"""

from Autodesk.Revit import DB

from ..core.column_roof import RoofBendDirection, free_edge_run_mm
from ..core.column_roof_run import nearest_crossing_mm
from .column_host import read_orientation, read_section_mm
from .units import internal_to_mm

#: R42's own four names, in a fixed order so a caller can rely on it.
BEND_DIRECTION_NAMES = ("+Hand", "-Hand", "+Facing", "-Facing")

#: R42's probe: "a 20 m probe line from the column's own face".
PROBE_LENGTH_MM = 20000.0

#: How far past the boundary a crossing is trusted to mean "no edge found
#: within the probe" rather than "the slab runs out here". Anything at or
#: beyond this is treated as a deep-interior direction with no limit worth
#: naming (R41's third case): "the run exceeds what L_D needs".
_NO_EDGE_FOUND_RUN_MM = PROBE_LENGTH_MM


class ColumnRoofSlabError(Exception):
    """A top-floor slab read this module will not detail, with the reason
    the caller reads. Raised rather than returned so a half-populated read
    can never reach `rft.core.column_roof` (the beam tool's own #65
    failure mode)."""


def _require(condition, message):
    if not condition:
        raise ColumnRoofSlabError(message)


def find_top_floor(doc, column):
    """The single `Floor` this column's top bears into, or a refusal.

    R37's stated default and R39's architectural-Roof case both refuse
    here, by the SAME path: no candidate Floor sits above this column.
    """
    joined_ids = DB.JoinGeometryUtils.GetJoinedElements(doc, column)
    column_top_z = column.get_BoundingBox(None).Max.Z

    candidates = []
    for element_id in joined_ids:
        element = doc.GetElement(element_id)
        if not isinstance(element, DB.Floor):
            continue
        box = element.get_BoundingBox(None)
        if box is None:
            continue
        if box.Min.Z <= column_top_z <= box.Max.Z:
            candidates.append(element)

    _require(
        candidates,
        "No Floor is joined to the top of this column, so there is no "
        "top-floor slab to bend the longitudinal bars into (R37). Under "
        "R39 this is also what a column under an architectural Revit Roof "
        "reads as, and that refusal is correct: the tool details "
        "structural slabs, not roofs.")
    _require(
        len(candidates) == 1,
        "This column's top is joined to %d Floors, and the top-floor slab "
        "is ambiguous. The tool will not pick a favourite." %
        len(candidates))
    return candidates[0]


def read_slab_thickness_mm(floor):
    """R37: `FLOOR_ATTR_THICKNESS_PARAM`, the one source #161 measured."""
    parameter = floor.get_Parameter(DB.BuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM)
    _require(
        parameter is not None,
        "This Floor has no thickness parameter, so the vertical leg's "
        "length cannot be established (R37).")
    return internal_to_mm(parameter.AsDouble())


def read_slab_cover_mm(floor, typed_cover_mm=None):
    """R38: the slab's cover, read from `CLEAR_COVER_OTHER` -- and, only
    when that reads zero (nothing set), the typed value.

    Returns ``(cover_mm, provenance)`` where ``provenance`` is ``"read"``
    or ``"typed"``, so a caller building §4's report can name which one it
    was without recomputing anything.
    """
    parameter = floor.get_Parameter(DB.BuiltInParameter.CLEAR_COVER_OTHER)
    read_mm = 0.0
    if parameter is not None:
        cover_type = floor.Document.GetElement(parameter.AsElementId())
        if cover_type is not None:
            read_mm = internal_to_mm(cover_type.CoverDistance)

    if read_mm != 0.0:
        return read_mm, "read"

    _require(
        typed_cover_mm is not None,
        "This Floor's cover reads zero, which R38 treats as nobody having "
        "set one. Cover is read from the model and never typed EXCEPT in "
        "this one case, and there is no default to fall back on -- type a "
        "cover for this slab.")
    return typed_cover_mm, "typed"


def _floor_top_face_segments_mm(floor):
    """Every edge of the floor's top face, as flat `(p0, p1)` mm tuples.

    `HostObjectUtils.GetTopFaces` and `GetEdgesAsCurveLoops` are both
    SHAPE UNVERIFIED -- see the module header.
    """
    references = DB.HostObjectUtils.GetTopFaces(floor)
    _require(references, "This Floor has no top face to measure the slab's "
                         "run from.")
    face = floor.GetGeometryObjectFromReference(references[0])
    segments = []
    for loop in face.GetEdgesAsCurveLoops():
        for curve in loop:
            p0 = curve.GetEndPoint(0)
            p1 = curve.GetEndPoint(1)
            segments.append(((internal_to_mm(p0.X), internal_to_mm(p0.Y)),
                             (internal_to_mm(p1.X), internal_to_mm(p1.Y))))
    return segments


def _measured_run_mm(origin_mm, axis_xy, segments_mm, cover_mm):
    """R42: the nearest crossing along `axis_xy` from `origin_mm`, less the
    slab's own cover -- or, if nothing crosses within the probe length, a
    run generous enough that no realistic `L_D` is limited by it (R41's
    deep-interior case)."""
    crossing_mm = nearest_crossing_mm(origin_mm, axis_xy, segments_mm)
    if crossing_mm is None or crossing_mm > _NO_EDGE_FOUND_RUN_MM:
        crossing_mm = _NO_EDGE_FOUND_RUN_MM
    return crossing_mm - cover_mm


def read_bend_directions(doc, floor, column, cover_mm, free_edge_names=()):
    """One :class:`RoofBendDirection` per `BEND_DIRECTION_NAMES`, for
    `rft.core.column_roof.terminate_bar` (R41, R42).

    `free_edge_names` is the input §3's picking UI will eventually supply
    (defaulting to none flagged, per #167): a name in it gets the free-edge
    cap (`free_edge_run_mm`) instead of the measured boundary run, and its
    `has_slab` reports False so a later report can say WHY the run was
    short.
    """
    section = read_section_mm(column)
    hand, facing = read_orientation(column)
    point = column.Location.Point
    origin_mm = (internal_to_mm(point.X), internal_to_mm(point.Y))
    segments_mm = _floor_top_face_segments_mm(floor)

    axes = {
        "+Hand": ((hand[0], hand[1]), section.b_mm),
        "-Hand": ((-hand[0], -hand[1]), section.b_mm),
        "+Facing": ((facing[0], facing[1]), section.h_mm),
        "-Facing": ((-facing[0], -facing[1]), section.h_mm),
    }

    flagged = frozenset(free_edge_names)
    directions = []
    for name in BEND_DIRECTION_NAMES:
        axis_xy, column_width_mm = axes[name]
        if name in flagged:
            run_mm = free_edge_run_mm(column_width_mm, cover_mm)
            has_slab = False
        else:
            half_extent = 0.5 * column_width_mm
            face_origin_mm = (origin_mm[0] + axis_xy[0] * half_extent,
                              origin_mm[1] + axis_xy[1] * half_extent)
            run_mm = _measured_run_mm(face_origin_mm, axis_xy, segments_mm,
                                      cover_mm)
            has_slab = True
        directions.append(
            RoofBendDirection(name=name, has_slab=has_slab,
                              available_run_mm=run_mm))
    return tuple(directions)


def read_top_floor_slab(doc, column, typed_cover_mm=None,
                        free_edge_names=()):
    """Everything `rft.core.column_roof` needs about the slab above this
    column, or a :class:`ColumnRoofSlabError` naming why there is none.

    Returns a dict: ``floor``, ``thickness_mm``, ``cover_mm``,
    ``cover_provenance`` (``"read"`` or ``"typed"``, R38) and ``directions``
    (four `RoofBendDirection`, R41/R42).
    """
    floor = find_top_floor(doc, column)
    thickness_mm = read_slab_thickness_mm(floor)
    cover_mm, provenance = read_slab_cover_mm(floor, typed_cover_mm)
    directions = read_bend_directions(doc, floor, column, cover_mm,
                                      free_edge_names)
    return {
        "floor": floor,
        "thickness_mm": thickness_mm,
        "cover_mm": cover_mm,
        "cover_provenance": provenance,
        "directions": directions,
    }
