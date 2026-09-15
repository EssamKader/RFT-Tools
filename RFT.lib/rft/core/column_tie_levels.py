# -*- coding: utf-8 -*-
"""Where the ties actually sit, and which ones are mirrored (issue #91).

PURE. Millimetres from the base support face, upward.

The report has to list the tie levels, and the placer will have to build
them. Computing them twice is how the two disagree, so they are computed
once -- the same reason ``rft.core.column_spacing`` holds one spacing plan
for both. This module consumes that plan and produces the ladder.

## The ladder, from the spec

- Section 4: the first tie sits at an **exact 50 mm** from the face of the
  support, at each end. That is a placement, not a maximum.
- Section 3/4: within `L0` of each support face, ties step at `S0`.
- Section 5: between the two confinement zones, spacing must not exceed
  `2 x S0`. The middle run is divided into EQUAL intervals at or under
  that cap rather than stepped from one end and left with a short last
  bay -- a ragged final spacing is a site query every time, and equal
  division satisfies the same maximum.
- Section 6.3: the hook corner must move between consecutive levels, so
  alternate levels carry a mirror. #70 proved this is ONE rebar set plus
  a per-bar transform, never a set per level -- so what this module emits
  is a level-indexed mirror MAP, not a list of distinct tie shapes.

The top zone is generated downward from the top face, so its 50 mm tie is
50 mm from the top support and not wherever a bottom-up run happened to
land. Both ends are anchored; the middle absorbs the remainder.
"""

import math
from collections import namedtuple

ZONE_CONFINEMENT_BOTTOM = "confinement (bottom)"
ZONE_MIDDLE = "middle"
ZONE_CONFINEMENT_TOP = "confinement (top)"

#: A level and everything the report and the placer need to say about it.
#: ``mirrored`` is section 6.3's alternation; ``index`` is the bar position
#: index the transform will be applied at, which is why it is stored
#: rather than recomputed -- #70 found that a layout change does NOT
#: remap those indices and silently scrambles the alternation.
TieLevel = namedtuple("TieLevel", "index z_mm zone mirrored")

TieLadder = namedtuple(
    "TieLadder",
    "levels bottom_count middle_count top_count middle_spacing_mm")

#: Floating-point slack for "is this level still inside the zone". Levels
#: are tens of millimetres apart, so a micron of tolerance separates a
#: rounding artefact from a real step with no risk of merging two ties.
EPSILON_MM = 1.0e-6


def tie_levels(clear_height_mm, l0_mm, confinement_spacing_mm,
               middle_zone_spacing_mm, first_tie_offset_mm):
    """The full ladder, base face upward.

    ``confinement_spacing_mm`` and ``middle_zone_spacing_mm`` are what will
    be BUILT -- ``SpacingPlan.confinement_spacing_mm`` and
    ``.middle_zone_spacing_mm`` -- not the code limits. In Mode B those
    differ, and the ladder must describe the model rather than the code,
    or the report lists ties at positions nothing will occupy.

    Raises ``ValueError`` when the two confinement zones would meet or
    overlap: a column shorter than twice `L0` has no middle zone, and
    silently producing an empty one would hide that the whole column is a
    confinement region.
    """
    for name, value in (("clear height", clear_height_mm),
                        ("L0", l0_mm),
                        ("confinement spacing", confinement_spacing_mm),
                        ("middle-zone spacing", middle_zone_spacing_mm),
                        ("first tie offset", first_tie_offset_mm)):
        if value is None or value <= 0:
            raise ValueError(
                "%s must be positive to lay out ties -- got %r." % (name, value))

    if 2.0 * l0_mm >= clear_height_mm:
        raise ValueError(
            "This column's two confinement zones (2 x %.0f mm) meet or "
            "overlap within its clear height of %.0f mm, so there is no "
            "middle zone. The whole column is a confinement region, which "
            "this layout does not describe -- it needs a ruling, not a "
            "silently empty middle run."
            % (l0_mm, clear_height_mm))

    bottom = []
    z = first_tie_offset_mm
    while z <= l0_mm + EPSILON_MM:
        bottom.append(z)
        z += confinement_spacing_mm

    top = []
    z = clear_height_mm - first_tie_offset_mm
    while z >= clear_height_mm - l0_mm - EPSILON_MM:
        top.append(z)
        z -= confinement_spacing_mm

    if not bottom or not top:
        raise ValueError(
            "The first tie at %.0f mm falls outside the %.0f mm "
            "confinement zone, so no confinement tie can be placed."
            % (first_tie_offset_mm, l0_mm))

    # Equal division of what is left, at or under the middle-zone spacing.
    span_lo, span_hi = bottom[-1], top[-1]
    span = span_hi - span_lo
    interval_count = int(math.ceil(span / middle_zone_spacing_mm - EPSILON_MM))
    interval_count = max(1, interval_count)
    middle_step = span / interval_count
    middle = [span_lo + middle_step * i for i in range(1, interval_count)]

    ordered = ([(z, ZONE_CONFINEMENT_BOTTOM) for z in bottom]
               + [(z, ZONE_MIDDLE) for z in middle]
               + [(z, ZONE_CONFINEMENT_TOP) for z in reversed(top)])

    levels = [TieLevel(index=i, z_mm=z, zone=zone, mirrored=bool(i % 2))
              for i, (z, zone) in enumerate(ordered)]

    return TieLadder(
        levels=levels,
        bottom_count=len(bottom),
        middle_count=len(middle),
        top_count=len(top),
        middle_spacing_mm=middle_step,
    )


def mirror_map(ladder):
    """``{bar position index: True}`` for every level section 6.3 mirrors.

    Emitted as a map keyed by INDEX rather than as a list of mirrored
    positions, because that is the shape ``Rebar.MoveBarInSet`` needs --
    and because #70 found a layout change does not remap those indices.
    The whole map must be reset and re-applied after any layout change;
    keeping it addressable by index is what makes that possible.
    """
    return dict((level.index, True) for level in ladder.levels
                if level.mirrored)
