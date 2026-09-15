# -*- coding: utf-8 -*-
"""#90 -- section 2's perimeter model and section 6.1's tiered rule.

The coordinates are checked against ``docs/column/verification/
issue-67-q9-inner-subset-tie.md``, which derived the same layout from the
spec by hand on the live 450 x 600 column: corner bars at
``u = +/-167.6, v = +/-242.6`` and intermediates at ``v = +/-80.9``.
"""

import pytest

from rft.core.column_layout import (
    MAX_TIE_BRANCH_SPACING_MM,
    TIER_ALTERNATE,
    TIER_EVERY_BAR,
    TIER_EXCEEDED,
    bar_centre_offset_mm,
    perimeter_bar_positions,
    tie_half_dimensions_mm,
    tier_for_clear_distance,
    tier_summary,
    worst_gap,
)

B, H, COVER, TIE, BAR = 450.0, 600.0, 40.0, 9.5, 15.9


def live(count_b=3, count_h=4):
    return perimeter_bar_positions(B, H, COVER, TIE, BAR, count_b, count_h)


def test_the_bar_offset_matches_the_hand_derivation():
    """40 + 9.5 + 15.9/2 = 57.45, the number #67 worked out by hand and
    #80 saw the placer ask for.
    """
    assert bar_centre_offset_mm(COVER, TIE, BAR) == pytest.approx(57.45)


def test_the_corner_positions_match_the_verified_layout():
    layout = live()
    corners = [(layout.bars[i].u_mm, layout.bars[i].v_mm)
               for i in layout.corner_indices]
    for u, v in corners:
        assert abs(u) == pytest.approx(167.55, abs=0.05)
        assert abs(v) == pytest.approx(242.55, abs=0.05)


def test_the_intermediate_bars_match_the_verified_layout():
    layout = live()
    # A tolerance, not a rounding: +80.85 and -80.85 come out of the
    # arithmetic a float-epsilon apart, so round(..., 1) put them in two
    # different buckets and the test failed on a layout that is correct.
    vs = [abs(bar.v_mm) for bar in layout.bars
          if not bar.is_corner and abs(bar.u_mm) > 100]
    assert len(vs) == 4, "two intermediate bars on each h-face"
    for v in vs:
        assert v == pytest.approx(80.85, abs=0.05)


def test_the_tie_centreline_carries_the_HALF_TIE_term():
    """#67's page labels 185.0 as the outer tie centreline. That is
    ``b/2 - cover``, the tie's OUTER FACE. #80 MEASURED a tie for the same
    column and cover landing at half-u 180.25, which is
    ``b/2 - cover - tie/2``.

    CreateFromCurves takes centrelines, so the half-tie term belongs, and
    the measured number is the one to trust. See the correction banner now
    on #67's page.
    """
    half_u, half_v = tie_half_dimensions_mm(B, H, COVER, TIE)
    assert half_u == pytest.approx(180.25)
    assert half_v == pytest.approx(255.25)
    assert half_u != pytest.approx(185.0)


def test_the_four_corner_bars_appear_ONCE_each():
    """The trap the reuse audit names: ``corner_bar_u_positions_mm`` puts
    a bar at EACH end of a face, so four faces concatenated give eight
    corners -- and it would pass a per-face check.
    """
    layout = live()
    assert len(layout.corner_indices) == 4
    assert len(layout.bars) == 10, "2 x (3 + 4) - 4"
    positions = [(round(bar.u_mm, 6), round(bar.v_mm, 6))
                 for bar in layout.bars]
    assert len(set(positions)) == len(positions), "a bar was placed twice"


def test_the_bars_are_ordered_AROUND_the_perimeter():
    """Order is data, not presentation: section 6.1's clear distances are
    between CONSECUTIVE bars, and section 6.2's subsets are "an initial
    bar index and the number of tied bars".
    """
    layout = live()
    assert [bar.index for bar in layout.bars] == list(range(10))
    # Consecutive bars are neighbours: no step jumps across the section.
    for gap in layout.gaps:
        a, b = layout.bars[gap.from_index], layout.bars[gap.to_index]
        step = ((a.u_mm - b.u_mm) ** 2 + (a.v_mm - b.v_mm) ** 2) ** 0.5
        assert step < max(B, H), "consecutive bars are not adjacent"


def test_the_perimeter_closes():
    """The last bar's gap returns to the first. A perimeter with an open
    end would silently omit one clear distance -- and it would be the one
    spanning a corner.
    """
    layout = live()
    assert len(layout.gaps) == len(layout.bars)
    assert layout.gaps[-1].to_index == 0


def test_the_gap_is_CLEAR_distance_not_centre_to_centre():
    """Section 6.1 says clear distance. Centre-to-centre overstates every
    gap by one bar diameter and mis-tiers the borderline ones -- and the
    live column sits at 151.7, six millimetres over a tier boundary.
    """
    layout = live()
    gap = layout.gaps[0]
    a, b = layout.bars[0], layout.bars[1]
    centre_to_centre = ((b.u_mm - a.u_mm) ** 2 + (b.v_mm - a.v_mm) ** 2) ** 0.5
    assert gap.clear_mm == pytest.approx(centre_to_centre - BAR)


def test_the_live_column_lands_in_the_every_bar_tier():
    """151.7 mm, just over the 150 boundary -- so every bar must be tied.
    A centre-to-centre gap would have read 167.6 and reached the same
    tier by accident; a nominal 16 mm bar would have read 151.6 and also
    passed. The boundary is close enough that the real diameter matters.
    """
    layout = live()
    worst = worst_gap(layout)
    assert worst.clear_mm == pytest.approx(151.7, abs=0.1)
    assert worst.tier == TIER_EVERY_BAR
    assert "EVERY bar must be restrained" in tier_summary(layout)


def test_more_bars_drop_the_layout_into_the_alternate_tier():
    layout = live(count_b=4, count_h=5)
    assert worst_gap(layout).tier == TIER_ALTERNATE
    assert "alternate bars may be left untied" in tier_summary(layout)


def test_a_bare_four_bar_column_exceeds_every_tier():
    """Four corner bars on a 450 x 600 leaves a clear distance no tier
    covers. Section 6.1 stops at 250 mm, so this is the absence of a rule
    rather than a fourth tier -- and the sketch paints it as a failure.
    """
    layout = live(count_b=2, count_h=2)
    assert worst_gap(layout).tier == TIER_EXCEEDED
    assert "EXCEEDS" in tier_summary(layout)
    assert "add intermediate bars" in tier_summary(layout)


@pytest.mark.parametrize("clear_mm,tier", [
    (0.0, TIER_ALTERNATE),
    (150.0, TIER_ALTERNATE),
    (150.01, TIER_EVERY_BAR),
    (250.0, TIER_EVERY_BAR),
    (250.01, TIER_EXCEEDED),
])
def test_the_tier_boundaries_are_inclusive_upward(clear_mm, tier):
    """Section 6.1 reads "x <= 150" and "150 < x <= 250", so each bound
    belongs to the tighter tier.
    """
    assert tier_for_clear_distance(clear_mm) == tier


def test_the_tie_branch_limit_is_NAMED_but_not_evaluated_here():
    """300 mm governs the distance between TIE BRANCHES, which is a
    property of the topology -- issue #89, blocked on Q11 -- not of the
    bar layout. Naming it stops the next reader assuming it was
    forgotten; evaluating it would require inventing the topology.
    """
    assert MAX_TIE_BRANCH_SPACING_MM == 300.0
    layout = live()
    assert not any(getattr(gap, "branch", None) for gap in layout.gaps)


def test_a_section_too_small_for_its_cover_is_refused():
    with pytest.raises(ValueError) as excinfo:
        perimeter_bar_positions(100.0, 100.0, 40.0, 9.5, 15.9, 2, 2)
    assert "outside the concrete" in str(excinfo.value)


def test_a_face_with_one_bar_is_refused_by_the_shared_function():
    """``corner_bar_u_positions_mm`` raises for < 2, citing the beam
    spec's silence on a one-bar face. A column face carrying only its two
    shared corners is normal; fewer is not.
    """
    with pytest.raises(ValueError):
        live(count_b=1)
