# -*- coding: utf-8 -*-
"""Issue #226 -- specs/isolated-footing-batch.md: mock-object verification
of ``rft.revit.footing_batch``, the ORCHESTRATION around collect/read/
group/plan/refuse/place -- mirrors tests/test_column_batch.py's own
adapter section, same reasoning that file states for why ``read_column``
(here: ``find_column_above``/``read_dowel_column_section_mm``/
``read_footing_geometry_mm``) is monkeypatched to canned reads rather
than driven through the full ray-cast machinery: those functions' OWN
correctness is ``test_footing_revit_host.py``'s job, and driving them
through a shared ``FakeFilteredElementCollector._ITEMS`` list here would
collide with the SAME list ``collect_candidates`` needs for its own
footing collection.

Per this ticket's own "Test volume rule" spirit (nothing in the ticket
body states one explicitly, but every other footing ticket this session
has): this file does not re-test ``build_footing_plan``'s own core math
(``tests/test_footing_plan.py``) or ``place_straight_bottom_mesh``/
``place_dowel_bars``'s own placement mechanics (``tests/
test_footing_revit_mesh.py``/``test_footing_revit_dowels.py``) -- only
the batch orchestration layered on top of them.
"""

import pytest

from fake_revit_api import (
    FakeBoundingBox,
    FakeBuiltInCategory,
    FakeColumn,
    FakeDocument,
    FakeElementId,
    FakeFamilySymbol,
    FakeFilteredElementCollector,
    FakeRebarBarType,
    FakeRebarElement,
    FakeXYZ,
)

import rft.revit.footing_batch as footing_batch_module
from rft.core.footing_batch import Exclusion
from rft.core.footing_plan import (
    TOP_REINFORCEMENT_TOP_AND_BTM,
    DowelColumnSection,
    FootingInputs,
    build_footing_plan,
)
from rft.revit.column_host import ColumnHostError
from rft.revit.footing_batch import (
    BatchInputs, BatchPlan, FootingBatchError, FootingCandidate,
    apply_batch, collect_candidates, plan_candidates, read_candidates,
    read_existing,
)
from rft.revit.footing_host import FootingGeometry, FootingHostError
from rft.revit.footing_ownership import partition_tag

FT = 304.8


def mm(value):
    return value / FT


@pytest.fixture(autouse=True)
def _clear_collector_items():
    FakeFilteredElementCollector._ITEMS = []
    yield
    FakeFilteredElementCollector._ITEMS = []


class _FakeLocation(object):
    def __init__(self, rotation_rad):
        self.Rotation = rotation_rad


class _FakeFootingElement(object):
    """Only what ``footing_batch`` and the mesh/dowel adapters read:
    ``Symbol``/``Id`` (the type filter and identity), ``get_BoundingBox``/
    ``Location.Rotation`` (``footing_mesh._footing_origin``), and
    ``_category`` (``FakeFilteredElementCollector.OfCategory``)."""

    def __init__(self, element_id, symbol=None, rotation_rad=0.0):
        self.Id = FakeElementId(element_id)
        self.Symbol = symbol if symbol is not None else FakeFamilySymbol(
            "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
        self.Location = _FakeLocation(rotation_rad)
        self._box = FakeBoundingBox(
            FakeXYZ(0.0, 0.0, 0.0),
            FakeXYZ(mm(1800.0), mm(1200.0), mm(450.0)))
        self._category = FakeBuiltInCategory.OST_StructuralFoundation

    def get_BoundingBox(self, _view):
        return self._box


def _geometry(a_mm=1800.0, b_mm=1200.0, footing_thickness_mm=450.0):
    return FootingGeometry(
        a_mm=a_mm, b_mm=b_mm, footing_thickness_mm=footing_thickness_mm,
        cover_mm=50.0, bottom_cover_mm=50.0, top_cover_mm=50.0)


def _column_section(cw_mm=300.0, cd_mm=600.0, ccover_mm=40.0):
    return DowelColumnSection(Cw_mm=cw_mm, Cd_mm=cd_mm, Ccover_mm=ccover_mm)


def _plan(cw_mm=300.0, cd_mm=600.0, ccover_mm=40.0):
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=20.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=3)
    return build_footing_plan(
        inputs, column_section=_column_section(cw_mm, cd_mm, ccover_mm))


def _shared_inputs():
    return BatchInputs(
        x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=40.0,
        bar_x_type=FakeRebarBarType(bar_nominal_diameter=mm(16.0)),
        bar_y_type=FakeRebarBarType(bar_nominal_diameter=mm(12.0)),
        dowel_bar_type=FakeRebarBarType(bar_nominal_diameter=mm(25.0)),
        dowel_tie_bar_type=FakeRebarBarType(bar_nominal_diameter=mm(10.0)),
        dowel_ld_multiplier=20.0, dowel_count_b_face=3,
        dowel_count_h_face=3)


def _install_reads(monkeypatch, column_by_footing_id, section_by_footing_id,
                   geometry_by_footing_id):
    """Stand in for ``find_column_above``/``read_dowel_column_section_mm``/
    ``read_footing_geometry_mm``, each keyed by the FOOTING's own element
    id -- see the module docstring for why these are not driven through
    the fake's own ray-cast machinery here."""
    def fake_find_column_above(_doc, footing):
        result = column_by_footing_id[footing.Id.IntegerValue]
        if isinstance(result, Exception):
            raise result
        return result

    def fake_read_dowel_column_section_mm(column):
        result = section_by_footing_id[column._for_footing_id]
        if isinstance(result, Exception):
            raise result
        return result

    def fake_read_footing_geometry_mm(footing):
        result = geometry_by_footing_id[footing.Id.IntegerValue]
        if isinstance(result, Exception):
            raise result
        return result

    monkeypatch.setattr(footing_batch_module, "find_column_above",
                        fake_find_column_above)
    monkeypatch.setattr(footing_batch_module,
                        "read_dowel_column_section_mm",
                        fake_read_dowel_column_section_mm)
    monkeypatch.setattr(footing_batch_module, "read_footing_geometry_mm",
                        fake_read_footing_geometry_mm)


def _column_for(footing_id, symbol):
    """A fake column stand-in, tagged with the footing id it was
    "detected above" so ``fake_read_dowel_column_section_mm`` can look up
    the matching canned section -- ``read_dowel_column_section_mm`` in
    real life takes only the column, but this fake needs the extra
    context since one test may install several distinct columns."""
    column = FakeColumn(symbol=symbol, element_id=900000 + footing_id)
    column._for_footing_id = footing_id
    return column


# ----------------------------------------------------------------- #
# collect_candidates: the FOOTING type is the filter


def test_collect_candidates_matches_only_the_same_footing_family_type():
    shared_symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    other_symbol = FakeFamilySymbol(
        "2000 x 1500 x 500mm", family_name="M_Footing-Rectangular")
    picked = _FakeFootingElement(1, symbol=shared_symbol)
    same_type = _FakeFootingElement(2, symbol=shared_symbol)
    different_type = _FakeFootingElement(3, symbol=other_symbol)
    FakeFilteredElementCollector._ITEMS = [picked, same_type, different_type]

    candidates = collect_candidates(FakeDocument({}), picked)

    assert set(c.Id.IntegerValue for c in candidates) == {1, 2}


def test_collect_candidates_includes_the_picked_footing_itself():
    shared_symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    picked = _FakeFootingElement(1, symbol=shared_symbol)
    FakeFilteredElementCollector._ITEMS = [picked]

    candidates = collect_candidates(FakeDocument({}), picked)

    assert [c.Id.IntegerValue for c in candidates] == [1]


# ----------------------------------------------------------------- #
# read_candidates: #220/#221/#228 refusals AND a column-type mismatch


def test_read_candidates_excludes_a_no_column_refusal_and_keeps_its_reason(
        monkeypatch):
    symbol = FakeFamilySymbol("450 x 600mm")
    ftg_ok = _FakeFootingElement(1)
    ftg_bad = _FakeFootingElement(2)
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, symbol),
            2: FootingHostError("No column is attached to this footing."),
        },
        section_by_footing_id={1: _column_section()},
        geometry_by_footing_id={1: _geometry()})

    reads, exclusions = read_candidates(
        FakeDocument({}), [ftg_ok, ftg_bad], symbol.Id)

    assert [element.Id.IntegerValue for element, _g, _cs in reads] == [1]
    assert len(exclusions) == 1
    assert exclusions[0].element_id == 2
    assert "No column is attached" in exclusions[0].reason


def test_read_candidates_excludes_a_mismatched_column_type_with_its_own_reason(
        monkeypatch):
    host_column_symbol = FakeFamilySymbol("450 x 600mm")
    other_column_symbol = FakeFamilySymbol("300 x 300mm")
    ftg_match = _FakeFootingElement(1)
    ftg_mismatch = _FakeFootingElement(2)
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, host_column_symbol),
            2: _column_for(2, other_column_symbol),
        },
        section_by_footing_id={1: _column_section(), 2: _column_section()},
        geometry_by_footing_id={1: _geometry(), 2: _geometry()})

    reads, exclusions = read_candidates(
        FakeDocument({}), [ftg_match, ftg_mismatch], host_column_symbol.Id)

    assert [element.Id.IntegerValue for element, _g, _cs in reads] == [1]
    assert len(exclusions) == 1
    assert exclusions[0].element_id == 2
    assert "different family type" in exclusions[0].reason


def test_read_candidates_excludes_a_column_section_refusal(monkeypatch):
    symbol = FakeFamilySymbol("450 x 600mm")
    ftg_ok = _FakeFootingElement(1)
    ftg_bad = _FakeFootingElement(2)
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, symbol), 2: _column_for(2, symbol)},
        section_by_footing_id={
            1: _column_section(),
            2: ColumnHostError("This column is mirrored."),
        },
        geometry_by_footing_id={1: _geometry(), 2: _geometry()})

    reads, exclusions = read_candidates(
        FakeDocument({}), [ftg_ok, ftg_bad], symbol.Id)

    assert [element.Id.IntegerValue for element, _g, _cs in reads] == [1]
    assert exclusions[0].element_id == 2
    assert "mirrored" in exclusions[0].reason


def test_read_candidates_excludes_a_footing_geometry_refusal(monkeypatch):
    symbol = FakeFamilySymbol("450 x 600mm")
    ftg_ok = _FakeFootingElement(1)
    ftg_bad = _FakeFootingElement(2)
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, symbol), 2: _column_for(2, symbol)},
        section_by_footing_id={1: _column_section(), 2: _column_section()},
        geometry_by_footing_id={
            1: _geometry(),
            2: FootingHostError("This footing's 'Width' is not set."),
        })

    reads, exclusions = read_candidates(
        FakeDocument({}), [ftg_ok, ftg_bad], symbol.Id)

    assert [element.Id.IntegerValue for element, _g, _cs in reads] == [1]
    assert exclusions[0].element_id == 2
    assert "'Width' is not set" in exclusions[0].reason


# ----------------------------------------------------------------- #
# plan_candidates: read/group (Sec 3, R9), plan and refuse (Sec 5)


def test_plan_candidates_groups_by_the_live_read_tuple_and_builds_a_plan_per_survivor(
        monkeypatch):
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    ftg_a = _FakeFootingElement(1, symbol=symbol)
    ftg_b = _FakeFootingElement(2, symbol=symbol)
    FakeFilteredElementCollector._ITEMS = [ftg_a, ftg_b]
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, symbol), 2: _column_for(2, symbol)},
        section_by_footing_id={
            1: _column_section(cw_mm=300.0),
            2: _column_section(cw_mm=350.0),
        },
        geometry_by_footing_id={1: _geometry(), 2: _geometry()})

    result = plan_candidates(FakeDocument({}), ftg_a, _shared_inputs())

    assert isinstance(result, BatchPlan)
    assert result.exclusions == []
    assert len(result.candidates) == 2
    assert len(result.groups) == 2
    plan_a, plan_b = (c.plan for c in result.candidates)
    assert plan_a.dowel.bars != plan_b.dowel.bars


def test_plan_candidates_threads_the_shared_splice_length_to_every_survivor(
        monkeypatch):
    """R12 (issue #234): ``BatchInputs.dowel_splice_length_mm`` (the SAME
    shared value the engineer states once, per ``BatchInputs``' own
    docstring) must reach every candidate's own ``FootingInputs`` -- never
    silently dropped back to ``None`` for a batch run."""
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    ftg_a = _FakeFootingElement(1, symbol=symbol)
    FakeFilteredElementCollector._ITEMS = [ftg_a]
    _install_reads(
        monkeypatch,
        column_by_footing_id={1: _column_for(1, symbol)},
        section_by_footing_id={1: _column_section()},
        geometry_by_footing_id={1: _geometry()})

    shared_inputs = _shared_inputs()._replace(dowel_splice_length_mm=600.0)
    result = plan_candidates(FakeDocument({}), ftg_a, shared_inputs)

    assert len(result.candidates) == 1
    plan = result.candidates[0].plan
    assert plan.inputs.dowel_splice_length_mm == 600.0
    assert plan.dowel.bars[0].vertical.end.z_mm == pytest.approx(
        plan.inputs.footing_thickness_mm + 600.0)


def test_plan_candidates_threads_the_shared_top_reinforcement_choice(
        monkeypatch):
    """#233 (R13): ``BatchInputs.top_reinforcement``/``top_mat_shape_mode``
    (the SAME shared value the engineer states once) must reach every
    candidate's own ``FootingInputs`` -- never silently reverted to
    BTM-only for a batch run."""
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    ftg_a = _FakeFootingElement(1, symbol=symbol)
    FakeFilteredElementCollector._ITEMS = [ftg_a]
    _install_reads(
        monkeypatch,
        column_by_footing_id={1: _column_for(1, symbol)},
        section_by_footing_id={1: _column_section()},
        geometry_by_footing_id={1: _geometry()})

    shared_inputs = _shared_inputs()._replace(
        top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM,
        # #253 (R16): the top mat's own bar types are REQUIRED once
        # TOP+BTM is chosen -- never inferred from bar_x_type/bar_y_type.
        top_mesh_bar_x_type=FakeRebarBarType(bar_nominal_diameter=mm(16.0)),
        top_mesh_bar_y_type=FakeRebarBarType(bar_nominal_diameter=mm(12.0)))
    result = plan_candidates(FakeDocument({}), ftg_a, shared_inputs)

    assert len(result.candidates) == 1
    plan = result.candidates[0].plan
    assert plan.inputs.top_reinforcement == TOP_REINFORCEMENT_TOP_AND_BTM
    assert plan.top_mesh is not None


def test_plan_candidates_threads_the_shared_perimeter_tie_inputs(
        monkeypatch):
    """#244 (R14): ``BatchInputs.perimeter_tie_bar_type``/``_spacing_mm``/
    ``_quantity`` must reach every candidate's own ``FootingInputs`` --
    never silently dropped back to no `perimeter_tie` for a batch run."""
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    ftg_a = _FakeFootingElement(1, symbol=symbol)
    FakeFilteredElementCollector._ITEMS = [ftg_a]
    _install_reads(
        monkeypatch,
        column_by_footing_id={1: _column_for(1, symbol)},
        section_by_footing_id={1: _column_section()},
        geometry_by_footing_id={1: _geometry()})

    shared_inputs = _shared_inputs()._replace(
        perimeter_tie_bar_type=FakeRebarBarType(bar_nominal_diameter=mm(10.0)),
        perimeter_tie_spacing_mm=50.0, perimeter_tie_quantity=1)
    result = plan_candidates(FakeDocument({}), ftg_a, shared_inputs)

    assert len(result.candidates) == 1
    plan = result.candidates[0].plan
    assert plan.perimeter_tie is not None
    assert plan.perimeter_tie.dia_mm == pytest.approx(10.0)
    assert plan.perimeter_tie.spacing_mm == pytest.approx(50.0)
    assert plan.perimeter_tie.quantity == 1


def test_plan_candidates_excludes_a_find_column_above_refusal_before_planning(
        monkeypatch):
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    ftg_a = _FakeFootingElement(1, symbol=symbol)
    ftg_b = _FakeFootingElement(2, symbol=symbol)
    FakeFilteredElementCollector._ITEMS = [ftg_a, ftg_b]
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, symbol),
            2: FootingHostError("No column is attached to this footing."),
        },
        section_by_footing_id={1: _column_section()},
        geometry_by_footing_id={1: _geometry()})

    result = plan_candidates(FakeDocument({}), ftg_a, _shared_inputs())

    assert [c.element.Id.IntegerValue for c in result.candidates] == [1]
    assert len(result.exclusions) == 1
    assert result.exclusions[0].element_id == 2
    # Excluded BEFORE grouping ever runs on it.
    assert len(result.groups) == 1


def test_plan_candidates_excludes_a_footing_build_footing_plan_refuses(
        monkeypatch):
    """The dowel-array layout ValueError path (spec Sec 5) -- a column
    section too small for the shared count-per-face inputs to fit."""
    symbol = FakeFamilySymbol(
        "1800 x 1200 x 450mm", family_name="M_Footing-Rectangular")
    ftg_a = _FakeFootingElement(1, symbol=symbol)
    ftg_b = _FakeFootingElement(2, symbol=symbol)
    FakeFilteredElementCollector._ITEMS = [ftg_a, ftg_b]
    _install_reads(
        monkeypatch,
        column_by_footing_id={
            1: _column_for(1, symbol), 2: _column_for(2, symbol)},
        section_by_footing_id={
            1: _column_section(),
            # A tiny section -- cover + tie + half bar leaves no room.
            2: _column_section(cw_mm=10.0, cd_mm=10.0, ccover_mm=40.0),
        },
        geometry_by_footing_id={1: _geometry(), 2: _geometry()})

    result = plan_candidates(FakeDocument({}), ftg_a, _shared_inputs())

    assert [c.element.Id.IntegerValue for c in result.candidates] == [1]
    assert len(result.exclusions) == 1
    assert result.exclusions[0].element_id == 2


# ----------------------------------------------------------------- #
# apply_batch: ONE transaction, all-or-nothing


def _candidate(element_id, cw_mm=300.0):
    element = _FakeFootingElement(element_id)
    return FootingCandidate(
        element=element, geometry=_geometry(),
        column_section=_column_section(cw_mm=cw_mm),
        plan=_plan(cw_mm=cw_mm))


def _plan_with_top_mesh(cw_mm=300.0, cd_mm=600.0, ccover_mm=40.0):
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=20.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=3,
        top_reinforcement=TOP_REINFORCEMENT_TOP_AND_BTM,
        # #253 (R16): the top mat's own bar diameters are REQUIRED once
        # TOP+BTM is chosen.
        top_mesh_bar_x_dia_mm=16.0, top_mesh_bar_y_dia_mm=12.0)
    return build_footing_plan(
        inputs, column_section=_column_section(cw_mm, cd_mm, ccover_mm))


def _candidate_with_top_mesh(element_id, cw_mm=300.0):
    element = _FakeFootingElement(element_id)
    return FootingCandidate(
        element=element, geometry=_geometry(),
        column_section=_column_section(cw_mm=cw_mm),
        plan=_plan_with_top_mesh(cw_mm=cw_mm))


def test_apply_batch_refuses_the_whole_run_without_opening_a_transaction():
    doc = FakeDocument({})
    empty_batch = BatchPlan(groups=[], exclusions=[
        Exclusion(element_id=1, reason="out of scope")], candidates=[])

    with pytest.raises(FootingBatchError):
        apply_batch(doc, empty_batch, object(), object(), object())

    assert doc.deleted_ids == []


def test_apply_batch_places_every_candidate_and_tags_it_with_its_own_host_id():
    doc = FakeDocument({})
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[_candidate(101), _candidate(102)])

    read_existing(doc, batch)
    result = apply_batch(doc, batch, object(), object(), object())

    ids = [element_id for element_id, _result in result.per_footing]
    assert ids == [101, 102]
    for element_id, placement in result.per_footing:
        assert placement.dowel_bars
        for rebar in (list(placement.bars_x) + list(placement.bars_y)
                     + list(placement.dowel_bars)):
            assert rebar.LookupParameter("Partition").AsString() == (
                partition_tag(element_id))


def test_a_failure_placing_one_footing_rolls_back_the_WHOLE_batch(
        monkeypatch):
    """The batch equivalent of R25 extended: the first candidate's OWN
    existing bar is deleted, the second candidate's dowel placement then
    blows up, and the rollback must restore the FIRST candidate's bar too
    -- proof both footings share one transaction rather than one each."""
    footing_1 = _FakeFootingElement(201)
    old_bar = FakeRebarElement(host_id=footing_1.Id, id_value=900,
                              partition=partition_tag(201))
    FakeFilteredElementCollector._ITEMS = [old_bar]
    doc = FakeDocument({})

    candidate_1 = _candidate(201)
    candidate_1.element = footing_1
    candidate_2 = _candidate(202)
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[candidate_1, candidate_2])

    call_count = [0]
    real_place_dowel_bars = footing_batch_module.place_dowel_bars

    def _boom(doc_, element, dowel_plan, bar_type):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("second footing's dowels blew up")
        return real_place_dowel_bars(doc_, element, dowel_plan, bar_type)

    monkeypatch.setattr(footing_batch_module, "place_dowel_bars", _boom)
    read_existing(doc, batch)

    with pytest.raises(RuntimeError, match="second footing's dowels"):
        apply_batch(doc, batch, object(), object(), object())

    remaining_ids = set(
        item.Id.IntegerValue for item in FakeFilteredElementCollector._ITEMS)
    assert 900 in remaining_ids


def test_apply_batch_places_the_top_mesh_when_the_plan_carries_one():
    """#233 (R13): a candidate whose OWN plan carries a top_mesh gets its
    top mat placed inside the SAME transaction, tagged like every other
    bar this run places -- and a candidate with no top_mesh (BTM-only, the
    default) places none, unchanged."""
    doc = FakeDocument({})
    with_top = _candidate_with_top_mesh(501)
    without_top = _candidate(502)
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[with_top, without_top])
    read_existing(doc, batch)

    result = apply_batch(
        doc, batch, object(), object(), object(),
        top_mesh_bar_x_type=object(), top_mesh_bar_y_type=object())

    results_by_id = dict(result.per_footing)
    assert results_by_id[501].top_bar_x is not None
    assert results_by_id[501].top_bar_y is not None
    assert results_by_id[502].top_bar_x is None
    assert results_by_id[502].top_bar_y is None
    assert results_by_id[501].top_bar_x.LookupParameter(
        "Partition").AsString() == partition_tag(501)


def _plan_with_perimeter_tie(cw_mm=300.0, cd_mm=600.0, ccover_mm=40.0):
    inputs = FootingInputs(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=1500.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0, dowel_bar_dia_mm=25.0, dowel_ld_multiplier=20.0,
        dowel_tie_dia_mm=10.0, dowel_count_b_face=3, dowel_count_h_face=3,
        perimeter_tie_dia_mm=10.0, perimeter_tie_spacing_mm=200.0,
        perimeter_tie_quantity=2)
    return build_footing_plan(
        inputs, column_section=_column_section(cw_mm, cd_mm, ccover_mm))


def _candidate_with_perimeter_tie(element_id, cw_mm=300.0):
    element = _FakeFootingElement(element_id)
    element._box = FakeBoundingBox(
        FakeXYZ(0.0, 0.0, 0.0),
        FakeXYZ(mm(1800.0), mm(1200.0), mm(1500.0)))
    return FootingCandidate(
        element=element, geometry=_geometry(footing_thickness_mm=1500.0),
        column_section=_column_section(cw_mm=cw_mm),
        plan=_plan_with_perimeter_tie(cw_mm=cw_mm))


def test_apply_batch_places_the_perimeter_tie_when_the_plan_carries_one():
    """#244 (R14): a candidate whose own plan carries a `perimeter_tie`
    gets its own closed-loop shape placed inside the SAME transaction,
    tagged like every other bar this run places -- a candidate with no
    `perimeter_tie` places none, unchanged."""
    doc = FakeDocument({})
    with_tie = _candidate_with_perimeter_tie(601)
    without_tie = _candidate(602)
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[with_tie, without_tie])
    read_existing(doc, batch)

    result = apply_batch(
        doc, batch, object(), object(), object(),
        perimeter_tie_bar_type=object(),
        perimeter_tie_hook_type=object())

    results_by_id = dict(result.per_footing)
    assert len(results_by_id[601].perimeter_ties) == (
        len(with_tie.plan.perimeter_tie.ladder.levels_mm))
    assert results_by_id[602].perimeter_ties == []
    assert results_by_id[601].perimeter_ties[0].LookupParameter(
        "Partition").AsString() == partition_tag(601)


def test_apply_batch_refuses_when_read_existing_was_never_run():
    batch = BatchPlan(groups=[], exclusions=[], candidates=[_candidate(401)])

    with pytest.raises(FootingBatchError, match="never read"):
        apply_batch(FakeDocument({}), batch, object(), object(), object())


def test_apply_batch_deletes_exactly_what_read_existing_counted():
    footing_element = _FakeFootingElement(302)
    counted = FakeRebarElement(host_id=footing_element.Id, id_value=902,
                              partition=partition_tag(302))
    FakeFilteredElementCollector._ITEMS = [counted]
    candidate = _candidate(302)
    candidate.element = footing_element
    batch = BatchPlan(groups=[], exclusions=[], candidates=[candidate])
    doc = FakeDocument({})

    rows = read_existing(doc, batch)
    assert rows[0].replaced_count == 1
    latecomer = FakeRebarElement(host_id=footing_element.Id, id_value=903,
                                partition=partition_tag(302))
    FakeFilteredElementCollector._ITEMS = [counted, latecomer]

    apply_batch(doc, batch, object(), object(), object())

    assert 902 in [element_id.IntegerValue for element_id in doc.deleted_ids]
    assert 903 not in [element_id.IntegerValue
                      for element_id in doc.deleted_ids]


def test_read_existing_returns_a_row_per_candidate_with_its_own_counts():
    footing_element = _FakeFootingElement(301)
    ours = FakeRebarElement(host_id=footing_element.Id, id_value=901,
                           partition=partition_tag(301))
    FakeFilteredElementCollector._ITEMS = [ours]
    candidate = _candidate(301)
    candidate.element = footing_element
    batch = BatchPlan(groups=[], exclusions=[], candidates=[candidate])

    rows = read_existing(FakeDocument({}), batch)

    assert [row.element_id for row in rows] == [301]
    assert rows[0].replaced_count == 1
    assert candidate.ours and candidate.foreign == []
