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
