# -*- coding: utf-8 -*-
"""Issue #226 -- specs/isolated-footing-batch.md Section 3, and R9
(docs/footing/spec-amendments.md): the grouping key a footing batch
splits on.

PURE. No Revit import. This module GROUPS what ``rft.revit.footing_host.
read_footing_geometry_mm``/``read_dowel_column_section_mm`` already
computed; it never re-derives any field from a parameter or from geometry
of its own -- the same discipline ``rft.core.column_batch`` follows for
ColumnRFT (that module's own docstring explains why: recomputing a key
field here would be a second derivation, and "the whole safety argument is
that a batch and a single run compute the same numbers the same way").

## Why the key is the FULL live-read tuple, not the column section alone

R9 records the ruling: unlike `column_batch`'s key (two fields off ONE
function's output, `read_column`'s `ColumnExtent`), the footing tool's own
live-read surface is split across TWO functions -- the footing's own plan
dimensions/thickness/covers (`read_footing_geometry_mm`, #228) and the
auto-detected column's own section/cover (`read_dowel_column_section_mm`,
#221). Grouping on the column section alone would ASSUME two footings of
the same family type always measure identically rather than MEASURE it --
exactly the category of mistake `specs/column-batch-placement.md` Sec 0
warns against. Since #228 already reads the footing's own geometry live,
there is no reason to fall back to an assumption when the real measurement
is one function call away.

Deliberately NOT defined by importing ``rft.core.column_batch``'s own
``Exclusion``/``BatchExisting`` types -- this repo's element-isolation
convention keeps each element's core batch module self-contained rather
than cross-coupling two elements' core packages for what are, here, three
trivial namedtuples.
"""

from collections import OrderedDict, namedtuple

#: R9's own nine-field key: the footing's own geometry (#228) plus the
#: auto-detected column's own section/cover (#221) -- both already live-
#: read by the single-footing path, read here, never recomputed.
GroupKey = namedtuple(
    "GroupKey",
    ["a_mm", "b_mm", "footing_thickness_mm", "cover_mm",
     "bottom_cover_mm", "top_cover_mm", "Cw_mm", "Cd_mm", "Ccover_mm"])

#: One group: its key, and the footing element ids that fell in it, in
#: the order they were read. A group of one is not an error (spec Sec 3).
BatchGroup = namedtuple("BatchGroup", ["key", "element_ids"])

#: A footing excluded before any transaction opened (spec Sec 5), and the
#: reason -- carried whether the exclusion came from #220/#221/#228's own
#: refusal, the batch's own "column type pair mismatch" check (spec Sec
#: 2), or `build_footing_plan`'s own `ValueError`/`DowelArrayLayoutError`,
#: so the report cannot tell (and does not need to) which stage excluded
#: it.
Exclusion = namedtuple("Exclusion", ["element_id", "reason"])

#: What ONE candidate's host already holds, read once before any dialog
#: and before the transaction (spec Sec 6): how many of this tool's own
#: elements the replacement confirmation must count, and the foreign
#: rebar that is reported and never deleted.
BatchExisting = namedtuple(
    "BatchExisting", ["element_id", "replaced_count", "foreign_ids"])


def group_key(geometry, column_section):
    """R9's key, read off ONE footing's own ``FootingGeometry`` (#228)
    and ``DowelColumnSection`` (#221) -- nothing here is computed from a
    parameter or from geometry; every field is already decided.
    """
    return GroupKey(
        a_mm=geometry.a_mm, b_mm=geometry.b_mm,
        footing_thickness_mm=geometry.footing_thickness_mm,
        cover_mm=geometry.cover_mm,
        bottom_cover_mm=geometry.bottom_cover_mm,
        top_cover_mm=geometry.top_cover_mm,
        Cw_mm=column_section.Cw_mm, Cd_mm=column_section.Cd_mm,
        Ccover_mm=column_section.Ccover_mm)


def group_hosts(reads):
    """Group ``(element_id, geometry, column_section)`` triples -- one per
    surviving candidate footing -- by :func:`group_key`.

    Order is FIRST-SEEN, for groups and for the element ids inside each
    group: the report must read the same way on every run of an identical
    batch, and a hash-ordered grouping would not promise that -- same
    reasoning ``column_batch.group_hosts`` already states.
    """
    groups = OrderedDict()
    for element_id, geometry, column_section in reads:
        key = group_key(geometry, column_section)
        groups.setdefault(key, []).append(element_id)
    return [BatchGroup(key=key, element_ids=list(element_ids))
            for key, element_ids in groups.items()]
