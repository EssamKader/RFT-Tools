# IsolatedFooting.extension -- standing rules for this element only

Per `docs/token-efficient-expansion.md` Sec 2: repo-root `CONTEXT.md` carries
only rules true for every element. Anything footing-specific lives here.

## Scope, as of #198

**In:** bottom mesh, straight case only (no hooks, no L-shape alternation)
-- one `mesh_bar_x` bar and one `mesh_bar_y` bar, centred on the footing's
plan centroid, placed hosted directly on a picked isolated footing
`FamilyInstance`. The `rft.core.footing_plan.build_footing_plan` composing
module (spec Sec 4) is the one object any future report/preview and the
placer both read the bottom-mesh geometry from.

**Not yet in** (spec Sec 11's tracer-bullet order, followed as-is):

- Hook / development-length decision per bar end (#199, Story 2 / spec
  Sec 5).
- L-shape-alternating option (Story 3 / spec Sec 6).
- Top mesh (Story 4 / spec Sec 7).
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

## Open spec gap: X == Y

`specs/isolated-footing.md` Sec 2/3 states the Primary-direction rule only
as "if X > Y => Primary Reinforcement in X direction". It does not say
what happens when the two column-face offsets are exactly equal.
`rft.core.footing_mesh.primary_reinforcement_direction` raises
`FootingDirectionTieError` in that case rather than guessing a tie-break --
see that function's own docstring. If a footing with X == Y needs
detailing, this is a decision ticket, not something to resolve inline.

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
