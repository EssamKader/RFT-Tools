# -*- coding: utf-8 -*-
"""Issue #167 -- R42's nearest-crossing geometry, PURE.

No Revit import. Millimetres and plain ``(x, y)`` tuples in, a millimetre
distance (or ``None``) out. The adapter (``rft.revit.column_roof_slab``)
turns a Floor's top face into a flat list of 2D edge segments and a probe
origin/direction along the column's own Hand or Facing axis (R42: "never
world X/Y") and hands both to :func:`nearest_crossing_mm`.

R42: "the nearest crossing of a probe line from the column's own face" --
across every boundary loop, because a stair void beside a column should
count as an edge (untested, a reading of the code rather than a
measurement -- see the R42 verification note). Loops are therefore not
kept distinct here; every edge segment from every loop is one flat list,
and "nearest across all of them" falls out of taking the minimum.
"""

import math


def _segment_crossing(origin, direction, p0, p1):
    """The distance along ``direction`` from ``origin`` to where the ray
    crosses segment ``p0``-``p1``, or ``None`` if it does not.

    Standard ray/segment intersection: solve
    ``origin + t*direction == p0 + s*(p1 - p0)`` for ``t`` and ``s``, and
    accept only ``t > 0`` (ahead of the probe) and ``0 <= s <= 1`` (within
    the segment, not its infinite extension).
    """
    ox, oy = origin
    dx, dy = direction
    x0, y0 = p0
    x1, y1 = p1
    ex, ey = x1 - x0, y1 - y0
    fx, fy = x0 - ox, y0 - oy

    denom = ex * dy - ey * dx
    if denom == 0.0:
        return None  # parallel (or the same line) -- not a crossing

    t = (ex * fy - ey * fx) / denom
    s = (dx * fy - dy * fx) / denom
    if t <= 0.0 or s < 0.0 or s > 1.0:
        return None
    return t


def nearest_crossing_mm(origin_mm, direction, segments_mm):
    """The nearest boundary crossing along ``direction`` from ``origin_mm``,
    across every segment in ``segments_mm``, or ``None`` if none crosses.

    ``origin_mm`` and each segment endpoint are ``(x, y)`` tuples in
    millimetres. ``direction`` need not be a unit vector -- it is
    normalised here so the returned distance is always in millimetres
    regardless of what the caller passed.
    """
    dx, dy = direction
    length = math.sqrt(dx * dx + dy * dy)
    if length == 0.0:
        raise ValueError(
            "The probe direction is the zero vector; there is no axis to "
            "measure the slab's run along.")
    unit = (dx / length, dy / length)

    nearest = None
    for p0, p1 in segments_mm:
        crossing = _segment_crossing(origin_mm, unit, p0, p1)
        if crossing is None:
            continue
        if nearest is None or crossing < nearest:
            nearest = crossing
    return nearest
