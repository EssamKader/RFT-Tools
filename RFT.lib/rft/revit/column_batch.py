# -*- coding: utf-8 -*-
"""Issue #153 -- specs/column-batch-placement.md: running the column tool
over every column of the picked type, instead of one.

THE ADAPTER for the batch. Grouping is `rft.core.column_batch`'s (pure);
this module does only the Revit-touching parts the spec's Sections 1, 2, 4
and 5 add on top of the single-column path:

    1. collect every ``OST_StructuralColumns`` instance of the SAME family
       TYPE as the picked column (Section 2) -- the type is the filter a
       person selects with, never the grouping key;
    2. read each one through the SAME `rft.revit.column_host.read_column`
       the single-column path already calls, excluding (before any
       transaction) whatever it refuses, with the reason kept (Section 5);
    3. group the survivors by `rft.core.column_batch.group_hosts` -- the
       computed extent, never a second derivation (Section 3);
    4. plan each survivor with the SAME `rft.core.column_plan.bar_plan`/
       `complete_plan` the window calls, off the SAME shared inputs, then
       run the SAME `refuse_if_not_ready` gate the single-column placer
       uses (Section 5) -- a further exclusion, same report;
    5. read what each survivor's host ALREADY holds -- once, before any
       dialog and before any transaction -- so R23's replacement count and
       R24's foreign list are the same query the placement then uses
       (Section 6);
    6. place every remaining candidate inside ONE transaction, all-or-
       nothing (Section 4, R25 extended) -- refusing the whole run rather
       than opening an empty transaction if nothing survived.

Nothing here re-derives a detailing rule: every ColumnPlan is built by the
exact functions the single-column window already calls, so a batch and a
single run cannot compute two different cages for the same host.

## Why `column_placer`'s own tie-role splitting is reused, not copied

`_place_ties_by_role` is `column_placer`'s private helper for A3 step 8 --
calling the ALREADY-MERGED `place_ties` once per role on a plan slice,
per Section 7's "structurally separate" hook pickers. Copying that split
here would be a second place that could drift from the single-column
path's own outer/inner slicing; importing it keeps there being exactly one.
"""

from collections import namedtuple

from Autodesk.Revit import DB
from Autodesk.Revit.DB import Transaction

from ..core.column_batch import BatchExisting, Exclusion, group_hosts
from ..core.column_plan import bar_plan, complete_plan
from . import column_placer
from .column_host import ColumnHostError, read_column
from .column_ownership import tag_as_ours
from .column_place_bars import place_bars
from .column_placer import (
    ColumnPlacementError, PlacementResult, existing_elements,
    refuse_if_not_ready,
)

#: Named separately from the single-column path's TRANSACTION_NAME so the
#: undo menu tells the two apart -- the same "named so it reads properly"
#: reasoning R25 states for the single-column transaction.
BATCH_TRANSACTION_NAME = "RFT Detail Column Batch"


#: What the engineer states ONCE for the whole batch (spec Section 1) --
#: carried as one object so `plan_candidates` never has to remember which
#: caller supplied which shared input. Everything HOST-derived (the
#: extent, the cover, the ladder) is instead read per column inside
#: `bar_plan`/`complete_plan`, from that column's OWN `read_column` result.
BatchInputs = namedtuple(
    "BatchInputs",
    "counts splice bar_diameter_mm tie_diameter_mm bar_type_name "
    "tie_type_name mode tie_bend_diameter_mm tie_subsets_text "
    "manual_confinement_mm manual_middle_zone_mm")


class ColumnCandidate(object):
    """One column that survived reading and refusal: its element, its own
    host read, and the ``ColumnPlan`` built from it -- ready for step 4's
    transaction.

    ``ours``/``foreign`` stay ``None`` until :func:`read_existing` fills
    them. They are NOT read inside the transaction: spec Section 6 keeps
    R23's count and the set Apply deletes the same single read, exactly as
    `column_placer.apply` takes them as arguments rather than re-reading
    them, so the number the engineer confirmed and the elements that go
    cannot be two different queries.
    """

    def __init__(self, element, host, plan):
        self.element = element
        self.host = host
        self.plan = plan
        self.ours = None
        self.foreign = None


class BatchPlan(object):
    """Everything :func:`plan_candidates` produced -- the ONE object the
    report and :func:`apply_batch` both read (token-efficient-expansion.md
    Section 7), so neither can disagree with the other about which columns
    were grouped how, or which were excluded and why.
    """

    def __init__(self, groups, exclusions, candidates):
        self.groups = groups
        self.exclusions = exclusions
        self.candidates = candidates


class BatchPlacementResult(object):
    """What step 4's transaction actually built, per column -- the report
    material spec Section 6 (R23/R24 "applies per column") needs."""

    def __init__(self, per_column):
        #: ``[(element_id, PlacementResult), ...]``, in the order the
        #: candidates were placed.
        self.per_column = per_column


def collect_candidates(doc, host_element):
    """Every ``OST_StructuralColumns`` instance of the SAME family TYPE as
    ``host_element`` (spec Section 2).

    ``host_element`` is included in the result: the engineer picked it as
    one of the columns to detail by asking for the batch, and there is no
    reason for it to be the one column excluded from its own run.
    """
    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_StructuralColumns)
        .WhereElementIsNotElementType())
    symbol_id = host_element.Symbol.Id
    return [element for element in collector
            if getattr(element, "Symbol", None) is not None
            and element.Symbol.Id == symbol_id]


def read_candidates(doc, elements):
    """Read every candidate through the SAME `read_column` the single-
    column path uses (spec Section 2). A column it refuses is excluded
    here, before any plan is built and before any transaction opens (spec
    Section 5), with its reason kept for the report.
    """
    reads = []
    exclusions = []
    for element in elements:
        try:
            host = read_column(doc, element)
        except ColumnHostError as refusal:
            exclusions.append(Exclusion(
                element_id=element.Id.IntegerValue, reason=str(refusal)))
            continue
        reads.append((element, host))
    return reads, exclusions


def plan_candidates(doc, host_element, inputs):
    """Spec Sections 2/3/5: collect, read and group, plan per column, and
    refuse per column -- everything that must happen BEFORE step 4's
    transaction can open.

    A column `complete_plan`'s plan fails `refuse_if_not_ready` on is
    excluded here too (spec Section 5), by the exact gate the single-
    column placer calls -- never a second opinion about buildability.
    """
    elements = collect_candidates(doc, host_element)
    reads, exclusions = read_candidates(doc, elements)

    candidates = []
    for element, host in reads:
        bars = bar_plan(
            host, inputs.counts, inputs.splice, inputs.bar_diameter_mm,
            inputs.tie_diameter_mm, inputs.bar_type_name,
            inputs.tie_type_name)
        plan = complete_plan(
            bars, inputs.mode, inputs.tie_bend_diameter_mm,
            inputs.tie_subsets_text,
            manual_confinement_mm=inputs.manual_confinement_mm,
            manual_middle_zone_mm=inputs.manual_middle_zone_mm)
        try:
            refuse_if_not_ready(plan)
        except ColumnPlacementError as refusal:
            exclusions.append(Exclusion(
                element_id=element.Id.IntegerValue, reason=str(refusal)))
            continue
        candidates.append(
            ColumnCandidate(element=element, host=host, plan=plan))

    # Grouped from the SURVIVORS, never from every read: R33 makes the
    # group listing the thing a reviewer checks a split by, so a column
    # named in a group must be a column that gets steel. Grouping before
    # the refusal gate would print an excluded column in a group AND in
    # the exclusion list, and the report would contradict itself.
    groups = group_hosts([(candidate.element.Id.IntegerValue, candidate.host)
                          for candidate in candidates])

    return BatchPlan(groups=groups, exclusions=exclusions,
                     candidates=candidates)


def read_existing(doc, batch_plan):
    """Spec Section 6, per column and BEFORE any transaction: this tool's
    own elements on each candidate's host, and the foreign rebar R24
    leaves alone -- through the SAME `existing_elements` the single-column
    path calls.

    R23 says "show the count, then replace", and the spec says that for a
    batch it "is a table". This returns that table's rows; the window
    shows them and asks. The values are also kept on the candidates, so
    :func:`apply_batch` deletes exactly the elements that were counted.
    """
    rows = []
    for candidate in batch_plan.candidates:
        candidate.ours, candidate.foreign = existing_elements(
            doc, candidate.element)
        rows.append(BatchExisting(
            element_id=candidate.element.Id.IntegerValue,
            replaced_count=len(candidate.ours),
            foreign_ids=[found.element_id for found in candidate.foreign]))
    return rows


def apply_batch(doc, batch_plan, bar_type, tie_bar_type, outer_hook_type,
                inner_hook_type):
    """Spec Section 4: ONE transaction for the whole batch, all-or-nothing
    (R25, extended). If every candidate was excluded, the run refuses as a
    whole rather than opening an empty transaction (spec Section 5) --
    checked on ``batch_plan.candidates`` before ``Transaction`` is ever
    constructed, the same "refuse before opening" shape
    `column_placer.refuse_if_not_ready` already uses.
    """
    if not batch_plan.candidates:
        raise ColumnPlacementError(
            "Every candidate column in this batch was excluded -- see the "
            "report. Nothing to place, so no transaction was opened "
            "(spec Section 5).")

    # R25's "everything knowable must be checked before the transaction
    # opens", applied per candidate: `plan_candidates` already ran this
    # gate once (spec Section 5) to decide what belongs in this list, but a
    # caller that reached `apply_batch` directly -- or a defect in that
    # earlier filtering -- must still be unable to open the ONE shared
    # transaction on a plan already known to fail. Run for every candidate
    # BEFORE `Transaction` is constructed, exactly as
    # `column_placer.apply` re-checks a single plan before its own
    # transaction opens.
    for candidate in batch_plan.candidates:
        refuse_if_not_ready(candidate.plan)
        if candidate.ours is None or candidate.foreign is None:
            # R23 again: a caller that never ran `read_existing` never
            # showed the engineer a count, so this run would delete
            # reinforcement nobody confirmed. Refused before the
            # transaction, like every other thing knowable beforehand.
            raise ColumnPlacementError(
                "Column %s: existing reinforcement was never read, so R23's "
                "replacement count was never shown. Call read_existing "
                "before apply_batch." % candidate.element.Id.IntegerValue)

    transaction = Transaction(doc, BATCH_TRANSACTION_NAME)
    transaction.Start()
    try:
        per_column = []
        for candidate in batch_plan.candidates:
            ours, foreign = candidate.ours, candidate.foreign
            for element in ours:
                doc.Delete(element.Id)

            ties_created = column_placer._place_ties_by_role(
                doc, candidate.element, candidate.plan, tie_bar_type,
                outer_hook_type, inner_hook_type)
            bars_created = place_bars(doc, candidate.element, bar_type,
                                      candidate.plan)

            host_id = candidate.element.Id.IntegerValue
            for rebar in ties_created + bars_created:
                tag_as_ours(rebar, host_id)

            per_column.append((host_id, PlacementResult(
                ties_created=ties_created, bars_created=bars_created,
                replaced_count=len(ours), foreign=foreign)))
    except Exception:
        transaction.RollBack()
        raise
    transaction.Commit()

    return BatchPlacementResult(per_column=per_column)
