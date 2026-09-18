# -*- coding: utf-8 -*-
"""Issue #167 -- ``rft.revit.column_roof_slab``, run against stand-in Revit
types (the same discipline `test_column_mock_adapter.py` established for
`column_host.py`).

The fixture is #161/#170's own column and floor: 450 x 600, `Hand=(1,0,0)`,
`Facing=(0,1,0)`, top at 3000 mm, under Floor 424637 (300 mm thick), a
5000 x 6000 mm rectangular slab whose boundary is placed so the column's
plan position reproduces #170's measured runs (127.5 / 2922.5 / 5059.7 /
140.3 mm) to make this fixture double as a regression check on those
numbers, not merely a clean-room rectangle.
"""

import pytest

from fake_revit_api import (
    FakeBuiltInParameter,
    FakeColumn,
    FakeCurve,
    FakeCurveLoop,
    FakeDocument,
    FakeDoubleParameter,
    FakeElementId,
    FakeElementIdParameter,
    FakeFloor,
    FakeRebarCoverType,
    FakeTopFace,
    FakeXYZ,
)

from rft.core.column_roof import RoofBendDirection
from rft.revit.column_roof_slab import (
    BEND_DIRECTION_NAMES,
    ColumnRoofSlabError,
    find_top_floor,
    read_bend_directions,
    read_slab_cover_mm,
    read_slab_thickness_mm,
    read_top_floor_slab,
)

FT = 304.8


def mm(value):
    return value / FT


COVER_ID = 500001
FLOOR_ID = 424637
COLUMN_ID = 424596

#: #170's own numbers: column at (2500, 3000) inside a 0..5127.5-wide,
#: 0..3062.5-tall rectangle puts the four faces at exactly the measured
#: distances. b (Hand) = 450, h (Facing) = 600, so half-extents are 225
#: and 300.
COLUMN_X, COLUMN_Y = 2500.0, 3000.0
RECT_MIN_X, RECT_MAX_X = COLUMN_X - 225.0 - 2922.5, COLUMN_X + 225.0 + 127.5
RECT_MIN_Y, RECT_MAX_Y = COLUMN_Y - 300.0 - 140.3, COLUMN_Y + 300.0 + 5059.7


def rectangular_top_face():
    def pt(x, y):
        return FakeXYZ(mm(x), mm(y), mm(3000.0))

    loop = FakeCurveLoop([
        FakeCurve(pt(RECT_MIN_X, RECT_MIN_Y), pt(RECT_MAX_X, RECT_MIN_Y)),
        FakeCurve(pt(RECT_MAX_X, RECT_MIN_Y), pt(RECT_MAX_X, RECT_MAX_Y)),
        FakeCurve(pt(RECT_MAX_X, RECT_MAX_Y), pt(RECT_MIN_X, RECT_MAX_Y)),
        FakeCurve(pt(RECT_MIN_X, RECT_MAX_Y), pt(RECT_MIN_X, RECT_MIN_Y)),
    ])
    return FakeTopFace([loop])


def floor(document, thickness_mm=300.0, cover_mm=0.0, min_z=2700.0,
         max_z=3000.0, top_face=None, element_id=FLOOR_ID):
    parameters = {
        FakeBuiltInParameter.FLOOR_ATTR_THICKNESS_PARAM:
            FakeDoubleParameter(mm(thickness_mm)),
    }
    if cover_mm is not None:
        cover_type = FakeRebarCoverType(mm(cover_mm), name="Edge",
                                        id_value=COVER_ID)
        document._elements[COVER_ID] = cover_type
        parameters[FakeBuiltInParameter.CLEAR_COVER_OTHER] = \
            FakeElementIdParameter(cover_type.Id)
    return FakeFloor(document=document, min_z_internal=mm(min_z),
                     max_z_internal=mm(max_z), parameters=parameters,
                     element_id=element_id,
                     top_face=top_face or rectangular_top_face())


def column(document, joined_ids=None, top_z=3000.0):
    return FakeColumn(document=document, element_id=COLUMN_ID,
                      base_z_internal=mm(0.0), top_z_internal=mm(top_z),
                      location_xy=(mm(COLUMN_X), mm(COLUMN_Y)),
                      joined_ids=(joined_ids if joined_ids is not None
                                  else [FakeElementId(FLOOR_ID)]))


# --------------------------------------------------------------------- #
# Finding the slab -- R37, R39


def test_the_joined_floor_above_the_column_is_found():
    doc = FakeDocument()
    f = floor(doc)
    doc._elements[FLOOR_ID] = f
    col = column(doc)
    assert find_top_floor(doc, col) is f


def test_no_joined_floor_is_a_REFUSAL_naming_R37_and_R39():
    doc = FakeDocument()
    col = column(doc, joined_ids=[])
    with pytest.raises(ColumnRoofSlabError) as caught:
        find_top_floor(doc, col)
    message = str(caught.value)
    assert "No Floor is joined" in message
    assert "R39" in message


def test_a_joined_floor_BELOW_the_column_does_not_count():
    """The floor a column stands ON might also be joined to it; only a
    Floor whose own vertical extent contains the column's TOP counts."""
    doc = FakeDocument()
    below = FakeFloor(document=doc, min_z_internal=mm(-300.0),
                      max_z_internal=mm(0.0), element_id=999,
                      parameters={})
    doc._elements[999] = below
    col = column(doc, joined_ids=[FakeElementId(999)])
    with pytest.raises(ColumnRoofSlabError):
        find_top_floor(doc, col)


def test_two_candidate_floors_is_a_REFUSAL_not_a_pick():
    doc = FakeDocument()
    f1 = floor(doc)
    doc._elements[FLOOR_ID] = f1
    second = floor(doc, element_id=424638)
    doc._elements[424638] = second
    col = column(doc, joined_ids=[FakeElementId(FLOOR_ID),
                                  FakeElementId(424638)])
    with pytest.raises(ColumnRoofSlabError) as caught:
        find_top_floor(doc, col)
    assert "2 Floors" in str(caught.value)


def test_something_that_is_not_a_Floor_does_not_count():
    """A non-Floor with a bounding box that WOULD pass the z-range test if
    the isinstance check were not there -- so the isinstance check, not a
    coincidental ``None`` bounding box, is what this test proves."""
    doc = FakeDocument()
    not_a_floor = FakeColumn(document=doc, element_id=777,
                             base_z_internal=mm(2700.0),
                             top_z_internal=mm(3000.0))
    doc._elements[777] = not_a_floor
    col = column(doc, joined_ids=[FakeElementId(777)])
    with pytest.raises(ColumnRoofSlabError):
        find_top_floor(doc, col)


# --------------------------------------------------------------------- #
# Thickness -- R37


def test_the_thickness_is_read_from_FLOOR_ATTR_THICKNESS_PARAM():
    doc = FakeDocument()
    f = floor(doc, thickness_mm=300.0)
    assert read_slab_thickness_mm(f) == pytest.approx(300.0)


def test_a_floor_with_no_thickness_parameter_is_REFUSED():
    doc = FakeDocument()
    f = FakeFloor(document=doc, parameters={})
    with pytest.raises(ColumnRoofSlabError) as caught:
        read_slab_thickness_mm(f)
    assert "thickness" in str(caught.value)


# --------------------------------------------------------------------- #
# Cover -- R38


def test_a_real_cover_is_READ_and_cannot_be_overridden():
    doc = FakeDocument()
    f = floor(doc, cover_mm=25.0)
    cover_mm, provenance = read_slab_cover_mm(f, typed_cover_mm=999.0)
    assert cover_mm == pytest.approx(25.0)
    assert provenance == "read"


def test_a_zero_cover_opens_the_typed_field():
    doc = FakeDocument()
    f = floor(doc, cover_mm=0.0)
    cover_mm, provenance = read_slab_cover_mm(f, typed_cover_mm=25.0)
    assert cover_mm == pytest.approx(25.0)
    assert provenance == "typed"


def test_a_zero_cover_with_no_typed_value_is_a_REFUSAL_not_a_default():
    doc = FakeDocument()
    f = floor(doc, cover_mm=0.0)
    with pytest.raises(ColumnRoofSlabError) as caught:
        read_slab_cover_mm(f, typed_cover_mm=None)
    assert "type a cover" in str(caught.value) or "type" in str(caught.value)


def test_an_unset_cover_parameter_ALSO_opens_the_typed_field():
    doc = FakeDocument()
    f = floor(doc, cover_mm=None)
    cover_mm, provenance = read_slab_cover_mm(f, typed_cover_mm=30.0)
    assert cover_mm == pytest.approx(30.0)
    assert provenance == "typed"


# --------------------------------------------------------------------- #
# The run -- R41, R42, reproducing #170's own measured numbers


def test_the_run_reproduces_R42s_measured_numbers_in_every_direction():
    doc = FakeDocument()
    f = floor(doc, cover_mm=0.0)
    doc._elements[FLOOR_ID] = f
    col = column(doc)
    directions = read_bend_directions(doc, f, col, cover_mm=0.0)
    by_name = dict((d.name, d.available_run_mm) for d in directions)
    assert by_name["+Hand"] == pytest.approx(127.5, abs=0.1)
    assert by_name["-Hand"] == pytest.approx(2922.5, abs=0.1)
    assert by_name["+Facing"] == pytest.approx(5059.7, abs=0.1)
    assert by_name["-Facing"] == pytest.approx(140.3, abs=0.1)
    assert all(d.has_slab for d in directions)


def test_a_non_zero_slab_cover_is_SUBTRACTED_from_the_measured_run():
    """R42: the probe measures to the boundary; a real cover on the slab
    must not be inherited as a coincidental zero."""
    doc = FakeDocument()
    f = floor(doc, cover_mm=0.0)
    doc._elements[FLOOR_ID] = f
    col = column(doc)
    directions = read_bend_directions(doc, f, col, cover_mm=25.0)
    by_name = dict((d.name, d.available_run_mm) for d in directions)
    assert by_name["+Hand"] == pytest.approx(127.5 - 25.0, abs=0.1)


def test_a_flagged_free_edge_uses_the_free_edge_cap_not_the_measured_run():
    doc = FakeDocument()
    f = floor(doc, cover_mm=0.0)
    doc._elements[FLOOR_ID] = f
    col = column(doc)
    directions = read_bend_directions(doc, f, col, cover_mm=40.0,
                                      free_edge_names=("+Hand",))
    by_name = dict((d.name, d) for d in directions)
    hand_plus = by_name["+Hand"]
    assert hand_plus.has_slab is False
    # section.b_mm (Hand) is 450 for this fixture's FakeColumn default type.
    assert hand_plus.available_run_mm == pytest.approx(450.0 - 2 * 40.0)
    assert by_name["-Hand"].has_slab is True


def test_all_four_names_are_always_present_in_the_fixed_order():
    doc = FakeDocument()
    f = floor(doc)
    doc._elements[FLOOR_ID] = f
    col = column(doc)
    directions = read_bend_directions(doc, f, col, cover_mm=0.0)
    assert tuple(d.name for d in directions) == BEND_DIRECTION_NAMES


# --------------------------------------------------------------------- #
# The whole read, end to end


def test_read_top_floor_slab_assembles_everything():
    doc = FakeDocument()
    f = floor(doc, thickness_mm=300.0, cover_mm=0.0)
    doc._elements[FLOOR_ID] = f
    col = column(doc)
    result = read_top_floor_slab(doc, col, typed_cover_mm=25.0)
    assert result["floor"] is f
    assert result["thickness_mm"] == pytest.approx(300.0)
    assert result["cover_mm"] == pytest.approx(25.0)
    assert result["cover_provenance"] == "typed"
    assert len(result["directions"]) == 4
    for direction in result["directions"]:
        assert isinstance(direction, RoofBendDirection)
