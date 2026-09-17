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

Inner ties and cross-ties ARE drawn, as of #89 -- but only the ones the
engineer stated. R4 settled that the user selects the topology and
section 6.1 validates it, and R17 settled the control: direct subset
entry. Nothing here derives a topology. With no subsets entered the
sketch shows the perimeter tie alone, which is what the column actually
has, and section 6.1's verdict says whether that is enough.

A cross-tie is drawn as a single leg in its own colour, never as a thin
rectangle: A1 makes it a cross-tie precisely because the rectangle cannot
be bent, so drawing one would picture the thing Revit refuses.

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
from ..core.column_ties import KIND_CROSS_TIE, restrained_bar_indices
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
    "tie_inner",        # an inner tie the engineer stated (6.2)
    "cross_tie",        # a single-leg cross-tie, where A1's bend test fails
    "bar_unrestrained", # a bar no tie corner holds -- 6.1's actual subject
    "bar_main",         # a longitudinal bar
    "bar_corner",       # a corner bar, which R15 says will move
    "bar_selected",     # a bar the engineer has clicked, mid-tie (#137)
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
                         layout, ties=()):
    """The cross-section: concrete, cover, every tie, bars, section 6.1
    clear distances.

    ``layout`` is a ``PerimeterLayout`` and ``ties`` a list of
    ``ResolvedTie``. Nothing is recomputed from either -- positions, gaps,
    tiers, rectangles and the loop/cross-tie verdict all arrive decided.
    """
    shapes = [
        _rect(b_mm / 2.0, h_mm / 2.0, "concrete"),
        _rect(b_mm / 2.0 - cover_mm, h_mm / 2.0 - cover_mm, "cover"),
    ]

    # The ties the engineer stated, resolved. The first is always the
    # perimeter; the rest are inner. Drawn BEFORE the bars so a bar is
    # never hidden under a tie leg.
    if ties:
        for position, tie in enumerate(ties):
            shapes.extend(_tie_shapes(tie, "tie_outer" if position == 0
                                      else "tie_inner"))
    else:
        shapes.append(_rect(layout.tie_half_u_mm, layout.tie_half_v_mm,
                            "tie_outer"))

    restrained = restrained_bar_indices(ties) if ties else None
    radius = bar_dia_mm / 2.0
    for bar in layout.bars:
        if restrained is not None and bar.index not in restrained:
            # Section 6.1's actual subject. A bar no tie corner holds is
            # the thing the rule is about, so it is marked rather than
            # left for the reader to work out from the tie rectangles.
            style = "bar_unrestrained"
        elif bar.is_corner:
            style = "bar_corner"
        else:
            style = "bar_main"
        shapes.append(SketchCircle(u=bar.u_mm, v=bar.v_mm, r=radius,
                                   style=style))

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


def selected_bar_shapes(layout, selection, radius_mm):
    """The highlight ring for every bar the engineer has clicked so far
    (issue #137) -- drawn AFTER the ordinary bars, so a selection is never
    hidden underneath one.

    ``selection`` is the pending list ``rft.ui.column_sketch.
    toggle_bar_selection`` builds; nothing here decides membership, it only
    draws it. ``radius_mm`` is the caller's choice, same reasoning as
    ``bar_at_point``'s ``pick_radius_mm``: this module does not guess a
    size from the section it is given.
    """
    by_index = dict((bar.index, bar) for bar in layout.bars)
    return [SketchCircle(u=by_index[index].u_mm, v=by_index[index].v_mm,
                         r=radius_mm, style="bar_selected")
            for index in selection if index in by_index]


def _tie_shapes(tie, loop_style):
    """One resolved tie: a rectangle, or -- where A1's bend test failed --
    a single leg.

    A cross-tie is NOT drawn as a thin rectangle. A1 makes it a cross-tie
    because the rectangle cannot be bent, so drawing one would picture
    exactly the geometry Revit refuses with a modal dialog.
    """
    if tie.kind == KIND_CROSS_TIE:
        return [SketchLine(
            u1=tie.centre_u_mm - tie.half_u_mm,
            v1=tie.centre_v_mm - tie.half_v_mm,
            u2=tie.centre_u_mm + tie.half_u_mm,
            v2=tie.centre_v_mm + tie.half_v_mm,
            style="cross_tie")]
    return [SketchPolygon(points=[
        (tie.centre_u_mm - tie.half_u_mm, tie.centre_v_mm - tie.half_v_mm),
        (tie.centre_u_mm + tie.half_u_mm, tie.centre_v_mm - tie.half_v_mm),
        (tie.centre_u_mm + tie.half_u_mm, tie.centre_v_mm + tie.half_v_mm),
        (tie.centre_u_mm - tie.half_u_mm, tie.centre_v_mm + tie.half_v_mm),
    ], style=loop_style)]


def cross_section_captions(layout, tier_sentence, ties=()):
    """The words under the cross-section.

    Separate from the shapes because they are prose, not geometry, and
    because the two "we are not claiming this" lines must be impossible to
    drop by editing a drawing loop.
    """
    captions = [
        tier_sentence,
        "Corner bars are drawn at their COMPUTED positions. Each one will "
        "move roughly %.1f mm inboard once a tie exists, because it binds "
        "to the tie's bend (R15, measured). The exact landing cannot be "
        "predicted and must be read back after placement."
        % MEASURED_CORNER_SNAP_MM,
    ]
    if not ties:
        captions.append(
            "No inner ties stated. The perimeter tie alone is drawn, which "
            "is what this column would have -- section 6.1's verdict above "
            "says whether that is enough.")
    else:
        unrestrained = [bar.index for bar in layout.bars
                        if bar.index not in restrained_bar_indices(ties)]
        captions.append(
            "%d tie(s) drawn, exactly as stated -- nothing here derives a "
            "topology (R4, R17). Bars no tie corner holds are marked: %s."
            % (len(ties),
               ", ".join(str(i) for i in unrestrained) if unrestrained
               else "none"))
    return captions


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


def bar_at_point(bars, u_mm, v_mm, pick_radius_mm):
    """The index of the bar nearest ``(u_mm, v_mm)``, or ``None`` if the
    nearest one is further away than ``pick_radius_mm`` (issue #137).

    ``pick_radius_mm`` is the caller's to choose -- the drawn bar radius
    grown enough to be clickable at a small canvas -- so this function
    does not guess a size of its own from the section it is given.

    Compared by SQUARED distance throughout, which keeps a tie decided by
    the same comparison that decided everything else: the nearer centre
    wins, and no square root is needed to know which one that is.
    """
    best_index = None
    best_distance_sq = None
    limit_sq = pick_radius_mm * pick_radius_mm
    for bar in bars:
        distance_sq = (bar.u_mm - u_mm) ** 2 + (bar.v_mm - v_mm) ** 2
        if distance_sq > limit_sq:
            continue
        if best_distance_sq is None or distance_sq < best_distance_sq:
            best_distance_sq = distance_sq
            best_index = bar.index
    return best_index


def toggle_bar_selection(selection, bar_index):
    """One bar added to or removed from a pending tie selection (#137).

    Returns a NEW list; the one passed in is never mutated, which is what
    lets the window compare an old selection to a new one without having
    to have copied it first.

    Click ORDER is kept, not sorted -- R19 makes a two-bar selection a
    cross-tie from the first bar to the second, so which one was clicked
    first is part of what the selection means, not an incidental detail a
    sort would be free to discard.
    """
    if bar_index in selection:
        return [index for index in selection if index != bar_index]
    return list(selection) + [bar_index]


def format_tie_selection(selection):
    """The exact text one ``Add tie`` press writes into the Ties box: the
    selected bar numbers, space-joined, in click order (#137).

    The existing parser (``rft.core.column_ties``) gives this line meaning
    -- this function's only job is producing text indistinguishable from
    what the engineer would have typed by hand.
    """
    return " ".join(str(index) for index in selection)


def all_style_keys_used(shapes):
    """Every style key a shape list actually carries.

    Used by the guard that checks the emitted keys against the palette --
    the reverse direction from ``STYLE_KEYS``, which is what the module
    DECLARES. A key declared but never emitted is harmless; a key emitted
    but never declared draws in WPF's invisible default.
    """
    return set(shape.style for shape in shapes)
