# -*- coding: utf-8 -*-
"""Footing-perimeter tie bar geometry and splice for the isolated footing
tool (#204).

Spec Ref: specs/isolated-footing.md Sec 3 (Story 7), Sec 10.
Pure core: no Revit import, plain numbers in, plain numbers out, in
millimetres (REUSE_GUIDELINES.md Sec 1, "Strict Core/Adapter Split").

## What this module is, and is not

`perimeter_tie` is separate from `dowel_tie` (#203): it wraps the
footing's own plan perimeter, bundling `mesh_bar_x`/`mesh_bar_y` together,
not the column dowel bars. Sec 10 gives this module everything it needs
for the footing's OWN geometry -- `a`, `b`, `cover` (all already carried
by `rft.core.footing_plan.FootingInputs` since #198) -- so, unlike
`dowel_tie` (`docs/footing/reuse-audit.md` Sec 1, "Blocked, not guessed"),
this ticket is NOT blocked on a bar array or a column cross-section
dimension: the closed rectangle is built directly from the footing's own
`a`/`b`/`cover`, the same way `footing_mesh.local_mesh_bar_endpoints`
already builds footing-local plan geometry from those same inputs.

`rft.core.column_ties.resolve_tie` is therefore **not called here**: its
signature takes a `ColumnLayout`/`layout.bars` -- named bar positions --
and grows a bounding box around them (see that module's own
`resolve_tie`/`_rectangle_corners`). A footing perimeter has no bar
positions to grow a box around; it has a plan rectangle it is already
offset in from by `cover`. Reusing `resolve_tie` here would mean
inventing two bar positions purely to hand it a box it would then have to
re-derive -- less direct than building the same four-corner rectangle
this module's own `local_perimeter_tie_corners_mm` computes straight from
`inner_a_mm`/`inner_b_mm`. See `docs/footing/reuse-audit.md` Sec 1 (this
ticket's own row) for the recorded verdict: the SHAPE (a closed rectangle)
is the thing spec Sec 1 says is reused conceptually, not `resolve_tie`'s
own code path, which needs data this element does not have.

## Scope this ticket does NOT cover: the vertical ladder / array

Sec 10 states diameter, spacing and quantity are all direct user inputs
("one `perimeter_tie` loop every 200mm vertically up the footing
thickness" is given only as an example), but -- unlike Sec 9's `dowel_tie`
("50mm from the bottom", "50mm below T.O.F.") -- Sec 10 states no starting
offset or array-position formula for WHERE the first (or only) loop sits
vertically, or how `quantity` loops are distributed between a start and
end. Building a Z-elevation ladder here would mean inventing that
placement rule, which REUSE_GUIDELINES.md Sec 3 ("Explicit Refusals")
forbids. This module therefore returns the closed-loop's plan geometry
(footing-local X/Y corners, no Z) and the length/splice math only;
`local_perimeter_tie_corners_mm`'s corners are meant to be reused at
whatever Z a later, spec-amended ticket resolves. Flagged to Essam as an
open question -- see `IsolatedFooting.extension/CONTEXT.md`'s "Scope, as
of #204" note.

## The splice's own open question -- RESOLVED (R5)

Sec 10 says a loop over 12m "split[s] into two bars, overlapped by lap
length `Ls` at the joint" (singular). A true closed rectangular loop has
no free ends, so splitting it into two straight bars would ordinarily need
TWO overlaps (one at each end where the two bars meet), not one -- but
Sec 10's own wording, and its "no restricted splice zone... may be placed
anywhere along the perimeter" reasoning, reads as the perimeter treated as
one long UNROLLED length cut at a single point, exactly like a straight
bar lap-spliced along its run (Sec 8's `Ls` is the same symbol, and is
stated there as a direct user input, not a computed value -- so `Ls`
itself is not the open question). What Sec 10 leaves unstated is how the
total "length + one lap" divides into the two bars' own individual cut
lengths -- :func:`perimeter_tie_splice` reports the DECISION (one bar or
two) and the total steel length to cut, and per **R5**
(`docs/footing/spec-amendments.md`), the per-bar split is NOT a formula
at all: the engineer types the two individual bar lengths directly (a 13m
total could be entered as 8m + 5m, 7m + 6m, or any other split chosen on
site), and :func:`perimeter_tie_bar_lengths_mm` only validates that the
two typed lengths sum to the total this module already computed -- it
never derives them.

## The vertical ladder -- RESOLVED (R4)

Sec 10 states diameter, spacing and quantity are all direct user inputs
("one `perimeter_tie` loop every 200mm vertically up the footing
thickness" is given only as an example), but -- unlike Sec 9's `dowel_tie`
("50mm from the bottom", "50mm below T.O.F.") -- Sec 10 states no starting
offset for WHERE the first (or only) loop sits vertically. Per **R4**
(`docs/footing/spec-amendments.md`), the first `perimeter_tie` sits
:data:`PERIMETER_TIE_START_OFFSET_ABOVE_BOTTOM_MESH_MM` (250mm) above the
bottom mesh's own top face -- the SAME "top of the bottom mesh" datum
`rft.core.footing_dowels`'s own bend-corner elevation already uses
(`bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm`, the top face
of `mesh_bar_y`). Every subsequent loop (up to the user's own `quantity`)
steps upward from there at the user's own `spacing_mm` --
:func:`perimeter_tie_ladder_mm` raises
:class:`PerimeterTieLadderExceedsFootingError` if that would place a loop
above the footing's own top face, since no spec text or ruling permits
that; it is a physical impossibility this module refuses rather than
silently allows.
"""

from collections import namedtuple

#: Spec Ref: Sec 10 -- "12m stock length, hardcoded, not a user input."
PERIMETER_TIE_STOCK_LENGTH_MM = 12000.0

#: R4 (`docs/footing/spec-amendments.md`) -- the first `perimeter_tie`
#: sits 250mm above the bottom mesh's own top face.
PERIMETER_TIE_START_OFFSET_ABOVE_BOTTOM_MESH_MM = 250.0

#: `inner_a_mm`/`inner_b_mm` -- Sec 10: "offset inward from all four faces
#: by cover". `a` is the footing's X-direction dimension, `b` its
#: Y-direction dimension (Sec 2/3 naming table), matching the same axis
#: convention `footing_mesh`'s `mesh_bar_x`/`mesh_bar_y` already use.
InnerDimensions = namedtuple("InnerDimensions", ["inner_a_mm", "inner_b_mm"])

#: One plan corner, footing-local mm, centroid at x=y=0 -- the SAME local
#: frame `footing_mesh.LocalPoint` uses, minus `z_mm`: this module
#: deliberately does not resolve a Z elevation (see module docstring,
#: "Scope this ticket does NOT cover").
PerimeterTieCorner = namedtuple("PerimeterTieCorner", ["x_mm", "y_mm"])

#: The splice decision. `bar_count` is 1 (continuous) or 2 (split at a
#: joint); `lap_mm` is `None` for a continuous bar and the supplied `Ls`
#: for a split one; `total_length_mm` is the total steel to cut --
#: `length_mm` unchanged for one bar, `length_mm + lap_mm` for two (one
#: lap's worth of extra steel at the single overlap Sec 10 describes).
PerimeterTieSplice = namedtuple(
    "PerimeterTieSplice", ["bar_count", "lap_mm", "total_length_mm"])

#: The whole `perimeter_tie` geometry/splice result for one footing.
#: `corners` is a 4-tuple of `PerimeterTieCorner`, wound the same way
#: `rft.core.column_ties._rectangle_corners` winds a closed loop's
#: rectangle (SW, SE, NE, NW) -- not imported from there (that function
#: takes a centre/half-dimension pair already in its own module's terms),
#: but kept consistent so a later placement adapter's winding-sensitive
#: hook-orientation reasoning (see `column_ties`' own docstring on
#: `_RECTANGLE_WINDING_SIGN`) transfers rather than needing re-deriving.
#: R4: the full vertical ladder -- `start_z_mm` is 250mm above the bottom
#: mesh's own top face, `levels_mm` is every loop's Z (absolute
#: footing-local, bottom face = 0), `spacing_mm`/`quantity` as supplied.
PerimeterTieLadder = namedtuple(
    "PerimeterTieLadder", ["start_z_mm", "levels_mm", "spacing_mm"])

#: R5: the engineer's own two individual bar cut lengths for a split
#: `perimeter_tie` (only meaningful when `PerimeterTieSplice.bar_count ==
#: 2` -- see :func:`perimeter_tie_bar_lengths_mm`).
PerimeterTieBarLengths = namedtuple(
    "PerimeterTieBarLengths", ["first_bar_length_mm", "second_bar_length_mm"])

PerimeterTieGeometry = namedtuple(
    "PerimeterTieGeometry",
    ["inner_a_mm", "inner_b_mm", "length_mm", "splice", "corners"])


class PerimeterTieLadderExceedsFootingError(ValueError):
    """A computed `perimeter_tie` level would sit above the footing's own
    top face.

    R4 anchors the ladder's START 250mm above the bottom mesh; nothing in
    the spec or that ruling states an UPPER bound, so a large `quantity`
    or `spacing_mm` could otherwise walk the ladder above the footing
    entirely. Refused rather than silently placed outside the footing --
    the same discipline `footing_dowel_ties.DowelTieRunTooShortError`
    already applies to its own physically-impossible case.
    """


class PerimeterTieBarLengthMismatchError(ValueError):
    """R5: the engineer's two typed bar lengths do not sum to the total
    steel length `perimeter_tie_splice` already computed
    (`length_mm + lap_mm`).

    Per R5, the split point is the engineer's own choice, not a formula --
    but the two lengths they type must still account for every millimetre
    of the total, or the cut list silently loses or invents steel.
    """


class PerimeterTieBarLengthsNotApplicableError(ValueError):
    """R5's two-field split only applies when `perimeter_tie_splice`
    decided the loop must be split (`bar_count == 2`). Calling
    :func:`perimeter_tie_bar_lengths_mm` for a single continuous bar has
    nothing to validate against -- refused rather than silently ignored,
    since a caller passing bar lengths for a one-bar loop is very likely
    reading stale UI state, not stating a real design decision.
    """


class PerimeterTieLapRequiredError(ValueError):
    """`perimeter_tie_length_mm` exceeds the 12m stock length but no lap
    length (`Ls`, spec Sec 8/10) was supplied.

    Sec 10 requires a lap at the joint whenever the loop must be split;
    Sec 8 states `Ls` is a direct user input, never a default -- so a
    missing `Ls` here is refused rather than guessed at, the same
    discipline `footing_dowel_ties.dowel_tie_ladder` already applies to
    its own no-default user input (`tie_spacing_mm`).
    """


def inner_dimensions_mm(a_mm, b_mm, cover_mm):
    """Spec Ref: Sec 10 -- `inner_a = a - 2*cover`; `inner_b = b - 2*cover`."""
    return InnerDimensions(
        inner_a_mm=a_mm - 2.0 * cover_mm,
        inner_b_mm=b_mm - 2.0 * cover_mm)


def perimeter_tie_length_mm(inner_a_mm, inner_b_mm):
    """Spec Ref: Sec 10 -- `perimeter_tie_length = 2*(inner_a + inner_b)`."""
    return 2.0 * (inner_a_mm + inner_b_mm)


def perimeter_tie_splice(length_mm, lap_mm=None):
    """Spec Ref: Sec 10 -- one continuous bar at or under the 12m stock
    length, or two bars overlapped by `Ls` (`lap_mm`) at the joint.

    Raises :class:`PerimeterTieLapRequiredError` when a split is required
    but `lap_mm` was not supplied (or is not positive) -- see this
    module's own docstring, "The splice's own open question", for why
    only the DECISION and total steel length are computed here, not the
    individual bar cut lengths.
    """
    if length_mm <= PERIMETER_TIE_STOCK_LENGTH_MM:
        return PerimeterTieSplice(
            bar_count=1, lap_mm=None, total_length_mm=length_mm)

    if lap_mm is None or lap_mm <= 0:
        raise PerimeterTieLapRequiredError(
            "perimeter_tie_length %.1f mm exceeds the %.1f mm stock "
            "length (Sec 10), so a splice is required, but no positive "
            "lap length (Ls, Sec 8/10 -- a direct user input, never a "
            "default) was supplied: got %r."
            % (length_mm, PERIMETER_TIE_STOCK_LENGTH_MM, lap_mm))

    return PerimeterTieSplice(
        bar_count=2, lap_mm=lap_mm, total_length_mm=length_mm + lap_mm)


def perimeter_tie_bar_lengths_mm(splice, first_bar_length_mm,
                                  second_bar_length_mm):
    """R5 (`docs/footing/spec-amendments.md`): validate the engineer's own
    two individual bar cut lengths against the total
    :func:`perimeter_tie_splice` already computed. Does NOT derive the
    split -- the engineer's own choice, per R5.

    Raises :class:`PerimeterTieBarLengthsNotApplicableError` when `splice`
    is a single continuous bar (`bar_count == 1` -- nothing to split), and
    :class:`PerimeterTieBarLengthMismatchError` when the two lengths do
    not sum to `splice.total_length_mm`.
    """
    if splice.bar_count == 1:
        raise PerimeterTieBarLengthsNotApplicableError(
            "This perimeter_tie is one continuous bar (total_length_mm="
            "%.1f mm, at or under the %.1f mm stock length) -- there is "
            "nothing to split, so first_bar_length_mm/"
            "second_bar_length_mm do not apply."
            % (splice.total_length_mm, PERIMETER_TIE_STOCK_LENGTH_MM))

    total_typed_mm = first_bar_length_mm + second_bar_length_mm
    if abs(total_typed_mm - splice.total_length_mm) > 1.0e-6:
        raise PerimeterTieBarLengthMismatchError(
            "first_bar_length_mm (%.1f) + second_bar_length_mm (%.1f) = "
            "%.1f mm, which does not match the total steel length this "
            "perimeter_tie needs (%.1f mm = %.1f mm length + %.1f mm lap). "
            "The engineer's own split point is free (R5), but the two "
            "lengths must still add up to the total."
            % (first_bar_length_mm, second_bar_length_mm, total_typed_mm,
               splice.total_length_mm, splice.total_length_mm - splice.lap_mm,
               splice.lap_mm))

    return PerimeterTieBarLengths(
        first_bar_length_mm=first_bar_length_mm,
        second_bar_length_mm=second_bar_length_mm)


def bottom_mesh_top_z_mm(bottom_cover_mm, mesh_bar_x_dia_mm,
                          mesh_bar_y_dia_mm):
    """The bottom mesh's own top face, footing-local Z (bottom face = 0) --
    the SAME datum `rft.core.footing_dowels`'s bend-corner elevation
    already uses (`bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm`,
    the top face of `mesh_bar_y`, the higher of the bottom mat's two bar
    layers). Recomputed here rather than imported, since `footing_dowels`
    does not expose this datum as a standalone function -- kept
    numerically identical on purpose, not re-derived independently.
    """
    return bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm


def perimeter_tie_start_z_mm(bottom_cover_mm, mesh_bar_x_dia_mm,
                              mesh_bar_y_dia_mm):
    """R4: the first `perimeter_tie`'s Z, footing-local (bottom face = 0) --
    :data:`PERIMETER_TIE_START_OFFSET_ABOVE_BOTTOM_MESH_MM` above
    :func:`bottom_mesh_top_z_mm`.
    """
    return (bottom_mesh_top_z_mm(
                bottom_cover_mm, mesh_bar_x_dia_mm, mesh_bar_y_dia_mm)
            + PERIMETER_TIE_START_OFFSET_ABOVE_BOTTOM_MESH_MM)


def perimeter_tie_ladder_mm(footing_thickness_mm, bottom_cover_mm,
                             mesh_bar_x_dia_mm, mesh_bar_y_dia_mm,
                             spacing_mm, quantity):
    """R4: the full `perimeter_tie` vertical ladder -- the first loop at
    :func:`perimeter_tie_start_z_mm`, then `quantity - 1` more loops
    stepping upward at the user's own `spacing_mm` (Sec 10: both direct
    user inputs, no default).

    Raises :class:`PerimeterTieLadderExceedsFootingError` if the last
    level would sit above the footing's own top face
    (`footing_thickness_mm`) -- see that exception's own docstring.
    """
    if spacing_mm is None or spacing_mm <= 0:
        raise ValueError(
            "spacing_mm must be a positive user input (Sec 10: no "
            "default) -- got %r." % (spacing_mm,))
    if quantity is None or quantity < 1:
        raise ValueError(
            "quantity must be a positive user input (Sec 10: no "
            "default) -- got %r." % (quantity,))

    start_z_mm = perimeter_tie_start_z_mm(
        bottom_cover_mm, mesh_bar_x_dia_mm, mesh_bar_y_dia_mm)
    levels_mm = tuple(
        start_z_mm + i * spacing_mm for i in range(int(quantity)))

    if levels_mm[-1] > footing_thickness_mm:
        raise PerimeterTieLadderExceedsFootingError(
            "The last perimeter_tie level (%.1f mm) sits above the "
            "footing's own top face (footing_thickness_mm=%.1f mm) -- "
            "%d loops at %.1f mm spacing starting %.1f mm above the "
            "bottom mesh do not fit inside this footing."
            % (levels_mm[-1], footing_thickness_mm, quantity, spacing_mm,
               start_z_mm - bottom_mesh_top_z_mm(
                   bottom_cover_mm, mesh_bar_x_dia_mm, mesh_bar_y_dia_mm)))

    return PerimeterTieLadder(
        start_z_mm=start_z_mm, levels_mm=levels_mm, spacing_mm=spacing_mm)


def local_perimeter_tie_corners_mm(inner_a_mm, inner_b_mm):
    """The closed rectangle's four plan corners, footing-local mm, centred
    on the footing's own plan centroid (x=y=0) -- the same centroid
    `footing_mesh.local_mesh_bar_endpoints` centres its bars on.

    Wound SW, SE, NE, NW (matching `column_ties._rectangle_corners`'s own
    order) so a future placement adapter's corner-to-corner leg order is
    unsurprising if it is ever compared against that module's convention.
    """
    half_a = inner_a_mm / 2.0
    half_b = inner_b_mm / 2.0
    return (
        PerimeterTieCorner(-half_a, -half_b),
        PerimeterTieCorner(half_a, -half_b),
        PerimeterTieCorner(half_a, half_b),
        PerimeterTieCorner(-half_a, half_b),
    )


def perimeter_tie_geometry(a_mm, b_mm, cover_mm, lap_mm=None):
    """The one place `inner_dimensions_mm`/`perimeter_tie_length_mm`/
    `perimeter_tie_splice`/`local_perimeter_tie_corners_mm` are called
    from together -- `rft.core.footing_plan.build_footing_plan` reads
    THIS function's result, never the pieces above independently (Sec 4,
    "one composing module").
    """
    inner = inner_dimensions_mm(a_mm, b_mm, cover_mm)
    length_mm = perimeter_tie_length_mm(inner.inner_a_mm, inner.inner_b_mm)
    splice = perimeter_tie_splice(length_mm, lap_mm)
    corners = local_perimeter_tie_corners_mm(
        inner.inner_a_mm, inner.inner_b_mm)
    return PerimeterTieGeometry(
        inner_a_mm=inner.inner_a_mm, inner_b_mm=inner.inner_b_mm,
        length_mm=length_mm, splice=splice, corners=corners)
