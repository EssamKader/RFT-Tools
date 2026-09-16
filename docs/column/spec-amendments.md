# Column spec — amendment ledger

The column tool's **own** ledger. Per `docs/reuse-for-new-elements.md` §4, a new
element starts its own ledger and does **not** extend the beam's
(`docs/beam/spec-amendments.md`). Amendment numbers here are independent of the
beam's `A1..A49`; a bare "A3" in a column module means *this* file's A3.

Why this exists: it is what makes a spec disagreement resolvable six months
later instead of re-litigated. Every row names what changed, why, and which
issue decided it.

## Status

`specs/column-rft-detailing.md` is **LOCKED at v1**, with **two amendments** —
**A1** against §6.2 and **A2** against §1. Everything else the Wayfinder cycle produced was a
decision *about* the spec (packaging, API mechanics, reuse) rather than a
change to its text.

## Amendments

| # | Section | Change | Decided by |
|---|---|---|---|
| **A1** | **§6.2** | **Cross-ties are reinstated, as a fallback triggered by ONE condition only: the bend fails.** §6.2's amendment had deleted single-leg cross-ties outright ("the original simple 1-leg cross-tie assumption is DELETED"). A1 partially reverses that: a bar §6.1 requires to be restrained gets a **closed rectangular loop**, and a **single-leg cross-tie only where that loop cannot physically be bent**. A loop is *buildable* when `narrow dimension >= tie bend diameter + tie diameter`, the bend diameter **read from the `RebarBarType`**, never assumed. Owner's wording: *"use tie only when bending fail"* — so a cross-tie may never be chosen for tidiness, simplicity, preference, or because a loop would merely be awkward. Failing the bend test is the **sole** permitted trigger, and the Review report must state per restrained bar which was used and that the bend test is why. | #81 |
| **A2** | **§1** | **Cover is READ from the Revit element, not entered in the tool.** §1 listed cover as a user input *"assumed 25 mm as a starting default … but must remain an editable input, not a hardcoded constant"*. Owner's ruling: *"cover to be determined from revit element cover setting"*. The host's cover parameter is the **single source of truth**; the tool reads it and shows it **read-only**. Cover remains editable — in Revit, on the element, where every other discipline already sees it — and is never typed into the tool or defaulted to 25. | #83 |

### Why A2 was forced — the input was already fiction

R16 proved the tool could not have honoured a typed cover anyway. Ties carry
`Edge -> ToCover` constraints, so Revit **clamps** them to the host's cover: a
tie built for 25 landed at the host's 40, silently, with no warning and no
exception. A user typing 25 would have got 40 in the model while the Review
report said 25 — exactly the report/model divergence §8 exists to prevent.

A2 does not remove a capability; it **stops the tool claiming one it never
had**. It also strengthens §8's single-source-of-truth principle rather than
weakening it: report and model now read the same number because they read the
*same parameter*.

**Which parameter:** for a column's four vertical faces — the ones every tie
and perimeter bar is measured from — that is `CLEAR_COVER_OTHER`
("Other Faces"). Confirmed empirically: the test column reads 40 mm there, and
ties clamped to exactly 40.

> **Open, and must not be guessed (Q5):** the same column's
> `Rebar Cover - Top Face` is **unset** (`-1`). A2 makes that load-bearing —
> the tool now depends on reading cover, so what it does when the parameter it
> needs is unset is a real branch, not a defensive nicety. Refuse, fall back
> to "Other Faces", or prompt?

### Why A1 was needed — it was not a theoretical gap

A hand-built cage on the live host (450×600, cover 40, 10M ties, 16M bars,
3 bars per 450-face) put **both** faces in §6.1's `150 < x <= 250` tier, so
every bar required restraint. The subset {N-mid bar, S-mid bar} is a closed
rectangle **25.4 mm wide** — narrower than a 10M bar's ~38 mm bend diameter.
Revit refused with a modal **"Can't solve Rebar Shape"**, three times, and
blocked the session. §6.2 as written demanded a shape that cannot exist.

### What A1 changes in the data model

`column_layout`'s output stops being "a list of closed loops". It becomes a
list of **restraint elements**, each either a closed loop (subset → rectangle)
or a cross-tie (a single leg between two bars). The review report, the sketch
and the placer all consume that union type. The buildability test runs
**before** the Revit API call, so the user sees a stated choice rather than a
modal refusal.

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
| R14 | #80 — does placement ORDER decide where a bar ends up? | **No.** Bar-then-tie and tie-then-bar give the identical result; the bar is created *already* shifted. Order is irrelevant, and #80's opening hypothesis was wrong. | #80 |
| R15 | Why did the bars move, then? | **Only CORNER bars move, and Revit is right.** With no tie present every bar lands exactly as asked. The tie's `StirrupTieBendDiameter` is 40 mm, so its corners are 20 mm arcs — a corner bar cannot occupy the intersection of two straight legs, that point is inside the bend. Revit nestles it against the real arc. The computed position was an idealisation. **Compounding:** a set is "first bar + spacing", so if the first bar is a corner bar its snap **translates the whole array** — 3.5 mm at the corner became 18.5 mm on every bar of that face. **Never start a bar set on a corner bar.** The position cannot be dictated (`SetDistanceToTargetRebar` throws on a `HookBend`/`BarBend` target) — it must be **read back** and reported as-built. | #80 |
| R16 | Is the §1 cover input honoured by Revit? | **Not downward.** Ties carry `Edge -> ToCover` constraints and are **silently clamped to the host's cover parameter**: a tie built for cover 25 landed at the host's 40. More cover is honoured, less is pulled back, with no warning or exception. See Q12 — the response is an open owner ruling. | #80 |

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
| Q5 | §1 | The test column's `Rebar Cover - Top Face` is **unset** (`-1`), so a per-face read cannot assume all three cover parameters resolve. **A2 makes this load-bearing** — the tool now depends on reading cover, so an unset parameter is a real branch: refuse, fall back to "Other Faces", or prompt? | open (#69, #83) |
| Q6 | §9 | **Roof / top-storey column.** §9 protrudes `L_s` above the top support "to connect with the next story" — a roof column has none, so bars would project out of the slab. The closure rule at the roof slab is undefined. | open, **deferred by owner** (#77) |
| Q7 | §6.3 | Can `MoveBarInSet` accept a **reflection**, and is a **mirrored 135° hook** legal? | **CLOSED** → R9/R10 (#78) |
| Q8 | §6.3 | Only the `hand`-normal mirror plane (SW→SE) was tested. Mirroring about the `face` normal (SW→NW) is the other adjacent move, untested. Should alternation use one plane throughout, or alternate between both across four levels? §6.3 requires only "a different corner" each level, so the spec does not decide this. | open |
| Q9 | §6.2 | Every tie experiment so far used the **outer perimeter** tie only. No inner subset tie had ever been created. | **CLOSED** → R11 |
| Q10 | §6.2 | **The tie/stirrup SHAPE CATALOGUE cannot be finalised.** Owner, 2026-09-14: *"for stirrups shape it is very hard to give you one final answer."* There is no closed list of tie shapes to implement against, and there may never be one. | **open by nature, not by omission** — see below |
| Q11 | §6.2 | Given Q10, should the template picker (#71) offer a fixed catalogue of Figure 13-3 sections at all, or let the user **define subsets directly** (start bar index + count, per §6.2's own convention) with §6.1 validating whatever they build? | open |
| Q12 | §1 | The cover input is not honoured downward — Revit clamps a tie to the host's cover parameter. | **CLOSED** → **A2**: cover is read from the element (#83) |
| Q13 | §6.1 | **The tier check may validate coordinates the model does not use.** `x`, the clear distance between bars, decides which tier applies and therefore which bars need restraint. Per R15, corner bars sit ~3.5 mm inboard of their computed positions. Should §6.1 be evaluated on idealised coordinates or on positions read back after placement? | open |

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
| **Placing rebar silently MOVES rebar already placed.** Revit auto-creates `ToOtherRebar` constraints: longitudinal bars placed first were dragged ~18.5 mm off their computed positions when the ties were placed afterwards. Spacing and span survived; only the origins moved. Zero warnings, nothing thrown. | §2, §6.2, §9 — every placed quantity | The placer must **own** the constraints, not let Revit infer them: set each handle explicitly to a host face or cover, never to other rebar, unless a rebar target is deliberately wanted. Creation ORDER is part of the contract. Read positions back and assert them. (#80) |
| A closed loop whose narrow dimension is below the tie's bend diameter is **geometrically unsolvable**, and Revit refuses with a **modal dialog** that blocks the whole session — not a catchable exception. | §6.2 / A1 | Run the buildability test (`narrow >= bend diameter + tie diameter`, bend diameter read from the `RebarBarType`) **before** any API call, and fall back to a cross-tie per A1. Never let the geometry reach Revit untested. (#81) |

## Q10 — why the tie shape catalogue stays open, and why that is fine

The owner's position is explicit: *"for stirrups shape it is very hard to give
you one final answer."* There is no closed list of tie shapes to implement
against, and pretending otherwise would mean inventing one — precisely what
`CONTEXT.md` forbids.

This **vindicates R4** (#71) rather than undermining it. R4 chose "the user
picks, §6.1 validates" over auto-derivation exactly because the tool has no
business deciding tie topology. Q10 says the same thing one level deeper: the
tool should not hardcode the *catalogue* either.

What follows for the implementation, and what does not:

- **Not blocked.** §6.1's validator, A1's buildability test, the subset →
  rectangle geometry, the per-level mirror map and the placer are all
  shape-agnostic. They take whatever subsets they are given.
- **Blocked:** shipping a fixed list of Figure 13-3 sections as *the*
  templates. That list does not exist yet and may never be complete.
- **Open (Q11):** whether the picker offers named templates at all, or lets
  the engineer state subsets directly in §6.2's own terms (start bar index +
  count) with §6.1 and A1 validating whatever they build. The second needs no
  catalogue and cannot go stale — but it asks more of the user.

Nothing here may be resolved by assumption.

## R17 (#89) — Q11 ANSWERED: direct subset entry, no template catalogue

**Owner ruling, 2026-09-15.** The tie topology control is **direct subset
entry**: the engineer states each tie in §6.2's own terms — an initial bar
index and how many bars it encloses — and §6.1 plus A1 validate whatever
they build.

A named-template picker was the alternative and was **rejected**, for the
reason Q10 already gave: the catalogue does not exist, cannot be completed,
and shipping one would mean inventing it.

Two consequences worth stating, because they are why this option was the
only one that could be chosen without regret:

- Subset entry is **strictly more general**. A named template is a preset
  that emits exactly these subsets, so a picker can be added later as a
  convenience without changing the model underneath it. Nothing built now
  is wasted if templates are ever wanted.
- The control **cannot go stale**. A section nobody anticipated is
  expressible on the day it is drawn, instead of being a feature request.

Implemented in `rft.core.column_ties`.

## R18 (#89) — Q13: §6.1 validates IDEALISED positions, and the reason is
   not convenience

Q13 asked whether §6.1's clear distance `x` is evaluated on idealised bar
positions or on as-built ones, given R15's finding that a corner bar sits
~3.5 mm inboard of its computed position once a tie exists.

**Ruling: idealised, before placement — and it is the CONSERVATIVE choice,
not merely the only available one.**

Two facts settle it together:

1. **As-built positions do not exist before placement.** #80 established
   that the corner position cannot be dictated and that its closed form was
   never derived: "the tool must read the value back rather than predict
   it". A pre-placement validator has nothing else to read.
2. **The snap only SHRINKS clear distances.** A corner bar moves inboard on
   both axes, toward the section centroid. Its neighbours are mid-face bars
   along the same faces, so the distance to each of them gets *smaller*, not
   larger. On the live column: corner `(-167.55, -242.55)` → `(-164.02,
   -239.02)`, and its clear distance to the mid-face bar at `(0, -242.55)`
   falls from 167.55 to 164.06.

So a validator reading idealised positions reports gaps that are **wider
than reality** — it can demand restraint that turns out to be unnecessary,
and it can never miss restraint that was needed. That is the safe direction,
and it means this ruling does not have to be revisited when as-built
read-back lands.

**What still must happen after placement:** the Review report states
as-built positions (R15), so a re-validation on read-back positions is a
report-time check, not a gate. If it ever disagrees with the pre-placement
result, it will disagree by being *less* demanding.

---

## R19 — A tie is the bars it touches, not a run of them

**Supersedes R17's notation. R17's *principle* stands unchanged:** the
engineer states the topology and the tool never derives one (R4). What
changes is the alphabet R17 chose to state it in.

**Decided:** a tie is written as the **bar numbers it touches**, one tie per
line. `1 6` is a cross-tie from bar 1 straight across to bar 6; `0 1 2 3` is
a closed loop around those four. The outer perimeter tie stays implied and is
never typed.

**Why R17's "start index + count" had to go.** It can only name a
**contiguous run** of the perimeter, and the commonest inner tie in practice
— a cross-tie from one mid-face bar to the one opposite — is not contiguous.
Found by detailing the live 450 × 600 column: bars 1 and 6 face each other
across the width, and every cross-tie the old notation could express joined
bars **adjacent on the same face**, 25.4 mm apart, which is not a detail
anybody draws. Asked for the conventional three cross-ties, the tool instead
offered three overlapping closed loops.

The evidence was already in the repository, asserting the opposite of its own
name: `test_a_two_bar_subset_across_a_face_becomes_a_CROSS_TIE` asserted
`KIND_CLOSED_LOOP`, twice, because `TieSubset(1, 6)` meant *the run 1..6*.
The test documented the gap and nobody read it that way.

**Nothing downstream changed.** The bounding box, A1's bend test, the corner
scan and §6.1's tiers only ever saw a list of bar indices; the contiguous
assumption lived in `subset_indices` alone. A list is strictly more
expressive — a run is just a list — so no topology expressible before is
lost.

**One new failure mode, guarded:** a free-form list can name the same bar
twice. `1 6 1` would resolve to the same tie as `1 6`, because a bounding box
does not care how often a corner is named. It is refused, naming the repeated
bar: a typo that produces a plausible result is worse than one that produces
none.

---

## R20 — A cross-tie counts as a leg for §6.1's 300 mm branch limit

**Decided by the owner**, after the live column showed what the previous
behaviour cost.

**The behaviour until now:** `_branch_spacing_findings` skipped cross-ties
entirely. Only closed-loop legs counted toward the 300 mm maximum between
branches.

**Why that was wrong.** A cross-tie from bar 1 to bar 6 is a single bar
running the full height of the section at `u = 0`. As a branch restraining
the core, that **is** a vertical leg. Skipping it meant the 300 mm rule could
only ever be satisfied by **nested closed loops**, so the tool steered the
engineer away from the detail they would actually draw and toward a heavier
one — extra steel in every column, produced by a validator's blind spot
rather than by the code.

**The rule as implemented:** a cross-tie contributes **one** coordinate, not
two, and **only on the axis it is thin across**. Bar 1 → bar 6 is a vertical
leg at `u = 0` and contributes nothing horizontally. Counting it on both axes
would invent a horizontal branch that no steel provides, which is the unsafe
direction and is separately guarded.

**On the live column**, the conventional detail now passes:

```
ties: 1 6 | 9 3 | 8 4        all three resolve as CROSS-TIE
u legs:  -180.25, 0, +180.25             -> 180, 180          (was 360)
v legs:  -255.25, -80.8, +80.9, +255.25  -> 174, 162, 174     (was 510)
all 10 bars restrained                    BLOCKING: none
```
