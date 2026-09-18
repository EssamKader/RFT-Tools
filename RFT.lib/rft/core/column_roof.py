# -*- coding: utf-8 -*-
"""Issue #160 -- ``specs/column-roof-termination.md`` sections 1 and 2: where
a longitudinal bar ENDS when there is no storey above it.

PURE. No Revit import, no WPF. Millimetres in, millimetres out.

## What this module is for

The main spec's section 9 splices a bar into the storey above. At roof level
there is none, so the bar turns into the roof slab instead: a vertical leg
``a`` up through the slab and a horizontal leg ``b`` bent into it, together
making the development length ``L_D`` (section 1).

Section 2 then asks, **per bar**, whether slab actually continues in the
direction that bar would bend. Where it does, the bend achieves the full
``L_D``. Where it does not -- a free building edge -- the horizontal leg is
capped to what fits inside the column itself, and the bar accepts less than
``L_D``. "Interior / edge / corner column" are descriptions of how many free
edges a column happens to have, **not three code paths** (section 2).

## Why anchorage.py is NOT imported, though it computes the same shape

``rft.core.anchorage`` already splits a development length into ``a`` and
``b`` for the beam tool, with the same 200 mm minimum-bend-leg cap. It is
deliberately not imported here, for two separate reasons:

1. **CONTEXT.md states it outright** -- *"This tool does NOT call or reuse
   `rft.core.anchorage`"* -- and #99 is open precisely because
   ``column_inputs`` already violates that transitively, through
   ``grades -> guards -> anchorage``, while the guard meant to catch it
   walks one file's own imports instead of the resolved graph. Adding a
   second, DIRECT path in would make a live bug worse while its guard kept
   passing. ``column_spacing.py`` set the precedent: written with zero
   imports from ``rft.core.spacing`` for exactly this reason.
2. **The formulas differ where it matters.** The beam's ``a`` comes from a
   support's width; section 1's comes from the roof slab's thickness and
   cover. Sharing the split would mean sharing a constant that means
   something different at each end.

What IS taken from that module is its **discipline**, restated rather than
imported: cap ``a`` so ``b`` can never fall below the minimum bend leg, and
raise rather than let a zero or negative leg reach the Revit API. The beam
tool shipped that bug once (#14 review finding 3) and the same small-``L_D``
input reaches this code.

## R35: the multiplier is stated, never chosen

``L_D = multiplier x bar diameter`` -- *"l_d for roof column can be
calculated as in beam like 60 column bar diameter or 50 or whatever"*. The
multiplication is arithmetic and lives in :func:`development_length_mm`;
**the multiplier is an input**, and this module has no default for it. The
beam module's ``DEFAULT_LD_BTM_MULTIPLIER`` / ``DEFAULT_LD_TOP_MULTIPLIER``
(55 / 60) are the beam spec's numbers for bars in bending and are not
imported, not copied, and not implied.
"""

from collections import namedtuple

#: Section 2.3's minimum bend leg, restated here rather than imported from
#: ``rft.core.anchorage`` (see the module docstring). The value is the same
#: because it is the same physical minimum, not because the modules share
#: code.
MIN_BEND_LEG_MM = 200.0

#: One direction a bar could bend, and what is there. ``available_run_mm``
#: is section 2's free-edge cap for THAT face -- see
#: :func:`free_edge_run_mm`; it is ignored where ``has_slab`` is true,
#: because a bend into slab is not constrained by the column's own width.
RoofBendDirection = namedtuple("RoofBendDirection",
                               "name has_slab available_run_mm")

#: What one bar does at the roof.
#:
#: ``achieved_mm`` is what the bar actually develops and ``shortfall_mm``
#: how far that falls below ``L_D`` -- zero everywhere slab continues. Both
#: are carried rather than left for a caller to subtract, because section 4
#: makes the report name them and a reviewer must not have to recompute a
#: shortfall to notice one.
RoofTermination = namedtuple(
    "RoofTermination",
    "direction a_mm b_mm ld_mm achieved_mm shortfall_mm free_edge")


def development_length_mm(multiplier, bar_diameter_mm):
    """R35: ``L_D = multiplier x bar diameter``.

    The multiplier is the engineer's (60, 50, whatever the job calls for);
    this is only the multiplication. There is deliberately **no default**
    -- a multiplier this module chose would be a detailing decision the
    tool is not allowed to make.
    """
    if multiplier <= 0.0:
        raise ValueError(
            "The LD multiplier must be positive; got %r. R35: the engineer "
            "states it (60 x diameter, 50 x diameter, ...), and the tool "
            "never picks one." % (multiplier,))
    if bar_diameter_mm <= 0.0:
        raise ValueError(
            "The bar diameter must be positive; got %r." % (bar_diameter_mm,))
    return multiplier * bar_diameter_mm


def vertical_leg_mm(slab_thickness_mm, slab_cover_mm):
    """Section 1's ``a``: the vertical run from the slab's bottom face up to
    (thickness - cover).

    Both numbers are **read from the slab** (R37), never typed, so both can
    arrive wrong together: a cover at or above the thickness is a modelling
    error, and it must not silently produce a zero or negative leg.
    """
    leg = slab_thickness_mm - slab_cover_mm
    if leg <= 0.0:
        raise ValueError(
            "The roof slab's cover (%.1f mm) is not less than its thickness "
            "(%.1f mm), so there is no vertical run to bend within. Both are "
            "read from the slab (R37) -- check the element above this column."
            % (slab_cover_mm, slab_thickness_mm))
    return leg


def free_edge_run_mm(column_width_mm, cover_mm):
    """Section 2's ``b_E`` cap: ``column width at that face - cover x 2``.

    This is the whole point of the free-edge case. With no slab beyond the
    column, a full-length horizontal leg would run out into open air, so
    the leg may use only what lies inside the concrete.
    """
    run = column_width_mm - cover_mm * 2.0
    if run <= 0.0:
        raise ValueError(
            "A %.1f mm face with %.1f mm cover on both sides leaves no room "
            "for a bend inside the column (section 2's b_E cap)."
            % (column_width_mm, cover_mm))
    return run


def _split(ld_mm, a_formula_mm):
    """Section 1's ``a + b = L_D`` with section 2.3's cap discipline.

        a = min(a_formula, L_D - 200)
        b = max(200, L_D - a)

    Restated, not imported -- see the module docstring.
    """
    if ld_mm < MIN_BEND_LEG_MM:
        raise ValueError(
            "L_D = %.1f mm is below the %.0f mm minimum bend leg, so no "
            "valid vertical/bent split exists. R35: raise the multiplier or "
            "the bar diameter -- the tool will not choose either."
            % (ld_mm, MIN_BEND_LEG_MM))
    a = min(a_formula_mm, ld_mm - MIN_BEND_LEG_MM)
    b = max(MIN_BEND_LEG_MM, ld_mm - a)
    return a, b


def terminate_bar(ld_mm, slab_thickness_mm, slab_cover_mm, directions):
    """Section 2, for ONE bar: which way it bends, and what it develops.

    ``directions`` are the ways this particular bar could turn, in the
    order the caller states them. A bar with none has nowhere to go and is
    refused rather than given a straight end that would look placed.

    **Slab continuing anywhere wins.** Section 2: a corner bar "may bend
    into whichever available direction has slab", achieving full ``L_D`` --
    it is never forced into a direction that happens to face a free edge.

    Only when NO direction has slab does the free-edge cap apply, and then
    the bar still develops ``a + b_E``, short of ``L_D`` by
    ``shortfall_mm``.
    """
    if not directions:
        raise ValueError(
            "This bar has no bend direction at all, so section 1's leg "
            "cannot be placed. A roof bar needs somewhere to turn.")

    a, b = _split(ld_mm, vertical_leg_mm(slab_thickness_mm, slab_cover_mm))

    with_slab = [one for one in directions if one.has_slab]
    if with_slab:
        # STATED DEFAULT, not a rule: section 2 says there is "no preferred
        # direction" among those with slab, and something must still be
        # deterministic or the same column details differently between
        # runs. First-stated is chosen because it keeps the caller's own
        # order meaningful; any of them is equally valid per the spec, and
        # this is recorded as a default the way R31 records "the left of
        # the two top corners".
        return RoofTermination(
            direction=with_slab[0].name, a_mm=a, b_mm=b, ld_mm=ld_mm,
            achieved_mm=a + b, shortfall_mm=0.0, free_edge=False)

    # STATED DEFAULT, not a rule: with every direction a free edge, the
    # longest available run is taken, because it develops the most bar.
    # Section 2 does not choose between two free edges -- it only caps each
    # one -- so this is a default, and it is the ENGINEERING-best of the
    # options rather than an arbitrary first.
    best = max(directions, key=lambda one: one.available_run_mm)
    if best.available_run_mm <= 0.0:
        raise ValueError(
            "Free edge %r leaves no run inside the column for the bend "
            "(section 2's b_E cap). Check the face width and cover."
            % (best.name,))
    b_edge = min(b, best.available_run_mm)
    achieved = a + b_edge
    return RoofTermination(
        direction=best.name, a_mm=a, b_mm=b_edge, ld_mm=ld_mm,
        achieved_mm=achieved, shortfall_mm=max(0.0, ld_mm - achieved),
        free_edge=True)
