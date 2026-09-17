# -*- coding: utf-8 -*-
"""Issue #117 -- R24/R26: which rebar in this column is ours.

Run against ``tests/fake_revit_api.py`` (#106), extended here with a
writable ``Partition`` parameter (``FakeRebarElement`` /
``FakeRebarPartitionParameter``). No live Revit host -- see
``rft.revit.column_ownership``'s own module docstring for what is
confirmed live (issue #109/#117) and what is still ``SHAPE UNVERIFIED``.
"""

import pytest

from fake_revit_api import (
    FakeBuiltInParameter,
    FakeColumn,
    FakeDocument,
    FakeElementId,
    FakeFilteredElementCollector,
    FakeRebarBarType,
    FakeRebarElement,
)

from rft.revit.column_ownership import (
    ColumnOwnershipError,
    OWNERSHIP_PREFIX,
    ForeignRebar,
    hosted_rebar,
    is_ours,
    partition_host_rebar,
    partition_tag,
    read_partition,
    tag_as_ours,
)


@pytest.fixture(autouse=True)
def _clear_collector_items():
    FakeFilteredElementCollector._ITEMS = []
    yield
    FakeFilteredElementCollector._ITEMS = []


def column(element_id=422078):
    return FakeColumn(element_id=element_id)


# --------------------------------------------------------------------- #
# R26: tag written and found again


def test_an_element_tagged_by_this_module_is_found_by_it_afterwards():
    host = column()
    rebar = FakeRebarElement(host_id=host.Id, id_value=1)
    tag_as_ours(rebar, host.Id.IntegerValue)
    assert read_partition(rebar) == "RFT-COL-%s" % host.Id.IntegerValue
    assert is_ours(rebar) is True


def test_the_tag_is_exactly_the_prefix_plus_the_host_id():
    assert partition_tag(422078) == "RFT-COL-422078"


def test_an_untagged_element_reads_as_not_ours():
    rebar = FakeRebarElement(host_id=FakeElementId(1), id_value=2)
    assert read_partition(rebar) is None
    assert is_ours(rebar) is False


def test_a_missing_partition_parameter_is_a_named_refusal():
    class NoPartition(object):
        Id = FakeElementId(3)

        def LookupParameter(self, _name):
            return None

    with pytest.raises(ColumnOwnershipError) as caught:
        read_partition(NoPartition())
    assert "Partition" in str(caught.value)


# --------------------------------------------------------------------- #
# R26: hand-edited Partition is FOREIGN, not silently adopted


def test_a_hand_edited_partition_is_reported_as_foreign_not_adopted():
    rebar = FakeRebarElement(host_id=FakeElementId(1), id_value=4,
                             partition="Structural steel")
    assert is_ours(rebar) is False


# --------------------------------------------------------------------- #
# R26: a cage carrying a STALE host id is still ours -- the case only a
# PREFIX test survives


def test_a_cage_carrying_a_stale_host_id_is_still_ours():
    """A column copied together with its cage: the Partition value still
    reads ``RFT-COL-<old id>``, not the id of the column it now sits on."""
    rebar = FakeRebarElement(host_id=FakeElementId(999),
                             id_value=5, partition="RFT-COL-111111")
    assert is_ours(rebar) is True


def test_the_ownership_test_is_a_PREFIX_not_an_equality_check():
    """The direct, non-mutation statement of the rule the mutation case in
    ``tools/prove_guards.py`` also proves against the source: equality
    would reject the stale-id case above."""
    stale = "RFT-COL-111111"
    current_tag = partition_tag(999)
    assert stale != current_tag
    assert stale.startswith(OWNERSHIP_PREFIX)


# --------------------------------------------------------------------- #
# R24: foreign rebar is described, not merely counted


def test_foreign_rebar_is_returned_with_id_bar_type_and_quantity():
    host = column()
    bar_type = FakeRebarBarType(name="16M", id_value=FakeElementId(77))
    doc = FakeDocument({77: bar_type})
    foreign_rebar = FakeRebarElement(
        host_id=host.Id, id_value=6, bar_type_id=FakeElementId(77),
        quantity=3, partition="")
    FakeFilteredElementCollector._ITEMS = [foreign_rebar]

    ours, foreign = partition_host_rebar(doc, host)

    assert ours == []
    assert len(foreign) == 1
    entry = foreign[0]
    assert isinstance(entry, ForeignRebar)
    assert entry.element_id == 6
    assert entry.bar_type_name == "16M"
    assert entry.quantity == 3


def test_foreign_rebar_with_an_unresolvable_bar_type_still_reports_something():
    host = column()
    doc = FakeDocument({})
    foreign_rebar = FakeRebarElement(
        host_id=host.Id, id_value=9, bar_type_id=FakeElementId(404),
        quantity=1)
    FakeFilteredElementCollector._ITEMS = [foreign_rebar]

    _, foreign = partition_host_rebar(doc, host)

    assert foreign[0].bar_type_name == "<unknown bar type>"


# --------------------------------------------------------------------- #
# R24/R26: ours vs. foreign partition, hosted-only


def test_partition_host_rebar_splits_ours_from_foreign():
    host = column()
    other_host = column(element_id=1)
    ours_rebar = FakeRebarElement(host_id=host.Id, id_value=10,
                                  partition=partition_tag(host.Id.IntegerValue))
    foreign_rebar = FakeRebarElement(host_id=host.Id, id_value=11,
                                     partition="")
    not_hosted_here = FakeRebarElement(
        host_id=other_host.Id, id_value=12,
        partition=partition_tag(other_host.Id.IntegerValue))
    FakeFilteredElementCollector._ITEMS = [
        ours_rebar, foreign_rebar, not_hosted_here]
    doc = FakeDocument({})

    ours, foreign = partition_host_rebar(doc, host)

    assert [r.Id.IntegerValue for r in ours] == [10]
    assert [f.element_id for f in foreign] == [11]


def test_hosted_rebar_never_returns_an_element_hosted_elsewhere():
    host = column(element_id=422078)
    other_host = column(element_id=1)
    elsewhere = FakeRebarElement(host_id=other_host.Id, id_value=20)
    FakeFilteredElementCollector._ITEMS = [elsewhere]

    assert hosted_rebar(FakeDocument({}), host) == []
