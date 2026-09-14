# Column RFT Detailing Spec (v1 — Single Floor-to-Floor Segment)

> **Status: LOCKED** — scope, detailing rules, and citations are final. This
> document authorizes exactly one next step: the API tracer bullet in §11. No
> core module code or UI work is started by this document.
>
> **Conversion note:** this markdown is the citable form of
> `technical-material/column/column-rft-detailing-spec.docx`, which remains the
> signed original. Section numbering is preserved exactly so that a `# Spec Ref:
> §6.1` in code resolves against either. If the two ever disagree, the `.docx`
> wins and this file is corrected.

Companion to `beam-rft-detailing.md`. Written the same way: every rule cites its
source, every open question is answered in writing rather than left to be
guessed at build time, and every deliberate deviation from code is named as an
exception rather than left silent.

---

## 0. Scope

**In scope:** detailing the longitudinal bars and transverse reinforcement
(ties/stirrups + cross-ties) of ONE column segment, floor-to-floor, for a single
rectangular column of user-input dimensions `a × b`.

**Out of scope, explicitly** (not "later," named as cut now):

- **C1 — Foundation starter bars / dowels.** Bars protruding from a footing into
  the base of a ground-floor column are out of scope. A separate footing tool
  will own that connection. This tool's bottom boundary is "continues the bar
  from the segment below" (see §6), never "starts from a footing."
- **C2 — Multi-story continuity beyond one splice.** This tool details exactly
  one floor-to-floor segment and its top-of-support splice protrusion into the
  segment above (§6). It does not model a full-height column stack across
  multiple stories in one run.
- **C3 — Non-rectangular columns.** Circular, L-shaped, or other cross-sections
  are out of scope for v1.

## 1. Inputs (user-provided, never invented)

| Input | Notes |
|---|---|
| `a_mm`, `b_mm` | Column cross-section dimensions. |
| `Hc_mm` | Clear height of the column segment (support face to support face). |
| Longitudinal bar type, count per face, corner bars | Ø and fy read from the selected `RebarBarType`, same convention as beam's `role_picker_label`. |
| Tie/stirrup bar type | Ø and fy, user-selected. |
| Cover | Cover to ties/stirrups. Assumed 25 mm as a starting default per the original sketch, but **must remain an editable input, not a hardcoded constant** — same discipline as the beam tool's per-face cover reads. |
| Main outer tie hook type | User-selected dropdown, populated from available `RebarHookType`s in the project, default 135° (§7). |
| Inner tie hook type | A SEPARATE, independently user-selected dropdown from the main outer tie hook, default 135° (§7). |
| Spacing mode | Toggle: Mode A (Auto-Calculate) or Mode B (Manual Override) — see §8. |
| `L_s` (splice length) | Raw user input (value or diameter multiplier). NEVER auto-calculated by the tool (§9). |

## 2. Data model: Perimeter Layout (C9)

**Decision:** the column's longitudinal bar layout is modeled as ONE continuous
perimeter arrangement (corner bars + intermediate bars per side), not as
independent faces.

This is a deliberate departure from the beam tool's `FacePlan`/`LayerPlan` model.
A beam's two faces (top/bottom) are genuinely independent — different bar counts,
different layer counts, different anchorage per face. A column's longitudinal
bars, ties, confinement zone, and splice rule all act on ONE system around the
full perimeter at once. Force-fitting the beam's two-face model onto four column
faces would misrepresent the geometry and was rejected on that basis.

**Consequence:** this warrants a new core module (working name
`rft.core.column_layout`, final name TBD at implementation), not a re-skin of
`rft.core.layout`. Do not assume beam's per-face functions apply without
re-deriving them against the perimeter model.

**Governing dimension rule (C2, closes the original a/b question):**

Evaluate both cross-section dimensions `a` and `b`. The **SMALLER** dimension
governs `S₀`. The **LARGER** dimension governs `L₀`. Both governing values are
then applied uniformly to all four faces of the column — independent per-axis
values are explicitly rejected, by decision, in favor of one governing value
applied uniformly (standard construction practice, avoids site errors).

## 3. Confinement zone length — `L₀`

```
L₀ = max(clear height / 6, larger cross-sectional dimension, 500 mm)
```

measured from the face of the support.

*Source: ECP 203, Chapter 8 — Seismic Detailing Provisions. See §12.*

## 4. Confinement tie spacing — `S₀`

`S₀` equals the **smallest** of:

1. 8 × diameter of smallest longitudinal bar
2. 24 × diameter of the tie
3. Half the SMALLER column cross-sectional dimension
4. 150 mm

*Source: ECP 203, Chapter 8 — Seismic Detailing Provisions (originally sketched
from the manual notes as "13-4-أ", items 1-4). See §12.*

**First tie placement (closes the inequality ambiguity):** the first tie is
placed at an EXACT offset of **50 mm** from the face of the support. This is a
definitive placement instruction, replacing the code's "not exceeding `S₀`"
language, which is a maximum and not by itself a placeable position.

## 5. Middle-zone spacing

Outside `L₀`, transverse reinforcement spacing shall not exceed `2 × S₀`.

This closes what was originally sketched as a bare "150 mm" figure — that number
belonged to a DIFFERENT rule (§6) and is not an independent cap on middle-zone
spacing.

## 6. Horizontal bar restraint & inner tie geometry (C7 — IN SCOPE, AMENDED)

> **AMENDMENT** to the original version of this section: the original simple
> "1-leg cross-tie" assumption is **DELETED**. ECP standard practice
> predominantly restrains interior bars with **OVERLAPPING CLOSED TIES** (boxes
> within boxes), not single-leg cross-ties. Everything below replaces the earlier
> cross-tie language; `rft.core.stirrups`' single-closed-rectangle model is even
> further from what this section now requires than originally scoped.

### 6.1 Which bars need restraint (tiered spacing rule — UNCHANGED)

This folds and REPLACES the earlier loose "150 mm horizontal spacing" note. There
is no separate hard 150 mm cap sitting underneath this rule — this tiered rule is
the only horizontal-spacing provision in scope, and it now governs which bars a
tie's SUBSET must enclose, not merely whether a single-leg cross-tie exists.

Evaluate the horizontal clear distance `x` between consecutive longitudinal bars
around the perimeter:

- Maximum distance between any two tie branches must not exceed **300 mm**.
- If `x ≤ 150 mm`: alternate — tie one bar, leave one bar untied.
- If `150 mm < x ≤ 250 mm`: every single bar must be tied (restrained by a tie
  corner or an inner tie leg).

*Source: Egyptian Detailing Guide (2001), Figure 13-3 (see §12).*

### 6.2 Data model — subset-based closed loops (CADS Rebar logic)

Internal ties are NOT modeled as single-leg cross-ties. The perimeter layout
module (`rft.core.column_layout`, §2) must define each tie — outer and inner
alike — using **SUBSET logic**: an initial bar index and the number of tied bars
it encloses, in a given direction (matching the convention used by CADS Rebar
Extensions). The module generates **CLOSED RECTANGULAR LOOPS** around the
specified bar range, not open lines.

*Example:* Tie 1 wraps the full outer perimeter (all bars). Tie 2 wraps only the
intermediate bars on the North and South faces. A column's full tie set is the
union of one or more such closed, possibly overlapping, loops — never a mix of
"the main tie" plus separate free-floating cross-tie legs.

> **Open item, not yet decided — flagged rather than assumed:** is the subset
> assignment (which ties enclose which bar ranges, i.e. the column's tie
> TOPOLOGY) derived automatically from §6.1's tiered rule for a given bar layout,
> or does the tool ask the user to pick/confirm a topology (e.g. select one of
> Figure 13-3's typical sections)? Auto-deriving a closed-loop topology from a
> spacing rule alone is a non-trivial geometry problem; deferring this to the
> tracer bullet / early implementation spike (§11) rather than guessing now.
>
> **RESOLVED (R4, #71):** the **user selects**; §6.1 **validates** the
> selection rather than generating it. §6.1 admits many valid coverings of the
> same layout and the spec has no tie-break rule between them, so
> auto-derivation would mean inventing one.

> ### ⚠️ AMENDED — A1 (#81): cross-ties return, for ONE reason only
>
> The blanket deletion of single-leg cross-ties above is **partially
> reversed**. A closed loop can only enclose a subset whose narrow dimension
> exceeds the tie's minimum bend diameter — a subset of two bars on opposite
> faces produces a rectangle ~25 mm wide, which no bar can bend to. Revit
> refuses it with a **modal dialog**, not a catchable exception.
>
> So: a bar §6.1 requires to be restrained gets a **closed rectangular loop**;
> a **single-leg cross-tie is used only where that loop cannot be bent**.
>
> ```
> loop is buildable  <=>  narrow dimension >= tie bend diameter + tie diameter
> ```
>
> The bend diameter is **read from the `RebarBarType`**, never assumed as a
> multiple of Ø. Failing this test is the **sole** permitted trigger for a
> cross-tie — never tidiness, simplicity or preference. The test runs
> **before** the Revit API call, and the Review report states, per restrained
> bar, which was used and that the bend test is why.
>
> Full rationale and the live-host evidence: `docs/column/spec-amendments.md`.

### 6.3 Hook corner alternation (NEW rule — do not confuse with §6.1's static bar-membership rule)

To avoid a vertical plane of weakness under compressive load, the HOOK CORNER of
any closed tie (outer or inner) must alternate at each spacing level, vertically.
If a rectangular tie's hook sits at the North-East corner at level `n`, it must
rotate to a DIFFERENT corner (e.g. North-West) at level `n+1`. This is built into
the vertical array loop, not a one-time placement decision.

This is explicitly a DIFFERENT property from §6.1's "static pattern" rule, and
the two must not be conflated:

| | What alternates | Vertically? |
|---|---|---|
| **§6.1** (bar membership) | WHICH bars are enclosed by a tie | **NO** — fixed once, applied at every level |
| **§6.3** (hook rotation) | WHICH CORNER the tie's hook sits at | **YES** — rotates at every level, by design |

Both rules govern the same tie objects; they are not in tension with each other,
but a future reader skimming for "does this alternate" must not merge them into
one answer.

**Consequence:** this is new geometry the beam tool never needed at all —
subset-defined closed loops, per-level hook-corner rotation, and overlapping tie
shapes are a genuinely new module, not a re-skin of `rft.core.stirrups`.

## 7. Hook types — two independent dropdowns (C8, CONFIRMED)

The main outer tie hook type and the inner tie hook type are TWO INDEPENDENT,
user-selectable dropdowns, each populated from the `RebarHookType`s available in
the project — the same `hook_type_options`-style approach as the beam tool, but
NOT collapsed into one control.

**Default value: 135° for both dropdowns.** The default is not a hard requirement
— the user may change either dropdown to any available `RebarHookType` — but 135°
is what each control opens with, reflecting standard seismic practice, per §6.3's
hook-alternation rule applying to whichever hook type is ultimately selected.

*Rationale (stated, not left implicit):* inner ties in seismic detailing commonly
require a strict 135° hook on at least one end, specifically because an inner
tie's function is restraining an intermediate bar against buckling; the main
outer tie may legitimately be detailed differently per project. The tool does not
hardcode either angle — it defaults both to 135° and lets the user override, but
keeps the two choices structurally separate so one dropdown's selection can never
silently apply to the other role.

## 8. Spacing input: Mode A / Mode B toggle

The UI provides a toggle for vertical tie spacing (`S₀` and middle-zone spacing):

- **Mode A (Auto-Calculate):** the tool computes the strict code maximums per
  §3–§5.
- **Mode B (Manual Override):** the user enters exact spacing values for the
  confinement zone and the middle zone directly.

**Manual-override behavior — "warn but place,"** stated explicitly so it is never
confused with either silent refusal or silent compliance:

If Mode B's user-entered spacing violates the code-calculated limit, the tool
does NOT refuse, and does NOT silently accept it either. The Review report MUST
display the code-calculated limit ALONGSIDE the user's manual value as a visible
flag/warning. The placer logic ultimately respects and builds the user's manual
value regardless of the warning.

This mirrors the beam tool's single-source-of-truth principle: the Review report
and the placer must show/use the same number, so a violation is visible on the
page the same instant it becomes true in the model — never discoverable only
after the fact.

## 9. Splice location — constructability override (C4, named exception)

**Constructability Override (Exception to Seismic Clause):** Despite the `L₀`
confinement zone being a critical seismic region, lap splices shall deliberately
start at the top face of the support (falling entirely within the lower `L₀` zone
of the upper segment). This is a conscious deviation from the mid-height splice
rule to accommodate standard real-world floor-by-floor concrete pouring joints.
The tool knowingly places lap splices inside `L₀` at the base of every story.

**Bar geometry:** the longitudinal bar is modeled starting from the current floor
level, extending upward through the column's clear height and through the top
support, protruding by a splice length `L_s` above the top support's face to
connect with the next story.

**`L_s` as user input, never auto-calculated:** because `L_s` varies based on
tension/compression zones, `L_s` is a direct user input (raw value or diameter
multiplier). The tool does not auto-calculate `L_s`; it blindly applies the
user's input.

## 10. Explicit non-reuse

This tool does **NOT** call or reuse `rft.core.anchorage`. Column bar ends are
governed entirely by the floor-to-floor splice/protrusion logic in §9, not by
beam-style supported/unsupported end anchorage.

Stated plainly, the same way any other non-reuse should be, so a future
contributor does not assume `anchorage.py` should be wired in by default.

## 11. Prerequisite before any core logic or UI is built

A throwaway tracer-bullet script MUST be written and verified against a real
Revit host, on a real test column, for:

1. **Section orientation** — reading which direction is `a` vs `b` in the model.
   A column is a point-based `FamilyInstance` with a vertical `Location.Point`;
   its cross-section rotation does not come from `Location.Curve`-based axis
   reads the way beam geometry does, and this exact class of "wrong reference"
   assumption has cost this project multiple release candidates before.
2. **Finding vertical framing neighbours** — locating the supporting/framing
   element at BOTH the base and the top of the column segment. Beam's
   `find_supporting_element` searches along one line at one end; a column needs a
   genuinely new vertical search, not a reuse.

Both must be confirmed on a live host BEFORE any `core.column_layout` module or
WPF window is designed around an assumption about either.

> **Status: DONE.** Verified 2026-09-14 against Revit 2024 via the MCP
> connection. See `docs/column/verification/issue-69-column-tracer-bullet.md`.
> Findings that change the design: `b` follows `HandOrientation` and `h` follows
> `FacingOrientation` (the bounding box is unusable for this); the clear height
> must come from a support-face search, **not** from `INSTANCE_LENGTH_PARAM`,
> which reports the level-to-level length; and the base search may legitimately
> return nothing.

## 12. Citations (CLOSED)

| Rule | Source |
|---|---|
| §3 — `L₀` confinement length | ECP 203, Chapter 8 (Seismic Detailing Provisions). |
| §4 — `S₀` confinement spacing, first-tie offset | ECP 203, Chapter 8 (Seismic Detailing Provisions). |
| §6 — horizontal restraint tiers, inner tie subset/closed-loop geometry | Egyptian Detailing Guide (2001), Figure 13-3 (Typical Column Reinforcement Sections). |

This closes the citation gap flagged in the prior draft. All three sources are
chapter/figure-level references rather than a numbered sub-clause — if a more
granular clause number exists within Chapter 8 or Figure 13-3 for any individual
rule (e.g. the exact sub-item for the 8×/24×/half-b/150 mm list in §4), it should
still be added when convenient, the same standard the beam spec holds itself to
(rev 2 section 2.4, not just "rev 2"). This is a refinement to make later, not a
blocker to starting the tracer bullet.
