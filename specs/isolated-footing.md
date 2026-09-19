# Isolated Footing RFT Detailing Spec

> **Status: LOCKED** — scope, detailing rules, and formulas are final. This
> document authorizes the tracer-bullet order in §11. No core module code or
> UI work is started by this document.
>
> **Conversion note:** this markdown is the citable form of
> `IsolatedFooting/IsolatedFootingRFT-Spec_V2.docx`. **Provenance:** the source
> `.docx`'s own header text still reads *"v1 — Wayfinder Complete"* — that is
> a label left over from an earlier draft cycle and was not updated when the
> file was superseded and renamed to `_V2`. This document is the current,
> single spec; it does not carry a v1/V2 distinction forward, because there is
> only one live spec, not two versions in parallel. If the `.docx` is ever
> revised again, that revision replaces this file wholesale rather than being
> reconciled section-by-section against a stale header label. Section
> numbering is preserved exactly so that a `# Spec Ref: §9` in code resolves
> against either.

Companion to `beam-rft-detailing.md` and `column-rft-detailing.md`. Same
discipline: every rule cites its source section, every open question is
answered in writing, every reuse decision is stated rather than re-derived.

---

## 0. Scope

**In scope:** detailing the reinforcement of **one isolated (pad) footing** —
bottom mesh, optional top mesh, column dowels (vertical starter bars), dowel
stirrups (ties), and the footing-perimeter tie bar — for a single rectangular
footing of user-input plan dimensions `a × b` under one rectangular column.

**Out of scope, explicitly** (named as cut now, not "later"):

- **F1 — Multi-footing / batch placement.** §11 item 7 names this as the last
  tracer-bullet step and it stays there: this spec details exactly one
  footing per run. Batch support is a future ticket, not part of this pass.
- **F2 — Non-rectangular footings.** Circular or combined/strap footings are
  out of scope.
- **F3 — Column-side detailing.** The column's own vertical bars above the
  splice, its own ties above T.O.F., and its own anchorage/spacing logic
  belong to `ColumnRFT` (`specs/column-rft-detailing.md`). This tool's top
  boundary is "hands off at 50mm below Top of Footing" (§9) — it never
  details anything the column tool already owns.
- **F4 — Non-rectangular / non-orthogonal footing-to-column offset cases.**
  The `a = 2·X + Cw` symmetric-offset model (§3) is the only geometry modeled;
  an off-center column is not covered.

## 1. Reused Components (§2)

Per the spec's own §2 and §9, and treated here as a decided reuse, not a
fresh audit:

- **`dowel_tie` (§9)** reuses ColumnRFT's existing tie/stirrup geometry logic
  — `RFT.lib/rft/core/column_ties.py` + `RFT.lib/rft/core/column_tie_levels.py`
  for shape/level generation, `RFT.lib/rft/revit/column_place_ties.py` for the
  placement pattern.
- **`perimeter_tie` (§10)** is a plain closed rectangular loop
  (`2·(inner_a + inner_b)`), the same shape ColumnRFT's outer tie already
  generates — it reuses the same closed-loop geometry primitive as
  `dowel_tie`, not a new shape module.
- This reuse conclusion will be recorded as a table in
  `docs/footing/reuse-audit.md` (per `docs/token-efficient-expansion.md` §1)
  before any placement code is written, so a later element reads that table
  instead of re-deriving this conclusion from source.
- **Not reused, by construction:** `rft.core.anchorage` (footing bar ends are
  governed by the hook/development-length rule in §5, not a
  supported/unsupported end condition) and the beam's `FacePlan`/`LayerPlan`
  model in `rft.core.layout` (a footing mesh is not a beam face).

## 2. Naming & Geometry Conventions (§3)

| Symbol | Meaning |
|---|---|
| `a`, `b` | Footing plan dimensions (`a` along X, `b` along Y). |
| `Cw` | Column width in the `a`-direction. |
| `X`, `Y` | Clear offset, column face → footing edge, in the a- and b-direction respectively. `a = 2·X + Cw`. |
| `cover` | Footing cover (top/bottom, per face). |
| `Z` | `a − 2·cover` — straight length of an a-direction bottom bar. |
| `N` | `footing_thickness − bottom_cover − top_cover` — vertical hook leg of the first (lowest) mat. |
| `N2` | `footing_thickness − bottom_cover − ⌀(first mat bar) − top_cover` — hook leg of the mat stacked above the first one. |
| `LD` | Required development/lap length = `multiplier × db`; multiplier is user input or code-table lookup. |
| Primary Reinforcement | The bar direction with the larger offset/overhang beyond the column face (`X` or `Y`) — sits lowest within whichever mesh it's in. |
| Secondary Reinforcement | The other direction — stacked above Primary Reinforcement, within the same mesh. |
| `mesh_bar_x` | Bottom-mesh bars spanning the a-direction. |
| `mesh_bar_y` | Bottom-mesh bars spanning the b-direction, stacked above `mesh_bar_x`. |

**Direction rule:** `if X > Y ⇒ Primary Reinforcement in X direction` — whichever
column-face offset is larger, that direction's bars become Primary.

**Primary/Secondary is per-mesh, not global.** The bottom mesh has its own
Primary(Bottom)/Secondary(Bottom) pair; if TOP + BTM (§7) is chosen, the top
mesh has its own Primary(Top)/Secondary(Top) pair. The same X-vs-Y comparison
decides the Primary direction identically for both meshes, since it is based
on the fixed column offsets, not on which mesh it is.

## 3. User Stories

### Story 1 — Bottom mesh bar lengths (§4)

> As a BIM engineer, I want the tool to compute `mesh_bar_x` and `mesh_bar_y`
> straight and hook-leg lengths automatically from the footing and cover
> inputs, so that I never have to hand-calculate mesh bar lengths per footing.

- `Z = a − 2·cover`; `Z2 = b − 2·cover`
- `N = footing_thickness − bottom_cover − top_cover`
- `N2 = footing_thickness − bottom_cover − ⌀mesh_bar_x − top_cover`
- `mesh_bar_x = Z + 2·N`; `mesh_bar_y = Z2 + 2·N2`
- Both bars are L-shaped at each end by default (a U in elevation), unless
  the L-shape-alternating option (Story 3 / §6) is chosen.

### Story 2 — Hook / development-length decision per bar end (§5)

> As a BIM engineer, I want the tool to decide per bar end whether a hook is
> needed (and whether the bar switches from U-shape to L-shape) by comparing
> available straight length to the required development length, so that I
> never place an under-anchored bar or over-hook one that didn't need it.

At each bar end, compare the straight length available outside the column
footprint (`X` for a-direction bars, `Y` for b-direction bars, per-end,
per-direction) against `LD`:

- `LD > offset` → bend the bar up (hook) to add embedment via the vertical
  leg; total anchorage = straight offset + hook.
- `offset > LD` → switch that bar from U-shape to L-shape — hook only the
  end(s) where `LD > offset` still applies; the end where `offset > LD`
  stays straight (no hook needed there).

`LD` here (as in §8) is never a flat length: `LD = multiplier × db`, where
`db` is the diameter of the bar being checked and the multiplier is a user
input or code-table lookup.

### Story 3 — U-shape vs. L-shape-alternating, set separately per mat (§6)

> As a BIM engineer, I want to directly choose U-shape or L-shape-alternating
> for the bottom mat and, independently, for the top mat, so that I can trade
> steel quantity for anchorage margin per mat without the tool guessing.

- **U-Shape** — every bar hooked at both ends. Safe default, more steel.
- **L-Shape Alternative** — each bar is L-shaped (one hook); consecutive bars
  alternate which end is hooked, so the mat is anchored at both edges
  overall with less steel than full U-shape.
- This is a direct user input, never a calculated result, and it is set
  independently for the bottom mat and the top mat.
- Whichever the user picks for a given mat **overrides** Story 2's per-end
  `LD` comparison for that mat. Story 2's comparison only applies if/when the
  tool needs to decide the shape itself — this input makes that unnecessary.

### Story 4 — Top reinforcement option (§7)

> As a BIM engineer, I want to explicitly choose BTM-only or TOP+BTM rather
> than have the tool infer top steel from footing thickness, so that the
> decision is always mine and never a silent guess.

- Options: **BTM only** / **TOP + BTM**.
- If TOP + BTM is chosen, the top mat uses the same U-shape/L-shape choice
  (Story 3), closing top+bottom L-bars into a loop at the edge as an
  alternative to full U-shape bars top and bottom.
- Independent of Story 3: the BTM-only/TOP+BTM toggle and the U-shape/
  L-shape toggle are set separately, never coupled.

### Story 5 — Column dowels / vertical starter bars (§8)

> As a BIM engineer, I want the tool to size dowel embedment and hook leg
> automatically from the footing thickness, cover, and mesh bar diameters,
> upgrading the hook only when required development length demands it, so
> that dowels are neither under-anchored nor unnecessarily long.

- `Ls` = lap/splice length — user input.
- `dowel_bar` = column vertical starter bar, tied by `dowel_tie` (Story 6),
  hooked horizontally at the bottom, resting on top of the bottom mesh.
- Embedment inside the footing = `a_dowel + b_dowel`:
  - `a_dowel = footing_thickness − bottom_cover − ⌀mesh_bar_x − ⌀mesh_bar_y`
  - `b_dowel = 200 mm` (default)
- `LD` (dowel development length) = user input, e.g. `55·db` or `60·db`
  (`db` = dowel bar diameter). Compare `LD` to `(a_dowel + b_dowel)`:
  - `LD ≤ a_dowel + b_dowel` → keep `a_dowel` and default `b_dowel = 200mm`.
  - `LD > a_dowel + b_dowel` → increase the hook: `b_dowel = LD − a_dowel`.

### Story 6 — Dowel stirrups / ties (§9)

> As a BIM engineer, I want dowel ties placed automatically at the correct
> starter/end offsets using the same tie geometry logic already proven for
> ColumnRFT, so that dowel confinement is consistent with the column tool and
> I don't re-specify tie shape generation from scratch.

- `dowel_tie` ties the `dowel_bar`s together. **Reuses ColumnRFT's tie/
  stirrup geometry logic** (§1 above).
- Starter (first) `dowel_tie`: 50mm from the bottom of the footing.
- End (last) `dowel_tie`: 50mm below Top of Footing (T.O.F.) — inside the
  footing depth. No `dowel_tie` is placed above T.O.F.; the column's own
  ties take over there (this is the F3 boundary in §0).
- Tie diameter and spacing are both direct user inputs, with **no default**
  — matches the wall-automation/column-tool pattern of never hardcoding
  rebar sizes.

### Story 7 — Footing-perimeter tie bar (§10)

> As a BIM engineer, I want a perimeter tie bar automatically sized and
> spliced around the footing's own edge to bundle the mesh bars together on
> large footings, so that oversized footings get a binding bar without me
> manually computing perimeter length or where to split it.

- `perimeter_tie` is separate from `dowel_tie` — it wraps the footing's own
  perimeter, bundling/holding `mesh_bar_x`/`mesh_bar_y` (top and/or bottom)
  together. It is a **binding element, not a structural one**.
- Geometry — closed rectangle, offset inward from all four faces by `cover`:
  - `inner_a = a − 2·cover`; `inner_b = b − 2·cover`
  - `perimeter_tie_length = 2·(inner_a + inner_b)`
- Splice rule (12m stock length, **hardcoded**, not user input):
  - `perimeter_tie_length ≤ 12m` → one continuous bar.
  - `perimeter_tie_length > 12m` → split into two bars, overlapped by lap
    length `Ls` at the joint. Because `perimeter_tie` is strictly a binding
    element (no direct tensile/compressive demand), the splice may be placed
    anywhere along the perimeter — no restricted zone.
- Diameter, spacing, and quantity of `perimeter_tie` are all direct user
  inputs — same pattern as beam side-face/crack reinforcement (e.g. one
  `perimeter_tie` loop every 200mm vertically up the footing thickness).

## 4. Data flow (per `docs/token-efficient-expansion.md` §7)

Before both a report/preview module and placement code independently call
`column_ties`/`column_tie_levels`/the mesh-length formulas above, a single
composing module (`footing_plan.py`-equivalent) must exist as the one object
both consumers read from — built as part of the first ticket that needs it,
not retrofitted after two independent call sites already exist. This mirrors
the beam tool's `ZONE_LAYOUT_FLAGS` drift bug and the column tool's stated
intent to avoid repeating it.

## 5. Verification discipline

Same standing rule as every element in this repo (`CONTEXT.md`): `master`
means the code exists, a tag (`footing/vX.Y.Z`) means it was verified on a
live host. Any Revit-API-dependent logic in Stories 5–7 (dowel placement,
tie placement, host behavior for rebar-on-footing) is gated on the §11
tracer bullet below, and per `docs/token-efficient-expansion.md` §8, that
tracer bullet must prove a **kept write** (a `Rebar` element actually placed
and left in the model), not only a rolled-back read — a read-only proof does
not cover write behavior.

## 6. Suggested Implementation Order — Tracer Bullet (§11)

Followed as-is from the spec; not re-derived:

1. Tracer bullet: place one isolated footing + column dowels against a live
   Revit host over MCP; verify rebar-on-footing-host API behavior (kept
   write, per §5 above).
2. Bottom mesh, straight case only (no hooks), single footing.
3. Add hook/development-length logic (Story 2 / §5), U-shape default.
4. Add L-shape-alternating option (Story 3 / §6).
5. Add TOP + BTM option (Story 4 / §7).
6. Column dowels + embedment logic (Story 5 / §8).
7. Wire in ColumnRFT's stirrup/tie logic for dowel stirrups (Story 6 / §9).
8. Perimeter tie bar (Story 7 / §10) — not explicitly numbered in the
   source §11 list, but has no upstream dependency beyond mesh geometry
   (step 2), so it is sequenced after step 2 in To-Tickets, before batch.
9. Multi-footing / batch support — **out of scope for this pass** (F1, §0).
