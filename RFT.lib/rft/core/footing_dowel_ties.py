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

## Reusing `column_tie_levels.tie_levels` for a footing that has no zones

`rft.core.column_tie_levels.tie_levels` builds a ladder against the
COLUMN spec's own confinement-zone model (`L0`, a confinement spacing
near each support face, a middle zone at a possibly coarser spacing).
Spec Sec 9 states no such zone distinction for a footing's dowel ties --
only a fixed start, a fixed end, and one user spacing throughout.

Rather than writing a second, parallel level-ladder algorithm (the
`docs/footing/reuse-audit.md`-mandated reuse target names this module
explicitly), this treats the whole dowel run as tie_levels' own
confinement-zone model, but **found and fixed in review**: `l0_mm` is set
to :data:`START_OFFSET_FROM_FOOTING_BOTTOM_MM` itself (50mm), NOT the
user's own tie spacing. `tie_levels` refuses upfront whenever
``2 * l0_mm >= clear_height_mm`` -- a real constraint for the COLUMN
model, where `L0` is a confinement-zone length independent of the tie
spacing within it, but a spurious one here if `l0_mm` were set to
`tie_spacing_mm`: it would falsely reject an ordinary, physically valid
footing/spacing combination (e.g. a 450mm-thick footing with a 250mm tie
spacing) purely because `2 * tie_spacing_mm` happens to exceed the
footing thickness, even though the actual usable run between the two
fixed 50mm offsets (350mm here) has nothing to do with that comparison.
Setting `l0_mm = START_OFFSET_FROM_FOOTING_BOTTOM_MM` makes `tie_levels`'
own bottom/top zones each collapse to exactly the one anchor tie
(50mm from each end) regardless of `tie_spacing_mm`, and its upfront
precondition becomes ``2 * 50 >= footing_thickness_mm`` -- the SAME
"footing too thin for the two fixed offsets" case
:func:`dowel_tie_run_mm` already checks independently, not a spurious
spacing-dependent one. `confinement_spacing_mm`/`middle_zone_spacing_mm`
are still set to `tie_spacing_mm` -- they only govern the (now unreached,
single-tie) confinement-zone stepping and the middle-zone equal
division, and the middle-zone division alone is what determines the
in-between ties: it rounds DOWN to fit evenly, never up, so the result
never exceeds the spacing the engineer typed. This is an engineering
adaptation of the reused function to a spec that has no zones of its
own, not a new spec-stated formula -- documented here, in
`docs/footing/reuse-audit.md`, and in `IsolatedFooting.extension/
CONTEXT.md`'s Sec 9 note, and flagged to Essam as worth confirming before
a live host run: a strict "every step exactly tie_spacing_mm, ragged last
bay" ladder is the other reasonable reading of "spacing is a user input"
and would need a different (much smaller) piece of code.
"""

from collections import namedtuple

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
    set to :data:`START_OFFSET_FROM_FOOTING_BOTTOM_MM` (50mm), NOT
    `tie_spacing_mm` -- **found and fixed in review**, see the module
    docstring for why setting `l0_mm = tie_spacing_mm` would spuriously
    refuse ordinary, physically valid footing/spacing combinations. With
    `l0_mm` anchored to the fixed offset, `tie_levels`' zone model
    degenerates to exactly one bottom anchor tie, one top anchor tie, and
    an equally-divided middle run at (or under) the user's spacing.

    `tie_levels` already applies its own `first_tie_offset_mm` symmetrically
    at BOTH ends of `clear_height_mm` -- exactly Sec 9's own shape (a fixed
    offset from the bottom, the SAME-VALUED fixed offset below T.O.F.), so
    this calls it directly with `clear_height_mm=footing_thickness_mm` and
    `first_tie_offset_mm=START_OFFSET_FROM_FOOTING_BOTTOM_MM`, rather than
    computing a relative run and re-shifting it afterwards. That only
    works because Sec 9 states the SAME 50mm value at both ends; the guard
    below refuses rather than silently mis-placing the end tie if the two
    module constants are ever changed to differ.

    With `l0_mm` anchored to the fixed offset, `tie_levels`' own upfront
    precondition (``2 * l0_mm >= clear_height_mm``) becomes exactly the
    SAME "footing too thin for the two fixed offsets" case
    :func:`dowel_tie_run_mm` already raises :class:`DowelTieRunTooShortError`
    for above -- so in practice `tie_levels` itself no longer raises for
    any input this function reaches (that check already failed earlier, on
    `dowel_tie_run_mm`'s own call). The `try`/`except` below is kept as a
    defensive re-wrap, not because a distinct `tie_levels`-only failure
    mode is expected today.
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
            l0_mm=START_OFFSET_FROM_FOOTING_BOTTOM_MM,
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
