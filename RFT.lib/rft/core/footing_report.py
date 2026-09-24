# -*- coding: utf-8 -*-
"""The footing tool's own Review report (#205) -- the page read before
pressing Place/Batch.

PURE. Values in, lines of text out. No Revit, no WPF: the report is a
list of ``(heading, [lines])`` sections and the window renders it, so the
whole page is testable under plain CPython -- the same shape
``rft.core.column_report`` already established for ColumnRFT (``rft.ui.
report`` is NOT reused: confirmed beam-specific, per that module's own
docstring and `docs/footing/reuse-audit.md`).

## The rule the page exists to keep

The report and the placer are fed by the SAME `rft.core.footing_plan.
build_footing_plan`/`rft.revit.footing_batch.plan_candidates` objects
(REUSE_GUIDELINES.md Sec 1), so they cannot disagree. Nothing here is
recomputed -- every number is read off a `FootingGeometry`, a
`DowelColumnSection`, a `FootingPlan` or a `footing_batch.BatchPlan`.
"""

from collections import namedtuple

ReportSection = namedtuple("ReportSection", "heading lines")


def _mm(value):
    return "%.1f mm" % value


def footing_geometry_section(geometry):
    """R8's own live-read footing geometry (#228) -- never typed."""
    lines = [
        "a (X) = %s, b (Y) = %s" % (_mm(geometry.a_mm), _mm(geometry.b_mm)),
        "Thickness = %s" % _mm(geometry.footing_thickness_mm),
        "Side cover = %s" % _mm(geometry.cover_mm),
        "Bottom cover = %s, Top cover = %s" % (
            _mm(geometry.bottom_cover_mm), _mm(geometry.top_cover_mm)),
    ]
    return ReportSection("Footing geometry (read live, #228)", lines)


def column_section_section(column_section):
    """R7's own live-read column section/cover (#221) -- never typed."""
    lines = [
        "Cw = %s, Cd = %s" % (
            _mm(column_section.Cw_mm), _mm(column_section.Cd_mm)),
        "Cover = %s" % _mm(column_section.Ccover_mm),
    ]
    return ReportSection("Column above (read live, #221)", lines)


def mesh_section(plan):
    """The bottom mesh's own two representative bars (#198)."""
    lengths = plan.bottom_mesh.lengths
    lines = [
        "mesh_bar_x length = %s" % _mm(lengths.mesh_bar_x_mm),
        "mesh_bar_y length = %s" % _mm(lengths.mesh_bar_y_mm),
        "Primary reinforcement direction = %s" % plan.bottom_mesh.primary_direction,
    ]
    return ReportSection("Bottom mesh (#198)", lines)


def dowel_array_section(plan):
    """The dowel array (#202/#222): embedment sizing plus how many bars
    the live column section produced -- one representative bar when no
    live array inputs were supplied, N bars from `perimeter_bar_positions`
    otherwise."""
    embedment = plan.dowel.embedment
    lines = [
        "a_dowel = %s, b_dowel = %s, LD = %s" % (
            _mm(embedment.a_dowel_mm), _mm(embedment.b_dowel_mm),
            _mm(embedment.ld_mm)),
        "%d dowel bar(s) in this plan" % len(plan.dowel.bars),
    ]
    return ReportSection("Dowel array (#202/#222, hooks bend outward -- R10)",
                         lines)


def not_yet_placed_section():
    """R6-R10 and #198-#228 built and placed the bottom mesh and the
    dowel array; top mesh (#201), dowel_tie's closed-loop shape (#203)
    and the perimeter_tie bar (#204) have core math but no Revit
    placement adapter yet (`IsolatedFooting.extension/CONTEXT.md`'s own
    "Not yet in" list) -- stated here rather than exposed as an input
    this window cannot act on."""
    lines = [
        "Top mesh, dowel-tie closed loops and the perimeter-tie bar are "
        "not yet wired to placement -- see IsolatedFooting.extension/"
        "CONTEXT.md. This window does not ask for their inputs, since "
        "there is nothing yet for them to place.",
    ]
    return ReportSection("Not yet placed by this tool", lines)


def batch_group_section(groups):
    """#226/R9: name every group and its live-read key, and which
    footings fell in it -- the report carries the burden of a split
    type-pair, the same ruling column batch's own R33 makes."""
    lines = []
    if not groups:
        lines.append(
            "No group was formed -- every candidate footing was excluded "
            "(see 'Excluded footings' below).")
    for index, group in enumerate(groups, start=1):
        key = group.key
        lines.append(
            "Group %d -- a=%s b=%s t=%s cover=%s/%s/%s Cw=%s Cd=%s "
            "Ccover=%s -- footing(s) %s" % (
                index, _mm(key.a_mm), _mm(key.b_mm),
                _mm(key.footing_thickness_mm), _mm(key.cover_mm),
                _mm(key.bottom_cover_mm), _mm(key.top_cover_mm),
                _mm(key.Cw_mm), _mm(key.Cd_mm), _mm(key.Ccover_mm),
                ", ".join(str(i) for i in group.element_ids)))
    return ReportSection("Groups", lines)


def batch_exclusion_section(exclusions):
    """#226 spec Sec 5: every footing excluded before the transaction
    opened, named, with the reason."""
    if not exclusions:
        lines = ["No footings were excluded from this batch."]
    else:
        lines = ["Footing %s -- %s" % (exclusion.element_id, exclusion.reason)
                 for exclusion in exclusions]
    return ReportSection("Excluded footings", lines)


def batch_replacement_section(rows):
    """#226 spec Sec 6: the replacement table, one line per footing --
    a footing holding nothing is said to hold nothing rather than left
    out, so a reviewer counting lines finds every footing that will be
    placed."""
    if not rows:
        return ReportSection(
            "Existing reinforcement",
            ["No footings will be placed, so nothing will be replaced."])
    lines = []
    for row in rows:
        line = "Footing %s -- %d element(s) of ours" % (
            row.element_id, row.replaced_count)
        if row.foreign_ids:
            line += "; foreign (left untouched): %s" % (
                ", ".join(str(i) for i in row.foreign_ids))
        lines.append(line)
    return ReportSection("Existing reinforcement", lines)


def render(sections):
    """Sections to plain text, for the window and for the pyRevit output
    window copy."""
    out = []
    for section in sections:
        out.append(section.heading.upper())
        out.append("-" * len(section.heading))
        out.extend(section.lines)
        out.append("")
    return "\n".join(out).rstrip() + "\n"
