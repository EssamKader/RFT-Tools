# -*- coding: utf-8 -*-
"""The single composing object a future report/preview AND the placer both
read the bottom-mesh (and, as of #201, optional top-mesh) geometry from.

Spec Ref: specs/isolated-footing.md Sec 4 ("Data flow"). Built now, per
docs/token-efficient-expansion.md Sec 7, BEFORE a second consumer exists --
this ticket's own placement code is the FIRST consumer and reads the plan
from here rather than calling ``rft.core.footing_mesh`` directly, so a
later report ticket has one place to read from instead of two independently
diverging call sites (the beam tool's ``ZONE_LAYOUT_FLAGS`` drift bug).

#201 (Spec Ref: Sec 3 Story 4, Sec 7): the top mat is not new mesh math --
it is the SAME ``mesh_bar_lengths`` / ``primary_reinforcement_direction`` /
``local_mesh_bar_endpoints`` / ``bar_hook_plan_for_mat`` call sequence #198/
#199/#200 already run for the bottom mat, run a second time with the top
mat's own ``top_mat_shape_mode``. ``_build_mesh_mat_plan`` below is that one
shared call sequence both mats go through, so it is never duplicated
inline per mat (the same "one composing module" discipline Sec 4 already
applies to bottom vs. a future report consumer, now applied to bottom vs.
top too).
"""

from collections import namedtuple

from .column_layout import perimeter_bar_positions
from .footing_dowels import (
    dowel_embedment,
    dowel_hook_exceeds_footing_edge,
    dowel_outward_direction,
    local_dowel_bar_geometry,
    positioned_dowel_bar_geometry,
)
from .footing_dowel_ties import dowel_tie_ladder, dowel_tie_loop_mm
from .footing_perimeter_tie import (
    perimeter_tie_bar_lengths_mm,
    perimeter_tie_geometry,
    perimeter_tie_ladder_mm,
)
from .footing_mesh import (
    MAT_SHAPE_L_ALTERNATING,
    MAT_SHAPE_U,
    bar_hook_plan_for_mat,
    bottom_mesh_bar_array_geometry,
    bottom_mesh_bar_geometry,
    local_mesh_bar_endpoints,
    local_top_mesh_bar_endpoints,
    mesh_bar_lengths,
    primary_reinforcement_direction,
    top_mesh_bar_geometry,
)

#: ``MAT_SHAPE_L_ALTERNATING``/``MAT_SHAPE_U`` (imported above) are
#: re-exported from THIS module on purpose: the pushbutton script may only
#: import from ``footing_plan`` (docs/token-efficient-expansion.md Sec 7,
#: `tests/test_footing_plan.py::test_the_pushbutton_script_reads_the_
#: composing_plan_not_bare_footing_mesh`), so #200's own U/L-alternating
#: constants need to be reachable here rather than forcing a direct
#: ``rft.core.footing_mesh`` import in the script.

#: Every straight-case input this ticket's geometry needs. ``x_offset_mm``/
#: ``y_offset_mm`` are the column-face clear offsets (Sec 2/3's `X`/`Y`),
#: supplied directly rather than derived from `a`/`b`/`Cw` here -- deriving
#: them would need a column footprint dimension the spec's Sec 2/3 naming
#: table never names for the b-direction, which is a gap outside this
#: ticket's formulas, not something to fill by guessing a symbol.
#: ``ld_multiplier`` is Sec 5's ``LD = multiplier * db`` multiplier -- a
#: single user input/code-table value shared by both directions, per
#: Sec 5's own wording ("the multiplier is a user input or code-table
#: lookup"), not a separate value per direction.
#: ``bottom_mat_shape_mode`` is Sec 3 (Story 3) / Sec 6's direct, per-mat
#: user override (``None``, ``footing_mesh.MAT_SHAPE_U`` or
#: ``footing_mesh.MAT_SHAPE_L_ALTERNATING``) -- ``None`` (the default, so
#: every existing caller that predates #200 keeps #199's behaviour
#: unchanged) means no override was given and Story 2's own per-end LD
#: comparison still decides.
#:
#: #201 (Sec 3 Story 4, Sec 7): ``top_reinforcement`` is the direct,
#: never-inferred user toggle between ``TOP_REINFORCEMENT_BTM_ONLY`` (the
#: default, so every existing caller that predates #201 keeps building a
#: bottom-only plan unchanged) and ``TOP_REINFORCEMENT_TOP_AND_BTM``.
#: ``top_mat_shape_mode`` is the top mat's OWN U/L-alternating override
#: (same three values as ``bottom_mat_shape_mode``), set independently --
#: Sec 7's own wording, "Independent of Story 3 ... the BTM-only/TOP+BTM
#: toggle and the U-shape/L-shape toggle are set separately, never
#: coupled." Neither top field reuses the bottom mat's own dimensional
#: inputs by inventing a second set of them: Sec 7 names no top-mat-
#: specific ``a``/``b``/cover/diameter, so the top mat is built from the
#: SAME ``a_mm``..``ld_multiplier`` fields above -- only the shape-mode
#: differs per mat.
#: #202 (Sec 3 Story 5, Sec 8): ``dowel_bar_dia_mm``/``dowel_ld_multiplier``
#: are the dowel's OWN diameter and LD multiplier -- distinct fields from
#: ``mesh_bar_x_dia_mm``/``mesh_bar_y_dia_mm``/``ld_multiplier`` above,
#: since Sec 8's ``LD = multiplier * db`` uses the dowel bar's own ``db``,
#: never a mesh bar's. Both default to ``None`` (no dowel plan built) so
#: every existing caller that predates #202 keeps building a mesh-only
#: plan unchanged -- same trailing-defaults pattern #200/#201 already
#: established for ``bottom_mat_shape_mode``/``top_reinforcement``/
#: ``top_mat_shape_mode``.
#: #203 (Sec 3 Story 6, Sec 9): ``dowel_tie_dia_mm``/``dowel_tie_spacing_mm``
#: are the tie's own direct user inputs -- Sec 9 states both have NO
#: default, matching Sec 8's own ``dowel_bar_dia_mm``/``dowel_ld_multiplier``
#: pattern immediately above. Both default to ``None`` (no dowel-tie
#: ladder built) so every existing caller that predates #203 is unchanged.
#: ``dowel_tie_dia_mm`` is carried on ``FootingInputs`` (not just the
#: spacing) even though the core ladder math in this module never reads
#: the diameter -- Sec 9 names diameter and spacing as one paired user
#: input, and the diameter is what a future placement adapter needs to
#: resolve a ``RebarBarType``, the same reasoning ``dowel_bar_dia_mm``
#: already carries a value #202's own ladder-equivalent code never reads
#: either.
#: #204 (Sec 3 Story 7, Sec 10): ``perimeter_tie_dia_mm``/
#: ``perimeter_tie_spacing_mm``/``perimeter_tie_quantity`` are direct user
#: inputs Sec 10 names but this ticket's own core math never reads --
#: they are carried here for the SAME reason ``dowel_tie_dia_mm`` is
#: carried unread by #203's ladder math: a future placement adapter needs
#: them (diameter to resolve a ``RebarBarType``, spacing/quantity for the
#: vertical array this ticket explicitly does NOT build -- see
#: ``rft.core.footing_perimeter_tie``'s own docstring, "Scope this ticket
#: does NOT cover"). ``perimeter_tie_lap_mm`` is Sec 8/10's ``Ls`` -- a
#: direct user input, no default, consumed by ``perimeter_tie_splice``
#: only when ``perimeter_tie_length_mm`` exceeds the 12m stock length.
#: All four default to ``None`` (opt-in, gated on ``perimeter_tie_dia_mm``
#: being supplied) so every existing caller that predates #204 keeps
#: building a plan with no ``perimeter_tie`` unchanged -- same trailing-
#: defaults pattern #200-#203 already established.
#: R4/R5 (`docs/footing/spec-amendments.md`), added after #204 merged:
#: ``perimeter_tie_first_bar_length_mm``/``perimeter_tie_second_bar_
#: length_mm`` are the engineer's own two individual cut lengths for a
#: split ``perimeter_tie`` (R5 -- a direct two-field input, not a formula;
#: only meaningful when the loop must be split, validated against the
#: total ``perimeter_tie_splice`` computes by
#: ``footing_perimeter_tie.perimeter_tie_bar_lengths_mm``). Both default
#: to ``None``; the ladder itself (R4) needs no new ``FootingInputs``
#: fields -- it is built from ``footing_thickness_mm``/``bottom_cover_mm``/
#: ``mesh_bar_x_dia_mm``/``mesh_bar_y_dia_mm`` (all already present) plus
#: the already-existing ``perimeter_tie_spacing_mm``/
#: ``perimeter_tie_quantity``.
#: #222 (specs/isolated-footing-dowel-array.md Sec 3 Story 3, ruling R6):
#: ``dowel_count_b_face``/``dowel_count_h_face`` are the dowel array's own
#: count-per-face-including-corners inputs, the SAME counting convention
#: ``column_layout.perimeter_bar_positions``'s own ``count_b_face``/
#: ``count_h_face`` already use for ColumnRFT -- R6's own ruling is that a
#: dowel array is not an independently invented count/spacing input, it
#: mirrors the column's own longitudinal bar layout exactly. Both default
#: to ``None`` (opt-in, same trailing-defaults pattern every dowel-related
#: field has used since #202) so every caller that predates this ticket
#: keeps building a plan with no dowel array unchanged. ``Cw_mm``/
#: ``Cd_mm``/``Ccover_mm`` themselves are NOT ``FootingInputs`` fields --
#: per the addendum spec Sec 4 ("Data flow"), they are read live off the
#: auto-detected column (a later ticket's own adapter work) and passed
#: into ``build_footing_plan`` as plain arguments alongside ``inputs``,
#: never stored here.
#: #232 (R11, docs/footing/spec-amendments.md): ``mesh_bar_x_spacing_mm``/
#: ``mesh_bar_y_spacing_mm`` are the direct, per-direction user spacing
#: inputs the bottom-mesh ARRAY is built from (count derived, never a
#: separate typed count) -- mirrors ``dowel_tie_spacing_mm``'s own
#: precedent (a direct number, no default). Appended at the very end,
#: both defaulting to ``None`` (opt-in) so every caller that predates
#: #232 keeps building a plan with no array, unchanged -- the SAME
#: trailing-defaults pattern every field since ``bottom_mat_shape_mode``
#: has used.
FootingInputs = namedtuple(
    "FootingInputs",
    ["a_mm", "b_mm", "cover_mm", "footing_thickness_mm",
     "bottom_cover_mm", "top_cover_mm",
     "mesh_bar_x_dia_mm", "mesh_bar_y_dia_mm",
     "x_offset_mm", "y_offset_mm", "ld_multiplier",
     "bottom_mat_shape_mode", "top_reinforcement", "top_mat_shape_mode",
     "dowel_bar_dia_mm", "dowel_ld_multiplier",
     "dowel_tie_dia_mm", "dowel_tie_spacing_mm",
     "perimeter_tie_dia_mm", "perimeter_tie_spacing_mm",
     "perimeter_tie_quantity", "perimeter_tie_lap_mm",
     "perimeter_tie_first_bar_length_mm",
     "perimeter_tie_second_bar_length_mm",
     "dowel_count_b_face", "dowel_count_h_face",
     "mesh_bar_x_spacing_mm", "mesh_bar_y_spacing_mm",
     "dowel_splice_length_mm"],
)
#: Python 2/3-compatible way to give a namedtuple field a default without
#: breaking every existing positional/keyword call site that predates
#: #200/#201 (this repo's IronPython 2.7 target rules out dataclasses'
#: `field(default=...)`). Only the trailing fields get defaults, in field
#: order: ``bottom_mat_shape_mode=None`` (#200), then #201's
#: ``top_reinforcement=TOP_REINFORCEMENT_BTM_ONLY`` and
#: ``top_mat_shape_mode=None``.
TOP_REINFORCEMENT_BTM_ONLY = "BTM_ONLY"
TOP_REINFORCEMENT_TOP_AND_BTM = "TOP_AND_BTM"

#: R12 (docs/footing/spec-amendments.md): ``dowel_splice_length_mm`` is
#: append-only at the very end, default ``None`` -- every caller that
#: predates this ticket keeps building the dowel's vertical leg stopping
#: exactly at ``footing_thickness_mm``, unchanged.
FootingInputs.__new__.__defaults__ = (
    None, TOP_REINFORCEMENT_BTM_ONLY, None, None, None, None, None,
    None, None, None, None, None, None,
    None, None, None, None, None)

#: ``lengths`` is a ``footing_mesh.MeshBarLengths``; ``primary_direction``
#: is ``footing_mesh.DIRECTION_X``/``DIRECTION_Y``; ``bar_x_endpoints``/
#: ``bar_y_endpoints`` are ``footing_mesh.BarEndpoints`` (footing-local mm);
#: ``bar_x_hooks``/``bar_y_hooks`` are ``footing_mesh.BarHookPlan`` (#199,
#: Sec 3 Story 2 / Sec 5; #200's per-mat U/L-alternating override, Sec 3
#: Story 3 / Sec 6, is applied before this plan is built -- see
#: ``FootingInputs.bottom_mat_shape_mode``).
#: #229: ``bar_x_geometry``/``bar_y_geometry`` are each a
#: ``footing_mesh.MeshBarGeometry`` -- the bar's own REAL bent centreline
#: (straight run plus each hooked end's vertical leg), built from this
#: SAME plan's own ``lengths``/``bar_x_hooks``/``bar_y_hooks`` right after
#: this namedtuple is constructed (see ``build_footing_plan``). ``None``
#: on ``TopMeshPlan`` (shares this field list, see below) -- the top mat
#: has no hook-direction ruling and no placement adapter yet, so it is
#: never computed there; only the BOTTOM mat's own build step fills it in.
#: #232 (R11): ``bar_x_array``/``bar_y_array`` are each a tuple of
#: ``footing_mesh.MeshBarGeometry`` -- the FULL bottom-mesh array per
#: direction, built by the SAME per-bar hook logic ``bar_x_geometry``/
#: ``bar_y_geometry`` already use, only at ``inputs.mesh_bar_x_spacing_mm``/
#: ``mesh_bar_y_spacing_mm``-derived positions instead of one bar at the
#: centroid. ``None`` when that direction's own spacing was not supplied
#: (every caller that predates #232, and any direction left unspaced) --
#: the placement adapter falls back to the single ``bar_x_geometry``/
#: ``bar_y_geometry`` bar in that case, unchanged. Always ``None`` on
#: ``TopMeshPlan`` (the array, like the bent geometry above, is
#: bottom-mat-only -- see ``footing_mesh.bottom_mesh_bar_array_geometry``).
BottomMeshPlan = namedtuple(
    "BottomMeshPlan",
    ["lengths", "primary_direction", "bar_x_endpoints", "bar_y_endpoints",
     "bar_x_hooks", "bar_y_hooks", "bar_x_geometry", "bar_y_geometry",
     "bar_x_array", "bar_y_array"],
)
BottomMeshPlan.__new__.__defaults__ = (None, None, None, None)

#: #201 (Sec 3 Story 4, Sec 7): mirrors ``BottomMeshPlan`` field-for-field
#: -- the top mat is the same per-mat geometry/hook decision as the bottom
#: mat, just built with the top mat's own ``top_mat_shape_mode``, so it
#: carries exactly the same shape rather than inventing a differently-
#: shaped plan for what is not new math. #233 (R13): ``bar_x_geometry``/
#: ``bar_y_geometry`` are now populated too, by
#: ``footing_mesh.top_mesh_bar_geometry`` -- the mirror image of
#: ``bottom_mesh_bar_geometry`` (hook leg subtracted, not added).
#: ``bar_x_array``/``bar_y_array`` stay ``None`` here -- #232's own array
#: builder is still bottom-mat-only; the top mat's array is separate,
#: unbuilt follow-up scope (this ticket's own PR description), the same
#: "single representative bar first" step the bottom mat itself went
#: through between #229 and #232.
TopMeshPlan = namedtuple("TopMeshPlan", BottomMeshPlan._fields)
TopMeshPlan.__new__.__defaults__ = (None, None, None, None)

#: #222 (specs/isolated-footing-dowel-array.md Sec 4, "Data flow"): the
#: column's own live cross-section width/depth and dowel-positioning
#: cover, bundled into ONE namedtuple rather than passed as three
#: same-typed, same-unit positional floats -- found in review (PR #225):
#: three bare floats at two call sites (``build_footing_plan`` and
#: ``_build_dowel_plan``) invite a silent width/depth swap that
#: type-checks fine and produces a silently mirrored array. A caller now
#: either constructs this by keyword or gets a ``TypeError`` at
#: construction, never a silent transposition.
#: Deliberately named ``DowelColumnSection``, NOT ``ColumnSection`` --
#: found in review (PR #227): ``rft.core.column_host_rules`` already
#: defines its OWN, differently-shaped ``ColumnSection`` (``b_mm h_mm
#: narrow_mm wide_mm``) for ColumnRFT. Reusing that exact name here would
#: have replaced this PR's own width/depth-swap fix with an adjacent
#: same-name/different-shape collision the moment both modules are
#: imported together -- exactly what #221 will need to do. That existing
#: type is untouched; this is a new, footing-dowel-specific type.
#: No construction-time validation: a caller can still build one with a
#: ``None`` sub-field, and (as of this writing) ``_build_dowel_plan`` is
#: the ONLY place that checks all three fields are non-``None`` before
#: using it. A smart constructor (mirroring ``column_host_rules.
#: section_from_dimensions``'s validate-once pattern) would close this
#: structurally for every future consumer, but is left out of THIS
#: ticket's scope (found in review, PR #227) since #222/#227 have exactly
#: one consumer today; revisit if/when #221 or #223 adds a second one.
DowelColumnSection = namedtuple(
    "DowelColumnSection", ["Cw_mm", "Cd_mm", "Ccover_mm"])

#: #202 (Sec 3 Story 5, Sec 8), reshaped by #222 (specs/isolated-footing-
#: dowel-array.md Sec 3 Story 3): ``embedment`` is a ``footing_dowels.
#: DowelEmbedment`` (``a_dowel_mm``/``b_dowel_mm``/``ld_mm``) -- ONE shared
#: value, since every dowel in the array has identical vertical sizing,
#: never re-derived per bar. ``bars`` is a list of ``footing_dowels.
#: DowelBarGeometry`` (bent-bar centreline resting on top of the bottom
#: mesh, see ``footing_dowels`` docstrings), one entry per dowel position.
#:
#: When ``inputs.dowel_count_b_face``/``dowel_count_h_face``/
#: ``dowel_tie_dia_mm`` and the ``column_section`` (``DowelColumnSection``)
#: argument to ``build_footing_plan`` are all supplied, ``bars`` holds one
#: ``DowelBarGeometry`` per position
#: ``column_layout.perimeter_bar_positions`` returns (corner dowels
#: de-duplicated -- see ``_build_dowel_plan``). Otherwise ``bars`` holds
#: exactly the SAME single representative bar (centred on the footing's
#: own plan centroid) #202 always built -- every caller that predates
#: #222 keeps building a plan with no dowel array unchanged, just wrapped
#: in the new one-item ``bars`` list instead of a bare ``geometry`` field,
#: per docs/token-efficient-expansion.md Sec 7 (one composing-module
#: shape, built before a second consumer -- #223's placement adapter --
#: exists).
#:
#: Issue #230: ``overshoot_bar_indices`` (append-only field, added after
#: this ticket's own DowelArrayPlan shape shipped) is the list of indices
#: into ``bars`` whose hook far end (``bars[i].bottom_hook.start``) lands
#: outside the footing's own plan edge (``footing_dowels.dowel_hook_
#: exceeds_footing_edge``, computed once here so the report and any future
#: consumer read the SAME list rather than re-deriving it). Empty when no
#: bar overshoots -- the common case -- never ``None``, so a caller can
#: always call ``len()``/iterate without a null check.
DowelArrayPlan = namedtuple(
    "DowelArrayPlan", ["embedment", "bars", "overshoot_bar_indices"])

#: #203 (Sec 3 Story 6, Sec 9): ``ladder`` is a
#: ``footing_dowel_ties.DowelTieLadder`` -- the starter/end-offset vertical
#: ladder, spacing_mm as supplied.
#: #242: ``loop`` is a ``footing_dowel_ties.DowelTieLoop`` -- the closed-
#: loop rectangle wrapping the WHOLE dowel array, footing-local plan
#: corners, no Z (the ladder's own ``levels`` supply that). ``None`` when
#: no real dowel array exists yet (``dowel`` is ``None``, or its own
#: ``bars`` still holds the single-representative-bar fallback -- see
#: ``footing_dowel_ties.dowel_tie_loop_mm``'s own refusal for fewer than
#: 2 bars) or when the tie bar type's own bend diameter was not supplied
#: (``dowel_tie_bend_diameter_mm`` -- read live off the ``RebarBarType``
#: at the Revit layer, passed into ``build_footing_plan`` alongside
#: ``inputs``, never stored on ``FootingInputs``, the same "read live,
#: pass in as a plain argument" shape ``column_section`` already
#: established). The LADDER is unaffected either way -- every caller that
#: predates #242 (tie diameter/spacing supplied, no array/bend diameter
#: yet) keeps building the SAME ladder-only plan, unchanged.
DowelTiePlan = namedtuple("DowelTiePlan", ["ladder", "tie_dia_mm", "loop"])

#: #204 (Sec 3 Story 7, Sec 10): ``geometry`` is a
#: ``footing_perimeter_tie.PerimeterTieGeometry`` (inner dimensions,
#: length, splice decision, footing-local plan corners). ``dia_mm``/
#: ``spacing_mm``/``quantity`` are carried straight off ``inputs`` for a
#: future placement adapter, unread by this ticket's own math -- same
#: reasoning ``DowelTiePlan.tie_dia_mm`` is carried unread by #203.
#: ``ladder`` (R4, added after #204 merged) is
#: ``footing_perimeter_tie.PerimeterTieLadder`` -- built from
#: ``spacing_mm``/``quantity`` plus the footing's own geometry, always
#: present once ``perimeter_tie`` itself is (spacing/quantity were
#: already required opt-in inputs). ``bar_lengths`` (R5) is
#: ``footing_perimeter_tie.PerimeterTieBarLengths`` when both
#: ``perimeter_tie_first_bar_length_mm``/``perimeter_tie_second_bar_
#: length_mm`` are supplied AND the loop needed splitting, else ``None``
#: (an unsplit loop, or a split loop whose two lengths the engineer
#: hasn't typed yet).
PerimeterTiePlan = namedtuple(
    "PerimeterTiePlan",
    ["geometry", "dia_mm", "spacing_mm", "quantity", "ladder",
     "bar_lengths"])

#: ``top_mesh`` is ``None`` when ``inputs.top_reinforcement ==
#: TOP_REINFORCEMENT_BTM_ONLY`` (Sec 7's "BTM only" option -- no top mat
#: exists at all, not an empty/zeroed one) and a ``TopMeshPlan`` when
#: ``TOP_REINFORCEMENT_TOP_AND_BTM`` is chosen.
#: ``dowel`` is ``None`` when ``inputs.dowel_bar_dia_mm``/
#: ``dowel_ld_multiplier`` were not supplied (#202 is opt-in, same
#: trailing-default pattern as ``top_mesh``) and a ``DowelArrayPlan``
#: (#222) otherwise.
#: ``dowel_ties`` is ``None`` when ``inputs.dowel_tie_dia_mm``/
#: ``dowel_tie_spacing_mm`` were not supplied (#203 is opt-in, same
#: trailing-default pattern) and a ``DowelTiePlan`` otherwise.
#: ``perimeter_tie`` is ``None`` when ``inputs.perimeter_tie_dia_mm`` was
#: not supplied (#204 is opt-in, same trailing-default pattern) and a
#: ``PerimeterTiePlan`` otherwise.
FootingPlan = namedtuple(
    "FootingPlan",
    ["inputs", "bottom_mesh", "top_mesh", "dowel", "dowel_ties",
     "perimeter_tie"])


def _bottom_mat_endpoints(lengths, inputs):
    """Bottom mat Z-elevation, measured from ``bottom_cover_mm`` upward --
    unchanged since #198."""
    return local_mesh_bar_endpoints(
        lengths, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
        inputs.mesh_bar_y_dia_mm)


def _top_mat_endpoints(lengths, inputs):
    """Top mat Z-elevation, measured from ``top_cover_mm`` / footing
    thickness downward -- see ``local_top_mesh_bar_endpoints``'s own
    docstring (R3, docs/footing/spec-amendments.md) for why this differs
    from the bottom mat; confirmed correct by Essam."""
    return local_top_mesh_bar_endpoints(
        lengths, inputs.top_cover_mm, inputs.footing_thickness_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm)


def _build_mesh_mat_plan(plan_cls, inputs, mat_shape_mode, endpoints_fn):
    """The one shared per-mat call sequence both the bottom and (#201) top
    mat go through: ``mesh_bar_lengths``, ``primary_reinforcement_
    direction``, an endpoints function and ``bar_hook_plan_for_mat``,
    parametrized by which mat's ``mat_shape_mode`` to honour and which
    ``endpoints_fn`` computes that mat's own Z-elevation.

    Spec Ref: Sec 4 (one composing module) and the #201 ticket body itself
    ("the top mat reuses the SAME mesh-length formulas ... and the SAME
    U-shape/L-shape choice mechanism ... this ticket wires a second mat
    instance through the existing per-mat logic, it does not invent new
    mesh math") -- extracted out of ``build_footing_plan`` so bottom and
    top call the identical sequence instead of it being written out twice
    and silently diverging (the beam tool's ``ZONE_LAYOUT_FLAGS`` bug this
    rule exists to avoid repeating).

    **Found in review (PR #214):** ``endpoints_fn`` exists because the
    bottom and top mats do NOT share the same Z-elevation formula --
    ``local_mesh_bar_endpoints`` measures from ``bottom_cover_mm``, which
    is only correct for the bottom mat. The lengths/direction/hook-plan
    calls above ARE genuinely identical for both mats (per spec Sec 4-6
    formulas, which cite no bottom/top distinction), so only the
    endpoints step is parametrized, not the whole sequence.
    """
    lengths = mesh_bar_lengths(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.top_cover_mm, inputs.mesh_bar_x_dia_mm)
    direction = primary_reinforcement_direction(
        inputs.x_offset_mm, inputs.y_offset_mm)
    bar_x_endpoints, bar_y_endpoints = endpoints_fn(lengths, inputs)
    # Spec Ref: Sec 2/3 -- a = 2*X + Cw is symmetric, so both ends of
    # mesh_bar_x share the same X offset (and both ends of mesh_bar_y the
    # same Y offset); bar_hook_plan_for_mat itself takes independent
    # start/end offsets for a future non-symmetric footing (Sec 0 F4).
    #
    # bar_index=0: #198/#199 place only ONE representative bar per
    # direction (full mesh count/spacing is a later ticket -- CONTEXT.md
    # "Not yet in"), so mesh_bar_x and mesh_bar_y are each that
    # direction's own bar 0. Sec 6's "consecutive bars alternate" only
    # produces a visible pattern once a real array of parallel bars
    # exists per direction; that wiring belongs to whichever ticket adds
    # the array, not this one. Same reasoning applies unchanged to the
    # top mat (#201).
    bar_x_hooks = bar_hook_plan_for_mat(
        0, mat_shape_mode,
        inputs.x_offset_mm, inputs.x_offset_mm, inputs.mesh_bar_x_dia_mm,
        inputs.ld_multiplier)
    bar_y_hooks = bar_hook_plan_for_mat(
        0, mat_shape_mode,
        inputs.y_offset_mm, inputs.y_offset_mm, inputs.mesh_bar_y_dia_mm,
        inputs.ld_multiplier)
    return plan_cls(
        lengths=lengths, primary_direction=direction,
        bar_x_endpoints=bar_x_endpoints, bar_y_endpoints=bar_y_endpoints,
        bar_x_hooks=bar_x_hooks, bar_y_hooks=bar_y_hooks)


class DowelArrayLayoutError(ValueError):
    """The live column cross-section/cover the caller supplied leaves no
    room for a dowel at ``perimeter_bar_positions``' own offset from the
    column face (cover + tie + half a bar).

    Wraps ``column_layout.perimeter_bar_positions``' own ``ValueError``
    (raised in column-cross-section wording -- "the bar centreline would
    fall outside the concrete") into a footing-domain error, the same
    pattern ``footing_dowel_ties.DowelTieRunTooShortError`` already
    establishes for wrapping a reused function's own ``ValueError`` (found
    in review, PR #225): every footing refusal is catchable as a
    footing-specific class, never a bare ``ValueError`` from a reused
    column module leaking through unlabelled.
    """


def _build_dowel_plan(inputs, column_section):
    """#202 (Sec 3 Story 5, Sec 8), extended by #222 (specs/isolated-
    footing-dowel-array.md Sec 3 Story 3): the one place ``footing_dowels.
    dowel_embedment``/``local_dowel_bar_geometry``/``translate_dowel_bar_
    geometry`` (and, when a real array is being built, ``column_layout.
    perimeter_bar_positions``) are called from, so a future report/preview
    and the placement adapter (#223) both read the SAME ``DowelArrayPlan``
    rather than each calling ``footing_dowels``/``column_layout``
    independently (the same Sec 4 "one composing module" rule
    ``_build_mesh_mat_plan`` already follows for the mesh mats).

    Reads mesh bar diameters and ``footing_thickness_mm``/
    ``bottom_cover_mm`` straight off ``inputs`` -- the SAME fields
    ``mesh_bar_lengths``/``local_mesh_bar_endpoints`` already read for the
    bottom mat -- never a second, independently-named copy of them.
    ``embedment`` is computed exactly once and shared by every bar in the
    array (Sec 3 Story 3: "every dowel has identical vertical sizing").

    A real array (``perimeter_bar_positions``, R6's own reuse target) is
    built only when the caller supplies the live column cross-section
    (``column_section`` -- a ``DowelColumnSection``, read live off the
    auto-detected column by a later ticket's adapter, never stored on
    ``FootingInputs``, per the addendum spec Sec 4) WITH ALL THREE of its
    own ``Cw_mm``/``Cd_mm``/``Ccover_mm`` fields set (found missing in
    review, PR #225: a non-``None`` ``column_section`` whose own fields
    are still ``None`` reproduced the exact same bare-``TypeError`` defect
    named below, one level down), AND the array's own THREE remaining
    opt-in ``FootingInputs`` fields: ``dowel_count_b_face``/``dowel_count_
    h_face`` (this ticket) and ``dowel_tie_dia_mm`` (#203 -- an
    independently opt-in field ``perimeter_bar_positions`` still requires
    as its own ``tie_dia_mm`` argument; found missing from this gate in
    review, PR #225, where its absence produced a bare ``TypeError`` deep
    in ``rft.core.layout`` instead of the documented fallback). That is
    FOUR conceptual inputs (``column_section`` as a whole, plus the two
    count fields, plus ``dowel_tie_dia_mm``), checked by SEVEN ``is not
    None`` terms (``column_section`` itself plus its own three
    sub-fields, plus the three remaining fields) -- found miscounted as
    "five"/"six" in review, PR #227. When ANY of these seven checks is
    not satisfied, ``bars`` falls back to the SAME single representative
    bar #202 always built, at the footing's own
    plan centroid -- every caller that predates #222 keeps building a
    plan with no dowel array unchanged (see ``DowelArrayPlan``'s own
    docstring).

    R12 (docs/footing/spec-amendments.md): ``inputs.dowel_splice_length_mm``
    is passed straight through to ``positioned_dowel_bar_geometry``/
    ``local_dowel_bar_geometry`` for every bar built here -- the SAME
    value for every bar in the array (Sec 8 gives no per-bar splice
    variation), never re-derived or defaulted here (``None`` already
    means "no splice, stop at the footing's own top face exactly as
    before", handled entirely inside ``footing_dowels``).

    ``perimeter_bar_positions``' own ``(u, v)`` is used directly as this
    footing's own local ``(x, y)`` with NO rotation transform for a column
    whose axes are not parallel to the footing's own a/b axes --
    ``column_host.read_orientation`` exists precisely because ColumnRFT
    found this can differ (#69). #222 has no orientation input available
    to it at all (pure numbers only, per the addendum spec Sec 4), so this
    is assumed and deferred, not silently forgotten: see
    ``docs/footing/reuse-audit.md`` Sec 1 (#222 entry) for the same note,
    to whichever future ticket (#221/#223) has access to the column's
    actual orientation.
    """
    embedment = dowel_embedment(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.dowel_bar_dia_mm, inputs.dowel_ld_multiplier)

    if (column_section is not None
            and column_section.Cw_mm is not None
            and column_section.Cd_mm is not None
            and column_section.Ccover_mm is not None
            and inputs.dowel_count_b_face is not None
            and inputs.dowel_count_h_face is not None
            and inputs.dowel_tie_dia_mm is not None):
        # Spec Ref: specs/isolated-footing-dowel-array.md Sec 3 Story 3 --
        # the exact call the addendum spec names, reused as-is (R6): every
        # dowel's footing-local (u, v) position, once, corner dowels
        # de-duplicated between faces.
        try:
            layout = perimeter_bar_positions(
                b_mm=column_section.Cw_mm, h_mm=column_section.Cd_mm,
                cover_mm=column_section.Ccover_mm,
                tie_dia_mm=inputs.dowel_tie_dia_mm,
                bar_dia_mm=inputs.dowel_bar_dia_mm,
                count_b_face=inputs.dowel_count_b_face,
                count_h_face=inputs.dowel_count_h_face)
        except ValueError as exc:
            raise DowelArrayLayoutError(
                "Column section %.1f x %.1f mm at cover %.1f mm leaves no "
                "room for a dowel array: %s"
                % (column_section.Cw_mm, column_section.Cd_mm,
                   column_section.Ccover_mm, exc))
        # R10 (docs/footing/spec-amendments.md): each bar's own hook bends
        # OUTWARD from the column centroid -- never the single fixed
        # direction every bar used to share. half_u/half_v are the BAR's
        # own half-dimensions (perimeter_bar_positions' internal values,
        # not the TIE's different ones PerimeterLayout itself returns),
        # recomputed here from the SAME two inputs that function used.
        half_u_mm = column_section.Cw_mm / 2.0 - layout.bar_offset_mm
        half_v_mm = column_section.Cd_mm / 2.0 - layout.bar_offset_mm
        bars = []
        for bar in layout.bars:
            direction_u, direction_v = dowel_outward_direction(
                bar.u_mm, bar.v_mm, half_u_mm, half_v_mm, bar.is_corner)
            bars.append(positioned_dowel_bar_geometry(
                embedment, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
                inputs.mesh_bar_y_dia_mm, bar.u_mm, bar.v_mm,
                direction_u, direction_v,
                splice_length_mm=inputs.dowel_splice_length_mm))
    else:
        bars = [local_dowel_bar_geometry(
            embedment, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
            inputs.mesh_bar_y_dia_mm,
            splice_length_mm=inputs.dowel_splice_length_mm)]

    # Issue #230: Sec 8's own b_dowel formula has no clamp against the
    # footing's own plan size -- flag, once, here (the one composing
    # module every consumer reads), never silently reshaped. half_a_mm/
    # half_b_mm are the footing's own plan half-extents in the SAME
    # footing-local frame (centroid at x=y=0) every bar's (u, v) already
    # uses (see this function's own docstring, "no rotation transform").
    half_a_mm = inputs.a_mm / 2.0
    half_b_mm = inputs.b_mm / 2.0
    overshoot_bar_indices = [
        index for index, bar in enumerate(bars)
        if dowel_hook_exceeds_footing_edge(
            bar.bottom_hook.start.x_mm, bar.bottom_hook.start.y_mm,
            half_a_mm, half_b_mm)]

    return DowelArrayPlan(embedment=embedment, bars=bars,
                          overshoot_bar_indices=overshoot_bar_indices)


def _build_dowel_tie_plan(inputs, dowel_plan, dowel_tie_bend_diameter_mm):
    """#203 (Sec 3 Story 6, Sec 9), extended by #242: the one place
    ``footing_dowel_ties.dowel_tie_ladder``/``dowel_tie_loop_mm`` are
    called from, so a future placement adapter reads the SAME
    ``DowelTiePlan`` rather than calling ``footing_dowel_ties``
    independently (Sec 4's "one composing module" rule, already applied
    above to the mesh mats and the dowel bar).

    ``dowel_plan`` is the SAME ``DowelArrayPlan`` (or ``None``)
    ``build_footing_plan`` already built -- never re-derived here, since
    a `dowel_tie` wraps THAT array, not a second one. ``loop`` stays
    ``None`` (ladder-only, #203's own original scope) unless a real array
    exists (``dowel_plan`` is not ``None`` and carries at least 2 bars --
    see ``footing_dowel_ties.dowel_tie_loop_mm``'s own refusal) AND
    ``dowel_tie_bend_diameter_mm``/``inputs.dowel_bar_dia_mm`` are both
    supplied.
    """
    ladder = dowel_tie_ladder(
        inputs.footing_thickness_mm, inputs.dowel_tie_spacing_mm)

    loop = None
    if (dowel_plan is not None and len(dowel_plan.bars) >= 2
            and dowel_tie_bend_diameter_mm is not None
            and inputs.dowel_bar_dia_mm is not None):
        loop = dowel_tie_loop_mm(
            dowel_plan.bars, inputs.dowel_tie_dia_mm,
            inputs.dowel_bar_dia_mm, dowel_tie_bend_diameter_mm)

    return DowelTiePlan(
        ladder=ladder, tie_dia_mm=inputs.dowel_tie_dia_mm, loop=loop)


def _build_perimeter_tie_plan(inputs):
    """#204 (Sec 3 Story 7, Sec 10), extended by R4/R5 after #204 merged:
    the one place ``footing_perimeter_tie.perimeter_tie_geometry``/
    ``perimeter_tie_ladder_mm``/``perimeter_tie_bar_lengths_mm`` are
    called from, so a future placement adapter reads the SAME
    ``PerimeterTiePlan`` rather than calling ``footing_perimeter_tie``
    independently (Sec 4's "one composing module" rule, already applied
    above to the mesh mats, the dowel bar and the dowel ties).

    Reads ``a_mm``/``b_mm``/``cover_mm`` straight off ``inputs`` -- the
    SAME fields ``mesh_bar_lengths`` already reads for the bottom mat,
    never a second, independently-named copy of them. The R4 ladder reads
    ``footing_thickness_mm``/``bottom_cover_mm``/``mesh_bar_x_dia_mm``/
    ``mesh_bar_y_dia_mm`` the same way -- the SAME fields the bottom mesh
    and the dowel bar already read, never re-derived.
    """
    geometry = perimeter_tie_geometry(
        inputs.a_mm, inputs.b_mm, inputs.cover_mm,
        inputs.perimeter_tie_lap_mm)
    ladder = perimeter_tie_ladder_mm(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.perimeter_tie_spacing_mm, inputs.perimeter_tie_quantity)

    bar_lengths = None
    if (geometry.splice.bar_count == 2
            and inputs.perimeter_tie_first_bar_length_mm is not None
            and inputs.perimeter_tie_second_bar_length_mm is not None):
        bar_lengths = perimeter_tie_bar_lengths_mm(
            geometry.splice, inputs.perimeter_tie_first_bar_length_mm,
            inputs.perimeter_tie_second_bar_length_mm)

    return PerimeterTiePlan(
        geometry=geometry, dia_mm=inputs.perimeter_tie_dia_mm,
        spacing_mm=inputs.perimeter_tie_spacing_mm,
        quantity=inputs.perimeter_tie_quantity, ladder=ladder,
        bar_lengths=bar_lengths)


def build_footing_plan(inputs, column_section=None,
                       dowel_tie_bend_diameter_mm=None):
    """The ONE place ``mesh_bar_lengths``, ``primary_reinforcement_
    direction``, ``local_mesh_bar_endpoints`` and ``bar_hook_plan_for_mat``
    are called from, for both the bottom mat and (#201) the optional top
    mat.

    #242: ``dowel_tie_bend_diameter_mm`` is the SAME "read live, pass in
    as a plain argument alongside ``inputs``" shape ``column_section``
    already established -- the selected ``dowel_tie`` ``RebarBarType``'s
    own ``StirrupTieBendDiameter`` (mm), read by the caller
    (``rft.revit.bar_types.bar_type_bend_diameter_mm``) and needed only to
    build the `dowel_tie` loop's own A1 buildability check
    (``footing_dowel_ties.dowel_tie_loop_mm``). Defaults to ``None`` so
    every caller that predates #242 (ladder-only ``dowel_ties``) is
    unchanged.

    Spec Ref: Sec 4. Both a future report/preview and the placer must call
    THIS function and read the ``FootingPlan`` it returns, never the
    ``footing_mesh`` functions above independently -- that is the single
    composing module docs/token-efficient-expansion.md Sec 7 requires.

    Spec Ref: Sec 3 Story 4, Sec 7 -- ``inputs.top_reinforcement`` is the
    direct user toggle (never inferred from ``footing_thickness_mm``)
    between ``TOP_REINFORCEMENT_BTM_ONLY`` (``top_mesh`` stays ``None``)
    and ``TOP_REINFORCEMENT_TOP_AND_BTM`` (builds a ``TopMeshPlan`` with
    ``inputs.top_mat_shape_mode``, independent of ``bottom_mat_shape_mode``
    per Sec 7's "set separately, never coupled").

    #222 (specs/isolated-footing-dowel-array.md Sec 4, "Data flow"):
    ``column_section`` is a ``DowelColumnSection`` (``Cw_mm``/``Cd_mm``/
    ``Ccover_mm`` -- the column's own live cross-section width/depth and
    dowel-positioning cover, bundled into one namedtuple rather than three
    bare same-typed floats, PR #225 review) -- deliberately NOT a
    ``FootingInputs`` field, since Sec 4 states it is "read live ... and
    passed in as plain arguments alongside inputs", keeping this function
    unit-testable with a plain ``DowelColumnSection`` (or ``None``) and no
    Revit object ever required. Defaults to ``None`` so every caller that
    predates #222 (this file's own callers that build no dowel array) is
    unchanged; see ``_build_dowel_plan`` for exactly which combination of
    ``column_section`` plus ``inputs.dowel_count_b_face``/``dowel_count_
    h_face``/``dowel_tie_dia_mm`` is required to build a real array.
    """
    bottom_mesh = _build_mesh_mat_plan(
        BottomMeshPlan, inputs, inputs.bottom_mat_shape_mode,
        _bottom_mat_endpoints)
    # #229: the bottom mat's own real bent U/L geometry, built from the
    # SAME lengths/hook-plan just computed above -- never re-derived
    # independently, so the report and the placer read the identical
    # shape (REUSE_GUIDELINES.md Sec 1).
    bar_x_geometry, bar_y_geometry = bottom_mesh_bar_geometry(
        bottom_mesh.lengths, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        bottom_mesh.bar_x_hooks, bottom_mesh.bar_y_hooks)
    # #232 (R11): the full array, per direction -- built from the SAME
    # lengths/hook-plan just computed above (never re-derived), so the
    # report and the placer read the identical bars. ``None`` per
    # direction when that direction's own spacing was not supplied (see
    # ``BottomMeshPlan.bar_x_array``/``bar_y_array``'s own docstring).
    bar_x_array, bar_y_array = bottom_mesh_bar_array_geometry(
        bottom_mesh.lengths, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        bottom_mesh.bar_x_hooks, bottom_mesh.bar_y_hooks,
        inputs.mesh_bar_x_spacing_mm, inputs.mesh_bar_y_spacing_mm)
    bottom_mesh = bottom_mesh._replace(
        bar_x_geometry=bar_x_geometry, bar_y_geometry=bar_y_geometry,
        bar_x_array=bar_x_array, bar_y_array=bar_y_array)

    if inputs.top_reinforcement == TOP_REINFORCEMENT_BTM_ONLY:
        top_mesh = None
    elif inputs.top_reinforcement == TOP_REINFORCEMENT_TOP_AND_BTM:
        top_mesh = _build_mesh_mat_plan(
            TopMeshPlan, inputs, inputs.top_mat_shape_mode,
            _top_mat_endpoints)
        # #233 (R13, docs/footing/spec-amendments.md): the top mat's own
        # real bent centreline -- the mirror image of the bottom mat's
        # own #229 step just above, built from this SAME plan's own
        # lengths/hook-plan, never re-derived independently. No array
        # (bar_x_array/bar_y_array) for the top mat yet -- see
        # TopMeshPlan's own docstring and this ticket's PR description.
        top_bar_x_geometry, top_bar_y_geometry = top_mesh_bar_geometry(
            top_mesh.lengths, inputs.top_cover_mm,
            inputs.footing_thickness_mm, inputs.mesh_bar_x_dia_mm,
            inputs.mesh_bar_y_dia_mm, top_mesh.bar_x_hooks,
            top_mesh.bar_y_hooks)
        top_mesh = top_mesh._replace(
            bar_x_geometry=top_bar_x_geometry,
            bar_y_geometry=top_bar_y_geometry)
    else:
        raise ValueError(
            "Unknown top_reinforcement %r; expected "
            "TOP_REINFORCEMENT_BTM_ONLY or TOP_REINFORCEMENT_TOP_AND_BTM"
            % (inputs.top_reinforcement,))

    dowel = None
    if (inputs.dowel_bar_dia_mm is not None
            and inputs.dowel_ld_multiplier is not None):
        dowel = _build_dowel_plan(inputs, column_section)

    dowel_ties = None
    if (inputs.dowel_tie_dia_mm is not None
            and inputs.dowel_tie_spacing_mm is not None):
        dowel_ties = _build_dowel_tie_plan(
            inputs, dowel, dowel_tie_bend_diameter_mm)

    perimeter_tie = None
    if inputs.perimeter_tie_dia_mm is not None:
        perimeter_tie = _build_perimeter_tie_plan(inputs)

    return FootingPlan(
        inputs=inputs, bottom_mesh=bottom_mesh, top_mesh=top_mesh,
        dowel=dowel, dowel_ties=dowel_ties, perimeter_tie=perimeter_tie)
