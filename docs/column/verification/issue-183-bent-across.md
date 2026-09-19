# #183 — an arrayed bent set bending ACROSS its own step axis

**Status: ANSWERED. It works, exactly as R44 predicted.** Measured on
Revit 2024 build 24.3.40.26, document `ColumnRFT.Trail`, column `424596`
(450 × 600 mm), bar type 13M. Transcript:
`issue-183-bent-across-transcript.txt`. Nothing was kept — every
transaction was rolled back.

## What was unanswered

`Rebar.CreateFromCurves`'s `normal` is load-bearing twice, and each role
had been proven by its **own separate experiment**:

- **#131** — `SetLayoutAsNumberWithSpacing` arrays the set **along** the
  normal. Getting it wrong shipped overlapping steel: two bars 11.7 mm
  apart at two corners.
- **#173 part 1** — a bend renders only when `normal` is
  **perpendicular** to the bend plane. Parallel and vertical both raised
  *"An internal error has occurred."*

Before this probe, the grid of what had actually been built looked like
this:

| | single bar | arrayed set |
|---|---|---|
| bend **along** the normal | raised (#173 p1) | raised (#173 p3) |
| bend **across** it | OK (#161) | **never built** |

R44 forbids the whole first row. #180 then made every one of the four
face runs take the second row's right-hand cell — so the untested corner
became the **only** path `rft.revit.column_place_bars` can take for a
top-floor column.

## What was measured

### Part A — the R44-legal set

`normal = Hand` (what #131 requires), bend toward `+Facing` (what #173
part 1 requires). Three bars at 150 mm.

```
bar 0: 3 curves [Line 653.7, Arc 72.8, Line 353.7]   along step axis: 0.0 mm
bar 1: 3 curves [Line 653.7, Arc 72.8, Line 353.7]   along step axis: 150.0 mm
bar 2: 3 curves [Line 653.7, Arc 72.8, Line 353.7]   along step axis: 300.0 mm
```

**Both roles are satisfied by the one argument, simultaneously.**

- **Every bar carries the bend** — three curves each, Line/Arc/Line, not
  only the seed. The probe asked
  `GetCenterlineCurves(..., barPositionIndex=i)` per bar precisely
  because a flattened repeat would be invisible from the set as a whole,
  and a straight bar that looks placed is the worst failure available
  here.
- **The array is exact**: 0.0 / 150.0 / 300.0 mm along Hand. The second
  curve did not disturb the layout.
- The curve lengths are **identical to #173 part 1's single bar** (Line
  653.7, Arc 72.8, Line 353.7), so arraying changed the bar's geometry in
  no respect.

### Part B — the control

The same set bending along `+Hand`, which R44 forbids:

```
RAISED Exception: An internal error has occurred.
```

This is what makes part A trustworthy. Had both parts raised, the finding
would have been about the probe. Instead the rig is demonstrably able to
build such a set, and **R44 is confirmed from a second, independent
direction** — it is not merely a rule inferred from #173's single-bar
table.

### Part C — the other axis

`normal = Facing`, bend `+Hand`. Identical result to part A: three curves
on every bar, 0.0 / 150.0 / 300.0 mm. **The answer is a property of the
geometry, not of Hand.**


## Re-measured after a regeneration (2026-09-19)

#92 established that **a bar's position is not settled until
`Document.Regenerate()` runs** — constraints resolve there, and a read
taken before it reports the coordinate that was *requested*. This page's
original numbers were read before any regeneration, so they were open to
that doubt.

Re-measured on the same host, same configuration, reading twice in one
sub-transaction:

```
BEFORE regen  bar 0/1/2: 3 curves, 0.00 / 150.00 / 300.00 mm
AFTER  regen  bar 0/1/2: 3 curves, 0.00 / 150.00 / 300.00 mm
```

**Unchanged.** Every bar still carries its bend and the array still holds
the requested pitch. The conclusions below stand as published.

Why this one did not move while #92's did: that bar was placed at an
interior point beside a tie's bend, where an unpinned handle had a rebar
to bind to. This one runs on the column's own axis with no neighbour to
snap to — which is a reason, not a guarantee, and is exactly why it was
worth re-reading rather than assuming.

## Consequences

1. **R44's rule is fully measured, not merely reasoned.** Its own
   section "Why this costs nothing" argued that the array axis and the
   bend-plane normal become the same vector, and that no placer change
   was needed. That argument is now a measurement.
2. **The SHAPE UNVERIFIED bullet in `rft.revit.column_place_bars` is
   retired** by this page, and the module's docstring is updated to cite
   it. The note was rewritten during #182's review to say this corner had
   never been built; that is no longer true.
3. **#180's per-run split is vindicated on the host.** Four runs, four
   legal normals, each arraying and bending correctly.

## What this page does NOT say

- It does not test a bend whose horizontal leg runs back **into** the
  column and out the far side, which R44 permits and
  `rft.core.column_plan.roof_termination_plan` records as under-measured
  (`available_run_mm` is taken from the column's own face outward).
  Nothing here contradicts that note; the leg here is 400 mm into open
  air.
- It does not re-test `_pin_to_host_faces` on an arrayed bent set. R45
  pinned the fifth handle per axis and is guarded, but the pinning of an
  **arrayed** bent set on a live host remains its own question.
