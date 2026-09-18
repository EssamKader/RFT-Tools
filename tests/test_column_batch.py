# -*- coding: utf-8 -*-
"""Issue #153 -- specs/column-batch-placement.md and R33
(docs/column/spec-amendments.md): grouping, exclusion, report and the ONE
transaction, exercised against the same real fixtures the single-column
suites use.

Three layers, matching the ticket's own split:

- `rft.core.column_batch` (PURE) -- the grouping key, exercised directly
  with no Revit stand-in at all.
- `rft.core.column_report`'s two new sections -- also pure, values in,
  lines out.
- `rft.revit.column_batch` (the adapter) -- run against
  `tests/fake_revit_api.py`. `read_column` itself is monkeypatched to
  canned host reads rather than driven through the full support-search
  machinery: its OWN correctness is `test_column_mock_adapter.py`'s job,
  and driving it through a shared `FakeFilteredElementCollector._ITEMS`
  list here would collide with the SAME list `collect_candidates` needs
  for its own column collection. What this file proves is the
  ORCHESTRATION around that call -- collect, exclude, group, plan, refuse,
  and place inside one transaction -- against the real
  `FakeDocument`/`FakeTransaction`/`FakeRebar` machinery `test_column_apply
  .py` already trusts for R25's rollback guarantee.
"""

from collections import namedtuple

import pytest

from fake_revit_api import (
    FakeColumn,
    FakeDocument,
    FakeFamilySymbol,
    FakeFilteredElementCollector,
    FakeRebarElement,
)

import rft.revit.column_batch as column_batch_module
from rft.core.column_batch import BatchGroup, Exclusion, GroupKey, group_hosts
from rft.core.column_host_rules import (
    ColumnExtent, SOURCE_LEVEL_ELEVATION, SOURCE_SUPPORT_FACE,
    section_from_dimensions,
)
from rft.core.column_inputs import perimeter_bars
from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_plan import MODE_AUTO, bar_plan, complete_plan
from rft.core.column_batch import BatchExisting
from rft.core.column_report import (
    batch_exclusion_section, batch_group_section, batch_replacement_section,
)
from rft.revit.column_batch import (
    BatchInputs, BatchPlan, ColumnCandidate, apply_batch, collect_candidates,
    plan_candidates, read_candidates, read_existing,
)
from rft.revit.column_host import ColumnHostError
from rft.revit.column_ownership import partition_tag
from rft.revit.column_placer import ColumnPlacementError

FT = 304.8

#: The same fixture values `test_column_plan.py` uses for its own
#: known-NOT-blocked plan (`is_blocked(plan()) is False`) -- reused here
#: rather than re-derived, so a batch candidate's `ColumnPlan` is
#: guaranteed buildable without this file having to work out section 6.1's
#: verdict on a combination of its own choosing.
B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM = 450.0, 600.0, 40.0, 9.5, 15.9
BEND_DIAMETER_MM = 65.0
COUNT_B, COUNT_H = 3, 4
#: The three cross-ties `test_column_plan.py`'s CONVENTIONAL fixture draws
#: (R19/R20) -- an outer-tie-only plan is section 6.1 BLOCKED (see that
#: file's `test_is_blocked_is_the_ONE_test_of_section_6_1_s_verdict`), so a
#: candidate built with an empty tie box would never reach `apply_batch`.
TIE_SUBSETS_TEXT = "1 6\n9 3\n8 4"

_Splice = namedtuple("_Splice", "length_mm")


@pytest.fixture(autouse=True)
def _clear_collector_items():
    FakeFilteredElementCollector._ITEMS = []
    yield
    FakeFilteredElementCollector._ITEMS = []


# ======================================================================= #
# rft.core.column_batch -- PURE grouping


def _extent(clear_height_mm, top_support_found, base_z_mm=3000.0):
    top_source = (SOURCE_SUPPORT_FACE if top_support_found
                 else SOURCE_LEVEL_ELEVATION)
    return ColumnExtent(
        base_z_mm=base_z_mm, top_z_mm=base_z_mm + clear_height_mm,
        clear_height_mm=clear_height_mm,
        base_source=SOURCE_SUPPORT_FACE, top_source=top_source)


def _host_stub(clear_height_mm, top_support_found, base_z_mm=3000.0):
    """Only what `group_key` reads -- a minimal stand-in for the dict
    `read_column` returns, used where a whole host is not needed."""
    return {"extent": _extent(clear_height_mm, top_support_found, base_z_mm)}


def test_two_columns_same_type_different_clear_height_land_in_different_groups():
    groups = group_hosts([
        (421967, _host_stub(2700.0, False)),
        (423606, _host_stub(3000.0, True)),
    ])
    assert len(groups) == 2
    assert groups[0].key.clear_height_mm == 2700.0
    assert groups[1].key.clear_height_mm == 3000.0


def test_two_columns_same_type_same_extent_land_in_one_group():
    groups = group_hosts([
        (424280, _host_stub(2500.0, False)),
        (424284, _host_stub(2500.0, False)),
    ])
    assert len(groups) == 1
    assert groups[0].element_ids == [424280, 424284]


def test_a_group_of_one_is_not_an_error():
    groups = group_hosts([(423606, _host_stub(3000.0, True))])
    assert len(groups) == 1
    assert groups[0].element_ids == [423606]


def test_same_clear_height_but_different_top_support_split_too():
    """The SECOND half of the key, isolated: identical clear height, one
    with a measured support face and one falling back to the level
    elevation -- the exact 421967/422078 vs. 423606/422840 split #104
    measured, reduced to the one field that differs."""
    groups = group_hosts([
        (421967, _host_stub(2700.0, top_support_found=False)),
        (999999, _host_stub(2700.0, top_support_found=True)),
    ])
    assert len(groups) == 2


def test_group_order_is_first_seen_not_hash_order():
    groups = group_hosts([
        (3, _host_stub(3000.0, True)),
        (1, _host_stub(2700.0, False)),
        (2, _host_stub(3000.0, True)),
    ])
    assert [g.key.clear_height_mm for g in groups] == [3000.0, 2700.0]
    assert groups[0].element_ids == [3, 2]


# ======================================================================= #
# rft.core.column_report's two new sections -- PURE


def test_batch_group_section_names_each_group_its_height_and_its_columns():
    groups = [
        BatchGroup(key=GroupKey(2700.0, False), element_ids=[1, 2]),
        BatchGroup(key=GroupKey(3000.0, True), element_ids=[3]),
    ]
    lines = "\n".join(batch_group_section(groups).lines)
    assert "2700" in lines and "1" in lines and "2" in lines
    assert "3000" in lines and "3" in lines
    assert "no top support" in lines
    assert "a top support was found" in lines


def test_batch_group_section_with_no_groups_says_so():
    lines = batch_group_section([]).lines
    assert any("excluded" in line for line in lines)


def test_batch_exclusion_section_names_every_exclusion_and_its_reason():
    exclusions = [Exclusion(element_id=42, reason="multi-storey")]
    lines = "\n".join(batch_exclusion_section(exclusions).lines)
    assert "42" in lines
    assert "multi-storey" in lines


def test_batch_exclusion_section_when_empty_says_so():
    lines = batch_exclusion_section([]).lines
    assert any("No columns were excluded" in line for line in lines)


# ======================================================================= #
# rft.revit.column_batch -- the adapter, against the fake


def _shared_inputs():
    return BatchInputs(
        counts=perimeter_bars(COUNT_B, COUNT_H),
        splice=_Splice(length_mm=600.0),
        bar_diameter_mm=BAR_DIA_MM,
        tie_diameter_mm=TIE_DIA_MM,
        bar_type_name="16M",
        tie_type_name="10M",
        mode=MODE_AUTO,
        tie_bend_diameter_mm=BEND_DIAMETER_MM,
        tie_subsets_text=TIE_SUBSETS_TEXT,
        manual_confinement_mm=None,
        manual_middle_zone_mm=None,
    )


def _host(clear_height_mm, top_support_found, element_id, base_z_mm=3000.0):
    extent = _extent(clear_height_mm, top_support_found, base_z_mm)
    return {
        "element_id": element_id,
        "type_name": "450 x 600mm",
        "family_name": "M_Concrete-Rectangular-Column",
        "section": section_from_dimensions(B_MM, H_MM),
        "hand": (1.0, 0.0, 0.0),
        "facing": (0.0, 1.0, 0.0),
        "cover_mm": COVER_MM,
        "cover_type_name": "Interior (framing, columns)",
        "top_face_cover_is_set": top_support_found,
        "base_level": ("Level 1", base_z_mm),
        "top_level": ("Level 2", extent.top_z_mm),
        "extent": extent,
        "search_view_name": "{3D}",
    }


def _install_reads(monkeypatch, reads_by_id):
    """Stand in for `read_column`, keyed by element id -- see the module
    docstring for why `read_column` itself is not driven through the
    fake's own support-search machinery here."""
    def fake_read_column(_doc, element):
        result = reads_by_id[element.Id.IntegerValue]
        if isinstance(result, Exception):
            raise result
        return result
    monkeypatch.setattr(column_batch_module, "read_column", fake_read_column)


# ----------------------------------------------------------------- #
# collect_candidates: the TYPE is the filter


def test_collect_candidates_matches_only_the_same_family_type():
    shared_symbol = FakeFamilySymbol("450 x 600mm")
    other_symbol = FakeFamilySymbol("300 x 600mm")
    picked = FakeColumn(symbol=shared_symbol, element_id=1)
    same_type = FakeColumn(symbol=shared_symbol, element_id=2)
    different_type = FakeColumn(symbol=other_symbol, element_id=3)
    FakeFilteredElementCollector._ITEMS = [picked, same_type, different_type]

    candidates = collect_candidates(FakeDocument({}), picked)

    assert set(c.Id.IntegerValue for c in candidates) == {1, 2}


def test_collect_candidates_includes_the_picked_column_itself():
    shared_symbol = FakeFamilySymbol("450 x 600mm")
    picked = FakeColumn(symbol=shared_symbol, element_id=1)
    FakeFilteredElementCollector._ITEMS = [picked]

    candidates = collect_candidates(FakeDocument({}), picked)

    assert [c.Id.IntegerValue for c in candidates] == [1]


# ----------------------------------------------------------------- #
# read_candidates: a refused column is excluded, reason carried


def test_read_candidates_excludes_a_refused_column_and_keeps_its_reason(
        monkeypatch):
    col_ok = FakeColumn(element_id=1)
    col_bad = FakeColumn(element_id=2)
    _install_reads(monkeypatch, {
        1: _host(2700.0, False, 1),
        2: ColumnHostError("This column passes through 1 level(s)."),
    })

    reads, exclusions = read_candidates(FakeDocument({}), [col_ok, col_bad])

    assert [element.Id.IntegerValue for element, _host in reads] == [1]
    assert len(exclusions) == 1
    assert exclusions[0].element_id == 2
    assert "passes through 1 level" in exclusions[0].reason


# ----------------------------------------------------------------- #
# plan_candidates: read/group (Section 3), plan and refuse (Section 5)


def test_plan_candidates_groups_by_extent_and_builds_a_plan_per_survivor(
        monkeypatch):
    shared_symbol = FakeFamilySymbol("450 x 600mm")
    col_a = FakeColumn(symbol=shared_symbol, element_id=421967)
    col_b = FakeColumn(symbol=shared_symbol, element_id=423606)
    FakeFilteredElementCollector._ITEMS = [col_a, col_b]
    _install_reads(monkeypatch, {
        421967: _host(2700.0, False, 421967),
        423606: _host(3000.0, True, 423606),
    })

    result = plan_candidates(FakeDocument({}), col_a, _shared_inputs())

    assert isinstance(result, BatchPlan)
    assert result.exclusions == []
    assert len(result.candidates) == 2
    heights = sorted(g.key.clear_height_mm for g in result.groups)
    assert heights == [2700.0, 3000.0]
    # Two DIFFERENT plans -- not the same ladder stamped on both hosts.
    plan_a, plan_b = (c.plan for c in result.candidates)
    assert plan_a.extent.clear_height_mm != plan_b.extent.clear_height_mm


def test_plan_candidates_excludes_a_read_column_refusal_before_planning(
        monkeypatch):
    shared_symbol = FakeFamilySymbol("450 x 600mm")
    col_a = FakeColumn(symbol=shared_symbol, element_id=1)
    col_b = FakeColumn(symbol=shared_symbol, element_id=2)
    FakeFilteredElementCollector._ITEMS = [col_a, col_b]
    _install_reads(monkeypatch, {
        1: _host(2700.0, False, 1),
        2: ColumnHostError("out of scope"),
    })

    result = plan_candidates(FakeDocument({}), col_a, _shared_inputs())

    assert [c.element.Id.IntegerValue for c in result.candidates] == [1]
    assert len(result.exclusions) == 1
    assert result.exclusions[0].element_id == 2
    # Excluded BEFORE grouping ever runs on it: one group, not a group of
    # one PLUS the refused column's own (nonexistent) extent.
    assert len(result.groups) == 1


def test_plan_candidates_excludes_a_column_refuse_if_not_ready_declines(
        monkeypatch):
    """The per-column `refuse_if_not_ready` gate (spec Section 5) -- proven
    against a fake refusal so this test targets the ORCHESTRATION (the
    try/except around the call), not `refuse_if_not_ready`'s own logic,
    which `test_column_apply.py` already covers."""
    shared_symbol = FakeFamilySymbol("450 x 600mm")
    col_a = FakeColumn(symbol=shared_symbol, element_id=1)
    col_b = FakeColumn(symbol=shared_symbol, element_id=2)
    FakeFilteredElementCollector._ITEMS = [col_a, col_b]
    _install_reads(monkeypatch, {
        1: _host(2700.0, False, 1),
        2: _host(2700.0, False, 2),
    })
    real_refuse = column_batch_module.refuse_if_not_ready

    def fake_refuse(plan):
        if plan.host["element_id"] == 2:
            raise ColumnPlacementError("refused: unbuildable tie (test)")
        return real_refuse(plan)

    monkeypatch.setattr(column_batch_module, "refuse_if_not_ready",
                        fake_refuse)

    result = plan_candidates(FakeDocument({}), col_a, _shared_inputs())

    assert [c.element.Id.IntegerValue for c in result.candidates] == [1]
    assert len(result.exclusions) == 1
    assert result.exclusions[0].element_id == 2
    assert "refused: unbuildable tie" in result.exclusions[0].reason


# ----------------------------------------------------------------- #
# apply_batch: ONE transaction, all-or-nothing


class _SpyTransaction(object):
    """See `test_column_apply.py`'s identical fixture -- the direct
    statement of "never opens a transaction on a plan already known to
    fail", reused here for the whole-batch claim."""

    constructed = []

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        _SpyTransaction.constructed.append(self)

    def Start(self):
        pass

    def Commit(self):
        pass

    def RollBack(self):
        pass


@pytest.fixture
def _reset_spy_transaction():
    _SpyTransaction.constructed = []
    yield


def _candidate(element_id, clear_height_mm=2700.0, level_z=(50.0, 150.0)):
    from rft.core.column_tie_levels import TieLadder, TieLevel, ZONE_MIDDLE
    layout = perimeter_bar_positions(
        B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM, COUNT_B, COUNT_H)
    bars = bar_plan(
        _host(clear_height_mm, False, element_id), perimeter_bars(COUNT_B, COUNT_H),
        _Splice(length_mm=600.0), BAR_DIA_MM, TIE_DIA_MM, "16M", "10M")
    plan = complete_plan(bars, MODE_AUTO, BEND_DIAMETER_MM, TIE_SUBSETS_TEXT)
    element = FakeColumn(element_id=element_id)
    return ColumnCandidate(element=element, host=bars.host, plan=plan)


def test_apply_batch_refuses_the_whole_run_without_opening_a_transaction(
        monkeypatch, _reset_spy_transaction):
    monkeypatch.setattr(column_batch_module, "Transaction", _SpyTransaction)
    doc = FakeDocument({})
    empty_batch = BatchPlan(groups=[], exclusions=[
        Exclusion(element_id=1, reason="out of scope")], candidates=[])

    with pytest.raises(ColumnPlacementError):
        apply_batch(doc, empty_batch, object(), object(), object(), object())

    assert _SpyTransaction.constructed == []
    # The fake DOCUMENT, not a message: nothing was ever deleted, because
    # nothing was ever allowed to open a transaction against it.
    assert doc.deleted_ids == []


def test_apply_batch_uses_exactly_one_transaction_for_every_candidate(
        monkeypatch, _reset_spy_transaction):
    monkeypatch.setattr(column_batch_module, "Transaction", _SpyTransaction)
    doc = FakeDocument({})
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[_candidate(1), _candidate(2), _candidate(3)])

    read_existing(doc, batch)
    apply_batch(doc, batch, object(), object(), object(), object())

    assert len(_SpyTransaction.constructed) == 1


def test_apply_batch_places_every_candidate_and_tags_it_with_its_own_host_id():
    doc = FakeDocument({})
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[_candidate(101, 2700.0),
                                 _candidate(102, 3000.0)])

    read_existing(doc, batch)
    result = apply_batch(doc, batch, object(), object(), object(), object())

    ids = [element_id for element_id, _result in result.per_column]
    assert ids == [101, 102]
    for element_id, placement in result.per_column:
        assert placement.ties_created
        assert placement.bars_created
        for rebar in placement.ties_created + placement.bars_created:
            assert rebar.LookupParameter("Partition").AsString() == (
                partition_tag(element_id))


def test_a_failure_placing_one_column_rolls_back_the_WHOLE_batch(
        monkeypatch):
    """R25 extended to a batch: the first candidate's OWN existing cage is
    deleted, the second candidate's placement then blows up, and the
    rollback must restore the FIRST candidate's cage too -- proof that both
    columns share one transaction rather than one each."""
    host_element_1 = FakeColumn(element_id=201)
    old_tie = FakeRebarElement(host_id=host_element_1.Id, id_value=900,
                              partition=partition_tag(201))
    FakeFilteredElementCollector._ITEMS = [old_tie]
    doc = FakeDocument({})

    candidate_1 = _candidate(201)
    candidate_1.element = host_element_1
    candidate_2 = _candidate(202)
    batch = BatchPlan(groups=[], exclusions=[],
                      candidates=[candidate_1, candidate_2])

    call_count = [0]
    real_place_bars = column_batch_module.place_bars

    def _boom(doc_, element, bar_type, plan):
        call_count[0] += 1
        if call_count[0] == 2:
            raise RuntimeError("second column's bars blew up")
        return real_place_bars(doc_, element, bar_type, plan)

    monkeypatch.setattr(column_batch_module, "place_bars", _boom)
    read_existing(doc, batch)

    with pytest.raises(RuntimeError, match="second column's bars blew up"):
        apply_batch(doc, batch, object(), object(), object(), object())

    # Candidate 1's old tie was deleted while building its NEW cage, then
    # restored when candidate 2's failure rolled back the SHARED
    # transaction.
    remaining_ids = set(item.Id.IntegerValue
                        for item in FakeFilteredElementCollector._ITEMS)
    assert 900 in remaining_ids


def test_apply_batch_refuses_before_opening_when_a_candidate_plan_is_blocked(
        monkeypatch, _reset_spy_transaction):
    """Belt-and-braces re-check (mirrors `column_placer.apply`): even a
    candidate that reached `apply_batch` with a plan `refuse_if_not_ready`
    would decline must not let the SHARED transaction open."""
    monkeypatch.setattr(column_batch_module, "Transaction", _SpyTransaction)
    good = _candidate(1)
    bad = _candidate(2)

    def fake_refuse(plan):
        if plan is bad.plan:
            raise ColumnPlacementError("blocked (test)")

    monkeypatch.setattr(column_batch_module, "refuse_if_not_ready",
                        fake_refuse)
    batch = BatchPlan(groups=[], exclusions=[], candidates=[good, bad])
    doc = FakeDocument({})

    with pytest.raises(ColumnPlacementError):
        apply_batch(doc, batch, object(), object(), object(), object())

    assert _SpyTransaction.constructed == []


# ----------------------------------------------------------------- #
# Spec Section 6: R23's count and R24's foreign list, read ONCE


def test_read_existing_returns_a_row_per_candidate_with_its_own_counts():
    host = FakeColumn(element_id=301)
    ours = FakeRebarElement(host_id=host.Id, id_value=901,
                           partition=partition_tag(301))
    FakeFilteredElementCollector._ITEMS = [ours]
    candidate = _candidate(301)
    candidate.element = host
    batch = BatchPlan(groups=[], exclusions=[], candidates=[candidate])

    rows = read_existing(FakeDocument({}), batch)

    assert [row.element_id for row in rows] == [301]
    assert rows[0].replaced_count == 1
    assert candidate.ours and candidate.foreign == []


def test_apply_batch_deletes_exactly_what_read_existing_counted():
    """Spec Section 6: ONE read. What the engineer confirmed and what goes
    are the same elements -- so an element that appears only AFTER the
    count was taken is not swept up by a second read inside the
    transaction."""
    host = FakeColumn(element_id=302)
    counted = FakeRebarElement(host_id=host.Id, id_value=902,
                              partition=partition_tag(302))
    FakeFilteredElementCollector._ITEMS = [counted]
    candidate = _candidate(302)
    candidate.element = host
    batch = BatchPlan(groups=[], exclusions=[], candidates=[candidate])
    doc = FakeDocument({})

    rows = read_existing(doc, batch)
    assert rows[0].replaced_count == 1
    # Appears after the count was shown -- never confirmed, so never
    # deleted.
    latecomer = FakeRebarElement(host_id=host.Id, id_value=903,
                                partition=partition_tag(302))
    FakeFilteredElementCollector._ITEMS = [counted, latecomer]

    apply_batch(doc, batch, object(), object(), object(), object())

    assert 902 in [element_id.IntegerValue for element_id in doc.deleted_ids]
    assert 903 not in [element_id.IntegerValue
                      for element_id in doc.deleted_ids]


def test_apply_batch_refuses_when_read_existing_was_never_run(
        monkeypatch, _reset_spy_transaction):
    """R23: no count shown, no deletion. Refused before the transaction,
    like everything else knowable beforehand."""
    monkeypatch.setattr(column_batch_module, "Transaction", _SpyTransaction)
    batch = BatchPlan(groups=[], exclusions=[], candidates=[_candidate(401)])

    with pytest.raises(ColumnPlacementError, match="never read"):
        apply_batch(FakeDocument({}), batch, object(), object(), object(),
                    object())

    assert _SpyTransaction.constructed == []


def test_batch_replacement_section_names_every_column_and_its_count():
    section = batch_replacement_section([
        BatchExisting(element_id=1, replaced_count=17, foreign_ids=[]),
        BatchExisting(element_id=2, replaced_count=0, foreign_ids=[55, 56]),
    ])

    text = "\n".join(section.lines)
    assert "Column 1" in text and "17" in text
    # Every column that will be placed appears, including one holding
    # nothing -- a reviewer counts lines against the groups.
    assert "Column 2" in text
    # R24: foreign named, and said to be left alone.
    assert "55, 56" in text and "left untouched" in text


def test_batch_replacement_section_with_no_rows_says_nothing_is_replaced():
    section = batch_replacement_section([])
    assert "nothing will be replaced" in "\n".join(section.lines)


def test_a_column_excluded_by_the_refusal_gate_is_in_NO_group(monkeypatch):
    """R33's group listing is what a reviewer checks a split by, so it must
    name only columns that get steel -- never a column the report also
    lists as excluded."""
    shared_symbol = FakeFamilySymbol("450 x 600mm")
    col_a = FakeColumn(symbol=shared_symbol, element_id=1)
    col_b = FakeColumn(symbol=shared_symbol, element_id=2)
    FakeFilteredElementCollector._ITEMS = [col_a, col_b]
    _install_reads(monkeypatch, {
        1: _host(2700.0, False, 1),
        2: _host(2700.0, False, 2),
    })
    real_refuse = column_batch_module.refuse_if_not_ready

    def fake_refuse(plan):
        if plan.host["element_id"] == 2:
            raise ColumnPlacementError("refused: unbuildable tie (test)")
        return real_refuse(plan)

    monkeypatch.setattr(column_batch_module, "refuse_if_not_ready",
                        fake_refuse)

    result = plan_candidates(FakeDocument({}), col_a, _shared_inputs())

    grouped = [element_id for group in result.groups
               for element_id in group.element_ids]
    assert grouped == [1]
    assert [exclusion.element_id for exclusion in result.exclusions] == [2]
