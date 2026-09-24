# -*- coding: utf-8 -*-
"""Mock-object verification of ``rft.revit.ray_search`` -- the shared
"prove a View3D can see a known element by ray, then reuse it for a
different category search" mechanism, extracted from
``rft.revit.column_host`` during PR #224 review (finding 3) after
``rft.revit.footing_host`` had duplicated the same structure verbatim.

THIS is the one place the view-selection MECHANICS (blind view rejected,
every-view-blind refuses naming what was tried, a template view is never
a candidate) are tested -- both ``rft.revit.column_host`` (via
``test_column_mock_adapter.py``, unchanged, still exercising its own
not-yet-migrated copy) and ``rft.revit.footing_host`` (via
``test_footing_revit_host.py``) call into this shared logic, so neither
of those files re-tests it; see each file's own docstring.
"""

import pytest

from fake_revit_api import (
    FakeFilteredElementCollector,
    FakeReferenceIntersector,
    FakeReferenceWithContext,
    FakeView3D,
    FakeXYZ,
)

from rft.revit.ray_search import (
    RaySearchError,
    find_nearest_in_category,
    find_self_testing_view,
    inset_internal,
)

KNOWN_ID = object()
CATEGORY = object()


def only_if_the_ray_meets_the_known_element():
    def hits(_view, _origin, _direction):
        return [FakeReferenceWithContext(KNOWN_ID, 0.0)]
    return hits


def test_a_view_that_cannot_see_the_known_element_is_REJECTED(monkeypatch):
    """#69/#107's own finding, restated generically: two views can have
    identical settings and disagree on what a ray sees through them, so
    the self-test alone -- not a name, not a property -- decides.
    """
    blind = FakeView3D("Analytical Model", blind=True)
    plain = FakeView3D("{3D}")
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        [blind, plain])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(only_if_the_ray_meets_the_known_element(), None)])

    view = find_self_testing_view(
        None, CATEGORY, FakeXYZ(0.0, 0.0, 0.0), FakeXYZ(1.0, 0.0, 0.0),
        KNOWN_ID, no_view_message="no views", all_blind_message="blind")
    assert view is plain


def test_every_view_blind_is_a_REFUSAL_naming_what_was_tried(monkeypatch):
    monkeypatch.setattr(
        FakeFilteredElementCollector, "_ITEMS",
        [FakeView3D("Analytical Model", blind=True),
         FakeView3D("{3D}", blind=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])

    with pytest.raises(RaySearchError) as caught:
        find_self_testing_view(
            None, CATEGORY, FakeXYZ(0.0, 0.0, 0.0), FakeXYZ(1.0, 0.0, 0.0),
            KNOWN_ID, no_view_message="no views",
            all_blind_message="nothing can see it")
    message = str(caught.value)
    assert "nothing can see it" in message
    assert "Analytical Model" in message and "{3D}" in message


def test_a_template_view_is_never_a_candidate(monkeypatch):
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        [FakeView3D("Template", is_template=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])

    with pytest.raises(RaySearchError) as caught:
        find_self_testing_view(
            None, CATEGORY, FakeXYZ(0.0, 0.0, 0.0), FakeXYZ(1.0, 0.0, 0.0),
            KNOWN_ID, no_view_message="no non-template 3D view",
            all_blind_message="nothing can see it")
    assert "no non-template 3D view" in str(caught.value)


def test_no_views_at_all_refuses_with_the_no_view_message(monkeypatch):
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS", [])
    with pytest.raises(RaySearchError) as caught:
        find_self_testing_view(
            None, CATEGORY, FakeXYZ(0.0, 0.0, 0.0), FakeXYZ(1.0, 0.0, 0.0),
            KNOWN_ID, no_view_message="no non-template 3D view",
            all_blind_message="nothing can see it")
    assert str(caught.value) == "no non-template 3D view"


def test_find_nearest_in_category_returns_the_intersector_s_nearest_hit(
        monkeypatch):
    hit = FakeReferenceWithContext(KNOWN_ID, 42.0)
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(lambda _v, _o, _d: [hit], None)])
    result = find_nearest_in_category(
        FakeView3D("{3D}"), CATEGORY, FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(0.0, 0.0, 1.0))
    assert result is hit


def test_find_nearest_in_category_is_none_when_nothing_is_hit(monkeypatch):
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(lambda _v, _o, _d: [], None)])
    result = find_nearest_in_category(
        FakeView3D("{3D}"), CATEGORY, FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(0.0, 0.0, 1.0))
    assert result is None


# --------------------------------------------------------------------- #
# inset_internal


def test_inset_is_the_full_clearance_on_a_tall_element():
    assert inset_internal(0.0, 100.0, clearance=1.0) == pytest.approx(1.0)


def test_inset_is_scaled_down_on_a_short_element():
    """A 2-unit-tall element with a 1-unit clearance: the full clearance
    would put the upward origin past the downward one, so it is scaled to
    a quarter of the span instead."""
    assert inset_internal(0.0, 2.0, clearance=1.0) == pytest.approx(0.5)
