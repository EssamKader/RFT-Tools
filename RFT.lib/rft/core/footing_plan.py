# -*- coding: utf-8 -*-
"""The single composing object a future report/preview AND the placer both
read the bottom-mesh geometry from.

Spec Ref: specs/isolated-footing.md Sec 4 ("Data flow"). Built now, per
docs/token-efficient-expansion.md Sec 7, BEFORE a second consumer exists --
this ticket's own placement code is the FIRST consumer and reads the plan
from here rather than calling ``rft.core.footing_mesh`` directly, so a
later report ticket has one place to read from instead of two independently
diverging call sites (the beam tool's ``ZONE_LAYOUT_FLAGS`` drift bug).
"""

from collections import namedtuple

from .footing_mesh import (
    bar_hook_plan_for_mat,
    local_mesh_bar_endpoints,
    mesh_bar_lengths,
    primary_reinforcement_direction,
)

#: Every straight-case input this ticket's geometry needs. ``x_offset_mm``/
#: ``y_offset_mm`` are the column-face clear offsets (Sec 2/3's `X`/`Y`),
#: supplied directly rather than derived from `a`/`b`/`Cw` here -- deriving
#: them would need a column footprint dimension the spec's Sec 2/3 naming
#: table never names for the b-direction, which is a gap outside this
#: ticket's formulas, not something to fill by guessing a symbol.
#: ``ld_multiplier`` is Sec 5's ``LD = multiplier * db`` multiplier -- a
#: single user input/code-table value shared by both directions, per
#: Sec 5's own wording ("the multiplier is a user input or code-table
#: lookup"), not a separate value per direction.
#: ``bottom_mat_shape_mode`` is Sec 3 (Story 3) / Sec 6's direct, per-mat
#: user override (``None``, ``footing_mesh.MAT_SHAPE_U`` or
#: ``footing_mesh.MAT_SHAPE_L_ALTERNATING``) -- ``None`` (the default, so
#: every existing caller that predates #200 keeps #199's behaviour
#: unchanged) means no override was given and Story 2's own per-end LD
#: comparison still decides. There is no ``top_mat_shape_mode`` yet
#: because the top mat itself (Story 4 / Sec 7) is not built yet --
#: IsolatedFooting.extension/CONTEXT.md "Not yet in".
FootingInputs = namedtuple(
    "FootingInputs",
    ["a_mm", "b_mm", "cover_mm", "footing_thickness_mm",
     "bottom_cover_mm", "top_cover_mm",
     "mesh_bar_x_dia_mm", "mesh_bar_y_dia_mm",
     "x_offset_mm", "y_offset_mm", "ld_multiplier",
     "bottom_mat_shape_mode"],
)
#: Python 2/3-compatible way to give a namedtuple field a default without
#: breaking every existing positional/keyword call site that predates
#: #200 (this repo's IronPython 2.7 target rules out dataclasses'
#: `field(default=...)`). Only the last field gets a default.
FootingInputs.__new__.__defaults__ = (None,)

#: ``lengths`` is a ``footing_mesh.MeshBarLengths``; ``primary_direction``
#: is ``footing_mesh.DIRECTION_X``/``DIRECTION_Y``; ``bar_x_endpoints``/
#: ``bar_y_endpoints`` are ``footing_mesh.BarEndpoints`` (footing-local mm);
#: ``bar_x_hooks``/``bar_y_hooks`` are ``footing_mesh.BarHookPlan`` (#199,
#: Sec 3 Story 2 / Sec 5; #200's per-mat U/L-alternating override, Sec 3
#: Story 3 / Sec 6, is applied before this plan is built -- see
#: ``FootingInputs.bottom_mat_shape_mode``).
BottomMeshPlan = namedtuple(
    "BottomMeshPlan",
    ["lengths", "primary_direction", "bar_x_endpoints", "bar_y_endpoints",
     "bar_x_hooks", "bar_y_hooks"],
)

FootingPlan = namedtuple("FootingPlan", ["inputs", "bottom_mesh"])


def build_footing_plan(inputs):
    """The ONE place ``mesh_bar_lengths``, ``primary_reinforcement_
    direction`` and ``local_mesh_bar_endpoints`` are called from.

    Spec Ref: Sec 4. Both a future report/preview and the placer must call
    THIS function and read the ``FootingPlan`` it returns, never the three
    ``footing_mesh`` functions above independently -- that is the single
    composing module docs/token-efficient-expansion.md Sec 7 requires.
    """
    lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    direction = primary_reinforcement_direction(
        inputs.x_offset_mm, inputs.y_offset_mm)
    bar_x_endpoints, bar_y_endpoints = local_mesh_bar_endpoints(
        lengths, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
        inputs.mesh_bar_y_dia_mm)
    # Spec Ref: Sec 2/3 -- a = 2*X + Cw is symmetric, so both ends of
    # mesh_bar_x share the same X offset (and both ends of mesh_bar_y the
    # same Y offset); bar_hook_plan_for_mat itself takes independent
    # start/end offsets for a future non-symmetric footing (Sec 0 F4).
    #
    # bar_index=0: #198/#199 place only ONE representative bar per
    # direction (full mesh count/spacing is a later ticket -- CONTEXT.md
    # "Not yet in"), so mesh_bar_x and mesh_bar_y are each that
    # direction's own bar 0. Sec 6's "consecutive bars alternate" only
    # produces a visible pattern once a real array of parallel bars
    # exists per direction; that wiring belongs to whichever ticket adds
    # the array, not this one.
    bar_x_hooks = bar_hook_plan_for_mat(
        0, inputs.bottom_mat_shape_mode,
        inputs.x_offset_mm, inputs.x_offset_mm, inputs.mesh_bar_x_dia_mm,
        inputs.ld_multiplier)
    bar_y_hooks = bar_hook_plan_for_mat(
        0, inputs.bottom_mat_shape_mode,
        inputs.y_offset_mm, inputs.y_offset_mm, inputs.mesh_bar_y_dia_mm,
        inputs.ld_multiplier)
    bottom_mesh = BottomMeshPlan(
        lengths=lengths, primary_direction=direction,
        bar_x_endpoints=bar_x_endpoints, bar_y_endpoints=bar_y_endpoints,
        bar_x_hooks=bar_x_hooks, bar_y_hooks=bar_y_hooks)
    return FootingPlan(inputs=inputs, bottom_mesh=bottom_mesh)
