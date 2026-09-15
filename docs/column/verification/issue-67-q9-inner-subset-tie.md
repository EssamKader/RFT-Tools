# §6.2 inner subset tie — verified on a live host (ledger Q9)

**Status: ANSWERED.** Overlapping closed tie loops work as §6.2 describes:
two `Rebar` sets on one host, each a closed rectangle around its own bar
subset, each independently reflectable for §6.3's hook alternation.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26 |
| Document | `ColumnRFT.Trail.rvt` |
| Test column | id `421967`, `450 x 600mm` |
| Tie bar / hook | `10M` (53672) / `Stirrup/Tie - 135 deg.` (53733), orientation **`Left`** (per #78) |
| Writes | inside a rolled-back `SubTransaction` — model left with **0** rebar |
| Date | 2026-09-14 |

> ## CORRECTION (from #90) - the tie figures below are OUTER FACES, not centrelines
>
> The layout block below labels `u = +/-185.0` as the OUTER tie
> **centreline**. It is not. For a 450 wide column at cover 40,
> `185.0 = 450/2 - 40`, which is the tie's **outer face**; the centreline
> is half a tie diameter further in, at `450/2 - 40 - 9.5/2 = 180.25`.
>
> **`180.25` is what #80 MEASURED a tie landing at** for the same column
> and the same cover (`issue-80-rebar-constraints-and-cover-clamp.md`
> section 3), so the two documents disagreed by exactly `tie/2` and the
> measured one is right.
>
> `CreateFromCurves` takes CENTRELINES, so the ties this page created were
> built 4.75 mm outside their intended position. The page did not notice
> because #80's other finding covers it: Revit **clamps** a tie to the
> host's own cover, so the too-wide tie was silently pulled back to
> 180.25 regardless. Two errors cancelling is not the same as being right,
> and the next person to copy these numbers into a placer would get one
> error without the other.
>
> **This page's CONCLUSIONS stand** - a second overlapping closed tie
> creates, costs one element, and reflects for section 6.3. None of that
> depends on the half-tie term. But the coordinates here must not be
> treated as a worked example of tie geometry. `rft.core.column_layout.
> tie_half_dimensions_mm` is the one that carries the term.

## Why this had to be tested

Every earlier experiment (#70, #78) used the **outer perimeter tie only**. §6.2
is explicit that a column's tie set is *"the union of one or more such closed,
possibly overlapping, loops — never a mix of 'the main tie' plus separate
free-floating cross-tie legs."* None of that had been observed. Whether Revit
accepts a second, overlapping closed `StirrupTie` on the same host was an
assumption.

## The layout tested

Derived from the spec's own arithmetic rather than invented: cover 40, tie
Ø9.5, main bars Ø15.9, so bar centreline offset from the face is
`40 + 9.5 + 15.9/2 = 57.45`.

```
corner bar centres        u = ±167.6    v = ±242.6
intermediate bars         v = ±80.9     (4 bars per 600-face, equal spacing)

OUTER tie centreline      u = ±185.0    v = ±260.0     (wraps all bars)
INNER tie centreline      u = ±180.3    v = ±93.6      (wraps the 4 intermediate bars)
```

This is §6.2's own worked example — *"Tie 2 wraps only the intermediate bars
on the North and South faces"* — and it is a genuinely overlapping case: the
inner tie spans almost the full width in `u` while nesting inside in `v`.

## Results

```
OUTER created: id=422074 shapeId=168549 qty=6
INNER created OK: id=422075 shapeId=168549 qty=6
  reflection on INNER: HasReflection=True Determinant=-1.000
  inner bar0: u=-119.1 v=2.6 insideInnerTie=True
  inner bar1: u=+119.1 v=2.6 insideInnerTie=True
Rebar ELEMENTS = 2   (one per tie definition)
```

| Question | Answer |
|---|---|
| Does a second overlapping closed tie create at all? | **Yes** — no exception, no refusal |
| Element cost | **2 elements — one per tie definition**, not per level. #70's economics hold for inner ties |
| Does `MoveBarInSet` reflection work on an inner tie? | **Yes** — `Determinant = -1`, stored |
| Does §6.3 alternation work on an inner tie? | **Yes** — `u = -119.1 → +119.1`, adjacent corner, hook still **inside** the inner tie |

## One behaviour worth knowing: the two ties SHARE a `RebarShape`

```
outerShape = 168549    innerShape = 168549    -> SAME shape reused
```

`CreateFromCurves` was called with `useExistingShapeIfPossible: true`, and both
ties are closed rectangles, so Revit matched them to one parametric
`RebarShape` with different A/B dimensions. The document holds 39 shapes and
gained none.

This is **correct** and desirable — a rebar schedule groups by shape code, and
both ties genuinely *are* the same shape code at different dimensions. But it
means the outer and inner tie are **not distinguishable by `GetShapeId()`**.
Anything that needs to tell the roles apart (the review report, a
role-to-grade lookup, a sketch legend) must track the distinction itself
rather than reading it back off the shape.

Passing `useExistingShapeIfPossible: false` would force separate shapes and
pollute the project's shape list for no detailing benefit — not recommended.

## Consequences for `column_layout`

The §6.2 subset model maps cleanly onto the API:

- each subset (initial bar index + count) resolves to **one closed rectangle**
  whose half-dimensions come from the enclosed bars' centrelines plus
  `½·Ø_bar + ½·Ø_tie`;
- each subset becomes **one `Rebar` set**, laid out once, then carrying its own
  level-indexed reflection map for §6.3;
- ties overlapping in plan is a non-issue for the API.

So the output contract is a **list of tie definitions**, each
`(subset → rectangle, layout, rotation map)` — not one privileged "main tie"
plus extras.

## Still unverified

- Only **one** inner tie was created. A section with **three or more**
  overlapping loops (Figure 13-3's denser typical sections) is untested,
  including whether Revit warns about near-coincident bars where two ties'
  legs nearly touch.
- The inner tie here shares its `u` extent with the outer tie but does not
  **intersect** it. Two ties whose legs genuinely cross — which some Figure
  13-3 sections require — were not tested.
- No longitudinal bars were placed, so nothing here verifies that the ties
  actually enclose real bars, only that the geometry lands where the
  arithmetic says.
- Save/reopen round-trip untested.
