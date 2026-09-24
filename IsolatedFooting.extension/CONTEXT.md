# IsolatedFooting.extension -- standing rules for this element only

Per `docs/token-efficient-expansion.md` Sec 2: repo-root `CONTEXT.md` carries
only rules true for every element. Anything footing-specific lives here.

## Scope, as of #204

**In:** `perimeter_tie` geometry and splice -- Story 7, spec Sec 10.
`rft.core.footing_perimeter_tie.perimeter_tie_geometry` computes
`inner_a`/`inner_b` (`a`/`b` offset inward by `cover`),
`perimeter_tie_length = 2*(inner_a+inner_b)`, the 12m-stock splice
decision (`perimeter_tie_splice`: one continuous bar at or under
`PERIMETER_TIE_STOCK_LENGTH_MM`, or two bars plus one `Ls` lap over it),
and the closed rectangle's four footing-local plan corners
(`local_perimeter_tie_corners_mm`, centred on the footing's own plan
centroid, no Z). `rft.core.footing_plan.FootingPlan.perimeter_tie` is the
one composing-module field a future placement adapter reads from --
`None` unless `FootingInputs.perimeter_tie_dia_mm` is supplied (opt-in,
same trailing-default pattern as `dowel`/`dowel_ties`).

**Not reusing `rft.core.column_ties.resolve_tie`, and this is a genuinely
different situation from `dowel_tie` (#203), not the same blocker
restated:** `resolve_tie` needs named bar positions to grow a bounding
box around; `perimeter_tie` wraps the footing's own plan perimeter, which
needs only `a`/`b`/`cover` -- already carried by `FootingInputs` since
#198, with no missing prerequisite. See `docs/footing/reuse-audit.md`
Sec 4 for the full verdict table.

**Resolved after #204 merged (R4/R5, `docs/footing/spec-amendments.md`):**

1. **The vertical ladder / array (R4).** The first `perimeter_tie` sits
   250mm above the bottom mesh's own top face
   (`rft.core.footing_perimeter_tie.PERIMETER_TIE_START_OFFSET_ABOVE_
   BOTTOM_MESH_MM`, using the SAME "top of the bottom mesh" datum
   `footing_dowels`'s bend corner already uses). Every subsequent loop (up
   to `FootingInputs.perimeter_tie_quantity`) steps upward at
   `perimeter_tie_spacing_mm` -- both already-existing direct user inputs.
   `perimeter_tie_ladder_mm` computes this and refuses
   (`PerimeterTieLadderExceedsFootingError`) if the ladder would place a
   loop above the footing's own top face.
2. **The splice's own per-bar cut lengths (R5).** Not a formula: the
   engineer types the two individual bar lengths directly
   (`FootingInputs.perimeter_tie_first_bar_length_mm`/`perimeter_tie_
   second_bar_length_mm` -- e.g. a 13m total as 8m + 5m, or 7m + 6m, any
   split). `perimeter_tie_bar_lengths_mm` validates the two typed lengths
   sum to the total `perimeter_tie_splice` already computes
   (`length_mm + lap_mm`); it never derives the split itself. Only
   meaningful when the loop needed splitting in the first place
   (`PerimeterTieBarLengthsNotApplicableError` otherwise).

Both are wired into `FootingPlan.perimeter_tie.ladder`/`.bar_lengths`
(`rft.core.footing_plan._build_perimeter_tie_plan`) -- the one composing
module both a future report and the placement adapter below will read
from, not called independently.

**Still NOT in #204/R4/R5, flagged as open (REUSE_GUIDELINES.md Sec 3):**

- **Revit placement.** No `rft.revit.footing_perimeter_tie` adapter is
  built yet -- R4's Z-elevations now exist to build curves from, but
  `docs/footing/verification/issue-197-footing-tracer-bullet.md` Sec 4
  lists closed-loop shapes as still unverified against a live footing
  host (only straight, unhooked curves were tested). The placement
  adapter should follow `rft.revit.column_place_ties`'s own
  `norm = XYZ.BasisZ` convention for a closed loop lying in a horizontal
  plane (perpendicular to the loop's own plane) -- NOT
  `rft.revit.footing_dowels`'s `XYZ.BasisY`, which is specific to a bent
  bar's vertical bend plane; a `perimeter_tie` loop is horizontal,
  geometrically the same case column ties already are.

## Scope, as of #203

**In:** the `dowel_tie` vertical placement ladder -- Story 6, spec Sec 9.
`rft.core.footing_dowel_ties.dowel_tie_run_mm` computes the fixed
starter/end datum (`START_OFFSET_FROM_FOOTING_BOTTOM_MM = 50.0` from the
footing's own bottom face, `END_OFFSET_BELOW_TOF_MM = 50.0` below Top of
Footing -- its own constants, deliberately NOT shared with the column
tool's identically-valued `column_layout.EDGE_OFFSET_MM`, per
`docs/column/reuse-audit.md` Sec 1's "two rules that coincide" ruling).
`dowel_tie_ladder` fills the run between them at the engineer's own tie
spacing (no default, per Sec 9) by calling `rft.core.column_tie_levels.
tie_levels` directly -- `clear_height_mm=footing_thickness_mm`,
`first_tie_offset_mm=START_OFFSET_FROM_FOOTING_BOTTOM_MM`, and
`l0_mm=confinement_spacing_mm=middle_zone_spacing_mm=tie_spacing_mm` so
the column's own confinement-zone model (which the footing spec has no
equivalent of) degenerates to one continuous run at the user's spacing.
This only works because Sec 9 states the SAME 50mm value at both ends;
`dowel_tie_ladder` raises `NotImplementedError` rather than silently
mis-placing the end tie if the two constants are ever changed to differ.
`rft.core.footing_plan.FootingPlan.dowel_ties` is the one composing-module
field a future placement adapter reads from -- `None` unless
`FootingInputs.dowel_tie_dia_mm`/`dowel_tie_spacing_mm` are both supplied
(opt-in, same trailing-default pattern as `dowel`/`top_mesh`).

**Explicitly NOT in #203, per `docs/footing/reuse-audit.md` Sec 1
("Blocked, not guessed"):** the `dowel_tie`'s own closed-loop SHAPE and its
Revit placement. `rft.core.column_ties.resolve_tie` needs at least two
named dowel-bar positions to build a rectangle from, and #202 places
exactly ONE representative dowel bar -- there is no bar array yet to wrap
a tie around. A real tie rectangle also needs the column's own
cross-section width/depth in the b-direction, which
`specs/isolated-footing.md` Sec 2/3's naming table never gives a symbol
for and `FootingInputs` does not carry today. Building either now would
mean guessing an array and a dimension the spec doesn't supply --
REUSE_GUIDELINES.md Sec 3's "Explicit Refusals" rule, applied here as a
documented scope boundary rather than a raised exception, since the
missing prerequisites are architectural (no data to guess with) rather
than a single ambiguous input value. See `docs/footing/reuse-audit.md`
Sec 1 for the full reasoning and the exact reuse calls (`resolve_tie`,
`rft.revit.column_place_ties.place_ties`) the follow-on ticket should make
once a dowel-bar array and a column cross-section field exist.

## Scope, as of #202

**In (added by #202):** column dowel embedment/hook sizing and placement
-- Story 5, spec Sec 8. `rft.core.footing_dowels.a_dowel` /
`dowel_embedment` compute `a_dowel = footing_thickness - bottom_cover -
mesh_bar_x_dia - mesh_bar_y_dia` and the `b_dowel`/`LD` comparison exactly
as Sec 8 states (`LD <= a_dowel + b_dowel_default` keeps the 200mm
default; `LD > a_dowel + b_dowel_default` sets `b_dowel = LD - a_dowel`),
reading the mesh bar diameters straight off `FootingInputs` -- the SAME
fields #198's mesh math already reads -- never a second, independently
hardcoded copy. `local_dowel_bar_geometry` places the bend corner exactly
on top of the bottom mesh (same Z-datum `footing_mesh.
local_mesh_bar_endpoints` already uses for the top of `mesh_bar_y`) and
the vertical leg's top exactly at the footing's own top face, per Sec 8's
"resting on top of the bottom mesh" / the embedment length being measured
inside the footing. `rft.core.footing_plan.FootingPlan.dowel` is the one
composing-module field both a future report and
`rft.revit.footing_dowels.place_dowel_bar` read from -- `None` unless
`FootingInputs.dowel_bar_dia_mm`/`dowel_ld_multiplier` are both supplied
(opt-in, same trailing-default pattern as `top_mesh`).
`place_dowel_bar` places ONE representative dowel, centred on the
footing's own plan centroid, as a single bent `Rebar` (two connected
curves: the horizontal hook leg, then the vertical leg) -- the same
tracer-bullet-vertical-slice precedent #198 set for the mesh bars, not
yet an array or a stirrup/tie.

**Resolved by R10 (docs/footing/spec-amendments.md), 2026-09-24 --
Essam, from a live-model screenshot:** Sec 8 names only the dowel's two
leg LENGTHS, never a plan direction for the hook, so `local_dowel_bar_
geometry` originally placed every bar's hook along a single fixed local
+X -- flagged in this file's own earlier text as an unconfirmed
placement choice, then found visibly wrong once a real array existed
(#222 widened it from one bar to the whole array, since every bar shared
the SAME fixed direction regardless of which face it sat on -- a bar on
the LEFT face bent back into the column instead of away from it).

**The rule:** a dowel's hook bends OUTWARD from the column centroid, per
bar position -- a face bar straight out perpendicular to its own face, a
corner bar along the 45-degree diagonal bisecting the two faces meeting
there. `rft.core.footing_dowels.translate_dowel_bar_geometry` (shift-
only, no rotation) is REMOVED -- replaced by `positioned_dowel_bar_
geometry` (builds each bar directly at its own position AND direction)
plus `dowel_outward_direction` (the rule itself, pure). `local_dowel_bar_
geometry` (the single-representative-bar fallback, no live column/array
inputs) is unchanged, now a thin call into the new function at the
origin with the legacy `+X` direction. The Revit adapter's own `norm`
argument (`rft.revit.footing_dowels._create_dowel_rebar`) is derived per
bar too (a 90-degree in-plane rotation of that bar's own hook vector),
since a fixed `XYZ.BasisY` was only ever correct for the old fixed +X
case. See `docs/footing/reuse-audit.md` §10 and
`docs/footing/verification/issue-222-real-dowel-array-inside-column.md`.

**Combining two already-proven facts into one NOT-yet-proven live
combination:** `place_dowel_bar` passes TWO connected curves to a single
`Rebar.CreateFromCurves` call on a FOOTING host. Issue #197's own tracer
bullet only tried one straight curve on a footing host; the multi-curve
bent-bar shape is proven live only on a COLUMN host
(`column_place_bars.py`'s roof-termination path, #173/#183). See
`rft/revit/footing_dowels.py`'s own "SHAPE UNVERIFIED" docstring note --
this composition should be confirmed on a live footing host before it
ships to a tag.

## Scope, as of #201

**In:** bottom mesh, straight case -- one `mesh_bar_x` bar and one
`mesh_bar_y` bar, centred on the footing's plan centroid, placed hosted
directly on a picked isolated footing `FamilyInstance`. The
`rft.core.footing_plan.build_footing_plan` composing module (spec Sec 4)
is the one object any future report/preview and the placer both read the
bottom-mesh geometry from. As of #199, that plan also carries each bar's
per-end hook/development-length decision and resulting U-/L-shape
(`rft.core.footing_mesh.bar_hook_plan`, spec Sec 3 Story 2 / Sec 5) -- the
decision only, not yet wired into the Revit placement adapter (see "Not
yet in" below). As of #200, `FootingInputs.bottom_mat_shape_mode` (`None`,
`footing_mesh.MAT_SHAPE_U` or `footing_mesh.MAT_SHAPE_L_ALTERNATING`) lets
that decision be overridden per mat with a direct user choice instead of
#199's own LD-vs-offset comparison (`footing_mesh.bar_hook_plan_for_mat`,
spec Sec 3 Story 3 / Sec 6) -- again the core decision only, not yet
wired into the pushbutton UI or the Revit placement adapter (see "Not yet
in" below). `bar_hook_plan_for_mat`'s `bar_index` parameter is generic
(the L-Shape-Alternating even/odd rule is mutation-proven for indices
0-3), but #198/#199 place only ONE representative bar per direction, so
`build_footing_plan` calls it with `bar_index=0` for both `mesh_bar_x` and
`mesh_bar_y` today -- a visible alternating pattern needs the bar-array
ticket below first.

As of #201, `FootingInputs.top_reinforcement` (`footing_plan.
TOP_REINFORCEMENT_BTM_ONLY`, the default, or `footing_plan.
TOP_REINFORCEMENT_TOP_AND_BTM`) is the direct user toggle for Story 4
(spec Sec 7) -- never inferred from `footing_thickness_mm`. When TOP +
BTM is chosen, `build_footing_plan` returns a `FootingPlan.top_mesh`
(`footing_plan.TopMeshPlan`, field-for-field identical to
`BottomMeshPlan`) built by the exact same `mesh_bar_lengths` /
`primary_reinforcement_direction` / `bar_hook_plan_for_mat` sequence as
the bottom mat (`footing_plan._build_mesh_mat_plan`, the one shared
per-mat helper both mats call), parametrized by the top mat's own
`FootingInputs.top_mat_shape_mode` -- independent of
`bottom_mat_shape_mode`, per Sec 7's "set separately, never coupled."
`top_mesh` is `None` (not an empty/zeroed plan) when BTM-only is chosen.
This is the composing-module decision only; the pushbutton UI and the
Revit placement adapter still only ask for and place the bottom mat (see
"Not yet in" below).

**Found and fixed in review (PR #214), confirmed as R3:** the endpoints
step is NOT the same function for both mats. The first version of this
ticket reused `local_mesh_bar_endpoints` (measured from `bottom_cover_mm`
upward) unchanged for the top mat, which placed the "top mat" at the
exact same elevation as the bottom mat. Fixed with a new
`footing_mesh.local_top_mesh_bar_endpoints`, measured from `top_cover_mm`
/ `footing_thickness_mm` downward instead. This mirrored convention (spec
Sec 7 names the TOP+BTM toggle but gives no explicit top-mat vertical
formula the way Sec 4's N/N2 do for the bottom mat) was proposed in code
and then confirmed correct by Essam — recorded as **R3** in
`docs/footing/spec-amendments.md`, same discipline as R1/R2.

**Not yet in** (spec Sec 11's tracer-bullet order, followed as-is):

- Wiring #201's `top_mesh` into the pushbutton UI (asking
  `top_reinforcement`/`top_mat_shape_mode` via `pyrevit.forms`) or into a
  Revit placement adapter that places the top mat's bars -- same
  core-before-UI/adapter precedent #199/#200 already set. `rft.revit.
  footing_mesh.place_straight_bottom_mesh` only knows how to place the
  bottom mat's two representative bars today.
- Wiring #199's hook decision into `rft.revit.footing_mesh.place_straight_
  bottom_mesh` -- placing an actual Revit hook (`RebarHookType`, hook
  orientation) on a bar end. Issue #197's own tracer-bullet write-up lists
  "hook types" under its Sec 4 "Still unverified" and #199's own ticket
  body only asked for the core decision math, not host wiring -- zero API
  guessing (`REUSE_GUIDELINES.md` Sec 3) means this stays a placement
  adapter TODO, not something to guess a `RebarHookType` shape for here.
  #200's override sits on top of the same un-wired decision and inherits
  this gap unchanged.
- Asking `bottom_mat_shape_mode` via the pushbutton UI
  (`IsolatedFootingRFT.pushbutton/script.py` still builds `FootingInputs`
  without it, so it defaults to `None` -- #199's own LD comparison keeps
  deciding until a later ticket adds the `pyrevit.forms` prompt and wires
  it through). #200's own ticket body named only
  `RFT.lib/rft/core/footing_mesh.py` as the file to extend, matching
  #199's precedent of shipping the core decision before the UI/adapter
  wiring.
- Full mesh bar count/spacing/quantity for either direction -- this
  ticket places ONE representative bar per direction only, to prove the
  placement mechanics; array/spacing is not named by any formula in the
  #198 ticket and is not invented here.
- The footing-perimeter tie bar (Story 7 / spec Sec 10) is still not
  wired into the pushbutton script or placed. `dowel_tie`'s own
  closed-loop shape and Revit placement (Story 6 / Sec 9, the rest of
  what #203 did not build) remains a follow-on ticket
  (`docs/footing/HANDOVER-2026-09-24.md` item 6) -- unblocked now that a
  real dowel-bar array exists and places (#222/#223), but not built.
- `dowel_tie`'s own closed-loop shape/placement and `perimeter_tie`
  placement remain out of the single-footing path AND the batch (spec
  Ref: `specs/isolated-footing-batch.md` §7) -- a batch cannot place what
  the single-footing path does not place either. `IsolatedFootingRFT.
  pushbutton/FootingWindow.xaml`'s own "Mesh & Dowels" tab deliberately
  asks nothing for these (see #205's own scope note below) rather than
  offering an input this tool cannot act on.

**Now DONE, no longer a gap (2026-09-24 session):** the dowel array
(#220-#223 -- auto-detect the column, read its Cw/Cd/cover live, compute
the full array, place every bar, hooks bending OUTWARD per R10), the
footing's own plan dimensions/thickness/three covers (#228 -- read live
off the picked `FamilyInstance`'s `STRUCTURAL_FOUNDATION_LENGTH`/`_WIDTH`/
`_THICKNESS` type parameters and `CLEAR_COVER_BOTTOM`/`_TOP`/`_OTHER`
instance parameters, never typed), multi-footing batch placement (#226,
`specs/isolated-footing-batch.md` -- collect by footing+column type
pair, group by R9's live-read tuple, plan/refuse/report, one
all-or-nothing transaction, `RFT-FTG-` ownership tagging via new
`rft.revit.footing_ownership`, live-host-verified including the
N-footing loop), and the modeless Review window (#205 -- `IsolatedFootingRFT.
pushbutton/FootingWindow.xaml` + `script.py`'s `FootingWindow` class,
`engine: persistent: true` now set) are all built. `x_offset_mm`/
`y_offset_mm`/`ld_multiplier`, the dowel array's own bar-type/LD-
multiplier/count-per-face inputs, and the batch checkbox all live in the
window's own three tabs (Footing & Column -- read-only live values;
Mesh & Dowels -- the shared inputs; Review -- the report plus Place/
Batch), shared across the whole batch when one is run -- see
`docs/footing/reuse-audit.md` §6-§10 and `docs/footing/verification/
issue-22{0,2,3,6}-*.md` / `issue-228-footing-dimension-read.md` for the
live-host proof.

**#205's own scope decision, recorded here (not a separate ruling --
a reuse/scope note, per REUSE_GUIDELINES.md §3):** the ticket's own text
names every input across #198-#204, including top mesh's U/L-shape
toggle, `dowel_tie` diameter/spacing and `perimeter_tie` diameter/
spacing/quantity. None of those three has a Revit PLACEMENT adapter in
this repo (see the bullet above and `docs/footing/reuse-audit.md`) --
only core math. Exposing input fields for them would let an engineer
configure something this tool cannot place, which is the exact
"guessed scope" REUSE_GUIDELINES.md §3 exists to prevent. The window
therefore wires only what #198-#228 actually PLACE (bottom mesh, the
dowel array, single or batch) and says so directly in its own "Mesh &
Dowels" tab, rather than silently expanding scope to build three new
placement adapters as a side effect of a UI-wiring ticket.

## Open gap: rotated footings refuse rather than place wrong

`rft.revit.footing_mesh._footing_origin` translates footing-local mm
coordinates into world XYZ using only the footing's bounding-box centre,
with no rotation transform. Per issue #69's own finding for columns
(bounding boxes are axis-aligned in model space and only agree with the
element's own dimensions at 0/90/180/270 deg), a rotated footing would get
its bars placed along world X/Y instead of its own a/b directions if this
went unchecked. `_footing_origin` therefore raises
`FootingRotationUnsupportedError` for any footing not at a quarter-turn,
per REUSE_GUIDELINES.md Sec 3's "Explicit Refusals" rule (found and fixed
in review, PR #209). Supporting a rotated footing needs a live-host check
of `footing.GetTransform()` against the plan centroid and the family's own
a/b axes — unverified, and a decision ticket of its own, not something to
guess at inline.

## Resolved spec gap: X == Y (R1)

`specs/isolated-footing.md` Sec 2/3 states the Primary-direction rule only
as "if X > Y => Primary Reinforcement in X direction" and never said what
happens when the two column-face offsets are exactly equal. Raised to
Essam directly rather than guessed; ruling recorded as R1 in
`docs/footing/spec-amendments.md`: it does not matter which direction is
Primary in the tie case. `rft.core.footing_mesh.primary_reinforcement_
direction` now defaults to `DIRECTION_X` when `x_offset_mm == y_offset_mm`.

## Resolved spec gap: LD == offset at a bar end (R2)

`specs/isolated-footing.md` Sec 5 defines the per-end hook decision only
as "LD > offset" (hook) and "offset > LD" (no hook, switch to L-shape) and
never said what happens when they are exactly equal. Raised to Essam
directly rather than guessed; ruling recorded as R2 in
`docs/footing/spec-amendments.md` -- **not** a silent default: the
automatic comparison keeps raising `HookDevelopmentLengthTieError`, and
the engineer gets the SAME explicit U-shape/L-shape-alternating choice
#200 already built (`bar_hook_plan_for_mat` with an explicit
`mat_shape_mode`) instead of leaving that mat on automatic.

## Reuse already decided (not re-derived here)

- `rft.revit.units.mm_to_internal` / `internal_to_mm` -- the repo's one mm
  <-> internal-units boundary (`REUSE_GUIDELINES.md` Sec 1). Reused as-is.
- `rft.revit.bar_types.bar_type_options` / `bar_type_diameter_mm` -- the
  already-verified `RebarBarType` enumeration and diameter read-back.
  Reused as-is; nothing footing-specific was added to that module.
- `dowel_tie` (spec Sec 9) reuses `column_tie_levels.tie_levels` for its
  vertical ladder, exercised as of #203 -- see `docs/footing/
  reuse-audit.md`. Its own closed-loop shape (`column_ties.resolve_tie`)
  and `column_place_ties.py`'s placement pattern remain reuse targets not
  yet exercised, blocked on a dowel-bar array and a column cross-section
  field that don't exist yet (see "Scope, as of #203" above). `perimeter_
  tie` (spec Sec 10) is unstarted -- #204's own ticket, per spec Sec 1's
  decided reuse.

## Verification status

`master` means the code exists; a tag (`footing/vX.Y.Z`) means it was
verified on a live host (repo-root `CONTEXT.md` rule 5). #198's placement
code follows the API pattern
`docs/footing/verification/issue-197-footing-tracer-bullet.md` proved with
a kept write, but #198 itself has not yet been run against a live host --
see that gap named in the PR that introduced this file.
