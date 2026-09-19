# #92 — the tie snap, measured: it is real, and R22 removes it

**Status: ANSWERED.** Revit 2024 build 24.3.40.26, document
`ColumnRFT.Trail`, run through the Revit MCP connector. Every bar was
created inside a `SubTransaction` that was rolled back; the document's
rebar count was 508 before and 508 after every step.

## The methodology finding, first, because it invalidates other readings

**A bar's position is not settled until `Document.Regenerate()` runs.**

The same two-bar set, read twice in the same sub-transaction:

```
BEFORE regen  bar 0: (154.98, -68.08)     exactly as asked
BEFORE regen  bar 1: (154.98,  93.62)     exactly as asked
AFTER  regen  bar 0: (148.96, -88.32)     drift (-6.02, -20.24)
AFTER  regen  bar 1: (148.96,  73.38)     drift (-6.02, -20.24)
```

Constraints resolve on regeneration. A read taken before it reports the
coordinate that was *requested*, not the one the bar will *occupy* — and
reports it with total confidence.

Three readings taken earlier in this same session were therefore
meaningless, and all three said "no drift":

- an unpinned two-bar set at `v = 80.85`;
- the same set pinned;
- four unpinned bars placed deliberately **on** the inner tie's bend.

That last one was the positive control — the test meant to prove the
experiment could detect a snap at all. It reported no drift, which would
have been read as "#92 no longer reproduces". **It reproduces.** The
control was simply blind.

**Consequence for #183:** that probe read an arrayed bent set's bar
positions without regenerating, and reported exact 0 / 150 / 300 mm
spacing. The bend rendering it measured stands — curve geometry is not a
constraint — but its *spacing* numbers are subject to the same doubt and
should be re-read after a regeneration before they are relied on.

## What the snap actually is

With no pinning, after regeneration, the constraints on the four handles:

| handle | targets |
|---|---|
| Bar Plane | **rebar 424237** (a tie) |
| Bar Segment 1 | **rebar 424237** (a tie) |
| Start of Bar | column 423606 |
| End of Bar | column 423606 |

The two handles that govern the bar's position in section bound
themselves to **another rebar element**, and the pair then translated by
`(-6.02, -20.24)` mm with its spacing preserved at 161.70 — which is
#92's own signature: *"Spacing stayed exact (161.70); the pairs moved."*

#92's item 1 asked which tie a bar binds to, and whether that can be
known. **It can**: `GetCurrentConstraintOnHandle(handle)` returns the
constraint, and `GetTargetElement()` names the element. (`GetPreferred‐
ConstraintForHandle` does **not** exist — the reader is
`GetPreferredConstraintOnHandle`.)

## What R22's pinning does to it

The same set, with `rft.revit.column_place_bars._pin_to_host_faces`'s
sequence applied, after regeneration:

| handle | targets |
|---|---|
| Bar Plane | column 423606 |
| Bar Segment 1 | column 423606 |
| Start of Bar | column 423606 |
| End of Bar | column 423606 |

**No handle targets a rebar any more.** #92's item 3 asked whether the
constraints could be set to host faces so the bar never binds to a tie at
all, and noted that "a host-face constraint was never attempted". It has
been attempted, and it holds: the tie binding is gone.

The pinned bar in this control also *moved* — to `(185.00, -260.00)`,
which is 40 mm from each near face, i.e. exactly the cover line it was
pinned to. That is correct behaviour and not a defect: the control asked
for a bar at an arbitrary interior point, and pinning put it where the
pin said. The tool never asks for such a bar — its layout computes every bar
at the cover offset already.

## The shipped tool's own cages

Which is why the decisive evidence is the tool's output, not a synthetic
bar. Two columns detailed by the shipped tool, read from the saved model
(so, post-regeneration):

**Column 422078** — perimeter tie only:

```
(-167.50, -242.50)  (0.00, -242.50)  (167.50, -242.50)
(167.50,  -80.83)   (167.50, 80.83)  (167.50, 242.50)
(0.00, 242.50)      (-167.50, 242.50)
(-167.50, 80.83)    (-167.50, -80.83)
```

**Column 423606** — perimeter tie **plus an inner 310 × 171 loop**
(element 424233, spanning `u −154.98 … 154.98`, `v −239.51 … −68.08`), so
its intermediate bars at `v = ±80.83` sit ~12 mm from that loop's own
bend — the adjacency #92 describes:

```
identical grid, to the same two decimals
```

**Mirror check on both: 0 of 10 bars without a twin at `(−u, −v)`.**

#92's asymmetry was one bar of four landing differently. Twenty bars
across two columns, one of them in the exact inner-tie configuration,
are symmetric to 0.01 mm.

## Verdict per item

1. **Which tie does a bar bind to, and can it be made deterministic?**
   It binds to a named rebar element, readable through
   `GetCurrentConstraintOnHandle`. Made moot by (3).
2. **Is single-bar-per-set the general answer?** No — and it is not
   needed. R22 already supersedes it, and the sets place exactly.
3. **Can constraints be set to host faces so it never binds to a tie?**
   **Yes, measured.** All four handles retarget to the host.
4. **Does the asymmetry survive save/reopen?** There is no asymmetry in
   the saved model to survive.

## What this page does NOT claim

- It does not claim the snap is impossible. It is live and reproducible
  in this document today, one unpinned bar away. What is established is
  that the **shipped path** does not take it.
- It does not re-measure #183's spacing numbers, which the regeneration
  finding puts in doubt.
- It says nothing about whether a **cross-tie** should alternate its hook
  ends — that is a detailing rule, split to #192.
