# -*- coding: utf-8 -*-
"""#91 -- the tie ladder, and section 6.3's alternation.

The headline case is the live column, and it is a real check rather than a
transcription: #91's brief names "the 16 tie levels" as a known quantity,
and this layout produces exactly 16 from the spec's own rules. A ladder
that produced 15 or 17 would mean the derivation disagrees with whoever
wrote the ticket.
"""

import pytest

from rft.core.column_spacing import FIRST_TIE_OFFSET_MM
from rft.core.column_tie_levels import (
    ZONE_CONFINEMENT_BOTTOM,
    ZONE_CONFINEMENT_TOP,
    ZONE_MIDDLE,
    mirror_map,
    tie_levels,
)

HC = 2700.0
L0 = 600.0
S0 = 127.2
MIDDLE = 254.4


def live():
    return tie_levels(HC, L0, S0, MIDDLE, FIRST_TIE_OFFSET_MM)


def test_the_live_column_gives_the_SIXTEEN_levels_the_ticket_names():
    ladder = live()
    assert len(ladder.levels) == 16
    assert (ladder.bottom_count, ladder.middle_count, ladder.top_count) == (5, 6, 5)


def test_the_first_tie_sits_at_exactly_50_from_each_support_face():
    """Section 4 closes the inequality ambiguity. A maximum is not a
    placeable position, so both ends are anchored at 50 -- and the TOP one
    is 50 from the top face, not wherever a bottom-up run happened to
    land.
    """
    ladder = live()
    assert ladder.levels[0].z_mm == pytest.approx(50.0)
    assert ladder.levels[-1].z_mm == pytest.approx(HC - 50.0)


def test_the_confinement_ties_step_at_S0():
    ladder = live()
    bottom = [lv.z_mm for lv in ladder.levels
              if lv.zone == ZONE_CONFINEMENT_BOTTOM]
    for earlier, later in zip(bottom, bottom[1:]):
        assert later - earlier == pytest.approx(S0)


def test_no_confinement_tie_falls_outside_L0():
    ladder = live()
    for level in ladder.levels:
        if level.zone == ZONE_CONFINEMENT_BOTTOM:
            assert level.z_mm <= L0 + 1e-6
        elif level.zone == ZONE_CONFINEMENT_TOP:
            assert level.z_mm >= HC - L0 - 1e-6


def test_the_middle_run_is_divided_EQUALLY_and_under_the_cap():
    """Stepping from one end leaves a short final bay, which is a site
    query every time. Equal division satisfies the same maximum.
    """
    ladder = live()
    zs = [lv.z_mm for lv in ladder.levels]
    gaps = [b - a for a, b in zip(zs, zs[1:])]
    middle_gaps = gaps[ladder.bottom_count - 1:
                       ladder.bottom_count + ladder.middle_count]
    assert middle_gaps, "no middle-zone gaps found"
    for gap in middle_gaps:
        assert gap == pytest.approx(middle_gaps[0]), "a ragged final bay"
        assert gap <= MIDDLE + 1e-6, "a gap above the section 5 maximum"
    assert ladder.middle_spacing_mm == pytest.approx(middle_gaps[0])


def test_every_gap_in_the_whole_ladder_is_within_its_zone_maximum():
    ladder = live()
    zs = [lv.z_mm for lv in ladder.levels]
    for gap in (b - a for a, b in zip(zs, zs[1:])):
        assert gap <= MIDDLE + 1e-6


def test_the_levels_are_ordered_and_distinct():
    zs = [lv.z_mm for lv in live().levels]
    assert zs == sorted(zs)
    assert len(set(round(z, 6) for z in zs)) == len(zs)


def test_the_indices_are_contiguous_from_zero():
    """They are the bar POSITION indices the per-bar transform will use.
    #70 found a layout change does not remap them, so they are stored and
    carried rather than recomputed downstream.
    """
    assert [lv.index for lv in live().levels] == list(range(16))


def test_section_6_3_alternates_every_other_level():
    ladder = live()
    flags = [lv.mirrored for lv in ladder.levels]
    assert flags == [bool(i % 2) for i in range(len(flags))]
    for earlier, later in zip(flags, flags[1:]):
        assert earlier != later, (
            "the hook corner must MOVE between consecutive levels")


def test_the_mirror_map_is_keyed_by_index():
    """``Rebar.MoveBarInSet`` takes a bar position index, so that is the
    shape the map has. Anything else would be converted at the call site,
    which is where #70's scrambling bug lives.
    """
    mapping = mirror_map(live())
    assert set(mapping) == set(range(1, 16, 2))
    assert all(value is True for value in mapping.values())


def test_mode_b_spacings_drive_the_ladder_not_the_code_limits():
    """The ladder must describe the MODEL. Feeding it the code maximums in
    Mode B would list ties at positions nothing will occupy.
    """
    tighter = tie_levels(HC, L0, 100.0, 200.0, FIRST_TIE_OFFSET_MM)
    assert len(tighter.levels) > 16
    assert tighter.levels[1].z_mm == pytest.approx(150.0)


def test_a_column_shorter_than_two_confinement_zones_is_refused():
    """The whole column is then a confinement region, which this layout
    does not describe. A silently empty middle run would hide that.
    """
    with pytest.raises(ValueError) as excinfo:
        tie_levels(1000.0, 600.0, S0, MIDDLE, FIRST_TIE_OFFSET_MM)
    assert "no middle zone" in str(excinfo.value)
    assert "needs a ruling" in str(excinfo.value)


def test_a_first_tie_beyond_L0_is_refused():
    with pytest.raises(ValueError) as excinfo:
        tie_levels(HC, 40.0, S0, MIDDLE, FIRST_TIE_OFFSET_MM)
    assert "no confinement tie" in str(excinfo.value)


@pytest.mark.parametrize("kwargs", [
    {"clear_height_mm": 0.0},
    {"l0_mm": None},
    {"confinement_spacing_mm": -10.0},
    {"middle_zone_spacing_mm": 0.0},
])
def test_a_missing_input_is_refused(kwargs):
    args = dict(clear_height_mm=HC, l0_mm=L0, confinement_spacing_mm=S0,
                middle_zone_spacing_mm=MIDDLE,
                first_tie_offset_mm=FIRST_TIE_OFFSET_MM)
    args.update(kwargs)
    with pytest.raises(ValueError):
        tie_levels(**args)
