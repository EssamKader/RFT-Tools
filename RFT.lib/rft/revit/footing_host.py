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
an UNKNOWN column -- which was new code the first time it was written
(this direction had never been exercised on a live host). Since PR #224
review, the shared ray-cast MECHANISM itself (the self-test-then-refuse
view search, the inset-from-a-known-extent math) lives in
``rft.revit.ray_search``, which this module calls -- see that module's
own docstring for why ``column_host.py`` was not also migrated onto it
(element isolation: a footing ticket does not edit a column-tool file).

**The self-test-category assumption -- confirmed live, residual risk
still open (PR #224 review, finding 1):**

``find_search_view`` below self-tests a candidate view with an
``OST_StructuralFoundation`` ray at the footing itself -- there is no
known column yet at that point, which is the very thing being searched
for -- then ``find_column_above`` reuses that SAME view, unquestioned, for
an ``OST_StructuralColumns`` upward ray. This transfer (a view proven to
see foundations also seeing columns) is now **live-verified**: see
``docs/footing/verification/issue-220-footing-column-autodetect.md``,
which reproduced this module's exact logic in C# against the live
``ColumnRFT.Trail.rvt`` document and found the ``{3D}`` view, self-tested
only against ``OST_StructuralFoundation``, correctly located the one real
column present, with the two footings genuinely lacking a column
correctly producing "no column found" (confirmed as true negatives by an
independent bounding-box check, not assumed from a null hit).

That measurement was taken on a project where neither category's
visibility had been overridden. **The residual risk it does NOT cover:**
a project where a view filter or V/G override hides
``OST_StructuralColumns`` specifically (while ``OST_StructuralFoundation``
stays visible) would still pass the foundation self-test, then the
upward ``OST_StructuralColumns`` ray would report nothing -- indistin-
guishable from the legitimate "no column above this footing" case. A
mitigation was considered (checking
``view.GetCategoryHidden(OST_StructuralColumns)`` before trusting the
view) and deliberately NOT added: ``column_host.find_search_view``'s own
docstring records that #69/#107 found ``GetCategoryHidden`` IDENTICAL
across two views that disagreed on ray-cast visibility, which is this
repo's own precedent that a property check does not reliably predict ray
behaviour -- adding one here would trade a real, ray-based finding for a
property read this project has already shown can be misleading. The
ray-based self-test is judged the right final word for the same reason
this repo already trusts it for the column/support direction; the
residual risk above is documented rather than silently mitigated with a
check this repo has reason to distrust.

**Pedestal/plinth disambiguation -- known limitation, not fixed here (PR
#224 review, finding 2):** ``find_column_above`` returns whichever
``OST_StructuralColumns`` element the nearest ray hit reports. A short
pedestal or plinth modelled as its own ``OST_StructuralColumns``
``FamilyInstance`` directly on the footing, below the real column, would
be nearer to the ray's origin and would be returned INSTEAD of the real
column above it -- there is no plinth/column disambiguation here. A
caller further down the chain (#221's ``column_host.read_section_mm`` /
``read_orientation``) would then read the pedestal's section, not the
real column's, with no refusal raised anywhere in between. Flagged rather
than silently guessed at; a full fix (e.g. requiring a second ray past
the first hit, or a plinth/column naming convention) is out of this
ticket's scope.
"""

from collections import namedtuple

from Autodesk.Revit import DB

from . import column_host
from ..core.footing_plan import DowelColumnSection
from .ray_search import (
    RAY_CLEARANCE_INTERNAL,
    RaySearchError,
    find_nearest_in_category,
    find_self_testing_view,
    inset_internal,
)
from .units import internal_to_mm


class FootingHostError(Exception):
    """A footing for which no column could be auto-detected, its own plan
    dimensions/thickness/cover could not be read (#228), or a reason a
    search could not run at all. Raised, never returned, so no caller can
    carry on past a refusal with a half-populated read -- the same
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


def find_search_view(doc, footing, box=None):
    """A ``View3D`` whose ``ReferenceIntersector`` can actually see the
    footing -- and, per this module's own docstring, live-confirmed (with
    a documented residual risk) to also see the column above it.

    ``box`` lets a caller that already computed the footing's bounding
    box (``find_column_above`` does) pass it straight through instead of
    this function re-fetching it -- PR #224 review, finding 6. Computed
    fresh from ``footing`` when omitted, so this remains independently
    callable (as the tests do).
    """
    if box is None:
        box = footing_bounding_box_internal(footing)
    centre_x, centre_y = _plan_centre(box)
    probe_z = 0.5 * (box.Min.Z + box.Max.Z)
    # Mid-height of THIS footing, offset clear of its own solid along X --
    # mirrors column_host.find_search_view's own self-test ray exactly,
    # with the footing standing in for the column.
    origin = DB.XYZ(centre_x - 6.0 * RAY_CLEARANCE_INTERNAL, centre_y,
                    probe_z)
    try:
        return find_self_testing_view(
            doc, DB.BuiltInCategory.OST_StructuralFoundation, origin,
            DB.XYZ.BasisX, footing.Id,
            no_view_message=(
                "This project has no non-template 3D view. The column "
                "search casts a ray through one, so the column above "
                "this footing cannot be found without it. Create a 3D "
                "view and try again."),
            all_blind_message=(
                "No 3D view in this project can see the selected "
                "footing, so the search for the column above it would "
                "report 'nothing found' whether or not anything is "
                "there. A plain {3D} view works; an analytical-model "
                "view does not."))
    except RaySearchError as error:
        raise FootingHostError(str(error))


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
      (Sec 0). See this module's own docstring for the pedestal/plinth
      case this does NOT disambiguate.
    - Section/orientation validity (rectangular, non-flipped) is
      deliberately NOT checked here -- Story 1's own text assigns that to
      whichever caller next runs ``column_host.read_section_mm`` /
      ``read_orientation`` against the element this function returns.
    """
    box = footing_bounding_box_internal(footing)
    centre_x, centre_y = _plan_centre(box)
    inset = inset_internal(box.Min.Z, box.Max.Z, RAY_CLEARANCE_INTERNAL)

    view = find_search_view(doc, footing, box=box)

    # Just below the footing's own top face -- clear of the footing's own
    # solid boundary, and (per #69's "origin INSIDE the target returns
    # zero hits" finding) clear of the column above it too, since the
    # column sits ON TOP of the footing and never reaches down into it.
    origin = DB.XYZ(centre_x, centre_y, box.Max.Z - inset)
    nearest = find_nearest_in_category(
        view, DB.BuiltInCategory.OST_StructuralColumns, origin,
        DB.XYZ.BasisZ)
    _require(nearest is not None, "No column is attached to this footing.")

    column = doc.GetElement(nearest.GetReference().ElementId)
    _require(isinstance(column, DB.FamilyInstance),
             "No column is attached to this footing.")
    return column


def read_dowel_column_section_mm(column):
    """The plain-number ``DowelColumnSection`` #221 wires into
    ``footing_plan.build_footing_plan`` -- ``find_column_above``'s own
    return, live-read.

    Spec Ref: specs/isolated-footing-dowel-array.md Sec 3 Story 2. Ruling
    Ref: docs/footing/spec-amendments.md R7 (incl. the same-day cover
    extension).

    Reuses ``column_host.read_section_mm``/``read_orientation``/
    ``read_cover_mm`` AS-IS -- no fork, no new refusal wording, since all
    three already carry correct messages from ColumnRFT (issue #87/#69).
    ``read_orientation`` runs for its refusal ONLY: a flipped column must
    stop this call before any rebar placement, but its ``(hand, facing)``
    vectors are not part of ``DowelColumnSection`` and are discarded once
    that check has passed -- `b` already lies along ``HandOrientation`` and
    `h` along ``FacingOrientation`` regardless (#69), so ``Cw_mm``/``Cd_mm``
    map straight onto ``section.b_mm``/``section.h_mm`` with no re-deriving.

    Any of the three refusals (non-rectangular section, flipped column,
    cover unset) propagates unchanged -- this function adds none of its
    own.
    """
    column_host.read_orientation(column)
    section = column_host.read_section_mm(column)
    cover_mm, _cover_name = column_host.read_cover_mm(column)
    return DowelColumnSection(
        Cw_mm=section.b_mm, Cd_mm=section.h_mm, Ccover_mm=cover_mm)


#: #228, spec Ref: docs/footing/spec-amendments.md R8. Bundled into one
#: namedtuple, keyword-constructed only, for the SAME reason #225/#227
#: bundled DowelColumnSection: six same-typed, same-unit mm floats at the
#: call site otherwise invite a silent swap (a/b, or bottom/top cover) that
#: type-checks fine and produces a silently wrong plan.
FootingGeometry = namedtuple(
    "FootingGeometry",
    ["a_mm", "b_mm", "footing_thickness_mm", "cover_mm",
     "bottom_cover_mm", "top_cover_mm"])


def _require_type_dimension_mm(symbol, built_in, label):
    parameter = symbol.get_Parameter(built_in)
    _require(
        parameter is not None,
        "This footing's family (%s) has no '%s' parameter, so its %s "
        "cannot be read. The tool reads plan dimensions and thickness "
        "from the type, as the Autodesk metric rectangular footing family "
        "names them; a family that names them differently is not "
        "supported." % (symbol.Family.Name, label, label))
    return internal_to_mm(parameter.AsDouble())


def _require_instance_cover_mm(footing, built_in, label):
    parameter = footing.get_Parameter(built_in)
    _require(parameter is not None,
             "This footing has no '%s' parameter, so the cover it "
             "governs cannot be read." % label)
    cover_type = footing.Document.GetElement(parameter.AsElementId())
    _require(
        cover_type is not None,
        "This footing's '%s' is not set. Cover is read from the element "
        "and never typed (amendment A2, R8), so there is nothing to "
        "detail against. Set a cover on the footing and pick it again."
        % label)
    return internal_to_mm(cover_type.CoverDistance)


def read_footing_geometry_mm(footing):
    """The footing's own plan dimensions, thickness and three covers,
    read live off the picked ``FamilyInstance`` -- R8's ruling ("read
    dimension from revit not from typed inputs"), and the batch-grouping
    prerequisite #226 needs (two footings that measure identically this
    way share identical detailing automatically, per R8's own "no worries
    for no.02 run").

    Spec Ref: docs/footing/spec-amendments.md R8.

    **Parameter names confirmed live** (2026-09-24, ``ColumnRFT.Trail.rvt``,
    footing family ``M_Footing-Rectangular``) -- see
    ``docs/footing/verification/issue-228-footing-dimension-read.md``:
    unlike ``column_host.read_section_mm``'s family-defined ``b``/``h``
    parameters, a Revit structural foundation carries FIXED
    ``BuiltInParameter``s for its own plan/thickness, read here instead of
    a name lookup (more robust than ``LookupParameter``, since a built-in
    ID does not depend on the UI language a family happens to be
    authored/renamed in):

    - ``STRUCTURAL_FOUNDATION_LENGTH`` / ``_WIDTH`` / ``_THICKNESS``, all
      TYPE (``Symbol``) parameters, never the bounding box -- the same
      "type, not bounding box" discipline ``column_host.read_section_mm``
      follows, for the same reason (#69: a bounding box degrades on
      anything but an axis-aligned footing; ``footing_mesh._footing_origin``
      already refuses a rotated footing rather than trust one).
    - ``CLEAR_COVER_OTHER`` / ``_BOTTOM`` / ``_TOP``, all INSTANCE
      parameters -- confirmed to exist independently of the TYPE cover
      convention ``column_host.read_cover_mm`` reads (a column has only
      ``CLEAR_COVER_OTHER``; a footing, being a horizontal element, also
      carries distinct bottom/top face covers).

    ``a_mm``/``b_mm`` map from ``Length``/``Width`` respectively --
    matching this family's own "1800 x 1200 x 450mm" type name and
    ``IsolatedFootingRFT.pushbutton/script.py``'s pre-existing default
    prompts (a=1800 X-direction, b=1200 Y-direction) exactly, though which
    of the family's own local axes ``Length``/``Width`` actually run along
    was NOT independently re-derived the way #69 proved column `b`/`h`
    against a rotated instance -- this ticket's own live probe confirms
    the PARAMETER NAMES and VALUES, not a rotation-independent axis proof.
    Flagged, not silently assumed: see the verification doc's own "Still
    open" note.

    Any of the six missing/unset refuses with ``FootingHostError``, naming
    the parameter, before any rebar placement -- same discipline every
    other live-read function in this module and ``column_host`` follows.
    """
    symbol = footing.Symbol
    a_mm = _require_type_dimension_mm(
        symbol, DB.BuiltInParameter.STRUCTURAL_FOUNDATION_LENGTH, "Length")
    b_mm = _require_type_dimension_mm(
        symbol, DB.BuiltInParameter.STRUCTURAL_FOUNDATION_WIDTH, "Width")
    footing_thickness_mm = _require_type_dimension_mm(
        symbol, DB.BuiltInParameter.STRUCTURAL_FOUNDATION_THICKNESS,
        "Foundation Thickness")
    cover_mm = _require_instance_cover_mm(
        footing, DB.BuiltInParameter.CLEAR_COVER_OTHER,
        "Rebar Cover - Other Faces")
    bottom_cover_mm = _require_instance_cover_mm(
        footing, DB.BuiltInParameter.CLEAR_COVER_BOTTOM,
        "Rebar Cover - Bottom Face")
    top_cover_mm = _require_instance_cover_mm(
        footing, DB.BuiltInParameter.CLEAR_COVER_TOP,
        "Rebar Cover - Top Face")
    return FootingGeometry(
        a_mm=a_mm, b_mm=b_mm, footing_thickness_mm=footing_thickness_mm,
        cover_mm=cover_mm, bottom_cover_mm=bottom_cover_mm,
        top_cover_mm=top_cover_mm)
