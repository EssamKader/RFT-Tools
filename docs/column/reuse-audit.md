# Column RFT — `RFT.lib` reuse audit (issue #72)

Per `REUSE_GUIDELINES.md` §2 and `ColumnRFT/CONTEXT.docx`: reuse is
**earned, not assumed**, and each verdict's one-line reason becomes the
docstring note in the module that consumes it. Judged by whether the public
signature (and the module's imports) carry anything beam-shaped.

Verdicts: ✅ reuse as-is · ⚠️ reuse after a split/rename · ❌ do not reuse.

---

## 0. The contradiction this ticket was opened to settle

`docs/reuse-for-new-elements.md` §3 listed `core/layout.py` under *"Reusable
as-is — no beam knowledge at all"*, naming three functions and calling the
arithmetic *"identical for a column"*. `ColumnRFT/CONTEXT.docx` says do
**not** reuse `layout`'s `FacePlan`/`LayerPlan` functions and re-derive from
the perimeter model instead.

**Both are partly right, and the reuse doc overclaimed on one of its three
named functions.** Function by function:

| function | verdict | reason |
|---|---|---|
| `first_layer_offset_mm(cover, stirrup_dia, bar_dia)` | ✅ | `cover + tie_dia + ½·bar_dia` measured from a face to a bar centreline. A column asks this identically, and §2's perimeter model does not change it. |
| `corner_bar_side_offset_mm(...)` | ✅ | Same formula, reached from a side face. Same for a column. |
| `corner_bar_u_positions_mm(b, cover, stirrup_dia, bar_dia, bar_count)` | ✅ | "A bar at each corner, the rest at equal spacing between them" — that is exactly one column face. **See the corner-sharing caveat below.** |
| `layer_offset_mm(cover, stirrup_dia, bar_dia, spacer_dia, layer_n)` | ❌ | **The reuse doc was wrong here.** It takes `spacer_dia_mm` and `layer_n` — beam layers stacked vertically behind one face, separated by a spacer bar. The column perimeter model (§2) has no stacked layers and no spacer bars. |
| `main_layer_v_positions_mm(h, offsets, is_top)` | ❌ | `is_top` **is** the beam's independent-face model, in a parameter. This is the function `CONTEXT.docx` is protecting against. |
| `spacer_length_mm`, `spacer_diameter_warning` | ❌ | Spacer bars are a beam-§4.1 construct. |

**Correction to apply:** `docs/reuse-for-new-elements.md` §3 must move
`layer_offset_mm` out of "reusable as-is". Left uncorrected, the next
element's author inherits a claim this audit has falsified.

### Corner-sharing caveat on `corner_bar_u_positions_mm`

The function places a bar at **each** end of a face. On a beam that is
correct — top and bottom faces are independent. On a column the four faces
**share their corner bars**, so calling it once per face counts every corner
bar twice. `rft.core.column_layout` must call it per face and then
**de-duplicate the four corners** when assembling the perimeter. This is a
consequence of §2's perimeter model, and is exactly the kind of thing that
would pass a unit test per-face and produce eight corner bars in Revit.

Also note it raises `ValueError` for `bar_count < 2`, citing beam §6.1's
silence on a one-bar face. A column face carrying only its two shared corner
bars and no intermediate bars is a **normal** case, so the column caller
must decide what "bars on this face" means before it reaches this function.

---

## 1. `core/stirrups.py` — the strongest reuse found, with a trap

⚠️ **Split. The geometry transfers; the beam's closure vocabulary does not.**

`_rectangle_corners_mm(width_mm, height_mm, start_corner)` already does what
§6.3 needs: it returns the four centreline corners in fixed winding order,
**rotated so `start_corner` is first** — i.e. it parameterises *which corner
the hooks meet at*. That is the hook-corner rule, already written, tested,
and in the repo. Paired with `_closed_loop_endpoints_mm`, it produces the
closed 4-curve loop a column tie is.

Both are **private** (`_` prefix) and would need promotion to public API —
an `element:shared` change, not a column change.

> ### ⚠️ The trap: do NOT call this per level
>
> #70 proved the per-level hook alternation is done with
> `Rebar.MoveBarInSet(i, rotation180)` on **one** rebar set — measured at 1
> element / 111 ms against 25 elements / 828 ms for the per-level
> alternative. Generating *different curves* per level would force a
> separate `Rebar` element per level, which is precisely the option that
> lost.
>
> So `_rectangle_corners_mm` supplies the **base** corner for the single tie
> shape. The alternation on top of it is a **transform**, not another call
> to this function. An implementer who reads "it already parameterises the
> start corner" and loops it 25 times will rebuild the losing option.

| member | verdict | reason |
|---|---|---|
| `_rectangle_corners_mm`, `_closed_loop_endpoints_mm` | ⚠️ | Promote to public; the geometry is exactly a column tie's closed loop. Subject to the trap above. |
| `centreline_leg_dimensions_mm`, `outer_leg_dimensions_mm` | ✅ | `(b − 2·cover − dia) × (h − 2·cover − dia)`. Dimension-agnostic; a column tie asks the same. |
| `stirrup_curve_endpoints_mm(closure_type, ...)` | ❌ | Dispatches on the beam's **§7.2 closure vocabulary** (types 1/2/4, type 3 parked). The column spec has no closure types — it has §6.2 subsets. Reuse the two private helpers underneath it, not this dispatcher. |
| `stirrup_zones_mm`, `ZONE_LAYOUT_FLAGS`, `zone_array_length_mm` | ❌ | The beam's 3-zone (dense/normal/dense) rule. The column's §3–§5 L₀/middle-zone rule is a different geometry measured from a different datum. |
| `stirrup_count_and_spacing(array_length, max_spacing, include_first, include_last)` | ✅ | Pure "how many at what spacing fits this run" arithmetic. Serves both L₀ and the middle zone. |
| `EDGE_OFFSET_MM = 50.0` | ❌ **deliberately** | See below. |

### `EDGE_OFFSET_MM` — the same number, and it must still not be shared

Beam §3.1 puts the first stirrup 50 mm from the support face. Column §4 puts
the first tie at **exactly 50 mm** from the support face. Same value, same
meaning, and it is still the wrong thing to share.

They are **two rules in two specs that happen to agree today**. Sharing the
constant means a future amendment to the beam spec silently moves every
column's first tie, with no ticket, no citation, and nothing to notice it.
The column tool defines its own constant carrying its own `# Spec Ref: §4`.

This is not a contradiction of the project's anti-duplication lesson
(`ZONE_LAYOUT_FLAGS`, the support-detection dict): those were **one** rule
copied into two places, where drift is corruption. This is two rules that
coincide numerically, where forced agreement is the corruption.

---

## 2. `core/spacing.py` — reuse the computation, not the policy

⚠️ **Split along computation vs. policy.**

| member | verdict | reason |
|---|---|---|
| `achieved_clear_spacing_mm(b, cover_side, stirrup_dia, bar_dia, bar_count)` | ✅ | Genuinely face-generic: `b` is "the width of the face being checked", and the A43-corrected clear-width form needs no beam context. **This is what §6.1's `x` (horizontal clear distance between consecutive bars) is.** |
| `governing_min_spacing_mm`, `validate_layer_spacing`, `validate_face_spacing`, `max_bars_per_layer`, `suggest_min_layer_count` | ❌ | Beam **policy**: §6.2–6.4 thresholds, the 5-layer cap, the stacked/single-row options. The column's §6.1 tiers (`x ≤ 150` alternate, `150 < x ≤ 250` tie every bar, ≤ 300 mm between branches) are different thresholds driving a different decision — which bars a tie's subset encloses, not whether a layer passes. |

So: compute `x` with the shared function, then apply the column's own tiers.

---

## 3. `core/guards.py` — a concrete import violation, not a style preference

⚠️ **Must be split before the column tool imports it at all.**

`GuardMessage`, `SEVERITY_BLOCKING`, `SEVERITY_WARNING` and `is_blocking`
are the generic refusal/warning contract, and the column tool wants exactly
them. But the module's own header does:

```python
from .anchorage import free_end_configuration_warning
from .stirrups import TYPE3_PARKED_MESSAGE
```

So `import rft.core.guards` **transitively imports `rft.core.anchorage`** —
the one module spec §10 and `CONTEXT.docx` forbid this tool from importing
*for any reason*. The prohibition is not honoured by simply never calling
into it; the import is already the dependency.

**And it is worse than one module.** `core/spacing.py` line 27 does:

```python
from .guards import GuardMessage, SEVERITY_BLOCKING
```

which makes the full chain:

```
rft.core.spacing  ->  rft.core.guards  ->  rft.core.anchorage
```

`rft.core.spacing` is the module this audit rates **most** reusable (§2 —
it supplies §6.1's `x`). As things stand, the column tool cannot import its
single best reuse candidate without dragging in the one module its spec
forbids. This is not a tidiness argument: it is the reason the split below
is **blocking** rather than nice-to-have.

**Required `element:shared` change:** move the namedtuple, the severity
constants and `is_blocking` into their own dependency-free module
(`rft.core.guard_message`), leaving the beam's S9 guard policy where it is.
The beam tool re-exports for compatibility; the column tool imports the new
module and never touches `guards`.

### RESOLVED (#99, 2026-09-18)

`rft.core.guard_message` now holds `GuardMessage`, the two severity
constants and `is_blocking`, and **imports nothing**. `guards.py`
re-exports all four unchanged, so no beam call site moved; `grades.py`
and `spacing.py` take them from the new module.

**This section under-counted the damage.** It named `spacing.py` as the
second module on the chain, and did not check `grades.py` — which had the
identical defect and was already shipping in column code, giving

```
rft.core.column_inputs -> grades -> guards -> anchorage
```

That is #99, and it went unnoticed because the guard written to catch it
read one file's import statements with the AST. A first-hop check cannot
see a three-hop chain. The replacement,
`tests/test_column_non_reuse.py`, checks the **resolved** graph in a
fresh interpreter, for every `rft.core.column_*` module found by walking
the package rather than from a list.

Measured after the fix: `anchorage` is in **no** column module's import
graph. Nothing had ever been miscalculated by the coupling — no anchorage
function was evaluated — which is the point: the rule exists to remove it
before something comes to rely on it.

---

---

## 4. `core/grades.py` — mechanism yes, the hook guard emphatically no

⚠️ **Reuse the mechanism. Do not reuse the 135° guard.**

| member | verdict | reason |
|---|---|---|
| role→grade mapping, `role_picker_label`, `bar_type_for_role`, the missing-selection messages | ✅ | The mechanism is generic and already carries five roles; a column adds its own (`ROLE_TIE`, `ROLE_INNER_TIE`, `ROLE_LONGITUDINAL`). Explicit selection over name-matching is the right policy here too. |
| `hook_style_guard_message` (`HOOK_STYLE_STIRRUP_TIE`) | ✅ | A column tie is a `StirrupTie`; #70 confirmed the style works with a 135° hook in Revit 2024. |
| `hook_angle_guard_message` / `HOOK_ANGLE_REQUIRED_DEG = 135.0` | ❌ | The beam **requires** 135° and refuses anything else. Column §7 **defaults** to 135° for both dropdowns and explicitly lets the user override to any available `RebarHookType`. Reusing this guard would refuse what the column spec permits. |
| `ROLE_*` constants, `stirrup_grade_conflict_message` | ❌ | Beam roles and the A42 grade-conflict rule; the column's grade question is open in #74. |

---

## 5. `rft.revit.*`

| module | verdict | reason |
|---|---|---|
| `units.py` | ✅ | 19 lines, internal↔mm. The single unit boundary `REUSE_GUIDELINES.md` §1 mandates. |
| `bar_types.py` | ✅ | Collects `RebarBarType`/`RebarHookType`, reads diameter, hook angle and style. #70 confirmed the shapes live. Note `list_stirrup_hook_types` filtering — a column wants the same filter for both tie dropdowns. |
| `placement.py` | ⚠️ | `bar_point_at_uv`, `bar_face_points_at_uv`, `run_in_transaction` ✅ generic. `place_anchored_bar`, `build_bottom_bar_curves`, `main_bar_end_geometry`, `bent_end_corner` ❌ — anchorage-shaped, and §10 governs column bar ends by the splice rule instead. |
| `host.py` | ⚠️ | `validate_rebar_host`, `face_normal`, `classify_face_role`, `classify_exposed_faces` ✅ any rebar host. `read_beam_face_covers_mm` is beam-**named** but axis-parameterised — rename on promotion. **#69 caveat:** the test column's `Rebar Cover - Top Face` was unset (`-1`), so the cover read must tolerate an invalid `ElementId` rather than assume three populated covers. |
| `stirrups.py` | ⚠️ | `build_stirrup_curves(origin, u_dir, v_dir, endpoints_mm, to_internal)` ✅ generic. `apply_maximum_spacing_layout` ❌ — beam zone layout, and #70's ruling means the column's layout call is followed by a per-bar transform pass this function knows nothing about. |
| `geometry.py` | ❌ | Beam axis, endpoints, `find_supporting_element`. #69 **proved** a column needs a new vertical search — and that it must treat "nothing found" as a normal outcome. |
| `guards.py` | ❌ | Continuous-run detection between beams. |

---

## 6. `rft.ui.*` — the pattern transfers, the content does not

| module | verdict |
|---|---|
| `inputs.py` (field parsers and refusal messages) | ✅ |
| `sketch_layout.py` (pixel-space label placement, zero domain knowledge) | ✅ |
| `sketch_palette.py` (style keys) | ✅ |
| `persistence.py` | ⚠️ pattern only — including the load-bearing part: **withhold the fields that would restore intent**. Slot name and field lists are per-tool. |
| `derivation.py` | ⚠️ pattern only — "state the derivation in words" transfers, its content does not. |
| `report.py`, `sketch.py` | ❌ beam sections, faces, zones and hook details throughout. |

---

## 7. Fixed non-reuse — not audited, settled by spec

- `core/anchorage.py` — spec §10, explicit. **§3's import violation is the
  live threat to this**, not a call site.
- `core/crack_bars.py` (`h > 700` deep-beam rule), `core/plan.py` (composes
  beam quantities) — single-span-beam-shaped.
- The beam's per-face model as a whole — spec §2.

An irony worth recording: the beam's stirrup **type 3** is parked precisely
because *"the inner loop's offset, diameter and hook-overlap-corner rule are
entirely undefined in the spec"* — and the column's §6.2 **defines** exactly
that for overlapping closed ties. The column spec answers the beam's parked
question. That is **not** licence to unpark type 3: it is a different spec
governing a different element, and any move in that direction is a beam
ticket with its own amendment.

---

## 8. `element:shared` changes this audit implies

Each is its own ticket. None may ride inside a column ticket.

1. **Split `GuardMessage` out of `core/guards.py`** into a dependency-free
   module, so importing the guard contract stops importing `anchorage`.
   *(Blocking — the column tool cannot honour §10 until this lands.)*
2. **Promote `_rectangle_corners_mm` / `_closed_loop_endpoints_mm`** to
   public API in `core/stirrups.py`, or move them to a shared
   `core/tie_geometry.py`.
3. **Rename `read_beam_face_covers_mm`** to an element-neutral name, and
   make it tolerate an unset cover parameter (#69).
4. **Correct `docs/reuse-for-new-elements.md` §3** — remove
   `layer_offset_mm` from "reusable as-is" (§0 above).

Every reused function must state its audit verdict in the consuming
module's docstring, the way `rft.core.plan` states its own reasoning.
