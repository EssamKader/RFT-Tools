# Issue #226 — Batch placement across footings, verified on a live host

**Status:** WRITE-PROVEN (kept, not rolled back). #223's own tracer
bullet proved N BARS in a loop, inside one transaction, on ONE footing.
This bullet proves the batch's own new claim: N FOOTINGS, each getting
its own full placement (mesh + dowel bars) and its own `RFT-FTG-<id>`
ownership tag, inside the SAME one transaction.

| | |
|---|---|
| Host | Same live Revit session used for #197/#69/#220/#223/#228, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` |
| Connection | `revit-mcp` MCP server, `send_code_to_revit` (C#) |
| Access | Read and write — a `SubTransaction` was **committed, not rolled back** |
| Date | 2026-09-24 |
| Footings used | `425190` and `425131` — two DIFFERENT footings of the same `M_Footing-Rectangular` `1800 x 1200 x 450mm` type (#220's/#228's own verification already confirmed both measure identically) |
| Elements created | Footing `425190`: `425614`-`425617` (mesh_bar_x, mesh_bar_y, 2 dowel bars), tagged `RFT-FTG-425190`. Footing `425131`: `425618`-`425621` (same shape), tagged `RFT-FTG-425131` |

---

## 1. The question

`footing_batch.apply_batch` opens ONE `Transaction` and loops every
surviving candidate footing inside it, placing that footing's own mesh
bars and dowel array, then tagging every element it created with THAT
footing's own `RFT-FTG-<hostId>` partition. Does looping a FULL
per-footing placement (multiple `Rebar.CreateFromCurves` calls, per-bar
`Partition.Set`) across MULTIPLE DIFFERENT footing hosts, inside one
transaction, actually work end-to-end on a live host — do all footings
get their own correctly-tagged elements, with no cross-footing mix-up (a
tag or a host id leaking from one footing's loop iteration into
another's)?

## 2. Method

Reproduced the loop shape `footing_batch.apply_batch` implements (not
`plan_candidates`'s own grouping/exclusion logic — that is pure Python,
already unit-tested in `tests/test_footing_batch.py`/`tests/
test_footing_revit_batch.py`; this bullet is about the WRITE LOOP across
multiple hosts, the one thing those mock-object tests cannot themselves
prove against a real document):

1. For each of the two footings, in one shared loop, inside ONE
   `SubTransaction`:
   - computed the footing's own plan centroid/bottom-Z from its bounding
     box (`footing_mesh._footing_origin`'s own math);
   - created ONE straight `mesh_bar_x` and ONE straight `mesh_bar_y`
     (`_place_one_bar`'s own shape, `norm=XYZ.BasisZ`), hosted on that
     footing;
   - created TWO bent dowel bars (`_create_dowel_rebar`'s own shape,
     `norm=XYZ.BasisY`, hook + vertical), hosted on that footing, at
     distinct `(u, v)` offsets — the same per-footing "place mesh + place
     dowel array" sequence `apply_batch` runs;
   - set every element's own `Partition` parameter to
     `"RFT-FTG-" + <that footing's own element id>` — `footing_ownership.
     tag_as_ours`'s own shape.
2. Committed the `SubTransaction` (kept, not rolled back).
3. A **separate**, later `send_code_to_revit` call with no transaction
   open re-read all 8 created ids purely by `ElementId`, confirmed each
   is a `Rebar`, confirmed each `GetHostId()` resolves to the RIGHT
   footing (not the other one), and confirmed each `Partition` reads the
   RIGHT per-footing tag (not the other footing's tag).

## 3. Result

```
Placement call:
425190: created=425614,425615,425616,425617 tag=RFT-FTG-425190
425131: created=425618,425619,425620,425621 tag=RFT-FTG-425131

Independent persistence check (separate call, no open transaction):
425614: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425190)
425615: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425190)
425616: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425190)
425617: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425190)
425618: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425131)
425619: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425131)
425620: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425131)
425621: exists=True isRebar=True hostOk=True tagOk=True(RFT-FTG-425131)
DocumentIsValidObject=True
```

(One earlier `send_code_to_revit` call for this same script timed out at
the transport level before this run; the subsequent element ids run
contiguously from `425614`, confirming the timed-out attempt created
nothing and was not a partial/duplicate write.)

## 4. Findings

1. **The multi-footing loop works as designed.** All 8 `Rebar.
   CreateFromCurves` calls across TWO DIFFERENT footing hosts, inside the
   single `SubTransaction`, succeeded — no exception, no state bleeding
   from one footing's loop iteration into the next.
2. **All 8 are KEPT writes, not just committed-without-exception** — the
   independent, transaction-free re-read confirms persistence, matching
   #197's/#223's own bar for what counts as write-proven.
3. **No cross-footing mix-up.** Every element's `GetHostId()` resolves to
   the CORRECT footing (never the other one in the batch), and every
   element's `Partition` carries the CORRECT per-footing tag — the
   specific new risk a single-footing tracer bullet (#223) could not
   exercise, since it only ever had one host in scope.
4. **Still unverified:** this bullet used TWO ILLUSTRATIVE footings, not
   a real batch of footings sharing an IDENTICAL live-read grouping key
   (R9) — footing `425131` has no real column above it (#220's own
   verification), so this bullet supplied its dowel geometry directly
   rather than through a real `find_column_above`/`read_dowel_column_
   section_mm` chain for that footing. The GROUPING logic itself
   (`rft.core.footing_batch.group_hosts`, the column-type-pair filter,
   every refusal path) is proven by mock-object tests only
   (`tests/test_footing_revit_batch.py`) — this bullet's own scope is the
   WRITE LOOP across multiple hosts, not the selection logic upstream of
   it. A live model with two or more REAL footing+column pairs of an
   identical type would be needed to also live-verify the grouping path
   end-to-end; this trial model has only one real footing+column pairing
   (`425190`/`425531`).

## 5. What this authorises

`rft.revit.footing_batch.apply_batch`'s own per-footing placement-and-tag
loop is WRITE-PROVEN: multiple footings, each getting its own full
placement and its own correctly-scoped `RFT-FTG-<id>` tag, inside one
committed transaction, with no cross-footing interference. Combined with
the mock-object tests' proof of the SELECTION/GROUPING/EXCLUSION logic
(`tests/test_footing_batch.py`, `tests/test_footing_revit_batch.py`) and
#223's own proof of the per-footing N-BAR-loop shape, this closes
`docs/token-efficient-expansion.md` §8's verification requirement for
#226's own new write behaviour.

It does **not** authorise assuming the real `find_column_above`/R9
grouping pipeline runs cleanly end-to-end against two or more GENUINE
footing+column pairs sharing an identical type — this trial model does
not currently contain more than one such real pair to test that against.

**Addendum, 2026-09-24 (Essam, visual inspection):** this bullet's own
illustrative dowel positions on footing `425190` (`425616`/`425617`, at
arbitrary ±300/±200mm offsets, same shape as #223's own debris) landed
OUTSIDE the real column `425531`'s own footprint — correctly flagged as
looking wrong on inspection, and always the finding-4 caveat above, not
a production defect. Deleted, and replaced by the real
`perimeter_bar_positions` output for that column, verified inside its
own bounding box — see `docs/footing/verification/
issue-222-real-dowel-array-inside-column.md`. Footing `425131`'s own
illustrative debris (`425618`-`425621`, no real column to check against)
was deleted in the same pass, since it was equally non-representative.
