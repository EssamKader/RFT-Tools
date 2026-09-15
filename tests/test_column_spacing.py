# -*- coding: utf-8 -*-
"""#88 -- spec sections 3, 4, 5 and 8, the tie spacing arithmetic.

The worked numbers are the LIVE test column: `450 x 600mm`, clear height
2700 mm (measured to the soffit, not the 3000 mm Length parameter), `16M`
longitudinal at 15.90 mm and `10M` ties at 9.50 mm. Using the real bar
diameters matters: a test written against a nominal 16.0 would pass while
the tool shipped 127.2 and the test expected 128.0.
"""

import pytest

from rft.core.column_spacing import (
    FIRST_TIE_OFFSET_MM,
    MODE_AUTO,
    MODE_MANUAL,
    confinement_spacing_mm,
    confinement_zone_length_mm,
    manual_spacing_flags,
    middle_zone_max_spacing_mm,
    spacing_plan,
)

HC = 2700.0
NARROW = 450.0
WIDE = 600.0
LONG_DIA = 15.90   # 16M, measured live
TIE_DIA = 9.50     # 10M, measured live


def test_l0_on_the_live_column():
    """max(2700/6, 600, 500) = max(450, 600, 500) = 600."""
    l0, candidates = confinement_zone_length_mm(HC, WIDE)
    assert l0 == 600.0
    assert [c.value_mm for c in candidates] == [450.0, 600.0, 500.0]


def test_l0_takes_the_LARGER_section_dimension():
    """Section 2's C2 rule: the larger dimension governs L0, the smaller
    governs S0. Swapping them inverts both silently, which is why the
    caller is handed narrow/wide already resolved rather than b/h.
    """
    assert confinement_zone_length_mm(HC, WIDE)[0] == 600.0
    assert confinement_zone_length_mm(HC, NARROW)[0] == 500.0  # floor wins


def test_the_500_floor_governs_a_short_small_column():
    l0, _ = confinement_zone_length_mm(2100.0, 300.0)
    assert l0 == 500.0


def test_the_height_term_governs_a_tall_column():
    l0, _ = confinement_zone_length_mm(6000.0, 400.0)
    assert l0 == 1000.0


def test_s0_on_the_live_column_and_which_term_governs():
    """min(8 x 15.9, 24 x 9.5, 450/2, 150) = min(127.2, 228, 225, 150)."""
    s0 = confinement_spacing_mm(LONG_DIA, TIE_DIA, NARROW)
    assert s0.s0_mm == pytest.approx(127.2)
    assert s0.governing_label == "8 x smallest longitudinal bar"


def test_the_absolute_cap_governs_a_large_column_with_large_bars():
    s0 = confinement_spacing_mm(25.0, 12.0, 900.0)
    assert s0.s0_mm == 150.0
    assert s0.governing_label == "absolute cap"


def test_half_the_smaller_dimension_can_govern():
    s0 = confinement_spacing_mm(25.0, 12.0, 250.0)
    assert s0.s0_mm == 125.0
    assert s0.governing_label == "half the smaller section dimension"


def test_the_tie_term_can_govern():
    s0 = confinement_spacing_mm(32.0, 5.0, 900.0)
    assert s0.s0_mm == 120.0
    assert s0.governing_label == "24 x tie diameter"


def test_a_tie_names_the_first_governing_term_in_SPEC_order():
    """Two candidates at the same value must not make the reported reason
    depend on iteration order -- the report prints this string.
    """
    # 8 x 18.75 = 150 = the absolute cap.
    s0 = confinement_spacing_mm(18.75, 12.0, 900.0)
    assert s0.s0_mm == 150.0
    assert s0.governing_label == "8 x smallest longitudinal bar"


def test_the_SMALLEST_longitudinal_bar_governs_not_the_largest():
    """Taking the largest would RAISE S0 and under-confine the column --
    the unsafe direction. The spec says smallest; the parameter is named
    for it so a caller passing "the" bar diameter reads the requirement.
    """
    small = confinement_spacing_mm(12.0, TIE_DIA, NARROW).s0_mm
    large = confinement_spacing_mm(25.0, TIE_DIA, NARROW).s0_mm
    assert small < large


def test_middle_zone_is_twice_s0_with_no_150_cap():
    """Section 5 exists to CORRECT a bare 150 that belonged to a different
    rule. A min(..., 150) here would reintroduce the error the spec fixed.
    """
    assert middle_zone_max_spacing_mm(127.2) == pytest.approx(254.4)
    assert middle_zone_max_spacing_mm(150.0) == 300.0


def test_the_first_tie_offset_is_an_exact_position_not_a_maximum():
    """Section 4 closes the inequality ambiguity: the code's "not
    exceeding S0" is a maximum, and a maximum is not a placeable
    position.
    """
    assert FIRST_TIE_OFFSET_MM == 50.0


# --------------------------------------------------------------------- #
# Section 8 -- Mode A / Mode B


def test_mode_a_builds_the_computed_maximums():
    plan = spacing_plan(MODE_AUTO, HC, NARROW, WIDE, LONG_DIA, TIE_DIA)
    assert plan.confinement_spacing_mm == plan.s0_mm
    assert plan.middle_zone_spacing_mm == plan.middle_zone_max_mm
    assert plan.flags == []


def test_mode_b_builds_the_USER_value_and_flags_it():
    """"Warn but place". The tool does not refuse and does not silently
    accept: the number that will be BUILT is the user's, and the flag
    carries both numbers.
    """
    plan = spacing_plan(MODE_MANUAL, HC, NARROW, WIDE, LONG_DIA, TIE_DIA,
                        manual_confinement_mm=200.0,
                        manual_middle_zone_mm=300.0)
    assert plan.confinement_spacing_mm == 200.0, "the user's value is built"
    assert plan.middle_zone_spacing_mm == 300.0
    assert len(plan.flags) == 2
    for flag in plan.flags:
        assert "EXCEEDS" in flag.message
        assert "will place" in flag.message
        assert "refus" not in flag.message.lower(), (
            "a flag that says refused contradicts what the placer does")


def test_the_report_and_the_placer_read_the_same_field():
    """Section 8's single-source rule, as a structure rather than a
    convention two call sites are asked to remember. A report reading
    ``s0_mm`` while the placer reads ``confinement_spacing_mm`` would
    disagree in Mode B -- which is the only mode where it matters.
    """
    plan = spacing_plan(MODE_MANUAL, HC, NARROW, WIDE, LONG_DIA, TIE_DIA,
                        manual_confinement_mm=200.0,
                        manual_middle_zone_mm=300.0)
    assert plan.s0_mm != plan.confinement_spacing_mm
    assert plan.flags[0].limit_mm == plan.s0_mm
    assert plan.flags[0].value_mm == plan.confinement_spacing_mm


def test_a_tighter_manual_spacing_is_not_flagged():
    """Tighter than the code maximum is conservative and legitimate.
    Flagging it would train the engineer to ignore these.
    """
    plan = spacing_plan(MODE_MANUAL, HC, NARROW, WIDE, LONG_DIA, TIE_DIA,
                        manual_confinement_mm=100.0,
                        manual_middle_zone_mm=200.0)
    assert plan.flags == []
    assert plan.confinement_spacing_mm == 100.0


def test_only_the_violating_zone_is_flagged():
    plan = spacing_plan(MODE_MANUAL, HC, NARROW, WIDE, LONG_DIA, TIE_DIA,
                        manual_confinement_mm=200.0,
                        manual_middle_zone_mm=200.0)
    assert [f.zone for f in plan.flags] == ["confinement zone"]


def test_a_value_exactly_at_the_limit_is_not_a_violation():
    s0 = confinement_spacing_mm(LONG_DIA, TIE_DIA, NARROW).s0_mm
    assert manual_spacing_flags(s0, middle_zone_max_spacing_mm(s0),
                                s0, middle_zone_max_spacing_mm(s0)) == []


def test_mode_b_without_values_is_a_read_failure_not_a_silent_zero():
    with pytest.raises(ValueError):
        spacing_plan(MODE_MANUAL, HC, NARROW, WIDE, LONG_DIA, TIE_DIA)


def test_an_unknown_mode_is_refused():
    with pytest.raises(ValueError) as excinfo:
        spacing_plan("C", HC, NARROW, WIDE, LONG_DIA, TIE_DIA)
    assert "auto" in str(excinfo.value)


@pytest.mark.parametrize("kwargs", [
    {"clear_height_mm": 0.0},
    {"narrow_mm": 0.0},
    {"wide_mm": -600.0},
    {"smallest_long_bar_dia_mm": 0.0},
    {"tie_dia_mm": None},
])
def test_a_missing_measurement_is_refused_rather_than_treated_as_small(kwargs):
    args = dict(mode=MODE_AUTO, clear_height_mm=HC, narrow_mm=NARROW,
                wide_mm=WIDE, smallest_long_bar_dia_mm=LONG_DIA,
                tie_dia_mm=TIE_DIA)
    args.update(kwargs)
    with pytest.raises(ValueError):
        spacing_plan(**args)
