# -*- coding: utf-8 -*-
"""The Review report (issue #91) — the page read before pressing Place.

PURE. Values in, lines of text out. No Revit, no WPF: the report is a list
of ``(heading, [lines])`` sections and the window renders it, so the whole
page is testable under plain CPython and the wording is checkable line by
line.

## The rule the page exists to keep

The report and the placer are fed by the SAME computation engine
(`REUSE_GUIDELINES.md` §1), so they cannot disagree. Everything here is
read off a ``SpacingPlan``, a ``TieLadder`` and the host read -- nothing is
recomputed. A number this module derived itself would be a second source
of truth wearing the report's authority.

## What this module deliberately does NOT claim

One of #91's three headline items still cannot be written, and it is
STATED as missing rather than omitted:

**As-built bar positions (R15).** #80 measured a corner bar asked for
`-167.55` landing at `-164.02`: it binds to the tie's bend, the position
cannot be dictated (``SetDistanceToTargetRebar`` throws on a ``HookBend``
target), and it must be read back AFTER placement. There is no placer
yet, so there is nothing to read back. The report says the coordinates it
shows are idealised and will move.

Silence on that would read as "there is nothing to say", which is the
failure `REUSE_GUIDELINES.md` §3 exists to prevent.

#91's OTHER missing item -- loop vs cross-tie per restrained bar (A1) --
is written now. #89 answered Q11, and :func:`tie_section` states per tie
what it is, what it encloses, which bars it restrains, and for a
cross-tie that the bend test is why.

`rft.ui.report` is not reused -- beam sections, faces and zones
throughout. What transfers is ``rft.ui.derivation``'s *pattern*: state the
derivation in words beside the number.
"""

from collections import namedtuple

from .column_spacing import MODE_MANUAL
from .column_ties import SEVERITY_BLOCKING

ReportSection = namedtuple("ReportSection", "heading lines")

#: Marks a line the engineer must act on or accept -- the Mode B flags and
#: the two "not available yet" statements. The window paints these; the
#: prefix is here so the report reads the same as plain text.
FLAG_PREFIX = "!! "
NOTE_PREFIX = "-- "


def _mm(value):
    return "%.0f mm" % value


def host_section(data):
    """What was read off the element, with where each number came from.

    R5/R6: "2700 from a soffit" and "2700 from a level elevation" are
    different claims, so the source travels with every one of them. A2:
    cover is labelled as READ, never as an input, because it is not one.
    """
    section = data["section"]
    extent = data["extent"]
    base_name, base_z = data["base_level"]
    top_name, top_z = data["top_level"]
    lines = [
        "Column %s -- %s : %s" % (data["element_id"], data["family_name"],
                                  data["type_name"]),
        "Section b x h: %s x %s (b along HandOrientation, h along "
        "FacingOrientation, both from the type parameters -- never the "
        "bounding box)" % (_mm(section.b_mm), _mm(section.h_mm)),
        "Governing dimensions: narrow %s governs S0 (section 4), wide %s "
        "governs L0 (section 3)" % (_mm(section.narrow_mm),
                                    _mm(section.wide_mm)),
        "Cover: %s -- READ from the element's 'Rebar Cover - Other Faces' "
        "(cover type '%s'). Amendment A2: never typed into this tool, "
        "never defaulted to 25." % (_mm(data["cover_mm"]),
                                    data["cover_type_name"]),
        "Base: %s, from the %s (level %s at %s)"
        % (_mm(extent.base_z_mm), extent.base_source, base_name, _mm(base_z)),
        "Top: %s, from the %s (level %s at %s)"
        % (_mm(extent.top_z_mm), extent.top_source, top_name, _mm(top_z)),
        "Clear height Hc: %s -- measured top to base, NOT the Length "
        "parameter, which reads level to level and differs by the slab "
        "thickness." % (_mm(extent.clear_height_mm)),
    ]
    if extent.base_source != "support face":
        lines.append(
            NOTE_PREFIX + "No support element was found below this column, "
            "so the base datum is the level elevation (R6). That is normal "
            "for a ground-floor column -- case C1, foundation dowels out of "
            "scope.")
    if not data["top_face_cover_is_set"]:
        lines.append(
            NOTE_PREFIX + "'Rebar Cover - Top Face' is not set on this "
            "element. Nothing here depends on it; reported because open "
            "question Q5 has not been answered.")
    return ReportSection("Column", lines)


def longitudinal_section(bars, splice, bar_type_name, bar_diameter_mm,
                         splice_line):
    """Section 1's counts and section 9's `L_s`.

    R5's ruling is stated OUT LOUD: there is no bottom `L_s`. Its absence
    on a ground-floor column is a decision, and an unexplained absence
    reads as an omission every time somebody checks the drawing.
    """
    return ReportSection("Longitudinal bars", [
        "Bar type: %s (diameter %.2f mm, read from the type -- a bar "
        "type's NAME routinely disagrees with its diameter)"
        % (bar_type_name, bar_diameter_mm),
        "Bars per b-face: %d (including its two corner bars)"
        % bars.count_b_face,
        "Bars per h-face: %d (including its two corner bars)"
        % bars.count_h_face,
        "Total: %d bars -- 2 x (%d + %d) - 4. The four corner bars are "
        "SHARED between faces and counted once, not twice."
        % (bars.total_count, bars.count_b_face, bars.count_h_face),
        splice_line,
        "Splice position: the lap starts at the TOP FACE of the support "
        "and lies inside the upper segment's lower L0. Section 9's "
        "constructability override -- a conscious deviation from the "
        "mid-height rule, to match floor-by-floor pouring joints.",
        "No bottom Ls. Bars start at this floor level and protrude Ls "
        "above the top support only (R5). The absence at the base is a "
        "ruling, not an omission.",
    ])


def spacing_section(plan):
    """Sections 3, 4, 5 and 8, with the minima that governed each.

    Mode B's flags appear HERE, beside the limit they exceed, because
    section 8 requires the code-calculated limit shown "ALONGSIDE the
    user's manual value". A flag on a different page is a flag that gets
    read after the fact.
    """
    lines = [
        "Confinement zone L0: %s -- max of %s (section 3)"
        % (_mm(plan.l0_mm),
           ", ".join("%s %s" % (c.label, _mm(c.value_mm))
                     for c in plan.l0_candidates)),
        "Code maximum S0: %s -- governed by '%s', the smallest of %s "
        "(section 4)"
        % (_mm(plan.s0_mm), plan.s0_governing_label,
           ", ".join(_mm(c.value_mm) for c in plan.s0_candidates)),
        "Middle-zone maximum: %s -- 2 x S0 (section 5). There is no "
        "independent 150 mm cap here; that figure belongs to a different "
        "rule." % _mm(plan.middle_zone_max_mm),
        "First tie: exactly 50 mm from each support face (section 4) -- a "
        "placement, not a maximum.",
    ]
    if plan.mode == MODE_MANUAL:
        lines.append(
            "Spacing mode: B (manual override). The values below are the "
            "ones that will be BUILT.")
    else:
        lines.append(
            "Spacing mode: A (auto). The code maximums above are the "
            "values that will be built.")
    lines.append("Confinement spacing to be built: %s"
                 % _mm(plan.confinement_spacing_mm))
    lines.append("Middle-zone spacing to be built: %s"
                 % _mm(plan.middle_zone_spacing_mm))
    for flag in plan.flags:
        lines.append(FLAG_PREFIX + flag.message)
    return ReportSection("Tie spacing", lines)


def tie_level_section(ladder):
    """The ladder, and which levels section 6.3 mirrors.

    Levels are listed rather than summarised: the count and the mirror
    pattern are the two things an engineer checks against a section, and
    "16 ties, alternating" cannot be checked against anything.
    """
    lines = [
        "%d tie levels: %d in the bottom confinement zone, %d in the "
        "middle, %d in the top." % (len(ladder.levels), ladder.bottom_count,
                                    ladder.middle_count, ladder.top_count),
        "Middle-zone ties are divided EQUALLY at %s, which is at or under "
        "the maximum -- rather than stepped from one end and left with a "
        "short final bay." % _mm(ladder.middle_spacing_mm),
        "Hook corner alternates between consecutive levels (section 6.3). "
        "Mirrored levels are marked M.",
        # R32. Stated unconditionally because it is a RULE, not a fact
        # about this ladder -- the ladder does not know what shapes the
        # ties are, and the mirror map it carries is the same either way.
        # Saying it here stops the line above reading as a promise the
        # triangles do not keep.
        "A TRIANGLE does not alternate (R32): its closure stays at the "
        "apex on every level. The mirror applies to closed loops, whose "
        "four corners give it somewhere to alternate to.",
    ]
    for level in ladder.levels:
        lines.append("  %2d  %8s  %-22s %s"
                     % (level.index, _mm(level.z_mm), level.zone,
                        "M" if level.mirrored else ""))
    lines.append(
        NOTE_PREFIX + "The alternation is ONE rebar set plus a per-bar "
        "transform, applied after the final layout is set. Any later "
        "layout change silently scrambles it unless the whole mirror map "
        "is reset and re-applied (issue #70).")
    return ReportSection("Tie levels", lines)


def tie_section(findings, tie_lines):
    """Section 6.2's topology as stated, and section 6.1's verdict on it.

    #91 had to leave this saying "not guessed here". #89 answered Q11 --
    the engineer states the subsets, the tool validates them -- so the
    page can now say, per tie, what it is and which bars it holds.

    The findings come first. A topology that section 6.1 refuses is the
    thing to read, and putting it under a list of tie geometry is how it
    gets skimmed past.
    """
    lines = []
    for finding in findings:
        prefix = FLAG_PREFIX if finding.severity == SEVERITY_BLOCKING \
            else NOTE_PREFIX
        lines.append(prefix + finding.message)
    if not findings:
        lines.append("Section 6.1: every requirement met by this "
                     "arrangement.")
    lines.append("")
    lines.extend(tie_lines)
    lines.append(
        "Tie arrangement is STATED by the engineer, not derived (R4, R17). "
        "Section 6.1 admits many valid coverings of one bar layout and the "
        "spec has no rule to choose between them, so the tool validates "
        "rather than invents.")
    return ReportSection("Ties (section 6.2)", lines)


def outstanding_section():
    """What this report still cannot say, said plainly.

    One entry now. #89 closed the other. Omitting what remains would make
    the page look complete, and a report that looks complete is trusted as
    complete -- so this section is asserted never to be empty.
    """
    return ReportSection("Not yet reported", [
        NOTE_PREFIX + "AS-BUILT POSITIONS (R15). Bar coordinates shown "
        "anywhere in this tool are IDEALISED. A corner bar binds to the "
        "tie's bend and moves: one measured live was asked for -167.55 and "
        "landed at -164.02, and the position cannot be dictated. Real "
        "positions must be read back after placement, and nothing is "
        "placed yet.",
        NOTE_PREFIX + "Section 6.1 is validated on those idealised "
        "positions, and that is the CONSERVATIVE direction (R18): the snap "
        "moves a corner bar toward its own neighbours, so real clear "
        "distances are SMALLER than the ones checked. This can demand "
        "restraint that proves unnecessary; it cannot miss restraint that "
        "was needed.",
    ])


def roof_termination_section(roof):
    """`specs/column-roof-termination.md` section 4 (issue #172).

    ``roof`` is a `rft.core.column_plan.RoofTerminationPlan` -- one object,
    so nothing here is recomputed. A reviewer must be able to catch a
    missed pick by READING this, not by finding a stray bar in the model,
    so EVERY direction is named, not only the one the bend took.
    """
    t = roof.termination
    if roof.cover_provenance == "read":
        cover_line = "READ from %s (R38)" % roof.floor_label
    else:
        cover_line = ("TYPED -- %s's own cover reads zero, which R38 "
                     "treats as nobody having set one" % roof.floor_label)
    lines = [
        "Top-floor slab: %s -- thickness %s (R37)"
        % (roof.floor_label, _mm(roof.thickness_mm)),
        "Slab cover: %s -- %s" % (_mm(roof.cover_mm), cover_line),
    ]
    for direction in roof.directions:
        taken = " -- BEND TAKEN" if direction.name == t.direction else ""
        if direction.has_slab:
            lines.append(
                "  %s -- DEFAULTED: slab assumed to continue -- available "
                "run %s, MEASURED to the slab edge (R41/R42)%s"
                % (direction.name, _mm(direction.available_run_mm), taken))
        else:
            lines.append(
                "  %s -- FLAGGED free edge (the engineer's own statement, "
                "section 3) -- available run %s, the column's OWN WIDTH at "
                "this face (section 2's b_E cap)%s"
                % (direction.name, _mm(direction.available_run_mm), taken))
    lines.append(
        "Bend taken: %s -- vertical leg a %s, horizontal leg b %s (nominal "
        "legs handed to the API, R40)"
        % (t.direction, _mm(t.a_mm), _mm(t.b_mm)))
    lines.append(
        "Achieved development: %s of %s L_D required -- the BUILT bar's "
        "centreline length after Revit's %.1f mm fillet loss (R40), never "
        "the nominal legs" % (_mm(t.achieved_mm), _mm(t.ld_mm), t.bend_loss_mm))
    if t.shortfall_mm > 0.0:
        lines.append(
            FLAG_PREFIX + "Shortfall: %s short of full L_D, because %s "
            "limited the run to what fits (R41)."
            % (_mm(t.shortfall_mm),
               "the FLAGGED free edge" if t.free_edge else
               "the MEASURED slab edge"))
    else:
        lines.append("No shortfall -- the full L_D was achieved.")
    return ReportSection("Top-floor termination", lines)


def batch_group_section(groups):
    """Issue #153 / R33: name every group and its clear height, and which
    columns fell in it.

    R33's ruling is that a split TYPE is placed, not refused -- "the report
    carries the burden instead" (spec-amendments.md). This is the sentence
    that carries it: a reviewer must see that one selection produced more
    than one cage by READING this, not by noticing a tie count in a 3D view.
    """
    lines = []
    if not groups:
        lines.append(
            "No group was formed -- every candidate column was excluded "
            "(see 'Excluded columns' below).")
    for index, group in enumerate(groups, start=1):
        support = ("a top support was found" if group.key.top_support_found
                   else "no top support was found (level elevation used)")
        lines.append(
            "Group %d -- clear height %s, %s -- column(s): %s"
            % (index, _mm(group.key.clear_height_mm), support,
               ", ".join(str(element_id)
                        for element_id in group.element_ids)))
    return ReportSection("Batch groups", lines)


def batch_exclusion_section(exclusions):
    """Issue #153 / spec Section 5: every column excluded before the
    transaction opened, named, with the reason -- whether `read_column`
    refused it or `refuse_if_not_ready`'s later gate did.
    """
    if not exclusions:
        lines = ["No columns were excluded from this batch."]
    else:
        lines = ["Column %s -- %s" % (exclusion.element_id, exclusion.reason)
                 for exclusion in exclusions]
    return ReportSection("Excluded columns", lines)


def batch_replacement_section(rows):
    """Issue #153 / spec Section 6: R23 and R24, per column.

    "Reporting '17 existing bars will be replaced' for one column is a
    sentence; for forty it is a table, and the confirmation must stay
    readable or it stops being a confirmation" -- so this IS the table,
    one line per column, and it is what the batch's confirmation shows.
    Columns holding nothing are said to hold nothing rather than left out:
    a reviewer counting lines must find every column that will be placed.
    """
    if not rows:
        return ReportSection(
            "Existing reinforcement",
            ["No columns will be placed, so nothing will be replaced."])
    lines = []
    for row in rows:
        if row.replaced_count:
            line = ("Column %s -- %d element(s) placed by this tool will be "
                    "DELETED and rebuilt" % (row.element_id,
                                             row.replaced_count))
        else:
            line = ("Column %s -- nothing of ours to replace"
                    % row.element_id)
        if row.foreign_ids:
            # R24: named, never silently present, and never deleted.
            line += (" | %d foreign rebar element(s) left untouched (id %s)"
                     % (len(row.foreign_ids),
                        ", ".join(str(found) for found in row.foreign_ids)))
        lines.append(line)
    return ReportSection("Existing reinforcement", lines)


def build_report(data, bars, splice, splice_line, bar_type_name,
                 bar_diameter_mm, plan, ladder, findings=(), tie_lines=(),
                 roof_termination=None):
    """The whole page, in order.

    Every argument is a value some other module already decided. This
    function chooses wording and order and nothing else -- which is what
    keeps it incapable of disagreeing with the placer.

    ``roof_termination`` (issue #172, R36) is OPTIONAL and defaults to
    ``None`` -- an ordinary column states no top-floor condition, and its
    report must carry no section about one. Only a
    `rft.core.column_plan.RoofTerminationPlan` adds the section.
    """
    sections = [
        host_section(data),
        longitudinal_section(bars, splice, bar_type_name, bar_diameter_mm,
                             splice_line),
        spacing_section(plan),
        tie_level_section(ladder),
        tie_section(list(findings), list(tie_lines)),
    ]
    if roof_termination is not None:
        sections.append(roof_termination_section(roof_termination))
    sections.append(outstanding_section())
    return sections


def render(sections):
    """Sections to plain text, for the window and for a copy-paste."""
    out = []
    for section in sections:
        out.append(section.heading.upper())
        out.append("-" * len(section.heading))
        out.extend(section.lines)
        out.append("")
    return "\n".join(out).rstrip() + "\n"
