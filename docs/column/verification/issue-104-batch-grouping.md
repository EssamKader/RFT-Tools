# #104 — what may "the same type" mean for a batch?

> **Answered, and the answer is no.** A family type does **not** determine
> the cage. Two `450 x 600mm` columns on the **same two levels** differ by
> 300 mm of clear height in this model.

## What ran, and against what

Revit **2024**, build **24.3.40.26**. Document **`ColumnRFT.Trail`** —
named in the same call, because a probe is only evidence about the document
it ran against (the lesson R27 was corrected by).

Read-only, no transaction. Two passes:

1. Every `OST_StructuralColumns` instance, with the parameters
   `rft.revit.column_host` already reads per column: the base/top level and
   offsets, `CLEAR_COVER_OTHER`, `CLEAR_COVER_TOP`, the type's `b`/`h`,
   `HandOrientation`/`FacingOrientation` and the location rotation.
2. Each column's **solid** extent — the z of its top and bottom planar
   faces, which is the cut solid the tool actually details.

## The model: 10 columns, 2 types

### `450 x 600mm` — five instances, and they are NOT interchangeable

| id | levels | **clear height** | top cover set |
|---|---|---|---|
| 421967 | Level 1 → Level 2 | **2700** | no |
| 422316 | Level 1 → Level 2 | **2700** | no |
| 423606 | Level 1 → Level 2 | **3000** | **yes** |
| 422078 | Level 2 → Level 3 | **2700** | no |
| 422840 | Level 2 → Level 3 | **3000** | **yes** |

Every one of them shares: family, type name, `b` = 450, `h` = 600, cover
`Interior (framing, columns)`, rotation 0,
`Hand = (1,0,0)`, `Facing = (0,1,0)`, zero base and top offsets.

**And 421967 and 423606 are on the same two levels and differ by 300 mm of
clear height.**

Levels are at 0, 3000 and 6000, so the storey is 3000 throughout. The
columns reading 2700 are **cut by a beam or slab above**; the two reading
3000 run the full storey and have `CLEAR_COVER_TOP` **set**, which is
exactly the exposed-top-face condition #87 already treats as meaningful.
The correlation is perfect across all five.

### `300 x 600mm` — five instances, genuinely identical

ids 424280, 424284, 424287, 424290, 424293. Base Level 1 with a **−2500**
offset, top Level 1, clear height **2500**, every read field identical.
This group *is* batchable, and it is what a batch looks like when it is
safe.

## Why this settles the grouping rule

Clear height is not a detail. It drives:

- `L0` — `max(Hc/6, larger section dimension, 500)`; at 2700 the governing
  term is the 600 mm section, at 3000 it is still 600, but
- the **tie ladder**: both confinement zones and the equally-divided middle
  run are built from the clear height, so the number of ties and their
  levels differ;
- the **splice** geometry, measured from the top support face.

Detailing a 3000 mm column with a 2700 mm column's ladder produces a cage
that looks right in the browser and is short by a tie. That is precisely
the failure `CONTEXT.md`'s rules exist to refuse.

**So the batch key cannot be the family type.** It has to be what the tool
actually reads.

## The rule the data supports

**Group by the computed extent, not by the type.**

- The **type is the filter the engineer chooses with** — "every 450 × 600"
  is how a person thinks about it, and it should stay the way they select.
- The **batch key is `(clear height, whether a top support was found)`**,
  plus anything else `read_column` refuses on. Columns sharing a type but
  not a key are **separate runs**, and the report must say so rather than
  merging them.
- A group of one is not an error. 423606 would simply be its own run.

**This is a finding, not a ruling.** The owner has not been asked whether a
batch should split silently, refuse, or ask — and that question is now
worth asking with these numbers in hand rather than in the abstract.

## What this probe did NOT establish

1. **`read_column`'s own verdict.** It is Python in `RFT.lib` and cannot be
   executed through the MCP channel, so the clear heights above are the
   **solid's** extent, not the value the tool computes. They agree for
   422078 — 3000…5700, clear 2700 — which is the column every other
   verification in this folder used, so the correspondence is established
   for one column and inferred for the rest.
2. **Whether any of these columns is refused** as out of scope (#87's
   refusal paths), which would remove it from a batch before grouping ever
   arises.
3. **Rotation as a splitter.** Every column here reads rotation 0 and the
   same Hand/Facing, so this model cannot say whether a rotated column
   belongs in the same batch. #69 found Hand/Facing invariant under a 35°
   rotation, which suggests it does not matter — suggests, on a different
   question.
4. **Performance.** Ten columns says nothing about a hundred, and #104's
   own text raises one transaction versus many. Untouched here.

## Reproducing it

The probe is a throwaway button outside the repo,
`RFTProbe.extension/Probe.tab/Probe.panel/BatchGroups.pushbutton`, written
so it does not depend on the MCP channel being up. It reports, per family
type, which fields vary between instances and marks them.
