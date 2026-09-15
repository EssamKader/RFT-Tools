# -*- coding: utf-8 -*-
"""Spec sections 3, 4, 5 and 8 — the tie spacing arithmetic (issue #88).

PURE. Millimetres in, millimetres out. No Revit, no UI, no I/O, so every
number the Review report will print and the placer will build is decided
here once and checked under plain CPython.

**Section 8's single-source rule is the reason this module exists at all.**
The report and the placer must use the SAME number, "so a violation is
visible on the page the same instant it becomes true in the model — never
discoverable only after the fact". Two call sites computing `S0`
independently is how that guarantee dies quietly, so there is one.

Deliberately NOT ``rft.core.spacing``. That module is the beam's clear-bar
spacing rule (section 6.2-6.4 bar-to-bar gaps); this is a column's vertical
tie pitch. They share a word and nothing else. See
`docs/column/reuse-audit.md`.
"""

from collections import namedtuple

#: Section 4's fourth candidate, and section 5's multiplier. Named because
#: an unlabelled 150 in a min() is indistinguishable from the DIFFERENT
#: 150 the spec had to correct in section 5 -- that number "belonged to a
#: different rule and is not an independent cap on middle-zone spacing".
S0_ABSOLUTE_CAP_MM = 150.0
MIDDLE_ZONE_MULTIPLIER = 2.0

#: Section 3's floor and its divisor.
L0_ABSOLUTE_FLOOR_MM = 500.0
L0_HEIGHT_DIVISOR = 6.0

#: Section 4's multipliers.
S0_LONG_BAR_MULTIPLIER = 8.0
S0_TIE_MULTIPLIER = 24.0
S0_NARROW_FRACTION = 0.5

#: Section 4, closing the inequality ambiguity: the first tie sits at an
#: EXACT 50 mm from the support face. The code's "not exceeding S0" is a
#: maximum, and a maximum is not a placeable position.
FIRST_TIE_OFFSET_MM = 50.0

MODE_AUTO = "A"
MODE_MANUAL = "B"

#: Each candidate carries the words the Review report needs, so the report
#: never re-derives which term governed -- a re-derivation that could
#: disagree with the number beside it.
Candidate = namedtuple("Candidate", "label value_mm")

ConfinementSpacing = namedtuple(
    "ConfinementSpacing", "s0_mm governing_label candidates")

SpacingPlan = namedtuple(
    "SpacingPlan",
    "mode l0_mm l0_candidates s0_mm s0_governing_label s0_candidates "
    "middle_zone_max_mm confinement_spacing_mm middle_zone_spacing_mm flags")

#: A section 8 "warn but place" flag. ``limit_mm`` is what the code
#: computed; ``value_mm`` is what the user asked for and what WILL be
#: built.
SpacingFlag = namedtuple("SpacingFlag", "zone value_mm limit_mm message")


def _positive(value, name):
    if value is None or value <= 0:
        raise ValueError(
            "%s must be a positive length in mm -- got %r. A missing or "
            "zero value here means an input was never read, not that the "
            "quantity is small." % (name, value))
    return float(value)


def confinement_zone_length_mm(clear_height_mm, wide_mm):
    """Section 3::

        L0 = max(clear height / 6, larger cross-sectional dimension, 500)

    measured from the face of the support. `wide_mm` is the LARGER
    cross-section dimension -- section 2's governing-dimension rule (C2)
    gives the larger one to `L0` and the smaller to `S0`, and applies one
    governing value uniformly to all four faces rather than per-axis
    values, "standard construction practice, avoids site errors".

    Returns ``(L0, candidates)`` so the report can show the three terms
    rather than only the winner. Which term governs is the whole content
    of an engineer's check.
    """
    clear_height_mm = _positive(clear_height_mm, "clear height Hc")
    wide_mm = _positive(wide_mm, "the larger section dimension")
    candidates = (
        Candidate("Hc / 6", clear_height_mm / L0_HEIGHT_DIVISOR),
        Candidate("larger section dimension", wide_mm),
        Candidate("absolute floor", L0_ABSOLUTE_FLOOR_MM),
    )
    return max(c.value_mm for c in candidates), candidates


def confinement_spacing_mm(smallest_long_bar_dia_mm, tie_dia_mm, narrow_mm):
    """Section 4. `S0` is the SMALLEST of four candidates.

    Note the first is ``8 x the SMALLEST longitudinal bar``, not "the"
    longitudinal bar. With one bar type per column the two coincide, but
    the spec says smallest and the caller may one day have a mix -- taking
    the largest would raise `S0` and under-confine the column, which is
    the unsafe direction.

    Returns a :class:`ConfinementSpacing` naming the governing term. On a
    tie, the FIRST candidate in spec order wins the name, so the label is
    deterministic rather than dependent on iteration order.
    """
    smallest_long_bar_dia_mm = _positive(
        smallest_long_bar_dia_mm, "the smallest longitudinal bar diameter")
    tie_dia_mm = _positive(tie_dia_mm, "the tie diameter")
    narrow_mm = _positive(narrow_mm, "the smaller section dimension")

    candidates = (
        Candidate("8 x smallest longitudinal bar",
                  S0_LONG_BAR_MULTIPLIER * smallest_long_bar_dia_mm),
        Candidate("24 x tie diameter", S0_TIE_MULTIPLIER * tie_dia_mm),
        Candidate("half the smaller section dimension",
                  S0_NARROW_FRACTION * narrow_mm),
        Candidate("absolute cap", S0_ABSOLUTE_CAP_MM),
    )
    best = min(c.value_mm for c in candidates)
    governing = next(c.label for c in candidates if c.value_mm == best)
    return ConfinementSpacing(s0_mm=best, governing_label=governing,
                              candidates=candidates)


def middle_zone_max_spacing_mm(s0_mm):
    """Section 5: outside `L0`, spacing shall not exceed ``2 x S0``.

    Section 5 exists to correct a bare "150 mm" that "belonged to a
    DIFFERENT rule and is not an independent cap on middle-zone spacing".
    So there is deliberately no ``min(..., 150)`` here. Anyone adding one
    is reintroducing the error the spec already fixed.
    """
    return MIDDLE_ZONE_MULTIPLIER * _positive(s0_mm, "S0")


def manual_spacing_flags(confinement_mm, middle_zone_mm,
                         s0_limit_mm, middle_limit_mm):
    """Section 8's "warn but place", as data.

    Returns a flag per zone whose manual value EXCEEDS the code limit, and
    nothing else. The wording is deliberate on three counts:

    - it never says "refused", because the placer builds the user's value;
    - it never says "accepted", because the report must show it as a
      visible flag;
    - it carries BOTH numbers, because the spec requires the computed
      limit "ALONGSIDE the user's manual value".

    Only exceeding is flagged. A manual value TIGHTER than the code
    maximum is conservative and entirely legitimate -- flagging it would
    train the engineer to ignore these.
    """
    flags = []
    for zone, value_mm, limit_mm in (
            ("confinement zone", confinement_mm, s0_limit_mm),
            ("middle zone", middle_zone_mm, middle_limit_mm)):
        if value_mm is None or limit_mm is None:
            continue
        if value_mm > limit_mm:
            flags.append(SpacingFlag(
                zone=zone, value_mm=value_mm, limit_mm=limit_mm,
                message=(
                    "%s spacing %.0f mm EXCEEDS the code maximum of %.0f mm. "
                    "The tool will place %.0f mm as entered (section 8, "
                    "Mode B: warn but place)."
                    % (zone[0].upper() + zone[1:], value_mm, limit_mm,
                       value_mm))))
    return flags


def spacing_plan(mode, clear_height_mm, narrow_mm, wide_mm,
                 smallest_long_bar_dia_mm, tie_dia_mm,
                 manual_confinement_mm=None, manual_middle_zone_mm=None):
    """The one place the tie spacings are decided, for BOTH modes.

    Mode A takes the computed maximums; Mode B takes the user's values and
    flags the ones that exceed the same computed maximums. Either way the
    plan carries ``confinement_spacing_mm`` and ``middle_zone_spacing_mm``
    -- what will actually be BUILT -- alongside the code limits, so the
    report and the placer read the same two fields.

    That is section 8's single-source requirement expressed as a data
    structure rather than as a convention two call sites are asked to
    remember.
    """
    if mode not in (MODE_AUTO, MODE_MANUAL):
        raise ValueError(
            "spacing mode must be %r (auto) or %r (manual) -- got %r."
            % (MODE_AUTO, MODE_MANUAL, mode))

    l0_mm, l0_candidates = confinement_zone_length_mm(clear_height_mm, wide_mm)
    s0 = confinement_spacing_mm(smallest_long_bar_dia_mm, tie_dia_mm, narrow_mm)
    middle_max = middle_zone_max_spacing_mm(s0.s0_mm)

    if mode == MODE_AUTO:
        built_confinement = s0.s0_mm
        built_middle = middle_max
        flags = []
    else:
        built_confinement = _positive(manual_confinement_mm,
                                      "the manual confinement-zone spacing")
        built_middle = _positive(manual_middle_zone_mm,
                                 "the manual middle-zone spacing")
        flags = manual_spacing_flags(built_confinement, built_middle,
                                     s0.s0_mm, middle_max)

    return SpacingPlan(
        mode=mode,
        l0_mm=l0_mm,
        l0_candidates=l0_candidates,
        s0_mm=s0.s0_mm,
        s0_governing_label=s0.governing_label,
        s0_candidates=s0.candidates,
        middle_zone_max_mm=middle_max,
        confinement_spacing_mm=built_confinement,
        middle_zone_spacing_mm=built_middle,
        flags=flags,
    )
