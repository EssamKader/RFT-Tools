# Column RFT — Batch Placement Addendum

> **Status: rules LOCKED, tracer bullet DONE, not yet implemented.**
> The grouping rule below is derived from measurements on a live host
> (`docs/column/verification/issue-104-batch-grouping.md`), not from
> assumption. Tracked by **#104**.

**Batch placement is not a new element and not a new tool.** It is the
existing Column tool run over more than one host in one go. The cage, the
rules, the refusals and the report are unchanged; what this addendum
defines is **which columns may share a run**, and **what happens when they
cannot**.

Amendments are recorded in
[`docs/column/spec-amendments.md`](../docs/column/spec-amendments.md).

---

## 0. Why the obvious rule is wrong

"Place in every column of the same type" is the natural way to ask for
this, and taken literally it produces wrong reinforcement.

Measured on `ColumnRFT.Trail`, five `450 x 600mm` columns share family,
type, `b`, `h`, cover, rotation and orientation — and **two of them sit on
the same two levels with different clear heights**:

| id | levels | clear height | top cover set |
|---|---|---|---|
| 421967 | Level 1 → Level 2 | 2700 | no |
| 422316 | Level 1 → Level 2 | 2700 | no |
| 423606 | Level 1 → Level 2 | **3000** | **yes** |
| 422078 | Level 2 → Level 3 | 2700 | no |
| 422840 | Level 2 → Level 3 | **3000** | **yes** |

Storeys are 3000 throughout: the 2700s are cut by a beam above, the 3000s
run the full storey. Clear height drives both confinement zones and the
equally-divided middle run, so a batch keyed on the type would give a
3000 mm column a 2700 mm column's ladder — **a cage short by a tie, which
looks correct in the browser.**

## 1. What is shared across a batch, and what is not

This split is the whole reason batching is safe at all.

**Shared — the engineer's inputs.** Bar count and diameter, tie diameter
and bar type, the tie topology (§6.2's subsets, including triangles), both
hook choices (§7), Mode A/B and any manual spacings, the splice mode. These
are a *design decision about a column type*, and they are stated once.

**Per column — everything derived from the host.** The extent, the clear
height, `L0`, the tie ladder and its level count, the splice geometry, the
cover read back from the element, and every §6.1 finding.

A batch therefore states one design and produces as many cages as the model
requires.

## 2. Selection — the type is the filter, the extent is the key

The engineer selects **one column** exactly as today, fills in the tabs
exactly as today, and then asks for the batch. The tool collects every
other column **of the same family type** as the candidate set.

The type is the right thing for a *person* to select with — "every
450 × 600" is how the decision is actually made. It is the wrong thing to
*group* by, per §0.

## 3. The grouping key

Columns are grouped by **what `read_column` computes**, never by the
parameters it computes from:

- the **clear height**, and
- whether a **top support was found**.

Both come from the same read the single-column path already performs. **No
new geometry, no new parameter, and no second derivation** — the values are
the ones the report already prints, which is what keeps a batch and a
single run from disagreeing.

**A group of one is not an error.** In the model above, 423606 is simply
its own group.

> **Settled by measurement, and it stays out.** Rotation is not part of
> the key, and that is now a measured fact rather than an untested
> omission. The owner rotated two columns of the `300 x 600mm` group to
> **45°** and **315°**; every vertical face normal on both still comes
> back as **exactly ±`HandOrientation` or ±`FacingOrientation`** — dot
> products of `1.000000` and `0.000000` at full precision, with the wide
> faces mapping to ±Hand in every case, identical to the unrotated
> columns. The column's own frame rotates with it, so the cage does too.
> Recorded in `docs/column/verification/issue-104-batch-grouping.md`.

## 4. When a type splits — R33

**Place every group correctly, and report the split.** Decided by the
owner.

- The run proceeds. Each group gets the ladder its own extent requires.
- **The report names the groups**, their clear heights, and which columns
  fell in each. A reviewer must be able to see that one selection produced
  two cages **by reading the report**, not by noticing a tie count in a 3D
  view.
- Refusing here was considered and rejected: a floor with a beam over some
  columns and not others is normal, so refusing would make the common case
  the hard one.

## 5. Refusals, and the transaction

**A column the single-column path would refuse is refused here too**, by
the same `refuse_if_not_ready` gate, and for the same reasons — §6.1
blocking findings, an unbuildable tie, an out-of-scope host.

- Refused columns are **excluded before any transaction opens**, and every
  one is **named in the report with its reason**. A batch never details a
  column the tool would have refused on its own.
- If *every* candidate is refused, the run refuses as a whole rather than
  opening an empty transaction.

**One transaction for the whole batch (R25, extended).** R25 made a single
column's cage all-or-nothing so that a failure leaves the model exactly as
it was. The same reasoning applies with more force here: a batch that
half-succeeds leaves the engineer to work out which columns got steel.

> **Open:** whether one transaction remains the right shape at a hundred
> columns is untested. Ten columns says nothing about a hundred, and #104's
> own text raises it.

## 6. Ownership and replacement

Unchanged in substance, and it is the part that scales worst.

- Every bar carries the `RFT-COL-` prefix and its host's `Partition` tag
  (R24, R26), so a batch's output is attributable per column.
- **R23 — show the count, then replace — applies per column.** Reporting
  "17 existing bars will be replaced" for one column is a sentence; for
  forty it is a table, and the confirmation must stay readable or it stops
  being a confirmation.
- **R24 is absolute here too: foreign rebar is never deleted**, only
  reported, for every column in the batch.

## 7. Out of scope

- **Roof-level columns.** `specs/column-roof-termination.md` §6 already
  excludes them, and for a reason that still holds: its pick-the-exception
  input needs a human decision per column.
- **Multi-storey stacks.** §0/C2 of the main spec is unchanged — a batch
  details many columns, never one column through many storeys.
- **Mixing types in one run.** One selected type per run. Two types are two
  runs, which costs nothing and keeps the shared-inputs rule in §1 true.

## 8. Citations

**None are needed and none are claimed.** Nothing here is a detailing rule:
every rule a batch applies is the main spec's, applied more than once. This
addendum defines *which hosts share a run*, which is a tool behaviour, and
its one judgement call (§4) is recorded as an owner ruling in the ledger.
