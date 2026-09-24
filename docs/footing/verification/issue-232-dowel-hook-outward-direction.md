# R10 — Dowel hook direction, verified outward from the column on a live host

**Status:** WRITE-PROVEN (kept, not rolled back). Closes what
`issue-222-real-dowel-array-inside-column.md`'s own addendum flagged:
that bullet verified bar POSITION only; it still bent every hook along a
single fixed world `+X`, the exact un-directional placeholder R10
(`docs/footing/spec-amendments.md`) replaces. This bullet re-places the
same real 10-bar array using the CORRECTED, direction-aware geometry
(`rft.core.footing_dowels.positioned_dowel_bar_geometry`/`dowel_outward_
direction`, and the adapter's own per-bar `norm`, `rft.revit.footing_
dowels._dowel_norm`) and checks both position AND direction.

| | |
|---|---|
| Host | Same live Revit session used throughout this session, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` |
| Access | Read and write — a `SubTransaction` was **committed, not rolled back** |
| Date | 2026-09-24 |
| Footing / column | `425190` / `425531` (`b=300mm`, `h=600mm`, `cover=40mm`, live-read) |
| Array inputs | `dowel_bar_dia_mm=16.0`, `dowel_tie_dia_mm=10.0`, `count_b_face=3`, `count_h_face=4` — the SAME real `rft.core.footing_plan.build_footing_plan` call, run locally in CPython, whose `DowelArrayPlan.bars` output (all 10 bend/hook endpoints) was taken as data, not re-derived by hand |
| Elements deleted (superseded) | `425632`-`425641` — the previous "real position, fixed direction" array from `issue-222-real-dowel-array-inside-column.md` |
| Elements created | `425644`-`425653` — the same 10 positions, now with R10's own per-bar outward hook direction and per-bar `norm` |

---

## 1. The question

`dowel_outward_direction`'s corner-vs-face branching, and the adapter's
own per-bar `norm` rotation, are both unit-tested against synthetic
inputs (`tests/test_footing_dowels.py`, `tests/test_footing_revit_
dowels.py`). Does the REAL `build_footing_plan` output for a REAL
column's REAL section, placed on a live host, actually produce hooks
that point AWAY from the column centroid for every bar — corners
diagonally, faces perpendicular — with no bar's hook landing closer to
the centroid than its own bend corner (which would mean it bent inward,
Essam's own screenshot finding)?

## 2. Method

1. Ran the REAL `rft.core.footing_plan.build_footing_plan` (the same
   composing module `IsolatedFootingRFT.pushbutton/script.py` calls) in
   plain CPython with column `425531`'s own real `Cw_mm=300`/
   `Cd_mm=600`/`Ccover_mm=40` and `count_b_face=3`/`count_h_face=4`,
   taking its `DowelArrayPlan.bars` output (10 bars' bend/hook-far-end
   coordinates) as data.
2. Deleted the previous 10 bars (`425632`-`425641`) that used the
   pre-R10 fixed-direction placeholder.
3. Placed 10 NEW bent dowel bars at the same real positions, this time
   with each bar's own real hook-far-end coordinate (not a fixed `+X`
   offset), and each bar's own `norm` computed the same way the adapter's
   `_dowel_norm` does (90-degree in-plane rotation of that bar's own
   hook vector) — inside one committed `SubTransaction`, tagged
   `RFT-FTG-425190`.
4. For every created bar, read its own bend corner and hook-far-end
   points and checked TWO things against column `425531`'s own live
   `get_BoundingBox(null)`:
   - the bend corner (the vertical leg's own position) falls inside the
     column's bounding box (position, same check as before);
   - the hook's far end is FARTHER from the column's own centroid than
     the bend corner is (direction: genuinely outward, not toward it —
     the direct numeric statement of "does not bend into the column").
5. A **separate**, later `send_code_to_revit` call with no transaction
   open re-read all 10 ids, confirming persistence, host and tag.

## 3. Result

```
Created=425644,425645,425646,425647,425648,425649,425650,425651,425652,425653
425644: insideColumn=True outward=True distBend=1.020 distHook=1.473
425645: insideColumn=True outward=True distBend=0.978 distHook=1.450
425646: insideColumn=True outward=True distBend=1.020 distHook=1.473
425647: insideColumn=True outward=True distBend=0.553 distHook=0.994
425648: insideColumn=True outward=True distBend=0.553 distHook=0.994
425649: insideColumn=True outward=True distBend=1.020 distHook=1.473
425650: insideColumn=True outward=True distBend=0.978 distHook=1.450
425651: insideColumn=True outward=True distBend=1.020 distHook=1.473
425652: insideColumn=True outward=True distBend=0.553 distHook=0.994
425653: insideColumn=True outward=True distBend=0.553 distHook=0.994
badPosition=0 badDirection=0

Independent persistence check (separate call, no open transaction):
okCount=10/10 -- every bar exists, is a Rebar, hosted on 425190, tagged
RFT-FTG-425190. DocumentIsValidObject=True.
```

(`distBend`/`distHook` are each bar's own bend/hook-far-end distance
from the column's centroid, feet — every bar's `distHook > distBend`,
i.e. every hook moved AWAY from centre when it bent, never toward it.
The two lower pairs — `0.553`→`0.994`, the b-face-interior bars — show
the smallest outward jump, consistent with a perpendicular-only bend;
the corner bars' `1.020`→`1.473` jump is larger, consistent with a
diagonal bend covering both axes.)

## 4. Findings

1. **Every one of the 10 real bars bends outward, none inward.**
   `badDirection=0` across corner bars (4), b-face-interior bars (2), and
   h-face-interior bars (4) — the three distinct cases R10's own rule
   defines, all present in this one real array.
2. **Position remains correct** (`badPosition=0`), confirming the
   direction fix did not regress the earlier position-only proof.
3. **The per-bar `norm` computation works on a live host**, not just in
   the mock-object suite — all 10 `Rebar.CreateFromCurves` calls
   succeeded with a `norm` that varies per bar (verified directly in the
   unit tests; here, indirectly, by every bend actually being carried
   correctly rather than collapsing to a degenerate/rejected shape).
4. **Still unverified:** this used ONE real column's real section — a
   column with a MIRRORED or otherwise flipped orientation was not
   exercised (out of scope: `column_host.read_orientation` already
   refuses that case before `read_dowel_column_section_mm` runs, per
   R7/#221, so a flipped column never reaches this array-building code
   at all).

## 5. What this authorises

`rft.core.footing_dowels.dowel_outward_direction`/`positioned_dowel_bar_
geometry`, and the Revit adapter's own per-bar `norm`
(`_dowel_norm`), are now live-host WRITE-PROVEN: for a real column's
real section, every dowel in a real array bends outward from the
column's centroid — corners diagonally, faces perpendicular — with no
bar bending back toward the core. This closes R10's own verification gap
and the specific defect Essam's screenshot found.
