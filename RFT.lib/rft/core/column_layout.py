# -*- coding: utf-8 -*-
"""Section 2's perimeter model, and section 6.1's tiered rule (issue #90).

PURE. Millimetres, in the column's own section-local frame: `u` along
`HandOrientation` (the `b` direction), `v` along `FacingOrientation` (the
`h` direction), origin at the section centroid. #69 proved that mapping
by rotating the column 35 degrees and measuring -- both directions are
invariant, the bounding box is not.

## Why this is not ``rft.core.layout``

Section 2 models a column's longitudinal bars as ONE continuous perimeter,
not as independent faces, and rejects force-fitting the beam's
``FacePlan``/``LayerPlan`` model onto four column faces. The reuse audit
splits it function by function:

- ``corner_bar_side_offset_mm`` and ``corner_bar_u_positions_mm`` transfer
  as-is -- "a bar at each corner, the rest at equal spacing between them"
  is exactly one column face -- and are imported here rather than
  re-derived;
- ``layer_offset_mm``, ``main_layer_v_positions_mm`` and the spacer
  functions do NOT: stacked layers and spacer bars are beam constructs.

**The trap the audit names:** ``corner_bar_u_positions_mm`` places a bar
at EACH end of a face. A column's four faces SHARE their corner bars, so
calling it per face and concatenating counts every corner twice -- "exactly
the kind of thing that would pass a unit test per-face and produce eight
corner bars in Revit". :func:`perimeter_bar_positions` de-duplicates.
"""

from collections import namedtuple

from .layout import corner_bar_side_offset_mm, corner_bar_u_positions_mm

#: Section 6.1's tiers, on the horizontal CLEAR distance `x` between
#: consecutive longitudinal bars around the perimeter.
TIER_ALTERNATE = "alternate"      # x <= 150: tie one bar, leave one untied
TIER_EVERY_BAR = "every bar"      # 150 < x <= 250: every bar must be tied
TIER_EXCEEDED = "exceeded"        # x > 250: no tier covers it

TIER_ALTERNATE_MAX_MM = 150.0
TIER_EVERY_BAR_MAX_MM = 250.0

#: Section 6.1's other limit. Left as a named constant rather than
#: evaluated here: it governs the distance between TIE BRANCHES, which is
#: a property of the tie topology -- issue #89, blocked on Q11 -- not of
#: the bar layout this module describes.
MAX_TIE_BRANCH_SPACING_MM = 300.0

#: Face identifiers. The two `b`-faces run along `u`; the two `h`-faces
#: run along `v`.
FACE_BOTTOM = "bottom (b)"
FACE_RIGHT = "right (h)"
FACE_TOP = "top (b)"
FACE_LEFT = "left (h)"

Bar = namedtuple("Bar", "index u_mm v_mm is_corner")

#: One gap between consecutive bars around the perimeter, already judged.
#: ``clear_mm`` is centre-to-centre MINUS one bar diameter -- section 6.1
#: says "clear distance", and using centre-to-centre would overstate every
#: gap by a bar and mis-tier the borderline ones.
Gap = namedtuple("Gap", "from_index to_index clear_mm tier")

PerimeterLayout = namedtuple(
    "PerimeterLayout",
    "bars gaps corner_indices bar_offset_mm tie_half_u_mm tie_half_v_mm")


def bar_centre_offset_mm(cover_mm, tie_dia_mm, bar_dia_mm):
    """Distance from a concrete face to a longitudinal bar's CENTRELINE.

    ``cover + tie + half a bar``. Shared with the beam, which asks the
    same question of the same three numbers -- the reuse audit clears
    ``corner_bar_side_offset_mm`` as-is and this is a named alias so the
    column's callers read in column words.
    """
    return corner_bar_side_offset_mm(cover_mm, tie_dia_mm, bar_dia_mm)


def tie_half_dimensions_mm(b_mm, h_mm, cover_mm, tie_dia_mm):
    """Half-width and half-height of the OUTER tie's CENTRELINE rectangle.

    ``b/2 - cover - tie/2``. For the live 450 x 600 column at cover 40 with
    a 10M tie that is 180.25 x 260.25 -- and 180.25 is the number #80
    measured a tie actually landing at, which is the check that matters.

    (``issue-67-q9-inner-subset-tie.md`` quotes 185.0 for the same column.
    That is ``b/2 - cover``, the tie's OUTER face, not its centreline.
    ``CreateFromCurves`` takes centrelines, so the half-tie term belongs.)
    """
    return (b_mm / 2.0 - cover_mm - tie_dia_mm / 2.0,
            h_mm / 2.0 - cover_mm - tie_dia_mm / 2.0)


def tier_for_clear_distance(clear_mm):
    """Which of section 6.1's tiers a clear distance falls in.

    ``TIER_EXCEEDED`` is not a fourth tier -- it is the absence of one.
    Section 6.1 defines behaviour up to 250 mm and says nothing beyond it,
    so a wider gap is a layout the spec does not cover, and the sketch
    paints it as a failure rather than picking the nearer rule.
    """
    if clear_mm <= TIER_ALTERNATE_MAX_MM:
        return TIER_ALTERNATE
    if clear_mm <= TIER_EVERY_BAR_MAX_MM:
        return TIER_EVERY_BAR
    return TIER_EXCEEDED


def perimeter_bar_positions(b_mm, h_mm, cover_mm, tie_dia_mm, bar_dia_mm,
                            count_b_face, count_h_face):
    """Every longitudinal bar, once, ordered around the perimeter.

    Ordering starts at the bottom-left corner and runs anticlockwise in
    the ``(u, v)`` frame: along the bottom face in ``+u``, up the right
    face in ``+v``, back along the top in ``-u``, down the left in ``-v``.
    The order is not cosmetic -- section 6.1's clear distances are between
    CONSECUTIVE bars around the perimeter, and section 6.2's subsets are
    "an initial bar index and the number of tied bars", so the index IS
    part of the data model.

    ``count_b_face`` and ``count_h_face`` INCLUDE the shared corner bars,
    the convention ``rft.core.column_inputs`` sets and the window states.
    """
    offset = bar_centre_offset_mm(cover_mm, tie_dia_mm, bar_dia_mm)
    half_u = b_mm / 2.0 - offset
    half_v = h_mm / 2.0 - offset

    if half_u <= 0 or half_v <= 0:
        raise ValueError(
            "Cover %.0f plus tie %.0f plus half a %.0f mm bar leaves no room "
            "for a bar inside a %.0f x %.0f section -- the bar centreline "
            "would fall outside the concrete."
            % (cover_mm, tie_dia_mm, bar_dia_mm, b_mm, h_mm))

    us = corner_bar_u_positions_mm(b_mm, cover_mm, tie_dia_mm, bar_dia_mm,
                                   count_b_face)
    vs = corner_bar_u_positions_mm(h_mm, cover_mm, tie_dia_mm, bar_dia_mm,
                                   count_h_face)

    # Each face contributes its bars EXCLUDING its final corner, which is
    # the next face's first. Four faces, four corners, each counted once.
    ordered = []
    ordered += [(u, -half_v) for u in us[:-1]]                  # bottom, +u
    ordered += [(half_u, v) for v in vs[:-1]]                   # right, +v
    ordered += [(u, half_v) for u in reversed(us)][:-1]         # top, -u
    ordered += [(-half_u, v) for v in reversed(vs)][:-1]        # left, -v

    corner_uv = set([(round(su * half_u, 6), round(sv * half_v, 6))
                     for su in (-1, 1) for sv in (-1, 1)])
    bars = []
    for index, (u, v) in enumerate(ordered):
        is_corner = (round(u, 6), round(v, 6)) in corner_uv
        bars.append(Bar(index=index, u_mm=u, v_mm=v, is_corner=is_corner))

    gaps = []
    for position, bar in enumerate(bars):
        nxt = bars[(position + 1) % len(bars)]
        centre_to_centre = ((nxt.u_mm - bar.u_mm) ** 2
                            + (nxt.v_mm - bar.v_mm) ** 2) ** 0.5
        clear = centre_to_centre - bar_dia_mm
        gaps.append(Gap(from_index=bar.index, to_index=nxt.index,
                        clear_mm=clear, tier=tier_for_clear_distance(clear)))

    tie_half_u, tie_half_v = tie_half_dimensions_mm(b_mm, h_mm, cover_mm,
                                                    tie_dia_mm)
    return PerimeterLayout(
        bars=bars,
        gaps=gaps,
        corner_indices=[bar.index for bar in bars if bar.is_corner],
        bar_offset_mm=offset,
        tie_half_u_mm=tie_half_u,
        tie_half_v_mm=tie_half_v,
    )


def worst_gap(layout):
    """The gap that governs -- the widest clear distance around the
    perimeter. ``None`` only if there are no gaps, which cannot happen for
    a closed perimeter but is not worth crashing over.
    """
    if not layout.gaps:
        return None
    return max(layout.gaps, key=lambda gap: gap.clear_mm)


def tier_summary(layout):
    """One sentence for the report and the sketch caption.

    States the governing tier and what it REQUIRES, not just its name: a
    tier label alone tells the engineer nothing about whether alternate
    tying is allowed, which is the entire content of section 6.1.
    """
    gap = worst_gap(layout)
    if gap is None:
        return "No bar gaps to evaluate."
    if gap.tier == TIER_EXCEEDED:
        return ("Widest clear distance %.0f mm EXCEEDS %.0f mm. Section 6.1 "
                "does not cover a gap this wide -- add intermediate bars."
                % (gap.clear_mm, TIER_EVERY_BAR_MAX_MM))
    if gap.tier == TIER_EVERY_BAR:
        return ("Widest clear distance %.0f mm is above %.0f mm, so EVERY "
                "bar must be restrained by a tie corner or an inner tie leg "
                "(section 6.1)." % (gap.clear_mm, TIER_ALTERNATE_MAX_MM))
    return ("Widest clear distance %.0f mm is at or under %.0f mm, so "
            "alternate bars may be left untied (section 6.1)."
            % (gap.clear_mm, TIER_ALTERNATE_MAX_MM))
