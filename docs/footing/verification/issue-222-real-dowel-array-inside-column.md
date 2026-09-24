# Real dowel array positions, verified INSIDE the column footprint

**Status:** WRITE-PROVEN (kept, not rolled back). Found by Essam
visually inspecting the trial model: the earlier #223/#226 tracer
bullets' dowel bars (illustrative `(u, v)` offsets, ±300/±200mm, chosen
only to prove the WRITE LOOP mechanics) landed OUTSIDE the real column
`425531`'s own footprint — correctly flagged as looking wrong, because a
dowel is supposed to be the continuation of a real column vertical bar
(R6, `docs/footing/spec-amendments.md`) and must therefore sit INSIDE
the column's section, not outside it.

This closes the gap those two docs' own "Still unverified" notes named
explicitly: neither #223's nor #226's tracer bullet used
`column_layout.perimeter_bar_positions`' own REAL output for the real
column's REAL section — both said so in their own text. This bullet
does.

| | |
|---|---|
| Host | Same live Revit session used throughout this session, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` |
| Access | Read and write — a `SubTransaction` was **committed, not rolled back** |
| Date | 2026-09-24 |
| Footing / column | `425190` / `425531` — the one real footing+column pair in this model |
| Column's own live-read values | `b=300mm`, `h=600mm` (`FamilySymbol.LookupParameter("b"/"h")`), `cover=40mm` (`CLEAR_COVER_OTHER` → `RebarCoverType.CoverDistance`) — the EXACT values `column_host.read_section_mm`/`read_cover_mm` would read, confirmed directly rather than assumed |
| Dowel/tie bar types used | `423952` (16.0mm) / `423949` (10.0mm) — real `RebarBarType` elements already in the document |
| Array inputs | `count_b_face=3`, `count_h_face=4` (illustrative, not an engineer input — the POSITION FORMULA is what's under test, not a specific count choice) |
| Elements deleted (cleanup) | `425598`, `425599` (#223's own illustrative dowels), `425616`, `425617`, `425620`, `425621` (#226's own illustrative dowels) — all placed at arbitrary offsets never derived from a real column section |
| Elements created | `425632`-`425641` — 10 bent dowel bars, one per `perimeter_bar_positions`' own real output |

---

## 1. The question

`rft.core.footing_plan._build_dowel_plan` calls `column_layout.
perimeter_bar_positions(b_mm=Cw_mm, h_mm=Cd_mm, cover_mm=Ccover_mm,
tie_dia_mm=..., bar_dia_mm=..., count_b_face=..., count_h_face=...)` to
get every real dowel's footing-local `(u, v)` position. That function is
already unit-tested in isolation (`tests/test_column_layout.py`), and its
formula (`half_u = b_mm/2 - offset`, `offset = cover + tie + bar/2`)
mathematically cannot produce a `u`/`v` outside `±b_mm/2`/`±h_mm/2` by
construction — but has this EVER been run against a REAL column's REAL
live-read section and checked against that SAME column's REAL bounding
box on a live host? No prior verification doc in this session did that;
both #223's and #226's own tracer bullets used arbitrary offsets
specifically to avoid re-testing this exact math.

## 2. Method

1. Read column `425531`'s own real `b`/`h`/cover live (300mm/600mm/40mm)
   — the exact values `read_dowel_column_section_mm` (#221) would
   produce for this column, confirmed by direct parameter read rather
   than assumed from an earlier session's different test column.
2. Ran `rft.core.column_layout.perimeter_bar_positions(b_mm=300.0,
   h_mm=600.0, cover_mm=40.0, tie_dia_mm=10.0, bar_dia_mm=16.0,
   count_b_face=3, count_h_face=4)` in plain CPython (the same
   already-unit-tested, pure function `_build_dowel_plan` calls) and took
   its own 10-bar `(u, v)` output as data — not re-derived, not
   hand-computed.
3. Deleted the six illustrative, wrongly-positioned dowel bars #223/#226
   left in the model (their own docs already flagged these as
   illustrative, not production-representative).
4. Placed one bent dowel `Rebar` per position from step 2, hosted on
   footing `425190`, tagged `RFT-FTG-425190` — the same
   `_create_dowel_rebar`/`tag_as_ours` shape #223/#226 already used, only
   the POSITIONS differ (real, not illustrative).
5. Committed the `SubTransaction` (kept).
6. For every created bar, read its own vertical leg's top endpoint
   (`Rebar.GetCenterlineCurves`) and checked it against column `425531`'s
   own live `get_BoundingBox(null)` — in the SAME call, immediately after
   creation.
7. A **separate**, later `send_code_to_revit` call with no transaction
   open re-read all 10 ids, confirming persistence, host and tag.

## 3. Result

```
Created=425632,425633,425634,425635,425636,425637,425638,425639,425640,425641
ColumnBBox X[-16921.6,-16621.6] Y[-2813.0,-2213.0]
425632: X=-16863.6 Y=-2755.0 insideColumn=True
425633: X=-16771.6 Y=-2755.0 insideColumn=True
425634: X=-16679.6 Y=-2755.0 insideColumn=True
425635: X=-16679.6 Y=-2593.7 insideColumn=True
425636: X=-16679.6 Y=-2432.4 insideColumn=True
425637: X=-16679.6 Y=-2271.0 insideColumn=True
425638: X=-16771.6 Y=-2271.0 insideColumn=True
425639: X=-16863.6 Y=-2271.0 insideColumn=True
425640: X=-16863.6 Y=-2432.4 insideColumn=True
425641: X=-16863.6 Y=-2593.7 insideColumn=True
outsideCount=0

Independent persistence check (separate call, no open transaction):
okCount=10/10 -- every bar exists, is a Rebar, hosted on 425190,
tagged RFT-FTG-425190. DocumentIsValidObject=True.
```

## 4. Findings

1. **The real production position math keeps every dowel inside the
   column footprint, on a live host, not just in a unit test.** All 10
   bars computed by `perimeter_bar_positions` from the column's OWN
   live-read section/cover land strictly within that column's own
   bounding box (`outsideCount=0`).
2. **The earlier illustrative debris was exactly that — illustrative,
   not a production defect.** #223's/#226's own tracer bullets used
   arbitrary `(u, v)` offsets (±300/±200mm) chosen only to exercise the
   WRITE LOOP, explicitly not tied to any real column section — both
   docs said so in their own "Still unverified" notes. This was
   confirmed, not merely asserted: the real formula, given the real
   column's real numbers, produces different (and correctly bounded)
   positions.
3. **Cleanup, not a code fix.** No source file changed as a result of
   this check — `rft.core.column_layout.perimeter_bar_positions` and
   `rft.core.footing_plan._build_dowel_plan` were already correct
   (proven here, not patched). The action taken was deleting six
   misleading model elements that never represented real tool output.

## 5. What this authorises

The dowel array's own POSITION FORMULA (`perimeter_bar_positions`, R6's
reuse target) is now live-host-verified against a REAL column's REAL
section, closing the specific gap #222's/#223's/#226's own docs each
flagged and deferred. Combined with #223's own proof of the N-bar WRITE
LOOP and #226's own proof of the N-FOOTING loop, the full dowel-array
pipeline (detect column → read its real section → compute real positions
→ place every bar → tag it) is now verified end-to-end, on a live host,
with real numbers at every step, for the one real footing+column pair
this trial model contains.

**Addendum, 2026-09-24 (Essam, second screenshot) — this bullet's own
check was incomplete, not wrong.** The `insideColumn` check above reads
each bar's VERTICAL LEG's own `(u, v)` position only -- it never checked
which way the HOOK bent. This bullet's own C# script still bent every
one of the 10 hooks along a single fixed world `+X`, the exact same
un-directional placeholder R10 (`docs/footing/spec-amendments.md`)
exists to replace -- so several of these 10 bars (on the left/top/bottom
faces) had their hooks pointing the wrong way, which is what Essam's
second screenshot caught. The POSITION claim above stands; the
DIRECTION claim was never made or tested here. See
`docs/footing/verification/issue-232-dowel-hook-outward-direction.md`
for the corrected, direction-aware re-verification.
