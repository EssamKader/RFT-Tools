# IsolatedFooting.extension -- standing rules for this element only

Per `docs/token-efficient-expansion.md` Sec 2: repo-root `CONTEXT.md` carries
only rules true for every element. Anything footing-specific lives here.

## Scope, as of #200

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

**Not yet in** (spec Sec 11's tracer-bullet order, followed as-is):

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
- Top mesh (Story 4 / spec Sec 7) and its own `top_mat_shape_mode` --
  Story 3 (Sec 6) is written to apply independently to whichever mats
  exist, but there is only a bottom mat to apply it to today.
- Full mesh bar count/spacing/quantity for either direction -- this
  ticket places ONE representative bar per direction only, to prove the
  placement mechanics; array/spacing is not named by any formula in the
  #198 ticket and is not invented here.
- Column dowels, dowel ties, perimeter tie (Stories 5-7 / spec Sec 8-10).
- Any modeless Review window -- inputs are asked one at a time with
  `pyrevit.forms` for now.
- Multi-footing / batch placement (F1, spec Sec 0) -- explicitly out of
  scope for the whole tool, not just this ticket.

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

## Open spec gap: LD == offset at a bar end

`specs/isolated-footing.md` Sec 5 defines the per-end hook decision only
as "LD > offset" (hook) and "offset > LD" (no hook, switch to L-shape). It
does not say what happens when they are exactly equal.
`rft.core.footing_mesh.bar_end_hook_decision` raises
`HookDevelopmentLengthTieError` in that case rather than guessing which
side of the boundary applies -- same discipline as the X == Y gap above.

## Reuse already decided (not re-derived here)

- `rft.revit.units.mm_to_internal` / `internal_to_mm` -- the repo's one mm
  <-> internal-units boundary (`REUSE_GUIDELINES.md` Sec 1). Reused as-is.
- `rft.revit.bar_types.bar_type_options` / `bar_type_diameter_mm` -- the
  already-verified `RebarBarType` enumeration and diameter read-back.
  Reused as-is; nothing footing-specific was added to that module.
- `dowel_tie` (spec Sec 9) and `perimeter_tie` (spec Sec 10) will reuse
  ColumnRFT's tie/stirrup geometry (`RFT.lib/rft/core/column_ties.py` +
  `column_tie_levels.py`, `RFT.lib/rft/revit/column_place_ties.py`) --
  spec Sec 1's decided reuse, not exercised by #198. See
  `docs/footing/reuse-audit.md` once #203 creates it.

## Verification status

`master` means the code exists; a tag (`footing/vX.Y.Z`) means it was
verified on a live host (repo-root `CONTEXT.md` rule 5). #198's placement
code follows the API pattern
`docs/footing/verification/issue-197-footing-tracer-bullet.md` proved with
a kept write, but #198 itself has not yet been run against a live host --
see that gap named in the PR that introduced this file.
