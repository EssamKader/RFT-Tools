# Isolated Footing spec — amendment / ruling ledger

Per `docs/reuse-for-new-elements.md` §4.2: a new element starts its own
ledger; it does not extend the beam tool's. This is the footing tool's.

Format follows the beam/column convention: each entry names what changed,
why, and which issue/ticket decided it.

---

## R1 — X == Y tie-break: defaults to Primary in the X direction

**Spec Ref:** `specs/isolated-footing.md` §2/§3. The rule as written is
only "if X > Y ⇒ Primary Reinforcement in X direction" — it never states
what happens when the two column-face offsets are exactly equal.

**Found by:** ticket #198's implementation
(`rft.core.footing_mesh.primary_reinforcement_direction`), which refused
(`FootingDirectionTieError`) rather than guess, per REUSE_GUIDELINES.md
§3's "Explicit Refusals" rule — recorded in `IsolatedFooting.extension/
CONTEXT.md` and raised to the project owner rather than resolved inline.

**Ruling (Essam, 2026-09-19):** "if x=y it does not matter what direction
is the primary." When `x_offset_mm == y_offset_mm`, `primary_
reinforcement_direction` now returns `DIRECTION_X` — an arbitrary but
fixed default, not a guess, since the project owner confirmed the choice
has no structural consequence in the tie case.

**Why this doesn't need to touch anything else:** every downstream formula
(mesh lengths in §4, the hook/development-length decision in §5, U-shape/
L-shape in §6, TOP+BTM in §7) treats Primary/Secondary as a per-mesh
label, never as a value that changes which formula applies — so a fixed
default for the tie case is sufficient and does not require a special case
anywhere else in the tool.

---

## R2 — LD == offset tie-break: refuse, and route to the existing U/L choice

**Spec Ref:** `specs/isolated-footing.md` §5. The rule as written defines
only `LD > offset` (hook) and `offset > LD` (no hook, switch to L-shape)
— it never states what happens when the required development length
exactly equals the available straight offset at a bar end.

**Found by:** ticket #199's implementation
(`rft.core.footing_mesh.bar_end_hook_decision`), which refused
(`HookDevelopmentLengthTieError`) rather than guess, per
REUSE_GUIDELINES.md §3's "Explicit Refusals" rule — recorded in
`IsolatedFooting.extension/CONTEXT.md` and raised to the project owner
rather than resolved inline.

**First ruling (Essam, 2026-09-20):** "for this it does not matter, ld
depend on bar size." Implemented as a silent default to `needs_hook=True`.

**Revised ruling (Essam, 2026-09-20, same day):** "maybe shall have two
options available for engineer to choose from whether u shape or alter
l." This supersedes the silent default: `bar_end_hook_decision` keeps
raising `HookDevelopmentLengthTieError` on the exact tie, and the
resolution is not a new mechanism — it is the SAME per-mat U-shape/
L-shape-alternating choice ticket #200 already built
(`bar_hook_plan_for_mat` with an explicit `mat_shape_mode`, which never
calls `bar_end_hook_decision` at all). The engineer facing this exact tie
sets that mat's shape explicitly instead of leaving it on automatic.

**Why this doesn't need to touch anything else:** #200's per-mat override
already exists and already bypasses this comparison entirely, so nothing
new was built to satisfy the revised ruling — only the automatic
(`mat_shape_mode=None`) path's refusal message was updated to point the
engineer at the override that already answers the question.

---

## R3 — Top mat vertical convention: mirrors the bottom mat from the top face

**Spec Ref:** `specs/isolated-footing.md` §7 (Story 4). The spec names the
BTM-only / TOP+BTM toggle but gives no explicit top-mat vertical-position
formula, unlike §4's `N`/`N2` for the bottom mat's own two-layer stack.

**Found by:** ticket #201's Phase 8 review (PR #214) — the first version
of that ticket reused `local_mesh_bar_endpoints` (measured from
`bottom_cover_mm` upward) unchanged for the top mat, which placed the
"top mat" at the exact same elevation as the bottom mat. Fixed with a new
`footing_mesh.local_top_mesh_bar_endpoints`, proposed as a mirrored
convention rather than assumed silently, and raised to the project owner
for confirmation before it could be treated as decided.

**Ruling (Essam, 2026-09-20):** confirmed correct — "yes this is right."
The top mat's first bar layer sits just below the top cover; its second
layer is stacked one bar-diameter further down into the footing,
mirroring exactly how the bottom mat's two layers stack upward from the
bottom cover. `footing_mesh.local_top_mesh_bar_endpoints` implements this
as confirmed, not merely proposed, as of this ruling.

**Why this doesn't need to touch anything else:** the mesh-length,
direction and hook-decision formulas (`mesh_bar_lengths`,
`primary_reinforcement_direction`, `bar_hook_plan_for_mat`) are already
identical for both mats per spec §4-§6, which cite no bottom/top
distinction — only the Z-elevation step (`_bottom_mat_endpoints` /
`_top_mat_endpoints` in `footing_plan.py`) ever needed to differ, and it
already does.

---

## R4 — `perimeter_tie` vertical starting offset: 250mm above the bottom mesh

**Spec Ref:** `specs/isolated-footing.md` §10. The rule as written states
diameter, spacing and quantity are direct user inputs and gives "one loop
every 200mm vertically" only as an EXAMPLE — it never states where the
first (or only) `perimeter_tie` loop sits vertically, unlike §9's
explicit "50mm from the bottom of the footing" for `dowel_tie`.

**Found by:** ticket #204's implementation
(`rft.core.footing_perimeter_tie`), which built the loop's plan geometry
(footing-local X/Y corners) but deliberately left the Z-elevation
unresolved rather than guess, per REUSE_GUIDELINES.md §3's "Explicit
Refusals" rule — recorded in `IsolatedFooting.extension/CONTEXT.md` and
raised to the project owner.

**Ruling (Essam, 2026-09-20):** the first `perimeter_tie` sits 250mm
above the bottom mesh. Read as 250mm above the SAME "top of the bottom
mesh" datum `rft.core.footing_dowels`'s own bend-corner elevation already
uses (`bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm` —
the top face of `mesh_bar_y`, the higher of the bottom mat's two bar
layers) — proposed as the most natural reading of "above the bottom
mesh" given that datum already exists in this codebase for exactly this
purpose, not an independent guess. Every subsequent `perimeter_tie` (up
to the user's own `quantity`) steps upward from there at the user's own
`spacing_mm` — Sec 10 already states spacing/quantity are direct user
inputs, so only the STARTING point was the open question.

**Why this doesn't need to touch anything else:** the loop's own plan
geometry (`local_perimeter_tie_corners_mm`) is identical at every level —
only the Z each level sits at changes, matching how R3's top-mat fix only
ever needed to change the Z-elevation step, never the plan geometry.

---

## R5 — `perimeter_tie` splice cut-length split: a direct two-field engineer input, no formula

**Spec Ref:** `specs/isolated-footing.md` §10. The rule as written says a
loop over the 12m stock length is "split into two bars, overlapped by lap
length `Ls` at the joint" — it never states how the total length (the
loop's own length plus one `Ls`) divides between the two individual
bars' own cut lengths.

**Found by:** ticket #204's implementation
(`rft.core.footing_perimeter_tie.perimeter_tie_splice`), which computes
the bar-count decision (1 or 2) and the total steel length to cut, but
refused to invent a 50/50 (or any other) split rule — recorded in that
module's own docstring ("The splice's own open question") and raised to
the project owner.

**Ruling (Essam, 2026-09-20):** not a formula — the engineer fills in the
two individual bar lengths directly (e.g. a 13m total could be entered as
8m + 5m, or 7m + 6m, or any other split the engineer picks on site). The
tool's job is to report the TOTAL length needing to be cut (already
computed by `perimeter_tie_splice`) and then accept the engineer's own
two lengths, refusing if they don't add up to that total — the same
"accept the input, validate it, don't derive it" shape `dowel_tie_dia_mm`/
`dowel_tie_spacing_mm` already have (direct inputs, no default), just
with an added consistency check since these two specifically must sum to
a value the tool already knows.

**Why this doesn't need to touch anything else:** `perimeter_tie_length_mm`
and the bar-count/total-length decision in `perimeter_tie_splice` are
unchanged — this ruling only adds a validation step consuming that
existing total, it does not change how the total itself is computed.

---

## R6 — Dowel array layout: mirrors the column's own longitudinal bar layout

**Spec Ref:** `specs/isolated-footing.md` §8 (Story 5). The rule as
written sizes ONE `dowel_bar`'s embedment/hook, and #202 places exactly
one representative dowel — the spec never states how many dowels exist or
where they sit in plan, only that `dowel_bar` IS "the column vertical
starter bar."

**Found by:** the handover from the 2026-09-24 session
(`docs/footing/HANDOVER-2026-09-24.md` item 5) — this is one of the two
prerequisites blocking `dowel_tie`'s own closed-loop shape (§9), flagged
as an architectural gap (no data to guess with) rather than a single
ambiguous value, per `REUSE_GUIDELINES.md` §3's "Explicit Refusals" rule.

**Ruling (Essam, 2026-09-24):** the dowel array is not an independent
count/spacing input. It mirrors ColumnRFT's own longitudinal bar layout
model exactly (`specs/column-rft-detailing.md` §2 — bar count per face
plus corner bars, one continuous perimeter arrangement), because each
`dowel_bar` IS the continuation of a real column vertical bar below the
splice, not a separately-invented array. `FootingInputs` gains fields
matching ColumnRFT's own layout inputs; a dowel is positioned at the same
perimeter location its corresponding column bar occupies.

**Why this doesn't need to touch anything else:** the per-bar embedment/
hook math `footing_dowels.dowel_embedment`/`local_dowel_bar_geometry`
already builds (#202) is unchanged — this ruling only decides HOW MANY
dowels exist and WHERE in plan, not how any single dowel's own vertical
geometry is sized.

---

## R7 — Column cross-section (Cw/Cd) source: read live from the column, reusing `column_host`

**Spec Ref:** `specs/isolated-footing.md` §2/§3. The naming table gives a
symbol (`Cw`) for the column's width in the a-direction only — it never
names the column's depth (b-direction) dimension, and `FootingInputs`
deliberately never stores `Cw` either (`footing_plan.py`'s own comment:
`x_offset_mm`/`y_offset_mm` are supplied directly "rather than derived
from a/b/Cw").

**Found by:** the same handover gap as R6 — the second of the two
`dowel_tie` prerequisites, since a real tie rectangle needs the column's
own b-direction cross-section width, which nothing in `FootingInputs`
carries today.

**Ruling (Essam, 2026-09-24):** not derived by offset math
(`Cd = b_mm - 2*y_offset_mm`) and not a new typed field — "each column is
defined by two dimensions a and b" read from Revit itself. `Cw`/`Cd` are
sourced live by reusing `rft.revit.column_host.read_section_mm`/
`read_orientation` as-is (the same live-host-verified, rotation-safe
adapter ColumnRFT already uses — issue #87/#69), against the actual
column `FamilyInstance` above the footing. This refuses on a
non-rectangular or flipped column exactly as `column_host` already does
for ColumnRFT — no separate refusal rule invented here.

**Ruling (Essam, 2026-09-24) — column is auto-detected, not picked:**
the footing tool does not ask the engineer to separately pick the column.
It auto-detects the column sitting on top of the picked footing, the same
`ReferenceIntersector` ray-cast technique `column_host.find_search_view`/
`find_support_face_z_mm` already use to find what's above/below a column
(live-host-proven in that direction), run in reverse — a ray fired upward
from the footing's own top face, filtered to `OST_StructuralColumns`. This
exact direction (footing -> column above) is a NEW use of a proven
technique, not proven itself yet, so it needs its own tracer-bullet
verification before it ships (same discipline as every other footing
feature, spec §5). If no column is found (or the column found is
non-rectangular/flipped), the tool refuses with a clear message ("no
column is attached to this footing") before any rebar placement runs —
**no manual pick/typed fallback**.

**Why this doesn't need to touch anything else:** every existing formula
that already reads `mesh_bar_x_dia_mm`/`mesh_bar_y_dia_mm`/`footing_
thickness_mm`/etc. off `FootingInputs` is unchanged — `Cw`/`Cd` are new
data flowing in from a new adapter, consumed only by the new dowel-array
placement logic (R6), not by any mesh/tie math that predates this
ruling.

**Extended during To-Spec (Essam, 2026-09-24, same day):** the To-Spec
draft (`specs/isolated-footing-dowel-array.md`) initially proposed a new
typed `FootingInputs` field for the cover used to position dowels within
the column's own cross-section, since that cover is conceptually distinct
from the footing's own `cover_mm`/`bottom_cover_mm`. Flagged rather than
assumed. **Ruling:** "for this use column cover for sure" — same
treatment as `Cw`/`Cd`, read live off the detected column by reusing
`rft.revit.column_host.read_cover_mm` (`CLEAR_COVER_OTHER`, already
live-host-verified for ColumnRFT's own amendment A2: cover is read from
the element and never typed, since #80 found Revit silently clamping a
typed cover to the host's own). No new `FootingInputs` field for this —
one more value that flows in live alongside `Cw`/`Cd`, not a fourth
typed input.
