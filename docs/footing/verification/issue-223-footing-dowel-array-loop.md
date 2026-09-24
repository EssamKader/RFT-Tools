# Issue #223 — Dowel array loop placement, verified on a live host

**Status:** WRITE-PROVEN (kept, not rolled back). This closes the specific
gap `RFT.lib/rft/revit/footing_dowels.py`'s own docstring flagged: #202's
tracer bullet (`issue-197-footing-tracer-bullet.md`) proved ONE bent bar is
a kept write on a footing host; it never proved a LOOP of
`Rebar.CreateFromCurves` calls, inside one transaction, on the same host.

| | |
|---|---|
| Host | Same live Revit session used for #197/#69/#220, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` (confirmed via `ping`'s `document.title` before this bullet) |
| Connection | `revit-mcp` MCP server, `send_code_to_revit` (C#) |
| Access | Read and write — a `SubTransaction` was **committed, not rolled back** |
| Date | 2026-09-24 |
| Footing used | id `425190` (`1800 x 1200 x 450mm`) — the SAME footing #220's own verification confirmed has a real column (`425531`, `300 x 600mm`) sitting on it |
| Bar type used | `RebarBarType` id `53649` (first type found in the document — this bullet is not testing bar-type resolution) |
| Bars created | ids `425596`, `425597`, `425598`, `425599` — 4 bent (hook + vertical) dowel-shaped bars, one per loop iteration |

---

## 0. Harness finding (re-confirmed, not assumed)

Per #197's own harness finding: the executor already holds an open
transaction, so a `Transaction.Start()` inside the sent code fails; a
`SubTransaction` is required. Re-confirmed here: the code below opens and
**commits** a `SubTransaction`, matching #197's pattern exactly, not #220's
(read-only, no transaction at all).

A first attempt using bare `RebarBarType`/`Rebar`/`RebarStyle`/
`RebarHookOrientation` (unqualified) failed to compile: `"'RebarBarType' is
inaccessible due to its protection level"` — the sent-code template resolves
short names against something other than `Autodesk.Revit.DB.Structure`
first. Fixed by fully qualifying every `Structure` type
(`Autodesk.Revit.DB.Structure.Rebar`, etc.) — worth recording since #197/
#220's own snippets did not need this (they used no `Structure` type by its
short name inside the sent code in a context that triggered it).

## 1. The question

`footing_dowels.place_dowel_bars` (#223) loops the same
`Rebar.CreateFromCurves` call `place_dowel_bar` already proved as a kept
write, once per `DowelArrayPlan.bars` entry, with no `try`/`except` of its
own (the calling transaction owns rollback). Does looping this call N times
inside ONE transaction, on the SAME footing host, actually work end-to-end
on a live host — do all N calls succeed, do all N elements persist, and do
none of them collide or get silently dropped?

## 2. Method

Reproduced the loop shape `footing_dowels.place_dowel_bars` and
`footing_dowels._create_dowel_rebar` implement (not the exact production
`(u, v)` positions `column_layout.perimeter_bar_positions` would compute for
this specific column — that math is already unit-tested in
`tests/test_column_layout.py`/`tests/test_footing_plan.py`; this bullet is
about the WRITE LOOP, not re-proving array position math):

1. Found footing `425190` (the real footing→column pair #220 already
   confirmed) and the document's first `RebarBarType`.
2. Computed the footing's own plan centroid/bottom-Z the same way
   `footing_mesh._footing_origin` does (`get_BoundingBox(null)`, no
   rotation transform — this footing is axis-aligned, matching #220's own
   reading of it).
3. Built 4 bent-bar (hook + vertical) `DowelBarGeometry`-shaped curve pairs
   at 4 distinct footing-local `(u, v)` offsets (±300mm × ±200mm — a plain
   4-corner square arrangement, not the real column's own perimeter
   layout), using the same bend elevation (78mm) and top elevation (450mm,
   the footing's own thickness) `footing_dowels.local_dowel_bar_geometry`
   would produce for this footing's own mesh-cover/diameter inputs.
4. Opened one `SubTransaction`, looped `Rebar.CreateFromCurves` once per
   offset exactly as `_create_dowel_rebar` does (`RebarStyle.Standard`,
   `null`/`null` hooks, `footing` as host, `XYZ.BasisY` as `norm`,
   `RebarHookOrientation.Left`/`Left`), collected each created `Rebar.Id`,
   and **committed** the `SubTransaction` (not rolled back).
5. A **separate**, later `send_code_to_revit` call with no transaction open
   re-read all 4 created ids purely by `ElementId`, confirmed each is a
   `Autodesk.Revit.DB.Structure.Rebar`, confirmed each `GetHostId()` still
   resolves to footing `425190`, and confirmed `document.IsValidObject`.

## 3. Result

```
Loop call:
OK footingId=425190 barTypeId=53649 createdCount=4 ids=425596,425597,425598,425599

Independent persistence check (separate call, no open transaction):
425596:exists=True:isRebar=True:hostIs425190=True
425597:exists=True:isRebar=True:hostIs425190=True
425598:exists=True:isRebar=True:hostIs425190=True
425599:exists=True:isRebar=True:hostIs425190=True
DocumentIsValidObject=True
```

## 4. Findings

1. **The loop mechanics work as designed.** All 4 `Rebar.CreateFromCurves`
   calls inside the single `SubTransaction` succeeded — no exception on the
   2nd/3rd/4th call caused by the 1st/2nd/3rd bar already existing on the
   same host (no "already a rebar there" rejection, no id collision).
2. **All 4 are KEPT writes, not just committed-without-exception.** The
   independent, transaction-free re-read confirms all 4 persist as real
   `Rebar` elements correctly hosted on `425190`, matching #197's own
   "kept, not just committed" bar for what counts as write-proven
   (`docs/token-efficient-expansion.md` §8).
3. **No cross-bar interference.** Distinct `(u, v)` offsets produced
   distinct, independently valid bars — nothing about placing bar N was
   affected by bars 1..N-1 already existing on the same footing host in
   the same transaction.
4. **Still unverified:** this bullet used a plain 4-corner arrangement, not
   `column_layout.perimeter_bar_positions`' own real output for column
   `425531`'s actual `300 x 600mm` section/cover — the POSITION MATH is
   proven separately (unit tests), not re-run here. A mid-loop FAILURE
   (the exact scenario `tests/test_footing_revit_dowels.py`'s
   `test_a_mid_loop_failure_propagates_and_places_nothing_further` proves
   with a mock) was not reproduced live — inducing a genuine
   `Rebar.CreateFromCurves` failure on a live host on demand is not
   straightforward, and the mock-level proof (exception propagates,
   uncaught, out of `place_dowel_bars`) combined with the pushbutton
   script's existing, already-live-host-proven (#197) one-transaction
   rollback pattern is judged sufficient — the failure-path claim is about
   Python/transaction control flow, not Revit API behaviour, so a live
   reproduction would not add information a mock cannot already give.

## 5. What this authorises

`rft.revit.footing_dowels.place_dowel_bars` (#223) is now WRITE-PROVEN: an
N-bar loop of `Rebar.CreateFromCurves`, inside one transaction, on a real
footing host with a real column above it, produces N kept, correctly-hosted
`Rebar` elements with no cross-bar interference. Combined with the
mock-object tests' proof of the LOOP WIRING (right count, right per-bar
position source, mid-loop failure propagates uncaught) and #197's own
kept-write proof of the bent-bar SHAPE, this closes
`docs/token-efficient-expansion.md` §8's verification requirement for #223.

It does **not** authorise assuming the real `perimeter_bar_positions`
output for a specific column places without incident — that is core math,
already unit-tested, not a live-host question.
