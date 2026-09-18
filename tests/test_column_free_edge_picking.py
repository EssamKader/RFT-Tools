# -*- coding: utf-8 -*-
"""Section 3 answered by POINTING at faces, not by naming the tool's axes.

The window used to ask "is +Hand a free edge?" -- a question in a frame
that is **not visible in any view**. Answering it by checkbox means the
engineer translates first, and a translation done in someone's head is one
that can be wrong with nothing to catch it: the wrong face flagged moves a
bend to the wrong side of the column and every other number stays right.

#103 measured the correlation this rests on: every vertical face normal
came back as EXACTLY +/-Hand or +/-Facing by dot product, at full printed
precision, with no ambiguity.
"""

import pytest

from fake_revit_api import FakeCurvedFace, FakeElementId, FakePlanarFace

from rft.core.column_roof import (
    FACE_AXIS_TOLERANCE, direction_for_normal,
)
from rft.revit.column_roof_slab import ColumnFreeEdgeFaceFilter


# --------------------------------------------------------------------- #
# The pure mapping


HAND = (1.0, 0.0)
FACING = (0.0, 1.0)


@pytest.mark.parametrize("normal,expected", [
    ((1.0, 0.0), "+Hand"),
    ((-1.0, 0.0), "-Hand"),
    ((0.0, 1.0), "+Facing"),
    ((0.0, -1.0), "-Facing"),
])
def test_a_face_normal_names_its_own_direction(normal, expected):
    assert direction_for_normal(normal, HAND, FACING) == expected


def test_a_ROTATED_column_maps_by_its_OWN_axes_not_by_world_X_and_Y():
    """R42's rule, and #103's: the frame is the column's, never the
    world's. A column at 30 degrees has no face pointing along world X,
    and a mapping that assumed one would flag nothing -- or worse, flag
    the nearest.
    """
    import math
    angle = math.radians(30.0)
    hand = (math.cos(angle), math.sin(angle))
    facing = (-math.sin(angle), math.cos(angle))
    assert direction_for_normal(hand, hand, facing) == "+Hand"
    assert direction_for_normal(facing, hand, facing) == "+Facing"
    assert direction_for_normal((1.0, 0.0), hand, facing) is None


def test_a_face_that_squares_with_NEITHER_axis_is_refused_not_guessed():
    """Nearest-match would flag a face the engineer did not choose. The
    filter should already have made such a face unpickable; this is the
    belt to that braces.
    """
    assert direction_for_normal((0.7071, 0.7071), HAND, FACING) is None


def test_the_tolerance_is_a_REFUSAL_threshold_not_a_fitting_one():
    """#103 measured the normals as exact, so this number is not here to
    accommodate sloppy geometry -- it is here to reject geometry that is
    not one of the four faces at all."""
    assert FACE_AXIS_TOLERANCE > 0.99
    just_off = (FACE_AXIS_TOLERANCE - 0.01, 0.0)
    assert direction_for_normal(just_off, HAND, FACING) is None


# --------------------------------------------------------------------- #
# The filter: THIS column, and only its vertical faces


def _Face(normal):
    """A real `FakePlanarFace`, not a look-alike: the filter tests
    `isinstance(face, DB.PlanarFace)` on purpose, so a stub that merely
    carries a `FaceNormal` would pass this file while failing on a host.
    """
    return FakePlanarFace(normal)


class _Normal(object):
    def __init__(self, x, y, z):
        self.X, self.Y, self.Z = x, y, z


class _Element(object):
    def __init__(self, element_id, face=None):
        self.Id = element_id
        self._face = face

    def GetGeometryObjectFromReference(self, reference):
        return self._face


class _Document(object):
    def __init__(self, element):
        self._element = element

    def GetElement(self, reference):
        return self._element


def _filter_for(column_id, face):
    column = _Element(column_id, face)
    return ColumnFreeEdgeFaceFilter(_Document(column), column), column


def test_only_THIS_column_may_be_picked_not_any_structural_column():
    """The probe's filter matched by CATEGORY. That would let a free edge
    be flagged on the NEIGHBOURING column -- a face that looks right in
    the view and describes the wrong element entirely."""
    mine = FakeElementId(100)
    theirs = FakeElementId(200)
    column_filter, _ = _filter_for(mine, None)
    assert column_filter.AllowElement(_Element(mine))
    assert not column_filter.AllowElement(_Element(theirs))


def test_an_END_face_is_rejected_AT_THE_PICK_so_it_never_highlights():
    """#103: 205 end faces offered, 205 rejected. The engineer cannot make
    the mistake, rather than being told about it afterwards."""
    element_id = FakeElementId(100)
    column_filter, _ = _filter_for(
        element_id, _Face(_Normal(0.0, 0.0, 1.0)))
    assert not column_filter.AllowReference(object(), None)


def test_a_VERTICAL_face_of_this_column_is_allowed():
    element_id = FakeElementId(100)
    column_filter, _ = _filter_for(
        element_id, _Face(_Normal(1.0, 0.0, 0.0)))
    assert column_filter.AllowReference(object(), None)


def test_NEITHER_filter_method_ever_raises():
    """A filter that throws is one Revit stops calling, and the pick then
    silently allows everything -- the failure mode is the opposite of the
    one the filter exists to prevent."""
    column_filter, _ = _filter_for(FakeElementId(100), None)

    class _Exploding(object):
        @property
        def Id(self):
            raise RuntimeError("boom")

        def GetGeometryObjectFromReference(self, reference):
            raise RuntimeError("boom")

    assert column_filter.AllowElement(_Exploding()) is False

    class _ExplodingDocument(object):
        def GetElement(self, reference):
            raise RuntimeError("boom")

    exploding = ColumnFreeEdgeFaceFilter(_ExplodingDocument(),
                                         _Element(FakeElementId(100)))
    assert exploding.AllowReference(object(), None) is False


def test_a_CURVED_face_is_refused():
    """A round column's face has no single normal to map, so it is not one
    of section 3's four. Rejected at the pick like an end face."""
    element_id = FakeElementId(100)
    column_filter, _ = _filter_for(element_id, FakeCurvedFace())
    assert not column_filter.AllowReference(object(), None)
