# #109 — the first KEPT write

Revit 2024.3, `ColumnRFT.Trail.rvt`, host column **422078** (450 × 600 on
Level 2, spanning 3000–6000 mm). Owner approved writing into this document
rather than a scratch copy; it was unmodified beforehand and already held 95
rebar elements.

**Every previous proof in this repository — #69 included — ran inside a
`SubTransaction` that was aborted.** That established the *read* side and
nothing about writes. This is the first time the project has created a `Rebar`
element and kept it.

---

## What was created, and kept

```
423136   closed tie, 10M, hook "Stirrup/Tie - 135 deg."   z = 3300
423137   same                                              z = 3500
423139   same, useExistingShapeIfPossible = false          z = 3700
```

`Rebar.CreateFromCurves` works, with the signature the placer assumed:

```csharp
Rebar.CreateFromCurves(doc, RebarStyle.StirrupTie, barType, startHook, endHook,
                       host, XYZ.BasisZ, curves,
                       RebarHookOrientation.Right, RebarHookOrientation.Right,
                       useExistingShapeIfPossible, createNewShape)
```

`RebarHostData.GetRebarHostData(column).IsValidHost()` returned true, `Quantity`
is 1, `GetHostId()` returns 422078, and the elements survive the transaction
closing. Shape matching assigned "Rebar Shape 2" when allowed to reuse, and
created "Rebar Shape 3" when not — **neither changed the geometry**, which was
the first hypothesis and it was wrong.

---

## Finding 1 — read-back immediately after `Commit()` returns the REQUESTED
## geometry, not the as-built

The single most important result here, and it would have been easy to miss.

`GetCenterlineCurves(false, true, true, IncludeOnlyPlanarCurves, 0)` called in
the same execution as the commit returned **exactly the curves that were passed
in**. The identical call, on the identical elements, in a *later* execution
returned something different:

| element | read right after commit | read in a later call |
|---|---|---|
| 423136 | 180.25 × 255.25 | **182.63 × 257.63** |
| 423137 | 180.25 × 255.25 | **182.63 × 257.63** |
| 423139 | 180.25 × 255.25 | **182.63 × 257.63** |

All three agree once regeneration has happened. **R15 requires reading the
as-built position back; a placer that reads it in its own transaction gets its
own input handed back to it** and would report perfect agreement every time
while the model said otherwise.

This is exactly the class of defect `docs/token-efficient-expansion.md` §8 warns
about — a check that appears to pass because it never exercised the thing it
claims to verify.

## Finding 2 — WITHDRAWN. The as-built centreline is exactly the request

**This finding was wrong, and it was wrong in the way the whole document
warns about: a number read from the wrong thing.** It is kept here rather
than deleted because the mistake is more instructive than the correction.

The claim was that the built tie sits 2.38 mm outboard on both
half-dimensions, eating 2.4 mm of cover. It does not. Read back with the
bend radii and the hooks present, the four legs are:

```
bottom leg   y = 931.75          top leg    y = 1442.25     ->  510.50
left leg     x = -326.05         right leg  x =   34.45     ->  360.50
```

Both are the requested dimensions to the last decimal, and the cover is the
40 mm the host states.

**Where 2.38 came from.** The original measurement took the min and max of
every endpoint in a `suppressHooks=True` read. That read does not stop at
the corner — it returns the point where each hook *begins*, and those two
points overrun their legs by one bar radius (9.5 / 2 = 4.75 mm). Half of
4.75 is 2.38. The number was the hook tangent, measured as though it were
the rectangle.

**The rule this leaves for the placer**, which survives the correction and
is the part that matters: *an as-built check must compare the LEGS, not the
extremes of the curve array.* A bounding box over `GetCenterlineCurves`
includes the hooks and will disagree with the request on every tie ever
placed — reporting a cover violation that is not there, in a report an
engineer is meant to trust. Finding 1 stands unchanged and is the real
result of this ticket.

## Finding 3 — A1 is right, and attempting an unbuildable loop is worse than
## an exception

A1 says a closed loop narrower than `bend diameter + tie diameter` cannot be
bent, and that the tool must refuse it rather than offer it to Revit. For 10M
that threshold is `40.0 + 9.5 = 49.5 mm`. Both sides were tested:

| offered | result |
|---|---|
| **60 mm** (above) | built cleanly, rolled back |
| **25.4 mm** (below — what a cross-tie subset produces) | **took the whole execution down** |

The 25.4 mm attempt did not return null and did not raise anything the
surrounding `try/catch` could catch — the call failed at a level above it, with
`Exception has been thrown by the target of an invocation`. Revit itself stayed
responsive and **nothing was created** (rebar count 95 → 98, the three kept ties
and no more).

So the exact mechanism is still unconfirmed — whether a modal dialog is posted
is not something this probe can see from inside. What IS established:

- a sub-threshold loop is **never** silently accepted;
- the failure is **not catchable at the call site**, so a placer cannot wrap it
  and carry on;
- **pre-checking, as A1 does, is the only safe design.** Had the tool offered
  these loops and handled the failure, it would not have worked.

## Finding 4 — `RebarHookOrientation.Right` on both ends throws the 135°
## hooks OUT of the column

Found by the owner looking at the model, not by any check in this
repository. The three kept ties were built with
`RebarHookOrientation.Right` at both ends — the value the tracer bullet
assumed — and the hook tails land **outside the concrete**:

```
requested rectangle   x -326.05 .. 34.45      y 931.75 .. 1442.25
column extent         x -370.80 .. 79.20      y 887.00 .. 1487.00

Right / Right    tail (-260.2,  835.6) OUTSIDE   tail (-422.2, 997.6) OUTSIDE
Left  / Left     tail (-260.2, 1027.9) INSIDE    tail (-229.9, 997.6) INSIDE
Left  / Right    tail (-260.2, 1027.9) INSIDE    tail (-422.2, 997.6) OUTSIDE
Right / Left     tail (-260.2,  835.6) OUTSIDE   tail (-229.9, 997.6) INSIDE
```

All four combinations build without complaint. Revit does not object to a
tie whose hooks leave the member; it draws it, schedules it, and lets it
through. **`Left` / `Left` is the only combination that turns both hooks
into the core**, which is what a 135° seismic hook is for.

Two consequences:

- the placer must pass `Left` / `Left`, and that is now **R21**;
- more generally, *a tie that builds is not a tie that is right.* Nothing
  in the Revit API rejected the wrong one. Any check on hook position has
  to be ours — the placer should assert that both hook tails fall inside
  the host's extent, because this defect is invisible in every report that
  reads only the rectangle.

The three kept ties were **replaced** with `Left` / `Left` ties at the same
three levels.

---

## What this does NOT cover

- **The longitudinal bar set.** No multi-bar `Rebar` was created, so whether a
  set behaves as one element or many for read-back is still unknown.
- **R15's bar snap.** The 2.38 mm shift above is the *tie* moving. Whether a
  longitudinal bar snaps to the tie's bend, and by how much, is untested —
  R15/R18 still rest on the earlier measurement.
- **`MoveBarInSet`.** Never called.
- Placement through the pyRevit window. Every write here came through the MCP
  executor, which holds its own open transaction; the window's path is its own
  surface.

## State left behind

Three ties remain in `ColumnRFT.Trail.rvt` (423209, 423210, 423211) at
z = 3300 / 3500 / 3700 in column 422078. They are the kept write this ticket
exists to produce, rebuilt with R21's hook orientation after Finding 4;
the three original ties (423136, 423137, 423139) were deleted. The
document was unmodified before this session, so closing
without saving removes them; deleting the three elements does the same.
