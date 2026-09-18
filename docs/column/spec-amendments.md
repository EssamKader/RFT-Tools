# Column spec — amendment ledger

The column tool's **own** ledger. Per `docs/reuse-for-new-elements.md` §4, a new
element starts its own ledger and does **not** extend the beam's
(`docs/beam/spec-amendments.md`). Amendment numbers here are independent of the
beam's `A1..A49`; a bare "A3" in a column module means *this* file's A3.

Why this exists: it is what makes a spec disagreement resolvable six months
later instead of re-litigated. Every row names what changed, why, and which
issue decided it.

## Status

`specs/column-rft-detailing.md` is **LOCKED at v1**, with **three amendments** —
**A1** against §6.2, **A2** against §1, and **A3** adding §13 (Placement), which
the locked spec never had. Everything else the Wayfinder cycle produced was a
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


---

## R21 — a closed tie's hooks turn INWARD: `Left` / `Left`

**Established live** (#109, Finding 4), on column 422078.

`Rebar.CreateFromCurves` takes a hook orientation per end. With
`RebarHookOrientation.Right` at both ends — the obvious-looking choice, and
the one the tracer bullet used — both 135° hook tails land **outside the
concrete**. Revit builds it anyway: no exception, no warning, no null. The
element schedules and draws like any other tie.

Of the four combinations, only `Left` / `Left` turns both tails into the
core. **The placer passes `Left` / `Left`, and asserts that both hook tails
fall inside the host's extent before keeping the element.**

The assertion is not belt-and-braces. The orientation enum is interpreted
against the curve direction, so the correct value is a property of how the
loop was wound — and the loop is wound by
`rft.core.column_ties`, which is free to change. A constant that is right
today because of an unstated convention elsewhere is exactly the kind of
coupling this project has paid for before. The check is on the geometry
that came back, which cannot drift.


---

## R22 — a longitudinal bar is positioned by a DISTANCE TO A HOST FACE, never by a coordinate

**Established live** (#92), on column 422078, after #109 made kept writes
possible.

A bar handed to `Rebar.CreateFromCurves` **does not stay where it is put.**
It binds to the nearest tie bend and translates, and a multi-bar set
translates whole — every bar carrying the same error. On the live column a
corner bar moved `+4.75 / +12.05 mm`, which is R15's snap, measured.

The placer therefore does not rely on the coordinate it passes. After
creating the bar it **pins the in-plane handles to the host's own faces**:

- for the `RebarPlane` handle and each `Edge` handle, take the candidate
  from `GetConstraintCandidatesForHandle` that is `IsToHostFaceOrCover()`,
  is **not** `IsToCover()`, targets the host, and whose `PlanarFace` normal
  is the near face on that axis;
- `SetDistanceToTargetHostFace(-offset)` — **negative**, because the
  distance is signed against the OUTWARD face normal;
- `SetPreferredConstraintForHandle(handle, constraint)`.

Three things that look like the same fix and are not:

| tried | result |
|---|---|
| `ToCover` candidate | constraint re-points, **bar does not move** |
| positive offset | bar lands 57 mm **outside** the column |
| `IsRebarConstrainedPlacementEnabled` | static, already `False`, snap happens anyway |

**Why this is a rule and not an implementation detail.** The column's near
faces sit at `x = -370.822`, `y = 886.950` — not on a round coordinate, and
nothing requires them to be. A placer that computes absolute XY carries the
host's coordinate noise into every bar and must then decide what rounding is
acceptable. A placer that states *"57.45 mm from this face"* is exact by
construction and follows a cover change for free.

This supersedes #92's proposal to place single-bar sets for predictability.
Sets stay; the constraint is what buys the predictability.


---

# A3 — §13 Placement: a section the spec never had

`specs/column-rft-detailing.md` §0–§12 defines what the tool **reads,
computes and judges**. Nothing in it defines what the tool **builds**. That
was not an oversight in the spec — v1 was written before a write had ever
survived a transaction in this project — but it became a gap the moment
#109 proved one could.

Decided by the owner, four rulings, after #92 and #109 had established what
Revit actually does. **R23–R26 below are that section.**

---

## R23 — a second press REPLACES, and says so first

Pressing Apply on a column that already holds this tool's reinforcement
**deletes that reinforcement and rebuilds it**, after telling the engineer
what will go:

```
This column already holds 12 elements placed by this tool.
Apply will DELETE them and rebuild.

   [ Replace ]   [ Cancel ]
```

**Why not refuse.** The engineer tunes a tie arrangement by pressing Apply,
looking, and pressing again. A tool that refuses turns every iteration into
a manual cleanup, and the arrangement is exactly the thing §6.1 makes them
iterate on.

**Why not add.** Adding is what code does when nobody decides. It produces
a column carrying two cages that schedules as real steel, prices as real
steel, and cannot be built.

**The count is not decoration.** It is the engineer's only chance to notice
that the tool's idea of "its own" reinforcement differs from theirs — for
instance because a Partition was edited by hand (R26). A dialog that said
only "Replace?" would hide exactly the case worth catching.

## R24 — rebar the tool did not place is NEVER deleted, and is always reported

The placer deletes **only** elements it owns under R26. Anything else
hosted by the column — hand-modelled bars, another tool's output, a
colleague's correction — is left untouched **and named in the Review
report**.

Both halves are the ruling. Leaving it alone stops a button press
destroying someone's hand work. Reporting it stops the opposite failure:
an engineer reading a report that describes our cage, looking at a model
that contains ours *plus* three bars nobody mentioned, and trusting the
quantities.

**Not** "refuse if any foreign rebar is present". Most real columns have
been touched by hand somewhere, and a tool that blocks on that is a tool
nobody can use on a live project.

## R25 — the whole cage is ONE transaction: all of it, or none of it

One Revit transaction, named so it reads properly in the undo menu, wraps
**the deletions of R23 and the whole rebuild together**.

Three consequences, and the third is the one that would have been missed:

- a failure anywhere leaves the model **exactly as it was**;
- one Ctrl+Z undoes the placement, not thirty-eight;
- **a failed rebuild cannot leave the engineer with neither cage.** Because
  the delete and the rebuild share a transaction, rolling back the rebuild
  restores the reinforcement R23 had just removed. Deleting in a separate,
  already-committed transaction would produce the worst state available:
  the old cage gone, the new one never built.

**This is not defensive coding, it is the only workable design.** #109
Finding 3 established that offering Revit an unbuildable loop fails *above*
the call site — no null, nothing the surrounding `try`/`except` can catch.
The placer therefore cannot promise to notice its own failure and clean up.
The transaction is what makes the guarantee instead.

It follows that **everything knowable must be checked before the
transaction opens**: §6.1's blocking findings (`is_blocked`), and A1's bend
threshold on every loop. A transaction is never opened on a plan already
known to fail.

## R26 — ownership is a visible `Partition`, not hidden data

Each element the placer creates gets its host and the tool's mark written
into the rebar **`Partition`** parameter — confirmed on the live model as a
writable, currently empty string parameter:

```
Partition = RFT-COL-422078
```

**The ownership test is the `RFT-COL-` prefix**, not the number after it.
The id is there so the value is self-describing in a schedule; a column
copied with its cage keeps a stale id and must still be recognised as ours.

**Why visible rather than extensible storage.** Hidden data cannot be
wrong in a way anyone can see. An engineer can schedule Partition, filter
by it, notice a cage the tool has lost track of, and fix it by typing.
When ownership is a blob, an orphaned cage is undiagnosable and the only
recovery is to delete rebar by hand and hope.

The cost is accepted deliberately: a Partition can be edited or cleared by
hand, and then the tool will not recognise its own work. **That is what
R23's count exists to surface** — the engineer sees "3 elements" where they
expected twelve, and knows something was retagged before anything is
deleted.

**Not `Comments`.** Engineers already write in Comments. A tool that owns
that field competes for it and eventually overwrites somebody's note.

---

## The order the placer runs in

Stated because the order carries the rulings, and code that does the same
steps in a different order satisfies none of them:

1. compose the `ColumnPlan` (#110) — one object, read once;
2. **refuse** if `is_blocked(plan)`, before anything else;
3. **refuse** any loop failing A1's bend threshold — #109 Finding 3 means
   this cannot be left to Revit;
4. find this tool's existing elements in the host by R26's prefix; count
   foreign rebar separately;
5. if any exist, show R23's dialog and stop on Cancel;
6. **open one transaction** (R25);
7. delete the owned elements;
8. create ties and bars; apply R22's host-face constraints; assert R21's
   hook tails fall inside the host extent; write R26's Partition;
9. commit — or let anything at all roll the whole thing back;
10. report, naming the foreign rebar R24 left alone.

## Still open after this

**Save / reopen persistence** of R22's constraints (#92 Q4) and **§6.3's
alternation gap for cross-ties**, which has no corner to alternate. Neither
blocks writing the placer; both must be closed before it ships.


---

## R27 — the picker shows `fy`, and the longitudinal role takes `T` names only

**Decided by the owner** (#133), after the Longitudinal picker listed
`10M`…`57M` and read as entirely mild steel.

### The premise it corrects

It is not mild. Every `M` type in the verification model is **ASTM A615M
Grade 420** — the `M` is the METRIC bar designation, not "mild". Read live
on Revit 2024 build 24.3.40.26:

| types | fy |
|---|---|
| `10M` … `57M` (11) | **420 MPa** |
| `12T`, `16T` | **420 MPa** |
| `10T`, `14T` | **unknown** — no material assigned |

The chain is `MATERIAL_ID_PARAM` → `Material.StructuralAssetId` →
`PropertySetElement.GetStructuralAsset().MinimumYieldStress`, converted
with `UnitUtils.ConvertFromInternalUnits(..., UnitTypeId.Megapascals)`.

**This disproves A42's stated reason** — *"a `RebarBarType` carries a
diameter, not a grade"*. It carries both. A42's **policy** is unchanged:
the tool reports, it does not choose.

### The rule

- **Every label carries `fy`** beside the diameter. A type with no material
  reads `fy unknown`, never a defaulted 420 — the label exists precisely
  because a name guarantees nothing (`16M` is 15.9 mm), and this is the
  same problem one field over.
- **The longitudinal picker takes `T`-named types only.**
- **The tie picker is unfiltered.** Mild is *permitted* for a tie, not
  required; filtering this project's tie list to mild would empty it,
  because it holds no fy 240 material at all.

### What the ruling costs, on the record

Filtering by name is what `rft/core/grades.py`'s own docstring forbids —
*"never inferred from the document by name-matching"*. The owner chose it
knowing that, for a specific reason: **in a project where every type reads
420 MPa, yield strength separates nothing.** The letter is the only
discriminator that exists.

So:

- a correctly-specified 420 MPa bar named without a `T` is hidden from the
  longitudinal picker, for a reason that is typographic;
- a project not using this convention gets an empty longitudinal list;
- a `T`-named type with no material, or with mild steel, is still offered.

**The number shown beside each type is what makes that visible.** The
letter chooses the list; the engineer reads the grade. Both halves are the
ruling — the filter without the label would be the tool hiding its own
reasoning, and that is what R27 refuses.


### WITHDRAWN in part (#135) — the filter is gone, the label stays

**The T filter emptied the picker on the live model and has been removed.**

`ColumnRFT.Trail.rvt` holds **eleven** bar types — `10M` … `57M`, element
ids 53649–53681 — and **no T-named type has ever existed in it**. The
filter therefore selected nothing, and the Longitudinal dropdown came up
blank.

**How the mistake was made, because it is the instructive part.** The
evidence for R27 came from a live probe that reported fifteen types
including `10T`…`16T`, with `NEOM_*` shared parameters and `10M` at element
id **1542445**. The document actually being detailed has `10M` at **53672**.
Those are two different projects: the MCP connection answered from another
open document, and nobody checked the ids matched the column under test.

A live probe is only evidence about the document it ran against. **This
project had already learned that a fake can be laxer than the API; the same
discipline applies to a probe — it must be pinned to the element in
question, not merely to "the live host".**

**What survives:** every picker label carries the type's `fy`. That half was
never in doubt, and it is the half that does the work — the engineer sees
420 MPa beside `16M` and knows the name says "metric", not "mild". Hiding a
bar they need is worse than showing one they must judge.

`bar_type_options(..., high_tensile_only=True)` remains in the adapter,
tested, unused by either window. It is the correct implementation of a rule
this project's models cannot currently express; it costs nothing to keep and
would otherwise be rewritten from scratch the day a T-named project appears.


---

## R28 — a triangle is a genuine three-sided closed tie, and A1 generalises rather than needing a new rule

**Decided by the owner** (#141), across two comments. *"in addition to loop
stirrups i want to be able to make triangle stirrups"* set the definition
before any figure was produced; a supplied page then supplied the
**citation**, not the definition.

### The citation

**Egyptian Detailing Guide (2001), Figure 13-3, p. 78** — the same figure
`specs/column-rft-detailing.md` §12 already cites for §6's restraint tiers
and inner-tie geometry. Recorded earlier in the ticket as "figure number
unknown"; that half of the blocker is closed, and no new source is opened
by this ruling.

### What "triangle" means here

A **genuine three-sided closed tie through three bars** — never a diamond
(a rotated square, still four 90-degree corners, already buildable under
A1 unchanged), never a bounding box, never a diagonal corner tie that
happens to look three-sided in a photograph. If a future ticket needs the
diamond or the diagonal corner detail, it is a different shape with a
different citation, not a variant of this one.

### The bend test: A1 generalised, not replaced

A1 (`minimum_buildable_narrow_mm`) is the special case, for a 90-degree
corner, of a rule that holds for any polygon vertex. At a vertex of
interior angle `theta`, a bend of pin radius `r = bend_diameter / 2` has
its tangent points at `t = r / tan(theta / 2)` from the vertex along each
leg (`rft.core.column_ties.tangent_length_mm`). A leg between vertices `i`
and `j` must fit both bends plus A1's own clearance:

    leg_length  >=  t_i + t_j + tie_diameter

**At theta = 90 degrees this is exactly `bend_diameter + tie_diameter`** —
`minimum_buildable_narrow_mm` as written today —
(`test_tangent_length_reduces_to_A1_at_90_degrees`). That reduction is the
entire argument for using the generalised test without a new citation: it
is A1's own rule, stated once, for whichever polygon the tool is asked to
build.

**What this does NOT claim:** that the code permits an acute tie corner at
any particular minimum angle, or that `bend_diameter` is the same for an
acute bend as for a 90-degree one. The test says only what the bend
geometry the tie is already asked to make can physically close — the same
question A1 asks, for the same reason A1 asks it (Revit refuses the rest
with a modal dialog, not an exception).

### On failure, refuse — never degrade

A1 degrades an unbuildable rectangle to a cross-tie, because a rectangle
that cannot close still restrains its two named bars as a single leg. A
triangle has no such fallback with a source behind it: choosing one
(a cross-tie between two of its three bars? a smaller triangle nobody
asked for?) is a detailing decision this ticket was never given authority
to make. So `rft.core.column_ties._resolve_triangle_tie` **raises**,
naming the sharp vertex's angle and its two leg lengths, and constructs no
`ResolvedTie` of any kind. This is the one place the column tool's tie
resolution refuses outright rather than resolving to something weaker.

### The rest of the shape, briefly

- **Notation**: a `T`-marked line in the Ties box (`"T 1 3 5"`); an
  unmarked line is unchanged (loop or cross-tie, exactly as R19 left it).
  `TieSubset` gained a `triangle` field defaulting to `False` — one
  subset, a second fact about it, not a second way to describe geometry
  (#140's own point, applied here).
- **Geometry**: the three vertices are the three bar centres, each pushed
  outward along its own interior-angle bisector by `grow / sin(theta / 2)`,
  `grow = bar/2 + tie/2` — the same `grow` A1's rectangle already uses,
  applied per-vertex instead of per-axis.
- **Restraint**: a triangle restrains exactly its three named bars — no
  bounding-box corner can land on a fourth, because there is no bounding
  box.
- **UI**: `Add tie` gains a Loop / Triangle choice (`tie_shape_cb`); the
  window cannot run under CPython, so that half is proven by source-level
  guard and mutation (`tools/prove_guards.py`), not by import.
- **Placement/sketch**: three segments through the existing
  `_uv_segments_mm` dispatch and a 3-point `SketchPolygon` through the
  existing (kind-agnostic) drawing path — #140's `ResolvedTie.vertices` is
  what makes both need no triangle-specific code at all.


---

## R29 — a diagonal leg is not a branch for section 6.1's 300 mm rule

**Decided by the owner** (#146), asked directly whether a diagonal leg counts
for the 300 mm branch-spacing limit:

> no not count

### What it corrects

Section 6.1 sets a maximum of 300 mm between two tie branches. Until this
ruling the check read each tie's **bounding box** and took its two edges per
axis. For a rectangle that is exactly right — a closed loop's four legs *are*
its bounding box's edges. For a triangle it is not.

`T 1 9 3` on the verification column:

| bar | u | v |
|---|---|---|
| 1 | 0 | −243 |
| 9 | −168 | −81 |
| 3 | 168 | −81 |

The box spans `v = −243 … −81`, so the check credited **horizontal branches at
both**. Only leg 9–3 is real. At `v = −243` there is a single **vertex**, bar
1, with both of its legs running diagonally away from it. The box also claimed
vertical branches at `u = ±168`, where the triangle has only points.

### The rule

- A leg counts as a branch on an axis **when it runs along that axis** — a
  vertical leg is one at constant `u`, a horizontal leg one at constant `v`.
- **A diagonal leg counts for nothing**, on either axis.
- A zero-length leg counts for nothing, rather than reading as aligned on both.

### Why this direction matters

`validate`'s own discipline, stated in its docstring, is that it *"can demand
restraint that proves unnecessary; it can never miss restraint that was
needed."* A bounding box **misses**: it passes an arrangement whose steel is
more than 300 mm apart because a box edge said otherwise. Section 6.1 is a
blocking check, so that is the wrong way round.

### What it changes in practice

- **A closed loop: nothing.** Its four legs are its box's edges.
- **An axis-aligned cross-tie: nothing.** R20 already gave bar 1 → bar 6 one
  vertical branch at `u = 0` and nothing horizontally; the general rule says
  the same thing for the same reason.
- **A triangle:** only its genuinely axis-aligned legs count.
- **A diagonal cross-tie:** now counts for nothing, where R20's thin-axis test
  gave it a coordinate. No such tie exists in the verification model; the
  change is stated here rather than discovered later.

Three special cases became one question, asked through `tie_legs` and
`branch_coordinate`, both reading the `vertices` polygon #140 gave every tie.

### What is NOT claimed

That Figure 13-3 says this in so many words. It draws diagonal cross-ties in
several sections and says nothing about how they are measured for the 300 mm
limit; the owner read the rule as applying between branches parallel to the
face, and that reading is recorded here as a ruling, not as a citation.


---

## R30 — a diagonal leg bridges the gap it crosses, measured by the hypotenuse

**Decided by the owner** (#146), on seeing the tool demand a cross-tie the
engineering did not need:

> from engineering p.o.v the tie bar is not neccery … it already tied with
> triangular stirrup so no neccery calculation and if neccery i think
> hypotonus is the right call

and, asked what the hypotenuse is measured from:

> from column numbers  sqr hypotenus = sqr 152 + sqr 146

### What it refines

**R29 stands: a diagonal leg is not a branch AT a coordinate.** It does not sit
at a `u` or a `v`, and crediting it with one is what the bounding-box reading
did wrong.

R30 answers the question R29 left: a diagonal is still steel, and it still
holds the core at both its ends. So it **bridges** the gap it crosses — it
supports at its two endpoints — provided it is short enough to be doing that
job.

### The measure

The hypotenuse of the two **clear** distances between the bars the leg joins:

    span = sqrt( (Δu − bar) ² + (Δv − bar) ² )

On the verification column, bar 1 to bar 9 is 167.6 mm across and 161.7 mm up,
less one 15.9 mm bar each way — **152 and 146, giving 210 mm**, which is the
owner's own arithmetic.

**Clear, not centre to centre**, because section 6.1's other test already works
in clear distances (`Gap.clear_mm` is centre to centre minus one bar diameter).
One currency, not two.

**Between the BARS, not between the tie's vertices.** The same diagonal
measures 199 × 192 between grown centreline vertices and 152 × 146 between the
bars. R30 is about the second pair, so the span is recorded by `resolve_tie` —
the only place that knows both — as `ResolvedTie.leg_clear_spans_mm`, rather
than re-derived by a reader that has only the polygon.

Each component is **clamped at zero**: two bars level with each other are zero
apart on that axis, not minus a bar diameter. Unclamped, the square put the
15.9 mm back and a purely horizontal leg reported a span it does not have.

### What it changes

On the column that prompted it — `T 1 9 3` and `T 8 6 4`, 450 × 600 — the
perimeter tie's two vertical legs are 360 mm apart and no tie puts a vertical
leg between them. Four diagonals cross that gap at **210 mm** each, so the
arrangement stands on its own and **the cross-tie is no longer demanded**.

The limit still bites where it should: on a four-bar column the same triangle's
diagonal spans **568 mm** clear, far past 300, and the 360 mm gap stays
unbroken.

### What is NOT claimed

That Figure 13-3 states this. It draws diagonal cross-ties in several sections
and says nothing about how they are measured for the 300 mm limit. This is the
owner's reading of what the limit is *for* — the unsupported span between
points where the core is held — and it is recorded as a ruling, like R29, not
as a citation.


---

## R31 — the hook closure sits at a triangle's apex and a rectangle's top

**Decided by the owner** (#149):

> the hook closure shall always be at the top of rectangle in our case bar 1
> and 6 whether hook is 90 or 135

and, asked where exactly — bar 1 is the section's **bottom**-middle and bar 6
the **top**-middle, so the two halves of the sentence name different points —
the owner chose **the triangle's apex, and the rectangle's top**.

### What the closure is

`vertices[0]`. `_closed_loop_uv_segments_mm` winds so `curves[0]`'s start and
`curves[-1]`'s end coincide there, and that coincident point is where both hook
tails attach. Moving the closure means starting the vertex list elsewhere.

| tie | before | after |
|---|---|---|
| perimeter | bottom-left corner | top-left corner |
| `T 1 9 3` | bar 3's vertex | **bar 1's** vertex |
| `T 8 6 4` | bar 4's vertex | **bar 6's** vertex |

### The rule

- **A triangle closes at its apex — the vertex opposite the LONGEST leg.** The
  longest side is the base; that is how a triangle is drawn and how the owner
  named theirs. `T 1 9 3` has legs of 398, 277 and 277 mm, so the 398 mm leg
  between bars 9 and 3 is the base and bar 1 is the apex. `T 8 6 4` gives bar 6
  the same way. **Both are exactly the bars the owner named**, which is the
  check that the rule and the example agree rather than merely coinciding.
- **A rectangle closes at its top.** Of the two top corners, the left.
- **Independent of hook type.** The ruling says "whether hook is 90 or 135",
  and nothing in the closure reads the hook.

### What is a choice rather than a rule

**The left of the two top corners.** A rectangle has two, the owner ruled "the
top", and something has to break the tie deterministically or the closure moves
between runs. Left keeps the `u` convention the closure already had when it sat
at the bottom-**left**, so only the half that was actually ruled on moves.
Recorded here so it is visible as a default, not mistaken for the ruling.

### Rotation, never reversal

The load-bearing constraint. **R21 fixed `RebarHookOrientation.Left`/`Left`
against the DIRECTION the curves run**, not against which vertex is first, and
#145 already had to fix a triangle that wound whichever way the engineer typed
it. Reversing a vertex list to bring a different corner to the front would
point both 135° tails out of the concrete — the exact defect R21 exists to
prevent.

`rotate_to_closure` rotates and never reverses, and the winding is asserted
unchanged for **every** starting position rather than argued for in a comment.

### Its collision with §6.3, stated before it is met

§6.3 alternates the closure between levels up the cage. **A triangle has no
second corner to alternate to under this rule** — its apex is one vertex, fixed
by its geometry. That is not resolved here; it is written down so #92's
alternation gap is entered knowing it.
## R32 — a triangle does not alternate

**Decided by the owner** (#149), on the collision R31 recorded rather than
resolved:

> no alter in triangle

### The collision it closes

Section 6.3 moves the hook corner between consecutive levels, and
`TieLevel.mirrored` carries that as a level-indexed mirror map (#70 proved it
is ONE rebar set plus a per-bar transform, never a set per level).

R31 then fixed a triangle's closure at its **apex** — the vertex opposite its
longest leg. A triangle has three vertices and only one of them is the apex, so
**there is nowhere to alternate to** without either moving the closure onto the
base, which R31 forbids, or mirroring the whole triangle, which is a different
tie.

### The rule

- **A triangle's closure stays at its apex on every level.** It does not
  alternate.
- **A closed loop still alternates**, unchanged. Four corners give section 6.3
  somewhere to move to, which is the case the rule was written for.
- A cross-tie has no closure at all — one leg, two ends, no corner — so the
  question does not arise for it either. That half was already open in #92 and
  this ruling does not disturb it.

### Where it shows

Alternation is **modelled and reported, not yet placed**: `TieLevel.mirrored`
exists, the report lists which levels carry M, and the placer does not read it
(the gap tracked by #92). So the only thing that could be wrong today was the
report's own sentence, which promised alternation without qualification.

It now carries R32 beside it. Stated **unconditionally**, because it is a rule
rather than a fact about a particular ladder: `tie_level_section` takes the
ladder alone, the mirror map is the same whatever shapes the ties are, and the
ladder does not know which they are. Making the line conditional would mean
threading the tie list into the ladder's own section to say something that is
true regardless.

### What this leaves for #92

The placer still does not apply the mirror. When it does, **it must skip
triangles** — and that is now a stated rule with a test behind it rather than
something to be rediscovered from the geometry.


---

## R33 — a batch places every group correctly and reports the split

**Decided by the owner** (#104), after the tracer bullet showed that a family
type does not determine the cage.

### What was asked

Five `450 x 600mm` columns in the verification model share family, type, `b`,
`h`, cover, rotation and orientation, and **two of them sit on the same two
levels with different clear heights** — 2700 where a beam cuts the column, 3000
where it runs the full storey. Clear height drives the tie ladder, so one
selection genuinely contains two different cages.

Asked what should happen when a selected type splits, the owner chose: **place
each group correctly, and report the split.**

### The rule

- The run **proceeds**. Each group gets the ladder its own extent requires.
- **The report names the groups**, their clear heights, and which columns fell
  in each. A reviewer sees that one selection produced two cages by *reading
  the report*, not by noticing a tie count in a 3D view.
- The **type stays the filter the engineer selects with**; the **batch key is
  the computed extent** — clear height, and whether a top support was found.
- A group of one is not an error.

### What was rejected, and why it is worth recording

**Refusing the split** — making the engineer narrow the selection until it is
one cage — was the safest-looking option and would have matched how this tool
already refuses out-of-scope columns.

It was rejected because **a floor with a beam over some columns and not others
is the normal case, not the exceptional one**. Refusing it would make the
common situation the laborious one, and a tool that is laborious in the common
case gets worked around rather than used. The report carries the burden
instead.

**Asking before placing** was also rejected: it puts a click between the
engineer and the thing they already asked for, and the information it would
show is the same information the report shows afterwards.

### What this costs, stated plainly

The engineer learns there were two cages **after** the steel exists. That is
the accepted trade, and it is why §4 of
[`specs/column-batch-placement.md`](../../specs/column-batch-placement.md)
makes the group listing a requirement of the report rather than a nicety —
the ruling is only safe if the report is actually readable.

See also **R23**, which this stretches: "show the count, then replace" is a
sentence for one column and a table for forty.


---

## R34 — WITHDRAWN: a column that crosses a level stays refused

**Proposed and then withdrawn by the owner, in the same session** (#155,
closed unimplemented). Kept in the ledger as a withdrawal rather than deleted,
because the reasoning is the standing answer to “why not just place it
anyway?”

### What was proposed

On the two columns #153's first live batch excluded — 424290 and 424284 in
`ColumnRFT.Trail`, base offset −2500 and top offsets +1000 and +1500, so Level
1 at 0 mm falls strictly inside them:

> you place rebar no matter its instances and then report that after placement

`multi_storey_refusal` would have become a finding: detail the column, name the
crossed level and what the cage lacks there.

### Why it was withdrawn

> you know what single story column should be the right call ... due to
> construction sequance

A column is not cast in one piece through a floor. The pour stops at the
soffit, a construction joint forms there, and the next storey follows the
floor. A one-segment cage spanning a level cannot honour three things at once:

1. **the splice belongs above the joint** — bars lap just above the floor,
   which is exactly what §6's splice protrusion into the segment above models;
   a spanning cage laps wherever its ladder happened to end;
2. **confinement is required either side of the joint** — a continuous ladder
   runs ordinary middle-zone spacing through the one place it matters most;
3. **it cannot physically be placed** — the beam cage and the floor formwork
   occupy that elevation.

So `multi_storey_refusal` is not a gap standing in for a missing feature. It is
the tool declining to produce a cage that does not match how the column is
built, and its message already names the action: split at each level and detail
the storeys separately. The live trigger is a **model** condition — those two
columns are drawn through Level 1.

### What this leaves open, deliberately

A level datum with **nothing framing into it** is not a construction joint, and
refusing there is a false positive. Still refused today, on the grounds that a
stray datum is a two-second fix in the model and a wrong cage is not — to be
revisited against a real project if it appears in one.

**Nothing in the code changed.** §0/C2 and `specs/column-batch-placement.md`
§7 stand as written, and no amendment to either was merged.

---

## R35 — `L_D` is stated, never computed

**Decided by the owner**, setting up the roof addendum's implementation.

The roof termination's development length is a **raw input**. The owner's own
clarification, given while this was being written:

> l_d for roof column can be calculated as in beam like 60 column bar diameter
> or 50 or whatever

So the **multiplier is the input**, and `L_D = multiplier × bar diameter` is
arithmetic on it — exactly the beam tool's form. A plain millimetre value is
accepted too, for the case where the engineer has the number and not the
multiple.

**What the tool never does is choose the multiplier.** That is the whole of
§9's discipline for the splice length `L_s` — *“raw user input, NEVER
auto-calculated by the tool”* — and 50 against 60 is a detailing decision, not
a default to inherit.

`RFT.lib/rft/core/anchorage.py`'s `development_length(diameter_mm, multiplier)`
is that multiplication and may be reused for it. Its **defaults must not be**:
`DEFAULT_LD_BTM_MULTIPLIER = 55` and `DEFAULT_LD_TOP_MULTIPLIER = 60` are the
beam spec's numbers for top and bottom bars in bending, and a vertical column
bar anchoring into a roof slab is neither. Reuse the multiply; state the
multiplier.

What IS worth reusing from that module is its **cap discipline** — `a` clamped
so `b` can never fall below the 200 mm minimum bend leg, and a `ValueError`
rather than a negative leg reaching the Revit API. §1's `a + b = L_D` has
exactly the same failure mode with a small `L_D`.

---

## R36 — the engineer states that a column is at roof level

**Decided by the owner.** A checkbox, not an inference.

The model cannot distinguish *“this is the roof”* from *“the storey above is
not modelled yet”*, and the two demand opposite detailing: a splice protruding
into the segment above (§9) versus a bend into the slab (this addendum §1).
Guessing wrong swaps one for the other and **looks correct in the browser**,
which is the failure mode this project exists to refuse.

So the roof condition is **stated**. An unticked box means the ordinary §9
splice, unchanged, whatever happens to sit above the column.

---

## R37 — the roof slab's thickness and cover are READ

**Decided by the owner.** From the slab element above, never typed.

§1 measures `a` from the slab's bottom face up to (thickness − cover). Both
numbers come from the element the upward support search already locates — that
search currently hands back only a z, and must be extended to hand back the
element too.

This is **A2** applied where it has always applied: cover is read from the
model, never typed, so a typed value can never disagree with what will be
built.

### The default under it, stated because it was not ruled on

**If the upward search finds no slab, the tool refuses**, naming what it looked
for. A roof column with no roof above it is a modelling problem, and falling
back to typed values would turn it into a detailing number nobody re-checks.
Recorded here as a default rather than as part of the ruling.


---

## R38 — a slab with NO cover set: the engineer types it, and only then

**Decided by the owner**, on #161's measurement: the roof slab over column
424596 answers every cover parameter — `CLEAR_COVER_TOP`,
`CLEAR_COVER_BOTTOM`, `CLEAR_COVER_OTHER` — with **0.0 mm**.

### Why zero is the dangerous answer

Not because it fails. **Because it succeeds.** The parameter is present and
readable, so a check asking “did I get a number?” is satisfied, and §1 then
computes

    a = thickness - cover = 300 - 0 = 300 mm

which lays the bar's horizontal leg **on the top surface of the slab** —
outside the concrete, nothing over it. A cage that looks placed and is
exposed. Zero is not a cover; on a `Generic 300mm` floor it means nobody set
one.

### The rule

- **The model wins whenever it has something to say.** A slab with a real
  cover is READ, exactly as R37 and A2 require, and the engineer cannot
  override it.
- **Only when the slab's cover reads zero** does a typed field open. This is
  the narrow exception, not a general input.
- **An empty field is a refusal, never a default.** The tool has no cover of
  its own to fall back on, and inventing one would be the very substitution
  A2 exists to prevent.
- **The report must say which it was**, naming the slab: read from Floor
  424637, or typed because Floor 424637 has none set. A reviewer has to be
  able to tell a measured cover from a stated one **by reading the report**,
  which is the same standard §4 sets for a flagged free edge.

### The alternative that was rejected, and why it is worth recording

Falling back to the **column's own** cover was considered. It needs no
modelling work and places something plausible — which is precisely the
objection: it is a typed-equivalent number wearing a read one's clothes, and
it is silently wrong wherever the slab genuinely differs from the column. A
typed field at least appears in the report as a typed field.

### Where this leaves A2

A2 — *cover is READ, never typed* — assumed the model has something to read.
R38 does not weaken it: it names the one case where that assumption fails,
and keeps the exception visible in the report rather than letting a zero
pass as a measurement.


---

## R39 — it is the TOP FLOOR case, and the slab above is a Floor

**Decided by the owner**, closing #161's last open item:

> i know that roof is modelled as floor and that is the right call for
> structural elements so you can name it top floor case

### What it settles

**`OST_Roofs` does not need adding to `SUPPORT_CATEGORIES`.** #161 measured
the slab over column 424596 coming back as a **`Floor`** (`Generic 300mm`),
found by the shipped category list with no change. That was recorded as
“still open, because a model using an actual Revit Roof was never tested”.
It is now closed by **practice rather than by measurement**: a structural
model puts a structural slab there, and a Revit Roof is an architectural
element with no structural role. The tool details structural models.

This is a deliberate narrowing, so it is written down: **a column under a
Revit `Roof` element will find nothing and be refused**, and that refusal is
correct — it means the thing above is not a structural slab.

### The terminology

**“Top floor”, not “roof”**, in the UI and in the report. The condition is
“there is no storey above this column”, and what closes it is a **floor** —
the same element class as every other storey's. Calling it a roof invites
the reader to look for a roof element that structurally is not there.

`specs/column-roof-termination.md` keeps its filename: it is cited by #77,
#102, #103, #161, several verification documents and the amendments above,
and renaming a file to improve a word would break every one of those
references for no gain. **The prose is what the reader sees**, and that is
what changes.

### What does NOT change

R35, R36, R37 and R38 stand exactly as written. So does §1's `a + b = L_D`
and §2's per-face rule — this is a naming and scoping ruling, not a
detailing one.
---

## R40 — `L_D` is the DEVELOPED centreline length, not the nominal legs

**Decided by the owner**, shown both options drawn before ruling:

> ld is the development length

### What #161 measured

Two curves went into `CreateFromCurves` — 500 mm and 400 mm meeting at a
sharp corner — and **three** came back: `Line 453.7`, `Arc 72.8`,
`Line 353.7`. Revit fillets the corner, takes the bend's **tangent** off both
legs and puts an arc between them. The bar handed 900 mm of nominal leg
develops **880.2**.

### The rule

`L_D` is a length **of bar**, so it is measured **along the bar**. The tool
therefore lengthens the horizontal leg by what the fillet eats:

    Δ = 2t - arc = r(2 - π/2)  ≈ 0.4292 r      (90° bend)
    b = L_D - a + Δ

`a` is **not** free — §1 fixes it as the slab's thickness less its cover — so
the whole correction lands on `b`.

At the measured `r = 46.3 mm` that is **19.87 mm**, which reproduces the
probe's `900 → 880.2` to the decimal. The formula is not fitted to the
measurement; it agrees with it.

### Two things that follow, and both matter

1. **`r` is read from the BAR TYPE, never hardcoded.** The tool already reads
   a bar type's bend diameter for tie corners
   (`rft.revit.bar_types.bar_type_bend_diameter_mm`). A 25 mm bar bends on a
   bigger radius and loses more. Baking in 19.87 would be right for 13M and
   wrong for every other bar in the schedule.
2. **It is A1's own math.** `t = r / tan(θ/2)`, which at 90° reduces to
   `t = r` — the same relationship `rft.core.column_ties` already applies at
   a tie's corners. The top-floor bar is that relationship at a different
   corner; nothing new is invented, and the two must not drift apart.

### A leg shorter than the tangent is refused

A bend needs `t` of straight leg on each side to turn through. A leg below
that is not a tight bend — it is geometry that cannot exist, and the free-edge
cap in §2 can drive `b` there on a narrow face. Refused, naming the leg.

### What the report must say

Where a free edge already costs anchorage, the fillet costs a little more, and
both belong in §4's per-bar line — `achieved` is what the BUILT bar develops,
not what was asked for.


---

## R41 — the available RUN governs, in every direction, for every reason

**Decided by the owner**, on a case §2 does not cover:

> what if column is not edge or corner with is interior but was put like 50 cm
> from each side what if ld still cannot be modelled all as 500 mm is not yet
> has the free room for bent bar to run

### The hole this closes

§2 is **binary**: slab continues → full `L_D`; free edge → cap to the column's
own width. An interior column 500 mm from the slab edge is neither. The slab
*does* continue, so the tool takes the full-`L_D` branch and asks for a 704.8
mm horizontal leg into about 475 mm of real room — **the bar leaves the slab
by some 230 mm**. That is exactly the failure the free-edge cap exists to
prevent, occurring in the branch that has no cap.

“Interior” was never the right question. A column 5 m from the edge and one
500 mm from it are both interior; only one has room.

### The rule

**Every direction carries an available RUN, and the run always governs.** The
three cases stop being branches and become one number with three sources:

| case | what limits the run |
|---|---|
| free edge | the column's own width − 2 × cover (§2's existing cap) |
| interior, near an edge | distance to the slab edge − the slab's edge cover |
| deep interior | nothing — the run exceeds what `L_D` needs |

- **The bend takes the direction with the most room**, not merely one that has
  slab. That strengthens §2's corner-bar rule rather than replacing it: with
  room everywhere, every direction still achieves full `L_D` and the choice
  remains free.
- **A capped leg places and reports**, exactly as a free edge already does —
  the owner's ruling. Never steel outside concrete, and never a silent
  shortfall.
- **The report must distinguish WHY** a run was short: a free edge the
  engineer flagged, or a slab edge the tool measured. They are different
  facts, and only one of them is the engineer's own statement.

This is §2's stated intent — *“replaces separate Interior / Edge / Corner
cases”* — carried one step past where it was written.

---

## R42 — the run is MEASURED from the slab, not typed

**Decided by the owner**, same exchange.

The distance to the slab edge is read from the floor's own boundary, along the
bend direction, less the slab's edge cover. Not a field on a tab, and not an
extension of §3's pick-the-exception: a typed run is a number that is easy to
forget on the one column where it matters, and A2's discipline is that the
model is read.

**This needs a probe before it is built.** How to obtain a `Floor`'s boundary
reliably — sketch profile, top-face edge loops, or a horizontal ray — is
unmeasured, and openings and non-rectangular slabs are exactly where a
plausible-looking API shape goes wrong. No implementation until a transcript
says which query answers.

Until that lands, `rft.core.column_roof` takes the run as a **parameter**: the
math above is complete and testable, and the adapter supplies the number once
the probe says how to get it.


---

## R43 — the top-floor inputs live in their OWN window

**Decided by the owner:**

> ui will be part of column tool if i triggered or check roof column it deploy
> new window for it

### The shape

- The **Column tool is unchanged** for an ordinary column. It is one tool, not
  two, and a top-floor column is a *condition* (see the addendum's opening
  line), so nothing new appears on the existing tabs beyond the checkbox R36
  already requires.
- **Ticking that checkbox opens a second window** carrying every top-floor
  input: §5's `L_D` multiplier (R35), R38's cover field when — and only when —
  the slab reads zero, and §3's pick-the-exception.
- Unticking it closes that window and the plan reverts to §9's ordinary
  splice. **No top-floor input survives an unticked box**, or the tool would
  carry state the report does not show.

### Why a window rather than a fifth tab

The owner's call. The trade is worth recording because it is not free either
way:

- **a window** keeps the main tool exactly as it is for the great majority of
  columns, which are not top-storey, and keeps a rarely-used set of inputs out
  of the common path;
- **a tab** would have avoided a second modeless window entirely, and with it
  the state-sync and focus questions below.

### The constraint that makes this non-trivial

**A pick must run through `execute_in_revit_context`**, and a pyRevit modeless
window needs all three of: modeless, `execute_in_revit_context`, and a
persistent engine — miss one and it fails **silently**. §3's face picking is
the tool's first interactive selection, and it will be driven from the second
window. #103 measured the other half of this: `PickObjects` runs with
`IsModifiable = False` from the pushbutton path and cannot start from inside
an open transaction.

### The rule that keeps the two windows honest

**The second window owns the inputs; the main window owns the plan.** The
second window hands back one object and holds no plan state of its own, so
there is exactly one place a top-floor input can be read from. Two windows
each holding a copy is how they drift.

**Apply stays refused while the top-floor inputs are incomplete**, and says
which one is missing — the same discipline every other refusal in this tool
follows.


---

## R44 — a bar bends OUT OF ITS OWN FACE, never sideways along it

**Decided by the owner**, on a measurement that removed the alternative.

### What #173's probe measured

The same `+Hand` bend was built three times with different `normal`s
(transcript: `docs/column/verification/issue-173-bent-array-transcript.txt`):

| `normal` | result |
|---|---|
| `Hand` — PARALLEL to the bend | **internal error** |
| `Facing` — perpendicular | **built**: Line 653.7, Arc 72.8, Line 353.7 |
| `Z` — vertical | **internal error** |

**So `normal` is not free.** The two curves do NOT define the bend plane on
their own; the normal must be perpendicular to it, and Revit refuses anything
else. An arrayed bent set failed for the same reason (part 3).

### The collision this creates

`normal` is now load-bearing twice, from two different tickets:

- **#131**: `SetLayoutAsNumberWithSpacing` arrays the set **along** the
  normal. Handing it the perpendicular arrayed every run across its own face
  and put two bars 11.7 mm apart at two corners.
- **#173**: the normal must be **perpendicular to the bend plane**, or the
  call fails outright.

A run whose bend ran ALONG its own step axis would need the normal to be both
that axis and perpendicular to it. Impossible, and it is why part 3 failed.

### The rule

**Each face run may bend only along the two directions perpendicular to its
bars' step axis** — out of its own face, or back into the column. R41 is
unchanged in substance: it still takes whichever of the two has the most room.

### CONFIRMED ON THE HOST (#183, 2026-09-18)

The paragraph below was an **argument**, not a measurement: it reasoned
that the array axis and the bend-plane normal become the same vector, so
one argument satisfies both. #183 built it.

With `normal = Hand` and the bend toward `+Facing`, a three-bar set
arrayed at 150 mm gave **three curves on every bar** (Line 653.7, Arc
72.8, Line 353.7 — identical to #173 part 1's single bar) at **0.0 /
150.0 / 300.0 mm** along the step axis. The control bending along `+Hand`
still raised *"An internal error has occurred."*, so the rig was capable
and the refusal is Revit's. Exchanging the axes gave the same result, so
it is a property of the geometry rather than of Hand.

Write-up and transcript:
`docs/column/verification/issue-183-bent-across.md`.

### Why this costs nothing

With the bend `b` perpendicular to the step axis `d`, the bend plane is
`{Z, b}` and its normal is the horizontal perpendicular to `b` — which **is**
`d`. The array axis and the bend-plane normal become the same vector, and the
placer already passes the step direction. **Both constraints are satisfied by
one argument, and no placer change is needed.**

It is also how bars are detailed by hand: a bar on a face bends out of that
face, not sideways along it.

### The consequence the plan must carry

**A termination is now PER RUN, not per column.** Four face runs have four
step axes, so up to four different bends — the bars on the `+Facing` face bend
±Facing, those on the `+Hand` face bend ±Hand. #172's `RoofTerminationPlan`
carries one termination for the whole column and must become one per run.
§4's report follows: a line per run, not a line per column.

### Still open, and measured enough to name

**A bent bar has FIVE handles; a straight one has four.** `_pin_to_host_faces`
— R22's whole correctness argument, and the thing #92 measured going wrong by
12 mm — was written for four handles that share one `(u, v)`. What the fifth
is, and whether pinning it is right, is not answered by this probe: the
candidate query raised inside the probe's own reporting. **That is the last
unknown between here and placed steel.**


---

## R45 — the bent bar's FIFTH handle is never pinned

**Measured, then ruled**, on #173's second probe run (transcript:
`docs/column/verification/issue-173-bent-array-transcript.txt`).

### What the handles actually offer

| handle | straight bar | bent bar |
|---|---|---|
| 0 | ±Hand — governs `u` | ±Hand — identical |
| 1 | ±Facing — governs `v` | ±Facing — identical |
| 2 | ±Z | ±Z |
| 3 | ±Z | ±Z |
| **4** | — | **±Facing** — the horizontal leg's FAR END |

Both bars were born exactly where they were asked for, `(u, v) =
(150.0, 200.0)`, so nothing about the bend disturbs creation. **The first
four handles of a bent bar are indistinguishable from a straight bar's**,
which is why R22's pinning transfers unchanged.

### The defect this prevents

`_pin_to_host_faces` pins EVERY handle whose candidate face is the near face
on the axis it governs, using the SEED's own `(u, v)`. Handle 4 offers the
same axis the horizontal leg runs along — so it would be pinned to cover
distance from the near face, **using a coordinate that belongs to the
vertical leg hundreds of millimetres away**.

The horizontal leg would be dragged back onto the bar's own line and `b`
would be destroyed — in a cage that still looked placed. That is the same
failure mode as #92's 12 mm drift, one axis further along.

### The rule

**At most one handle per horizontal axis, the first offered.** A straight
bar is unaffected: its `u` and `v` handles are different axes and both are
still pinned, while its two vertical handles offer no horizontal face and
were already left alone. A bent bar's fifth handle repeats an axis, and is
skipped.

### Why “the first” rather than “the nearest”

Revit returns handles in an order it does not document, and the API offers no
position for a handle — only its candidates. “First” is therefore what can
actually be implemented, and it is correct because the vertical leg's handles
come first on every bar measured. **Recorded as a stated default**: if a
future Revit orders them differently, this is the line that breaks, and it
will break loudly because the bent bar's leg will move.

---

## R46 — R40's bend radius is the CENTRELINE radius, and it is measured

**Measured, not decided.** Revit 2024 build 24.3.40.26, document
`ColumnRFT.Trail`. Write-up: `docs/column/verification/issue-176-bend-radius.md`.

R40 said the fillet radius "comes from the BAR TYPE, never from a typed
input". Nothing read it — every test passed a number in — and the second
window (#176) is the first caller that must obtain one. So it was measured
before it was written, per CONTEXT.md's rule against guessing an API name.

### The rule

```
centreline bend radius = (StandardBendDiameter + BarNominalDiameter) / 2
```

`StandardBendDiameter` is the bend diameter to the bar's **inner face**;
the centreline Revit returns runs half a bar diameter outside it. Exact on
all four types built and read back:

| type | nominal | StandardBend | measured arc | implied radius |
|---|---|---|---|---|
| 13M | 12.70 | 80.00 | 72.806 | 46.350 |
| 19M | 19.10 | 115.00 | 105.322 | 67.050 |
| 12T | 12.00 | 72.00 | 65.973 | 42.000 |
| 16T | 16.00 | 96.00 | 87.965 | 56.000 |

### Why this is not a detail

`StandardBendDiameter / 2` — the obvious reading — gives **40.00 mm** for
13M against the measured **46.35**: a **13.7% error in the fillet loss**.
That loss is SUBTRACTED from the achieved development length §4 certifies,
so the error runs in the direction of **claiming more development than was
built**. `StirrupTieBendDiameter` is ruled out decisively by 12T and 16T
(155.00 against measured 42.00 and 56.00).

### Stated, not proven

`StandardHookBendDiameter` equals `StandardBendDiameter` on all four types
measured. `StandardBendDiameter` is used because this is a **bend, not a
hook** — an argument from meaning rather than from the data. A bar type
where the two differ would settle it.

### Corroboration

13M's arc of 72.806 mm reproduces the 72.8 mm #161 read months earlier, on
a different probe, for a different question.
