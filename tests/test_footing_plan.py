# -*- coding: utf-8 -*-
"""The composing module, spec Ref: specs/isolated-footing.md Sec 4;
docs/token-efficient-expansion.md Sec 7 ("build the single-source-of-truth
module BEFORE the second consumer exists").
"""

import io
import os

import pytest

from rft.core.footing_mesh import (
    DIRECTION_X,
    SHAPE_L,
    SHAPE_U,
    FootingDirectionTieError,
    bar_hook_plan,
    local_mesh_bar_endpoints,
    mesh_bar_lengths,
)
from rft.core.footing_plan import FootingInputs, build_footing_plan

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOTING_SCRIPT = os.path.join(
    REPO_ROOT, "IsolatedFooting.extension", "RFT-Tools.tab",
    "Footings.panel", "IsolatedFootingRFT.pushbutton", "script.py")


def _inputs(**overrides):
    values = dict(
        a_mm=1800.0, b_mm=1200.0, cover_mm=50.0,
        footing_thickness_mm=450.0, bottom_cover_mm=50.0,
        top_cover_mm=50.0, mesh_bar_x_dia_mm=16.0,
        mesh_bar_y_dia_mm=12.0, x_offset_mm=300.0, y_offset_mm=150.0,
        ld_multiplier=40.0)
    values.update(overrides)
    return FootingInputs(**values)


def test_the_plan_carries_exactly_what_mesh_bar_lengths_would_compute():
    inputs = _inputs()
    plan = build_footing_plan(inputs)

    expected_lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    assert plan.bottom_mesh.lengths == expected_lengths


def test_the_plan_carries_the_primary_direction_from_the_given_offsets():
    plan = build_footing_plan(_inputs(x_offset_mm=300.0, y_offset_mm=150.0))
    assert plan.bottom_mesh.primary_direction == DIRECTION_X


def test_the_plan_raises_the_same_tie_error_the_core_function_does():
    with pytest.raises(FootingDirectionTieError):
        build_footing_plan(_inputs(x_offset_mm=200.0, y_offset_mm=200.0))


def test_the_plan_carries_bar_endpoints_matching_local_mesh_bar_endpoints():
    inputs = _inputs()
    plan = build_footing_plan(inputs)

    lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    expected_bar_x, expected_bar_y = local_mesh_bar_endpoints(
        lengths, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
        inputs.mesh_bar_y_dia_mm)

    assert plan.bottom_mesh.bar_x_endpoints == expected_bar_x
    assert plan.bottom_mesh.bar_y_endpoints == expected_bar_y


def test_the_plan_keeps_the_inputs_it_was_built_from():
    inputs = _inputs()
    plan = build_footing_plan(inputs)
    assert plan.inputs == inputs


def test_the_plan_carries_bar_hooks_matching_bar_hook_plan():
    """#199: the composing module must be the ONE place bar_hook_plan is
    called from, same as the #198 fields above -- so its own output must
    match calling bar_hook_plan directly with the same inputs.
    """
    inputs = _inputs(x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=40.0)
    plan = build_footing_plan(inputs)

    expected_x_hooks = bar_hook_plan(
        inputs.x_offset_mm, inputs.x_offset_mm, inputs.mesh_bar_x_dia_mm,
        inputs.ld_multiplier)
    expected_y_hooks = bar_hook_plan(
        inputs.y_offset_mm, inputs.y_offset_mm, inputs.mesh_bar_y_dia_mm,
        inputs.ld_multiplier)
    assert plan.bottom_mesh.bar_x_hooks == expected_x_hooks
    assert plan.bottom_mesh.bar_y_hooks == expected_y_hooks


def test_the_plan_picks_up_a_u_shape_when_both_directions_still_need_hooks():
    # LD_x = 40*16 = 640 > 300; LD_y = 40*12 = 480 > 150 -> both U.
    plan = build_footing_plan(
        _inputs(x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=40.0))
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_U
    assert plan.bottom_mesh.bar_y_hooks.shape == SHAPE_U


def test_the_plan_switches_only_the_direction_whose_offset_wins_to_l_shape():
    # One shared ld_multiplier (Sec 5), but different db/offset per
    # direction can still split the outcome: LD_x = 15*16 = 240 < 300
    # -> mesh_bar_x switches to L. LD_y = 15*12 = 180 > 150 -> mesh_bar_y
    # stays U.
    plan = build_footing_plan(
        _inputs(x_offset_mm=300.0, y_offset_mm=150.0, ld_multiplier=15.0))
    assert plan.bottom_mesh.bar_x_hooks.shape == SHAPE_L
    assert plan.bottom_mesh.bar_y_hooks.shape == SHAPE_U


def test_the_pushbutton_script_reads_the_composing_plan_not_bare_footing_mesh():
    """docs/token-efficient-expansion.md Sec 7: the placer must call
    ``footing_plan.build_footing_plan``, never ``rft.core.footing_mesh``
    directly -- exactly the beam tool's ``ZONE_LAYOUT_FLAGS`` drift this
    rule exists to rule out one element earlier. Text-checked because
    script.py imports ``pyrevit`` and cannot be imported by this suite;
    proven by mutation in tools/prove_guards.py.
    """
    source = io.open(FOOTING_SCRIPT, encoding="utf-8").read()
    assert "from rft.core.footing_plan import" in source
    assert "build_footing_plan" in source
    assert "from rft.core.footing_mesh import" not in source
    assert "footing_mesh.mesh_bar_lengths" not in source
