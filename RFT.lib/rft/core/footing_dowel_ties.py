# -*- coding: utf-8 -*-
"""Dowel tie (stirrup) vertical placement for the isolated footing tool
(#203).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 6), Sec 9.
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").

## What this module is, and is not

Sec 9 states the `dowel_tie` PLACEMENT rule precisely: a starter tie 50mm
from the bottom of the footing, an end tie 50mm below Top of Footing
(T.O.F.), with the engineer's own diameter/spacing filling the run
between them. That vertical ladder -- genuinely new footing-specific
math, never built for any other element -- is what this module computes.

The tie's own SHAPE (a closed loop enclosing the dowel bars in plan) and
its Revit placement are **not** built here. Per `docs/footing/
reuse-audit.md` Sec 1 ("Blocked, not guessed"): `rft.core.column_ties.
resolve_tie` needs at least two named dowel-bar positions, and only ONE
representative dowel bar exists in this repo today (#202); building a
loop around it would mean inventing a bar array the spec's own tracer-
bullet order has not reached yet. See that audit for the full reasoning.
This is a REUSE_GUIDELINES.md Sec 3 "Explicit Refusal", not an oversight.

## The closed-loop rectangle (#242) -- built now that a real array exists

Per `docs/footing/reuse-audit.md` Sec 1: both prerequisites this module's
own earlier docstring named as blockers are resolved -- a real dowel-bar
array exists (#222/#223) and the column's own Cw/Cd are read live
(#220/#221). `dowel_tie_loop_mm` below builds the rectangle that WRAPS
that array, reusing `rft.core.column_ties.resolve_tie`/
`outer_perimeter_subset` AS-IS for the geometry (bounding box of the
enclosed bars' centrelines, grown by half a bar plus half a tie) --
per the ticket's own reuse plan, not re-derived here.

`resolve_tie` takes a `layout` whose `.bars` are objects with `.index`/
`.u_mm`/`.v_mm` (`rft.core.column_layout.Bar`'s own shape). `rft.core.
footing_plan.DowelArrayPlan.bars` is a list of `footing_dowels.
DowelBarGeometry` (`bottom_hook`/`vertical`), which carries no such
shape directly -- so `_ArrayLayout`/`_ArrayBarPosition` below are a thin,
LOCAL translation (per the ticket's own instruction: "a local translation
is fine", not a reshape of `DowelArrayPlan` itself). Each bar's own plan
position is read from `bar.vertical.start` (`footing_dowels.
positioned_dowel_bar_geometry`'s own docstring: the bend corner, at the
bar's own `(u_mm, v_mm)`, before the hook or the vertical leg's own
travel) -- the one point every dowel bar's geometry already carries that
IS its own plan position, never re-derived from the hook or the vertical
leg's end.

`resolve_tie` always wraps the WHOLE array (`outer_perimeter_subset`) --
there is no engineer-chosen subset here, unlike a column's own inner
ties (R17): a `dowel_tie` is one loop enclosing every dowel, per spec
Sec 9's own "the closed loop wraps the whole dowel array" reading (there
is no other tie topology named for it). If that whole-array rectangle's
narrow dimension is too small to bend (A1), `resolve_tie` degrades to a
`KIND_CROSS_TIE` rather than raising -- correct for an ENGINEER-CHOSEN
subset of two bars, but not a sensible detail for a loop that is supposed
to enclose the entire array, so :func:`dowel_tie_loop_mm` refuses
(`DowelTieNotBuildableError`) rather than silently placing a cross-tie
between two arbitrary array corners.

## Reusing `column_tie_levels.tie_levels` for a footing that has no zones

`rft.core.column_tie_levels.tie_levels` builds a ladder against the
COLUMN spec's own confinement-zone model (`L0`, a confinement spacing
near each support face, a middle zone at a possibly coarser spacing).
Spec Sec 9 states no such zone distinction for a footing's dowel ties --
only a fixed start, a fixed end, and one user spacing throughout.

Rather than writing a second, parallel level-ladder algorithm (the
`docs/footing/reuse-audit.md`-mandated reuse target names this module
explicitly), this treats the whole dowel run as tie_levels' own
confinement-zone model with `l0_mm` set equal to the user's own tie
spacing and `confinement_spacing_mm == middle_zone_spacing_mm ==
tie_spacing_mm`. With the two spacings equal, `tie_levels`' bottom/top
zones and its equal-division middle run all step at (or, only where an
uneven remainder forces it, slightly under) `tie_spacing_mm` --
`tie_levels`' own middle-zone division rounds DOWN to fit evenly, never
up, so the result never exceeds the spacing the engineer typed. This is
an engineering adaptation of the reused function to a spec that has no
zones of its own, not a new spec-stated formula -- documented here, in
`docs/footing/reuse-audit.md`, and in `IsolatedFooting.extension/
CONTEXT.md`'s Sec 9 note, and flagged to Essam as worth confirming before
a live host run: a strict "every step exactly tie_spacing_mm, ragged last
bay" ladder is the other reasonable reading of "spacing is a user input"
and would need a different (much smaller) piece of code.
"""

from collections import namedtuple

from .column_ties import KIND_CLOSED_LOOP, outer_perimeter_subset, resolve_tie
from .column_tie_levels import tie_levels

#: Spec Ref: Sec 9 -- "50mm from the bottom of the footing." Deliberately
#: its OWN constant, not shared with the column tool's
#: `column_layout.EDGE_OFFSET_MM` (also 50mm, per spec's column Sec 4):
#: `docs/column/reuse-audit.md` Sec 1 already ruled that two specs
#: agreeing on 50mm today is not a reason to couple them -- an amendment
#: to one must never silently move the other's tie.
START_OFFSET_FROM_FOOTING_BOTTOM_MM = 50.0

#: Spec Ref: Sec 9 -- "50mm below Top of Footing (T.O.F.)."
END_OFFSET_BELOW_TOF_MM = 50.0

#: The starter/end datum (absolute Z from the footing's own bottom face,
#: z=0 -- the same footing-local frame `footing_mesh.LocalPoint`/
#: `footing_dowels` already use) a `dowel_tie` ladder runs between.
DowelTieRun = namedtuple("DowelTieRun", ["start_z_mm", "end_z_mm"])

#: The full ladder: `levels` is a tuple of `column_tie_levels.TieLevel`,
#: whose own `z_mm` has been shifted so it reads as an ABSOLUTE footing-
#: local Z (footing bottom face = 0), not the zero-based value
#: `column_tie_levels.tie_levels` returns on its own.
DowelTieLadder = namedtuple(
    "DowelTieLadder", ["run", "levels", "spacing_mm"])


class DowelTieRunTooShortError(ValueError):
    """The footing is too thin for even one spacing step between the
    starter and end tie.

    Sec 9 gives the starter/end OFFSETS unconditionally; it says nothing
    about a minimum footing thickness for them to both fit with at least
    one spacing step between them. Rather than silently collapsing to a
    single tie or silently ignoring the user's spacing, this refuses --
    REUSE_GUIDELINES.md Sec 3, the same discipline `footing_mesh`'s
    `HookDevelopmentLengthTieError`/`FootingDirectionTieError` already
    follow for a spec silence found the same way.
    """


def dowel_tie_run_mm(footing_thickness_mm):
    """Spec Ref: Sec 9 -- the starter/end Z datum, absolute footing-local
    (bottom face = 0), before any spacing is applied.

    Raises :class:`DowelTieRunTooShortError` when the two fixed offsets
    would meet or cross -- a footing thinner than the two 50mm offsets
    combined has no run for a `dowel_tie` at all.
    """
    start_z = START_OFFSET_FROM_FOOTING_BOTTOM_MM
    end_z = footing_thickness_mm - END_OFFSET_BELOW_TOF_MM
    if end_z <= start_z:
        raise DowelTieRunTooShortError(
            "Footing thickness %.1f mm leaves no room for a dowel_tie run: "
            "the starter tie at %.1f mm from the bottom and the end tie at "
            "%.1f mm below T.O.F. (%.1f mm) meet or cross."
            % (footing_thickness_mm, start_z, footing_thickness_mm, end_z))
    return DowelTieRun(start_z_mm=start_z, end_z_mm=end_z)


def dowel_tie_ladder(footing_thickness_mm, tie_spacing_mm):
    """Spec Ref: Sec 9 -- the full `dowel_tie` vertical ladder: a starter
    tie at :data:`START_OFFSET_FROM_FOOTING_BOTTOM_MM`, an end tie at
    :data:`END_OFFSET_BELOW_TOF_MM` below T.O.F., and every tie between
    them at (or, only to fit evenly, slightly under) `tie_spacing_mm` --
    the direct user input, never defaulted (Sec 9's own wording).

    Reuses `column_tie_levels.tie_levels` per this module's own docstring
    ("Reusing `tie_levels` for a footing that has no zones"): `l0_mm` is
    set to `tie_spacing_mm` itself so the reused zone model degenerates to
    one continuous run at the user's spacing.

    `tie_levels` already applies its own `first_tie_offset_mm` symmetrically
    at BOTH ends of `clear_height_mm` -- exactly Sec 9's own shape (a fixed
    offset from the bottom, the SAME-VALUED fixed offset below T.O.F.), so
    this calls it directly with `clear_height_mm=footing_thickness_mm` and
    `first_tie_offset_mm=START_OFFSET_FROM_FOOTING_BOTTOM_MM`, rather than
    computing a relative run and re-shifting it afterwards. That only
    works because Sec 9 states the SAME 50mm value at both ends; the guard
    below refuses rather than silently mis-placing the end tie if the two
    module constants are ever changed to differ.

    Raises whatever `column_tie_levels.tie_levels` itself raises (a run
    shorter than `2 * tie_spacing_mm` has no middle zone in that
    function's own model) via :class:`DowelTieRunTooShortError`, so every
    refusal from this module carries the SAME exception type regardless
    of which of the two checks (this function's own, or `tie_levels`')
    actually fired.
    """
    if tie_spacing_mm is None or tie_spacing_mm <= 0:
        raise ValueError(
            "tie_spacing_mm must be a positive user input (Sec 9: no "
            "default) -- got %r." % (tie_spacing_mm,))
    if START_OFFSET_FROM_FOOTING_BOTTOM_MM != END_OFFSET_BELOW_TOF_MM:
        raise NotImplementedError(
            "dowel_tie_ladder's reuse of tie_levels' own symmetric "
            "first_tie_offset_mm assumes the starter and end offsets are "
            "equal (both currently 50mm per Sec 9); they no longer are, "
            "so this function must be rewritten to shift each end "
            "independently before it can be trusted.")

    run = dowel_tie_run_mm(footing_thickness_mm)

    try:
        ladder = tie_levels(
            clear_height_mm=footing_thickness_mm,
            l0_mm=tie_spacing_mm,
            confinement_spacing_mm=tie_spacing_mm,
            middle_zone_spacing_mm=tie_spacing_mm,
            first_tie_offset_mm=START_OFFSET_FROM_FOOTING_BOTTOM_MM)
    except ValueError as exc:
        raise DowelTieRunTooShortError(
            "Footing thickness %.1f mm with tie spacing %.1f mm leaves no "
            "room for a dowel_tie ladder between the starter (%.1f mm) and "
            "end (%.1f mm) ties: %s"
            % (footing_thickness_mm, tie_spacing_mm, run.start_z_mm,
               run.end_z_mm, exc))

    return DowelTieLadder(
        run=run, levels=ladder.levels, spacing_mm=tie_spacing_mm)


#: One dowel bar's plan position, in `column_layout.Bar`'s own shape
#: (`.index`/`.u_mm`/`.v_mm`) -- a LOCAL translation of `footing_plan.
#: DowelArrayPlan.bars`, not a reshape of that type itself (see this
#: module's own "The closed-loop rectangle" docstring section).
_ArrayBarPosition = namedtuple("_ArrayBarPosition", ["index", "u_mm", "v_mm"])

#: `resolve_tie`'s own `layout` argument needs only `.bars` -- this is the
#: whole of `column_layout.ColumnLayout`'s shape that function reads.
_ArrayLayout = namedtuple("_ArrayLayout", ["bars"])

#: The closed loop's own footing-local plan corners, mm, centred on the
#: footing's own plan centroid (x=y=0) -- the same frame `footing_dowels.
#: DowelBarGeometry`'s own `(u_mm, v_mm)` already uses. `corners` is
#: `resolve_tie`'s own `vertices` (already wound/closed per that module's
#: own rules), read as `(x_mm, y_mm)` pairs rather than `(u, v)` tuples,
#: matching `footing_perimeter_tie.PerimeterTieCorner`'s own naming
#: convention for a footing-local plan point.
DowelTieCorner = namedtuple("DowelTieCorner", ["x_mm", "y_mm"])
DowelTieLoop = namedtuple("DowelTieLoop", ["corners"])


class DowelTieArrayTooSmallError(ValueError):
    """Fewer than 2 dowel bars were supplied to wrap a loop around.

    `resolve_tie`'s own `subset_indices` already refuses a subset naming
    fewer than 2 bars ("a tie must touch at least 2 bars") -- this module
    raises its OWN, footing-domain exception for the same fact rather
    than letting that bare `ValueError` leak through unlabelled, the same
    wrapping discipline `footing_plan.DowelArrayLayoutError` already
    established for a reused function's own refusal (PR #225 review).

    This is the SAME situation `docs/footing/reuse-audit.md` Sec 1
    originally named as "Blocked, not guessed" for a caller with no real
    array (`footing_plan.DowelArrayPlan`'s own one-representative-bar
    fallback) -- not a new gap, just this ticket's own refusal for it.
    """


class DowelTieNotBuildableError(ValueError):
    """The whole-array rectangle's narrow dimension is too small to bend
    (A1) -- `resolve_tie` would degrade to a cross-tie, which is not a
    sensible detail for a loop meant to enclose the ENTIRE dowel array
    (see this module's own "The closed-loop rectangle" docstring
    section). Refused rather than silently placed as a two-bar cross-tie
    between two arbitrary corners of the array.
    """


def dowel_tie_loop_mm(dowel_bars, tie_dia_mm, bar_dia_mm, bend_diameter_mm):
    """#242 (Sec 3 Story 6, Sec 9): the closed-loop rectangle wrapping
    every bar in `dowel_bars` (a list of `footing_dowels.DowelBarGeometry`,
    e.g. `footing_plan.DowelArrayPlan.bars`) -- the bounding box of every
    bar's own plan position (`bar.vertical.start`), grown by half a bar
    plus half a tie, exactly as `rft.core.column_ties.resolve_tie` already
    computes for a column's own outer perimeter tie. Reused AS-IS for the
    geometry (see this module's own "The closed-loop rectangle" docstring
    section) -- no new rectangle math is written here.

    `bend_diameter_mm` is the tie bar TYPE's own `StirrupTieBendDiameter`
    (mm) -- read live off the selected `RebarBarType` at the Revit layer
    (`rft.revit.bar_types.bar_type_bend_diameter_mm`), passed in here as a
    plain number so this module stays Revit-free (REUSE_GUIDELINES.md
    Sec 1), the SAME "read live, pass in as a plain argument alongside
    inputs" shape `footing_plan.DowelColumnSection` already established
    for the column's own Cw/Cd/cover.

    Raises :class:`DowelTieArrayTooSmallError` for fewer than 2 bars, and
    :class:`DowelTieNotBuildableError` if the resulting rectangle cannot
    be bent (A1) -- see each exception's own docstring.
    """
    if len(dowel_bars) < 2:
        raise DowelTieArrayTooSmallError(
            "A dowel_tie loop needs at least 2 dowel bars to wrap -- got "
            "%d. This is the same 'no real array yet' situation "
            "docs/footing/reuse-audit.md Sec 1 named as blocked; supply "
            "a real dowel array (column_section plus dowel_count_b_face/"
            "dowel_count_h_face/dowel_tie_dia_mm) before building a "
            "dowel_tie loop." % len(dowel_bars))

    positions = [
        _ArrayBarPosition(
            index=index, u_mm=bar.vertical.start.x_mm,
            v_mm=bar.vertical.start.y_mm)
        for index, bar in enumerate(dowel_bars)]
    layout = _ArrayLayout(bars=positions)
    subset = outer_perimeter_subset(len(positions))
    resolved = resolve_tie(subset, layout, tie_dia_mm, bar_dia_mm,
                           bend_diameter_mm)

    if resolved.kind != KIND_CLOSED_LOOP:
        raise DowelTieNotBuildableError(
            "The dowel_tie loop wrapping all %d dowel bars cannot be "
            "bent as a closed loop: %s" % (len(dowel_bars), resolved.reason))

    corners = tuple(DowelTieCorner(x_mm=u, y_mm=v)
                    for u, v in resolved.vertices)
    return DowelTieLoop(corners=corners)
