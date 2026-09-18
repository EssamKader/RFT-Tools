# -*- coding: utf-8 -*-
"""Issue #153 -- specs/column-batch-placement.md Section 3, and R33
(docs/column/spec-amendments.md): the grouping key a batch splits on.

PURE. No Revit import, no WPF. This module GROUPS what
``rft.revit.column_host.read_column`` already computed; it never re-derives
either half of the key from a parameter or from geometry of its own.

## Why the key is two fields read off the SAME read, not two new ones

Measured on a live host (docs/column/verification/issue-104-batch-grouping.
md): five ``450 x 600mm`` columns share family, type, section, cover,
rotation and orientation, and two of them still need a different tie ladder
because they differ by 300 mm of clear height. A batch keyed on the family
type alone would give a 3000 mm column a 2700 mm column's ladder -- "a cage
short by a tie, which looks correct in the browser" (the verification
doc's own words).

The spec's rule (Section 3) is therefore: group by **the clear height** and
**whether a top support was found**, both already sitting on the
``ColumnExtent`` a single-column run's ``read_column`` returns. Recomputing
either from parameters here would be a second derivation, which is exactly
what the spec forbids -- "the whole safety argument is that a batch and a
single run compute the same numbers the same way."

Rotation is deliberately NOT part of the key -- spec Section 3 records this
as an open item, not an oversight, and this module must not quietly add it.
"""

from collections import OrderedDict, namedtuple

from .column_host_rules import SOURCE_SUPPORT_FACE

#: Spec Section 3's key: the clear height, and whether a top support was
#: found (``top_source`` from the SAME ``ColumnExtent`` the single-column
#: report already shows -- R5/R6's "support face" vs. "level elevation").
GroupKey = namedtuple("GroupKey", "clear_height_mm top_support_found")

#: One group: its key, and the element ids that fell in it, in the order
#: they were read. A group of one is not an error (spec Section 3).
BatchGroup = namedtuple("BatchGroup", "key element_ids")

#: A column excluded before any transaction opened (spec Section 5), and
#: the reason -- carried whether the exclusion came from `read_column`'s
#: own refusal or from `refuse_if_not_ready`'s later gate, so the report
#: cannot tell (and does not need to) which stage excluded it.
Exclusion = namedtuple("Exclusion", "element_id reason")

#: What ONE candidate's host already holds, read once before any dialog
#: and before the transaction (spec Section 6): how many of THIS tool's
#: own elements R23's confirmation must count, and the foreign rebar R24
#: requires naming and never deleting. Pure data, so the report's table
#: can be tested without a document.
BatchExisting = namedtuple("BatchExisting",
                           "element_id replaced_count foreign_ids")


def group_key(extent):
    """Spec Section 3's key, read off one ``ColumnExtent`` -- the object
    ``rft.core.column_host_rules.extent_from_ends`` already returns to the
    single-column path. Nothing here is computed from a parameter or from
    geometry; both fields are already decided.
    """
    return GroupKey(
        clear_height_mm=extent.clear_height_mm,
        top_support_found=(extent.top_source == SOURCE_SUPPORT_FACE))


def group_hosts(host_reads):
    """Group ``(element_id, host_dict)`` pairs -- exactly what
    ``rft.revit.column_host.read_column`` returns per column, paired with
    its element id -- by :func:`group_key`.

    Order is FIRST-SEEN, for groups and for the element ids inside each
    group: the report must read the same way on every run of an identical
    batch, and a hash-ordered grouping would not promise that.
    """
    groups = OrderedDict()
    for element_id, host in host_reads:
        key = group_key(host["extent"])
        groups.setdefault(key, []).append(element_id)
    return [BatchGroup(key=key, element_ids=list(element_ids))
            for key, element_ids in groups.items()]
