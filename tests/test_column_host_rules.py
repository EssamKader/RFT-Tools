# -*- coding: utf-8 -*-
"""#87 — the refusals that decide which columns get detailed.

Every case here is one a live host would otherwise be the first to see.
The numbers are not invented: the rectangular and I-section face counts
were measured on Revit 2024 and are recorded in
``docs/column/verification/issue-87-column-read-and-refusals.md``.
"""

import pytest

from rft.core.column_host_rules import (
    SOURCE_LEVEL_ELEVATION,
    SOURCE_SUPPORT_FACE,
    extent_from_ends,
    levels_between,
    multi_storey_refusal,
    rectangular_section_refusal,
    section_from_dimensions,
)

# As measured: 6 faces, 4 vertical, 0 curved.
RECTANGLE = [(1.0, 0.0, 0.0), (0.0, -1.0, 0.0), (-1.0, 0.0, 0.0),
             (0.0, 1.0, 0.0), (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]

# As measured on UC305x305x97: 14 planar faces, 12 of them vertical, plus
# 4 curved (the root fillets). Note the DIRECTIONS are the same four.
I_SECTION_VERTICALS = [(1.0, 0.0, 0.0), (0.0, -1.0, 0.0),
                       (-1.0, 0.0, 0.0), (0.0, 1.0, 0.0)] * 3
I_SECTION = I_SECTION_VERTICALS + [(0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]


def test_a_rectangular_column_is_accepted():
    assert rectangular_section_refusal(RECTANGLE, 0) is None


def test_the_i_section_is_refused_on_its_face_COUNT():
    """The finding that matters most in #87.

    An I-section's twelve vertical faces carry exactly the same four normal
    directions as a rectangle's four -- every flange and web face is
    axis-aligned, in antiparallel perpendicular pairs. So this case is run
    with ``curved_face_count=0`` deliberately, stripping away the fillets
    that would otherwise catch it, to prove the COUNT is doing the work.

    Without it the tool details a rectangular cage into a steel UC.
    """
    # The directions alone are indistinguishable from a rectangle's...
    assert set(I_SECTION_VERTICALS) == set(RECTANGLE[:4])
    # ...and the count still refuses it.
    refusal = rectangular_section_refusal(I_SECTION, 0)
    assert refusal is not None
    assert "12 vertical faces" in refusal


def test_a_curved_face_is_refused_and_counted():
    refusal = rectangular_section_refusal(RECTANGLE, 4)
    assert refusal is not None
    assert "4 curved face(s)" in refusal


def test_a_parallelogram_has_four_vertical_faces_and_is_still_refused():
    """Four faces in two opposite pairs, but the pairs are not
    perpendicular. The count passes; the direction check is what earns its
    place here.
    """
    skew = (0.7071, 0.7071, 0.0)
    parallelogram = [(1.0, 0.0, 0.0), (-1.0, 0.0, 0.0),
                     skew, (-skew[0], -skew[1], 0.0),
                     (0.0, 0.0, 1.0), (0.0, 0.0, -1.0)]
    refusal = rectangular_section_refusal(parallelogram, 0)
    assert refusal is not None
    assert "perpendicular" in refusal


def test_four_vertical_faces_that_are_not_even_paired_are_refused():
    unpaired = [(1.0, 0.0, 0.0), (0.0, 1.0, 0.0),
                (0.7071, 0.7071, 0.0), (-0.7071, 0.7071, 0.0)]
    refusal = rectangular_section_refusal(unpaired, 0)
    assert refusal is not None
    assert "opposite pairs" in refusal


def test_duplicate_normals_do_not_confuse_the_pairing():
    """Two distinct faces can share a normal. Matching by value and then
    "removing the one I matched" would remove the wrong face; the pairing
    works on indices for this reason.
    """
    duplicated = [(1.0, 0.0, 0.0), (1.0, 0.0, 0.0),
                  (-1.0, 0.0, 0.0), (-1.0, 0.0, 0.0)]
    # Not a rectangle -- no perpendicular pair at all -- and it must say so
    # rather than raise.
    assert rectangular_section_refusal(duplicated, 0) is not None


# --------------------------------------------------------------------- #
# Multi-storey


LEVELS = [("Level 1", 0.0), ("Level 2", 3000.0), ("Level 3", 6000.0)]


def test_a_single_storey_column_is_accepted():
    """The live case: the test column spans Level 1 to Level 2, so no level
    lies strictly between. This model has no multi-storey column, which is
    why the positive cases below are fabricated.
    """
    assert multi_storey_refusal(0.0, 3000.0, LEVELS) is None


def test_a_two_storey_column_is_refused_and_NAMES_the_level():
    refusal = multi_storey_refusal(0.0, 6000.0, LEVELS)
    assert refusal is not None
    assert "Level 2" in refusal, "a refusal the user cannot act on is half a refusal"
    assert "1 level(s)" in refusal


def test_the_end_levels_themselves_are_not_counted_as_crossed():
    assert levels_between(0.0, 3000.0, LEVELS) == []


def test_a_level_a_hair_off_an_end_does_not_read_as_a_storey():
    """A level and a column top both set to "3000" can differ in the last
    stored bit. A 0.1 mm difference must not refuse a perfectly ordinary
    column.
    """
    assert levels_between(0.0, 3000.1, LEVELS) == []
    assert multi_storey_refusal(0.0, 3000.1, LEVELS) is None


def test_an_upside_down_extent_still_finds_the_crossed_levels():
    assert len(levels_between(6000.0, 0.0, LEVELS)) == 1


# --------------------------------------------------------------------- #
# Extent, and where each number came from


def test_both_ends_from_support_faces():
    extent = extent_from_ends(300.0, 2700.0, 0.0, 3000.0)
    assert extent.clear_height_mm == 2400.0
    assert extent.base_source == SOURCE_SUPPORT_FACE
    assert extent.top_source == SOURCE_SUPPORT_FACE


def test_a_missing_base_support_is_normal_and_falls_back_to_the_level():
    """#69 found NOTHING below the test column. That is case C1 -- a
    ground-floor column with no base support element -- not a search
    failure, and a search that assumes a face exists at both ends throws on
    the very first ground-floor column.
    """
    extent = extent_from_ends(None, 2700.0, 0.0, 3000.0)
    assert extent.base_z_mm == 0.0
    assert extent.clear_height_mm == 2700.0
    assert extent.base_source == SOURCE_LEVEL_ELEVATION
    assert extent.top_source == SOURCE_SUPPORT_FACE


def test_the_source_travels_with_the_number():
    """Two columns can both report 2700 and be making different claims.
    Dropping the source lets a level elevation reach the Review report
    dressed as a measured support face.
    """
    measured = extent_from_ends(0.0, 2700.0, 0.0, 3000.0)
    assumed = extent_from_ends(None, None, 0.0, 2700.0)
    assert measured.clear_height_mm == assumed.clear_height_mm
    assert measured.top_source != assumed.top_source


def test_an_inverted_extent_is_a_read_error_not_a_geometry():
    with pytest.raises(ValueError) as excinfo:
        extent_from_ends(3000.0, 0.0, 0.0, 3000.0)
    assert "not above its base" in str(excinfo.value)


# --------------------------------------------------------------------- #
# Section roles


def test_the_narrow_dimension_is_resolved_once_not_by_every_caller():
    """Spec section 2 makes the SMALLER dimension govern S0 and the LARGER
    govern L0. Reading them the wrong way round inverts both silently.
    """
    for section in (section_from_dimensions(450.0, 600.0),
                    section_from_dimensions(600.0, 450.0)):
        assert section.narrow_mm == 450.0
        assert section.wide_mm == 600.0


def test_b_and_h_keep_their_own_identity():
    """narrow/wide are roles; b/h are directions (b along Hand, h along
    Facing, #69). A 600 x 450 column must not silently become 450 x 600.
    """
    section = section_from_dimensions(600.0, 450.0)
    assert (section.b_mm, section.h_mm) == (600.0, 450.0)


@pytest.mark.parametrize("b,h", [(0.0, 600.0), (450.0, 0.0), (-450.0, 600.0)])
def test_a_non_positive_dimension_is_a_read_failure(b, h):
    with pytest.raises(ValueError):
        section_from_dimensions(b, h)
