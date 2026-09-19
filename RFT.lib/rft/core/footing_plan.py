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
FootingInputs = namedtuple(
    "FootingInputs",
    ["a_mm", "b_mm", "cover_mm", "footing_thickness_mm",
     "bottom_cover_mm", "top_cover_mm",
     "mesh_bar_x_dia_mm", "mesh_bar_y_dia_mm",
     "x_offset_mm", "y_offset_mm"],
)

#: ``lengths`` is a ``footing_mesh.MeshBarLengths``; ``primary_direction``
#: is ``footing_mesh.DIRECTION_X``/``DIRECTION_Y``; ``bar_x_endpoints``/
#: ``bar_y_endpoints`` are ``footing_mesh.BarEndpoints`` (footing-local mm).
BottomMeshPlan = namedtuple(
    "BottomMeshPlan",
    ["lengths", "primary_direction", "bar_x_endpoints", "bar_y_endpoints"],
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
    bottom_mesh = BottomMeshPlan(
        lengths=lengths, primary_direction=direction,
        bar_x_endpoints=bar_x_endpoints, bar_y_endpoints=bar_y_endpoints)
    return FootingPlan(inputs=inputs, bottom_mesh=bottom_mesh)
