# Isolated Footing — Dowel Array & Column Auto-Detection (Addendum)

> **Status: DRAFT — pending Essam's confirmation, per ai-kaderskill To-Spec.**
> `specs/isolated-footing.md` is itself LOCKED and is not edited by this
> file. This is a companion addendum, same relationship
> `isolated-footing.md` already has to `beam-rft-detailing.md`/
> `column-rft-detailing.md`. It fills in what `specs/isolated-footing.md`
> §8/§9 (Story 5/6) left as an open gap — dowel count/layout and the
> column's own cross-section — now that Essam has ruled on both (R6/R7,
> `docs/footing/spec-amendments.md`).

Companion to `specs/isolated-footing.md`. Same discipline: every rule
cites its source (either the parent spec section or the ruling that
settled it), every reuse decision is stated rather than re-derived.

---

## 0. Why this exists

`docs/footing/HANDOVER-2026-09-24.md` items 5/6 named two architectural
gaps blocking the dowel array and, in turn, `dowel_tie`'s own closed-loop
shape (parent spec §9):

- No formula or input existed for how many dowels there are or where they
  sit in plan.
- `FootingInputs` had no symbol/field for the column's own depth
  (b-direction) cross-section dimension.

Essam ruled on both in the 2026-09-24 session — recorded as **R6** and
**R7** in `docs/footing/spec-amendments.md`. This document turns those
rulings into implementable user stories, per ai-kaderskill's To-Spec
phase.

## 1. Reused Components

- **`rft.revit.column_host.read_section_mm` / `read_orientation`**
  (R7) — reused as-is. Already live-host-verified for ColumnRFT (issue
  #87/#69): reads `b`/`h` off the column's TYPE parameters (never the
  bounding box — #69's own 58%-error finding), refuses on a
  non-rectangular section or an untested flip state. No footing-specific
  fork of this module — the SAME function, called against whichever
  column `FamilyInstance` Story 1 below detects.
- **`rft.revit.column_host`'s `ReferenceIntersector` ray-cast pattern**
  (`find_search_view` / `find_support_face_z_mm`) — the TECHNIQUE is
  reused (filtered category ray-cast through a `View3D` chosen by
  behaviour, per that module's own "chosen by behaviour, never by name"
  rule), but the DIRECTION is new: those functions cast a ray from a
  known column to find what's above/below it; Story 1 below casts a ray
  from a known footing to find the column above it. This is new code
  (see §4, Story 1) reusing a proven mechanism, not a call to an existing
  function.
- **`rft.core.column_layout.perimeter_bar_positions`** (R6) — reused
  as-is. Already computes "every longitudinal bar, once, ordered
  around the perimeter" (corner bars shared/de-duplicated between
  faces) for ColumnRFT. Story 3 below calls it with the footing's own
  dowel inputs in place of the column tool's own bar inputs — same
  function, same signature, no footing-specific fork.
- **`rft.revit.column_host.read_cover_mm`** (R7, extended
  2026-09-24) — reused as-is for dowel positioning. Reads
  `CLEAR_COVER_OTHER` ("Rebar Cover - Other Faces") live off the
  detected column's own `RebarCoverType`, per ColumnRFT's own amendment
  A2: "never typed, never defaults to 25" (#80 found Revit silently
  clamping a typed cover to the host's own, so the report and the model
  disagreed). Essam's ruling on this addendum's own draft: use the
  column's own cover, same as everything else about the column's
  cross-section (R7) — so there is no separate typed
  `dowel_column_cover_mm` input (see §2/Story 2).
- **Not reused:** `rft.core.column_ties.resolve_tie` (this addendum does
  not build `dowel_tie`'s own loop shape — that stays the follow-on
  ticket `docs/footing/HANDOVER-2026-09-24.md` item 6 names, now
  unblocked by this addendum but not built by it).

## 2. Naming additions (extends parent spec §2/§3)

| Symbol | Meaning |
|---|---|
| `Cw` | Column width in the a-direction (parent spec already names this; carried here for completeness). |
| `Cd` | Column depth in the b-direction — the symbol parent spec's naming table never gave. Read live off the detected column (`read_section_mm`), never derived by offset math and never typed. |
| `dowel_count_b_face` | Dowel count along the Cw-direction face, corner dowels included — same counting convention `column_layout.perimeter_bar_positions`'s own `count_b_face` already uses. |
| `dowel_count_h_face` | Dowel count along the Cd-direction face, corner dowels included — same convention as `count_h_face`. |
| `Ccover` | Cover from the column's own face to a dowel's centreline, for positioning ONLY (`column_layout.bar_centre_offset_mm`'s `cover_mm` argument). Read live off the detected column via `column_host.read_cover_mm` (`CLEAR_COVER_OTHER`) — **not** a typed `FootingInputs` field, per Essam's ruling on this draft: use the column's own cover, consistent with Cw/Cd also being read live rather than typed. Distinct from the footing's own `cover_mm`/`bottom_cover_mm` — a dowel is positioned inside the COLUMN's cross-section envelope, not the footing's. |

## 3. User Stories

### Story 1 — Auto-detect the column above the footing

> As a BIM engineer, I want the tool to automatically find the column
> sitting on top of the footing I picked, so that I never have to
> separately select it or risk pairing the wrong column with a footing.

- After the footing is picked (same `revit.pick_element` step the tool
  already has), fire an upward ray from the footing's own top-face
  centroid, filtered to `OST_StructuralColumns`, through a `View3D`
  chosen the same "prove it can see the target" way
  `column_host.find_search_view` already does.
- Exactly one column found, rectangular section, no untested flip state
  → proceed to Story 2 with that column.
- **No column found** → refuse immediately: alert "No column is attached
  to this footing," stop before any rebar placement runs. **No manual
  pick/typed fallback** — this is Essam's explicit ruling (R7), not a
  gap left open.
- Non-rectangular or flipped column found → the SAME refusal
  `column_host.read_section_mm`/`read_orientation` already raises for
  ColumnRFT, unchanged.
- Multiple `OST_StructuralColumns` hits along the ray → nearest hit
  governs (`ReferenceIntersector.FindNearest`'s own behaviour) — an
  isolated footing has exactly one column per parent spec's own scope
  (§0), so this is not expected in practice and is not a case this story
  adds special handling for.

### Story 2 — Read Cw/Cd and cover live from the detected column

> As a BIM engineer, I want the footing dowel geometry to use the
> column's real cross-section and its own cover, so that it always
> matches what's actually modelled instead of a value I typed or a value
> derived from footing offsets that happens to agree with it.

- Call `column_host.read_section_mm(column)` /
  `column_host.read_orientation(column)` / `column_host.read_cover_mm(
  column)` against the column Story 1 found. Output: plain
  `Cw_mm`/`Cd_mm`/`Ccover_mm` numbers (the adapter boundary — Revit
  objects never cross into `rft.core`, same split every other
  footing/column module already follows).
- Refuses exactly as `column_host` already does for ColumnRFT for all
  three reads — including `read_cover_mm`'s own refusal when
  `CLEAR_COVER_OTHER` is unset (amendment A2: cover is read from the
  element and never typed, so an unset cover is a hard stop, not a
  25mm-default guess). No new refusal rule invented here.

### Story 3 — Dowel array layout: count per face + corner dowels

> As a BIM engineer, I want to specify the dowel array the same way I
> already specify a column's own longitudinal bar layout — count per
> face, corner bars included — so that dowels land exactly where the
> column bars they continue actually are.

- New `FootingInputs` fields: `dowel_count_b_face`, `dowel_count_h_face`
  only (§2 above) — `Ccover_mm` is NOT a `FootingInputs` field; it flows
  in alongside `Cw_mm`/`Cd_mm` from Story 2's live read (§4 below), same
  reasoning. Opt-in, trailing defaults of `None` for the two count
  fields, same pattern every dowel-related field has used since #202 —
  every caller that predates this addendum keeps building a plan with no
  dowel array unchanged.
- `rft.core.footing_plan` calls `column_layout.perimeter_bar_positions(
  b_mm=Cw_mm, h_mm=Cd_mm, cover_mm=Ccover_mm,
  tie_dia_mm=dowel_tie_dia_mm, bar_dia_mm=dowel_bar_dia_mm,
  count_b_face=dowel_count_b_face, count_h_face=dowel_count_h_face)` to
  get every dowel's footing-local `(u, v)` position, once, corner dowels
  de-duplicated — the same call ColumnRFT already makes for its own
  bars, no new position math written.
- Each position gets its own per-bar embedment/hook geometry from the
  EXISTING #202 math (`footing_dowels.dowel_embedment` /
  `local_dowel_bar_geometry`) — this story changes WHERE dowels are and
  HOW MANY there are, not how any single dowel's own vertical geometry is
  sized.
- `FootingPlan.dowel` (currently one `DowelBarGeometry`) becomes a
  `DowelArrayPlan` carrying `embedment` (unchanged, still one shared
  `DowelEmbedment` — every dowel in the array has identical vertical
  sizing) plus `bars`, a list of `DowelBarGeometry`, one per position —
  per `docs/token-efficient-expansion.md` §7, this is the one composing-
  module shape change both a future report and the placement adapter
  (Story 4) read from, done once, here, before a second consumer exists.

### Story 4 — Place the full dowel array

> As a BIM engineer, I want every dowel bar in the array actually placed
> in the model, not just the one representative bar #202 proved the
> mechanics with, so that the footing's starter bars are complete without
> manual placement.

- Extends `rft.revit.footing_dowels.place_dowel_bar` (currently ONE bent
  `Rebar`) to place one bent `Rebar` per `DowelArrayPlan.bars` entry, in
  the same single transaction the pushbutton script already wraps every
  placement in.
- #202 already proved a bent two-curve bar can be created on a footing
  host as a KEPT write (not just a rolled-back read) — per
  `docs/token-efficient-expansion.md` §8, that covers the WRITE side for
  one bar's shape. An N-bar array is the same shape repeated N times, not
  a new shape, so this story's own tracer bullet only needs to confirm
  the array placement mechanics (looping `Rebar.CreateFromCurves` inside
  one transaction, no cross-bar interference) — not re-prove the bent-bar
  shape itself.

## 4. Data flow

`footing_plan.build_footing_plan` stays the one composing module both a
future report and the placement adapter read from (parent spec §4 /
`docs/token-efficient-expansion.md` §7). `Cw_mm`/`Cd_mm`/`Ccover_mm` are
NOT stored on `FootingInputs` — they are read live (Story 1/2) at the
point the pushbutton script builds the plan and passed in as a single
`column_section` argument alongside `inputs`, the same "adapter reads
Revit, core takes plain numbers" split `REUSE_GUIDELINES.md` §1 already
states. As implemented (#222/#227), the three values are bundled into one
`footing_plan.DowelColumnSection` namedtuple (`Cw_mm`/`Cd_mm`/`Ccover_mm`)
rather than passed as three bare positional floats — found in review
(PR #225/#227): three same-typed, same-unit floats at two call sites
invited a silent width/depth swap that type-checks fine and produces a
silently mirrored array; a keyword-constructed namedtuple does not. This
keeps `rft.core.footing_plan` unit-testable with a plain
`DowelColumnSection` (or `None`), with no Revit object ever required to
exercise the core math. Not named `ColumnSection` — `rft.core.
column_host_rules` already defines its own, differently-shaped
`ColumnSection` for ColumnRFT; reusing that name here would collide the
moment both modules are imported together, which #221 will need to do.

## 5. Verification discipline

Same standing rule as every element in this repo (`CONTEXT.md`): `master`
means the code exists, a tag (`footing/vX.Y.Z`) means it was verified on
a live host. Story 1's ray-cast direction is NEW (§1 above) and needs its
own tracer bullet — a rolled-back read proving the upward ray finds the
right column is sufficient for Story 1/2 (read-only). Story 4's array
placement needs a SEPARATE kept-write tracer bullet per
`docs/token-efficient-expansion.md` §8 — a read-only proof of Story 1
does not cover Story 4's write behaviour.

## 6. Suggested Implementation Order — Tracer Bullet

1. Story 1 — column auto-detection ray-cast (read-only tracer bullet:
   prove the upward ray finds the right column against a live host,
   rolled back).
2. Story 2 — `Cw`/`Cd` live read (depends on Story 1's detected column;
   reuses already-verified `column_host` functions, so no new
   verification needed beyond Story 1's own).
3. Story 3 — dowel array core math (pure core, no Revit dependency; can
   be built and unit-tested in parallel with 1/2 using plain
   `(Cw_mm, Cd_mm)` test fixtures, per §4 above).
4. Story 4 — dowel array placement (depends on 1-3 for an end-to-end run;
   own kept-write tracer bullet, per §5).

Not in this addendum, explicitly deferred to the follow-on ticket
`docs/footing/HANDOVER-2026-09-24.md` item 6 already names:
`dowel_tie`'s own closed-loop shape and placement, now unblocked (a real
dowel-bar array exists after Story 3/4) but not built here.
