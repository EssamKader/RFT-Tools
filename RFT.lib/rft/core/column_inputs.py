# -*- coding: utf-8 -*-
"""Section 1 and section 9 inputs — bar counts, roles, and `L_s` (issue #88).

PURE. No Revit, no UI. The field parsers themselves come from
``rft.ui.inputs``, which the reuse audit clears as-is; what is here is what
a COLUMN means by those numbers, which is not what a beam means.

## The corner-sharing decision, made once and stated

Section 2 models the longitudinal bars as ONE perimeter, not four
independent faces, and the four faces **share their corner bars**. The
reuse audit warns that ``corner_bar_u_positions_mm`` places a bar at each
end of a face, so calling it per face and concatenating counts every corner
twice -- "exactly the kind of thing that would pass a unit test per-face
and produce eight corner bars in Revit".

There are two self-consistent conventions and no third:

1. a face's count **includes** its two corner bars;
2. a face's count is its **intermediate** bars only, with the four corners
   counted separately.

**This tool uses (1).** It is how a section is read off a drawing and how
an engineer says "4 bars on that face", and it makes the minimum legible:
a face cannot carry fewer than 2, because it always has its two corners.
(2) would make "0 bars on this face" the normal case for a small column,
which reads like an error every time.

The total is therefore **not** the sum of the four faces::

    total = 2 * (n_b + n_h) - 4

The ``- 4`` is the four corners, each counted by two faces. There is a test
that a 450x600 column with 3 and 4 per face gives **10**, not 14.
"""

from collections import namedtuple

from .grades import GRADE_HIGH_TENSILE, GRADE_MILD, format_role_picker_label

#: A face always carries its two shared corner bars, so this is a floor
#: imposed by the geometry rather than a policy choice.
MIN_BARS_PER_FACE = 2

#: Column roles. Deliberately NOT added to ``rft.core.grades``' ROLE_*
#: constants: those are the beam's, the reuse audit marks them do-not-reuse,
#: and mixing two elements' roles in one table is what the workspace rules
#: forbid. What IS shared is the grade vocabulary and the label format --
#: the same steel, named the same way, in both tools.
ROLE_LONGITUDINAL = "column longitudinal bars"
ROLE_TIE = "column ties"
ROLE_INNER_TIE = "column inner ties"

#: R7. Longitudinal bars high tensile, ties mild steel.
ROLE_GRADE = {
    ROLE_LONGITUDINAL: GRADE_HIGH_TENSILE,
    ROLE_TIE: GRADE_MILD,
    ROLE_INNER_TIE: GRADE_MILD,
}

ROLE_LABEL = {
    ROLE_LONGITUDINAL: "Longitudinal bars",
    ROLE_TIE: "Ties",
    ROLE_INNER_TIE: "Inner ties",
}

#: Section 7: both hook dropdowns OPEN at 135 degrees. A default, never a
#: requirement -- and the difference is load-bearing. The beam's
#: ``hook_angle_guard_message``/``HOOK_ANGLE_REQUIRED_DEG`` REFUSE anything
#: but 135, and the reuse audit marks them do-not-reuse for exactly this
#: reason: reusing them here would refuse what this spec permits.
DEFAULT_HOOK_ANGLE_DEG = 135.0

#: Section 9. `L_s` is entered either as a length or as a multiple of the
#: longitudinal bar diameter, and is NEVER auto-calculated -- it varies
#: with tension/compression zones, so the tool applies the user's number
#: blindly.
LS_MODE_MM = "mm"
LS_MODE_DIAMETERS = "diameters"

LS_MODE_CHOICES = (
    (LS_MODE_MM, "mm (a length)"),
    (LS_MODE_DIAMETERS, "x bar diameter"),
)

PerimeterBars = namedtuple(
    "PerimeterBars", "count_b_face count_h_face total_count corner_count")

SpliceLength = namedtuple("SpliceLength", "length_mm mode entered_value")


def role_picker_label(role):
    """The label the bar-type picker carries, grade included.

    Built from :data:`ROLE_GRADE` so it cannot drift from the mapping, and
    put in front of the engineer at the moment of choosing, since the grade
    cannot be checked afterwards from the selected type itself. Same
    reasoning, and the same format, as the beam's A42 rule.
    """
    return format_role_picker_label(ROLE_LABEL[role], ROLE_GRADE[role])


def role_grade_report_line(role, bar_type_name):
    """Which bar type was used for ``role``, and the grade R7 requires --
    so a wrong pick is visible after the fact even though it was never
    blocked mechanically.
    """
    return "{}: RebarBarType '{}' used (R7 requires {})".format(
        ROLE_LABEL[role], bar_type_name, ROLE_GRADE[role])


def perimeter_bars(count_b_face, count_h_face):
    """Resolve two per-face counts into the perimeter's real bar count.

    Both counts INCLUDE their two corner bars -- see the module docstring
    for why that convention and not the other one. The four corners are
    shared, so the total subtracts them once each::

        total = 2 * (n_b + n_h) - 4
    """
    for label, value in (("bars per b-face", count_b_face),
                         ("bars per h-face", count_h_face)):
        if value is None:
            raise ValueError(
                "%s has not been entered. Section 1 takes bar counts from "
                "the user and never invents them." % label)
        if value < MIN_BARS_PER_FACE:
            raise ValueError(
                "%s must be at least %d -- got %d. Each face carries the "
                "two corner bars it SHARES with its neighbours, so a face "
                "with fewer than two is not a face this layout can "
                "describe." % (label, MIN_BARS_PER_FACE, value))
    total = 2 * (count_b_face + count_h_face) - 4
    return PerimeterBars(count_b_face=count_b_face,
                         count_h_face=count_h_face,
                         total_count=total,
                         corner_count=4)


def intermediate_bars_per_face(count_including_corners):
    """The bars on a face that are NOT its shared corners.

    Section 6.1 asks which bars need restraint, and the corner bars are
    never the ones in question -- a tie corner already restrains them. So
    the count that matters downstream is this one, derived here rather
    than by every caller subtracting 2 and one of them forgetting.
    """
    return max(0, count_including_corners - MIN_BARS_PER_FACE)


def splice_length(entered_value, mode, bar_diameter_mm):
    """Section 9's `L_s`, from a raw length or a diameter multiplier.

    **Never auto-calculated.** `L_s` varies with tension and compression
    zones, so the spec makes it a direct user input and says the tool
    "blindly applies" it. Nothing here consults bar grade, concrete grade
    or anchorage -- and ``rft.core.anchorage`` is explicitly not called by
    this tool (section 10).

    The multiplier form needs the bar diameter, which comes from the
    selected ``RebarBarType`` and not from the bar's NAME: the live model's
    ``16M`` is 15.90 mm, so "40 diameters" is 636 mm there, not 640.
    """
    if entered_value is None or entered_value <= 0:
        raise ValueError(
            "The splice length Ls must be a positive number -- got %r. "
            "Section 9 makes it a direct user input; the tool never "
            "computes one." % (entered_value,))
    if mode == LS_MODE_MM:
        return SpliceLength(length_mm=float(entered_value), mode=mode,
                            entered_value=entered_value)
    if mode == LS_MODE_DIAMETERS:
        if bar_diameter_mm is None or bar_diameter_mm <= 0:
            raise ValueError(
                "Ls was entered as a multiple of bar diameter, but no "
                "longitudinal bar type is selected, so there is no "
                "diameter to multiply. Pick the bar type first, or enter "
                "Ls in mm.")
        return SpliceLength(
            length_mm=float(entered_value) * float(bar_diameter_mm),
            mode=mode, entered_value=entered_value)
    raise ValueError(
        "Ls mode must be %r or %r -- got %r." % (LS_MODE_MM,
                                                 LS_MODE_DIAMETERS, mode))


def splice_length_report_line(splice, bar_diameter_mm):
    """How `L_s` is stated on the report: the number that will be built,
    and what the user actually typed.

    Both, always. "636 mm" alone hides that it came from "40 x 15.9", and
    "40 diameters" alone hides which diameter -- and the diameter is the
    part a bar type's name gets wrong.
    """
    if splice.mode == LS_MODE_DIAMETERS:
        return ("Ls = %.0f mm (entered as %g x bar diameter %.2f mm; "
                "section 9: user input, never auto-calculated)"
                % (splice.length_mm, splice.entered_value, bar_diameter_mm))
    return ("Ls = %.0f mm (entered directly; section 9: user input, never "
            "auto-calculated)" % splice.length_mm)
