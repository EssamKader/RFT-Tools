# -*- coding: utf-8 -*-
"""Issue #120 -- R23/R25 (docs/column/spec-amendments.md, A3, section 13
Placement): the Apply path that wires the ownership layer (#117), the tie
placer (#118) and the bar placer (#119) into one transaction.

Nothing here computes a detailing value or re-derives anything the
composed ``rft.core.column_plan.ColumnPlan`` (#110) already carries -- it
only sequences the ten steps A3 states, in the order A3 states them,
because the order is the ruling ("The order the placer runs in", spec-
amendments.md):

    1. compose the ColumnPlan (#110) -- done by the caller, once, before
       this module is ever reached;
    2. refuse if `is_blocked(plan)`;
    3. refuse any loop failing A1's bend threshold;
    4. find this tool's existing elements by prefix; count foreign
       separately;
    5. if any of ours exist, the CALLER shows R23's dialog and stops on
       Cancel -- a WPF dialog is UI, not this module's job;
    6. open one transaction (R25);
    7. delete the owned elements;
    8. create ties and bars; apply R22's constraints; assert R21's hook
       tails; write R26's Partition;
    9. commit -- or let anything at all roll the whole thing back;
    10. report, naming the foreign rebar R24 left alone.

## Why steps 2 and 3 are checked here too, not left to the modules that
   already check them

`rft.core.column_plan.is_blocked` and `rft.revit.column_place_ties`'s own
`_ensure_buildable` already refuse a bad plan -- but only from INSIDE
`place_ties`, which :func:`apply` calls after its transaction has opened
(step 8). #109 Finding 3 established that an unbuildable loop fails ABOVE
`Rebar.CreateFromCurves`, uncatchable, so `place_ties`'s own check stops
the wrong ELEMENT from being built; it does not stop a transaction from
having opened on a plan already known to fail. A3's ruling is explicit
that steps 2 and 3 happen BEFORE step 6, so :func:`refuse_if_not_ready`
re-runs the SAME comparison `_ensure_buildable` makes -- reading
`tie.narrow_mm` and `tie.min_buildable_mm`, values `ColumnPlan` already
carries, never recomputed from the layout -- as its own gate, and
:func:`apply` calls it again as the first thing inside itself, so no path
into a transaction skips it.

## R23/R24 -- the dialog is the caller's, the count is this module's

Showing a WPF dialog is UI, so this module never shows one.
:func:`existing_elements` returns the ``(ours, foreign)`` split so the
window can decide whether to ask, word the count, and stop on Cancel --
exactly A3's steps 4-5. :func:`apply` (steps 6-10) is only ever called
once the window already has that answer, and takes ``ours``/``foreign``
back in rather than re-reading them, so the count the dialog showed is
the exact set step 7 deletes and the exact set step 10 reports untouched.

## R25 -- the one transaction

:func:`apply` opens ONE `Transaction`, deletes `ours` (step 7), builds the
ties and bars (step 8), tags them (R26), and commits -- or lets any
exception roll the whole thing back (step 9), so a failed rebuild leaves
the ORIGINAL cage in place exactly as A3 requires. Nothing here catches
the tie/bar placers' own exceptions; catching them here would be the
mistake #109 Finding 3 warns against; a caller that swallowed a defect
here would commit a partial, or worse a DELETED-and-never-rebuilt, cage.

## SHAPE UNVERIFIED

``Document.Delete(ElementId)`` (step 7) is one of the oldest, most
standard members of the Revit API -- but it has not been probed against
this project's own live host, and CONTEXT.md's zero-guessing rule draws
no line for "obviously standard". The real member is documented to return
``ICollection<ElementId>`` naming every dependent element also removed;
this module discards that return value and relies only on the fact that
the element it named is gone. See ``tests/fake_revit_api.py``'s header.
"""

from Autodesk.Revit.DB import Transaction

from ..core.column_plan import is_blocked
from ..core.column_ties import KIND_CLOSED_LOOP, describe_subset
from .column_ownership import partition_host_rebar, tag_as_ours
from .column_place_bars import place_bars
from .column_place_ties import place_ties

#: R25: named so the undo menu reads properly -- "the whole cage is ONE
#: transaction: all of it, or none of it" (spec-amendments.md, R25).
TRANSACTION_NAME = "RFT Detail Column"


class ColumnPlacementError(Exception):
    """A plan refused before any transaction opened (A3 steps 2-3)."""


class PlacementResult(object):
    """A3 step 10's report: what was built, how many were replaced, and
    the foreign rebar R24 requires naming."""

    def __init__(self, ties_created, bars_created, replaced_count, foreign):
        self.ties_created = ties_created
        self.bars_created = bars_created
        self.replaced_count = replaced_count
        self.foreign = foreign


def refuse_if_not_ready(plan):
    """A3 steps 2-3: refuse before anything else -- before step 4's read,
    before any dialog, before any transaction.

    Raises :class:`ColumnPlacementError`. Never lets a plan either check
    would have refused reach a transaction: :func:`apply` calls this
    itself, first, so a caller that skipped this gate (or an orchestrator
    bug that called `apply` directly) still cannot open one.
    """
    if is_blocked(plan):
        raise ColumnPlacementError(
            "Section 6.1 blocks this tie arrangement -- Apply refused "
            "before opening a transaction (R25). See the Review tab's "
            "findings.")
    for tie in plan.ties:
        if tie.kind != KIND_CLOSED_LOOP:
            continue
        if tie.narrow_mm < tie.min_buildable_mm:
            raise ColumnPlacementError(
                "Tie %s: narrow dimension %.1f mm is below the %.1f mm A1 "
                "threshold (bend diameter + tie diameter) and cannot be "
                "bent. Refused before any transaction opened -- issue #109 "
                "Finding 3 found this fails above the call site, "
                "uncatchable, so it must never be reached (R25)."
                % (describe_subset(tie.subset), tie.narrow_mm,
                   tie.min_buildable_mm))


def existing_elements(doc, host_element):
    """A3 step 4: this tool's own elements on this host, and the foreign
    rebar R24 leaves alone -- both from ONE read, so R23's count and
    R24's report never come from two queries that could disagree.

    A thin name for `partition_host_rebar` at the placer's own call site,
    not a new computation (#117 already owns the ownership test).
    """
    return partition_host_rebar(doc, host_element)


def _place_ties_by_role(doc, host_element, plan, tie_bar_type,
                        outer_hook_type, inner_hook_type):
    """A3 step 8's tie half, split by role rather than widening
    `place_ties`'s own one-hook-type-per-call signature (#118).

    Section 7 keeps the outer and inner hook pickers "structurally
    separate so one dropdown's selection can never silently apply to the
    other role" -- honoured here by calling the ALREADY-MERGED
    `place_ties` once per role, on a `plan._replace(ties=...)` slice of
    the SAME plan, rather than asking that module to accept two hook
    types or recomputing anything about the ties themselves.

    `plan.ties[0]` is always the outer loop (`rft.core.column_ties`'s own
    convention, already relied on by the window's "No inner ties stated"
    wording); `plan.ties[1:]` are whatever inner subsets were stated.
    """
    created = []
    outer_ties, inner_ties = plan.ties[:1], plan.ties[1:]
    if outer_ties:
        created += place_ties(doc, host_element, plan._replace(ties=outer_ties),
                              tie_bar_type, outer_hook_type)
    if inner_ties:
        created += place_ties(doc, host_element, plan._replace(ties=inner_ties),
                              tie_bar_type, inner_hook_type)
    return created


def apply(doc, host_element, plan, ours, foreign, bar_type, tie_bar_type,
         outer_hook_type, inner_hook_type):
    """A3 steps 6-10, all inside ONE transaction (R25).

    ``ours``/``foreign`` are exactly what :func:`existing_elements`
    already returned to the caller for R23's dialog -- passed back in
    rather than re-read, so the count the engineer saw and the set this
    deletes are the same query, and the foreign rebar this reports is the
    same list R24 required the caller to have already left alone.

    Deletion, rebuild and tagging are all inside the transaction, so an
    exception ANYWHERE in this block -- including one this module cannot
    predict, per #109 Finding 3 -- rolls back the deletions along with the
    rebuild and leaves the original cage exactly as it was (R25's whole
    point). Nothing here narrows the ``except`` or inspects the exception:
    narrowing it is exactly the mistake that would let an unexpected
    failure commit a partial cage.
    """
    refuse_if_not_ready(plan)

    transaction = Transaction(doc, TRANSACTION_NAME)
    transaction.Start()
    try:
        for element in ours:
            doc.Delete(element.Id)

        ties_created = _place_ties_by_role(
            doc, host_element, plan, tie_bar_type,
            outer_hook_type, inner_hook_type)
        bars_created = place_bars(doc, host_element, bar_type, plan)

        host_id = host_element.Id.IntegerValue
        for rebar in ties_created + bars_created:
            tag_as_ours(rebar, host_id)
    except Exception:
        transaction.RollBack()
        raise
    transaction.Commit()

    return PlacementResult(
        ties_created=ties_created,
        bars_created=bars_created,
        replaced_count=len(ours),
        foreign=foreign,
    )
