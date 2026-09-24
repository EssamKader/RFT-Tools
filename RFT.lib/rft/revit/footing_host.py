# -*- coding: utf-8 -*-
"""Issue #220 -- auto-detecting the column above a picked footing.

Spec Ref: specs/isolated-footing-dowel-array.md Sec 1 ("Reused
Components"), Sec 3 Story 1. Ruling Ref: docs/footing/spec-amendments.md
R7 ("column is auto-detected, not picked").

THE TECHNIQUE, not the function, is reused from
``rft.revit.column_host`` -- that module's ``find_search_view`` /
``find_support_face_z_mm`` already prove a ``ReferenceIntersector``
ray-cast, filtered by category, through a ``View3D`` chosen by "can it
actually see the target" (never by name/settings), for a column casting a
ray at what supports it above/below. This module runs the SAME mechanism
in the OPPOSITE direction -- a known FOOTING casting a ray upward to find
an UNKNOWN column -- which is new code (this direction has never been
exercised on a live host), per the addendum's own Sec 1 wording.

**Design decision made WITHOUT live-host access (Zero API Guessing, this
agent's own instructions) -- flag for the orchestrator's own tracer
bullet before merge:**

``column_host.find_search_view`` self-tests a candidate view by firing a
ray, filtered to the SAME category it will search with later
(``OST_StructuralColumns``), at the element already known to exist (the
column itself). Story 1 has no column yet -- that is the very thing being
searched for -- so there is no known column to self-test against. The
element that IS known to exist here is the FOOTING itself, so this module
mirrors the self-test onto it: fire a ray filtered to
``OST_StructuralFoundation`` at the footing, and trust a view that can see
it to also see ``OST_StructuralColumns`` above it.

This is not a new kind of assumption -- ``column_host`` already carries
the same shape of trust (the view chosen by a ``OST_StructuralColumns``
self-test is then reused, unquestioned, for a SEPARATE
``ElementMulticategoryFilter`` over floors/framing/walls in
``find_support_face_z_mm``) -- but the SPECIFIC claim "a view that sees
foundations also sees columns" has never been measured, live, the way
#69/#107 measured the column/support case. This is exactly what the
addendum's Sec 5 calls out as Story 1's own required tracer bullet
(read-only, rolled back).
"""

from Autodesk.Revit import DB

#: Mirrors column_host.RAY_CLEARANCE_INTERNAL -- how far outside the
#: footing's own solid the self-test ray starts, and the scale used to
#: keep the upward search ray's origin inside the footing (never inside
#: the column it is trying to find -- see #69's "origin INSIDE the
#: target returns zero hits" finding, quoted in column_host.py).
RAY_CLEARANCE_INTERNAL = 1.0  # feet, Revit internal units


class FootingHostError(Exception):
    """A footing for which no column could be auto-detected, or a reason
    the search could not run at all. Raised, never returned, so no caller
    can carry on past a refusal with a half-populated read -- the same
    discipline column_host.ColumnHostError follows (see that module's own
    docstring).
    """


def _require(condition, message):
    if not condition:
        raise FootingHostError(message)


def footing_bounding_box_internal(footing):
    """The footing's own bounding box, in internal units.

    Every ray in this module is positioned from this, never from
    ``Location.Point`` -- mirrors column_host.vertical_extent_internal's
    own reasoning, and a footing family instance has no more guarantee
    that its insertion point reports a useful elevation than a column's
    does (#69/#107).
    """
    box = footing.get_BoundingBox(None)
    _require(box is not None,
             "This footing has no bounding box, so the ray used to find "
             "the column above it cannot be positioned.")
    return box


def _plan_centre(box):
    return (box.Min.X + box.Max.X) / 2.0, (box.Min.Y + box.Max.Y) / 2.0


def _inset_internal(min_z, max_z):
    """How far inside the footing's own top face the upward ray starts.

    Mirrors column_host._inset_internal: normally the full clearance, but
    scaled down on a footing shallower than four clearances so the origin
    cannot cross below the footing's own bottom face.
    """
    span = max_z - min_z
    return min(RAY_CLEARANCE_INTERNAL, span / 4.0)


def find_search_view(doc, footing):
    """A ``View3D`` whose ``ReferenceIntersector`` can actually see the
    footing -- and, by the assumption this module's own docstring flags,
    trusted to also see the column above it.

    **Chosen by behaviour, never by name or by settings** -- same rule
    column_host.find_search_view states and the same reason: #69/#107
    found two views with identical ``GetCategoryHidden``,
    ``ViewTemplateId`` and ``IsSectionBoxActive`` disagree on what they can
    see, so there is no property to inspect. Refuses rather than falling
    back, for the same reason column_host does: a guessed elevation here
    would be a plausible number, not a finding.
    """
    box = footing_bounding_box_internal(footing)
    centre_x, centre_y = _plan_centre(box)
    probe_z = 0.5 * (box.Min.Z + box.Max.Z)
    element_id = footing.Id

    views = [view for view
             in DB.FilteredElementCollector(doc).OfClass(DB.View3D)
             if not view.IsTemplate]
    _require(views,
             "This project has no non-template 3D view. The column search "
             "casts a ray through one, so the column above this footing "
             "cannot be found without it. Create a 3D view and try again.")

    tried = []
    for view in views:
        intersector = DB.ReferenceIntersector(
            DB.ElementCategoryFilter(
                DB.BuiltInCategory.OST_StructuralFoundation),
            DB.FindReferenceTarget.Element, view)
        intersector.FindReferencesInRevitLinks = False
        # Mid-height of THIS footing, offset clear of its own solid along
        # X -- mirrors column_host.find_search_view's own self-test ray
        # exactly, with the footing standing in for the column.
        origin = DB.XYZ(centre_x - 6.0 * RAY_CLEARANCE_INTERNAL,
                        centre_y, probe_z)
        hits = intersector.Find(origin, DB.XYZ.BasisX)
        for hit in hits:
            if hit.GetReference().ElementId == element_id:
                return view
        tried.append(view.Name)
    raise FootingHostError(
        "No 3D view in this project can see the selected footing, so the "
        "search for the column above it would report 'nothing found' "
        "whether or not anything is there. Tried: %s. A plain {3D} view "
        "works; an analytical-model view does not." % ", ".join(tried))


def find_column_above(doc, footing):
    """The single ``OST_StructuralColumns`` element above ``footing``.

    Spec Ref: specs/isolated-footing-dowel-array.md Sec 3 Story 1.

    Fires one ray upward from the footing's own top-face centroid,
    filtered to ``OST_StructuralColumns``, through a view
    ``find_search_view`` has already proven can see the footing itself.

    - Exactly one hit -> returns that ``FamilyInstance``.
    - No hit -> refuses with "No column is attached to this footing." --
      the exact message Story 1 names, with **no manual pick/typed
      fallback** (R7's own explicit ruling).
    - Multiple hits -> the nearest one wins, because
      ``ReferenceIntersector.FindNearest`` already returns only the
      nearest hit -- Story 1 states this is not special-cased, since an
      isolated footing has exactly one column per parent spec's own scope
      (Sec 0).
    - Section/orientation validity (rectangular, non-flipped) is
      deliberately NOT checked here -- Story 1's own text assigns that to
      whichever caller next runs ``column_host.read_section_mm`` /
      ``read_orientation`` against the element this function returns.
    """
    box = footing_bounding_box_internal(footing)
    centre_x, centre_y = _plan_centre(box)
    inset = _inset_internal(box.Min.Z, box.Max.Z)

    view = find_search_view(doc, footing)
    intersector = DB.ReferenceIntersector(
        DB.ElementCategoryFilter(DB.BuiltInCategory.OST_StructuralColumns),
        DB.FindReferenceTarget.Element, view)
    intersector.FindReferencesInRevitLinks = False

    # Just below the footing's own top face -- clear of the footing's own
    # solid boundary, and (per #69's "origin INSIDE the target returns
    # zero hits" finding) clear of the column above it too, since the
    # column sits ON TOP of the footing and never reaches down into it.
    origin = DB.XYZ(centre_x, centre_y, box.Max.Z - inset)
    nearest = intersector.FindNearest(origin, DB.XYZ.BasisZ)
    _require(nearest is not None, "No column is attached to this footing.")

    column = doc.GetElement(nearest.GetReference().ElementId)
    _require(column is not None, "No column is attached to this footing.")
    _require(isinstance(column, DB.FamilyInstance),
             "No column is attached to this footing.")
    return column
