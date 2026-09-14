# Issue #80 — What actually decides where a placed bar ends up

**Status: ANSWERED.** The original framing ("placing rebar moves rebar already
placed, fix the order") was **wrong**. Order is irrelevant. Three separate
mechanisms are at work, two of them silent, and one of them is Revit being
*more* correct than the arithmetic was.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26 |
| Document | `ColumnRFT.Trail.rvt`, column `421967` (450 × 600) |
| Host cover | `Interior (framing, columns)` = **40 mm** |
| Tie / main bar | `10M` (Ø9.5, `StirrupTieBendDiameter` **40 mm**) / `16M` (Ø15.9) |
| Writes | all inside rolled-back `SubTransaction`s — model left with **0** rebar |
| Date | 2026-09-15 |

---

## 1. Order does not matter — the snap happens at creation

| | bar placed first, tie second | tie placed first, bar second |
|---|---|---|
| tie | — | **did not move** |
| bar | moved to `u=-164.02, v=239.02` | created **already at** `u=-164.02, v=239.02` |

Both orders produce the identical result. The bar never sits where it was
asked to, and reversing the order does not rescue it. **The ordering
hypothesis this ticket was opened on is disproved.**

Constraint profiles explain why:

```
TIE : RebarPlane -> FixedDistanceToHostFace
      Edge x4    -> ToCover                  <<< binds to the HOST's cover
      ends       -> ToCover
BAR : RebarPlane -> ToOtherRebar             <<< binds to the TIE's bend
      Edge       -> ToOtherRebar
      ends       -> FixedDistanceToHostFace  (0.00 and 636.00 = Ls, correct)
```

## 2. Only CORNER bars move — and Revit is right to move them

Same tie, three bars, asked for exact coordinates:

| bar | no tie present | tie present |
|---|---|---|
| **corner** (`-167.55, 242.55`) | exact ✓ | **`-164.02, 239.02`** |
| **mid-face** (`0, 242.55`) | exact ✓ | **exact ✓** |
| **centre** (`0, 0`) | exact ✓ | **exact ✓** |

With no tie in the host, *every* bar lands exactly where asked — so
`CreateFromCurves` is faithful and the API is not the problem.

The tie's `StirrupTieBendDiameter` is **40 mm**, so its corners are 20 mm
radius arcs, not sharp corners. **A corner bar cannot physically occupy the
intersection of two straight legs** — that point is inside the bend. Revit
nestles the bar against the actual arc.

> The computed position `-167.55` was an **idealisation** derived from the
> straight legs. `-164.02` is where a real bar sits inside a real bend. Revit
> is not corrupting the placement; it is correcting arithmetic that ignored
> the bend radius.

### The compounding consequence

A shape-driven set is defined by its **first bar plus a spacing**. When the
first bar of a face set is a corner bar and it snaps, **the whole array
translates with it**. In the hand-built cage this turned a 3.5 mm corner
correction into every bar on that face being 18.5 mm out — including
mid-face bars that would have been exact on their own.

> **Never start a bar set on a corner bar.** Either place corner bars as their
> own single-bar sets, or start the array from a mid-face bar.

## 3. ⚠️ Ties are silently CLAMPED to the host's cover

The most consequential finding, and it hits spec §1 directly.

| tie built for | asked half-u | **landed half-u** |
|---|---|---|
| cover 25 | 195.25 | **180.25** ← overridden |
| cover 40 | 180.25 | 180.25 ✓ |
| cover 60 | 160.25 | 160.25 ✓ |

The `Edge -> ToCover` constraints mean a tie **cannot be placed with less
cover than the host's own cover parameter**. More cover is honoured; less is
silently pulled back. No warning, no exception, no failed call.

### Why this matters to §1

Spec §1 requires cover to be *"an editable input, not a hardcoded
constant"*, defaulting to 25 mm. On this column, **a user entering 25 gets
40 in the model** — while the Review report, computing from the input, would
state 25. That is precisely the divergence between report and model that §8's
single-source-of-truth rule exists to prevent, and it would appear on a
drawing.

Three possible responses, none yet chosen (owner's call):

1. **Read the host's cover and use it**, treating the parameter as the truth
   and showing it read-only. Honest, but the §1 input stops being editable.
2. **Write the user's cover to the host's cover parameter** before placing.
   Makes the input real, but the tool then edits the host element, which is a
   larger claim on the model than detailing.
3. **Refuse/warn when the user's cover is below the host's**, naming both
   numbers. Cheapest, and consistent with §8's "warn but place" precedent.

## 4. What cannot be steered

- `SetDistanceToTargetRebar` **throws** on these constraints:
  `InvalidOperationException: The RebarTargetConstraintType is 'HookBend' or
  'BarBend'.` The corner bar is bound to the tie's *bend*, and that distance
  is not settable.
- `RemovePreferredConstraintFromHandle` on every handle **does not** restore
  the asked-for position — it clears a *preferred* constraint, not the current
  automatic one.

So the corner-bar position is **not** something the placer can dictate. It must
be **read back** after placement and reported as-built.

## 5. Consequences for the tool

1. **Compute from the host's real cover**, not from an unchecked input (§1
   needs the owner's ruling above).
2. **Never begin a bar set on a corner bar** — one snap displaces the whole
   array.
3. **Read positions back after placement** and report those. The Review report
   must state as-built coordinates, not idealised ones, or report and model
   disagree by design.
4. **§6.1's tier check is affected.** The clear distance `x` between bars is
   computed from bar positions; if corner bars actually sit ~3.5 mm inboard,
   the real `x` differs from the computed one, and `x` decides which tier
   applies and therefore which bars need restraint. Validation on idealised
   positions can disagree with the model.
5. A guard is needed over point 2, mutation-provable: start a set on a corner
   bar and the guard must fail.

## 6. Still unverified

- Only **one** tie was present. Whether a bar between two ties (outer + inner,
  §6.2) binds to the nearer, both, or neither is untested.
- Tie-to-tie interaction: three overlapping tie definitions have never been
  present simultaneously.
- Whether the corner snap is stable across **save/reopen**, or re-evaluates.
- The exact arithmetic of `-164.02` was not derived. The *mechanism* (binding
  to the bend) is confirmed; the closed form is not, so the tool must read the
  value back rather than predict it.
- Non-rectangular tie shapes, and cross-ties (A1), untested.
