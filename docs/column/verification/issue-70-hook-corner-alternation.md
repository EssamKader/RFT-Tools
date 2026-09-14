# Issue #70 — §6.3 hook-corner alternation, verified on a live host

**Status:** ANSWERED. One shape-driven `Rebar` set **can** rotate the hook
corner per level. Option A (one set) wins on every measured axis. One
**defect risk** was found that must be designed around, not discovered later.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26 |
| Document | `ColumnRFT.Trail.rvt` |
| Test column | id `421967`, `450 x 600mm` |
| Tie bar / hook | `10M` (id 53672) / `Stirrup/Tie - 135 deg.` (id 53733) |
| Writes | all inside rolled-back `SubTransaction`s — model left with **0** rebar |
| Date | 2026-09-14 |

> ## ⚠️ CORRECTION (from #78) — read before copying any coordinate here
>
> Every experiment on this page used **`RebarHookOrientation.Right`**, which
> #78 later proved bends the 135° hook **out of the concrete core**: the free
> end lands at `v = -351.4` against a tie half-height of 260 mm, projecting
> 91 mm into cover and air. **Column ties must use `Left`** (derived from the
> loop's winding, not hardcoded).
>
> This page's **conclusions stand** — rotation storage, element counts,
> timings and the layout-change corruption do not depend on hook orientation.
> But the hook coordinates below describe an incorrectly oriented hook and
> must not be treated as a model of correct detailing.
>
> **Superseded outcome:** §6.3 requires an **adjacent** corner (owner's
> ruling, 2026-09-14), which the 180° rotation on this page does **not**
> deliver — it gives the diagonal. A reflection does, on the same
> one-set/one-element terms. See `issue-78-mirrored-tie-adjacent-corner.md`.

---

## 1. The API surface (by reflection, not by memory)

**Hooks are set-wide.** Every hook member is indexed by *end*, never by bar:

```
SetHookTypeId(int end, ElementId)          GetHookTypeId(int end)
SetHookOrientation(int iEnd, RebarHookOrientation)
SetHookRotationAngle(double, int iEnd)     GetHookRotationAngle(int iEnd)
RebarHookOrientation = { Left, Right }     // NOT a corner selector
```

So the hook **type and orientation cannot differ between levels** in one set.
That is not what §6.3 asks for, though — it asks for the hook *corner* to
move, which is a property of where the tie's start point sits, i.e. the
shape's placement.

**Per-bar placement, on the other hand, is exposed:**

```
Rebar.MoveBarInSet(int barPositionIndex, Transform moveTransform)
Rebar.GetMovedBarTransform(int barPositionIndex)
Rebar.ResetMovedBarTransform(int barPositionIndex)
RebarShapeDrivenAccessor.GetBarPositionTransform(int barPositionIndex)
```

Also present and useful later: `SetBarIncluded`, `DoesBarExistAtPosition`,
`SetBarHiddenStatus`, `GetTransformedCenterlineCurves(..., barPositionIndex)`.

---

## 2. `MoveBarInSet` accepts a ROTATION, not only a translation

The method name suggests translation. It is not limited to one. Applying
`Transform.CreateRotationAtPoint(XYZ.BasisZ, π, tieCentre)` to bar 1:

```
MoveBarInSet(1, ROTATION 180) ACCEPTED (no throw)
GetMovedBarTransform(1): BasisX=(-1,0,0)  BasisY=(0,-1,0)   rotationDiscarded = False
bar0 hook start : (-265.0,  835.6)   unchanged
bar1 hook start : ( -26.7, 1538.3)   <- exact reflection through the tie centre
```

The basis vectors come back negated, so the rotation is **stored, not
flattened** to a translation. Bar 0 was untouched, confirming the transform
is genuinely per-bar.

### Why 180° and not 90°

A 450 × 600 rectangle is **not** invariant under a 90° rotation — rotating
the tie 90° would place it outside the column. **180° is the only rotation
that maps a rectangular tie onto itself**, and it moves the hook from one
corner to the **diagonally opposite** one (NE → SW).

> **Open question for the spec, flagged rather than guessed:** §6.3's
> illustrative example is "North-East → North-West", i.e. an **adjacent**
> corner. 180° delivers a **diagonal** corner. The rule as written says the
> hook "must rotate to a DIFFERENT corner", which SW satisfies — but if
> adjacent-corner alternation is specifically intended, a rotation cannot
> deliver it on a rectangular tie and a mirrored transform would be needed
> (untested, and mirroring a chiral 135° hook may not be legal). **This
> needs an owner ruling before the placer is written.**

---

## 3. Option A vs Option B — measured, on 25 ties at 100 mm

| | **A: one set + `MoveBarInSet`** | **B: one `Rebar` per level** |
|---|---|---|
| `Rebar` elements in model | **1** | **25** |
| bars placed | 25 | 25 |
| wall-clock | **111 ms** (62 ms create+layout, 49 ms for 12 rotations) | **828 ms** |
| schedule | **one line item**, `Quantity = 25` | 25 line items |

Option A is **7.5× faster and 25× fewer elements**, and keeps the rebar
schedule readable. Alternation verified across the set:

```
hook XY: b0=(-265.0, 835.6)  b1=(-26.7, 1538.3)  b2=(-265.0, 835.6)  b3=(-26.7, 1538.3)
b0 == b2 : True    b1 == b3 : True    b0 != b1 : True
```

### Ruling

> **Option A.** One shape-driven `Rebar` set per tie definition, with
> `MoveBarInSet(i, rotation180)` applied to alternate bar positions.
> `column_layout` emits **one tie definition plus a level-indexed rotation
> map**; it does **not** emit fully-resolved per-level tie instances.

---

## 4. THE DEFECT RISK — a layout change silently scrambles the alternation

This is the finding that matters most, and it is not in any documentation.

Per-bar transforms are stored against **bar position index**, and those
indices are **not** re-mapped when the layout changes. Observed:

```
after rotating odd bars (6 bars)   : F,T,F,T,F,T        <- correct, alternating
after SPACING change 150 -> 200 mm : F,T,T,F,T,F        <- CORRUPTED
after COUNT change 6 -> 9          : F,T,T,F,T,F,F,F,F  <- corruption persists,
                                                            new bars unrotated
```

After a mere spacing edit, bars 1 and 2 are **both** rotated while bar 3 is
not. The alternation §6.3 requires is gone, the model still looks plausible,
and nothing throws.

### Mandatory consequences for the implementation

1. **Per-bar transforms must be applied only AFTER the final layout is set.**
   Never set layout after applying rotations.
2. **Any layout change must reset and re-apply the entire rotation map** —
   `ResetMovedBarTransform` across all positions, then re-apply from the
   level-indexed map. Never mutate spacing and assume the rotations followed.
3. This is a **prime AST-guard candidate**, and a mutation-provable one:
   reorder the calls so the layout is set after the rotations, and the guard
   must fail. Per `REUSE_GUIDELINES.md`, a guard that has never been shown to
   fail has only been written, not tested.

---

## 5. Incidental findings

**Hook types available in this template** (feeds #74):

```
53648  Standard - 90 deg.              90
53730  Standard - 180 deg.            180
53731  Stirrup/Tie - 90 deg.           90
53733  Stirrup/Tie - 135 deg.         135
93576  Stirrup/Tie Seismic - 135 deg. 135
```

A **135° `Stirrup/Tie` hook exists and was used successfully** with
`RebarStyle.StirrupTie`. This is directly relevant to the beam project's
recorded load-bearing unknown ("if `RebarStyle.StirrupTie` disallows 180°
hooks, the mild-steel hook decision must be revisited") — at least for 135°
on a tie, the combination is legal in Revit 2024. Note a dedicated
**Seismic** 135° variant also exists, which §7's rationale may prefer.

**Bar types are Canadian metric** (`10M`, `13M`, `16M`, `19M`, `22M`, `25M`,
`29M`, `32M`, `36M`, `43M`, `57M`) — **no ECP sizes** (T10/T12/T16…) in this
template. Spec §1 reads Ø and fy from the selected `RebarBarType`, so the
tool will offer whatever the project contains. Whether the production
template needs ECP bar types loaded is a project-setup question, not a code
one, but it will surface the first time a user picks a bar.

---

## 6. Still unverified

- **Adjacent-corner alternation** (a mirror rather than a 180° rotation) is
  untested, and may be illegal for a chiral hook. Blocked on the §6.3 ruling
  above.
- Whether a moved bar's rotation survives **file round-trip** (save/reopen)
  was not tested — only in-session edits.
- Interaction with `SetBarIncluded` / suppressed first-or-last bars is
  untested; both shift what a bar *position index* means.
- Only the **outer perimeter tie** was tested. An inner subset tie (§6.2) is
  a different closed loop and was not created — its behaviour under
  `MoveBarInSet` is assumed identical, **not observed**.
- All of the above was measured on **one** column in **one** document on
  Revit 2024. `SHAPE UNVERIFIED` discipline still applies.
