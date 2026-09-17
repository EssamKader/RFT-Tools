# -*- coding: utf-8 -*-
"""#91 -- the Review report.

Tested as TEXT, because text is what it is. Every assertion below is a
claim #91 makes about what the page must say, and several are about what
it must NOT say -- a report that quietly omits a limitation is worse than
one that has none, because it is trusted as complete.
"""

import re

import pytest

from rft.core.column_host_rules import extent_from_ends, section_from_dimensions
from rft.core.column_inputs import (
    LS_MODE_DIAMETERS, perimeter_bars, splice_length, splice_length_report_line,
)
from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_report import (
    FLAG_PREFIX, build_report, outstanding_section, render, spacing_section,
    tie_section,
)
from rft.core.column_ties import (
    TieSubset, resolve_ties, tie_report_lines, validate,
)
from rft.core.column_spacing import (
    FIRST_TIE_OFFSET_MM, MODE_AUTO, MODE_MANUAL, spacing_plan,
)
from rft.core.column_tie_levels import tie_levels

HC = 2700.0


def host_data(base_face_z=None, top_cover_set=False):
    return {
        "element_id": 421967,
        "family_name": "M_Concrete-Rectangular-Column",
        "type_name": "450 x 600mm",
        "section": section_from_dimensions(450.0, 600.0),
        "cover_mm": 40.0,
        "cover_type_name": "Interior (framing, columns)",
        "top_face_cover_is_set": top_cover_set,
        "base_level": ("Level 1", 0.0),
        "top_level": ("Level 2", 3000.0),
        "extent": extent_from_ends(base_face_z, 2700.0, 0.0, 3000.0),
    }


VALID_SUBSETS = [TieSubset((0, 1, 2, 3)), TieSubset((0, 1, 2, 3, 4)),
                 TieSubset((1, 2, 3, 4, 5))]


def report_text(mode=MODE_AUTO, manual=(None, None), data=None,
                findings=(), tie_lines=()):
    plan = spacing_plan(mode, HC, 450.0, 600.0, 15.9, 9.5,
                        manual_confinement_mm=manual[0],
                        manual_middle_zone_mm=manual[1])
    ladder = tie_levels(HC, plan.l0_mm, plan.confinement_spacing_mm,
                        plan.middle_zone_spacing_mm, FIRST_TIE_OFFSET_MM)
    bars = perimeter_bars(3, 4)
    splice = splice_length(40, LS_MODE_DIAMETERS, 15.9)
    return render(build_report(
        data if data is not None else host_data(), bars, splice,
        splice_length_report_line(splice, 15.9), "16M", 15.9, plan, ladder,
        findings=findings, tie_lines=tie_lines))


def test_cover_is_labelled_as_READ_never_as_an_input():
    """A2. The input was fiction: Revit clamps ties to the host's cover, so
    a typed 25 became 40 in the model while the report said 25.
    """
    text = report_text()
    assert "READ from the element" in text
    assert "never typed into this tool" in text
    assert "never defaulted to 25" in text


def test_every_datum_states_where_it_came_from():
    """R5/R6: "2700 from a soffit" and "2700 from a level elevation" are
    different claims.
    """
    text = report_text()
    assert "from the level elevation" in text
    assert "from the support face" in text
    assert "NOT the Length parameter" in text


def test_a_measured_base_does_not_carry_the_ground_floor_note():
    """The note explains an ABSENCE. Printing it when a support was found
    would be an explanation of something that did not happen.
    """
    text = report_text(data=host_data(base_face_z=300.0))
    assert "No support element was found below" not in text


def test_the_missing_base_support_is_explained_as_normal():
    text = report_text()
    assert "case C1" in text
    assert "normal for a ground-floor column" in text


def test_q5_is_reported_and_only_when_it_applies():
    assert "Q5" in report_text()
    assert "Q5" not in report_text(data=host_data(top_cover_set=True))


def test_the_corner_bars_are_explained_not_just_counted():
    text = report_text()
    assert "Total: 10 bars" in text
    assert "2 x (3 + 4) - 4" in text
    assert "SHARED between faces and counted once" in text


def test_the_absence_of_a_bottom_Ls_is_STATED():
    """R5. An unexplained absence reads as an omission every time somebody
    checks the drawing.
    """
    text = report_text()
    assert "No bottom Ls" in text
    assert "a ruling, not an omission" in text


def test_the_splice_position_names_the_override_it_deviates_from():
    text = report_text()
    assert "TOP FACE of the support" in text
    assert "constructability override" in text


def test_each_limit_is_shown_with_the_minimum_that_governed_it():
    text = report_text()
    assert "governed by '8 x smallest longitudinal bar'" in text
    assert "max of Hc / 6" in text
    assert "no independent 150 mm cap" in text


def test_mode_b_shows_the_limit_ALONGSIDE_the_users_value():
    """Section 8's requirement, literally: the code-calculated limit
    displayed next to the entered value, on the same page.
    """
    text = report_text(MODE_MANUAL, (200.0, 300.0))
    assert "Code maximum S0: 127 mm" in text
    assert "Confinement spacing to be built: 200 mm" in text
    assert FLAG_PREFIX in text
    assert "EXCEEDS" in text
    assert "will place 200 mm as entered" in text


def test_a_mode_b_flag_never_claims_a_refusal():
    text = report_text(MODE_MANUAL, (200.0, 300.0))
    assert "refus" not in text.lower(), (
        "the placer builds the user's value; a report saying otherwise "
        "contradicts the model")


def test_mode_a_carries_no_flags():
    assert FLAG_PREFIX not in report_text()


def test_the_tie_levels_are_LISTED_not_summarised():
    """"16 ties, alternating" cannot be checked against a section
    drawing. The count and the mirror pattern are what an engineer
    verifies.
    """
    text = report_text()
    assert "16 tie levels" in text
    assert text.count("confinement (bottom)") >= 5
    assert text.count("confinement (top)") >= 5
    # one M per mirrored level, plus none on the others
    # Matched on the SHAPE of a level line. "startswith three spaces"
    # silently dropped levels 10-15, whose two-digit index leaves only
    # two -- and the assertions below were still true of the smaller
    # list, so the test would have passed while watching ten of
    # sixteen lines.
    level_lines = [line for line in text.split("\n")
                   if re.match(r"^\s+\d+\s+\d+ mm\s", line)]
    assert len(level_lines) == 16
    assert sum(1 for line in level_lines if line.rstrip().endswith("M")) == 8


def test_the_ladder_follows_the_BUILT_spacing_in_mode_b():
    """Not the code limit. A ladder drawn from the maximums would list
    ties at positions nothing will occupy.
    """
    text = report_text(MODE_MANUAL, (100.0, 200.0))
    assert "16 tie levels" not in text


# --------------------------------------------------------------------- #
# What the report refuses to claim


def test_the_report_says_its_positions_are_IDEALISED():
    """R15. A corner bar binds to the tie's bend and moves -- measured
    live, -167.55 asked for and -164.02 landed. A report of idealised
    coordinates would be wrong on every corner bar in every column, so
    the page says so until there is a placement to read back from.
    """
    text = report_text()
    assert "IDEALISED" in text
    assert "-164.02" in text, (
        "the measured number makes the claim checkable; 'positions may "
        "differ' does not")
    assert "read back after placement" in text


def test_the_report_now_STATES_the_topology_it_once_could_not():
    """A1/#89. This assertion is the inverse of the one it replaces: the
    report used to say "not guessed here" because Q11 was open. Q11 is
    answered, so the page states per tie what it is and which bars it
    holds -- and must no longer carry the apology.
    """
    lay = perimeter_bar_positions(450.0, 600.0, 40.0, 9.5, 15.9, 3, 4)
    resolved = resolve_ties(VALID_SUBSETS, lay, 9.5, 15.9, 40.0)
    text = report_text(findings=validate(lay, resolved),
                       tie_lines=tie_report_lines(resolved))
    # render() upper-cases every heading.
    assert "TIES (SECTION 6.2)" in text
    assert "Outer perimeter tie: closed loop" in text
    assert "Not guessed here." not in text
    assert "blocked on open question Q11" not in text
    assert "STATED by the engineer, not derived" in text


def test_a_refused_topology_is_FLAGGED_at_the_top_of_its_section():
    """A topology section 6.1 refuses is the thing to read. Under a list
    of tie geometry it gets skimmed past.
    """
    lay = perimeter_bar_positions(450.0, 600.0, 40.0, 9.5, 15.9, 3, 4)
    bare = resolve_ties([], lay, 9.5, 15.9, 40.0)
    section = tie_section(validate(lay, bare), tie_report_lines(bare))
    assert section.lines[0].startswith(FLAG_PREFIX)
    assert "EVERY bar to be restrained" in section.lines[0]


def test_a_clean_topology_says_so_rather_than_saying_nothing():
    lay = perimeter_bar_positions(450.0, 600.0, 40.0, 9.5, 15.9, 3, 4)
    resolved = resolve_ties(VALID_SUBSETS, lay, 9.5, 15.9, 40.0)
    section = tie_section(validate(lay, resolved), tie_report_lines(resolved))
    assert "every requirement met" in section.lines[0]


def test_a_cross_tie_reaches_the_page_WITH_its_reason():
    lay = perimeter_bar_positions(450.0, 600.0, 40.0, 9.5, 15.9, 3, 4)
    unbuildable = resolve_ties([], lay, 9.5, 15.9, 900.0)
    section = tie_section(validate(lay, unbuildable),
                          tie_report_lines(unbuildable))
    joined = "\n".join(section.lines)
    assert "cross-tie" in joined
    assert "cannot be bent" in joined


def test_the_outstanding_section_is_never_empty():
    """It is the page's honesty. An empty section would read as "nothing
    outstanding", which is the one thing it must not say while these two
    items are open.
    """
    assert len(outstanding_section().lines) == 2


def test_the_report_recomputes_nothing():
    """The report and the placer are fed by the same engine and cannot
    disagree, which holds only while this module derives no number of its
    own. Checked on the imports: an arithmetic helper imported here would
    be a second source of truth wearing the report's authority.
    """
    import ast
    import io

    import rft.core.column_report as module
    path = module.__file__
    if path.endswith(("c", "o")):
        path = path[:-1]
    imported = set()
    for node in ast.walk(ast.parse(io.open(path, encoding="utf-8").read())):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported |= set(alias.name for alias in node.names)
    # SEVERITY_BLOCKING is a string constant used to choose a line
    # prefix. Like MODE_MANUAL it decides WORDING, not a number -- which
    # is the line this guard draws.
    assert imported == {"namedtuple", "MODE_MANUAL", "SEVERITY_BLOCKING"}, (
        "the report imports something it could compute WITH: %s" % imported)


def test_the_spacing_section_reads_the_built_values_not_the_limits():
    plan = spacing_plan(MODE_MANUAL, HC, 450.0, 600.0, 15.9, 9.5,
                        manual_confinement_mm=200.0,
                        manual_middle_zone_mm=300.0)
    lines = spacing_section(plan).lines
    built = [line for line in lines if "to be built" in line]
    assert any("200 mm" in line for line in built)
    assert any("300 mm" in line for line in built)

def test_the_report_says_a_triangle_does_NOT_alternate():
    """R32, ruled by the owner: "no alter in triangle".

    The line above it promises the hook corner alternates between
    consecutive levels (section 6.3). Left alone that reads as a promise
    the triangles do not keep -- a triangle's closure is its apex, fixed
    by its geometry, with no second corner to move to.

    Stated unconditionally because it is a RULE rather than a fact about
    this ladder: the ladder carries the same mirror map whatever shapes
    the ties are, and does not know which they are.
    """
    text = report_text()
    assert "does not alternate" in text.lower(), text
    assert "apex" in text.lower()
    # The alternation claim itself must SURVIVE -- R32 qualifies it, it
    # does not delete it. A closed loop still alternates.
    assert "alternates between consecutive levels" in text

