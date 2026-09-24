# Issue #228 — Footing plan dimensions/thickness/cover, live parameter names confirmed

**Status:** READ-PROVEN (no transaction opened, nothing written — a pure
`Parameters` enumeration and targeted `get_Parameter` reads). This closes
the ticket's own required first step: "**Do not guess the parameter
names**... this ticket's own first step must be a live-host probe."

| | |
|---|---|
| Host | Same live Revit session used for #197/#69/#220/#223, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` (confirmed via `ping`'s `document.title`) |
| Connection | `revit-mcp` MCP server, `send_code_to_revit` (C#) |
| Access | Read only — no `Transaction`/`SubTransaction` opened |
| Date | 2026-09-24 |
| Footing family/type probed | `M_Footing-Rectangular`, `1800 x 1200 x 450mm` (the SAME family #197/#220/#223 already used) |
| Instances probed | `425190` (full enumeration), then `425131`/`425423` (targeted re-check) — the same three footings #220's own verification names |

---

## 1. The question

`column_host.read_section_mm` reads a column's `b`/`h` via
`FamilySymbol.LookupParameter("b"/"h")` — FAMILY-DEFINED parameter names,
since a column's cross-section has no dedicated Revit `BuiltInParameter`.
Does a structural foundation family expose an equivalent, and if so, is it
a family-defined parameter (needing the same by-name `LookupParameter`
approach) or a fixed `BuiltInParameter` (more robust — independent of
family authoring/renaming/UI language)? Same open question for cover:
does a foundation carry a single uniform cover like a column's
`CLEAR_COVER_OTHER`, or something else (the ticket's own guess was
`CLEAR_COVER_BOTTOM`/`CLEAR_COVER_TOP` as "plausible candidates")?

## 2. Method

1. Enumerated EVERY parameter (`Definition.Name`, `StorageType`, value,
   and — via `((InternalDefinition)p.Definition).BuiltInParameter`, the
   same reflection technique used elsewhere in this repo — the
   `BuiltInParameter` enum name where one exists) on both `footing.Symbol`
   (TYPE) and `footing` itself (INSTANCE), for footing `425190`.
2. Isolated every parameter whose name contains `"Cover"`, and for each,
   resolved its `ElementId` value to the `RebarCoverType` it names
   (`.Name`, `.CoverDistance * 304.8` for mm) — the same resolution
   `column_host.read_cover_mm` already performs for `CLEAR_COVER_OTHER`.
3. Re-ran the plan-dimension/thickness/cover-set reads (this time by
   `BuiltInParameter`, not full enumeration) against `425131`/`425423` —
   the other two footings in the model — to confirm the same
   `BuiltInParameter`s resolve consistently across instances of this
   family/type, not just the one instance first enumerated.

## 3. Result

### 3.1 Full parameter enumeration (footing 425190)

Plan dimensions/thickness are TYPE (`Symbol`) parameters with fixed
`BuiltInParameter`s — NOT family-defined, unlike a column's `b`/`h`:

```
Length              | storage=Double | value=5.90551181102362 (ft) | builtin=STRUCTURAL_FOUNDATION_LENGTH
Width               | storage=Double | value=3.93700787401575 (ft) | builtin=STRUCTURAL_FOUNDATION_WIDTH
Foundation Thickness| storage=Double | value=1.47637795275591 (ft) | builtin=STRUCTURAL_FOUNDATION_THICKNESS
```

`5.90551181102362 ft x 304.8 = 1800.0mm`, `3.93700787401575 ft = 1200.0mm`,
`1.47637795275591 ft = 450.0mm` — matching this type's own name
(`"1800 x 1200 x 450mm"`) exactly.

Cover is THREE separate INSTANCE parameters (footing itself, not
`Symbol`) — a foundation does NOT use a column's single uniform
`CLEAR_COVER_OTHER`:

```
Rebar Cover - Bottom Face | builtin=CLEAR_COVER_BOTTOM | coverTypeId=112574 | coverTypeName=Interior (framing, columns) | coverDistanceMm=40
Rebar Cover - Top Face    | builtin=CLEAR_COVER_TOP    | coverTypeId=112574 | coverTypeName=Interior (framing, columns) | coverDistanceMm=40
Rebar Cover - Other Faces | builtin=CLEAR_COVER_OTHER  | coverTypeId=112574 | coverTypeName=Interior (framing, columns) | coverDistanceMm=40
```

(`CLEAR_COVER_TOP`/`CLEAR_COVER_OTHER` are the SAME `BuiltInParameter`
names `column_host.py` already uses for a column's own top/other-face
cover; `CLEAR_COVER_BOTTOM` is the footing-only addition — a column has no
bottom face.)

### 3.2 Cross-instance re-check (425131, 425423)

```
425131: Length=1800mm Width=1200mm Thickness=450mm bottomCoverSet=True topCoverSet=True otherCoverSet=True
425423: Length=1800mm Width=1200mm Thickness=450mm bottomCoverSet=True topCoverSet=True otherCoverSet=True
```

All three footings in the model (the same three #220's own verification
enumerated) resolve identically — this is not a fluke of one instance.

## 4. Findings

1. **A structural foundation's plan dimensions/thickness are fixed
   `BuiltInParameter`s, more robust than a column's family-defined
   `b`/`h`.** `read_footing_geometry_mm` reads
   `STRUCTURAL_FOUNDATION_LENGTH`/`_WIDTH`/`_THICKNESS` via
   `symbol.get_Parameter(BuiltInParameter....)`, not a name-based
   `LookupParameter` — the parameter identity does not depend on how a
   given family happened to name/rename them.
2. **Cover is three separate instance parameters, confirming the ticket's
   own guess.** `CLEAR_COVER_BOTTOM`/`CLEAR_COVER_TOP`/`CLEAR_COVER_OTHER`
   all exist and were all set on every footing probed — `read_footing_
   geometry_mm` reads all three (`bottom_cover_mm`/`top_cover_mm`/
   `cover_mm` respectively), refusing per-parameter if any one is missing
   or unset, same discipline `column_host.read_cover_mm` already applies.
3. **`a_mm`/`b_mm` mapped from `Length`/`Width` respectively** — matching
   this family's own type name and `IsolatedFootingRFT.pushbutton/
   script.py`'s pre-existing default prompts (`a=1800` X-direction,
   `b=1200` Y-direction) exactly. **Still open, not independently proven
   here:** WHICH of the family's own local axes `Length`/`Width` actually
   run along was not re-derived the way #69 proved column `b`/`h` against
   a deliberately-rotated instance — this probe confirms the parameter
   NAMES and VALUES on an axis-aligned footing (the only kind this tool
   supports at all — `footing_mesh._footing_origin` already refuses a
   rotated one), not a rotation-independent axis proof. Flagged rather
   than silently assumed, matching this repo's own standing practice for
   an assumption carried forward without a dedicated measurement.

## 5. What this authorises

`rft.revit.footing_host.read_footing_geometry_mm` (#228) reads REAL,
live-confirmed parameter names and values, not guessed ones:
`STRUCTURAL_FOUNDATION_LENGTH`/`_WIDTH`/`_THICKNESS` (TYPE) and
`CLEAR_COVER_BOTTOM`/`_TOP`/`_OTHER` (INSTANCE), each refusing by name if
missing or unset. This satisfies R8's ruling — footings measuring
identically on these six values will build identical `FootingInputs`
geometry fields automatically, the prerequisite #226's batch grouping key
needs.

It does **not** authorise assuming `Length`/`Width` map to the SAME plan
axis for every footing family in the wild (only `M_Footing-Rectangular`
was probed — same caveat every other footing/column verification doc in
this repo already carries for its own single tested family), nor does it
re-prove the axis-mapping the way #69 did for columns.
