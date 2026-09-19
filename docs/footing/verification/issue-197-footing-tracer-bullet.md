# Issue #197 — Footing tracer bullet (spec §11 / §6), verified on a live host

**Status:** WRITE-PROVEN. A `Rebar` element was created on an isolated
(pad) footing host and the write was **committed, not rolled back** — this
is the write-proving bullet the column tool's own tracer bullet (#69)
explicitly did not attempt (see `docs/column/verification/issue-69-column-tracer-bullet.md`
§4: *"It does not authorise any placement logic. No Rebar was created."*).
This write-up closes exactly that gap, for the footing element.

| | |
|---|---|
| Host | Same live Revit session used for the column tracer bullet, reached via `revit-mcp` |
| Document | `ColumnRFT.Trail.rvt` (confirmed via `document.Title` before writing anything) |
| Connection | `revit-mcp` MCP server, `send_code_to_revit` (C#) |
| Access | Read **and write** — writes committed, not rolled back (see §0) |
| Date | 2026-09-19 |
| Footing family/type used | `M_Footing-Rectangular`, `1800 x 1200 x 450mm` (FamilySymbol id `1744`) |
| Footing instance created | id `425423` |
| Mesh-style rebar created | id `425425`, bar type `13M`, horizontal, hosted on `425423` |
| Dowel-style rebar created | id `425426`, bar type `16M`, vertical, protruding above the footing top, hosted on `425423` |
| Level | `Level 1` @ elevation 0 |

---

## 0. Harness findings (about the MCP executor, confirmed independently of #69)

Re-confirmed rather than assumed, since a probe call costs nothing:

1. **`document` (lowercase) is the in-scope variable** — same as #69 found
   for the column tracer bullet. Confirmed with a one-line probe
   (`document.Title`) before writing any footing/rebar code.
2. **The executor already holds an open transaction.** Same as #69: use a
   `SubTransaction`, not `Transaction.Start()`.
3. **Unlike #69, this bullet commits its `SubTransaction`s** rather than
   rolling them back — per `docs/token-efficient-expansion.md` §8, a
   rolled-back write proves nothing about write behavior, only about reads.
   Both the mesh-style bar and the dowel-style bar were committed and their
   persistence was re-verified in a **separate, later** `send_code_to_revit`
   call with no open transaction at all (§3 below) — this is what makes the
   "kept write" claim real rather than assumed from the commit call
   succeeding without exception.

---

## 1. P1 — Can `Rebar.CreateFromCurves` host directly on an isolated footing `FamilyInstance`?

### The question

Spec §4–§10 assume mesh bars, dowels, dowel ties and the perimeter tie can
all be placed with the footing as host. Nothing in the column tool's prior
verification touched a `StructuralFoundation`-category host — this was
entirely unverified before this ticket.

### The proof

A footing instance (`M_Footing-Rectangular`, 1800×1200×450mm) was placed on
`Level 1` via `NewFamilyInstance(..., StructuralType.Footing)`. A single
straight horizontal `Rebar` (bar type `13M`) was then created with
`Rebar.CreateFromCurves(document, RebarStyle.Standard, barType, null, null,
footingInstance, XYZ.BasisZ, curves, ...)`, using the footing `FamilyInstance`
directly as the `host` argument — no cast, no wrapper, no intermediate
analytical element.

```
FootingInstanceId = 425423
FootingCategory   = Structural Foundations
RebarId           = 425425
RebarHostId       = 425423   <- resolves back to the footing instance
TRANSACTION       = COMMITTED (KEPT WRITE)
```

### Ruling

> **An isolated footing `FamilyInstance` (category `OST_StructuralFoundation`)
> is a valid, direct host for `Rebar.CreateFromCurves` with no special
> handling.** No `RebarHostData` setup, no cover-parameter pre-configuration,
> and no analytical-model step were required to get a first bar placed. This
> mirrors the ease with which #69's environment placed rebar conceptually on
> a column — the host-acceptance behavior generalizes to this category too.

## 2. P2 — Can a dowel-style bar protrude beyond the footing's own geometry, hosted on the footing?

### The question

Spec §8's entire embedment model (`a_dowel + b_dowel`, and the hook upgrade
when `LD > a_dowel + b_dowel`) depends on a dowel bar that starts inside the
footing and continues **above** the footing's own top face, into where the
column will sit. If the footing host only accepts curves fully contained
within its own solid, §8 could not be implemented as specified.

### The proof

A second `Rebar` (bar type `16M`, vertical) was created on the **same**
footing host (`425423`), running from `z = footing.Min.Z + 0.3'` up to
`z = footing.Max.Z + 2.0'` — i.e. two feet **above** the footing's own top
face, well outside the footing's own bounding box.

```
DowelRebarId  = 425426
DowelHostId   = 425423
TRANSACTION   = COMMITTED (KEPT WRITE)
```

### Ruling

> **A rebar hosted on a footing is not clipped or rejected for extending
> beyond the footing's own solid geometry.** The host relationship governs
> which element the bar is associated/grouped with for scheduling and
> ownership, not a geometric containment constraint. §8's dowel embedment
> model (bar starts inside the footing, continues up into the column above)
> is implementable as specified — the API does not need a special "starter
> bar" mechanism distinct from an ordinary hosted `Rebar`.

## 3. Independent persistence check (proves "kept," not just "committed without exception")

A **separate** `send_code_to_revit` call, issued after both writes above and
opening no transaction of its own, re-read all three elements purely by
`ElementId`:

```
FootingExists      = True
MeshRebarExists    = True
DowelRebarExists   = True
MeshRebar.Quantity = 1        (GetShapeDrivenAccessor() non-null)
DowelRebar.Quantity = 1
DocumentIsValidObject = True
```

This confirms the writes are genuinely in the document, not merely
un-exceptioned inside the same transaction that created them — the
distinction `docs/token-efficient-expansion.md` §8 requires.

**Caveat found and worth recording:** `get_current_view_elements` (the MCP
tool, filtered to `OST_StructuralFoundation`) returned **zero** results for
the same footing immediately after this check succeeded by direct
`ElementId` lookup. This is a **view-scoping artifact** (the placed
elements are outside the active `{3D}` view's crop/section box, at
`X=-10', Y=30'`, away from the rest of the model), not evidence against
persistence — the direct `ElementId` read is authoritative and unaffected
by view crop. **Do not use `get_current_view_elements` as the persistence
check for anything placed outside a view's visible extent** — use a direct
`document.GetElement(ElementId)` read instead, as done here.

## 4. Still unverified

- Only `M_Footing-Rectangular` (a rectangular, Autodesk-metric family) was
  tested. A different footing family may expose different host behavior —
  **`SHAPE UNVERIFIED`** for any other footing family, same caveat #69
  raised for column families.
- Closed-loop shapes (a real `dowel_tie`/`perimeter_tie` rectangle, per §9/
  §10) were **not** tested here — only straight, unhooked curves. §9's
  reuse of `ColumnRFT`'s tie/stirrup geometry logic is a shape-generation
  question, not a host-acceptance question, but the actual `RebarShape`
  used by `column_ties.py` should still be exercised against a footing host
  before ticket #203 (dowel stirrups) assumes it transfers without
  friction.
- No hook types were exercised (`startHookType`/`endHookType` were both
  `null` in both calls). Spec §5's hook logic and §8's dowel hook upgrade
  both require a real `RebarHookType` — untested here.
- Cover parameters on the footing instance were not read or set. Whether
  `Rebar.CreateFromCurves` silently clamps to an unset/default cover on a
  footing host (as #69 found Revit does for columns) is unconfirmed.
- Only one footing was placed in isolation, with no column instance
  actually resting on it — the real footing-supports-column relationship
  (as opposed to a standalone footing) was not modeled or tested.

## 5. What this authorises

Both real unknowns named in spec §11 item 1 and this ticket's own framing
are now proven, by execution, with kept writes:

- An isolated footing `FamilyInstance` is a direct, unmodified valid host
  for `Rebar.CreateFromCurves` (§1).
- A dowel-style bar may extend beyond the footing's own geometry while
  still hosted on it (§2) — §8's embedment model is implementable as
  written.

It does **not** authorise assuming hook types, closed-loop tie shapes, or
cover-parameter handling behave the same way — those remain open per §4 and
should be confirmed inside the tickets that first need them (#203 for tie
shapes reused from ColumnRFT, #199/#202 for hook types), not assumed from
this write-up.
