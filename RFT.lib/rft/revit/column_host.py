# -*- coding: utf-8 -*-
"""Issue #87 — reading a column out of the model.

THE ADAPTER. Everything here touches Revit and decides nothing:
measurements come out as plain millimetres and plain tuples, and
``rft.core.column_host_rules`` rules on them. That split is
`REUSE_GUIDELINES.md`'s, and it is why the refusals are unit-tested rather
than discovered on a host.

Verified live on **Revit 2024** build 24.3.40.26 — see
`docs/column/verification/issue-87-column-read-and-refusals.md` and
`issue-69-column-tracer-bullet.md`. Two findings shape this module and
neither is in any documentation:

1. A `UC305x305x97` I-section's twelve vertical faces carry **the same four
   normal directions** as a rectangle's four, so the rectangularity test
   must count faces, not just look at directions.
2. `ReferenceIntersector` answers **per view**, and the wrong answer is
   silence. In the test document `{3D}` finds the floor soffit at 2700 mm
   and `Analytical Model` finds nothing — with identical
   `GetCategoryHidden`, `ViewTemplateId` and `IsSectionBoxActive`. So the
   view is chosen by **behaviour**: it must be able to see the host column
   itself.

STILL UNVERIFIED (`SHAPE UNVERIFIED` discipline):
- `b` / `h` are the parameter names of the Autodesk metric
  `M_Concrete-Rectangular-Column` family. Any other family names them
  differently, so this module **refuses** rather than guesses.
- `Mirrored` / `HandFlipped` / `FacingFlipped` were all ``False`` on every
  column probed. Their effect on the b->Hand, h->Facing mapping is
  untested, so a flipped column is refused rather than detailed wrongly.
- Circular and L-shaped columns were never placed; the count rule should
  catch them, which is not the same as having seen it.
"""

# ``ElementMulticategoryFilter`` takes an ICollection<BuiltInCategory>;
# a Python list is not one, and the constructor overload resolution
# fails with a TypeError that names no argument. This is the same
# .NET-generic import pyRevit's own scripts use.
from System.Collections.Generic import List

from Autodesk.Revit import DB

from ..core.column_host_rules import (
    extent_from_ends,
    multi_storey_refusal,
    rectangular_section_refusal,
    section_from_dimensions,
)
from .bar_types import element_name
from .units import internal_to_mm

#: The parameter names the supported family uses for its section. Named
#: here, once, so the refusal can quote them.
SECTION_PARAM_B = "b"
SECTION_PARAM_H = "h"

#: What may support a column at either end. Order is irrelevant --
#: ``ReferenceIntersector`` returns the nearest hit, not the first
#: category.
SUPPORT_CATEGORIES = (
    DB.BuiltInCategory.OST_Floors,
    DB.BuiltInCategory.OST_StructuralFraming,
    DB.BuiltInCategory.OST_StructuralFoundation,
    DB.BuiltInCategory.OST_Walls,
)

#: How far outside the column's own solid a ray starts. #69: an origin
#: INSIDE the target returns zero hits, so "cast from the column's top" is
#: the wrong instinct -- cast from safely below the expected face, upward.
RAY_CLEARANCE_INTERNAL = 1.0  # feet, Revit internal units


def vertical_extent_internal(element):
    """``(min_z, max_z)`` of the column's own solid, in internal units.

    **Every ray in this module starts from a height derived here, never
    from ``Location.Point.Z``.** A structural column's ``Location.Point``
    reports ``Z = 0`` no matter which storey it stands on -- measured live
    on four columns, two of them spanning 3000-6000 mm and both reporting
    ``Location.Point.Z == 0``.

    That is not a quirk worth working around cleverly; it is simply a
    different quantity. The insertion point carries the column's plan
    position and its base LEVEL's origin, not its elevation.

    Using it as a ray height made every search fire at roughly 1200 mm
    above the project base regardless of the column picked, which is why
    an upper-storey column was told "no 3D view can see" it (the self-test
    ray passed underneath it and hit the column below) and why the support
    search returned the GROUND floor's soffit, 2700 mm, for a column whose
    real top support is at 5700 mm. The second failure is the dangerous
    one: it is a plausible number, not an error.

    Raises rather than guessing when there is no bounding box: a column
    with no geometry is not something to detail against.
    """
    box = element.get_BoundingBox(None)
    _require(box is not None,
             "This column has no bounding box, so the height at which to "
             "search for its supports cannot be established.")
    return box.Min.Z, box.Max.Z


def _inset_internal(min_z, max_z):
    """How far inside each end of the column a vertical ray starts.

    Normally the full clearance. On a column shorter than four clearances
    the two origins would cross and the upward ray would start below the
    downward one, so it is scaled to a quarter of the span instead --
    short columns are unusual, silently inverted rays are not detectable.
    """
    span = max_z - min_z
    return min(RAY_CLEARANCE_INTERNAL, span / 4.0)


class ColumnHostError(Exception):
    """A column this tool will not detail, with the reason the user reads.

    Raised rather than returned so that no caller can carry on past a
    refusal with a half-populated read, which is the failure mode the beam
    tool's #65 was.
    """


def _require(condition, message):
    if not condition:
        raise ColumnHostError(message)


def largest_solid(element):
    """The element's biggest solid, looking inside a ``GeometryInstance``.

    A family instance's geometry arrives wrapped, and the wrapper holds no
    faces of its own. Empty solids (volume 0) are the join leftovers Revit
    returns alongside the real one.
    """
    options = DB.Options()
    options.ComputeReferences = True
    options.DetailLevel = DB.ViewDetailLevel.Fine

    best = None
    for geometry_object in element.get_Geometry(options):
        instance = None
        if isinstance(geometry_object, DB.GeometryInstance):
            instance = geometry_object.GetInstanceGeometry()
        candidates = instance if instance is not None else [geometry_object]
        for candidate in candidates:
            if not isinstance(candidate, DB.Solid):
                continue
            if candidate.Volume <= 1.0e-9:
                continue
            if best is None or candidate.Volume > best.Volume:
                best = candidate
    _require(best is not None,
             "This column has no solid geometry to measure. It cannot be "
             "detailed without one.")
    return best


def face_normals(solid):
    """``(planar normals as (x, y, z) tuples, curved face count)``.

    Tuples, not ``XYZ``: the rule that consumes them is pure Python and
    must stay importable without Revit.
    """
    normals = []
    curved = 0
    for face in solid.Faces:
        if not isinstance(face, DB.PlanarFace):
            curved += 1
            continue
        normal = face.FaceNormal
        normals.append((normal.X, normal.Y, normal.Z))
    return normals, curved


def read_section_mm(element):
    """`b` and `h` from the TYPE parameters, in the roles §2 gives them.

    Never from the bounding box: #69 measured 712.8 x 749.6 for a
    450 x 600 column rotated 35 degrees, a 58% error on the face that
    governs S0.
    """
    symbol = element.Symbol
    values = {}
    for name in (SECTION_PARAM_B, SECTION_PARAM_H):
        parameter = symbol.LookupParameter(name)
        _require(
            parameter is not None,
            "This column's family (%s) has no '%s' parameter, so its "
            "section cannot be read. The tool reads 'b' and 'h' from the "
            "type, as the Autodesk metric rectangular column family names "
            "them; a family that names them differently is not supported."
            % (symbol.Family.Name, name))
        values[name] = internal_to_mm(parameter.AsDouble())
    return section_from_dimensions(values[SECTION_PARAM_B],
                                   values[SECTION_PARAM_H])


def read_orientation(element):
    """``(hand, facing)`` as ``(x, y, z)`` tuples, refusing a flipped column.

    #69 proved `b` lies along ``HandOrientation`` and `h` along
    ``FacingOrientation``, both invariant under rotation. Every column
    probed had all three flip flags ``False``, so what a flip does to that
    mapping is **unknown** — and a mapping that is silently inverted swaps
    which dimension governs L0 and which governs S0.
    """
    flipped = []
    if element.Mirrored:
        flipped.append("mirrored")
    if element.HandFlipped:
        flipped.append("hand-flipped")
    if element.FacingFlipped:
        flipped.append("facing-flipped")
    _require(
        not flipped,
        "This column is %s. The tool reads b along HandOrientation and h "
        "along FacingOrientation, and what a flip does to that mapping has "
        "never been verified on a host -- reading it wrong would silently "
        "swap which dimension governs L0 and which governs S0. Refusing "
        "rather than guessing." % " and ".join(flipped))
    hand = element.HandOrientation
    facing = element.FacingOrientation
    return ((hand.X, hand.Y, hand.Z), (facing.X, facing.Y, facing.Z))


def read_cover_mm(element):
    """Cover for the four vertical faces, READ from the element (A2, #83).

    ``CLEAR_COVER_OTHER`` is "Other Faces", which governs the four vertical
    faces every tie and perimeter bar is measured from. It is never typed
    and never defaults to 25: A2 settled that after #80 found Revit
    silently clamping a tie to the host's own cover, so a user's 25 became
    40 in the model while the report still said 25.

    **Q5 is unresolved and this is where it surfaces.** The test column's
    ``Rebar Cover - Top Face`` is unset (``ElementId -1``). This function
    reads only "Other Faces", which IS set — but a caller that ever needs
    the top face must not assume it is populated, and what to do when it is
    not is an owner ruling, not an implementer's choice.
    """
    parameter = element.get_Parameter(DB.BuiltInParameter.CLEAR_COVER_OTHER)
    _require(parameter is not None,
             "This column has no 'Rebar Cover - Other Faces' parameter, so "
             "the cover the ties are measured from cannot be read.")
    cover_type = element.Document.GetElement(parameter.AsElementId())
    _require(
        cover_type is not None,
        "This column's 'Rebar Cover - Other Faces' is not set. Cover is "
        "read from the element and never typed (amendment A2), so there is "
        "nothing to detail against. Set a cover on the column and pick it "
        "again.")
    return internal_to_mm(cover_type.CoverDistance), element_name(cover_type)


def read_top_face_cover_is_set(element):
    """Whether ``Rebar Cover - Top Face`` is populated (the Q5 probe).

    Separated from :func:`read_cover_mm` so the window can SAY the top face
    is unset without that fact changing what it details against. Q5 decides
    what happens next; until it is answered, nothing acts on this.
    """
    parameter = element.get_Parameter(DB.BuiltInParameter.CLEAR_COVER_TOP)
    if parameter is None:
        return False
    return element.Document.GetElement(parameter.AsElementId()) is not None


def read_levels_mm(doc):
    """Every level as ``(name, elevation_mm)``, low to high."""
    collector = DB.FilteredElementCollector(doc).OfClass(DB.Level)
    levels = [(level.Name, internal_to_mm(level.Elevation))
              for level in collector]
    levels.sort(key=lambda pair: pair[1])
    return levels


def _level_elevation_mm(doc, element, built_in_parameter, label):
    parameter = element.get_Parameter(built_in_parameter)
    _require(parameter is not None,
             "This column has no %s parameter." % label)
    level = doc.GetElement(parameter.AsElementId())
    _require(level is not None,
             "This column's %s is not set, so its extent cannot be "
             "established." % label)
    return level.Name, internal_to_mm(level.Elevation)


def read_base_and_top_levels(doc, element):
    """``((base name, base z), (top name, top z))`` in millimetres.

    Offsets are added: a column constrained to Level 1 with a 150 mm base
    offset starts at 150, and detailing from the level would place the
    first tie 150 mm out.
    """
    base = _level_elevation_mm(doc, element,
                               DB.BuiltInParameter.FAMILY_BASE_LEVEL_PARAM,
                               "base level")
    top = _level_elevation_mm(doc, element,
                              DB.BuiltInParameter.FAMILY_TOP_LEVEL_PARAM,
                              "top level")
    base_offset = element.get_Parameter(
        DB.BuiltInParameter.FAMILY_BASE_LEVEL_OFFSET_PARAM)
    top_offset = element.get_Parameter(
        DB.BuiltInParameter.FAMILY_TOP_LEVEL_OFFSET_PARAM)
    base_z = base[1] + (0.0 if base_offset is None
                        else internal_to_mm(base_offset.AsDouble()))
    top_z = top[1] + (0.0 if top_offset is None
                      else internal_to_mm(top_offset.AsDouble()))
    return (base[0], base_z), (top[0], top_z)


def find_search_view(doc, element):
    """A ``View3D`` whose ``ReferenceIntersector`` can actually see things.

    **Chosen by behaviour, never by name or by settings.** In the test
    document `{3D}` finds the floor soffit and `Analytical Model` finds
    nothing, while `GetCategoryHidden` for all four support categories,
    `ViewTemplateId` and `IsSectionBoxActive` are identical on both. There
    is no property to inspect.

    So each candidate is made to prove itself: fire a horizontal ray at the
    column being detailed, from outside it. The column is known to be
    there. A view that cannot see it cannot be trusted to report that
    nothing is above it — and "nothing above it" is a *legitimate* answer
    (R5/R6), which is exactly why an untrustworthy silence is dangerous.

    Refuses rather than falling back. At this point a level elevation would
    be a guess wearing a number's clothes.
    """
    point = element.Location.Point
    min_z, max_z = vertical_extent_internal(element)
    probe_z = 0.5 * (min_z + max_z)
    element_id = element.Id
    views = [view for view
             in DB.FilteredElementCollector(doc).OfClass(DB.View3D)
             if not view.IsTemplate]
    _require(views,
             "This project has no non-template 3D view. The support search "
             "casts rays through one, so the column's clear height cannot "
             "be established without it. Create a 3D view and try again.")

    tried = []
    for view in views:
        intersector = DB.ReferenceIntersector(
            DB.ElementCategoryFilter(DB.BuiltInCategory.OST_StructuralColumns),
            DB.FindReferenceTarget.Element, view)
        intersector.FindReferencesInRevitLinks = False
        # Mid-height of THIS column, so the ray meets it wherever it
        # stands. The X offset clears the widest plausible section; the
        # height is the half that used to be wrong.
        origin = DB.XYZ(point.X - 6.0 * RAY_CLEARANCE_INTERNAL,
                        point.Y,
                        probe_z)
        hits = intersector.Find(origin, DB.XYZ.BasisX)
        for hit in hits:
            if hit.GetReference().ElementId == element_id:
                return view
        tried.append(view.Name)
    raise ColumnHostError(
        "No 3D view in this project can see the selected column, so the "
        "support search above and below it would report 'nothing found' "
        "whether or not anything is there. Tried: %s. A plain {3D} view "
        "works; an analytical-model view does not." % ", ".join(tried))


def find_support_face_z_mm(doc, view, element, upward):
    """The elevation of the nearest support face above or below the column,
    or ``None``.

    ``None`` is a NORMAL outcome, not a failure: #69 found nothing below
    the test column, which is case C1 — a ground-floor column with no base
    support element. A search that assumes a face exists at both ends
    throws on the very first ground-floor column.

    The ray starts clear of the column's own solid and travels toward the
    expected face. #69: an origin *inside* the target returns zero hits,
    and the direction selects which face of a slab is reported — upward
    from below yields the soffit (2700), downward from above yields the top
    (3000). §3 measures from the support face, so upward-to-the-soffit is
    what the caller wants at the top end.
    """
    categories = List[DB.BuiltInCategory]()
    for category in SUPPORT_CATEGORIES:
        categories.Add(category)
    intersector = DB.ReferenceIntersector(
        DB.ElementMulticategoryFilter(categories),
        DB.FindReferenceTarget.Element, view)
    intersector.FindReferencesInRevitLinks = False

    point = element.Location.Point
    min_z, max_z = vertical_extent_internal(element)
    inset = _inset_internal(min_z, max_z)
    if upward:
        # Just inside the column's own top, firing up: the first face met
        # is the soffit of whatever supports it, which is what section 3
        # measures to.
        origin = DB.XYZ(point.X, point.Y, max_z - inset)
        direction = DB.XYZ.BasisZ
    else:
        origin = DB.XYZ(point.X, point.Y, min_z + inset)
        direction = -DB.XYZ.BasisZ
    nearest = intersector.FindNearest(origin, direction)
    if nearest is None:
        return None
    return internal_to_mm(nearest.GetReference().GlobalPoint.Z)


def read_column(doc, element):
    """Everything the window shows, or a :class:`ColumnHostError` saying
    why this column is out of scope.

    Order matters and is the beam tool's (rev 2 §10, applied to columns):
    **refuse first, read second.** A refusal discovered after half the
    read-outs are populated is a window showing numbers for a column it is
    about to decline.
    """
    _require(isinstance(element, DB.FamilyInstance),
             "Select a structural column. That selection is a %s."
             % type(element).__name__)
    host_data = DB.Structure.RebarHostData.GetRebarHostData(element)
    _require(host_data is not None and host_data.IsValidHost(),
             "Revit does not accept this element as a rebar host, so no "
             "reinforcement can be placed in it.")

    solid = largest_solid(element)
    normals, curved = face_normals(solid)
    refusal = rectangular_section_refusal(normals, curved)
    if refusal:
        raise ColumnHostError(refusal)

    base_level, top_level = read_base_and_top_levels(doc, element)
    refusal = multi_storey_refusal(base_level[1], top_level[1],
                                   read_levels_mm(doc))
    if refusal:
        raise ColumnHostError(refusal)

    section = read_section_mm(element)
    hand, facing = read_orientation(element)
    cover_mm, cover_name = read_cover_mm(element)

    view = find_search_view(doc, element)
    base_face_z = find_support_face_z_mm(doc, view, element, upward=False)
    top_face_z = find_support_face_z_mm(doc, view, element, upward=True)
    extent = extent_from_ends(base_face_z, top_face_z,
                              base_level[1], top_level[1])

    return {
        "element_id": element.Id.IntegerValue,
        "type_name": element_name(element.Symbol),
        "family_name": element.Symbol.Family.Name,
        "section": section,
        "hand": hand,
        "facing": facing,
        "cover_mm": cover_mm,
        "cover_type_name": cover_name,
        "top_face_cover_is_set": read_top_face_cover_is_set(element),
        "base_level": base_level,
        "top_level": top_level,
        "extent": extent,
        "search_view_name": view.Name,
    }
