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

from .footing_dowels import dowel_embedment, local_dowel_bar_geometry
from .footing_dowel_ties import dowel_tie_ladder
from .footing_mesh import (
    bar_hook_plan_for_mat,
    local_mesh_bar_endpoints,
    local_top_mesh_bar_endpoints,
    mesh_bar_lengths,
    primary_reinforcement_direction,
)

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
FootingInputs = namedtuple(
    "FootingInputs",
    ["a_mm", "b_mm", "cover_mm", "footing_thickness_mm",
     "bottom_cover_mm", "top_cover_mm",
     "mesh_bar_x_dia_mm", "mesh_bar_y_dia_mm",
     "x_offset_mm", "y_offset_mm", "ld_multiplier",
     "bottom_mat_shape_mode", "top_reinforcement", "top_mat_shape_mode",
     "dowel_bar_dia_mm", "dowel_ld_multiplier",
     "dowel_tie_dia_mm", "dowel_tie_spacing_mm"],
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

FootingInputs.__new__.__defaults__ = (
    None, TOP_REINFORCEMENT_BTM_ONLY, None, None, None, None, None)

#: ``lengths`` is a ``footing_mesh.MeshBarLengths``; ``primary_direction``
#: is ``footing_mesh.DIRECTION_X``/``DIRECTION_Y``; ``bar_x_endpoints``/
#: ``bar_y_endpoints`` are ``footing_mesh.BarEndpoints`` (footing-local mm);
#: ``bar_x_hooks``/``bar_y_hooks`` are ``footing_mesh.BarHookPlan`` (#199,
#: Sec 3 Story 2 / Sec 5; #200's per-mat U/L-alternating override, Sec 3
#: Story 3 / Sec 6, is applied before this plan is built -- see
#: ``FootingInputs.bottom_mat_shape_mode``).
BottomMeshPlan = namedtuple(
    "BottomMeshPlan",
    ["lengths", "primary_direction", "bar_x_endpoints", "bar_y_endpoints",
     "bar_x_hooks", "bar_y_hooks"],
)

#: #201 (Sec 3 Story 4, Sec 7): mirrors ``BottomMeshPlan`` field-for-field
#: -- the top mat is the same per-mat geometry/hook decision as the bottom
#: mat, just built with the top mat's own ``top_mat_shape_mode``, so it
#: carries exactly the same shape rather than inventing a differently-
#: shaped plan for what is not new math.
TopMeshPlan = namedtuple("TopMeshPlan", BottomMeshPlan._fields)

#: #202 (Sec 3 Story 5, Sec 8): ``embedment`` is a
#: ``footing_dowels.DowelEmbedment`` (``a_dowel_mm``/``b_dowel_mm``/
#: ``ld_mm``); ``geometry`` is a ``footing_dowels.DowelBarGeometry`` --
#: the one representative dowel bar's footing-local bent-bar centreline,
#: resting on top of the bottom mesh (see ``footing_dowels`` docstrings
#: for both).
DowelPlan = namedtuple("DowelPlan", ["embedment", "geometry"])

#: #203 (Sec 3 Story 6, Sec 9): ``ladder`` is a
#: ``footing_dowel_ties.DowelTieLadder`` -- the starter/end-offset vertical
#: ladder, spacing_mm as supplied. Per ``docs/footing/reuse-audit.md`` Sec 1
#: ("Blocked, not guessed"), this plan carries the ladder ONLY -- no tie
#: shape/loop geometry, since that needs a dowel-bar array this repo does
#: not have yet (#202 places one representative dowel).
DowelTiePlan = namedtuple("DowelTiePlan", ["ladder", "tie_dia_mm"])

#: ``top_mesh`` is ``None`` when ``inputs.top_reinforcement ==
#: TOP_REINFORCEMENT_BTM_ONLY`` (Sec 7's "BTM only" option -- no top mat
#: exists at all, not an empty/zeroed one) and a ``TopMeshPlan`` when
#: ``TOP_REINFORCEMENT_TOP_AND_BTM`` is chosen.
#: ``dowel`` is ``None`` when ``inputs.dowel_bar_dia_mm``/
#: ``dowel_ld_multiplier`` were not supplied (#202 is opt-in, same
#: trailing-default pattern as ``top_mesh``) and a ``DowelPlan`` otherwise.
#: ``dowel_ties`` is ``None`` when ``inputs.dowel_tie_dia_mm``/
#: ``dowel_tie_spacing_mm`` were not supplied (#203 is opt-in, same
#: trailing-default pattern) and a ``DowelTiePlan`` otherwise.
FootingPlan = namedtuple(
    "FootingPlan",
    ["inputs", "bottom_mesh", "top_mesh", "dowel", "dowel_ties"])


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


def _build_dowel_plan(inputs):
    """#202 (Sec 3 Story 5, Sec 8): the one place ``footing_dowels.
    dowel_embedment``/``local_dowel_bar_geometry`` are called from, so a
    future report/preview and the placement adapter both read the SAME
    ``DowelPlan`` rather than each calling ``footing_dowels`` independently
    (the same Sec 4 "one composing module" rule ``_build_mesh_mat_plan``
    already follows for the mesh mats).

    Reads mesh bar diameters and ``footing_thickness_mm``/
    ``bottom_cover_mm`` straight off ``inputs`` -- the SAME fields
    ``mesh_bar_lengths``/``local_mesh_bar_endpoints`` already read for the
    bottom mat -- never a second, independently-named copy of them.
    """
    embedment = dowel_embedment(
        inputs.footing_thickness_mm, inputs.bottom_cover_mm,
        inputs.mesh_bar_x_dia_mm, inputs.mesh_bar_y_dia_mm,
        inputs.dowel_bar_dia_mm, inputs.dowel_ld_multiplier)
    geometry = local_dowel_bar_geometry(
        embedment, inputs.bottom_cover_mm, inputs.mesh_bar_x_dia_mm,
        inputs.mesh_bar_y_dia_mm)
    return DowelPlan(embedment=embedment, geometry=geometry)


def _build_dowel_tie_plan(inputs):
    """#203 (Sec 3 Story 6, Sec 9): the one place
    ``footing_dowel_ties.dowel_tie_ladder`` is called from, so a future
    placement adapter reads the SAME ``DowelTiePlan`` rather than calling
    ``footing_dowel_ties`` independently (Sec 4's "one composing module"
    rule, already applied above to the mesh mats and the dowel bar).
    """
    ladder = dowel_tie_ladder(
        inputs.footing_thickness_mm, inputs.dowel_tie_spacing_mm)
    return DowelTiePlan(ladder=ladder, tie_dia_mm=inputs.dowel_tie_dia_mm)


def build_footing_plan(inputs):
    """The ONE place ``mesh_bar_lengths``, ``primary_reinforcement_
    direction``, ``local_mesh_bar_endpoints`` and ``bar_hook_plan_for_mat``
    are called from, for both the bottom mat and (#201) the optional top
    mat.

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
    """
    bottom_mesh = _build_mesh_mat_plan(
        BottomMeshPlan, inputs, inputs.bottom_mat_shape_mode,
        _bottom_mat_endpoints)

    if inputs.top_reinforcement == TOP_REINFORCEMENT_BTM_ONLY:
        top_mesh = None
    elif inputs.top_reinforcement == TOP_REINFORCEMENT_TOP_AND_BTM:
        top_mesh = _build_mesh_mat_plan(
            TopMeshPlan, inputs, inputs.top_mat_shape_mode,
            _top_mat_endpoints)
    else:
        raise ValueError(
            "Unknown top_reinforcement %r; expected "
            "TOP_REINFORCEMENT_BTM_ONLY or TOP_REINFORCEMENT_TOP_AND_BTM"
            % (inputs.top_reinforcement,))

    dowel = None
    if (inputs.dowel_bar_dia_mm is not None
            and inputs.dowel_ld_multiplier is not None):
        dowel = _build_dowel_plan(inputs)

    dowel_ties = None
    if (inputs.dowel_tie_dia_mm is not None
            and inputs.dowel_tie_spacing_mm is not None):
        dowel_ties = _build_dowel_tie_plan(inputs)

    return FootingPlan(
        inputs=inputs, bottom_mesh=bottom_mesh, top_mesh=top_mesh,
        dowel=dowel, dowel_ties=dowel_ties)
