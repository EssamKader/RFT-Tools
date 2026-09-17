# -*- coding: utf-8 -*-
"""Section 6.2's tie topology, and the rules that judge it (issue #89).

PURE. Subsets in, resolved ties and verdicts out.

## The model, settled by R4 and R17

**The user states the topology; this module validates it.** R4 (#71) chose
that over auto-derivation because §6.1 admits many valid coverings of the
same layout and the spec has no tie-break rule between them -- so deriving
one would mean inventing the rule. R17 (#89) then settled the control:
**direct subset entry**, in §6.2's own terms, with no template catalogue.

A tie is therefore ``TieSubset(start_index, count)``: an initial bar index
and how many consecutive bars around the perimeter it encloses, matching
the CADS Rebar convention §6.2 names. Subsets WRAP -- a tie may start at
bar 8 of 10 and enclose bars 8, 9, 0, 1.

## A1: closed loop where buildable, cross-tie only where it is not

A closed loop whose narrow dimension is under the tie's bend diameter is
geometrically unsolvable, and Revit refuses it with a **modal dialog that
blocks the whole session** -- not a catchable exception. So the test runs
here, before any API call::

    buildable  <=>  narrow dimension >= bend diameter + tie diameter

The bend diameter is READ from the ``RebarBarType``
(``StirrupTieBendDiameter``), never assumed as a multiple of the bar
diameter: the live model's 10M reads 40.00 mm against a 9.50 mm bar, which
is 4.2x, while its 19M reads 115.00 against 19.10, which is 6.0x. A
constant multiplier would be wrong for most of the range.

Failing that test is the **sole** permitted trigger for a cross-tie --
never tidiness, simplicity or preference.

## What "restrained" means, stated because the spec's phrase is short

§6.1 says a bar must be "restrained by a tie corner or an inner tie leg".
This module reads that as: a bar is restrained when it sits at a **corner
of some tie's rectangle**, or at an **end of a cross-tie**.

A bar merely *inside* a tie's rectangle is not restrained by it. That is
not a narrow reading -- it is the whole reason inner ties exist. The outer
perimeter tie has only four corners, so on a ten-bar column it restrains
four bars and leaves six for the inner ties, which is exactly the situation
Figure 13-3's sections are drawn to solve.
"""

from collections import namedtuple

from .column_layout import (
    TIER_ALTERNATE, TIER_EVERY_BAR, TIER_EXCEEDED, MAX_TIE_BRANCH_SPACING_MM,
    worst_gap,
)

KIND_CLOSED_LOOP = "closed loop"
KIND_CROSS_TIE = "cross-tie"

#: Tolerance for "is this bar at that corner". Bar positions are tens of
#: millimetres apart, so this only has to survive float arithmetic.
COINCIDENT_TOL_MM = 1.0e-6

#: A tie, as the bars it touches. R19 (supersedes R17's "start + count").
#:
#: R17 was right that the engineer states the topology and the tool never
#: derives it. It was wrong about the alphabet. "Start plus count" can only
#: name a CONTIGUOUS run of the perimeter, and the commonest inner tie of
#: all -- a cross-tie from one mid-face bar straight across to the one
#: opposite -- is not contiguous. On the live 450x600 column, bars 1 and 6
#: face each other across the width; every cross-tie the old notation could
#: express joined bars ADJACENT on the same face, 25.4 mm apart, which is
#: not a detail anybody draws.
#:
#: A plain list of bar numbers says everything the old form said (a run is
#: just a list) and says the thing it could not. Order is kept as typed:
#: for a cross-tie the first and last entries are its two ends.
TieSubset = namedtuple("TieSubset", "indices")

#: A subset resolved into geometry and judged. ``half_u``/``half_v`` are
#: the CENTRELINE half-dimensions -- what ``CreateFromCurves`` takes.
#: ``reason`` is empty for a closed loop and names the failed bend test for
#: a cross-tie, so the report never shows a cross-tie without saying why.
#:
#: ``vertices`` (#140) is the centreline polygon the tie's steel actually
#: follows, in order: a closed loop's four corners, or a cross-tie's two
#: end points. It exists so ``resolve_tie``'s own corner math,
#: ``rft.ui.column_sketch``'s tie drawing and
#: ``rft.revit.column_place_ties``'s curve builder read ONE object instead
#: of each re-deriving the same four numbers into corners -- the thing
#: #140 was filed to stop. ``half_u_mm``/``half_v_mm`` stay: A1's narrow
#: test and the report still read them, and they are still the right
#: description of a rectangle. This only stops them being the sole way to
#: know where the steel goes.
ResolvedTie = namedtuple(
    "ResolvedTie",
    "subset kind enclosed_indices restrained_indices "
    "centre_u_mm centre_v_mm half_u_mm half_v_mm narrow_mm "
    "min_buildable_mm reason vertices")

Finding = namedtuple("Finding", "severity message")

SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"


def describe_subset(subset):
    """A subset in the words the user typed, for a message."""
    return " ".join(str(i) for i in subset.indices)


def subset_indices(subset, bar_count):
    """The bar indices a tie touches, validated.

    No wrapping arithmetic any more: the list IS the answer. What remains
    is checking it, and every check below is a mistake that is easy to make
    by typing and impossible to see in the result.
    """
    indices = list(subset.indices)
    if len(indices) < 2:
        raise ValueError(
            "A tie must touch at least 2 bars -- %r names %d. A one-bar tie "
            "has no geometry."
            % (describe_subset(subset), len(indices)))
    if len(indices) > bar_count:
        raise ValueError(
            "A tie cannot touch %d bars: the perimeter has %d."
            % (len(indices), bar_count))
    for index in indices:
        if not (0 <= index < bar_count):
            raise ValueError(
                "Bar index %d is outside the perimeter's 0..%d."
                % (index, bar_count - 1))
    if len(set(indices)) != len(indices):
        repeated = sorted(set(i for i in indices if indices.count(i) > 1))
        raise ValueError(
            "%r names bar %s twice. A tie touches each bar once; a repeat "
            "is a typo that would otherwise pass silently, because a "
            "bounding box does not care how often a corner is named."
            % (describe_subset(subset),
               ", ".join(str(i) for i in repeated)))
    return indices


def outer_perimeter_subset(bar_count):
    """The tie that wraps everything. Always present, never entered by the
    user: every column has one, and asking for it would be asking the
    engineer to state the obvious before they can state anything else.
    """
    return TieSubset(indices=tuple(range(bar_count)))


def minimum_buildable_narrow_mm(bend_diameter_mm, tie_dia_mm):
    """A1's threshold: ``bend diameter + tie diameter``."""
    return bend_diameter_mm + tie_dia_mm


def is_buildable(tie):
    """A1: whether this tie's loop can physically be bent.

    PURE, and the only place the comparison is made. It was written twice
    -- once in the tie placer's own pre-check, once in the Apply path's
    gate -- because both must refuse before offering anything to Revit
    (#109 Finding 3: an unbendable loop fails ABOVE the call site and is
    not catchable). Two copies of one detailing decision is how the beam
    tool's ZONE_LAYOUT_FLAGS drifted, so it is asked here and nowhere
    else.

    A cross-tie has no loop to bend, so the threshold does not apply to
    it -- its narrow dimension is below the minimum BY DESIGN, and gating
    it would refuse exactly the detail A1 exists to permit.
    """
    if tie.kind != KIND_CLOSED_LOOP:
        return True
    return tie.narrow_mm >= tie.min_buildable_mm


def resolve_tie(subset, layout, tie_dia_mm, bar_dia_mm, bend_diameter_mm):
    """One subset, turned into a rectangle and judged against A1.

    The rectangle is the bounding box of the enclosed bars' centrelines,
    grown by half a bar plus half a tie -- the tie's centreline wraps
    outside the bars it holds.
    """
    indices = subset_indices(subset, len(layout.bars))
    bars = [layout.bars[i] for i in indices]
    us = [bar.u_mm for bar in bars]
    vs = [bar.v_mm for bar in bars]

    grow = bar_dia_mm / 2.0 + tie_dia_mm / 2.0
    half_u = (max(us) - min(us)) / 2.0 + grow
    half_v = (max(vs) - min(vs)) / 2.0 + grow
    centre_u = (max(us) + min(us)) / 2.0
    centre_v = (max(vs) + min(vs)) / 2.0

    narrow = min(2.0 * half_u, 2.0 * half_v)
    minimum = minimum_buildable_narrow_mm(bend_diameter_mm, tie_dia_mm)

    if narrow >= minimum:
        kind = KIND_CLOSED_LOOP
        reason = ""
        # The tie's own centreline polygon (#140's `vertices`) -- the same
        # four corners `rft.ui.column_sketch` and
        # `rft.revit.column_place_ties` have always drawn/placed from
        # `centre`/`half` alone, wound so consecutive entries share an
        # edge (the hook-overlap corner both hooks attach to).
        vertices = [(centre_u - half_u, centre_v - half_v),
                    (centre_u + half_u, centre_v - half_v),
                    (centre_u + half_u, centre_v + half_v),
                    (centre_u - half_u, centre_v + half_v)]
        # A bar is restrained where it sits at one of the tie's corners --
        # but a CORNER BAR sits at the un-grown bounding-box extreme, not
        # on the tie's own (grown) centreline: `grow` is subtracted back
        # off each corner of `vertices` to land on the bar itself. This is
        # deliberately a SEPARATE list from `vertices`: the two answer
        # different questions (where the steel runs vs. where a bar
        # restrained by it sits) and #140 does not collapse them into one.
        corner_bar_uv = [(centre_u - half_u + grow, centre_v - half_v + grow),
                         (centre_u + half_u - grow, centre_v - half_v + grow),
                         (centre_u + half_u - grow, centre_v + half_v - grow),
                         (centre_u - half_u + grow, centre_v + half_v - grow)]
        # Scanned over EVERY bar, not only the enclosed ones. A subset's
        # bounding box can put a corner on a bar the subset does not name,
        # and that bar is still inside the bend -- it is restrained by the
        # geometry, not by the bookkeeping. Checking only `bars` missed
        # one on the first layout this was run against.
        restrained = [bar.index for bar in layout.bars
                      if any(abs(bar.u_mm - cu) < COINCIDENT_TOL_MM
                             and abs(bar.v_mm - cv) < COINCIDENT_TOL_MM
                             for cu, cv in corner_bar_uv)]
    else:
        kind = KIND_CROSS_TIE
        reason = (
            "narrow dimension %.1f mm is below the %.1f mm a %.1f mm bend "
            "plus a %.1f mm tie needs, so a closed loop cannot be bent "
            "(A1). Revit refuses this with a modal dialog, not an "
            "exception, so it is never attempted."
            % (narrow, minimum, bend_diameter_mm, tie_dia_mm))
        # A cross-tie is a single leg between the subset's two extreme
        # bars, and restrains exactly those two. Its `vertices` are those
        # same two bars' own centrelines -- not the grown bounding box
        # `centre`/`half` describe -- because a cross-tie's steel runs bar
        # to bar, matching what
        # `rft.revit.column_place_ties._cross_tie_uv_segments_mm` has
        # always built the placed curve from.
        restrained = [bars[0].index, bars[-1].index]
        vertices = [(bars[0].u_mm, bars[0].v_mm),
                    (bars[-1].u_mm, bars[-1].v_mm)]

    return ResolvedTie(
        subset=subset, kind=kind, enclosed_indices=indices,
        restrained_indices=sorted(set(restrained)),
        centre_u_mm=centre_u, centre_v_mm=centre_v,
        half_u_mm=half_u, half_v_mm=half_v,
        narrow_mm=narrow, min_buildable_mm=minimum, reason=reason,
        vertices=vertices)


def resolve_ties(subsets, layout, tie_dia_mm, bar_dia_mm, bend_diameter_mm):
    """Every subset resolved, the outer perimeter tie first.

    The outer tie is prepended here rather than expected in ``subsets``:
    it is implied by the column, not chosen, and making the caller supply
    it is how one caller eventually forgets.
    """
    all_subsets = [outer_perimeter_subset(len(layout.bars))] + list(subsets)
    return [resolve_tie(subset, layout, tie_dia_mm, bar_dia_mm,
                        bend_diameter_mm)
            for subset in all_subsets]


def restrained_bar_indices(ties):
    restrained = set()
    for tie in ties:
        restrained |= set(tie.restrained_indices)
    return restrained


def _unrestrained_runs(bar_count, restrained):
    """Consecutive runs of unrestrained bars, around the perimeter.

    A run, not a count: the ``x <= 150`` tier permits alternating bars, so
    ONE unrestrained bar between two restrained ones is legal and TWO in a
    row is not. Counting unrestrained bars would confuse the two.
    """
    runs = []
    current = []
    for step in range(bar_count * 2):
        index = step % bar_count
        if index in restrained:
            if current:
                runs.append(current)
                current = []
        else:
            current.append(index)
        if step >= bar_count and not current:
            break
    if current:
        runs.append(current)
    # De-duplicate the wrap: a run can be found twice by the double pass.
    unique = []
    seen = set()
    for run in runs:
        key = tuple(sorted(run))
        if key not in seen:
            seen.add(key)
            unique.append(run)
    return unique


def validate(layout, ties):
    """Section 6.1, applied to a topology the user built.

    Returns a list of :class:`Finding`. Blocking findings are layouts the
    spec does not permit; warnings are things worth seeing that it does.

    Positions are the IDEALISED ones, per R18 -- and that is the
    conservative direction, not merely the available one. R15's snap moves
    a corner bar inboard on both axes, toward its own mid-face neighbours,
    so real clear distances are SMALLER than these. A validator reading
    idealised positions can demand restraint that proves unnecessary; it
    can never miss restraint that was needed.
    """
    findings = []
    gap = worst_gap(layout)
    restrained = restrained_bar_indices(ties)
    unrestrained = [bar.index for bar in layout.bars
                    if bar.index not in restrained]

    if gap is not None and gap.tier == TIER_EXCEEDED:
        findings.append(Finding(SEVERITY_BLOCKING,
            "Widest clear distance %.0f mm exceeds 250 mm. Section 6.1 does "
            "not cover a gap this wide, whatever the tie arrangement -- add "
            "intermediate bars." % gap.clear_mm))
    elif gap is not None and gap.tier == TIER_EVERY_BAR:
        if unrestrained:
            findings.append(Finding(SEVERITY_BLOCKING,
                "Clear distance %.0f mm is above 150 mm, so section 6.1 "
                "requires EVERY bar to be restrained. These are not: %s."
                % (gap.clear_mm, ", ".join(str(i) for i in unrestrained))))
    elif gap is not None and gap.tier == TIER_ALTERNATE:
        runs = [run for run in _unrestrained_runs(len(layout.bars), restrained)
                if len(run) > 1]
        if runs:
            findings.append(Finding(SEVERITY_BLOCKING,
                "Section 6.1 permits ALTERNATE bars to be left untied at "
                "this spacing, but these runs leave consecutive bars "
                "unrestrained: %s."
                % "; ".join("bars " + ", ".join(str(i) for i in run)
                            for run in runs)))
        if len(restrained) == len(layout.bars):
            findings.append(Finding(SEVERITY_WARNING,
                "Every bar is restrained. Section 6.1 permits alternate "
                "bars to be left untied at this spacing, so some of these "
                "ties may be more than the code requires."))

    findings.extend(_branch_spacing_findings(layout, ties))

    for tie in ties:
        if tie.kind == KIND_CROSS_TIE:
            findings.append(Finding(SEVERITY_WARNING,
                "Tie %s is a CROSS-TIE: %s"
                % (describe_subset(tie.subset), tie.reason)))
    return findings


def _branch_spacing_findings(layout, ties):
    """Section 6.1's other limit: never more than 300 mm between two tie
    branches.

    Evaluated per axis on the tie legs' own coordinates, and including the
    concrete faces is deliberately NOT done -- the rule is about branches,
    and a face is not one.
    """
    findings = []
    for axis, label in ((0, "vertical legs (u)"), (1, "horizontal legs (v)")):
        coords = set()
        for tie in ties:
            centre = tie.centre_u_mm if axis == 0 else tie.centre_v_mm
            half = tie.half_u_mm if axis == 0 else tie.half_v_mm
            if tie.kind == KIND_CROSS_TIE:
                # R20. A cross-tie is a single bar, not a rectangle, so it
                # contributes ONE coordinate rather than two -- and only on
                # the axis it is thin across. The cross-tie from bar 1 to
                # bar 6 runs the full height at u = 0: that is a vertical
                # leg at u = 0, and nothing at all horizontally.
                #
                # Skipping cross-ties entirely (the behaviour until this
                # ticket) meant the 300 mm rule could only ever be met by
                # NESTED CLOSED LOOPS, so the tool pushed the engineer away
                # from the detail they would actually draw toward heavier
                # ones. Found by detailing a real column with it.
                other_half = tie.half_v_mm if axis == 0 else tie.half_u_mm
                if half <= other_half:
                    coords.add(round(centre, 6))
                continue
            coords.add(round(centre - half, 6))
            coords.add(round(centre + half, 6))
        ordered = sorted(coords)
        for lower, upper in zip(ordered, ordered[1:]):
            if upper - lower > MAX_TIE_BRANCH_SPACING_MM:
                findings.append(Finding(SEVERITY_BLOCKING,
                    "%.0f mm between two %s exceeds the %.0f mm maximum "
                    "(section 6.1)." % (upper - lower, label,
                                        MAX_TIE_BRANCH_SPACING_MM)))
    return findings


def is_blocking(findings):
    return any(f.severity == SEVERITY_BLOCKING for f in findings)


def tie_report_lines(ties):
    """Per tie: what it encloses, which bars it restrains, and -- for a
    cross-tie -- that the bend test is why.

    #91 had to leave this section saying "not guessed here". It can be
    written now.
    """
    lines = []
    for position, tie in enumerate(ties):
        label = "Outer perimeter tie" if position == 0 else (
            "Tie %s" % describe_subset(tie.subset))
        lines.append(
            "%s: %s, encloses %d bars (%s), restrains %s. Narrow dimension "
            "%.1f mm against a %.1f mm minimum."
            % (label, tie.kind, len(tie.enclosed_indices),
               ", ".join(str(i) for i in tie.enclosed_indices),
               ", ".join(str(i) for i in tie.restrained_indices) or "none",
               tie.narrow_mm, tie.min_buildable_mm))
        if tie.reason:
            lines.append("    " + tie.reason)
    return lines


def parse_tie_subsets(text):
    """Subsets from the text the engineer types, one tie per line.

    ``"1 6"`` or ``"1,6"`` -- the bar numbers the tie touches (R19).
    ``"1 6"`` is a cross-tie from bar 1 straight across to bar 6;
    ``"0 1 2 3"`` is a loop around those four. Blank lines and ``#``
    comments are ignored, so a topology can be annotated and pasted
    between columns.

    A TEXT control rather than a list widget with add/remove buttons: the
    whole topology is visible and editable at once, it copies between
    columns, and it needs no widget state to stay in step with the model.
    R17 chose subset entry precisely because it has no catalogue to
    maintain; a control with its own hidden state would put one back.

    Raises ``ValueError`` naming the LINE, because "invalid input" on a
    six-line topology is not a message anybody can act on.
    """
    subsets = []
    for number, raw in enumerate(text.splitlines(), start=1):
        line = raw.split("#", 1)[0].strip()
        if not line:
            continue
        parts = [p for p in line.replace(",", " ").split() if p]
        if len(parts) < 2:
            raise ValueError(
                "Line %d (%r): a tie is the bar numbers it touches, at "
                "least two -- '1 6' is a cross-tie from bar 1 to bar 6, "
                "'0 1 2 3' is a loop around those four."
                % (number, raw.strip()))
        try:
            indices = tuple(int(p) for p in parts)
        except ValueError:
            raise ValueError(
                "Line %d (%r): every value must be a whole bar number."
                % (number, raw.strip()))
        subsets.append(TieSubset(indices=indices))
    return subsets


def format_tie_subsets(subsets):
    """The inverse, for restoring what was typed."""
    return "\n".join(describe_subset(s) for s in subsets)
