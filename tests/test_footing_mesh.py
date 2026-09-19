# -*- coding: utf-8 -*-
"""Mutation-proving tests for the genuinely new math in #198 (Essam's
velocity rule 3): Z/Z2/N/N2/mesh_bar_x/mesh_bar_y and the X-vs-Y direction
comparison. specs/isolated-footing.md Sec 3 (Story 1), Sec 4, Sec 2.

These assert concrete, hand-computed numbers rather than round-tripping
the formula against itself, so a mutated operator (+ for -, a swapped
term) changes the expected result and the test fails -- the same
mutation-proving bar tools/prove_guards.py enforces for text guards, met
here by direct numeric assertion since this module is plain, importable
Python (no Revit import), not text-scraped source.
"""

import pytest

from rft.core.footing_mesh import (
    DIRECTION_X,
    DIRECTION_Y,
    local_mesh_bar_endpoints,
    mesh_bar_lengths,
    primary_reinforcement_direction,
)


def test_mesh_bar_lengths_match_the_spec_formulas_by_hand():
    # a=1800, b=1200, cover=50, thickness=450, bottom_cover=50,
    # top_cover=50, mesh_bar_x_dia=16.
    # Z = 1800 - 100 = 1700; Z2 = 1200 - 100 = 1100
    # N = 450 - 50 - 50 = 350
    # N2 = 450 - 50 - 16 - 50 = 334
    # mesh_bar_x = 1700 + 700 = 2400
    # mesh_bar_y = 1100 + 668 = 1768
    lengths = mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)
    assert lengths.z_mm == pytest.approx(1700.0)
    assert lengths.z2_mm == pytest.approx(1100.0)
    assert lengths.n_mm == pytest.approx(350.0)
    assert lengths.n2_mm == pytest.approx(334.0)
    assert lengths.mesh_bar_x_mm == pytest.approx(2400.0)
    assert lengths.mesh_bar_y_mm == pytest.approx(1768.0)


def test_a_different_footing_still_matches_by_hand():
    # a=2200, b=2200 (square footing), cover=75, thickness=600,
    # bottom_cover=75, top_cover=40, mesh_bar_x_dia=20.
    # Z = Z2 = 2200 - 150 = 2050
    # N = 600 - 75 - 40 = 485
    # N2 = 600 - 75 - 20 - 40 = 465
    # mesh_bar_x = 2050 + 970 = 3020
    # mesh_bar_y = 2050 + 930 = 2980
    lengths = mesh_bar_lengths(
        a_mm=2200.0, b_mm=2200.0, cover_mm=75.0,
        footing_thickness_mm=600.0, bottom_cover_mm=75.0,
        top_cover_mm=40.0, mesh_bar_x_dia_mm=20.0)
    assert lengths.z_mm == pytest.approx(2050.0)
    assert lengths.z2_mm == pytest.approx(2050.0)
    assert lengths.n_mm == pytest.approx(485.0)
    assert lengths.n2_mm == pytest.approx(465.0)
    assert lengths.mesh_bar_x_mm == pytest.approx(3020.0)
    assert lengths.mesh_bar_y_mm == pytest.approx(2980.0)


def test_n2_is_strictly_less_than_n_by_exactly_the_mesh_bar_x_diameter():
    """Guards the ONE difference between N and N2's formulas: N2 subtracts
    the extra ⌀mesh_bar_x term N does not. A mutation that drops that term
    (N2 == N) or adds it twice must be caught by this, independent of the
    hand-computed cases above.
    """
    lengths = mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)
    assert lengths.n_mm - lengths.n2_mm == pytest.approx(16.0)


def test_mesh_bar_x_uses_n_and_mesh_bar_y_uses_n2_not_swapped():
    """A swap of N/N2 between the two bars would still produce two
    plausible-looking lengths, so this checks the PAIRING directly rather
    than only the two lengths' final values.
    """
    lengths = mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)
    assert lengths.mesh_bar_x_mm == pytest.approx(lengths.z_mm + 2.0 * lengths.n_mm)
    assert lengths.mesh_bar_y_mm == pytest.approx(lengths.z2_mm + 2.0 * lengths.n2_mm)


def test_x_greater_than_y_is_primary_in_x():
    assert primary_reinforcement_direction(300.0, 150.0) == DIRECTION_X


def test_y_greater_than_x_is_primary_in_y():
    assert primary_reinforcement_direction(150.0, 300.0) == DIRECTION_Y


def test_equal_offsets_default_to_x_per_ruling_r1():
    """Spec Ref: Sec 2/3 never defines X == Y. Raised to the project owner
    rather than guessed; docs/footing/spec-amendments.md R1 records the
    ruling -- it does not matter which direction is Primary in the tie
    case, so this defaults to DIRECTION_X rather than raising.
    """
    assert primary_reinforcement_direction(200.0, 200.0) == DIRECTION_X


def test_local_mesh_bar_endpoints_are_centred_and_span_the_full_length():
    lengths = mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)
    bar_x, bar_y = local_mesh_bar_endpoints(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)

    assert bar_x.start.x_mm == pytest.approx(-lengths.mesh_bar_x_mm / 2.0)
    assert bar_x.end.x_mm == pytest.approx(lengths.mesh_bar_x_mm / 2.0)
    assert bar_x.start.y_mm == pytest.approx(0.0)
    assert bar_x.end.y_mm == pytest.approx(0.0)

    assert bar_y.start.y_mm == pytest.approx(-lengths.mesh_bar_y_mm / 2.0)
    assert bar_y.end.y_mm == pytest.approx(lengths.mesh_bar_y_mm / 2.0)
    assert bar_y.start.x_mm == pytest.approx(0.0)
    assert bar_y.end.x_mm == pytest.approx(0.0)


def test_mesh_bar_y_sits_exactly_one_mesh_bar_x_diameter_above_mesh_bar_x():
    """Spec Ref: Sec 2 naming table -- "mesh_bar_y ... stacked above
    mesh_bar_x", unconditional on which direction is Primary. The vertical
    offset is mesh_bar_x's own diameter, the same term Sec 4's N2 formula
    already uses -- not a newly invented stacking distance.
    """
    lengths = mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)
    bar_x, bar_y = local_mesh_bar_endpoints(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0)

    z_x = bar_x.start.z_mm
    z_y = bar_y.start.z_mm
    assert z_x == pytest.approx(50.0 + 16.0 / 2.0)
    assert z_y == pytest.approx(z_x + 16.0 / 2.0 + 12.0 / 2.0)
