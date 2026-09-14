# Column spec — amendment ledger

The column tool's **own** ledger. Per `docs/reuse-for-new-elements.md` §4, a new
element starts its own ledger and does **not** extend the beam's
(`docs/beam/spec-amendments.md`). Amendment numbers here are independent of the
beam's `A1..A49`; a bare "A3" in a column module means *this* file's A3.

Why this exists: it is what makes a spec disagreement resolvable six months
later instead of re-litigated. Every row names what changed, why, and which
issue decided it.

## Status

`specs/column-rft-detailing.md` is **LOCKED at v1**. No amendments have been
issued yet — the Wayfinder cycle resolved decisions *about* the spec (packaging,
API mechanics, reuse) without changing the spec text.

## Amendments

| # | Section | Change | Decided by |
|---|---|---|---|
| — | — | *(none yet)* | — |

## Resolutions — questions answered without changing the spec

| # | Question | Resolution | Issue |
|---|---|---|---|
| R1 | §11 tracer bullet — how is a column's `a`/`b` orientation read? | `b` lies along `HandOrientation`, `h` along `FacingOrientation`; dimensions from the type parameters. The bounding box is **unusable** (712.8 × 749.6 for a 450 × 600 column at 35°). | #69 |
| R2 | §11 — how is the support face found at each end? | `ReferenceIntersector` against a non-template `View3D`. The ray origin **must be outside** the target solid, and the ray direction selects which face is returned. `INSTANCE_LENGTH_PARAM` is **not** `Hc` — it reported 3000 mm where the clear height was 2700 mm. | #69 |
| R3 | §6.3 — is per-level hook rotation one rebar set or N elements? | **One set.** `Rebar.MoveBarInSet(i, Transform)` stores a rotation, not just a translation. Measured 1 element / 111 ms against 25 elements / 828 ms. | #70 |

## Open questions raised by implementation work

These are **not** amendments — they are questions the spec does not currently
answer, raised rather than guessed. Each must be answered by the owner before
the affected code is written.

| # | Section | Question | Status |
|---|---|---|---|
| Q1 | §6.2 | Tie topology: auto-derived from §6.1's tiers, or user-picked from Figure 13-3 templates? | open — deferred by the spec itself, now live (#71) |
| Q2 | §6.3 | The rule's example is NE → N**W**, an **adjacent** corner. A 180° rotation gives the **diagonal** corner (NE → SW). No rotation can give an adjacent corner on a *rectangular* tie — that needs a mirror, which is untested and may be illegal for a chiral 135° hook. Is diagonal alternation acceptable? | open (#70) |
| Q3 | §0 | What the tool DOES when handed an out-of-scope column (C1 dowels / C2 stack / C3 non-rectangular). The spec says what is not built, not what happens. | open (#73) |
| Q4 | §7 | Tie bar steel grade vs the 135° hook default — deformed or mild steel, and do outer and inner ties get different defaults? | open (#74) |
| Q5 | §1 | Cover must be an editable input. The test column's `Rebar Cover - Top Face` was **unset** (`-1`), so a per-face read cannot assume all three cover parameters resolve. | open (#69) |

## Known defect risks recorded against the spec's rules

| Risk | Rule at stake | Mitigation required |
|---|---|---|
| Per-bar transforms are keyed on **bar position index**, and Revit does **not** re-map them when the layout changes. After a spacing edit the alternation silently became `F,T,T,F,T,F` — bars 1 and 2 both rotated, bar 3 not. Nothing throws. | §6.3 | Apply transforms only **after** the final layout; reset and re-apply the whole rotation map on **any** layout change; prove the ordering with a mutation-provable AST guard. (#70) |
