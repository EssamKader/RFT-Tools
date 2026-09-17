# #92 — why bars snap, and the one thing that stops them

Revit 2024.3, `ColumnRFT.Trail.rvt`, host column **422078** (450 × 600,
cover 40, 16M bars, 10M ties). Run live after #109 established that writes
survive, so every number below was measured rather than reasoned about.

#92 asked four questions. Three are answered; one needs a save.

---

## The short version

**A longitudinal bar placed by the API does not go where you put it.** It
binds to the nearest tie bend and translates — and if it is a *set*, the
whole set translates together, which is what the V2 hand cage showed.

**Explicitly constraining the bar to the host's own faces stops it
completely**, and lands the bar on the exact coordinate, not a near one.

```
                       requested            actual            error
4-bar set, unpinned    -313.35, 944.45   -308.60,  956.50   dx +4.75  dy +12.05
4-bar set, PINNED      -313.35, 944.45   -313.372, 944.400  exact (see below)
```

Every bar in the unpinned set carries the identical `+4.75 / +12.05`. The
set did not distort — it moved.

---

## Q1 — which tie level does a bar bind to?

The corner bar bound to **tie 423209**, and the constraint reports
`TargetIsHookBend() == True`. Not a corner bend: the **hook** bend.

That matters more than it looks, because R21 — decided yesterday — turns
the 135° hooks *inward*. R21 is correct and stays, but it places bend
geometry into the core precisely where the corner bar sits. **The two
rules interact**, and the interaction is the snap.

The mid-face bar, far from every bend, bound to the host and did not move:

```
(-313.35, 1187.00) -> (-313.35, 1187.00)   dx 0.00  dy 0.00
   Bar Segment 1   FixedDistanceToHostFace   target = the column
```

So the answer to "which level" is "whichever bend is nearest", and it is
**not worth making deterministic** — Q3 removes the question instead.

## Q2 — sets or single bars?

`#92` proposed single-bar sets to buy predictability at the cost of
element count (19 elements vs a theoretical 8). **The trade is not
necessary.** A pinned 4-bar set is exact on all four bars:

```
bar 0: (-313.372,  944.400)
bar 1: (-313.372, 1106.100)
bar 2: (-313.372, 1267.800)
bar 3: (-313.372, 1429.500)
```

Sets stay. This is the cheaper answer and the one that keeps the model
readable.

## Q3 — can constraints be set explicitly at creation? **Yes**

```csharp
var mgr = bar.GetRebarConstraintsManager();
foreach (var h in mgr.GetAllHandles()) {
    // RebarPlane and Edge handles only
    foreach (var c in mgr.GetConstraintCandidatesForHandle(h)) {
        if (!c.IsToHostFaceOrCover()) continue;
        if (c.IsToCover()) continue;                       // see below
        var target = c.GetTargetElement();                 // NOT GetTargetElementId
        if (target == null || target.Id != hostId) continue;
        var face = c.GetTargetHostFaceAndTransform(0, Transform.Identity)
                       as PlanarFace;                      // NOT a .PlanarFace property
        if (face == null) continue;
        if (!IsNearFace(face.FaceNormal)) continue;
        c.SetDistanceToTargetHostFace(-offset);            // note the sign
        mgr.SetPreferredConstraintForHandle(h, c);
        break;                                             // FIRST match
    }
}
```

> **These are the literal calls, because an earlier version of this section
> was not.** It described the filter in prose — *"whose `PlanarFace` normal
> is the near face"* — and #119's implementer read `GetTargetElementId()`
> and a `PlanarFace` property out of it. **Neither member exists.** The
> fake was then written to match the invention, so the suite passed on code
> that could not run on a host. Reflection over the live `RebarConstraint`
> is what caught it.
>
> `break` on the first match is deliberate: the live column returned
> **47–49 candidates for a single handle**, in an order Revit does not
> document. Taking the last match would be picking by an ordering nobody
> specified.

Four things were established the hard way and each would have cost a day:

**The offset is signed against the OUTWARD face normal.** `+57.45` put the
bar 57 mm *outside* the column, at `(-428.27, 829.50)`. The value the
placer passes is **negative**.

**`ToCover` re-points the constraint and does not move the bar.** It
reports `ToCover` afterwards and the bar stays at the snapped coordinate.
It looks like a fix and is not one — exactly the shape of defect
`token-efficient-expansion.md` §8 is about. Use
`FixedDistanceToHostFace` with an explicit distance.

**`RebarConstraintsManager.IsRebarConstrainedPlacementEnabled` is a
static, and it was already `False`.** The bar snapped regardless. Nobody
should reach for that switch; it does not govern API placement.

**`FlipHandleOverTarget()` throws** on anything that is not
`ToOtherRebar` — "The RebarConstraint is not of RebarConstraintType
'ToOtherRebar.'" Sign the offset instead.

### The bonus: the requested coordinate was wrong, and the constraint was right

```
column near faces   x = -370.822    y = 886.950
pinned bar          x = -313.372    y = 944.400     = face + 57.45, exactly
```

The `dx -0.02 / dy -0.05` residual seen in testing was **mine** — the
target came from a bounding box printed to one decimal. The column does
not sit on a round coordinate, and nothing says it should.

> **A placer that computes absolute XY carries the host's own coordinate
> noise into every bar. A placer that states a distance from a face does
> not, and inherits a cover change for free.**

## Q4 — does it survive? Partly answered

Re-read in a **later execution** (the check Finding 1 of #109 showed is the
only honest one), the set is identical to the micron and the constraints
are intact:

```
bar 0: (-313.372, 944.400)          Bar Plane     FixedDistanceToHostFace  -57.45
bar 1: (-313.372, 1106.100)         Bar Segment 1 FixedDistanceToHostFace  -57.45
bar 2: (-313.372, 1267.800)         preferred constraint recorded on both handles
bar 3: (-313.372, 1429.500)
```

**Save / reopen is NOT covered, and is now harder to cover.** The
claim this section supports is *"survives regeneration and a later
execution"*, never *"survives a file round trip"*.

The pinned set was kept in `ColumnRFT.Trail.rvt` so the round trip could be
finished; the owner has since discarded it, unsaved, rather than commit a
probe's leftovers to a working model. **That was the right call and it
closes this route.** Finishing Q4 now needs a scratch copy of the document
— which is what it should have needed from the start, because a test whose
prerequisite is "save the model you are working in" is a test nobody will
run twice.

---

## What this leaves open

**§6.3's alternation gap, unchanged by any of the above.** §6.3 requires
the hook corner of *"any closed tie"* to alternate. A cross-tie has no
corner, so the V2 cage's cross-ties alternate not at all — a choice nobody
made. That is a spec question for the owner and nothing here answers it.

## State left behind

**None.** The 4-bar pinned set (423228) and #109's three ties were deleted
on the owner's instruction and never saved — rebar count 99 -> 95, and
column 422078 hosts nothing of ours. `ColumnRFT.Trail.rvt` is as it was
before any of this work.

Every measurement above was taken while those elements existed, on a
committed transaction. Nothing here rests on them still being present.
