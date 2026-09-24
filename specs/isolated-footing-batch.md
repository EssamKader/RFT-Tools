# Isolated Footing RFT — Batch Placement Addendum

> **Status: rules resolved (R8/R9), tracer bullet pending, not yet
> implemented at the time this spec was written.**
> Mechanism Ref (Essam, 2026-09-24): reuse `specs/column-batch-
> placement.md`'s own mechanism as-is, translated to footing+column
> pairs — not a new batch design. Tracked by **#226**.

**Batch placement is not a new element and not a new tool.** It is the
existing Isolated Footing tool (spec Ref: `specs/isolated-footing.md`,
`specs/isolated-footing-dowel-array.md`) run over more than one
footing+column pair in one go. The plan, the refusals and the report are
unchanged; what this addendum defines is **which footings may share a
run**, and **what happens when they cannot**.

Amendments are recorded in
[`docs/footing/spec-amendments.md`](../docs/footing/spec-amendments.md)
(R8, R9).

---

## 0. Why the obvious rule is wrong

"Place in every footing of the same type" is the natural way to ask for
this, and per `specs/column-batch-placement.md` §0's own measured lesson
(five `450x600mm` columns, identical family+type, two of them needing a
different tie ladder because of a per-instance clear-height difference),
taken literally it risks the same failure mode here: two footings of the
identical family type could still carry a different column above them, a
different cover setting, or (before #228) even a different typed
dimension an engineer mistyped between runs.

R8 (`docs/footing/spec-amendments.md`) already closed the specific gap
this tool had that the column tool did not: before #228, footing
dimensions were manually typed per run, so there was no per-instance
MEASURED fact to group by at all — only an assumption that "same type"
meant "same geometry." #228 made the footing's own plan dimensions,
thickness and covers a live read, closing that gap.

## 1. What is shared across a batch, and what is not

This split is the whole reason batching is safe at all — unchanged in
shape from `specs/column-batch-placement.md` §1, translated to what this
tool's own inputs are (spec Ref: `specs/isolated-footing-dowel-array.md`
§3, `IsolatedFootingRFT.pushbutton/script.py`'s current prompts).

**Shared — the engineer's inputs.** The column-face clear offsets
(`x_offset_mm`/`y_offset_mm`), the mesh LD multiplier, the mesh bar
types (X/Y), the dowel bar type and its own LD multiplier, the dowel tie
bar type (array spacing only — the tie ladder itself is a separate,
not-yet-built ticket), and the dowel array's count-per-face
(`dowel_count_b_face`/`dowel_count_h_face`). These are a *design decision
about a footing+column TYPE PAIR*, and they are stated once.

**Per footing — everything derived from the host.** The auto-detected
column (#220), that column's own live-read `Cw`/`Cd`/`Ccover` (#221),
the footing's own live-read plan dimensions/thickness/covers (#228), the
resulting `FootingPlan` (mesh geometry, dowel array positions) `build_
footing_plan` computes from those, and the cover/reinforcement each
footing's own detailing actually needs.

A batch therefore states one design and produces as many footing plans as
the model requires.

## 2. Selection — the type PAIR is the filter, the live-read tuple is the key

The engineer selects **one footing** exactly as today (`revit.pick_
element`), the column auto-detects per #220, every shared input above is
filled in exactly as today, and then the batch is requested. The tool
collects every OTHER `OST_StructuralFoundation` instance of the SAME
family type as the picked footing.

For each candidate of that footing type, its own column is auto-detected
(#220) too — a candidate whose own detected column is a DIFFERENT family
type than the picked footing's own detected column is excluded, with that
reason named in the report (§5 below); this is genuinely new logic this
ticket adds, since #220's own single-run refusal has no concept of
"wrong column type," only "no column at all."

The footing+column TYPE PAIR is the right thing for a *person* to select
with — "every 1800x1200x450 footing with a 300x600 column on it" is how
the decision is actually made. It is the wrong thing to *group* by, per
§0 and R8/R9 — see §3.

## 3. The grouping key — R9

Footings are grouped by **the full live-read tuple** `read_footing_
geometry_mm` (#228) and `read_dowel_column_section_mm` (#221) already
compute for the single-run path, never by the type-pair match alone
(R9, `docs/footing/spec-amendments.md`):

- `a_mm`, `b_mm`, `footing_thickness_mm`, `cover_mm`, `bottom_cover_mm`,
  `top_cover_mm` (the footing's own geometry, #228), and
- `Cw_mm`, `Cd_mm`, `Ccover_mm` (the column's own section/cover, #221).

**No new geometry, no new parameter, and no second derivation** — every
one of these nine values is the one the single-footing path's own live
reads already produce; the batch grouping key only READS them, exactly
`column_batch.group_key` only reads `ColumnExtent`'s own fields rather
than recomputing them.

**A group of one is not an error**, same as `specs/column-batch-
placement.md` §3.

## 4. When a type pair splits into groups

**Place every group correctly, and report the split** — same ruling as
`specs/column-batch-placement.md` §4 / R33, applied here rather than
re-litigated: a floor where some footings of the matching type sit under
a slightly different cover setting, or a matching-type column with a
different live-read section for some other reason, is a normal modelling
situation, not an error condition.

- The run proceeds. Each group gets the `FootingPlan` its own live-read
  tuple requires.
- The report names the groups, their key values, and which footings fell
  in each.
- Refusing here was considered and rejected for the same reason column
  batch §4 rejects it.

## 5. Refusals, and the transaction

**A footing the single-run path would refuse is refused here too**, and
for the same reasons:

- #220's `FootingHostError` ("No column is attached to this footing."),
- #221's `ColumnHostError` propagated unchanged (non-rectangular section,
  flipped column, cover unset),
- #228's `FootingHostError` (a missing/unset geometry or cover
  parameter),
- §2's own new "column type pair mismatch" exclusion,
- and `build_footing_plan`'s own `ValueError`/`DowelArrayLayoutError`
  (e.g. a dowel array that does not fit the column's own section/cover).

Refused footings are **excluded before any transaction opens**, and every
one is **named in the report with its reason**. If *every* candidate is
refused, the run refuses as a whole rather than opening an empty
transaction (mirrors `specs/column-batch-placement.md` §5 exactly).

**One transaction for the whole batch, all-or-nothing** — this repo's own
transaction hard rule, extended from one footing to the batch, the same
way R25 extended it for the column tool.

> **Open, flagged not resolved, same as column batch's own §5:** whether
> one transaction remains the right shape at a hundred-plus footings is
> untested here too.

## 6. Ownership and replacement

Translated from `specs/column-batch-placement.md` §6, using a
footing-specific prefix — `column_ownership.py`'s own `RFT-COL-` prefix
is hardcoded to that module, not a parameter, so a new `footing_
ownership.py` (same pattern, not a literal reuse — mirrors `column_
ownership.py`'s `Partition`-parameter tagging and prefix-based ownership
test exactly) carries the footing tool's own:

- Every bar (mesh AND every dowel in the array, #222/#223) carries the
  `RFT-FTG-` prefix and its host footing's own `Partition` tag, so a
  batch's output is attributable per footing.
- **Show the count, then replace — applies per footing.** Reporting "12
  existing bars will be replaced" for one footing is a sentence; for
  many it is a table, same reasoning as column batch §6.
- **Foreign rebar is never deleted**, only reported, for every footing in
  the batch.

## 7. Out of scope

- **Rotated footings.** Already refused by `FootingRotationUnsupported
  Error` (`footing_mesh._footing_origin`, per `IsolatedFooting.
  extension/CONTEXT.md`'s "Open gap: rotated footings" section) — the
  single-footing refusal already covers this via §5, nothing new to add.
- **Mixing footing+column type pairs in one run.** One selected type pair
  per run, exactly like column batch's "two types are two runs."
- **`dowel_tie`'s own closed-loop shape/placement, and `perimeter_tie`
  placement.** Neither is built for the single-footing path yet
  (`docs/footing/HANDOVER-2026-09-24.md` item 6, and spec Sec 3 Story
  7's own placement gap) — a batch cannot place what the single-run path
  does not place either.

## 8. Citations

**None are needed and none are claimed**, for the same reason `specs/
column-batch-placement.md` §8 states: nothing here is a detailing rule.
Every rule a batch applies is `specs/isolated-footing.md`'s /
`specs/isolated-footing-dowel-array.md`'s, applied more than once. This
addendum defines *which hosts share a run*, a tool behaviour, and its
grouping-key judgement call is recorded in the ledger as R9.
