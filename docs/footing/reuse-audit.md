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
| `rft.core.column_tie_levels.tie_levels` | ✅ Reused, exercised | Drives the NEW footing-specific math this ticket adds: the starter/end vertical offset ladder (`rft.core.footing_dowel_ties.dowel_tie_ladder`, spec §9). The footing has no confinement-zone concept of its own, so `l0_mm` is set equal to the user's own tie spacing, degenerating the reused zone model to one continuous run — see that module's docstring for why this is a faithful adaptation, not a new zone model. `tie_levels`' own `first_tie_offset_mm` is already applied symmetrically at both ends of `clear_height_mm`, which matches spec §9's own shape exactly (a fixed 50mm offset from the bottom, the SAME 50mm value below T.O.F.) — a guard in `dowel_tie_ladder` refuses rather than silently mis-placing the end tie if that symmetry is ever broken by a future spec amendment. |
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

## 4. `perimeter_tie` (Story 7, spec §10) — audited by #204

Spec §1 states `perimeter_tie` reuses the same closed-loop geometry
primitive as `dowel_tie` "conceptually" (a plain closed rectangle) — this
audit finds that reuse is about the SHAPE, not about calling
`column_ties.resolve_tie`'s own code path, and that unlike `dowel_tie`
this ticket is **not** blocked the same way #203 was.

| Module / member | Status | Reason |
|---|---|---|
| `rft.core.column_ties.resolve_tie` / `TieSubset` | ❌ Not reused (different situation from `dowel_tie`) | `resolve_tie` takes a `ColumnLayout`/`layout.bars` — named bar positions — and grows a bounding box around ≥2 of them. `perimeter_tie` wraps the footing's OWN plan perimeter (offset inward by `cover` from `a`/`b`), not a bar array — there are no bar positions to name. Calling `resolve_tie` here would mean inventing two fake bar positions purely to hand it a box it would then re-derive, which is less direct (and less honest) than building the same four-corner rectangle straight from `inner_a`/`inner_b` — see `rft.core.footing_perimeter_tie.local_perimeter_tie_corners_mm`, new footing-specific geometry math, hand-tested in `tests/test_footing_perimeter_tie.py` per this ticket's own "Test volume rule" (not duplicating `tests/test_column_ties.py`, since this is not that function). |
| `rft.core.column_tie_levels` (vertical ladder, as `dowel_tie` reuses it) | ❌ Not reused — genuinely different ladder, not a gap any more (R4) | Spec §10 gave no starting-offset/array-position formula for `perimeter_tie`'s vertical ladder analogous to §9's "50mm from the bottom" / "50mm below T.O.F." for `dowel_tie`. **R4** (`docs/footing/spec-amendments.md`) resolved this: the first loop sits 250mm above the bottom mesh's own top face, then every subsequent loop (up to `quantity`) steps upward at the user's own `spacing_mm` — a single fixed start plus one constant step, unlike `dowel_tie`'s two-anchor-plus-equal-division shape, so `column_tie_levels.tie_levels` genuinely does not apply here (there is no second anchor to divide a middle zone between). `rft.core.footing_perimeter_tie.perimeter_tie_ladder_mm` implements this directly. See `IsolatedFooting.extension/CONTEXT.md`'s "Scope, as of #204" note. |
| `rft.revit.column_place_ties.place_ties` | ❌ Not reused (this ticket) | Same reason as `resolve_tie` above (no `ColumnLayout` to place against), compounded by the missing vertical-ladder formula immediately above. No Revit placement adapter is built by #204 — see CONTEXT.md. |

### `perimeter_tie` is NOT blocked the way `dowel_tie` was — and the geometry/splice math IS built now

`docs/footing/reuse-audit.md` §1's two `dowel_tie` blockers (a dowel-bar
array; a column cross-section dimension the spec's naming table never
gives a symbol for) do not apply here: `perimeter_tie`'s rectangle needs
only `a`/`b`/`cover`, all three already carried by `FootingInputs` since
#198. This ticket therefore builds `rft.core.footing_perimeter_tie.
perimeter_tie_geometry` — `inner_a`/`inner_b`, `perimeter_tie_length`, the
12m-stock splice decision, and the closed rectangle's four footing-local
plan corners — and wires it into `rft.core.footing_plan.FootingPlan.
perimeter_tie` (opt-in, gated on `FootingInputs.perimeter_tie_dia_mm`).

What #204 deferred, the vertical ladder (no spec formula at the time),
was resolved by **R4** shortly after merge — see the table row above and
`docs/footing/spec-amendments.md`. What remains deferred is the Revit
placement adapter, which now has R4's Z-elevations to build curves from,
but per `docs/footing/verification/issue-197-footing-tracer-bullet.md`
§4, a closed-loop shape's host acceptance is itself still unverified
against a live footing host. Recorded as an open item, not silently
skipped.

---

## 5. Column auto-detection ray-cast (Story 1, `specs/isolated-footing-dowel-array.md` §3) — audited by #220

| Module / member | Status | Reason |
|---|---|---|
| `rft.revit.column_host.find_search_view` / `find_support_face_z_mm` | ⚠️ Technique reused, not the function | Same verdict the addendum's own §1 already states: the `ReferenceIntersector` ray-cast through a behaviourally-chosen `View3D` is the proven mechanism (#69/#107). The DIRECTION — a footing casting a ray upward to find an unknown column, instead of a column casting a ray at a known support — is new code, calling into the new shared `rft.revit.ray_search` module (see below) rather than into `column_host` itself. `column_host.py` is imported by nothing new here. |
| `rft.revit.ray_search` (new, extracted PR #224 review, finding 3) | ✅ New shared module, used as-is | The self-test-then-refuse view search and the inset-from-a-known-extent math `column_host.py` and `footing_host.py` both needed were duplicated verbatim in this PR's first version. Extracted into `RFT.lib/rft/revit/ray_search.py`, which `footing_host.py` now calls. **`column_host.py` was deliberately NOT migrated onto it** — editing a column-tool module is out of a footing ticket's scope per this repo's own element-isolation rule (`CONTEXT.md`: "never edit a beam or column module"). `column_host.find_search_view`/`find_support_face_z_mm` therefore still carry their own, now-duplicate, copy of the same logic. **Recommended follow-up, not done here:** a ticket scoped for the column tool to migrate `column_host.py` onto `rft.revit.ray_search`, removing that remaining duplication from the column side. |
| `rft.revit.column_host.read_section_mm` / `read_orientation` | ❌ Not called by this ticket | Named by Story 1's own text as the NEXT ticket's job ("#11 calls `column_host.read_section_mm`/`read_orientation` against whatever element this ticket returns") — out of #220's scope by the ticket's own wording, not a gap. |

### Design decision made without live-host access — verified by the orchestrator's own tracer bullet

`column_host.find_search_view` self-tests a candidate view by firing a ray,
filtered to the SAME category it searches with later
(`OST_StructuralColumns`), at the element already known to exist (the
column itself). Story 1 has no known column yet — that is what is being
searched for — so `footing_host.find_search_view` mirrors the self-test
onto the FOOTING instead: fire a ray filtered to
`OST_StructuralFoundation` at the footing, then trust the same view,
unquestioned, for a SEPARATE `OST_StructuralColumns`-filtered search
upward. This is the same *shape* of trust `column_host` already carries
(a column-filtered self-test view is reused, unquestioned, for a
`SUPPORT_CATEGORIES` multicategory search in `find_support_face_z_mm`),
but the SPECIFIC claim "a view that sees foundations also sees columns"
had never been measured live the way #69/#107 measured the column/support
case.

**✅ Verified on a live host, 2026-09-24** — see
`docs/footing/verification/issue-220-footing-column-autodetect.md`. The
module's exact logic was reproduced in C# against the live
`ColumnRFT.Trail.rvt` document (read-only, no transaction opened) across
all 3 `OST_StructuralFoundation` instances present: the `{3D}` view
self-tested successfully against `OST_StructuralFoundation` for every
footing (`Analytical Model` saw none, matching `column_host`'s own
`{3D}`/`Analytical Model` split exactly), and that SAME view then
correctly found the one real column genuinely sitting on a footing in
that model, with the two footings that have no column above them
correctly producing "no column found" — independently confirmed as true
negatives via a bounding-box check, not assumed from a null result. The
flagged assumption is confirmed, not merely plausible.
