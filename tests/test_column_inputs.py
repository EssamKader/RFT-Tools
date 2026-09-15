# -*- coding: utf-8 -*-
"""#88 -- section 1 bar counts, R7 roles, and section 9's `L_s`.

The corner-sharing tests are the point of this file. The reuse audit
warned that a per-face function "would pass a unit test per-face and
produce eight corner bars in Revit", so the tests here are written on the
TOTAL, which is the number that would have been wrong.
"""

import ast
import importlib
import io

import pytest

from rft.core.column_inputs import (
    DEFAULT_HOOK_ANGLE_DEG,
    LS_MODE_DIAMETERS,
    LS_MODE_MM,
    MIN_BARS_PER_FACE,
    ROLE_GRADE,
    ROLE_INNER_TIE,
    ROLE_LONGITUDINAL,
    ROLE_TIE,
    intermediate_bars_per_face,
    perimeter_bars,
    role_grade_report_line,
    role_picker_label,
    splice_length,
    splice_length_report_line,
)
from rft.core.grades import (
    GRADE_HIGH_TENSILE, GRADE_MILD, ROLE_STIRRUP, role_picker_label as
    beam_role_picker_label,
)


def _module_source(dotted):
    module = importlib.import_module(dotted)
    path = module.__file__
    if path.endswith(("c", "o")):
        path = path[:-1]
    return io.open(path, encoding="utf-8").read()


def _imported_names(dotted):
    """Every name this module imports, by parsing it -- not by searching
    its text, which would also match the prose explaining what it avoids.
    """
    names = set()
    for node in ast.walk(ast.parse(_module_source(dotted))):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names |= set(alias.name for alias in node.names)
    return names


def _imported_modules(dotted):
    modules = set()
    for node in ast.walk(ast.parse(_module_source(dotted))):
        if isinstance(node, ast.Import):
            modules |= set(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    return modules


def test_the_four_corner_bars_are_counted_ONCE_not_twice():
    """3 on each b-face and 4 on each h-face is 10 bars, not 14.

    The naive sum -- 2 x (3 + 4) = 14 -- double-counts every corner. This
    is the exact defect docs/column/reuse-audit.md flags: it passes a
    per-face check and produces eight corner bars in the model.
    """
    bars = perimeter_bars(3, 4)
    assert bars.total_count == 10
    assert bars.total_count != 2 * (3 + 4)
    assert bars.corner_count == 4


def test_the_smallest_legal_column_is_four_corner_bars():
    """Two per face, every one of them shared: 2 x (2 + 2) - 4 = 4."""
    assert perimeter_bars(2, 2).total_count == 4


@pytest.mark.parametrize("nb,nh,total", [
    (2, 2, 4), (3, 3, 8), (4, 4, 12), (2, 5, 10), (5, 2, 10), (6, 4, 16),
])
def test_the_perimeter_count_over_a_range(nb, nh, total):
    assert perimeter_bars(nb, nh).total_count == total


def test_a_face_cannot_carry_fewer_than_its_two_shared_corners():
    with pytest.raises(ValueError) as excinfo:
        perimeter_bars(1, 4)
    assert "at least %d" % MIN_BARS_PER_FACE in str(excinfo.value)
    assert "SHARES" in str(excinfo.value), (
        "the refusal must say WHY two is the floor, or it reads as an "
        "arbitrary rule")


def test_a_blank_count_is_refused_rather_than_invented():
    """Section 1: inputs are user-provided, never invented."""
    with pytest.raises(ValueError) as excinfo:
        perimeter_bars(None, 4)
    assert "never invents" in str(excinfo.value)


def test_intermediate_bars_exclude_the_corners():
    """Section 6.1 asks which bars need restraint; a tie corner already
    restrains the corner bars, so the count that matters downstream is
    this one.
    """
    assert intermediate_bars_per_face(4) == 2
    assert intermediate_bars_per_face(2) == 0
    assert intermediate_bars_per_face(0) == 0


# --------------------------------------------------------------------- #
# R7 roles


def test_r7_grades():
    assert ROLE_GRADE[ROLE_LONGITUDINAL] == GRADE_HIGH_TENSILE
    assert ROLE_GRADE[ROLE_TIE] == GRADE_MILD
    assert ROLE_GRADE[ROLE_INNER_TIE] == GRADE_MILD


def test_the_two_tie_roles_are_SEPARATE_entries():
    """Section 7 keeps the outer and inner tie choices "structurally
    separate so one dropdown's selection can never silently apply to the
    other role". One shared role would defeat that before the UI is even
    written.
    """
    assert ROLE_TIE != ROLE_INNER_TIE
    assert ROLE_TIE in ROLE_GRADE and ROLE_INNER_TIE in ROLE_GRADE


def test_the_column_roles_are_NOT_in_the_beam_role_table():
    """The workspace rule: never mix two elements' requirements. The
    reuse audit marks the beam ROLE_* constants do-not-reuse.
    """
    from rft.core import grades
    for role in (ROLE_LONGITUDINAL, ROLE_TIE, ROLE_INNER_TIE):
        assert role not in grades.ROLE_GRADE
        assert role not in grades.ROLE_LABEL


def test_the_label_FORMAT_is_shared_with_the_beam():
    """The role tables are separate; the way a label is built is not.
    Two format strings would drift, and the grade is the part that must
    reach the engineer at the moment of choosing.
    """
    column = role_picker_label(ROLE_TIE)
    beam = beam_role_picker_label(ROLE_STIRRUP)
    assert column == "Ties -- " + GRADE_MILD
    assert beam.split(" -- ")[1] == column.split(" -- ")[1] == GRADE_MILD


def test_the_report_line_names_the_rule_that_required_the_grade():
    line = role_grade_report_line(ROLE_LONGITUDINAL, "16M")
    assert "16M" in line and "R7" in line and GRADE_HIGH_TENSILE in line


def test_135_is_a_DEFAULT_here_not_a_requirement():
    """The beam REFUSES anything but 135; column section 7 defaults to it
    and permits any available hook type. The reuse audit marks the beam's
    guard do-not-reuse for exactly this reason -- reusing it would refuse
    what this spec allows.
    """
    assert DEFAULT_HOOK_ANGLE_DEG == 135.0
    # Checked on the IMPORTS, not on the text. This module documents, in a
    # comment, exactly which beam members it must not reuse -- and a guard
    # that flags its own explanation cannot coexist with the explanation.
    # (The third time this has bitten in one sitting; the imports are what
    # "does not reuse" actually means anyway.)
    imported = _imported_names("rft.core.column_inputs")
    assert "hook_angle_guard_message" not in imported
    assert "HOOK_ANGLE_REQUIRED_DEG" not in imported


# --------------------------------------------------------------------- #
# Section 9 -- Ls


def test_ls_as_a_raw_length():
    splice = splice_length(600.0, LS_MODE_MM, 15.9)
    assert splice.length_mm == 600.0


def test_ls_as_a_multiplier_uses_the_TYPE_diameter_not_the_name():
    """40 x 16M is 636 mm, not 640: the live model's 16M measures 15.90 mm.
    A bar type's name routinely disagrees with its diameter, and Ls is one
    of the places that costs millimetres on a drawing.
    """
    splice = splice_length(40, LS_MODE_DIAMETERS, 15.9)
    assert splice.length_mm == pytest.approx(636.0)
    assert splice.length_mm != 640.0


def test_a_multiplier_without_a_bar_type_is_refused_with_the_fix():
    with pytest.raises(ValueError) as excinfo:
        splice_length(40, LS_MODE_DIAMETERS, None)
    assert "Pick the bar type first" in str(excinfo.value)


@pytest.mark.parametrize("value", [None, 0, -40])
def test_a_missing_or_non_positive_ls_is_refused(value):
    with pytest.raises(ValueError) as excinfo:
        splice_length(value, LS_MODE_MM, 15.9)
    assert "never computes one" in str(excinfo.value)


def test_the_report_states_BOTH_the_length_and_what_was_typed():
    """"636 mm" alone hides that it came from 40 x 15.9, and "40
    diameters" alone hides which diameter -- and the diameter is the part
    a bar type's name gets wrong.
    """
    splice = splice_length(40, LS_MODE_DIAMETERS, 15.9)
    line = splice_length_report_line(splice, 15.9)
    assert "636" in line and "40" in line and "15.90" in line


def test_nothing_here_consults_anchorage():
    """Section 10: this tool does NOT call rft.core.anchorage. Ls is
    applied blindly, so an import of the beam's anchorage logic would be
    the tool quietly starting to compute what the spec says it must not.
    """
    assert "anchorage" not in _imported_modules("rft.core.column_inputs")
