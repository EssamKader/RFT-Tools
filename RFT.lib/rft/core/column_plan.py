# -*- coding: utf-8 -*-
"""Issue #110 — the one object every consumer of the column reads.

PURE. No Revit, no WPF, no I/O. It composes; it decides nothing. If this
module ever computes a detailing value of its own, it has gone wrong — the
four modules below own those, and the whole point is that they are called
exactly once.

## Why this exists BEFORE there is a placer

The beam tool's costliest defect was `ZONE_LAYOUT_FLAGS` drifting between
the report and the placer, because each consumer independently called the
same underlying logic and the two quietly diverged. The repair was
`rft.core.plan` — one object both read from — and it was written *after*
both consumers existed, which is the expensive way round.

The column has **one** consumer today: the window. There is no placer yet.
So this is written now, while it is a composition rather than a retrofit.
`docs/token-efficient-expansion.md` §7 states the rule; this module is it.

## What "single source" buys that a convention does not

Spec §8 already makes the rule explicit for spacing, and does it as *data*:
``SpacingPlan`` carries BOTH ``s0_mm`` (the code limit) and
``confinement_spacing_mm`` (what will be built), so a violation is visible
on the page the same instant it is true in the model. That guarantee holds
inside one module and is unenforced across four.

R20 is the proof it was needed. It changed what ``validate`` returns for
unchanged inputs — a cross-tie now counts as a leg. Any consumer holding
its own copy of that reasoning would now silently disagree with the report,
and the disagreement would be about whether a column has enough steel.

## The two stages, because the window has two Apply buttons

``bar_plan`` is everything the Longitudinal tab decides; ``complete_plan``
adds everything the Ties tab decides. They are separate because the window
genuinely reaches those states separately, not because the data divides
naturally — a caller that has all the inputs at once simply calls both.
"""

from collections import namedtuple

from .column_layout import perimeter_bar_positions
# MODE_AUTO/MODE_MANUAL are imported, and therefore re-exported, on
# purpose: a caller states a mode TO the plan, and should not have to
# import the module the plan exists to call on its behalf. They are this
# module's inputs, not a second opinion about spacing.
from .column_spacing import (
    FIRST_TIE_OFFSET_MM, MODE_AUTO, MODE_MANUAL, spacing_plan,
)
from .column_tie_levels import tie_levels
from .column_ties import (
    is_blocking, parse_tie_subsets, resolve_ties, tie_report_lines, validate,
)


#: What the Longitudinal tab has settled. Carries the inputs as well as the
#: derived layout: a consumer that has to go back to the window for the bar
#: diameter is a consumer that can be handed a diameter which no longer
#: matches the layout it was given.
BarPlan = namedtuple(
    "BarPlan",
    "host section extent cover_mm counts splice "
    "bar_diameter_mm tie_diameter_mm bar_type_name tie_type_name layout")


#: The complete column: everything that will be BUILT, beside the limits it
#: was judged against. The report, the sketch and the placer read this and
#: call nothing underneath it.
#:
#: ``roof_termination`` is OPTIONAL and defaults to ``None`` (issue #172,
#: R36): an ordinary column has no storey-above condition to state, and an
#: unticked box means section 9's ordinary splice, unchanged. Only a column
#: the engineer has stated is at the top floor carries a
#: :class:`RoofTerminationPlan` here.
ColumnPlan = namedtuple(
    "ColumnPlan",
    "host section extent cover_mm counts splice "
    "bar_diameter_mm tie_diameter_mm tie_bend_diameter_mm "
    "bar_type_name tie_type_name "
    "layout spacing ladder ties findings tie_lines roof_termination")


#: What `specs/column-roof-termination.md` section 4 needs to report a
#: top-floor bar's bend, carried whole rather than recomputed (issue #172).
#:
#: ``termination`` is the one `rft.core.column_roof.RoofTermination`
#: `terminate_bar` decided -- the bend actually taken. ``directions`` are
#: ALL four `rft.core.column_roof.RoofBendDirection` values it chose among,
#: not only the winner: R41's own words are that a short run because the
#: engineer FLAGGED a free edge and a short run the tool MEASURED to a slab
#: edge are different facts, and a reviewer can only tell them apart -- and
#: catch a missed pick -- by seeing every direction's own flagged/defaulted
#: state and available run, not only the one that was chosen.
#:
#: ``floor_label``, ``thickness_mm``, ``cover_mm`` and ``cover_provenance``
#: are `rft.revit.column_roof_slab.read_top_floor_slab`'s own read of the
#: slab (R37, R38), carried as plain values so the report never re-reads
#: the model to say where a number came from.
RoofTerminationPlan = namedtuple(
    "RoofTerminationPlan",
    "termination directions floor_label thickness_mm cover_mm "
    "cover_provenance")


def bar_plan(host, counts, splice, bar_diameter_mm, tie_diameter_mm,
             bar_type_name, tie_type_name):
    """Stage one: the perimeter, from what the Longitudinal tab states.

    ``host`` is the dict :func:`rft.revit.column_host.read_column` returns.
    It is carried whole rather than unpacked because the report's host
    section states things nothing else uses — the search view, the cover
    type's name, whether the top-face cover is set — and a plan that
    dropped them would send the report back to a second source.
    """
    section = host["section"]
    layout = perimeter_bar_positions(
        section.b_mm, section.h_mm, host["cover_mm"],
        tie_diameter_mm, bar_diameter_mm,
        counts.count_b_face, counts.count_h_face)
    return BarPlan(
        host=host,
        section=section,
        extent=host["extent"],
        cover_mm=host["cover_mm"],
        counts=counts,
        splice=splice,
        bar_diameter_mm=bar_diameter_mm,
        tie_diameter_mm=tie_diameter_mm,
        bar_type_name=bar_type_name,
        tie_type_name=tie_type_name,
        layout=layout,
    )


def complete_plan(bars, mode, tie_bend_diameter_mm, tie_subsets_text,
                  manual_confinement_mm=None, manual_middle_zone_mm=None,
                  roof_termination=None):
    """Stage two: spacing, the tie ladder, the stated topology, and §6.1's
    verdict on it.

    Takes the tie box's raw TEXT rather than parsed subsets. Parsing is a
    decision about what the engineer meant, and leaving it to the caller is
    how two callers come to disagree about whether ``1 6`` is a cross-tie.

    Order is the window's, and it is deliberate: spacing first, so a typo
    in the tie box does not discard a valid spacing just entered. Raises
    ``ValueError`` from whichever module objects, with that module's own
    message — this one has nothing to add.

    ``roof_termination`` (issue #172, R36) is an OPTIONAL
    :class:`RoofTerminationPlan`, carried through unexamined -- this module
    decides nothing about it, exactly as it decides nothing about ``ties``.
    Its default of ``None`` IS the ordinary-column case: an unticked
    top-floor box means section 9's ordinary splice, and the plan must
    carry no opinion about a condition nobody stated.
    """
    ladder_inputs = spacing_plan(
        mode,
        clear_height_mm=bars.extent.clear_height_mm,
        narrow_mm=bars.section.narrow_mm,
        wide_mm=bars.section.wide_mm,
        smallest_long_bar_dia_mm=bars.bar_diameter_mm,
        tie_dia_mm=bars.tie_diameter_mm,
        manual_confinement_mm=manual_confinement_mm,
        manual_middle_zone_mm=manual_middle_zone_mm)

    # The BUILT spacings, never the code limits. In Mode B those differ,
    # and a ladder drawn from the maximums lists ties at positions nothing
    # will occupy.
    ladder = tie_levels(bars.extent.clear_height_mm,
                        ladder_inputs.l0_mm,
                        ladder_inputs.confinement_spacing_mm,
                        ladder_inputs.middle_zone_spacing_mm,
                        FIRST_TIE_OFFSET_MM)

    subsets = parse_tie_subsets(tie_subsets_text)
    ties = resolve_ties(subsets, bars.layout,
                        bars.tie_diameter_mm, bars.bar_diameter_mm,
                        tie_bend_diameter_mm)

    return ColumnPlan(
        host=bars.host,
        section=bars.section,
        extent=bars.extent,
        cover_mm=bars.cover_mm,
        counts=bars.counts,
        splice=bars.splice,
        bar_diameter_mm=bars.bar_diameter_mm,
        tie_diameter_mm=bars.tie_diameter_mm,
        tie_bend_diameter_mm=tie_bend_diameter_mm,
        bar_type_name=bars.bar_type_name,
        tie_type_name=bars.tie_type_name,
        layout=bars.layout,
        spacing=ladder_inputs,
        ladder=ladder,
        ties=ties,
        findings=validate(bars.layout, ties),
        # Formatted here, from the ties this object carries. The report's
        # import set is guarded to hold nothing it could compute with, and
        # that guard is right: every value on the page arrives already
        # decided. This is one more of them.
        tie_lines=tie_report_lines(ties),
        roof_termination=roof_termination,
    )


def is_blocked(plan):
    """Whether §6.1 refuses this plan.

    One accessor rather than every consumer reaching for ``plan.findings``
    and applying its own test. The placer's gate and the report's wording
    must agree about this, and the cheapest way to guarantee that is to
    leave them nothing to disagree with.
    """
    return is_blocking(plan.findings)
