# -*- coding: utf-8 -*-
"""Shared "prove a View3D can see a known element by ray, then reuse it
for a different category search" mechanism.

Extracted for issue #220's PR review (finding 3): ``rft.revit.
footing_host`` had duplicated ``rft.revit.column_host``'s
``find_search_view`` structure verbatim (``RAY_CLEARANCE_INTERNAL``,
``_inset_internal``, the self-test-then-refuse loop) to run the same
ray-cast MECHANISM in the opposite search direction (footing -> column,
instead of column -> support). This module is the one place that
mechanism now lives; ``footing_host.py`` calls it.

**``column_host.py`` is NOT migrated onto this module.** This repo's own
element-isolation rule ("never edit a beam or column module" --
`CONTEXT.md`, `REUSE_GUIDELINES.md` Sec 3) forbids a footing ticket from
editing a column-tool file, even a behaviour-preserving refactor.
``column_host.find_search_view``/``find_support_face_z_mm`` therefore
still carry their own, now-duplicate, copy of this same logic --
recorded here as an explicit, deliberate follow-up: a ticket scoped for
the column tool (not this one) should migrate ``column_host.py`` onto
this module. Both element modules already depend on nothing but this one
shared file, which is the point -- neither column nor footing code
depends on the OTHER element's module.

The rule this module exists to serve -- "chosen by behaviour, never by
name or by settings" -- is `column_host.find_search_view`'s own, restated
here rather than re-derived: #69/#107 found two ``View3D``s with
IDENTICAL ``GetCategoryHidden``, ``ViewTemplateId`` and
``IsSectionBoxActive`` disagree on what a ``ReferenceIntersector`` can see
through them. There is no property to inspect -- only a ray proves it.
"""

from Autodesk.Revit import DB

#: How far outside a known element's own solid a self-test ray starts.
#: Feet, Revit internal units -- the same value both
#: ``column_host.RAY_CLEARANCE_INTERNAL`` and the pre-extraction
#: ``footing_host.RAY_CLEARANCE_INTERNAL`` already used.
RAY_CLEARANCE_INTERNAL = 1.0


class RaySearchError(Exception):
    """No view's self-test succeeded, or the project has no non-template
    3D view to try. Callers translate this into their OWN element-specific
    exception (see ``footing_host.find_search_view``) rather than letting
    it reach past the module that called in here -- one exception type per
    element module, even though the mechanism is shared.
    """


def inset_internal(min_z, max_z, clearance=RAY_CLEARANCE_INTERNAL):
    """How far inside a known element's own vertical extent a directional
    search ray starts.

    Normally the full ``clearance``, scaled down on an element shorter
    than four clearances so the origin cannot cross past its opposite
    end -- mirrors ``column_host._inset_internal`` and the pre-extraction
    ``footing_host._inset_internal``, both replaced by this.
    """
    span = max_z - min_z
    return min(clearance, span / 4.0)


def find_self_testing_view(doc, self_test_category, self_test_origin,
                            self_test_direction, known_element_id,
                            no_view_message, all_blind_message):
    """A ``View3D`` whose ``ReferenceIntersector`` (filtered to
    ``self_test_category``) actually reports ``known_element_id`` when
    fired from ``self_test_origin`` toward ``self_test_direction``.

    Refuses (``RaySearchError``) rather than returning an unproven view --
    a guessed elevation past this point would be a plausible number, not a
    finding, per ``column_host.find_search_view``'s own reasoning.
    ``all_blind_message`` receives the list of tried view names appended,
    space-separated, as ``"<message> Tried: <names>."``.
    """
    views = [view for view
             in DB.FilteredElementCollector(doc).OfClass(DB.View3D)
             if not view.IsTemplate]
    if not views:
        raise RaySearchError(no_view_message)

    tried = []
    for view in views:
        intersector = DB.ReferenceIntersector(
            DB.ElementCategoryFilter(self_test_category),
            DB.FindReferenceTarget.Element, view)
        intersector.FindReferencesInRevitLinks = False
        hits = intersector.Find(self_test_origin, self_test_direction)
        for hit in hits:
            if hit.GetReference().ElementId == known_element_id:
                return view
        tried.append(view.Name)
    raise RaySearchError(
        "%s Tried: %s." % (all_blind_message, ", ".join(tried)))


def find_nearest_in_category(view, category, origin, direction):
    """The nearest element of ``category`` a ray from ``origin`` toward
    ``direction`` meets through ``view``, or ``None``.

    A thin wrapper only -- what ``None`` MEANS is left to the caller
    (a legitimate "nothing there" for a support search, a refusal for a
    column search), matching how each already handled its own bare
    ``ReferenceIntersector.FindNearest`` call before this extraction.
    """
    intersector = DB.ReferenceIntersector(
        DB.ElementCategoryFilter(category),
        DB.FindReferenceTarget.Element, view)
    intersector.FindReferencesInRevitLinks = False
    return intersector.FindNearest(origin, direction)
