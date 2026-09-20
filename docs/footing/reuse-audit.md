# Reuse Audit — Isolated Footing

Per `docs/token-efficient-expansion.md` §1 and `REUSE_GUIDELINES.md` §2:
reuse is earned, not assumed, and every verdict below was checked against
the **resolved** import graph (`import` the module for real and read
`sys.modules`, not just that module's own `import` lines) — the #99
lesson. Format follows `docs/column/reuse-audit.md`.

This is the footing tool's own reuse ledger. Ticket #204 (the
perimeter-tie ticket) extends this same file rather than starting a new
one — add rows to the tables below, don't duplicate them.

Verdicts: ✅ reuse as-is · ⚠️ reuse after a split/adaptation · ❌ do not reuse.

---

## 1. `dowel_tie` (Story 6, spec §9) — reuse target named by spec §1/§2

| Module / member | Status | Reason |
|---|---|---|
| `rft.core.column_ties.resolve_tie` / `TieSubset` / closed-loop geometry | ⚠️ Reusable, not yet exercised | The closed-loop rectangle construction (`resolve_tie` on a `TieSubset` naming ≥2 bar positions) is exactly the shape a `dowel_tie` needs once a real dowel-bar array exists in plan. **Not called by this ticket** — see "Blocked, not guessed" below. |
| `rft.core.column_tie_levels.tie_levels` | ✅ Reused, exercised | Drives the NEW footing-specific math this ticket adds: the starter/end vertical offset ladder (`rft.core.footing_dowel_ties.dowel_tie_ladder`, spec §9). The footing has no confinement-zone concept of its own, so `l0_mm` is set to the FIXED 50mm offset (not the user's tie spacing — **found and fixed in review**: setting `l0_mm = tie_spacing_mm` made `tie_levels`' own precondition spuriously refuse ordinary, physically valid spacing/thickness combinations), degenerating the reused zone model to just the two anchor ties plus an equally-divided middle run — see that module's docstring for the full reasoning. `tie_levels`' own `first_tie_offset_mm` is already applied symmetrically at both ends of `clear_height_mm`, which matches spec §9's own shape exactly (a fixed 50mm offset from the bottom, the SAME 50mm value below T.O.F.) — a guard in `dowel_tie_ladder` refuses rather than silently mis-placing the end tie if that symmetry is ever broken by a future spec amendment. |
| `rft.core.column_tie_levels.mirror_map` | ❌ Not applicable | Spec §9 states nothing about a hook-corner alternation for `dowel_tie` (unlike spec's column §6.3). Not called; if a later ticket needs it, add it there rather than wiring it in speculatively here. |
| `rft.revit.column_place_ties.place_ties` (and its helpers) | ⚠️ Reusable, not yet exercised | Same blocker as `resolve_tie` above — it places `plan.ties` against `plan.layout.bars`, and no footing dowel-bar-position layout object exists yet. |

### Blocked, not guessed: `dowel_tie`'s plan-geometry and placement are deferred

Two prerequisites `resolve_tie`/`place_ties` need do not exist in this
repo yet, and REUSE_GUIDELINES.md §3 ("Explicit Refusals") forbids
inventing them here:

1. **A dowel-bar array.** `rft.core.footing_dowels`/`rft.revit.footing_dowels`
   (#202) place exactly ONE representative dowel bar, centred on the
   footing's own plan centroid (the same tracer-bullet convention #198 set
   for the mesh bars) — `IsolatedFooting.extension/CONTEXT.md`'s own "Not
   yet in" list names "Dowel array/quantity" as a separate, not-yet-built
   scope item. `column_ties.resolve_tie` raises `ValueError` for a subset
   naming fewer than 2 bars, so there is nothing for a `dowel_tie` to
   physically wrap yet.
2. **The tie rectangle's own plan dimensions.** A closed loop around the
   dowel bars needs the column's own cross-section width/depth (or an
   equivalent bar-position spread) — `specs/isolated-footing.md` §2/§3's
   naming table gives `Cw` (column width in the a-direction) but never a
   b-direction column dimension, and `RFT.lib/rft/core/footing_plan.
   FootingInputs` carries no column cross-section field today.

Building `dowel_tie`'s rectangle/placement now would mean guessing both a
bar layout and a column dimension the spec doesn't supply — exactly what
REUSE_GUIDELINES.md §3 exists to stop. This ticket delivers the vertical
starter/end-offset ladder only (the genuinely new, fully-specified math);
wiring the actual closed-loop shape and `column_place_ties`-style
placement is left for the ticket that adds the dowel-bar array, which can
then call `resolve_tie`/`place_ties` directly per the ⚠️ rows above.

---

## 2. Resolved import graph — verified empirically (#99 discipline)

Checked by actually importing each module in a fresh interpreter (not by
reading its own `import` statements) and inspecting `sys.modules`:

```
>>> import rft.core.column_ties, rft.core.column_tie_levels
sys.modules gained: rft.core.column_layout, rft.core.column_ties,
                    rft.core.column_tie_levels, rft.core.layout
```

```
>>> import rft.revit.column_place_ties   # with tests/fake_revit_api.py installed
sys.modules gained: rft.core.column_layout, rft.core.column_ties,
                    rft.core.layout, rft.revit.column_place_ties,
                    rft.revit.units
```

| Finding | Verdict | Reason |
|---|---|---|
| `rft.core.anchorage` reachable? | ❌ No | Confirmed absent from `sys.modules` after both imports above — this ticket's reuse target does not carry the anchorage coupling #99 found in `column_inputs`/`grades`/`guards`. |
| `rft.core.guards` reachable? | ❌ No | Same check, same result. |
| `rft.core.layout` (the BEAM's own module, home of `FacePlan`/`LayerPlan`) reachable? | ⚠️ Yes, two hops away — but only two generic functions | `column_ties` imports `column_layout`, which imports `layout.corner_bar_side_offset_mm` / `layout.corner_bar_u_positions_mm` only. `rft.core.layout` itself has **zero** imports of its own (a leaf module) and neither `FacePlan` nor `LayerPlan` is on the import path — those are separate names defined in the same file but never referenced by `column_layout`. This is the exact two-hop shape #99 warns about, so it is recorded here rather than assumed safe: importing `column_ties` for a footing DOES put `rft.core.layout` in `sys.modules`, but it never executes the beam's face-plan code, and `specs/isolated-footing.md` §1's non-reuse line ("the beam's FacePlan/LayerPlan model in `rft.core.layout`") is about those two functions specifically, not the module as a whole. |
| `rft.revit.column_place_ties` importable under `tests/fake_revit_api.py`'s stand-ins? | ✅ Yes | No new fake types were needed — the existing harness the footing revit tests already use (`test_footing_revit_dowels.py`, `test_footing_revit_mesh.py`) covers it. |

---

## 3. Not reused, by construction — restated from spec §1 (not re-derived)

| Module | Status | Reason |
|---|---|---|
| `rft.core.anchorage` | ❌ NOT reused | Footing bar ends are governed by the hook/development-length rule in spec §5, not a supported/unsupported end condition (spec §1). Confirmed absent from the resolved import graph above. |
| `rft.core.layout`'s `FacePlan`/`LayerPlan` | ❌ NOT reused | A footing mesh is not a beam face (spec §1). Not on the `dowel_tie` reuse path either — see the two-hop finding above, which reaches only `corner_bar_side_offset_mm`/`corner_bar_u_positions_mm`, never `FacePlan`/`LayerPlan`. |

---

## 4. `perimeter_tie` (Story 7, spec §10) — reserved for #204

Spec §1 states `perimeter_tie` reuses the same closed-loop geometry
primitive as `dowel_tie`, not a new shape module. Not audited here — #204
extends this file's §1 table when it starts, rather than re-deriving the
`column_ties` verdicts from scratch.
