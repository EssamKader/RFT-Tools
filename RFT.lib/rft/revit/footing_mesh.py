# -*- coding: utf-8 -*-
"""Bottom-mesh placement adapter -- the tracer-bullet vertical slice, spec
Ref: specs/isolated-footing.md Sec 11 item 2.

Converts ``rft.core.footing_plan`` geometry (mm, footing-local, centroid at
x=y=0, bottom face at z=0) to Revit internal units at the mm/feet boundary
(``rft.revit.units``, the repo's single designated boundary -- REUSE_
GUIDELINES.md Sec 1) and calls ``Rebar.CreateFromCurves`` once per bar.

API shape: docs/footing/verification/issue-197-footing-tracer-bullet.md
Sec 1 confirms, by a KEPT write, that an isolated footing ``FamilyInstance``
is a valid, direct host for ``Rebar.CreateFromCurves`` -- "no cast, no
wrapper, no intermediate analytical element" -- and that call passed
``XYZ.BasisZ`` as the ``norm`` argument, exactly as used below. The
trailing ``RebarHookOrientation``/boolean arguments are NOT shown by
#197's write-up (truncated with "..."); rather than invent them, they are
copied from the one place in this repo that already calls
``Rebar.CreateFromCurves`` for a straight, unhooked bar --
``RFT.lib/rft/revit/placement.py``'s ``place_anchored_bar`` (RebarStyle.
Standard, no start/end hook, ``RebarHookOrientation.Left`` both ends,
``useExistingShapeIfPossible``/``createNewShape`` both True) -- which
itself is flagged there as "UNVERIFIED AGAINST A LIVE HOST" for those same
two boolean flags. Reusing that already-recorded uncertainty is not new
guessing; each call site does not need to guess again independently.

Per this repo's hard rule, this module does not open, commit or roll back
a transaction -- the caller owns the one transaction for the whole footing
(so a failure here leaves the model exactly as it was).
"""

from Autodesk.Revit.DB import Line, XYZ
from Autodesk.Revit.DB.Structure import Rebar, RebarHookOrientation, RebarStyle

from .units import mm_to_internal


def _footing_origin(footing):
    """(centre_x, centre_y, bottom_z), internal units, from the footing
    host's own bounding box -- the same Min/Max-bounding-box datum issue
    #197 Sec 2 measured a dowel's z-range against ("z = footing.Min.Z +
    ..."), and the same ``get_BoundingBox(None)`` call already used
    elsewhere in this repo for a structural host's vertical extent.
    """
    box = footing.get_BoundingBox(None)
    centre_x = (box.Min.X + box.Max.X) / 2.0
    centre_y = (box.Min.Y + box.Max.Y) / 2.0
    return centre_x, centre_y, box.Min.Z


def _to_world_point(origin_x, origin_y, origin_z, local_point):
    """One ``rft.core.footing_mesh.LocalPoint`` (mm) -> world ``XYZ``
    (internal units), translated by the footing's own origin.
    """
    return XYZ(
        origin_x + mm_to_internal(local_point.x_mm),
        origin_y + mm_to_internal(local_point.y_mm),
        origin_z + mm_to_internal(local_point.z_mm),
    )


def _bar_curve(origin_x, origin_y, origin_z, endpoints):
    start = _to_world_point(origin_x, origin_y, origin_z, endpoints.start)
    end = _to_world_point(origin_x, origin_y, origin_z, endpoints.end)
    return Line.CreateBound(start, end)


def _place_one_bar(document, footing, curve, bar_type):
    return Rebar.CreateFromCurves(
        document,
        RebarStyle.Standard,
        bar_type,
        None,  # startHook -- straight case, no hooks (that is #199)
        None,  # endHook
        footing,
        XYZ.BasisZ,  # norm -- confirmed by issue #197's own tracer bullet
        [curve],
        RebarHookOrientation.Left,
        RebarHookOrientation.Left,
        True,
        True,
    )


def place_straight_bottom_mesh(document, footing, bottom_mesh,
                                bar_x_type, bar_y_type):
    """Places ONE ``mesh_bar_x`` bar and ONE ``mesh_bar_y`` bar (straight
    case, centred on the footing's own plan centroid), hosted directly on
    ``footing`` -- the tracer-bullet vertical slice (spec Sec 11 item 2).

    No hook, no array, no spacing/quantity: this proves the placement
    mechanics end to end for a single representative bar per direction:
    full mesh spacing/quantity is later ticket scope, not named by this
    one's formulas.

    ``bottom_mesh`` is a ``rft.core.footing_plan.BottomMeshPlan`` -- the
    caller must build it via ``rft.core.footing_plan.build_footing_plan``,
    never by calling ``rft.core.footing_mesh`` directly (the one composing
    module rule, docs/token-efficient-expansion.md Sec 7).

    Returns ``(bar_x, bar_y)``, the two created ``Rebar`` elements.
    """
    origin_x, origin_y, origin_z = _footing_origin(footing)
    curve_x = _bar_curve(origin_x, origin_y, origin_z,
                          bottom_mesh.bar_x_endpoints)
    curve_y = _bar_curve(origin_x, origin_y, origin_z,
                          bottom_mesh.bar_y_endpoints)
    bar_x = _place_one_bar(document, footing, curve_x, bar_x_type)
    bar_y = _place_one_bar(document, footing, curve_y, bar_y_type)
    return bar_x, bar_y
