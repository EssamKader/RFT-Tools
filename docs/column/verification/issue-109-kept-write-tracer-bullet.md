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

## Finding 2 — the as-built centreline sits 2.38 mm outboard of the request

Reproducible across all three ties, on both half-dimensions:

```
requested half   180.25 x 255.25 mm
as built half    182.63 x 257.63 mm      (+2.38 mm each)
```

The requested geometry already placed the tie's outer surface exactly at the
40 mm cover (180.25 + 9.5/2 = 185.0 = 225 − 40). The as-built outer surface is
at 187.38, i.e. **37.6 mm of cover — less than the host's own setting.**

**Cause not identified, and not guessed.** 2.38 mm is a quarter of the 10M bar
diameter, which is suggestive and nothing more. What matters for the placer is
the rule this establishes: *the tie Revit builds is not the tie you asked for,
so the Review report's as-built section must read the model rather than restate
the request.* That is R15's requirement arriving from a second direction.

Worth a follow-up ticket rather than a guess in code.

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

Three ties remain in `ColumnRFT.Trail.rvt` (423136, 423137, 423139) at
z = 3300 / 3500 / 3700 in column 422078. They are the kept write this ticket
exists to produce. The document was unmodified before this session, so closing
without saving removes them; deleting the three elements does the same.
