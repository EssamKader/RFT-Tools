# -*- coding: utf-8 -*-
"""The column's live sketch (issue #90) — cross-section, and a zone strip.

PURE. Emits shapes in MILLIMETRES in the section-local frame; scaling to a
canvas is the window's job, which is what keeps every line of this file
testable under plain CPython.

Per A48, applied to a second element: the renderer does **no arithmetic of
its own**. It walks a list of shapes and maps a style key to a brush. Every
position here comes from ``rft.core.column_layout`` and
``rft.core.column_tie_levels`` -- the same modules the report reads and the
placer will build from -- so the three agree by construction rather than by
review.

``rft.ui.sketch`` is NOT reused: the reuse audit marks it do-not-reuse for
its beam sections, faces, zones and hook details. What IS shared is the
shape vocabulary (``rft.ui.sketch_shapes``) and the pixel-space label
placement in ``rft.ui.sketch_layout``, both of which carry no element
knowledge.

## What this draws, and what it honestly cannot

Drawn: the concrete outline, the cover band, the outer tie, every
longitudinal bar, section 6.1's clear distances coloured by tier, and a
vertical strip showing the two `L0` zones and the middle run.

**Not drawn: inner ties and cross-ties.** Which bars each closed loop
wraps is section 6.2's topology -- issue #89, blocked on Q11 -- and R4
settled that the USER selects it and section 6.1 validates, precisely
because section 6.1 admits many valid coverings and the spec has no
tie-break rule. Drawing a guessed topology would put a picture of one
arbitrary choice in front of an engineer about to press Place. The sketch
says so instead.

## R15: these positions are IDEALISED, and the sketch says so

A corner bar does not stay where the arithmetic puts it. A tie corner is a
20 mm bend arc and a bar cannot occupy the intersection of two straight
legs, so Revit nestles it inboard -- `-167.55` asked for, `-164.02`
measured. #80 explicitly did **not** derive the closed form and concluded
"the tool must read the value back rather than predict it", so this module
does not apply a correction it cannot justify. It draws the computed
position and LABELS the corner bars as ones that will move.
"""

from ..core.column_layout import (
    TIER_ALTERNATE, TIER_EVERY_BAR, TIER_EXCEEDED,
)
from ..core.column_tie_levels import ZONE_MIDDLE
from .sketch_shapes import SketchCircle, SketchLine, SketchPolygon, SketchText

#: The closed set of style keys this module emits. Every one needs a brush
#: in ``rft.ui.column_sketch_palette``, and that brush must exist in
#: ``RFT.lib/SharedStyles.xaml`` -- guarded both ways, so a new key added
#: here without a brush fails loudly instead of drawing invisible black on
#: white on a live host that nothing here can execute to notice.
STYLE_KEYS = frozenset([
    "concrete",         # the column outline
    "cover",            # the cover band, read from the element (A2)
    "tie_outer",        # the outer tie centreline rectangle
    "tie_inner",        # an inner tie -- reserved for #89, not yet emitted
    "cross_tie",        # a single-leg cross-tie -- reserved for #89 (A1)
    "bar_main",         # a longitudinal bar
    "bar_corner",       # a corner bar, which R15 says will move
    "dimension",        # a neutral dimension or label
    "dimension_pass",   # a section 6.1 clear distance inside a tier
    "dimension_fail",   # a clear distance no tier covers
    "zone_dense",       # an L0 confinement band
    "zone_normal",      # the middle-zone band
    "caption",          # explanatory text, no compliance meaning
])

#: A corner bar's measured inboard snap, for the caption only. NEVER
#: applied to a coordinate: it was measured once, on one tie bend
#: diameter, and #80 did not derive the closed form.
MEASURED_CORNER_SNAP_MM = 3.53


def _rect(half_u, half_v, style):
    return SketchPolygon(points=[(-half_u, -half_v), (half_u, -half_v),
                                 (half_u, half_v), (-half_u, half_v)],
                         style=style)


def _tier_style(tier):
    return "dimension_fail" if tier == TIER_EXCEEDED else "dimension_pass"


def cross_section_shapes(b_mm, h_mm, cover_mm, tie_dia_mm, bar_dia_mm,
                         layout):
    """The cross-section: concrete, cover, outer tie, bars, section 6.1
    clear distances.

    ``layout`` is a ``PerimeterLayout``. Nothing is recomputed from it --
    positions, gaps and tiers all arrive decided.
    """
    shapes = [
        _rect(b_mm / 2.0, h_mm / 2.0, "concrete"),
        _rect(b_mm / 2.0 - cover_mm, h_mm / 2.0 - cover_mm, "cover"),
        _rect(layout.tie_half_u_mm, layout.tie_half_v_mm, "tie_outer"),
    ]

    radius = bar_dia_mm / 2.0
    for bar in layout.bars:
        shapes.append(SketchCircle(
            u=bar.u_mm, v=bar.v_mm, r=radius,
            style="bar_corner" if bar.is_corner else "bar_main"))

    # Section 6.1's clear distances, drawn ON the gap they measure so a
    # violation is where the eye already is -- not in a legend.
    for gap in layout.gaps:
        a = layout.bars[gap.from_index]
        b = layout.bars[gap.to_index]
        style = _tier_style(gap.tier)
        shapes.append(SketchLine(u1=a.u_mm, v1=a.v_mm, u2=b.u_mm, v2=b.v_mm,
                                 style=style))
        shapes.append(SketchText(u=(a.u_mm + b.u_mm) / 2.0,
                                 v=(a.v_mm + b.v_mm) / 2.0,
                                 text="%.0f" % gap.clear_mm, style=style))

    shapes.append(SketchText(
        u=0.0, v=0.0,
        text="cover %.0f (from element)" % cover_mm, style="caption"))
    return shapes


def cross_section_captions(layout, tier_sentence):
    """The words under the cross-section.

    Separate from the shapes because they are prose, not geometry, and
    because the two "we are not claiming this" lines must be impossible to
    drop by editing a drawing loop.
    """
    return [
        tier_sentence,
        "Corner bars are drawn at their COMPUTED positions. Each one will "
        "move roughly %.1f mm inboard once a tie exists, because it binds "
        "to the tie's bend (R15, measured). The exact landing cannot be "
        "predicted and must be read back after placement."
        % MEASURED_CORNER_SNAP_MM,
        "Inner ties and cross-ties are NOT drawn. Which bars each closed "
        "loop wraps is section 6.2's topology -- issue #89, blocked on "
        "Q11 -- and R4 settled that the user selects it. A guessed "
        "topology drawn here would be one arbitrary covering of many.",
    ]


def zone_strip_shapes(clear_height_mm, l0_mm, ladder, strip_width_mm=120.0):
    """The vertical strip: the two `L0` bands, the middle band, and a tick
    at every tie level.

    Drawn in its own frame -- `v` is height above the base support face,
    `u` spans the strip's width -- because it shares no scale with the
    cross-section and overlaying them would misrepresent both.
    """
    half = strip_width_mm / 2.0
    shapes = [
        SketchPolygon(points=[(-half, 0.0), (half, 0.0),
                              (half, clear_height_mm), (-half, clear_height_mm)],
                      style="concrete"),
        SketchPolygon(points=[(-half, 0.0), (half, 0.0),
                              (half, l0_mm), (-half, l0_mm)],
                      style="zone_dense"),
        SketchPolygon(points=[(-half, clear_height_mm - l0_mm),
                              (half, clear_height_mm - l0_mm),
                              (half, clear_height_mm),
                              (-half, clear_height_mm)],
                      style="zone_dense"),
        SketchPolygon(points=[(-half, l0_mm), (half, l0_mm),
                              (half, clear_height_mm - l0_mm),
                              (-half, clear_height_mm - l0_mm)],
                      style="zone_normal"),
    ]
    for level in ladder.levels:
        shapes.append(SketchLine(u1=-half, v1=level.z_mm,
                                 u2=half, v2=level.z_mm, style="tie_outer"))
    first = ladder.levels[0]
    shapes.append(SketchText(u=half, v=first.z_mm,
                             text="first tie %.0f" % first.z_mm,
                             style="dimension"))
    shapes.append(SketchText(u=half, v=l0_mm, text="L0 %.0f" % l0_mm,
                             style="dimension"))
    middle = [lv for lv in ladder.levels if lv.zone == ZONE_MIDDLE]
    if middle:
        shapes.append(SketchText(
            u=half, v=middle[len(middle) // 2].z_mm,
            text="middle @ %.0f" % ladder.middle_spacing_mm,
            style="dimension"))
    return shapes


def all_style_keys_used(shapes):
    """Every style key a shape list actually carries.

    Used by the guard that checks the emitted keys against the palette --
    the reverse direction from ``STYLE_KEYS``, which is what the module
    DECLARES. A key declared but never emitted is harmless; a key emitted
    but never declared draws in WPF's invisible default.
    """
    return set(shape.style for shape in shapes)
