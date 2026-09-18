# #103 — does a picked face map back to `column_layout`'s four? (PART 1)

> **Partial. The geometry half is proven; the PICKING half is not run yet.**
> `PickObjects` has still never executed against this host. Everything below
> was read non-interactively, so it answers §5's item 2 (correlation);
> item 3 (rotation) was answered later, by the #104 batch probe. Items 1
> and 4 — the PICKING half — are still not run.

## What ran, and against what

Revit **2024**, build **24.3.40.26**. Document **`ColumnRFT.Trail`** —
confirmed by name in the same call, because a probe is only evidence about the
document it ran against (the lesson R27 was corrected by).

Element **422078**, `450 x 600mm`, category **Structural Columns** — the same
column every other column verification in this folder used.

`el.get_Geometry(Options{ComputeReferences = true, DetailLevel = Fine})`,
walking the one solid's faces.

## Result — six planar faces, and the four that matter

| face | normal | area (ft²) | stable representation |
|---|---|---|---|
| 1 | `(0, 0, -1)` | 2.906 | `…-000670be:9:SURFACE` |
| 2 | `(1, 0, 0)` | 17.438 | `…-000670be:14:SURFACE` |
| 3 | `(0, -1, 0)` | 13.078 | `…-000670be:18:SURFACE` |
| 4 | `(-1, 0, 0)` | 17.438 | `…-000670be:21:SURFACE` |
| 5 | `(0, 1, 0)` | 13.078 | `…-000670be:24:SURFACE` |
| 6 | `(0, 0, 1)` | 2.906 | **(no reference)** |

`HandOrientation = (1, 0, 0)`, `FacingOrientation = (0, 1, 0)`,
`LocationPoint` rotation `0`.

### The correlation is exact, by dot product

**Every vertical face normal is exactly ±`HandOrientation` or
±`FacingOrientation`** — not approximately, at full printed precision. So a
face reference maps to one of `column_layout`'s four by

    dot(face.FaceNormal, HandOrientation)   -> +1 / -1 / 0
    dot(face.FaceNormal, FacingOrientation) -> +1 / -1 / 0

with no tolerance question at this rotation and no ambiguity: exactly one of
the four matches each vertical face. **This is the load-bearing thing §5 item 2
asked for, and it holds.**

### The areas confirm which face is which, and expose the cut

- `±X` faces: 17.438 ft² = 1.620 m² = **0.600 × 2.700**
- `±Y` faces: 13.078 ft² = 1.215 m² = **0.450 × 2.700**
- end faces: 2.906 ft² = 0.270 m² = **0.450 × 0.600** ✓ the section

2.700 m is the **clear** height, not the 3.000 m the column spans
(z 9.8425 ft = 3.000 m at the bottom face, 18.7008 ft = **5.700 m** at the
top). The solid is cut at the top support, exactly as `column_host`'s extent
already reports.

### Face 6, the top face, has NO reference

It is the cut face and `f.Reference` came back null, while the bottom face
(face 1) has one. This matters for §3: a face the engineer cannot pick cannot
be flagged, and the top face is the one a roof column's rule is about. It is
not needed as an *input* — §3 asks for the four **vertical** faces — but any
code that assumes every face of the solid carries a reference is wrong here.

---

## Update — the owner reports the picking half WORKS

> probe picking face is working

The `Pick faces` probe button was run on the live host and the owner
reports it working. **The transcript has not been supplied**, so this
document does not record what it returned.

That distinction is the point of the file. "It worked" answers §5's item 1
— `PickObjects` runs from this host — and answers nothing about item 3
(rotation) or item 4 (a picked slab face, an end face, Escape), each of
which is a specific output this document would have to quote.

**Paste the probe's text and #103 closes on evidence.** Until then item 1
is reported working, on the owner's word, and the rest stands as written
above.

---
## What is still UNPROVEN

1. **`PickObjects` itself.** Never executed against this host. §5 item 1.
2. **Whether it can be run from the MCP path at all.** The MCP executor holds
   an open transaction — `document.IsModifiable` came back **True** in the same
   session. Revit does not allow a pick to be started from inside one, so this
   tracer bullet's picking half probably has to run from the pushbutton's
   `execute_in_revit_context` path, not from MCP. **Probably** — that has not
   been tested either way, and this document does not claim it.
3. ~~**Rotation.**~~ **ANSWERED** — by the #104 batch probe, on columns the
   owner rotated to **45°** and **315°** in the same document. Every vertical
   face normal on both comes back as **exactly ±`Hand` or ±`Facing`**
   (`1.000000` / `0.000000` at full precision), wide faces to ±Hand, exactly
   as on the unrotated columns — so the dot-product correlation above holds
   at a rotation, which is what #69 could only suggest. Recorded in
   `issue-104-batch-grouping.md`.
4. **The refusal paths** — a picked slab face, a picked end face, Escape.

Nothing in `specs/column-roof-termination.md` may be implemented on the
strength of this document. The addendum remains blocked on **#102** regardless
of what the rest of #103 finds.
