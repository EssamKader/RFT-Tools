# -*- coding: utf-8 -*-
"""Thin, focused tests for #203's genuinely new math (Essam's velocity
rule 3, per the ticket's own "Test volume rule"): the starter/end vertical
offset wiring for `dowel_tie`. specs/isolated-footing.md Sec 3 (Story 6),
Sec 9.

Tie SHAPE generation (the closed loop itself) is NOT tested here -- it is
inherited from `rft.core.column_ties`/`column_tie_levels`, already tested
in `tests/test_column_ties.py`/`test_column_tie_levels.py`, and not called
by this ticket at all (see `docs/footing/reuse-audit.md` Sec 1, "Blocked,
not guessed"). Re-testing it here would violate the velocity rule.
"""

import pytest

import rft.core.footing_dowel_ties as footing_dowel_ties
from rft.core.footing_dowel_ties import (
    END_OFFSET_BELOW_TOF_MM,
    START_OFFSET_FROM_FOOTING_BOTTOM_MM,
    DowelTieRunTooShortError,
    dowel_tie_ladder,
    dowel_tie_run_mm,
)


def test_starter_tie_is_50mm_from_the_bottom_of_the_footing():
    run = dowel_tie_run_mm(450.0)
    assert run.start_z_mm == pytest.approx(50.0)
    assert run.start_z_mm == pytest.approx(START_OFFSET_FROM_FOOTING_BOTTOM_MM)


def test_end_tie_is_50mm_below_top_of_footing():
    # T.O.F. == footing_thickness_mm (footing-local, bottom face at z=0).
    run = dowel_tie_run_mm(450.0)
    assert run.end_z_mm == pytest.approx(450.0 - 50.0)
    assert run.end_z_mm == pytest.approx(
        450.0 - END_OFFSET_BELOW_TOF_MM)


def test_end_tie_offset_tracks_a_different_footing_thickness():
    run = dowel_tie_run_mm(900.0)
    assert run.end_z_mm == pytest.approx(850.0)


def test_a_footing_too_thin_for_both_offsets_refuses_rather_than_guesses():
    # start=50, end=90 (thickness=140) -- crosses (50 >= 90 is false here,
    # so use a genuinely-crossing case: thickness=90 -> end=40 < start=50).
    with pytest.raises(DowelTieRunTooShortError):
        dowel_tie_run_mm(90.0)


def test_ladder_first_level_sits_exactly_at_the_starter_offset():
    ladder = dowel_tie_ladder(450.0, tie_spacing_mm=100.0)
    assert ladder.levels[0].z_mm == pytest.approx(50.0)


def test_ladder_last_level_sits_exactly_at_the_end_offset():
    ladder = dowel_tie_ladder(450.0, tie_spacing_mm=100.0)
    assert ladder.levels[-1].z_mm == pytest.approx(400.0)


def test_ladder_never_steps_further_apart_than_the_user_spacing():
    """Sec 9: spacing is a direct user input. Every consecutive pair of
    levels must be at or under it -- never over, whatever the reused
    zone-based ladder's equal-division rounding does in the middle."""
    ladder = dowel_tie_ladder(733.0, tie_spacing_mm=125.0)
    zs = [level.z_mm for level in ladder.levels]
    for lower, upper in zip(zs, zs[1:]):
        assert upper - lower <= 125.0 + 1.0e-6


def test_ladder_run_matches_dowel_tie_run_mm():
    ladder = dowel_tie_ladder(600.0, tie_spacing_mm=150.0)
    run = dowel_tie_run_mm(600.0)
    assert ladder.run == run


def test_ladder_reports_the_spacing_it_was_given():
    ladder = dowel_tie_ladder(600.0, tie_spacing_mm=150.0)
    assert ladder.spacing_mm == pytest.approx(150.0)


def test_no_default_spacing_is_ever_assumed():
    """Sec 9: tie diameter and spacing are direct user inputs, with no
    default -- omitting spacing must refuse, never silently pick one."""
    with pytest.raises(ValueError):
        dowel_tie_ladder(450.0, tie_spacing_mm=None)


def test_asymmetric_offsets_refuse_rather_than_silently_misplace_the_end_tie(
        monkeypatch):
    """The `tie_levels` reuse only works because Sec 9's own start/end
    offsets are the same 50mm value. If a future amendment ever makes them
    differ, this must refuse loudly rather than keep calling `tie_levels`
    with only one of the two offsets."""
    monkeypatch.setattr(
        footing_dowel_ties, "END_OFFSET_BELOW_TOF_MM", 75.0)
    with pytest.raises(NotImplementedError):
        dowel_tie_ladder(450.0, tie_spacing_mm=100.0)


def test_a_run_too_short_for_even_one_spacing_step_refuses():
    # thickness=90 -> start=50, end=40: the two fixed offsets cross before
    # tie_levels is even reached, via dowel_tie_run_mm's own check.
    with pytest.raises(DowelTieRunTooShortError):
        dowel_tie_ladder(90.0, tie_spacing_mm=100.0)


def test_a_large_tie_spacing_relative_to_thickness_does_not_spuriously_refuse():
    """Found and fixed in review: setting `tie_levels`' own `l0_mm` to
    `tie_spacing_mm` (instead of the fixed 50mm offset) made ordinary,
    physically valid inputs refuse purely because `2 * tie_spacing_mm`
    happened to exceed the footing thickness -- nothing to do with
    whether the actual 350mm run between the two fixed offsets can fit a
    250mm spacing (it can, with one middle tie). This is a regression
    test for that fix."""
    ladder = dowel_tie_ladder(450.0, tie_spacing_mm=250.0)
    assert ladder.levels[0].z_mm == pytest.approx(50.0)
    assert ladder.levels[-1].z_mm == pytest.approx(400.0)
    zs = [level.z_mm for level in ladder.levels]
    for lower, upper in zip(zs, zs[1:]):
        assert upper - lower <= 250.0 + 1.0e-6
