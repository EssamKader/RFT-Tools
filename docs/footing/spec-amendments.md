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
