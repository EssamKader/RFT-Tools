# Issue #69 — Column tracer bullet (spec §11), verified on a live host

**Status:** P1 PROVEN, P2 PROVEN. Both by execution against a running Revit
session, not by documentation.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26, English_USA |
| Document | `ColumnRFT.Trail.rvt` (non-workshared) |
| Connection | `revit-mcp` MCP server, `send_code_to_revit` (C#) |
| Access | Read **and write** (writes used once, rolled back — see §0) |
| Date | 2026-09-14 |
| Test column | id `421967`, `M_Concrete-Rectangular-Column : 450 x 600mm` |
| Test floor | id `421986`, `Generic 300mm`, Level 2 |
| Levels | Level 1 @ 0 mm, Level 2 @ 3000 mm |

The test column's `a ≠ b` (450 × 600). This is load-bearing for P1: on a
square column a correct orientation read and a wrong one return identical
numbers, and the test could not have failed.

---

## 0. Harness findings (about the MCP executor, not the Revit API)

Recorded because they cost four failed executions and will cost the next
person the same.

1. **The document variable is named `document`** (lowercase). `Document` is
   the *type* and fails to compile; `doc`, `uidoc`, `app`, `uiapp`,
   `commandData`, `uiApplication`, `revitDoc`, `_doc` do not exist.
   Discovered by referencing every candidate in one submission — the
   compiler lists every *undefined* name, so the one absent from the error
   list is the one that exists.
2. **The executor already has a transaction open** — `document.IsModifiable`
   is `True` on entry. `new Transaction(document, ...).Start()` therefore
   throws `Exception has been thrown by the target of an invocation`, with
   no inner detail. Use a **`SubTransaction`** instead.
3. Consequence for safety: a write lands in the *host's* transaction, so it
   cannot be undone by aborting. A `SubTransaction` that is rolled back
   leaves no net change, which is how P1's rotation test was made
   non-destructive. Verified: the column read `0.000°` / 450 × 600 before
   and after.

---

## 1. P1 — Section orientation: which direction is `a`, which is `b`

### The question

Spec §2 makes the **smaller** cross-section dimension govern `S₀` (§4) and
the **larger** govern `L₀` (§3). Reading the two the wrong way round
silently inverts both. A column is a point-based `FamilyInstance` with a
vertical `Location.Point`, so the `Location.Curve` axis reads the beam tool
uses do not apply.

### Confirmed shapes

```
Location runtime type      = LocationPoint          (LocationCurve is null)
LocationPoint.Rotation     = 0.000 rad              (readable, does not throw)
HandOrientation            = (1, 0, 0)
FacingOrientation          = (0, 1, 0)
FacingFlipped / HandFlipped / Mirrored = False / False / False
GetTotalTransform()        = BasisX (1,0,0)  BasisY (0,1,0)  BasisZ (0,0,1)
Type parameters            : b = 450.0 mm,  h = 600.0 mm     (StorageType.Double)
```

### The proof

Measured by tessellating the instance solid's edges and taking the extent
along each candidate direction. Read at 0°, then **inside a rolled-back
`SubTransaction`** at +35°:

| measurement | at 0° | at 35° | invariant? |
|---|---|---|---|
| extent along `HandOrientation` | 450.0 | **450.0** | ✅ tracks `b` |
| extent along `FacingOrientation` | 600.0 | **600.0** | ✅ tracks `h` |
| bounding box `dX` | 450.0 | **712.8** | ❌ |
| bounding box `dY` | 600.0 | **749.6** | ❌ |

### Ruling

> **`b` lies along `HandOrientation`; `h` lies along `FacingOrientation`.**
> Both are unit vectors in model space and are invariant under rotation.
> The section dimensions come from the **type parameters `b` and `h`**, and
> the model-space directions they occupy come from Hand/Facing.

**The bounding box must never be used to derive `a`/`b`.** At 35° it reports
712.8 × 749.6 for a 450 × 600 column — a 58% error on the face that governs
`S₀`. `get_BoundingBox(null)` is axis-aligned in model coordinates and
degenerates to the correct answer only at rotations of 0° / 90° / 180° /
270°, which is precisely why a square or orthogonal test column would have
certified the wrong code as correct.

### Still unverified

- `b`/`h` are the parameter names of the **Autodesk metric
  `M_Concrete-Rectangular-Column`** family. A different family (or an
  imperial/localised one) will name them differently. Reading them by
  literal name is a family-specific assumption — **`SHAPE UNVERIFIED`**
  until the tool's family-handling policy is decided.
- `FacingFlipped` / `HandFlipped` / `Mirrored` were all `False` here. Their
  effect on the mapping above is **untested** — a mirrored column is a
  plausible real-world case and was not present in this model.
- Slanted columns untested (`Column Style = 0`, i.e. vertical).

---

## 2. P2 — Vertical framing neighbours at base and top

### The question

`Hc` is measured support-face to support-face; `L₀` is measured *from the
face of the support* (§3); the first tie sits at an exact 50 mm from that
face (§4); the splice protrudes `L_s` above the **top** support's face (§9).
Every one of those needs a real face at a real elevation, at both ends.

### The single most important finding

```
param Length (level-to-level)   = 3000.0 mm
column SOLID  z bottom -> top   = 0.0 -> 2700.0 mm
floor soffit (bottom face) z    = 2700.0 mm
CLEAR height, base -> soffit    = 2700.0 mm
DELTA                           =  300.0 mm   (= the slab thickness)
```

> **`INSTANCE_LENGTH_PARAM` is NOT `Hc`.** It reports the level-to-level
> length (3000 mm) while the clear height to the support face is 2700 mm.
> Detailing off `Length` would place `L₀`, the 50 mm first tie and every
> subsequent tie 300 mm out of position, in a tool whose entire §3–§5 rule
> set is measured from the support face.

Note the column *solid* already stops at the soffit (2700) — Revit joined it
to the floor. So the solid's own extent happens to agree with the clear
height **in this model**. That agreement must not be relied on: it is a
consequence of the join, not a rule, and an unjoined column would report its
full 3000 mm.

### Method A — `ReferenceIntersector` (works, with one hard rule)

`ReferenceIntersector(ElementMulticategoryFilter, FindReferenceTarget.Element, view3D)`
against the non-template `{3D}` view, ray cast from the column's
`Location.Point`:

| ray | hits | result |
|---|---|---|
| UP from z=1500 (mid-column) | 1 | floor `421986`, proximity 1200 → **hitZ = 2700** (soffit) |
| UP from z=2690 (just below soffit) | 1 | floor `421986`, proximity 10 → **hitZ = 2700** |
| UP from z=2990 (**inside** the slab) | **0** | — |
| DOWN from z=5000 (above everything) | 1 | floor `421986` → **hitZ = 3000** (top face) |
| DOWN from z=10 (column base) | **0** | — |

Two behaviours to build on:

1. **The ray origin must be outside the target solid.** An origin at 2990,
   inside the slab, returns zero hits — it does not return the face it is
   sitting inside. Casting "from the column's top" is therefore the wrong
   instinct; cast from safely below the expected face, upward.
2. **The direction selects the face.** Upward from below yields the soffit
   (2700); downward from above yields the top face (3000). §9's splice
   protrudes above the *top support's face*, so which of the two the code
   wants must be stated per rule, not left to whichever the search returns.

### Method B — `BoundingBoxIntersectsFilter`

A 600 mm probe slab above the top found the floor; below the base found
nothing. It answers "is something there" but returns **no face elevation**,
so it is a cheap pre-filter at best, not a substitute for Method A.

### The base end returns nothing — and that is correct

Both methods found **zero** elements below the column base. There is no
footing and no Level 1 slab in this model. This is not a search failure; it
is a ground-floor column with no base support element, which is exactly
**case C1** (foundation dowels, out of scope per spec §0).

> The vertical search must therefore treat "no support found at this end"
> as a **normal, expected outcome**, not an error — and the disposition for
> it is the open decision in #73. A search that assumes a face exists at
> both ends will throw on the very first ground-floor column.

### Still unverified

- Only a **floor** was tested as the supporting element. Beams
  (`OST_StructuralFraming`), foundations and walls were in the category
  filter but **none were present in the model** — their behaviour is
  assumed, not observed. **`SHAPE UNVERIFIED`**.
- `ReferenceIntersector` requires a non-template `View3D`. `{3D}` was used.
  What the tool does when no such view exists in the project is untested.
- Multiple stacked hits (column passing several levels) untested — out of
  scope anyway per C2, but the search returns a *list* and the picking rule
  is undefined.
- Base/top **offset** parameters were both 0. Non-zero offsets untested.

---

## 3. Incidental finding — rebar cover is not fully set

Read from the test column's instance parameters:

```
Rebar Cover - Bottom Face  = 112574 -> Interior (framing, columns)
Rebar Cover - Other Faces  = 112574 -> Interior (framing, columns)
Rebar Cover - Top Face     = -1        <- NOT SET
```

Spec §1 requires cover to be an **editable input, not a hardcoded
constant**, in the same discipline as the beam tool's per-face cover reads.
A per-face read on this column would return an invalid `ElementId` for the
top face. Whatever the cover input does, it cannot assume all three cover
parameters are populated.

---

## 4. What this authorises

Spec §11's precondition is met for both items. `rft.core.column_layout` and
the WPF window may now be designed against:

- `b` → `HandOrientation`, `h` → `FacingOrientation`, dimensions from type
  parameters, **never** from the bounding box.
- Clear height derived from a **face search**, never from
  `INSTANCE_LENGTH_PARAM`.
- A vertical search that may legitimately find **nothing** at the base.

It does **not** authorise any placement logic. No `Rebar` was created,
and nothing in this write-up verifies a single placement API shape.
