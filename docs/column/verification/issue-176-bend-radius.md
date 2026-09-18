# #176 — where R40's bend radius comes from, measured

**Status: ANSWERED, and the obvious reading was wrong.** Measured on
Revit 2024 build 24.3.40.26, document `ColumnRFT.Trail`, via the Revit
MCP connector. Every bar was built inside a `SubTransaction` that was
rolled back; the document's rebar count was 404 before and 404 after.

## Why it had to be measured

`rft.core.column_roof.fillet_loss_mm` has said since **R40** that
`bend_radius_mm` *"comes from the BAR TYPE, never from a typed input"* —
and **nothing in the repository read it**. Every test passed a number in.
The second window (#176) is the first caller that has to obtain one, and
`CONTEXT.md` forbids guessing an API name.

The risk is not abstract. The fillet loss is **subtracted** from the
achieved development length that §4 certifies, so a radius that is wrong
by a factor makes the tool **overstate what it built**.

## The candidates

`RebarBarType` exposes six members whose names mention bend, diameter or
radius:

```
Double BarNominalDiameter       Double StandardHookBendDiameter
Double BarModelDiameter         Double StandardBendDiameter
Double StirrupTieBendDiameter   Double MaximumBendRadius
```

## The measurement

A two-curve bent bar was built per type and its arc read back off
`GetCenterlineCurves`. For a 90° bend the arc is `r·π/2`, so the arc
gives the radius directly.

| type | nominal | StandardBend | StirrupTie | measured arc | implied radius | (Std+Nom)/2 | (Stirrup+Nom)/2 |
|---|---|---|---|---|---|---|---|
| 13M | 12.70 | 80.00 | 50.00 | **72.806** | **46.350** | 46.350 | 31.350 |
| 19M | 19.10 | 115.00 | 115.00 | **105.322** | **67.050** | 67.050 | 67.050 |
| 12T | 12.00 | 72.00 | 155.00 | **65.973** | **42.000** | 42.000 | 83.500 |
| 16T | 16.00 | 96.00 | 155.00 | **87.965** | **56.000** | 56.000 | 85.500 |

## The rule

```
centreline bend radius = (StandardBendDiameter + BarNominalDiameter) / 2
```

Exact on all four types. `StandardBendDiameter` is the bend diameter to
the bar's **inner face**; the centreline the API returns runs half a bar
diameter outside it.

### What this rules out

- **`StandardBendDiameter / 2`** — the reading a careful person reaches
  for first. For 13M it gives 40.00 mm against the measured 46.35: a
  **13.7% error in the fillet loss**, always in the direction of claiming
  more development than was built.
- **`StirrupTieBendDiameter`** — ruled out decisively by 12T and 16T,
  which read 155.00 for it while measuring 42.00 and 56.00. 13M alone
  could not have settled this, because its stirrup and standard values
  differ in the wrong direction to discriminate.

### What this does NOT settle

`StandardHookBendDiameter` is **equal to** `StandardBendDiameter` on all
four types measured. The code uses `StandardBendDiameter` because this is
a **bend, not a hook** — an argument from meaning, not from the data. A
bar type where the two differ would settle it; none was available here.

## Corroboration

13M's measured arc of **72.806 mm** reproduces the **72.8 mm** read in
#161, months earlier, on a different probe and for a different question.
Two independent readings agreeing is the standard that made #161's slab
read trustworthy.

## Where it lives

`rft.revit.bar_types.bar_type_centreline_bend_radius_mm`, with the four
rows above as the test fixture in `tests/test_bar_type_bend_radius.py`:
the tests assert that the formula **reproduces the measured arcs**, so a
merely plausible formula cannot pass them.
