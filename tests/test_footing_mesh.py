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
    MAT_SHAPE_L_ALTERNATING,
    MAT_SHAPE_U,
    SHAPE_L,
    SHAPE_U,
    BarEndHook,
    BarHookPlan,
    HookDevelopmentLengthTieError,
    bar_end_hook_decision,
    bar_hook_plan,
    bar_hook_plan_for_mat,
    bottom_mesh_bar_array_geometry,
    bottom_mesh_bar_geometry,
    local_mesh_bar_endpoints,
    local_top_mesh_bar_endpoints,
    mesh_bar_lengths,
    mesh_bar_offsets_mm,
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


def test_local_top_mesh_bar_endpoints_mirrors_the_bottom_mat_from_the_top_face():
    """Found missing in review (PR #214): a naive reuse of
    local_mesh_bar_endpoints for the top mat placed it at the bottom
    mat's own elevation. This is the top-mat equivalent, measured from
    the TOP face downward instead of from the bottom face upward.
    """
    lengths = mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)
    bar_x, bar_y = local_top_mesh_bar_endpoints(
        lengths, top_cover_mm=50.0, footing_thickness_mm=450.0,
        mesh_bar_x_dia_mm=16.0, mesh_bar_y_dia_mm=12.0)

    z_x = bar_x.start.z_mm
    z_y = bar_y.start.z_mm
    assert z_x == pytest.approx(450.0 - 50.0 - 16.0 / 2.0)
    assert z_y == pytest.approx(z_x - 16.0 / 2.0 - 12.0 / 2.0)
    # Plan-view (x/y) geometry is identical to the bottom mat -- only Z
    # differs. Same lengths, same centring.
    assert bar_x.start.x_mm == pytest.approx(-lengths.mesh_bar_x_mm / 2.0)
    assert bar_y.start.y_mm == pytest.approx(-lengths.mesh_bar_y_mm / 2.0)


# ---------------------------------------------------------------------
# #199 -- per-end hook/development-length decision (Story 2, Sec 5).
# Mutation-proven: Essam's velocity rule 3 requires full coverage of
# genuinely new math, and the hook-vs-no-hook / U-vs-L-shape decision is
# exactly that -- nothing here is inherited from RFT.lib/ColumnRFT.
# ---------------------------------------------------------------------

def test_ld_greater_than_offset_needs_a_hook():
    # LD = 40 * 16 = 640 > offset 300 -> hook.
    decision = bar_end_hook_decision(
        offset_mm=300.0, db_mm=16.0, ld_multiplier=40.0)
    assert decision.ld_mm == pytest.approx(640.0)
    assert decision.needs_hook is True


def test_offset_greater_than_ld_does_not_need_a_hook():
    # LD = 10 * 16 = 160 < offset 300 -> no hook.
    decision = bar_end_hook_decision(
        offset_mm=300.0, db_mm=16.0, ld_multiplier=10.0)
    assert decision.ld_mm == pytest.approx(160.0)
    assert decision.needs_hook is False


def test_ld_is_multiplier_times_db_not_swapped_or_added():
    """Guards the exact Sec 5 formula LD = multiplier * db, independent
    of the hook/no-hook boundary -- a mutation swapping multiplier/db or
    turning '*' into '+' would still pass the two tests above by luck for
    some inputs, so this checks the raw product directly.
    """
    decision = bar_end_hook_decision(
        offset_mm=1.0, db_mm=12.0, ld_multiplier=5.0)
    assert decision.ld_mm == pytest.approx(60.0)


def test_ld_equal_to_offset_raises_rather_than_silently_pick_a_side():
    """Spec Ref: Sec 5 only defines '>' in each direction. Raised to the
    project owner rather than guessed; docs/footing/spec-amendments.md
    R2 (revised) records the ruling -- the automatic comparison refuses,
    and the engineer gets an explicit U-shape/L-shape-alternating choice
    for that mat via #200's bar_hook_plan_for_mat instead.
    """
    with pytest.raises(HookDevelopmentLengthTieError):
        bar_end_hook_decision(offset_mm=160.0, db_mm=16.0, ld_multiplier=10.0)


def test_both_ends_needing_a_hook_is_u_shape():
    plan = bar_hook_plan(
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=40.0)
    assert plan.start.needs_hook is True
    assert plan.end.needs_hook is True
    assert plan.shape == SHAPE_U


def test_one_end_not_needing_a_hook_switches_the_whole_bar_to_l_shape():
    # start: LD = 40*16 = 640 > 300 -> hook. end: LD = 10*16 = 160 < 300
    # -> no hook. Sec 5: "switch that bar from U-shape to L-shape".
    plan = bar_hook_plan(
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=40.0)
    other_end_plan = bar_hook_plan(
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=10.0)
    assert plan.shape == SHAPE_U
    assert other_end_plan.shape != SHAPE_U

    mixed_plan_start = bar_end_hook_decision(300.0, 16.0, 40.0)
    mixed_plan_end = bar_end_hook_decision(300.0, 16.0, 10.0)
    assert mixed_plan_start.needs_hook is True
    assert mixed_plan_end.needs_hook is False


def test_bar_hook_plan_uses_the_l_shape_constant_not_a_bespoke_string():
    plan = bar_hook_plan(
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=10.0)
    assert plan.shape == SHAPE_L
    assert plan.shape != SHAPE_U


def test_neither_end_needing_a_hook_is_not_u_shape():
    plan = bar_hook_plan(
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=1.0)
    assert plan.start.needs_hook is False
    assert plan.end.needs_hook is False
    assert plan.shape == SHAPE_L


# ---------------------------------------------------------------------
# #200 -- per-mat U-shape/L-shape-alternating user override (Story 3,
# Sec 6). Mutation-proven: Essam's velocity rule 3 names "the alternation
# logic (which end gets hooked on odd/even bar index) and the
# override-of-#199 behavior" as this ticket's genuinely new math.
# ---------------------------------------------------------------------

def test_no_override_delegates_to_bar_hook_plan_unchanged():
    """mat_shape_mode=None must reproduce #199's own decision exactly --
    this is the "Story 2's comparison only applies if/when the tool needs
    to decide the shape itself" half of Sec 6, not a new code path.
    """
    direct = bar_hook_plan(
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=10.0)
    via_mat = bar_hook_plan_for_mat(
        bar_index=0, mat_shape_mode=None,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=10.0)
    assert via_mat == direct


def test_mat_shape_u_hooks_both_ends_unconditionally():
    """A user MAT_SHAPE_U override must win even when the LD-vs-offset
    comparison would otherwise switch this bar to L-shape (LD=160 <
    offset=300 -> #199 alone would leave both ends unhooked / L-shape).
    """
    plan = bar_hook_plan_for_mat(
        bar_index=0, mat_shape_mode=MAT_SHAPE_U,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=10.0)
    assert plan.start.needs_hook is True
    assert plan.end.needs_hook is True
    assert plan.shape == SHAPE_U


def test_mat_shape_u_override_wins_even_where_bar_end_hook_decision_would_say_no():
    """Sec 6: the override makes Story 2's comparison "unnecessary", not
    merely pre-empted -- an offset where LD < offset (bar_end_hook_
    decision alone would leave this end unhooked) must still come out
    hooked once MAT_SHAPE_U is set.
    """
    plan = bar_hook_plan_for_mat(
        bar_index=0, mat_shape_mode=MAT_SHAPE_U,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=10.0)
    assert plan.start.needs_hook is True
    assert plan.end.needs_hook is True


def test_mat_shape_l_alternating_hooks_the_start_end_on_even_bar_index():
    plan = bar_hook_plan_for_mat(
        bar_index=0, mat_shape_mode=MAT_SHAPE_L_ALTERNATING,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=40.0)
    assert plan.start.needs_hook is True
    assert plan.end.needs_hook is False
    assert plan.shape == SHAPE_L


def test_mat_shape_l_alternating_hooks_the_end_end_on_odd_bar_index():
    plan = bar_hook_plan_for_mat(
        bar_index=1, mat_shape_mode=MAT_SHAPE_L_ALTERNATING,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=40.0)
    assert plan.start.needs_hook is False
    assert plan.end.needs_hook is True
    assert plan.shape == SHAPE_L


def test_mat_shape_l_alternating_keeps_alternating_past_the_first_pair():
    """Guards against an off-by-one or a mutation that only checks
    ``bar_index == 0``/``== 1`` instead of parity -- indices 2 and 3 must
    repeat the same even/odd pattern as 0 and 1.
    """
    even_again = bar_hook_plan_for_mat(
        bar_index=2, mat_shape_mode=MAT_SHAPE_L_ALTERNATING,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=40.0)
    odd_again = bar_hook_plan_for_mat(
        bar_index=3, mat_shape_mode=MAT_SHAPE_L_ALTERNATING,
        start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
        ld_multiplier=40.0)
    assert even_again.start.needs_hook is True
    assert even_again.end.needs_hook is False
    assert odd_again.start.needs_hook is False
    assert odd_again.end.needs_hook is True


def test_mat_shape_l_alternating_never_hooks_both_ends_of_one_bar():
    """A mutation that drops the "not hook_start" and hard-codes both
    ends True (silently degrading to U-shape) must fail this: Sec 6 says
    L-Shape-Alternating bars are "each ... L-shaped (one hook)".
    """
    for bar_index in range(4):
        plan = bar_hook_plan_for_mat(
            bar_index=bar_index, mat_shape_mode=MAT_SHAPE_L_ALTERNATING,
            start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
            ld_multiplier=40.0)
        assert plan.start.needs_hook != plan.end.needs_hook


def test_mat_shape_l_alternating_override_never_raises_the_199_tie_error():
    plan = bar_hook_plan_for_mat(
        bar_index=0, mat_shape_mode=MAT_SHAPE_L_ALTERNATING,
        start_offset_mm=160.0, end_offset_mm=160.0, db_mm=16.0,
        ld_multiplier=10.0)
    assert plan.start.needs_hook is True
    assert plan.end.needs_hook is False


def test_unknown_mat_shape_mode_raises_rather_than_silently_default():
    with pytest.raises(ValueError):
        bar_hook_plan_for_mat(
            bar_index=0, mat_shape_mode="bogus",
            start_offset_mm=300.0, end_offset_mm=300.0, db_mm=16.0,
            ld_multiplier=40.0)


# ---------------------------------------------------------------------
# #229 -- the mesh bar's own REAL bent centreline, honouring #199/#200's
# hook decision instead of a plain straight line spanning the full
# mesh_bar_x_mm/mesh_bar_y_mm total.
# ---------------------------------------------------------------------

def _lengths():
    return mesh_bar_lengths(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0)


def test_neither_end_hooked_is_a_plain_two_point_straight_run():
    lengths = _lengths()
    no_hook = BarHookPlan(
        start=BarEndHook(ld_mm=640.0, needs_hook=False),
        end=BarEndHook(ld_mm=640.0, needs_hook=False), shape=SHAPE_L)
    bar_x, _bar_y = bottom_mesh_bar_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=no_hook, bar_y_hooks=no_hook)

    assert len(bar_x.points) == 2
    half_z = lengths.z_mm / 2.0
    elevation = 50.0 + 16.0 / 2.0
    assert bar_x.points[0] == pytest.approx(
        (-half_z, 0.0, elevation), rel=1e-9)
    assert bar_x.points[1] == pytest.approx(
        (half_z, 0.0, elevation), rel=1e-9)


def test_both_ends_hooked_is_a_four_point_u_shape_rising_by_n():
    lengths = _lengths()
    both_hooked = BarHookPlan(
        start=BarEndHook(ld_mm=640.0, needs_hook=True),
        end=BarEndHook(ld_mm=640.0, needs_hook=True), shape=SHAPE_U)
    bar_x, _bar_y = bottom_mesh_bar_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=both_hooked, bar_y_hooks=both_hooked)

    half_z = lengths.z_mm / 2.0
    elevation = 50.0 + 16.0 / 2.0
    points = bar_x.points
    assert len(points) == 4
    # leg up, straight run, leg up -- Sec 3 Story 1's "a U in elevation".
    assert points[0] == pytest.approx(
        (-half_z, 0.0, elevation + lengths.n_mm), rel=1e-9)
    assert points[1] == pytest.approx((-half_z, 0.0, elevation), rel=1e-9)
    assert points[2] == pytest.approx((half_z, 0.0, elevation), rel=1e-9)
    assert points[3] == pytest.approx(
        (half_z, 0.0, elevation + lengths.n_mm), rel=1e-9)


def test_only_the_start_end_hooked_is_a_three_point_l_shape():
    lengths = _lengths()
    l_shape = BarHookPlan(
        start=BarEndHook(ld_mm=640.0, needs_hook=True),
        end=BarEndHook(ld_mm=640.0, needs_hook=False), shape=SHAPE_L)
    straight_y = BarHookPlan(
        start=BarEndHook(ld_mm=480.0, needs_hook=False),
        end=BarEndHook(ld_mm=480.0, needs_hook=False), shape=SHAPE_L)
    bar_x, _bar_y = bottom_mesh_bar_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=l_shape, bar_y_hooks=straight_y)

    half_z = lengths.z_mm / 2.0
    elevation = 50.0 + 16.0 / 2.0
    points = bar_x.points
    assert len(points) == 3
    assert points[0] == pytest.approx(
        (-half_z, 0.0, elevation + lengths.n_mm), rel=1e-9)
    assert points[1] == pytest.approx((-half_z, 0.0, elevation), rel=1e-9)
    assert points[2] == pytest.approx((half_z, 0.0, elevation), rel=1e-9)


def test_only_the_end_end_hooked_puts_the_leg_last_not_first():
    lengths = _lengths()
    l_shape = BarHookPlan(
        start=BarEndHook(ld_mm=640.0, needs_hook=False),
        end=BarEndHook(ld_mm=640.0, needs_hook=True), shape=SHAPE_L)
    bar_x, _bar_y = bottom_mesh_bar_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=l_shape, bar_y_hooks=l_shape)

    half_z = lengths.z_mm / 2.0
    elevation = 50.0 + 16.0 / 2.0
    points = bar_x.points
    assert len(points) == 3
    assert points[0] == pytest.approx((-half_z, 0.0, elevation), rel=1e-9)
    assert points[1] == pytest.approx((half_z, 0.0, elevation), rel=1e-9)
    assert points[2] == pytest.approx(
        (half_z, 0.0, elevation + lengths.n_mm), rel=1e-9)


def test_bar_y_uses_z2_and_n2_not_bar_x_own_z_and_n():
    """mesh_bar_y must use ITS OWN Z2/N2 (Sec 3), never bar_x's Z/N --
    the same swap risk R6/#222 style rulings exist to catch, checked here
    by hand since bar_x and bar_y in this fixture differ on both."""
    lengths = _lengths()
    both_hooked = BarHookPlan(
        start=BarEndHook(ld_mm=480.0, needs_hook=True),
        end=BarEndHook(ld_mm=480.0, needs_hook=True), shape=SHAPE_U)
    _bar_x, bar_y = bottom_mesh_bar_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=both_hooked, bar_y_hooks=both_hooked)

    half_z2 = lengths.z2_mm / 2.0
    elevation_y = 50.0 + 16.0 + 12.0 / 2.0
    points = bar_y.points
    assert len(points) == 4
    assert lengths.z2_mm != lengths.z_mm
    assert lengths.n2_mm != lengths.n_mm
    assert points[0] == pytest.approx(
        (0.0, -half_z2, elevation_y + lengths.n2_mm), rel=1e-9)
    assert points[1] == pytest.approx((0.0, -half_z2, elevation_y), rel=1e-9)
    assert points[2] == pytest.approx((0.0, half_z2, elevation_y), rel=1e-9)
    assert points[3] == pytest.approx(
        (0.0, half_z2, elevation_y + lengths.n2_mm), rel=1e-9)


# --------------------------------------------------------------------------
# #232 (R11, docs/footing/spec-amendments.md) -- the bottom-mesh bar ARRAY:
# direct spacing input per direction, count derived. Genuinely new math, so
# these assert hand-computed numbers (Essam's velocity rule 3), same
# discipline as this file's own #198 tests above.
# --------------------------------------------------------------------------


def test_mesh_bar_offsets_mm_evenly_fills_a_width_with_a_remainder():
    # width=1100 (Z2), spacing=200 -> n_spaces = ceil(1100/200) = ceil(5.5)
    # = 6; achieved_spacing = 1100/6 = 183.3333...; 7 offsets total
    # (n_spaces + 1), first/last exactly at the width's own two edges.
    offsets = mesh_bar_offsets_mm(width_mm=1100.0, spacing_mm=200.0)
    assert len(offsets) == 7
    assert offsets[0] == pytest.approx(-550.0)
    assert offsets[-1] == pytest.approx(550.0)
    achieved = 1100.0 / 6.0
    for index, offset in enumerate(offsets):
        assert offset == pytest.approx(-550.0 + index * achieved)


def test_mesh_bar_offsets_mm_exact_division_has_no_remainder():
    # width=1000, spacing=250 -> n_spaces = ceil(1000/250) = 4 exactly;
    # achieved_spacing stays 250.0 (no redistribution needed); 5 offsets.
    offsets = mesh_bar_offsets_mm(width_mm=1000.0, spacing_mm=250.0)
    assert offsets == pytest.approx([-500.0, -250.0, 0.0, 250.0, 500.0])


def test_mesh_bar_offsets_mm_a_width_narrower_than_spacing_still_gets_two_bars():
    # width=100, spacing=200 -> n_spaces = max(1, ceil(100/200)) = 1;
    # achieved_spacing = 100.0; exactly two bars, one at each edge.
    offsets = mesh_bar_offsets_mm(width_mm=100.0, spacing_mm=200.0)
    assert offsets == pytest.approx([-50.0, 50.0])


def test_mesh_bar_offsets_mm_refuses_a_non_positive_width():
    with pytest.raises(ValueError):
        mesh_bar_offsets_mm(width_mm=0.0, spacing_mm=200.0)


def test_mesh_bar_offsets_mm_refuses_a_non_positive_spacing():
    with pytest.raises(ValueError):
        mesh_bar_offsets_mm(width_mm=1100.0, spacing_mm=0.0)


def _straight_hooks(ld_mm):
    return BarHookPlan(
        start=BarEndHook(ld_mm=ld_mm, needs_hook=False),
        end=BarEndHook(ld_mm=ld_mm, needs_hook=False), shape=SHAPE_L)


def test_bottom_mesh_bar_array_geometry_returns_none_per_direction_when_no_spacing_given():
    lengths = _lengths()
    hooks = _straight_hooks(640.0)
    bar_x_array, bar_y_array = bottom_mesh_bar_array_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=hooks, bar_y_hooks=hooks,
        bar_x_spacing_mm=None, bar_y_spacing_mm=None)
    assert bar_x_array is None
    assert bar_y_array is None


def test_bottom_mesh_bar_array_geometry_builds_only_the_direction_given_spacing():
    lengths = _lengths()
    hooks = _straight_hooks(640.0)
    bar_x_array, bar_y_array = bottom_mesh_bar_array_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=hooks, bar_y_hooks=hooks,
        bar_x_spacing_mm=200.0, bar_y_spacing_mm=None)
    assert bar_x_array is not None
    assert bar_y_array is None
    # Z2 = 1100mm at 200mm spacing -> 7 bars (same hand-computed count as
    # test_mesh_bar_offsets_mm_evenly_fills_a_width_with_a_remainder).
    assert len(bar_x_array) == 7


def test_bottom_mesh_bar_array_spaces_bar_x_along_y_across_z2_not_z():
    """R11's own reading of local_mesh_bar_endpoints' axis convention:
    mesh_bar_x bars run along local X and are spaced along Y across
    Z2/b's own extent -- checked by hand against Z2=1100mm, NOT Z=1700mm
    (the swap this ruling explicitly warns against)."""
    lengths = _lengths()
    hooks = _straight_hooks(640.0)
    bar_x_array, _ = bottom_mesh_bar_array_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=hooks, bar_y_hooks=hooks,
        bar_x_spacing_mm=200.0, bar_y_spacing_mm=None)

    y_offsets = [bar.points[0].y_mm for bar in bar_x_array]
    assert y_offsets[0] == pytest.approx(-lengths.z2_mm / 2.0)
    assert y_offsets[-1] == pytest.approx(lengths.z2_mm / 2.0)
    # Every bar's own X extent is unchanged (still spans Z, centred at 0),
    # only Y (the offset) differs bar to bar.
    for bar in bar_x_array:
        xs = [point.x_mm for point in bar.points]
        assert min(xs) == pytest.approx(-lengths.z_mm / 2.0)
        assert max(xs) == pytest.approx(lengths.z_mm / 2.0)


def test_bottom_mesh_bar_array_spaces_bar_y_along_x_across_z_not_z2():
    """The mirrored half of R11's axis convention: mesh_bar_y bars run
    along local Y and are spaced along X across Z/a's own extent."""
    lengths = _lengths()
    hooks = _straight_hooks(480.0)
    _, bar_y_array = bottom_mesh_bar_array_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=hooks, bar_y_hooks=hooks,
        bar_x_spacing_mm=None, bar_y_spacing_mm=200.0)

    x_offsets = [bar.points[0].x_mm for bar in bar_y_array]
    assert x_offsets[0] == pytest.approx(-lengths.z_mm / 2.0)
    assert x_offsets[-1] == pytest.approx(lengths.z_mm / 2.0)
    for bar in bar_y_array:
        ys = [point.y_mm for point in bar.points]
        assert min(ys) == pytest.approx(-lengths.z2_mm / 2.0)
        assert max(ys) == pytest.approx(lengths.z2_mm / 2.0)


def test_bottom_mesh_bar_array_every_bar_shares_the_identical_hook_shape():
    """This ticket's own scope: every bar in the array reuses the SAME
    per-bar hook decision (no per-bar-index L-alternating over a real
    array -- that is separate, unbuilt scope), so every bar's own point
    COUNT (2 for straight, 3/4 for hooked) must be identical."""
    lengths = _lengths()
    both_hooked = BarHookPlan(
        start=BarEndHook(ld_mm=640.0, needs_hook=True),
        end=BarEndHook(ld_mm=640.0, needs_hook=True), shape=SHAPE_U)
    bar_x_array, _ = bottom_mesh_bar_array_geometry(
        lengths, bottom_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, bar_x_hooks=both_hooked,
        bar_y_hooks=both_hooked, bar_x_spacing_mm=200.0,
        bar_y_spacing_mm=None)

    assert len(bar_x_array) == 7
    for bar in bar_x_array:
        assert len(bar.points) == 4
