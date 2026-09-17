# -*- coding: utf-8 -*-
"""#133 -- the yield strength shown beside every type, and the T filter.

The owner's ruling, with its cost stated in
``rft.core.grades.is_high_tensile_by_name``: the LONGITUDINAL picker takes
T-named types only, the TIE picker takes everything, and every label
carries the type's own ``fy`` because the name guarantees nothing about it.

Why the name and not the number: in the verification model every bar type
resolves to **420 MPa**. The ``M`` types are ASTM A615M Grade 420, where
the M is the METRIC bar designation, not "mild". Filtering on yield
strength would separate nothing, because nothing differs.
"""

import pytest

from fake_revit_api import (

    FakeDocument,
    FakeElementId,
    FakeFilteredElementCollector,
    FakeMaterial,
    FakePropertySetElement,
    FakeRebarBarType,
    FakeStructuralAsset,
    FakeUnitTypeId,
    FakeUnitUtils,
)

from rft.core.grades import is_high_tensile_by_name
from rft.revit.bar_types import bar_type_options, bar_type_yield_mpa

#: Grade 420 in Revit's internal stress units -- 420 * 304800, the factor
#: measured against the live model.
GRADE_420_INTERNAL = 420.0 * 304800.0


def _document_with_grade_420():
    """A document whose material chain resolves, plus the ids to hang bar
    types off."""
    asset_id = FakeElementId(9001)
    material_id = FakeElementId(9002)
    # FakeDocument keys on IntegerValue, not the id object.
    return material_id, FakeDocument({
        material_id.IntegerValue: FakeMaterial(
            structural_asset_id=asset_id,
            name="Rebar - ASTM A615M - Grade 420"),
        asset_id.IntegerValue: FakePropertySetElement(
            FakeStructuralAsset(GRADE_420_INTERNAL)),
    })


# --------------------------------------------------------------------- #
# The policy, pure


def test_the_T_suffix_is_what_marks_a_type_high_tensile():
    assert is_high_tensile_by_name("16T")
    assert is_high_tensile_by_name("10t"), "case must not matter"
    assert is_high_tensile_by_name("  12T  "), "surrounding space must not"
    assert not is_high_tensile_by_name("16M")
    assert not is_high_tensile_by_name("")
    assert not is_high_tensile_by_name(None)


def test_a_420_MPa_M_type_is_still_NOT_high_tensile_by_this_rule():
    """The cost of the owner's ruling, asserted rather than left implicit.

    ``16M`` in the verification model is ASTM A615M Grade 420 -- the same
    steel as ``16T``. This rule hides it from the longitudinal picker for
    a reason that is typographic, and that is the accepted trade: the
    letter chooses the list, the number is shown beside it.
    """
    assert not is_high_tensile_by_name("16M")


# --------------------------------------------------------------------- #
# The yield strength, read through the live chain


def test_the_yield_strength_is_read_through_the_material(monkeypatch):
    material_id, document = _document_with_grade_420()
    bar_type = FakeRebarBarType(bar_nominal_diameter=16.0, name="16T",
                                material_id=material_id)
    assert bar_type_yield_mpa(bar_type, document) == pytest.approx(420.0)


def test_a_type_with_NO_material_reports_unknown_not_a_default():
    """10T and 14T are like this in the live model. Substituting 420
    because it is the common value would be exactly the plausible guess
    this project refuses everywhere else."""
    _material_id, document = _document_with_grade_420()
    bar_type = FakeRebarBarType(bar_nominal_diameter=10.0, name="10T")
    assert bar_type_yield_mpa(bar_type, document) is None


def test_a_material_with_no_structural_asset_reports_unknown():
    material_id = FakeElementId(9002)
    document = FakeDocument(
        {material_id.IntegerValue: FakeMaterial(None, "Paint")})
    bar_type = FakeRebarBarType(bar_nominal_diameter=16.0, name="16T",
                                material_id=material_id)
    assert bar_type_yield_mpa(bar_type, document) is None


def test_megapascals_and_millimetres_do_not_convert_the_same_way():
    """Guards the fake itself. It used to ignore the unit argument, so a
    yield strength came back as a length and no test could see it."""
    assert FakeUnitUtils.ConvertFromInternalUnits(
        GRADE_420_INTERNAL, FakeUnitTypeId.Megapascals) == pytest.approx(420.0)
    assert FakeUnitUtils.ConvertFromInternalUnits(
        1.0, FakeUnitTypeId.Millimeters) == pytest.approx(304.8)


# --------------------------------------------------------------------- #
# The pickers


def _three_types(material_id):
    return [
        FakeRebarBarType(bar_nominal_diameter=15.9, name="16M",
                         material_id=material_id),
        FakeRebarBarType(bar_nominal_diameter=16.0, name="16T",
                         material_id=material_id),
        FakeRebarBarType(bar_nominal_diameter=10.0, name="10T"),
    ]


def test_every_label_carries_the_yield_strength(monkeypatch):
    material_id, document = _document_with_grade_420()
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        _three_types(material_id))

    labels = [label for label, _t in bar_type_options(
        document, from_internal_units=lambda v: v)]
    assert labels == [
        "10T  --  10.0 mm  --  fy unknown",
        "16M  --  15.9 mm  --  420 MPa",
        "16T  --  16.0 mm  --  420 MPa",
    ]


def test_the_longitudinal_list_takes_T_types_only(monkeypatch):
    material_id, document = _document_with_grade_420()
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        _three_types(material_id))

    names = [label.split("  --  ")[0] for label, _t in bar_type_options(
        document, from_internal_units=lambda v: v, high_tensile_only=True)]
    assert names == ["10T", "16T"], (
        "the 420 MPa 16M is hidden -- that is the ruling, and the fy shown "
        "beside the survivors is what makes it visible")


def test_the_tie_list_hides_nothing(monkeypatch):
    """Mild is PERMITTED for a tie, not required, so the tie picker is
    unfiltered -- and in this project filtering it to mild would empty it,
    since there is no fy 240 material at all."""
    material_id, document = _document_with_grade_420()
    monkeypatch.setattr(FakeFilteredElementCollector, "_ITEMS",
                        _three_types(material_id))

    assert len(bar_type_options(document, from_internal_units=lambda v: v)) == 3


def test_an_unknown_fy_type_is_still_OFFERED_for_the_longitudinal_role():
    """10T has no material. It is T-named, so the ruling admits it; the
    label says ``fy unknown`` so the engineer sees what they are taking
    on. Hiding it would be the tool making the call."""
    material_id, document = _document_with_grade_420()
    types = _three_types(material_id)
    FakeFilteredElementCollector._ITEMS = types
    try:
        labels = [label for label, _t in bar_type_options(
            document, from_internal_units=lambda v: v, high_tensile_only=True)]
    finally:
        FakeFilteredElementCollector._ITEMS = []
    assert "10T  --  10.0 mm  --  fy unknown" in labels
