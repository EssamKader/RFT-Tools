# -*- coding: utf-8 -*-
"""Issue #220 -- mock-object verification of ``rft.revit.footing_host``,
run against ``tests/fake_revit_api.py``'s stand-in Revit types (see that
module's own header for what a green run here does and does not prove).

Spec Ref: specs/isolated-footing-dowel-array.md Sec 3 Story 1.

Per this ticket's own "Test volume rule": this file does NOT re-test the
``ReferenceIntersector``/``View3D``-selection MECHANICS themselves --
those now live in ``rft.revit.ray_search`` (extracted during PR #224
review, finding 3) and are tested exactly once, generically, in
``tests/test_ray_search.py``. ``column_host.find_search_view`` still
carries its own not-yet-migrated copy and is still covered by
``test_column_mock_adapter.py`` -- see ``ray_search.py``'s own docstring
for why that migration is a deliberate follow-up, not done here.

What THIS file tests is footing-specific: the ray runs footing -> column,
not column -> support; "no column found" refuses with the exact message
Story 1 names; the nearest hit governs multiple hits; and
``find_search_view``'s translation of a bare ``RaySearchError`` into this
module's own ``FootingHostError`` actually happens (PR #224 review,
finding 4 -- this is the one place that translation is new code, not a
restatement of ``ray_search``'s own mechanics).
"""

import pytest

from fake_revit_api import (
    FakeBoundingBox,
    FakeBuiltInParameter,
    FakeColumn,
    FakeDocument,
    FakeDoubleParameter,
    FakeElementId,
    FakeElementIdParameter,
    FakeFamilySymbol,
    FakeFilteredElementCollector,
    FakeRebarCoverType,
    FakeReferenceIntersector,
    FakeReferenceWithContext,
    FakeView3D,
    FakeXYZ,
)

from rft.core.footing_plan import DowelColumnSection
from rft.revit.column_host import ColumnHostError
from rft.revit.footing_host import (
    FootingAxisMismatchError,
    FootingGeometry,
    FootingHostError,
    find_column_above,
    find_search_view,
    footing_bounding_box_internal,
    read_dowel_column_section_mm,
    read_footing_geometry_mm,
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
# find_search_view's OWN new code: translating ray_search's generic
# RaySearchError into this module's FootingHostError. The self-test
# MECHANICS that produce a RaySearchError in the first place (blind view
# rejected, every-view-blind, template excluded) are exercised once,
# generically, in tests/test_ray_search.py -- not repeated here.


def test_a_view_that_can_see_the_footing_is_used(monkeypatch):
    ftg = footing()
    plain = FakeView3D("{3D}")
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS", [plain])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS",
                        [(only_if_the_ray_meets_the_footing(ftg), None)])
    assert find_search_view(None, ftg) is plain


def test_no_view_can_see_the_footing_is_a_FootingHostError_not_a_bare_RaySearchError(
        monkeypatch):
    """The translation this module adds: ``ray_search`` raises its own
    generic ``RaySearchError``, and no caller of ``footing_host`` should
    ever see that type -- only ``FootingHostError``, with this module's
    own footing-specific wording.
    """
    ftg = footing()
    monkeypatch.setattr(
        FakeFilteredElementCollector, "_ITEMS",
        [FakeView3D("Analytical Model", blind=True),
         FakeView3D("{3D}", blind=True)])
    monkeypatch.setattr(FakeReferenceIntersector, "HITS", [])
    with pytest.raises(FootingHostError) as caught:
        find_search_view(None, ftg)
    message = str(caught.value)
    assert "the selected footing" in message
    assert "Analytical Model" in message and "{3D}" in message


# --------------------------------------------------------------------- #
# read_dowel_column_section_mm (#221) -- thin wiring only. The three
# reused functions' own MECHANICS (b/h-from-type-parameters, the
# flip/cover refusals) are already tested where ColumnRFT built them, in
# test_column_mock_adapter.py -- per this ticket's own "Test volume rule",
# not repeated here. This only proves the call site: it returns the right
# (Cw_mm, Cd_mm, Ccover_mm) tuple, and each of the three refusals still
# reaches the caller unchanged.

COVER_ID = 112574


def _column_above(**kwargs):
    cover = FakeRebarCoverType(mm(40.0), name="Interior (framing, columns)",
                               id_value=COVER_ID)
    document = FakeDocument({COVER_ID: cover})
    parameters = {
        FakeBuiltInParameter.CLEAR_COVER_OTHER:
            FakeElementIdParameter(FakeElementId(COVER_ID)),
    }
    parameters.update(kwargs.pop("parameters", {}))
    return FakeColumn(document=document, parameters=parameters, **kwargs)


def test_returns_the_dowel_column_section_from_the_live_reads():
    """Cw/Cd map straight onto the type's b/h (#69: b along
    HandOrientation, h along FacingOrientation) -- FakeColumn's own default
    section is 450 x 600.
    """
    section = read_dowel_column_section_mm(_column_above())
    assert section == DowelColumnSection(
        Cw_mm=pytest.approx(450.0), Cd_mm=pytest.approx(600.0),
        Ccover_mm=pytest.approx(40.0))


def test_a_flipped_column_refuses_with_column_hosts_own_message():
    """R7's own ruling: propagate the existing refusal as-is, write none
    of its own.
    """
    with pytest.raises(ColumnHostError) as caught:
        read_dowel_column_section_mm(_column_above(mirrored=True))
    assert "mirrored" in str(caught.value)


def test_an_unset_cover_refuses_with_column_hosts_own_message():
    with pytest.raises(ColumnHostError) as caught:
        read_dowel_column_section_mm(_column_above(parameters={
            FakeBuiltInParameter.CLEAR_COVER_OTHER:
                FakeElementIdParameter(None),
        }))
    assert "Rebar Cover - Other Faces" in str(caught.value)


# --------------------------------------------------------------------- #
# read_footing_geometry_mm (#228) -- parameter names/values and refusal
# wording only. The TYPE-parameter-read and cover-read MECHANICS
# themselves are the same shape already proven for ColumnRFT
# (column_host.read_section_mm/read_cover_mm), per this ticket's own
# "Test volume rule".

FOOTING_COVER_ID = 998877


class _FakeFootingGeometryHost(object):
    """Only what ``read_footing_geometry_mm`` reads: ``Symbol`` (TYPE
    dimensions), ``get_Parameter`` (INSTANCE covers), ``Document`` (to
    resolve a cover parameter's ``ElementId`` to a ``RebarCoverType``) and,
    since #249, ``get_BoundingBox`` (to measure which world axis Length/
    Width actually runs along)."""

    def __init__(self, document, symbol, cover_parameters, box):
        self.Document = document
        self.Symbol = symbol
        self._cover_parameters = dict(cover_parameters)
        self._box = box

    def get_Parameter(self, built_in):
        return self._cover_parameters.get(built_in)

    def get_BoundingBox(self, _view):
        return self._box


def _footing_with_geometry(missing_type_param=None, missing_cover_param=None,
                           unset_cover_param=None, x_extent_mm=1800.0,
                           y_extent_mm=1200.0, length_mm=1800.0,
                           width_mm=1200.0):
    document = FakeDocument({
        FOOTING_COVER_ID: FakeRebarCoverType(
            mm(40.0), name="Interior (framing, columns)",
            id_value=FOOTING_COVER_ID),
    })

    type_params = {
        FakeBuiltInParameter.STRUCTURAL_FOUNDATION_LENGTH:
            FakeDoubleParameter(mm(length_mm)),
        FakeBuiltInParameter.STRUCTURAL_FOUNDATION_WIDTH:
            FakeDoubleParameter(mm(width_mm)),
        FakeBuiltInParameter.STRUCTURAL_FOUNDATION_THICKNESS:
            FakeDoubleParameter(mm(450.0)),
    }
    if missing_type_param is not None:
        del type_params[missing_type_param]
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular",
        built_in_parameters=type_params)

    cover_params = {
        FakeBuiltInParameter.CLEAR_COVER_OTHER:
            FakeElementIdParameter(FakeElementId(FOOTING_COVER_ID)),
        FakeBuiltInParameter.CLEAR_COVER_BOTTOM:
            FakeElementIdParameter(FakeElementId(FOOTING_COVER_ID)),
        FakeBuiltInParameter.CLEAR_COVER_TOP:
            FakeElementIdParameter(FakeElementId(FOOTING_COVER_ID)),
    }
    if missing_cover_param is not None:
        del cover_params[missing_cover_param]
    if unset_cover_param is not None:
        cover_params[unset_cover_param] = FakeElementIdParameter(None)

    box = FakeBoundingBox(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm(x_extent_mm), mm(y_extent_mm), mm(450.0)))

    return _FakeFootingGeometryHost(document, symbol, cover_params, box)


def test_returns_the_footing_geometry_from_the_live_reads():
    """Same-as-before case (#249): the measured bounding box agrees with
    the naive Length=X/Width=Y assumption, so a_mm/b_mm come out unchanged.
    """
    geometry = read_footing_geometry_mm(_footing_with_geometry())
    assert geometry == FootingGeometry(
        a_mm=pytest.approx(1800.0), b_mm=pytest.approx(1200.0),
        footing_thickness_mm=pytest.approx(450.0),
        cover_mm=pytest.approx(40.0), bottom_cover_mm=pytest.approx(40.0),
        top_cover_mm=pytest.approx(40.0))


def test_derives_a_mm_from_the_measured_extent_when_length_runs_along_y():
    """#249's own bug: a footing whose Length (1800) actually runs along
    world Y and Width (1200) along world X -- a_mm must come out as the
    dimension that MATCHES the measured X-extent (1200), not the type's
    Length value blindly.
    """
    geometry = read_footing_geometry_mm(
        _footing_with_geometry(x_extent_mm=1200.0, y_extent_mm=1800.0))
    assert geometry.a_mm == pytest.approx(1200.0)
    assert geometry.b_mm == pytest.approx(1800.0)


def test_neither_dimension_matches_the_measured_extents_refuses():
    with pytest.raises(FootingAxisMismatchError) as caught:
        read_footing_geometry_mm(
            _footing_with_geometry(x_extent_mm=900.0, y_extent_mm=900.0))
    message = str(caught.value)
    assert "900.0" in message
    assert "1800.0" in message and "1200.0" in message


def test_a_near_square_footing_refuses_instead_of_picking_the_first_match():
    """Review finding on #249's first draft: Length (1201.0) and Width
    (1199.5) are close enough to each other that, for a footing whose
    real bounding box measures X=1199.5/Y=1201.0 (Width actually runs
    along X), BOTH possible assignments land within
    ``_AXIS_MATCH_TOLERANCE_MM`` of the measured extents. Picking
    "whichever of Length/Width is checked first" would have silently
    returned the WRONG assignment here (Length=X) instead of refusing --
    this must refuse as ambiguous, not guess.
    """
    with pytest.raises(FootingAxisMismatchError) as caught:
        read_footing_geometry_mm(
            _footing_with_geometry(
                length_mm=1201.0, width_mm=1199.5,
                x_extent_mm=1199.5, y_extent_mm=1201.0))
    message = str(caught.value)
    assert "1201.0" in message and "1199.5" in message


def test_a_missing_type_dimension_refuses_naming_the_parameter():
    footing = _footing_with_geometry(
        missing_type_param=FakeBuiltInParameter.STRUCTURAL_FOUNDATION_WIDTH)
    with pytest.raises(FootingHostError) as caught:
        read_footing_geometry_mm(footing)
    assert "Width" in str(caught.value)


def test_a_missing_cover_parameter_refuses_naming_the_parameter():
    footing = _footing_with_geometry(
        missing_cover_param=FakeBuiltInParameter.CLEAR_COVER_BOTTOM)
    with pytest.raises(FootingHostError) as caught:
        read_footing_geometry_mm(footing)
    assert "Rebar Cover - Bottom Face" in str(caught.value)


def test_an_unset_cover_parameter_refuses_naming_the_parameter():
    footing = _footing_with_geometry(
        unset_cover_param=FakeBuiltInParameter.CLEAR_COVER_TOP)
    with pytest.raises(FootingHostError) as caught:
        read_footing_geometry_mm(footing)
    assert "Rebar Cover - Top Face" in str(caught.value)
