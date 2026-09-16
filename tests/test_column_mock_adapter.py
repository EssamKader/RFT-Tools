# -*- coding: utf-8 -*-
"""#106 -- the column adapter, run against stand-in Revit types.

Until this file, ``rft.revit.column_host`` -- 410 lines, every number the
window shows -- was imported by **nothing**. `test_column_host_rules.py`
covers the pure refusal logic; the adapter that actually talks to Revit had
never been executed or inspected by any test. The suite was green at 752
while ``read_column`` could not complete a single call.

Three defects reached a live host in one session as a result:

====================================  ==================================
``ElementType.Name`` unreadable       `AttributeError` on the first click
view self-test blind above ground     "no 3D view can see this column"
support search fired from Z = 0       **returned 2700 mm** for a column
                                      whose top support is at 5700 mm
====================================  ==================================

The third is why this file exists rather than more source guards. The
first two announce themselves. That one returns a **plausible number**, and
2700 mm would have gone onto the Review report and from there into a
drawing. It was caught only because the second defect refused first and
stopped execution, and because an upper-storey column happened to be
picked -- a ground-floor column passes all three.

The fakes carry the live-verified shapes (see ``fake_revit_api``). Two
matter most and are modelled deliberately rather than conveniently:

* ``FakeFamilySymbol`` and ``FakeRebarCoverType`` have **no readable
  ``.Name``**, because the real ``ElementType`` hides ``Element.Name``
  behind a setter-only property.
* ``FakeColumnLocation.Point.Z`` is **0 whatever storey the column stands
  on**, because that is what Revit reports. A fake that put the real
  elevation there would let the rc2 defect pass every test and still fire
  every ray at the project base on a host.
"""

import pytest

from fake_revit_api import (
    FakeBuiltInCategory,
    FakeBuiltInParameter,
    FakeColumn,
    FakeCurvedFace,
    FakeDocument,
    FakeElementId,
    FakeElementIdParameter,
    FakeFamilySymbol,
    FakeFilteredElementCollector,
    FakeLevel,
    FakePlanarFace,
    FakeRebarCoverType,
    FakeReferenceIntersector,
    FakeReferenceWithContext,
    FakeSolid,
    FakeView3D,
    FakeXYZ,
)

import rft.revit.column_host as host
from rft.revit.column_host import (
    ColumnHostError, face_normals, find_search_view, find_support_face_z_mm,
    largest_solid, read_cover_mm, read_orientation, read_section_mm,
    vertical_extent_internal,
)

FT = 304.8


def mm(value):
    """Millimetres as Revit's internal feet."""
    return value / FT


#: The column this session detailed: 450 x 600, standing on Level 2,
#: spanning 3000-6000 mm with its top support soffit at 5700.
UPPER_STOREY = dict(base_z_internal=mm(3000.0), top_z_internal=mm(6000.0))
GROUND = dict(base_z_internal=mm(0.0), top_z_internal=mm(3000.0))

COVER_ID = 112574
BASE_LEVEL_ID = 311
TOP_LEVEL_ID = 312


def rectangular_solid():
    """Four vertical faces in two antiparallel perpendicular pairs."""
    return FakeSolid([
        FakePlanarFace(FakeXYZ(1.0, 0.0, 0.0)),
        FakePlanarFace(FakeXYZ(-1.0, 0.0, 0.0)),
        FakePlanarFace(FakeXYZ(0.0, 1.0, 0.0)),
        FakePlanarFace(FakeXYZ(0.0, -1.0, 0.0)),
        FakePlanarFace(FakeXYZ(0.0, 0.0, 1.0)),
        FakePlanarFace(FakeXYZ(0.0, 0.0, -1.0)),
    ], volume=2.0)


def column(**kwargs):
    spans = kwargs.pop("spans", UPPER_STOREY)
    cover = FakeRebarCoverType(mm(40.0), name="Interior (framing, columns)",
                               id_value=COVER_ID)
    document = FakeDocument({
        COVER_ID: cover,
        BASE_LEVEL_ID: FakeLevel("Level 2", mm(3000.0)),
        TOP_LEVEL_ID: FakeLevel("Level 3", mm(6000.0)),
    })
    parameters = {
        FakeBuiltInParameter.CLEAR_COVER_OTHER:
            FakeElementIdParameter(FakeElementId(COVER_ID)),
        FakeBuiltInParameter.CLEAR_COVER_TOP:
            FakeElementIdParameter(None),
        FakeBuiltInParameter.FAMILY_BASE_LEVEL_PARAM:
            FakeElementIdParameter(FakeElementId(BASE_LEVEL_ID)),
        FakeBuiltInParameter.FAMILY_TOP_LEVEL_PARAM:
            FakeElementIdParameter(FakeElementId(TOP_LEVEL_ID)),
    }
    parameters.update(kwargs.pop("parameters", {}))
    return FakeColumn(document=document, solid=rectangular_solid(),
                      parameters=parameters, **dict(spans, **kwargs))


def only_if_the_ray_meets_the_column(col):
    """A hit ONLY when the ray actually passes through the column's own
    vertical span.

    Without this the self-test is untestable: a scenario that answers any
    ray lets the rc2 defect through, because the whole defect was the
    ray's HEIGHT. Confirmed by mutation -- firing from
    ``Location.Point.Z`` (which the fake reports as 0, as Revit does) then
    passes underneath a 3000-6000 mm column exactly as it did on the host.
    """
    box = col.get_BoundingBox(None)

    def hits(_view, origin, _direction):
        if box.Min.Z <= origin.Z <= box.Max.Z:
            return [FakeReferenceWithContext(col.Id, origin.Z)]
        return []
    return hits


# --------------------------------------------------------------------- #
# The rc1 defect: ElementType hides Element.Name


def test_the_type_name_is_read_without_touching_dot_Name():
    """`FamilySymbol` is an `ElementType`, so `.Name` raises under
    IronPython. The fake has none either, which is what makes this a test
    rather than a restatement.
    """
    symbol = FakeFamilySymbol("450 x 600mm")
    with pytest.raises(AttributeError):
        symbol.Name                                    # noqa: B018
    from rft.revit.bar_types import element_name
    assert element_name(symbol) == "450 x 600mm"


def test_the_cover_type_name_is_read_without_touching_dot_Name():
    col = column()
    cover_mm, cover_name = read_cover_mm(col)
    assert cover_mm == pytest.approx(40.0)
    assert cover_name == "Interior (framing, columns)"


def test_the_family_name_still_comes_from_dot_Name():
    """The opposite mistake. `Family` is not an `ElementType`; its
    `SYMBOL_NAME_PARAM` is present but EMPTY, so routing it through
    `element_name` would return a placeholder.
    """
    section = read_section_mm(column())
    assert section.b_mm == pytest.approx(450.0)
    from rft.revit.bar_types import element_name
    assert element_name(column().Symbol.Family).startswith("<unnamed")


# --------------------------------------------------------------------- #
# The rc2 defect: Location.Point.Z is not the column's elevation


def test_the_vertical_extent_comes_from_the_bounding_box_not_the_insertion_point():
    """The fake reports `Location.Point.Z == 0` for an upper-storey column
    exactly as Revit does, so a regression here fails rather than passing
    on a convenient fake.
    """
    col = column()
    assert col.Location.Point.Z == 0.0
    min_z, max_z = vertical_extent_internal(col)
    assert min_z * FT == pytest.approx(3000.0)
    assert max_z * FT == pytest.approx(6000.0)


def test_a_column_with_no_bounding_box_is_REFUSED_not_guessed():
    with pytest.raises(ColumnHostError) as caught:
        vertical_extent_internal(column(bounding_box=False))
    assert "bounding box" in str(caught.value)


def test_the_support_search_fires_from_the_column_s_OWN_ends(monkeypatch):
    """The defect that returned 2700 mm -- the ground floor's soffit -- for
    a column standing on Level 2.

    The scenario answers by height: a ray starting near 5700 finds the
    soffit above, one starting near 3000 finds the slab it bears on, and
    one starting near the project base finds the GROUND floor's soffit.
    A search built from `Location.Point.Z` gets that last answer, which is
    exactly what shipped in rc2.
    """
    def by_height(_view, origin, direction):
        upward = direction.Z > 0
        z_mm = origin.Z * FT
        if upward and z_mm > 4000.0:
            return [FakeReferenceWithContext(FakeElementId(9), mm(5700.0))]
        if upward and z_mm < 1000.0:
            return [FakeReferenceWithContext(FakeElementId(8), mm(2700.0))]
        if not upward and z_mm > 2000.0:
            return [FakeReferenceWithContext(FakeElementId(7), mm(3000.0))]
        return []

    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [(by_height, None)])
    FakeReferenceIntersector.HITS = [(by_height, None)]

    col = column()
    view = FakeView3D("{3D}")
    assert find_support_face_z_mm(None, view, col, upward=True) == \
        pytest.approx(5700.0)
    assert find_support_face_z_mm(None, view, col, upward=False) == \
        pytest.approx(3000.0)


def test_nothing_below_a_ground_floor_column_is_a_NORMAL_answer(monkeypatch):
    """Case C1. #69 found nothing below the test column and that is not a
    failure -- a search that assumes a face exists at both ends throws on
    the first ground-floor column."""
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(lambda _v, _o, d: [] if d.Z < 0 else None, None)])
    result = find_support_face_z_mm(None, FakeView3D("{3D}"),
                                    column(spans=GROUND), upward=False)
    assert result is None


# --------------------------------------------------------------------- #
# The view self-test: chosen by BEHAVIOUR, never by name or settings


def test_a_view_that_cannot_see_the_column_is_REJECTED(monkeypatch):
    """`Analytical Model` and `{3D}` have identical `GetCategoryHidden`,
    `ViewTemplateId` and `IsSectionBoxActive`, and one finds nothing. There
    is no property to inspect, so the adapter fires a ray -- and the fake's
    `blind` flag models a view that returns nothing whatever is asked.
    """
    col = column()
    analytical = FakeView3D("Analytical Model", blind=True)
    plain = FakeView3D("{3D}")
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        [analytical, plain])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(only_if_the_ray_meets_the_column(col), None)])
    assert find_search_view(None, col) is plain


def test_every_view_blind_is_a_REFUSAL_naming_what_was_tried(monkeypatch):
    """Falling back to a level elevation here would be a guess wearing a
    number's clothes."""
    col = column()
    monkeypatch.setattr(
        FakeFilteredElementCollector, "_ITEMS",
        [FakeView3D("Analytical Model", blind=True),
         FakeView3D("{3D}", blind=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])
    with pytest.raises(ColumnHostError) as caught:
        find_search_view(None, col)
    message = str(caught.value)
    assert "Analytical Model" in message and "{3D}" in message


def test_a_template_view_is_never_a_candidate(monkeypatch):
    col = column()
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        [FakeView3D("Template", is_template=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])
    with pytest.raises(ColumnHostError) as caught:
        find_search_view(None, col)
    assert "no non-template 3D view" in str(caught.value)


# --------------------------------------------------------------------- #
# Geometry and the refusals built on it


def test_the_section_comes_from_the_TYPE_never_the_bounding_box():
    """#69 measured 712.8 x 749.6 for a 450 x 600 column rotated 35
    degrees -- a 58% error on the face that governs S0. The fake's
    bounding box is deliberately square, so a regression to it produces an
    obviously wrong section rather than a plausible one."""
    section = read_section_mm(column())
    assert (section.b_mm, section.h_mm) == (pytest.approx(450.0),
                                            pytest.approx(600.0))
    assert section.narrow_mm == pytest.approx(450.0)
    assert section.wide_mm == pytest.approx(600.0)


def test_a_family_without_b_and_h_is_REFUSED_naming_the_family():
    col = column()
    col.Symbol = FakeFamilySymbol("Odd", parameters={"Width": mm(450.0)})
    with pytest.raises(ColumnHostError) as caught:
        read_section_mm(col)
    message = str(caught.value)
    assert "M_Concrete-Rectangular-Column" in message
    assert "'b'" in message


def test_the_largest_solid_wins_and_empty_ones_are_ignored():
    col = column()
    col._solid = None
    with pytest.raises(ColumnHostError) as caught:
        largest_solid(col)
    assert "no solid geometry" in str(caught.value)


def test_curved_faces_are_COUNTED_not_silently_skipped():
    solid = FakeSolid([FakePlanarFace(FakeXYZ(1.0, 0.0, 0.0)),
                       FakeCurvedFace(), FakeCurvedFace()])
    normals, curved = face_normals(solid)
    assert curved == 2
    assert normals == [(1.0, 0.0, 0.0)]


@pytest.mark.parametrize("flag,word", [
    ("Mirrored", "mirrored"),
    ("HandFlipped", "hand-flipped"),
    ("FacingFlipped", "facing-flipped"),
])
def test_a_flipped_column_is_REFUSED(flag, word):
    """Every column ever probed had all three flags False, so what a flip
    does to the b/h mapping is unknown -- and reading it wrong silently
    swaps which dimension governs L0 and which governs S0."""
    col = column()
    setattr(col, flag, True)
    with pytest.raises(ColumnHostError) as caught:
        read_orientation(col)
    assert word in str(caught.value)


def test_an_unflipped_column_reports_hand_and_facing_as_tuples():
    hand, facing = read_orientation(column())
    assert hand == (1.0, 0.0, 0.0)
    assert facing == (0.0, 1.0, 0.0)
