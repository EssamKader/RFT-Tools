# Issue #220 — Footing→column auto-detect ray-cast, verified on a live host

**Status:** READ-PROVEN (rolled back — no transaction was opened, nothing
was written). This closes the specific gap `RFT.lib/rft/revit/
footing_host.py`'s own module docstring and PR #224 flagged: the claim "a
`View3D` that can self-test-see a footing (`OST_StructuralFoundation` ray)
can also see the `OST_StructuralColumns` element above it" had never been
measured live — only the same *shape* of trust in `column_host.py` had
been (#69/#107, column→support direction). This measures the *opposite*
direction, `footing_host.py`'s own new code.

| | |
|---|---|
| Host | Same live Revit session used for #197/#69, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` (confirmed via `document.Title` before this bullet) |
| Connection | `revit-mcp` MCP server, `send_code_to_revit` (C#) |
| Access | Read only — no `Transaction`/`SubTransaction` opened, nothing written |
| Date | 2026-09-24 |
| Code tested | `RFT.lib/rft/revit/footing_host.py`'s `find_search_view`/`find_column_above` logic, reproduced in C# line-for-line against the live document (same ray origins, same `RAY_CLEARANCE`/inset constants, same category filters) |

---

## 0. Harness finding (re-confirmed, not assumed)

`send_code_to_revit`'s in-scope variable is **`document`** (lowercase),
matching #69/#197 exactly — confirmed by reflecting the generated
`AIGeneratedCode.CodeExecutor.Execute(Document document, object[]
parameters)` signature directly, since a first attempt using `doc` failed
to compile ("`doc` does not exist in the current context").

## 1. The question

`footing_host.find_search_view` self-tests a candidate `View3D` with an
`OST_StructuralFoundation` ray at the footing itself (there is no known
column yet — that's what's being searched for), then `find_column_above`
reuses that SAME view, unquestioned, for an `OST_StructuralColumns`
upward ray. Does a view proven to see a foundation actually see a
structural column above it, or could the two categories differ in
`ReferenceIntersector` visibility the way `column_host.py`'s own
`{3D}`/`Analytical Model` finding showed two seemingly-identical views
disagreeing on what they can see?

## 2. Method

Reproduced the module's exact two-step logic in C#, run against every
`OST_StructuralFoundation` instance in the live document (not a synthetic
single case):

1. For each footing: collect its bounding box, compute plan centroid and
   `probe_z`/`inset` exactly as `footing_host.py` does.
2. Self-test every non-template `View3D` with an `OST_StructuralFoundation`
   ray at the footing (`origin = centre - 6*RAY_CLEARANCE` along X,
   direction `+X`) — record which view (if any) sees the footing itself.
3. Using that same view, fire the upward `OST_StructuralColumns` ray
   (`origin = (cx, cy, box.Max.Z - inset)`, direction `+Z`,
   `FindNearest`) and record the result.

No `Transaction` or `SubTransaction` was opened — every call is a read
(`FilteredElementCollector`, `ReferenceIntersector.Find`/`FindNearest`,
`get_BoundingBox`), so there is nothing to roll back.

## 3. Result

```
Foundations found: 3
Non-template 3D views: 2 -> Analytical Model, {3D}

Footing 425131 (1800 x 1200 x 450mm)
  Self-test via 'Analytical Model': hits=0 sawFootingItself=False
  Self-test via '{3D}': hits=1 sawFootingItself=True
  RESULT: no column found above this footing via the self-tested view.

Footing 425190 (1800 x 1200 x 450mm)
  Self-test via 'Analytical Model': hits=0 sawFootingItself=False
  Self-test via '{3D}': hits=1 sawFootingItself=True
  RESULT: FOUND column Id 425531 (300 x 600mm), IsFamilyInstance=True, proximity=0.369

Footing 425423 (1800 x 1200 x 450mm)
  Self-test via 'Analytical Model': hits=0 sawFootingItself=False
  Self-test via '{3D}': hits=1 sawFootingItself=True
  RESULT: no column found above this footing via the self-tested view.
```

**Independently confirmed these are TRUE negatives, not ray misses:**
queried every `OST_StructuralColumns` element's own bounding box against
each footing's plan centroid. Only footing `425190`'s centroid falls
inside a column's footprint (column `425531`, bottom at the footing's own
top Z, confirming it actually sits ON that footing) — footings `425131`
and `425423` genuinely have no column placed above them in this model.
`425423` is the same footing #197's tracer bullet placed a mesh/dowel
`Rebar` on — consistent with it never having had a column added.

## 4. Findings

1. **The self-test technique transfers.** `{3D}` self-tests successfully
   against `OST_StructuralFoundation` for all three footings;
   `Analytical Model` sees none of them — the exact same two-view split
   `column_host.find_search_view` already found for
   `OST_StructuralColumns` (#69/#107). One more data point that "chosen by
   behaviour, never by name" is the right rule, not a coincidence specific
   to columns.
2. **The flagged assumption is CONFIRMED, not just plausible.** The `{3D}`
   view, proven only against `OST_StructuralFoundation`, correctly found
   the real column (`425531`) sitting on footing `425190` when searched
   with `OST_StructuralColumns` through that same view instance — with no
   re-proving step in between. This is the specific claim `footing_host.py`
   flagged as unmeasured; it now has a live, positive measurement.
3. **The refusal path is also exercised correctly**, not merely an
   untested branch: two footings with no real column above them correctly
   produced "no column found," matching `find_column_above`'s documented
   "No column is attached to this footing." behaviour — verified as a true
   negative by an independent bounding-box check, not assumed from the
   ray simply returning null.
4. **Still open:** this document proves the READ side only, on a model
   with exactly one real footing→column pairing to test against, and
   `Analytical Model` never got a chance to prove or disprove the same
   self-test/search-category transfer (it could not even self-test).
   Multiple-columns-along-one-ray and a non-rectangular/flipped column
   above a footing remain untested — those paths are #221's own refusals
   (`column_host.read_section_mm`/`read_orientation`), already
   independently live-verified for ColumnRFT (#87/#69), not re-tested
   here.
