# -*- coding: utf-8 -*-
"""Issue #226 -- specs/isolated-footing-batch.md Section 6: which rebar
on this footing is ours.

Mirrors ``tests/test_column_ownership.py`` (issue #117/R24/R26) test for
test, since ``rft.revit.footing_ownership`` mirrors ``column_ownership``
in PATTERN -- only the ``RFT-FTG-`` prefix differs. Run against
``tests/fake_revit_api.py`` (#106); ``FakeRebarElement`` reads the literal
``"Partition"`` string, the same accessor both modules use, so it is
reused here unmodified.
"""

import pytest

from fake_revit_api import (
    FakeDocument,
    FakeElementId,
    FakeFilteredElementCollector,
    FakeRebarBarType,
    FakeRebarElement,
)

from rft.revit.footing_ownership import (
    FootingOwnershipError,
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


class _Host(object):
    """Only what ``footing_ownership`` reads off a host: ``Id``."""

    def __init__(self, element_id):
        self.Id = FakeElementId(element_id)


def footing(element_id=425190):
    return _Host(element_id)


# --------------------------------------------------------------------- #
# Tag written and found again


def test_an_element_tagged_by_this_module_is_found_by_it_afterwards():
    host = footing()
    rebar = FakeRebarElement(host_id=host.Id, id_value=1)
    tag_as_ours(rebar, host.Id.IntegerValue)
    assert read_partition(rebar) == "RFT-FTG-%s" % host.Id.IntegerValue
    assert is_ours(rebar) is True


def test_the_tag_is_exactly_the_prefix_plus_the_host_id():
    assert partition_tag(425190) == "RFT-FTG-425190"


def test_an_untagged_element_reads_as_not_ours():
    rebar = FakeRebarElement(host_id=FakeElementId(1), id_value=2)
    assert read_partition(rebar) is None
    assert is_ours(rebar) is False


def test_a_missing_partition_parameter_is_a_named_refusal():
    class NoPartition(object):
        Id = FakeElementId(3)

        def LookupParameter(self, _name):
            return None

    with pytest.raises(FootingOwnershipError) as caught:
        read_partition(NoPartition())
    assert "Partition" in str(caught.value)


# --------------------------------------------------------------------- #
# A hand-edited Partition, or a COLUMN's own tag, is FOREIGN, not adopted


def test_a_hand_edited_partition_is_reported_as_foreign_not_adopted():
    rebar = FakeRebarElement(host_id=FakeElementId(1), id_value=4,
                             partition="Structural steel")
    assert is_ours(rebar) is False


def test_a_columns_own_RFT_COL_tag_is_foreign_to_the_footing_tool():
    """The prefixes are disjoint by construction (`RFT-FTG-` vs.
    `RFT-COL-`) -- a bar the column tool placed and tagged must never be
    swept up by the footing batch's own ownership test, even though both
    tools share the exact same `Partition`-parameter mechanism."""
    rebar = FakeRebarElement(host_id=FakeElementId(1), id_value=5,
                             partition="RFT-COL-422078")
    assert is_ours(rebar) is False


# --------------------------------------------------------------------- #
# A cage carrying a STALE host id is still ours -- the case only a
# PREFIX test survives


def test_a_cage_carrying_a_stale_host_id_is_still_ours():
    rebar = FakeRebarElement(host_id=FakeElementId(999),
                             id_value=6, partition="RFT-FTG-111111")
    assert is_ours(rebar) is True


def test_the_ownership_test_is_a_PREFIX_not_an_equality_check():
    stale = "RFT-FTG-111111"
    current_tag = partition_tag(999)
    assert stale != current_tag
    assert stale.startswith(OWNERSHIP_PREFIX)


# --------------------------------------------------------------------- #
# Foreign rebar is described, not merely counted


def test_foreign_rebar_is_returned_with_id_bar_type_and_quantity():
    host = footing()
    bar_type = FakeRebarBarType(name="16M", id_value=FakeElementId(77))
    doc = FakeDocument({77: bar_type})
    foreign_rebar = FakeRebarElement(
        host_id=host.Id, id_value=7, bar_type_id=FakeElementId(77),
        quantity=3, partition="")
    FakeFilteredElementCollector._ITEMS = [foreign_rebar]

    ours, foreign = partition_host_rebar(doc, host)

    assert ours == []
    assert len(foreign) == 1
    entry = foreign[0]
    assert isinstance(entry, ForeignRebar)
    assert entry.element_id == 7
    assert entry.bar_type_name == "16M"
    assert entry.quantity == 3


# --------------------------------------------------------------------- #
# ours vs. foreign partition, hosted-only


def test_partition_host_rebar_splits_ours_from_foreign():
    host = footing()
    other_host = footing(element_id=1)
    ours_rebar = FakeRebarElement(
        host_id=host.Id, id_value=10,
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
    host = footing(element_id=425190)
    other_host = footing(element_id=1)
    elsewhere = FakeRebarElement(host_id=other_host.Id, id_value=20)
    FakeFilteredElementCollector._ITEMS = [elsewhere]

    assert hosted_rebar(FakeDocument({}), host) == []
