# -*- coding: utf-8 -*-
"""#120 -- R23/R25: the Apply path that wires the ownership layer (#117),
the tie placer (#118) and the bar placer (#119) into one transaction.

Run against ``tests/fake_revit_api.py``, extended here (see its header)
with a transactional ``FakeDocument.Delete`` -- the mechanism this suite's
central test (``test_a_failed_rebuild_leaves_the_original_cage_intact``)
depends on, and which cannot be proven any other way: reading
``rft.revit.column_placer.apply``'s source cannot show that a rolled-back
delete actually restores the model.

The ``_Plan`` fixture below mirrors the same convention
``test_column_place_bars.py``/``test_column_place_ties.py`` already use: a
plain namedtuple carrying only what ``column_placer`` reads, built from the
REAL ``rft.core.column_layout``/``rft.core.column_ties`` output so the
tie/bar placers underneath are exercised against genuine geometry.
"""

from collections import namedtuple

import pytest

from fake_revit_api import (
    FakeColumn,
    FakeDocument,
    FakeFilteredElementCollector,
    FakeRebarElement,
)

import rft.revit.column_placer as column_placer_module
from rft.core.column_inputs import PerimeterBars
from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_ties import (
    KIND_CLOSED_LOOP,
    Finding,
    ResolvedTie,
    SEVERITY_BLOCKING,
    TieSubset,
    outer_perimeter_subset,
    resolve_tie,
)
from rft.core.column_tie_levels import TieLadder, TieLevel, ZONE_MIDDLE
from rft.revit.column_ownership import partition_host_rebar, partition_tag
from rft.revit.column_placer import (
    ColumnPlacementError,
    apply,
    existing_elements,
    refuse_if_not_ready,
)

FT = 304.8

B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM = 450.0, 600.0, 40.0, 9.5, 15.9
BEND_DIAMETER_MM = 40.0  # 10M StirrupTieBendDiameter, per test_column_ties.py
MIN_BUILDABLE_MM = BEND_DIAMETER_MM + TIE_DIA_MM
COUNT_B, COUNT_H = 3, 4
HOST_ID_VALUE = 422078

_Extent = namedtuple("_Extent", "base_z_mm top_z_mm")
_Splice = namedtuple("_Splice", "length_mm")
_Plan = namedtuple(
    "_Plan", "ties ladder layout extent splice counts host findings")


def mm(value):
    return value / FT


@pytest.fixture(autouse=True)
def _clear_collector_items():
    FakeFilteredElementCollector._ITEMS = []
    yield
    FakeFilteredElementCollector._ITEMS = []


def _layout():
    return perimeter_bar_positions(
        B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM, COUNT_B, COUNT_H)


def _outer_tie(layout):
    return resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                       TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)


def _ladder(levels):
    return TieLadder(
        levels=[TieLevel(index=i, z_mm=z, zone=ZONE_MIDDLE, mirrored=False)
               for i, z in enumerate(levels)],
        bottom_count=0, middle_count=len(levels), top_count=0,
        middle_spacing_mm=0.0)


def _plan(ties=None, levels=(50.0, 150.0), findings=()):
    layout = _layout()
    counts = PerimeterBars(count_b_face=COUNT_B, count_h_face=COUNT_H,
                          total_count=len(layout.bars),
                          corner_count=len(layout.corner_indices))
    return _Plan(
        ties=ties if ties is not None else [_outer_tie(layout)],
        ladder=_ladder(levels),
        layout=layout,
        extent=_Extent(base_z_mm=3000.0, top_z_mm=6000.0),
        splice=_Splice(length_mm=600.0),
        counts=counts,
        host={"hand": (1.0, 0.0, 0.0), "facing": (0.0, 1.0, 0.0)},
        findings=findings,
    )


def _host():
    return FakeColumn(element_id=HOST_ID_VALUE)


class _SpyTransaction(object):
    """Records whether ANY transaction was ever constructed/started, so a
    refusal test can assert none was -- the direct statement of "never
    opens a transaction on a plan already known to fail" (R25)."""

    constructed = []
    started = []

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        _SpyTransaction.constructed.append(self)

    def Start(self):
        _SpyTransaction.started.append(self)

    def Commit(self):
        pass

    def RollBack(self):
        pass


@pytest.fixture
def _reset_spy_transaction():
    _SpyTransaction.constructed = []
    _SpyTransaction.started = []
    yield


def _blocking_plan():
    return _plan(findings=(Finding(SEVERITY_BLOCKING, "refused by 6.1"),))


def _unbuildable_tie_plan():
    layout = _layout()
    bad = ResolvedTie(
        subset=TieSubset(indices=(1, 2)), kind=KIND_CLOSED_LOOP,
        enclosed_indices=[1, 2], restrained_indices=[1, 2],
        centre_u_mm=0.0, centre_v_mm=0.0, half_u_mm=12.7, half_v_mm=12.7,
        narrow_mm=25.4, min_buildable_mm=MIN_BUILDABLE_MM, reason="")
    return _plan(ties=[bad])


# --------------------------------------------------------------------- #
# A3 steps 2-3: refuse before anything else


def test_refuse_if_not_ready_raises_when_the_plan_is_blocked():
    with pytest.raises(ColumnPlacementError) as caught:
        refuse_if_not_ready(_blocking_plan())
    assert "6.1" in str(caught.value)


def test_refuse_if_not_ready_raises_for_a_subthreshold_loop():
    with pytest.raises(ColumnPlacementError) as caught:
        refuse_if_not_ready(_unbuildable_tie_plan())
    assert "1 2" in str(caught.value)


def test_refuse_if_not_ready_passes_a_good_plan():
    refuse_if_not_ready(_plan())  # must not raise


# --------------------------------------------------------------------- #
# A3 step 4: ours/foreign, one read


def test_existing_elements_is_partition_host_rebar_at_this_call_site():
    host = _host()
    ours_rebar = FakeRebarElement(
        host_id=host.Id, id_value=1, partition=partition_tag(HOST_ID_VALUE))
    foreign_rebar = FakeRebarElement(host_id=host.Id, id_value=2, partition="")
    FakeFilteredElementCollector._ITEMS = [ours_rebar, foreign_rebar]
    doc = FakeDocument({})

    ours, foreign = existing_elements(doc, host)

    assert [r.Id.IntegerValue for r in ours] == [1]
    assert [f.element_id for f in foreign] == [2]


# --------------------------------------------------------------------- #
# R25: never opens a transaction on a plan already known to fail


def test_apply_never_opens_a_transaction_when_blocked(
        monkeypatch, _reset_spy_transaction):
    monkeypatch.setattr(column_placer_module, "Transaction", _SpyTransaction)
    doc = FakeDocument({})
    host = _host()

    with pytest.raises(ColumnPlacementError):
        apply(doc, host, _blocking_plan(), [], [], object(), object(),
              object(), object())

    assert _SpyTransaction.constructed == []


def test_apply_never_opens_a_transaction_for_an_unbuildable_tie(
        monkeypatch, _reset_spy_transaction):
    monkeypatch.setattr(column_placer_module, "Transaction", _SpyTransaction)
    doc = FakeDocument({})
    host = _host()

    with pytest.raises(ColumnPlacementError):
        apply(doc, host, _unbuildable_tie_plan(), [], [], object(), object(),
              object(), object())

    assert _SpyTransaction.constructed == []


# --------------------------------------------------------------------- #
# Acceptance: a first placement builds and tags a complete cage


def test_first_placement_creates_and_tags_ties_and_bars():
    doc = FakeDocument({})
    host = _host()
    plan = _plan()

    result = apply(doc, host, plan, ours=[], foreign=[],
                   bar_type=object(), tie_bar_type=object(),
                   outer_hook_type=object(), inner_hook_type=object())

    assert len(result.ties_created) == len(plan.ladder.levels)  # one outer tie/level
    assert len(result.bars_created) == 4  # four perimeter face runs, per #119
    assert result.replaced_count == 0
    assert result.foreign == []
    for rebar in result.ties_created + result.bars_created:
        assert rebar.LookupParameter("Partition").AsString() == (
            "RFT-COL-%s" % HOST_ID_VALUE)


def test_outer_and_inner_ties_use_their_own_hook_type():
    """Section 7 keeps the two hook pickers independent; #118's
    `place_ties` takes one hook type per call, so `column_placer` must call
    it once per role rather than blending the two."""
    layout = _layout()
    outer = _outer_tie(layout)
    inner = resolve_tie(TieSubset(indices=(1, 6)), layout, TIE_DIA_MM,
                        BAR_DIA_MM, BEND_DIAMETER_MM)
    plan = _plan(ties=[outer, inner], levels=(50.0,))
    doc = FakeDocument({})
    host = _host()
    outer_hook, inner_hook = object(), object()

    result = apply(doc, host, plan, ours=[], foreign=[],
                   bar_type=object(), tie_bar_type=object(),
                   outer_hook_type=outer_hook, inner_hook_type=inner_hook)

    assert len(result.ties_created) == 2  # one outer + one inner, one level
    # args[3]/args[4] are CreateFromCurves' start/end hook TYPE -- args[8]
    # is the orientation (R21's Left/Left), a different argument entirely.
    hook_types_used = [rebar.args[3] for rebar in result.ties_created]
    assert outer_hook in hook_types_used
    assert inner_hook in hook_types_used


# --------------------------------------------------------------------- #
# Acceptance: a second press replaces, not doubles


def test_a_second_placement_deletes_the_first_and_does_not_double():
    host = _host()
    plan = _plan()
    old_tie = FakeRebarElement(host_id=host.Id, id_value=900,
                              partition=partition_tag(HOST_ID_VALUE))
    old_bar = FakeRebarElement(host_id=host.Id, id_value=901,
                              partition=partition_tag(HOST_ID_VALUE))
    FakeFilteredElementCollector._ITEMS = [old_tie, old_bar]
    doc = FakeDocument({})

    ours, foreign = existing_elements(doc, host)
    assert len(ours) == 2

    result = apply(doc, host, plan, ours, foreign,
                   bar_type=object(), tie_bar_type=object(),
                   outer_hook_type=object(), inner_hook_type=object())

    assert result.replaced_count == 2
    # The old elements are gone from the host's own rebar -- not just
    # uncounted (R23: "Apply will DELETE them and rebuild"). A freshly
    # created `FakeRebarInstance` is not itself registered into the
    # collector (see fake_revit_api.py's header on what this fake does
    # and does not model), so this checks the OLD elements' removal
    # directly rather than re-querying for the new ones.
    remaining_ids = set(item.Id.IntegerValue
                        for item in FakeFilteredElementCollector._ITEMS)
    assert 900 not in remaining_ids
    assert 901 not in remaining_ids
    # Exactly one cage's worth built -- not the old count doubled
    # (R23's "not add"): one tie per ladder level, one Rebar per
    # perimeter face run.
    assert len(result.ties_created) == len(plan.ladder.levels)
    assert len(result.bars_created) == 4


def test_foreign_rebar_is_reported_and_never_deleted():
    host = _host()
    plan = _plan()
    foreign_rebar = FakeRebarElement(host_id=host.Id, id_value=55, partition="")
    FakeFilteredElementCollector._ITEMS = [foreign_rebar]
    doc = FakeDocument({})

    ours, foreign = existing_elements(doc, host)
    assert ours == []
    assert len(foreign) == 1

    result = apply(doc, host, plan, ours, foreign,
                   bar_type=object(), tie_bar_type=object(),
                   outer_hook_type=object(), inner_hook_type=object())

    assert len(result.foreign) == 1
    assert result.foreign[0].element_id == 55
    assert doc.deleted_ids == []
    remaining_ids = [item.Id.IntegerValue
                    for item in FakeFilteredElementCollector._ITEMS
                    if item.Id.IntegerValue == 55]
    assert remaining_ids == [55]  # still there, untouched


# --------------------------------------------------------------------- #
# R25's whole point: a failed rebuild cannot leave the engineer with
# neither cage -- cannot be asserted by reading source (docs/column/
# spec-amendments.md, R25).


def test_a_failed_rebuild_leaves_the_original_cage_intact(monkeypatch):
    host = _host()
    plan = _plan()
    old_tie = FakeRebarElement(host_id=host.Id, id_value=700,
                              partition=partition_tag(HOST_ID_VALUE))
    FakeFilteredElementCollector._ITEMS = [old_tie]
    doc = FakeDocument({})
    ours, foreign = existing_elements(doc, host)
    assert len(ours) == 1

    def _boom(*_args, **_kwargs):
        raise RuntimeError("bar placement blew up")

    monkeypatch.setattr(column_placer_module, "place_bars", _boom)

    with pytest.raises(RuntimeError, match="bar placement blew up"):
        apply(doc, host, plan, ours, foreign,
             bar_type=object(), tie_bar_type=object(),
             outer_hook_type=object(), inner_hook_type=object())

    # The delete happened (step 7 ran)...
    assert doc.deleted_ids == [old_tie.Id]
    # ...but the ROLLBACK put it back: the original element is present
    # again, and nothing new was built in its place.
    ours_after, _foreign_after = partition_host_rebar(doc, host)
    assert [r.Id.IntegerValue for r in ours_after] == [700]


def test_a_failed_tie_rebuild_also_rolls_back_the_delete(monkeypatch):
    """Belt and braces on the same claim, failing in the OTHER placer."""
    host = _host()
    plan = _plan()
    old_bar = FakeRebarElement(host_id=host.Id, id_value=701,
                              partition=partition_tag(HOST_ID_VALUE))
    FakeFilteredElementCollector._ITEMS = [old_bar]
    doc = FakeDocument({})
    ours, foreign = existing_elements(doc, host)

    def _boom(*_args, **_kwargs):
        raise RuntimeError("tie placement blew up")

    monkeypatch.setattr(column_placer_module, "place_ties", _boom)

    with pytest.raises(RuntimeError, match="tie placement blew up"):
        apply(doc, host, plan, ours, foreign,
             bar_type=object(), tie_bar_type=object(),
             outer_hook_type=object(), inner_hook_type=object())

    ours_after, _foreign_after = partition_host_rebar(doc, host)
    assert [r.Id.IntegerValue for r in ours_after] == [701]
