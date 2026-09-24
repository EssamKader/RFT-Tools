# -*- coding: utf-8 -*-
"""Issue #220 -- mock-object verification of ``rft.revit.footing_host``,
run against ``tests/fake_revit_api.py``'s stand-in Revit types (see that
module's own header for what a green run here does and does not prove).

Spec Ref: specs/isolated-footing-dowel-array.md Sec 3 Story 1.

Per this ticket's own "Test volume rule": this file does NOT re-test the
``ReferenceIntersector``/``View3D``-selection MECHANICS -- those are
already covered by ``test_column_mock_adapter.py`` against
``column_host.find_search_view``. It tests only the footing-specific
DIRECTION this ticket adds: the ray runs footing -> column, not
column -> support, and "no column found" refuses with the exact message
Story 1 names.
"""

import pytest

from fake_revit_api import (
    FakeBoundingBox,
    FakeColumn,
    FakeDocument,
    FakeFilteredElementCollector,
    FakeReferenceIntersector,
    FakeReferenceWithContext,
    FakeView3D,
    FakeXYZ,
)

from rft.revit.footing_host import (
    FootingHostError,
    find_column_above,
    find_search_view,
    footing_bounding_box_internal,
)

FT = 304.8


def mm(value):
    """Millimetres as Revit's internal feet."""
    return value / FT


class _FakeFootingHost(object):
    """Stand-in for the footing ``FamilyInstance`` -- only what this
    adapter reads: ``get_BoundingBox(view)`` and ``Id``. Built as its own
    fixture rather than widening ``FakeColumn`` -- same element-isolation
    convention ``test_footing_revit_mesh.py``'s own ``_FakeFootingHost``
    already states.
    """

    def __init__(self, min_xyz, max_xyz, element_id):
        self._box = FakeBoundingBox(min_xyz, max_xyz)
        self.Id = element_id

    def get_BoundingBox(self, _view):
        return self._box


class _Id(object):
    """A bare stand-in for ``ElementId`` equality -- only ``==`` is used
    by this module, which is all this needs to carry."""

    def __init__(self, value):
        self.value = value

    def __eq__(self, other):
        return isinstance(other, _Id) and other.value == self.value

    def __hash__(self):
        return hash(self.value)


FOOTING_ID = _Id(1001)


def footing():
    return _FakeFootingHost(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm(1800.0), mm(1200.0), mm(450.0)),
        FOOTING_ID)


def only_if_the_ray_meets_the_footing(ftg):
    """A hit ONLY when the horizontal self-test ray actually passes
    through the footing's own vertical span -- mirrors
    ``test_column_mock_adapter.only_if_the_ray_meets_the_column``, with
    the footing standing in for the column being self-tested against.
    """
    box = ftg.get_BoundingBox(None)

    def hits(_view, origin, _direction):
        if box.Min.Z <= origin.Z <= box.Max.Z:
            return [FakeReferenceWithContext(ftg.Id, origin.Z)]
        return []
    return hits


# --------------------------------------------------------------------- #
# find_column_above: the new footing -> column direction


def test_the_column_above_is_found(monkeypatch):
    ftg = footing()
    column = FakeColumn(element_id=422078)
    view = FakeView3D("{3D}")
    document = FakeDocument({422078: column})

    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS", [view])

    def hits(_view, origin, direction):
        if direction.Z > 0:
            return [FakeReferenceWithContext(column.Id, mm(450.0))]
        return only_if_the_ray_meets_the_footing(ftg)(_view, origin, direction)

    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [(hits, None)])

    found = find_column_above(document, ftg)
    assert found is column


def test_no_column_found_refuses_with_the_exact_message(monkeypatch):
    """Story 1's own wording: 'No column is attached to this footing.'
    No manual pick/typed fallback -- R7's explicit ruling -- so this is a
    hard refusal, not a code the caller can recover from silently.
    """
    ftg = footing()
    view = FakeView3D("{3D}")
    document = FakeDocument({})

    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS", [view])

    def hits(_view, origin, direction):
        if direction.Z > 0:
            return []
        return only_if_the_ray_meets_the_footing(ftg)(_view, origin, direction)

    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [(hits, None)])

    with pytest.raises(FootingHostError) as caught:
        find_column_above(document, ftg)
    assert str(caught.value) == "No column is attached to this footing."


def test_multiple_hits_the_nearest_one_governs(monkeypatch):
    """Story 1's own text: nearest hit governs, via
    ``ReferenceIntersector.FindNearest``'s own behaviour -- not a case
    this module adds special handling for. The fake's ``FindNearest``
    always returns the FIRST hit in the scenario's own list, so ordering
    the near column first is what proves this, not new adapter logic.
    """
    ftg = footing()
    near_column = FakeColumn(element_id=1, top_z_internal=mm(3000.0))
    far_column = FakeColumn(element_id=2, top_z_internal=mm(6000.0))
    view = FakeView3D("{3D}")
    document = FakeDocument({1: near_column, 2: far_column})

    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS", [view])

    def hits(_view, origin, direction):
        if direction.Z > 0:
            return [FakeReferenceWithContext(near_column.Id, mm(450.0)),
                    FakeReferenceWithContext(far_column.Id, mm(3450.0))]
        return only_if_the_ray_meets_the_footing(ftg)(_view, origin, direction)

    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [(hits, None)])

    found = find_column_above(document, ftg)
    assert found is near_column


def test_a_footing_with_no_bounding_box_is_REFUSED_not_guessed():
    class _NoBoxFooting(object):
        Id = FOOTING_ID

        def get_BoundingBox(self, _view):
            return None

    with pytest.raises(FootingHostError) as caught:
        footing_bounding_box_internal(_NoBoxFooting())
    assert "bounding box" in str(caught.value)


# --------------------------------------------------------------------- #
# The view self-test: chosen by BEHAVIOUR, never by name or settings --
# mirrors test_column_mock_adapter.py's own coverage of this rule, run
# against the footing instead of a column (the new direction).


def test_a_view_that_cannot_see_the_footing_is_REJECTED(monkeypatch):
    ftg = footing()
    analytical = FakeView3D("Analytical Model", blind=True)
    plain = FakeView3D("{3D}")
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        [analytical, plain])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(only_if_the_ray_meets_the_footing(ftg), None)])
    assert find_search_view(None, ftg) is plain


def test_every_view_blind_is_a_REFUSAL_naming_what_was_tried(monkeypatch):
    ftg = footing()
    monkeypatch.setattr(
        FakeFilteredElementCollector, "_ITEMS",
        [FakeView3D("Analytical Model", blind=True),
         FakeView3D("{3D}", blind=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])
    with pytest.raises(FootingHostError) as caught:
        find_search_view(None, ftg)
    message = str(caught.value)
    assert "Analytical Model" in message and "{3D}" in message


def test_a_template_view_is_never_a_candidate(monkeypatch):
    ftg = footing()
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        [FakeView3D("Template", is_template=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])
    with pytest.raises(FootingHostError) as caught:
        find_search_view(None, ftg)
    assert "no non-template 3D view" in str(caught.value)
