# Issue #78 — Adjacent hook corner via a mirrored tie, verified on a live host

**Status: ANSWERED — adjacent-corner alternation is BUILDABLE**, on one rebar
set, with the 135° hook remaining geometrically correct. A separate **defect
was found in the hook orientation** used by #70's experiments.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26 |
| Document | `ColumnRFT.Trail.rvt` |
| Test column | id `421967`, `450 x 600mm` |
| Tie bar / hook | `10M` (53672) / `Stirrup/Tie - 135 deg.` (53733) |
| Writes | all inside rolled-back `SubTransaction`s — model left with **0** rebar |
| Date | 2026-09-14 |

Frame used throughout: `u` along `HandOrientation`, `v` along
`FacingOrientation`, origin at the column's `Location.Point` at each level
(#69 established these axes). Tie centreline rectangle:
`u ∈ [-185, 185]`, `v ∈ [-260, 260]` mm.

---

## 1. Does `MoveBarInSet` accept a reflection? — YES

```
reflection transform: HasReflection=True  Determinant=-1.000  IsConformal=True
MoveBarInSet(1, REFLECTION) ACCEPTED (no throw)
stored transform    : HasReflection=True  Determinant=-1.000  identity=False
>>> reflection PRESERVED? YES
```

The reflection is **stored, not normalised away**. This had to be tested
rather than inferred from #70: that result proved *rotations* survive, and a
reflection is a different class of transform (negative determinant).

## 2. Does it give an ADJACENT corner? — YES

Mirror plane normal = `HandOrientation`, through the tie centre. This flips
`u` and leaves `v` alone, which is exactly an adjacent-corner move:

| bar | hook corner | u | v |
|---|---|---|---|
| 0 (plain) | **SW** | -119.1 | -351.4 |
| 1 (mirrored) | **SE** | +119.1 | -351.4 |

`SW → SE` — adjacent, as §6.3 requires. A 180° rotation would have given
`SW → NE`, the diagonal.

## 3. Is it still ONE element? — YES

```
Rebar count in model = 1 | Quantity=6 | NumberOfBarPositions=6
hook types still set-wide: Stirrup/Tie - 135 deg. | orient0=Left orient1=Left
```

#70's entire advantage survives: one element, one schedule line. The
reflection does **not** force Revit to split the set.

---

## 4. ⚠️ DEFECT FOUND — `RebarHookOrientation.Right` bends the hook OUT of the core

Not what this ticket was opened to find, and more serious than what it was.

Both orientations were tested on the identical tie:

| `RebarHookOrientation` | hook free end | bend point | free end inside core? | tail points inward? |
|---|---|---|---|---|
| **`Right`** | `u=-119.1, v=-351.4` | `u=-173.0, v=-297.5` | **NO** | **NO** |
| **`Left`** | `u=-119.1, v=-159.1` | `u=-173.0, v=-213.0` | **YES** | **YES** |

With `Right`, the free end sits at `v = -351.4` against a tie half-height of
**260** — the 135° hook tail projects **91 mm beyond the tie, out of the
concrete**. That is not a detailing preference; it is a hook anchored into
cover and air instead of into the confined core.

> **Rule: column ties use `RebarHookOrientation.Left`.** `Right` produces a
> hook that bends outward and must never be used for a tie on this geometry.
>
> This also corrects the record: **#70's experiments all used `Right`**, so
> the geometry in `issue-70-hook-corner-alternation.md` shows an outward hook.
> #70's *conclusions* are unaffected — they concern rotation storage, element
> counts and timings, none of which depend on hook orientation — but its
> coordinates should not be copied as a model of correct detailing.

**Caveat, stated rather than generalised:** `Left`/`Right` are defined
relative to the curve direction and the loop's winding order. This tie was
built counter-clockwise starting at the SW corner. A different winding would
likely invert which enum value points inward, so the tool must not hardcode
`Left` blindly — it must derive it from, or assert it against, the winding it
actually generates. **`SHAPE UNVERIFIED` for any other winding.**

## 5. Does mirroring flip the hook's inward/outward sense? — NO

The chirality worry proved unfounded. With `Left`, the mirrored bar keeps its
tail inside the core:

| bar | free end | inside core | tail inward |
|---|---|---|---|
| 0 (plain) | `u=-119.1, v=-159.1` | YES | YES |
| 1 (mirrored) | `u=+119.1, v=-159.1` | **YES** | **YES** |

The mirror maps the whole tie — hook included — onto a valid
mirror-image detail. `GetHookOrientation` still reports `Left` for both ends,
because hook orientation is a **set-wide** property and the mirror acts on
placement, not on the hook definition.

## 6. The #70 corruption applies to reflections too — and the mitigation works

Per-bar transforms are keyed on **bar position index** and are not re-mapped
when the layout changes. Reflections behave exactly as rotations did:

```
after mirroring odd bars : .M.M.M      ( . = plain, M = mirrored )
after SPACING 150->200   : .MM.M.      CORRUPTED
after COUNT 6->9         : .MM.M....   persists, new bars unmirrored
after RESET + RE-APPLY   : .M.M.M.M.   mitigation WORKS
```

The prescribed mitigation is now **proven**, not merely prescribed:
`ResetMovedBarTransform` across every position, then re-apply the whole
level-indexed map from scratch. Partial repair is not enough — the corruption
moves transforms onto wrong indices, so the map must be rebuilt, not patched.

---

## 7. Ruling

> §6.3's adjacent-corner requirement is **satisfiable as specified**. No spec
> amendment is needed. R8 stands.
>
> Implementation contract:
> - one shape-driven `Rebar` set per tie definition;
> - `RebarHookOrientation.Left` (derived from the winding, not hardcoded);
> - `MoveBarInSet(i, Transform.CreateReflection(plane))` on alternate levels,
>   the plane's normal being `HandOrientation` through the tie centre;
> - the full rotation map applied **after** the final layout, and **reset and
>   re-applied** after any layout change.

## 8. Still unverified

- Only the **`hand`-normal** mirror plane was tested (SW→SE). Mirroring about
  the `face` normal (SW→NW) is the other adjacent move and was not tested.
- Only the **outer perimeter** tie. An inner subset tie (§6.2) was never
  created; its behaviour under reflection is assumed, not observed.
- Survival across **save/reopen** untested — only in-session edits.
- Interaction with `SetBarIncluded` / suppressed first-or-last bars untested;
  both change what a bar position index means.
- Whether alternating levels should mirror about `hand` or alternate between
  both planes across four levels is a **detailing** question the spec does not
  answer; §6.3 requires only "a different corner" each level.
