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
| R4 | §6.2 — is tie topology auto-derived or user-selected? | **User-selected** from a Figure 13-3 template library; §6.1 is a **validator**, not a generator. §6.1 admits many valid coverings of the same layout and the spec has no tie-break rule — auto-deriving would mean inventing one. No template covering the layout ⇒ explicit refusal, never a nearest-match fallback. | #71 |
| R5 | §0/C1 — what happens to a column with no footing below it? | **Detail it normally.** A missing footing is a modelling artifact. The bar starts at the base level, runs the clear height, and protrudes `L_s` above the **top** support only. **There is no bottom `L_s`** — `L_s` is a top-end quantity. No base treatment is produced. | #73 |
| R6 | §11/#69 left open — what is the base datum when the base search finds nothing? | The **base level elevation** plus its offset ("start at ground level"), *not* a support face. The top end still uses the support-face search. Two datum paths at the base; an absent base support is never an error. | #73 |
| R7 | §7 — which steel grade for ties vs main bars? | **Ties (outer and inner): mild steel**, St 24/35 plain round. **Main bars: high tensile**, St 36/52 deformed. Identical to the beam tool's mapping, so `rft.core.grades`' role→grade mechanism transfers unchanged. | #74 |
| R8 | §6.3 — diagonal (180°) or adjacent hook corner? | **Adjacent is required**; the spec's NE → NW example is the rule, not an illustration. Consequence: no *rotation* can produce it on a rectangular tie, so a **mirror** must be investigated before any placer work. | #70 → #78 |
| R9 | §6.3 — is an adjacent corner actually buildable? | **Yes, no amendment needed.** `MoveBarInSet` accepts a **reflection** and stores it (`Determinant = -1`, `HasReflection` preserved). Mirror plane normal = `HandOrientation` through the tie centre gives `SW → SE` — adjacent — on **one** rebar set, `Quantity` intact. The mirrored 135° hook stays geometrically correct: its tail remains inside the core. | #78 |
| R10 | §7 — which `RebarHookOrientation` for a tie? | **`Left`**, derived from the loop's winding rather than hardcoded. `Right` bends the 135° hook **out of the core** — free end 91 mm beyond the tie, in cover and air. Found while proving R9; it invalidates the hook *coordinates* (not the conclusions) in #70's write-up. | #78 |
| R11 | §6.2 — do overlapping closed subset ties actually work? | **Yes.** An inner tie wrapping the 4 intermediate bars was created alongside the outer perimeter tie: **2 `Rebar` elements, one per tie definition**, each independently reflectable for §6.3 (`Determinant = -1`), hook still inside its own loop. Output contract is therefore a **list** of `(subset → rectangle, layout, rotation map)` — not one privileged "main tie" plus extras. Note both ties **share one `RebarShape`** (same shape code, different dimensions), so tie ROLE cannot be read back from `GetShapeId()`. | Q9 |
| R12 | §0/C2 — multi-storey columns. | **Refuse.** Both a single element spanning several storeys *and* a multi-select of columns. Detection (verified live): count levels whose elevation lies **strictly between** the column's base and top — zero ⇒ single storey. The refusal names the intervening levels. | #73 |
| R13 | §0/C3 — non-rectangular sections. | **Refuse.** Detection (verified live): the solid has **exactly four vertical planar faces** with normals in two antiparallel perpendicular pairs. Deliberately **family-agnostic** — it does not read the `b`/`h` type parameters, whose names #69 flagged as family-specific. A circular section yields a `CylindricalFace`; an L-shape yields six vertical planar faces. | #73 |

## Open questions raised by implementation work

These are **not** amendments — they are questions the spec does not currently
answer, raised rather than guessed. Each must be answered by the owner before
the affected code is written.

| # | Section | Question | Status |
|---|---|---|---|
| Q1 | §6.2 | Tie topology: auto-derived, or user-picked from templates? | **CLOSED** → R4 (#71) |
| Q2 | §6.3 | Diagonal (180°) or adjacent hook corner? | **CLOSED** → R8 (adjacent required, #70) and R9 (proven buildable, #78) |
| Q3 | §0 | What the tool DOES with an out-of-scope column. | **CLOSED** → R5/R6 (C1), R12 (C2), R13 (C3) — #73 |
| Q4 | §7 | Tie bar steel grade vs the 135° hook default. | **CLOSED** → R7 (#74) |
| Q5 | §1 | Cover must be an editable input. The test column's `Rebar Cover - Top Face` was **unset** (`-1`), so a per-face read cannot assume all three cover parameters resolve. | open (#69) |
| Q6 | §9 | **Roof / top-storey column.** §9 protrudes `L_s` above the top support "to connect with the next story" — a roof column has none, so bars would project out of the slab. The closure rule at the roof slab is undefined. | open, **deferred by owner** (#77) |
| Q7 | §6.3 | Can `MoveBarInSet` accept a **reflection**, and is a **mirrored 135° hook** legal? | **CLOSED** → R9/R10 (#78) |
| Q8 | §6.3 | Only the `hand`-normal mirror plane (SW→SE) was tested. Mirroring about the `face` normal (SW→NW) is the other adjacent move, untested. Should alternation use one plane throughout, or alternate between both across four levels? §6.3 requires only "a different corner" each level, so the spec does not decide this. | open |
| Q9 | §6.2 | Every tie experiment so far used the **outer perimeter** tie only. No inner subset tie had ever been created. | **CLOSED** → R11 |

### Inherited, consciously

R7 places column ties on **mild steel** while §7 defaults both hook dropdowns
to **135°** — exactly the combination beam issue #32 flags (135° is the
deformed-bar convention). The column tool does not resolve #32; it lands on
the same side of it as the beam tool, by decision. Whatever #32 rules should
therefore be applied to **both** elements.

## Known defect risks recorded against the spec's rules

| Risk | Rule at stake | Mitigation required |
|---|---|---|
| Per-bar transforms are keyed on **bar position index**, and Revit does **not** re-map them when the layout changes. After a spacing edit the alternation silently became `F,T,T,F,T,F` — bars 1 and 2 both rotated, bar 3 not. Nothing throws. | §6.3 | Apply transforms only **after** the final layout; reset and re-apply the whole rotation map on **any** layout change; prove the ordering with a mutation-provable AST guard. (#70) |
