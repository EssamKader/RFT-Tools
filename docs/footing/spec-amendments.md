# Isolated Footing spec — amendment / ruling ledger

Per `docs/reuse-for-new-elements.md` §4.2: a new element starts its own
ledger; it does not extend the beam tool's. This is the footing tool's.

Format follows the beam/column convention: each entry names what changed,
why, and which issue/ticket decided it.

---

## R1 — X == Y tie-break: defaults to Primary in the X direction

**Spec Ref:** `specs/isolated-footing.md` §2/§3. The rule as written is
only "if X > Y ⇒ Primary Reinforcement in X direction" — it never states
what happens when the two column-face offsets are exactly equal.

**Found by:** ticket #198's implementation
(`rft.core.footing_mesh.primary_reinforcement_direction`), which refused
(`FootingDirectionTieError`) rather than guess, per REUSE_GUIDELINES.md
§3's "Explicit Refusals" rule — recorded in `IsolatedFooting.extension/
CONTEXT.md` and raised to the project owner rather than resolved inline.

**Ruling (Essam, 2026-09-19):** "if x=y it does not matter what direction
is the primary." When `x_offset_mm == y_offset_mm`, `primary_
reinforcement_direction` now returns `DIRECTION_X` — an arbitrary but
fixed default, not a guess, since the project owner confirmed the choice
has no structural consequence in the tie case.

**Why this doesn't need to touch anything else:** every downstream formula
(mesh lengths in §4, the hook/development-length decision in §5, U-shape/
L-shape in §6, TOP+BTM in §7) treats Primary/Secondary as a per-mesh
label, never as a value that changes which formula applies — so a fixed
default for the tie case is sufficient and does not require a special case
anywhere else in the tool.

---

## R2 — LD == offset tie-break: refuse, and route to the existing U/L choice

**Spec Ref:** `specs/isolated-footing.md` §5. The rule as written defines
only `LD > offset` (hook) and `offset > LD` (no hook, switch to L-shape)
— it never states what happens when the required development length
exactly equals the available straight offset at a bar end.

**Found by:** ticket #199's implementation
(`rft.core.footing_mesh.bar_end_hook_decision`), which refused
(`HookDevelopmentLengthTieError`) rather than guess, per
REUSE_GUIDELINES.md §3's "Explicit Refusals" rule — recorded in
`IsolatedFooting.extension/CONTEXT.md` and raised to the project owner
rather than resolved inline.

**First ruling (Essam, 2026-09-20):** "for this it does not matter, ld
depend on bar size." Implemented as a silent default to `needs_hook=True`.

**Revised ruling (Essam, 2026-09-20, same day):** "maybe shall have two
options available for engineer to choose from whether u shape or alter
l." This supersedes the silent default: `bar_end_hook_decision` keeps
raising `HookDevelopmentLengthTieError` on the exact tie, and the
resolution is not a new mechanism — it is the SAME per-mat U-shape/
L-shape-alternating choice ticket #200 already built
(`bar_hook_plan_for_mat` with an explicit `mat_shape_mode`, which never
calls `bar_end_hook_decision` at all). The engineer facing this exact tie
sets that mat's shape explicitly instead of leaving it on automatic.

**Why this doesn't need to touch anything else:** #200's per-mat override
already exists and already bypasses this comparison entirely, so nothing
new was built to satisfy the revised ruling — only the automatic
(`mat_shape_mode=None`) path's refusal message was updated to point the
engineer at the override that already answers the question.

---

## R3 — Top mat vertical convention: mirrors the bottom mat from the top face

**Spec Ref:** `specs/isolated-footing.md` §7 (Story 4). The spec names the
BTM-only / TOP+BTM toggle but gives no explicit top-mat vertical-position
formula, unlike §4's `N`/`N2` for the bottom mat's own two-layer stack.

**Found by:** ticket #201's Phase 8 review (PR #214) — the first version
of that ticket reused `local_mesh_bar_endpoints` (measured from
`bottom_cover_mm` upward) unchanged for the top mat, which placed the
"top mat" at the exact same elevation as the bottom mat. Fixed with a new
`footing_mesh.local_top_mesh_bar_endpoints`, proposed as a mirrored
convention rather than assumed silently, and raised to the project owner
for confirmation before it could be treated as decided.

**Ruling (Essam, 2026-09-20):** confirmed correct — "yes this is right."
The top mat's first bar layer sits just below the top cover; its second
layer is stacked one bar-diameter further down into the footing,
mirroring exactly how the bottom mat's two layers stack upward from the
bottom cover. `footing_mesh.local_top_mesh_bar_endpoints` implements this
as confirmed, not merely proposed, as of this ruling.

**Why this doesn't need to touch anything else:** the mesh-length,
direction and hook-decision formulas (`mesh_bar_lengths`,
`primary_reinforcement_direction`, `bar_hook_plan_for_mat`) are already
identical for both mats per spec §4-§6, which cite no bottom/top
distinction — only the Z-elevation step (`_bottom_mat_endpoints` /
`_top_mat_endpoints` in `footing_plan.py`) ever needed to differ, and it
already does.

---

## R4 — `perimeter_tie` vertical starting offset: 250mm above the bottom mesh

**Spec Ref:** `specs/isolated-footing.md` §10. The rule as written states
diameter, spacing and quantity are direct user inputs and gives "one loop
every 200mm vertically" only as an EXAMPLE — it never states where the
first (or only) `perimeter_tie` loop sits vertically, unlike §9's
explicit "50mm from the bottom of the footing" for `dowel_tie`.

**Found by:** ticket #204's implementation
(`rft.core.footing_perimeter_tie`), which built the loop's plan geometry
(footing-local X/Y corners) but deliberately left the Z-elevation
unresolved rather than guess, per REUSE_GUIDELINES.md §3's "Explicit
Refusals" rule — recorded in `IsolatedFooting.extension/CONTEXT.md` and
raised to the project owner.

**Ruling (Essam, 2026-09-20):** the first `perimeter_tie` sits 250mm
above the bottom mesh. Read as 250mm above the SAME "top of the bottom
mesh" datum `rft.core.footing_dowels`'s own bend-corner elevation already
uses (`bottom_cover_mm + mesh_bar_x_dia_mm + mesh_bar_y_dia_mm` —
the top face of `mesh_bar_y`, the higher of the bottom mat's two bar
layers) — proposed as the most natural reading of "above the bottom
mesh" given that datum already exists in this codebase for exactly this
purpose, not an independent guess. Every subsequent `perimeter_tie` (up
to the user's own `quantity`) steps upward from there at the user's own
`spacing_mm` — Sec 10 already states spacing/quantity are direct user
inputs, so only the STARTING point was the open question.

**Why this doesn't need to touch anything else:** the loop's own plan
geometry (`local_perimeter_tie_corners_mm`) is identical at every level —
only the Z each level sits at changes, matching how R3's top-mat fix only
ever needed to change the Z-elevation step, never the plan geometry.

---

## R5 — `perimeter_tie` splice cut-length split: a direct two-field engineer input, no formula

**Spec Ref:** `specs/isolated-footing.md` §10. The rule as written says a
loop over the 12m stock length is "split into two bars, overlapped by lap
length `Ls` at the joint" — it never states how the total length (the
loop's own length plus one `Ls`) divides between the two individual
bars' own cut lengths.

**Found by:** ticket #204's implementation
(`rft.core.footing_perimeter_tie.perimeter_tie_splice`), which computes
the bar-count decision (1 or 2) and the total steel length to cut, but
refused to invent a 50/50 (or any other) split rule — recorded in that
module's own docstring ("The splice's own open question") and raised to
the project owner.

**Ruling (Essam, 2026-09-20):** not a formula — the engineer fills in the
two individual bar lengths directly (e.g. a 13m total could be entered as
8m + 5m, or 7m + 6m, or any other split the engineer picks on site). The
tool's job is to report the TOTAL length needing to be cut (already
computed by `perimeter_tie_splice`) and then accept the engineer's own
two lengths, refusing if they don't add up to that total — the same
"accept the input, validate it, don't derive it" shape `dowel_tie_dia_mm`/
`dowel_tie_spacing_mm` already have (direct inputs, no default), just
with an added consistency check since these two specifically must sum to
a value the tool already knows.

**Why this doesn't need to touch anything else:** `perimeter_tie_length_mm`
and the bar-count/total-length decision in `perimeter_tie_splice` are
unchanged — this ruling only adds a validation step consuming that
existing total, it does not change how the total itself is computed.

---

## R6 — Dowel array layout: mirrors the column's own longitudinal bar layout

**Spec Ref:** `specs/isolated-footing.md` §8 (Story 5). The rule as
written sizes ONE `dowel_bar`'s embedment/hook, and #202 places exactly
one representative dowel — the spec never states how many dowels exist or
where they sit in plan, only that `dowel_bar` IS "the column vertical
starter bar."

**Found by:** the handover from the 2026-09-24 session
(`docs/footing/HANDOVER-2026-09-24.md` item 5) — this is one of the two
prerequisites blocking `dowel_tie`'s own closed-loop shape (§9), flagged
as an architectural gap (no data to guess with) rather than a single
ambiguous value, per `REUSE_GUIDELINES.md` §3's "Explicit Refusals" rule.

**Ruling (Essam, 2026-09-24):** the dowel array is not an independent
count/spacing input. It mirrors ColumnRFT's own longitudinal bar layout
model exactly (`specs/column-rft-detailing.md` §2 — bar count per face
plus corner bars, one continuous perimeter arrangement), because each
`dowel_bar` IS the continuation of a real column vertical bar below the
splice, not a separately-invented array. `FootingInputs` gains fields
matching ColumnRFT's own layout inputs; a dowel is positioned at the same
perimeter location its corresponding column bar occupies.

**Why this doesn't need to touch anything else:** the per-bar embedment/
hook math `footing_dowels.dowel_embedment`/`local_dowel_bar_geometry`
already builds (#202) is unchanged — this ruling only decides HOW MANY
dowels exist and WHERE in plan, not how any single dowel's own vertical
geometry is sized.

---

## R7 — Column cross-section (Cw/Cd) source: read live from the column, reusing `column_host`

**Spec Ref:** `specs/isolated-footing.md` §2/§3. The naming table gives a
symbol (`Cw`) for the column's width in the a-direction only — it never
names the column's depth (b-direction) dimension, and `FootingInputs`
deliberately never stores `Cw` either (`footing_plan.py`'s own comment:
`x_offset_mm`/`y_offset_mm` are supplied directly "rather than derived
from a/b/Cw").

**Found by:** the same handover gap as R6 — the second of the two
`dowel_tie` prerequisites, since a real tie rectangle needs the column's
own b-direction cross-section width, which nothing in `FootingInputs`
carries today.

**Ruling (Essam, 2026-09-24):** not derived by offset math
(`Cd = b_mm - 2*y_offset_mm`) and not a new typed field — "each column is
defined by two dimensions a and b" read from Revit itself. `Cw`/`Cd` are
sourced live by reusing `rft.revit.column_host.read_section_mm`/
`read_orientation` as-is (the same live-host-verified, rotation-safe
adapter ColumnRFT already uses — issue #87/#69), against the actual
column `FamilyInstance` above the footing. This refuses on a
non-rectangular or flipped column exactly as `column_host` already does
for ColumnRFT — no separate refusal rule invented here.

**Ruling (Essam, 2026-09-24) — column is auto-detected, not picked:**
the footing tool does not ask the engineer to separately pick the column.
It auto-detects the column sitting on top of the picked footing, the same
`ReferenceIntersector` ray-cast technique `column_host.find_search_view`/
`find_support_face_z_mm` already use to find what's above/below a column
(live-host-proven in that direction), run in reverse — a ray fired upward
from the footing's own top face, filtered to `OST_StructuralColumns`. This
exact direction (footing -> column above) is a NEW use of a proven
technique, not proven itself yet, so it needs its own tracer-bullet
verification before it ships (same discipline as every other footing
feature, spec §5). If no column is found (or the column found is
non-rectangular/flipped), the tool refuses with a clear message ("no
column is attached to this footing") before any rebar placement runs —
**no manual pick/typed fallback**.

**Why this doesn't need to touch anything else:** every existing formula
that already reads `mesh_bar_x_dia_mm`/`mesh_bar_y_dia_mm`/`footing_
thickness_mm`/etc. off `FootingInputs` is unchanged — `Cw`/`Cd` are new
data flowing in from a new adapter, consumed only by the new dowel-array
placement logic (R6), not by any mesh/tie math that predates this
ruling.

**Extended during To-Spec (Essam, 2026-09-24, same day):** the To-Spec
draft (`specs/isolated-footing-dowel-array.md`) initially proposed a new
typed `FootingInputs` field for the cover used to position dowels within
the column's own cross-section, since that cover is conceptually distinct
from the footing's own `cover_mm`/`bottom_cover_mm`. Flagged rather than
assumed. **Ruling:** "for this use column cover for sure" — same
treatment as `Cw`/`Cd`, read live off the detected column by reusing
`rft.revit.column_host.read_cover_mm` (`CLEAR_COVER_OTHER`, already
live-host-verified for ColumnRFT's own amendment A2: cover is read from
the element and never typed, since #80 found Revit silently clamping a
typed cover to the host's own). No new `FootingInputs` field for this —
one more value that flows in live alongside `Cw`/`Cd`, not a fourth
typed input.

---

## R8 — Footing batch grouping: footing dimensions must be read live off the model first, not typed

**Spec Ref:** ticket #226 (Footing #14, batch placement)'s own "Open
question." `specs/column-batch-placement.md` §0/§3's batch mechanism
(which Essam ruled #226 must reuse as-is) groups columns by a
per-instance fact the single-column path already MEASURES live off the
host (clear height) — never by the type match alone, because two
columns of identical family+type were found, on a live model, to need
different tie ladders (one pair sat under a beam and had 300mm less
clear height than the rest). The footing tool has no equivalent
per-instance measured fact: `a_mm`/`b_mm`/`footing_thickness_mm`/
`cover_mm` are all manually typed per run today
(`IsolatedFootingRFT.pushbutton/script.py`), so there is nothing real to
group footings by yet — flagged as an open question rather than guessed,
per `REUSE_GUIDELINES.md` §3.

**Ruling (Essam, 2026-09-24):** "first it shall read dimension from
revit not from typed inputs." Footing geometry (`a_mm`/`b_mm`/
`footing_thickness_mm`, and cover if a matching live parameter is
confirmed) must be read live off the picked footing `FamilyInstance`'s
own TYPE parameters BEFORE batch placement work starts — mirroring
`column_host.read_section_mm`'s pattern, not a typed-input assumption.
This is Option 1 of #226's two flagged readings, not Option 2 (grouping
by the attached column's own live-read `Cw`/`Cd`/`Ccover` alone, with the
footing's own dimensions still typed and merely assumed identical for a
"same type" match).

**"If same footing so do share same rft no worries for no.02 run"** —
once dimensions are read live (rather than typed), footings that measure
identically automatically share identical detailing; the batch mechanism
never needs a second, separate run for genuinely identical footings, the
same guarantee `column_batch`'s own live-read grouping key already gives
columns.

**Ticketed as #228** (footing dimension live-read), which blocks #226 —
the batch ticket's own grouping key (its equivalent of
`specs/column-batch-placement.md` §3) cannot be written correctly until
#228 lands and the actual measured facts it exposes are known.

**Why this doesn't touch anything else:** every existing formula that
reads `FootingInputs.a_mm`/`b_mm`/`footing_thickness_mm` as plain numbers
(`footing_mesh.py`, `footing_dowels.py`, `footing_perimeter_tie.py`,
`footing_plan.py`) is unchanged — #228 only changes WHERE those numbers
come from (a live Revit read instead of a `pyrevit.forms` prompt), not
what any core formula does with them once supplied.

---

## R9 — Footing batch grouping key: the full live-read tuple (footing geometry + column section), not the column section alone

**Spec Ref:** ticket #226 (Footing #14, batch placement)'s own "Open
question," section 2 — resolved now that #228 (R8) has landed and both
readings the question offered are informed by a real prerequisite rather
than a hypothetical one.

**Context:** #226's own ticket body offered two readings for the
grouping key once a live-read prerequisite existed: (1) key on the FULL
live-read tuple — the footing's own geometry (#228) plus the auto-
detected column's own section/cover (#221) — or (2) key on the column
section alone, assuming footing-type match already guarantees identical
footing geometry (since `a_mm`/`b_mm`/`footing_thickness_mm` are TYPE
parameters, fixed by definition for a given family type).

**Ruling (Essam, 2026-09-24, via AskUserQuestion):** Reading 1 — the
grouping key is the FULL live-read tuple: `(a_mm, b_mm,
footing_thickness_mm, cover_mm, bottom_cover_mm, top_cover_mm)` from
`footing_host.read_footing_geometry_mm` (#228), plus `(Cw_mm, Cd_mm,
Ccover_mm)` from `footing_host.read_dowel_column_section_mm` (#221) — nine
fields total, all already live-read by existing, independently-verified
functions. No new derivation, no new parameter read invented for this
ticket alone.

**Why not reading 2 (column section alone):** Reading 2 would ASSUME two
footings of the same family type always measure identically rather than
MEASURE it — the exact category of mistake `specs/column-batch-
placement.md` §0 itself exists to warn against (a type match that looks
safe but silently hides a per-instance difference). Since #228 already
reads the footing's own geometry live, there is no reason left to fall
back to an assumption when the real measurement is one function call
away — R8's own text ("if same footing so do share same rft, no worries
for no.02 run") already implies the geometry itself is part of what
"same" means, not just the column above it.

**Mirrors `column_batch.group_key` exactly in spirit, not in shape:**
column batch keys on two fields read off ONE function's output
(`read_column`'s `ColumnExtent`); footing batch keys on nine fields read
off TWO functions' outputs (`read_footing_geometry_mm` +
`read_dowel_column_section_mm`), because the footing tool's own live-read
surface is split across two adapters where the column tool's is one.
Neither key is re-derived from a parameter or a second geometry read —
both are read exactly once, by the functions the single-run path already
calls and already has live-host verification for (#220/#221/#228).

**Why this doesn't touch anything else:** no existing `read_footing_
geometry_mm`/`read_dowel_column_section_mm` call site changes — #226's
own new `rft.core.footing_batch.group_key` is the only new consumer of
both return values together, and it only reads their fields, never
recomputes them.

---

## R10 — Dowel hook direction: outward from the column centroid, per bar position, never a fixed axis

**Spec Ref:** `rft.core.footing_dowels.local_dowel_bar_geometry`'s own
docstring, "Placement direction... is NOT stated anywhere in Sec 8...
This picks +X arbitrarily and documents it as an engineering placement
choice... **flag to Essam before this runs against a live host** if a
specific hook direction... is intended instead" — the flag this ruling
resolves.

**Found by Essam, visual inspection (2026-09-24):** with every dowel's
hook bent along the SAME fixed +X direction (#222's own implementation,
inherited unchanged by #223/#226), a dowel positioned on the side of the
array away from +X had its hook bend back TOWARD the column's own core
instead of away from it — visibly wrong in a live model screenshot (the
leftmost of three dowel bars shown bending right, into the column,
instead of left, away from it).

**Ruling (Essam, 2026-09-24):** A dowel's hook must bend OUTWARD from the
column's own centroid, never toward it, following the same convention
per bar POSITION:

- **Face bar** (mid-span of one of the column's four faces, not a
  corner): hook bends perpendicular to that face, straight outward. In
  an elevation looking directly at that face, the hook leg points along
  the view's own depth axis and foreshortens to a point ("shall appear
  as a dot").
- **Corner bar**: hook bends along the 45-degree diagonal bisecting the
  two faces that meet at that corner, outward — the same
  "outward-from-centroid" reasoning `rft.core.column_ties._outward_
  bisector` already uses for triangular tie construction (§141), applied
  here per-bar on a rectangle rather than per-tie on a triangle.

**Why this is a real geometry change, not a tweak:** before this ruling,
`local_dowel_bar_geometry` built ONE hook shape at the origin (hook along
local +X) and `translate_dowel_bar_geometry` only SHIFTED it (x/y
translate, explicitly no rotation — its own docstring said so) to each
bar's `(u, v)` position. Every bar therefore inherited the identical
fixed direction regardless of where it actually sat on the perimeter.
Implementing this ruling replaces that shift-only step with one that
builds each bar's OWN geometry at its own position AND its own outward
direction — `rft.core.footing_dowels.positioned_dowel_bar_geometry`
(new) plus `dowel_outward_direction` (new, pure: corner → 45° diagonal,
face → perpendicular, derived from the bar's `(u, v)` against the
column's own `half_u`/`half_v`, never guessed or hardcoded per bar).
`local_dowel_bar_geometry` itself is kept, unchanged in behaviour, as a
thin call into the new function at the origin with the legacy `+X`
direction — the single-representative-bar fallback path (#202, no live
column/array inputs supplied) has no column shape to be "outward"
relative to, so it keeps its original, already-tested output exactly.

**The Revit adapter's own `norm` argument must also vary per bar now**
(`rft.revit.footing_dowels._create_dowel_rebar`) — previously hardcoded
to `XYZ.BasisY` (correct ONLY for the old fixed +X hook direction, per
`column_place_bars.py`'s #183 measurement that `norm` must be
perpendicular to the bend's OWN plane). A bend plane now differs per
bar, so `norm` is derived from each bar's own hook vector (a 90-degree
in-plane rotation of the hook direction), not a fixed axis — the exact
same #183 measurement still governs, just applied per bar instead of
once for the whole array.

**Why this doesn't touch anything else:** `translate_dowel_bar_geometry`
is removed — its ONLY caller was `_build_dowel_plan`'s array-building
loop, which now calls the new direction-aware function instead; nothing
else in the codebase referenced it. `column_layout.py`/`column_ties.py`
are read-only reuse targets here (the OUTWARD-FROM-CENTROID reasoning is
reused, not the code) — neither is modified, per this repo's
element-isolation rule.

## R11 — Bottom-mesh bar array: direct spacing input per direction, count derived

**Spec Ref:** specs/isolated-footing.md §4 (Story 1) defines `mesh_bar_x`/
`mesh_bar_y` bar-LENGTH formulas only — it never states how many mesh bars
exist or how they are spaced, the same silent gap the dowel array had
before R6. #198/#229 built and placed exactly ONE representative bar per
direction, matching the spec's own silence, not a shortcut invented here.

**Gap surfaced to Essam (2026-09-24):** running the fully-wired tool on a
real footing places only one `mesh_bar_x`/one `mesh_bar_y` — not a mesh —
because no ticket ever asked how many bars there are or their spacing.

**Ruling (Essam, 2026-09-24):** direct spacing input, one per direction
(mirrors `dowel_tie_spacing_mm`'s own precedent: a direct user number, no
formula/code-table lookup). The tool computes how many bars fit across the
footing's own available width for that direction and places them evenly —
same reasoning `perimeter_bar_positions` already applies to a column's own
bar layout, adapted to a rectangular mesh rather than a perimeter.

**Scope this ruling opens (not yet ticketed):** new `FootingInputs` fields
(`mesh_bar_x_spacing_mm`, `mesh_bar_y_spacing_mm`), a new core function
building the full array of `MeshBarGeometry` per direction (reusing
`bottom_mesh_bar_geometry`'s own per-bar hook logic unchanged — every bar
in the array gets the identical U/L hook shape #229 already built, only
its own Y/X offset differs), and a placement adapter looping
`place_straight_bottom_mesh`'s own single-bar call once per array position
(the same "loop the existing single-bar call" shape #223 already used for
the dowel array over #202's one representative dowel). Top mesh (Story 4)
gets the identical treatment once its own placement adapter exists (R11
does not itself unblock that — see the top-mesh ticket instead).

## R12 — Dowel splice length (`Ls`) extends into the column; the `§0 F3`
boundary is narrowed for this one bar only

**Spec Ref:** specs/isolated-footing.md §8 (Story 5) names `Ls` = lap/
splice length as a user input but never consumes it in any Story 5
formula — `LD` (development length), not `Ls`, governs `a_dowel`/
`b_dowel`. §0 F3 states this tool's top boundary is "hands off at 50mm
below Top of Footing... never details anything the column tool already
owns", which is why `footing_dowels.py`'s vertical leg was built to stop
exactly at the footing's own top face (`bend_z_mm + a_dowel_mm ==
footing_thickness_mm`), reading `Ls` as orphaned spec text rather than a
missed formula.

**Gap surfaced to Essam (2026-09-24):** a dowel bar that stops at the
footing top with no splice length into the column above is not a usable
dowel on a real project — visually and functionally incomplete, screenshot
on file.

**Ruling (Essam, 2026-09-24):** narrow the F3 boundary for the dowel bar
specifically: `Ls` becomes a real, direct user input on this tool
(distinct from `LD` — Ls is *how far the bar continues past the footing
top*, not a development-length comparison), and the dowel's vertical leg
extends `Ls` mm past `footing_thickness_mm` into the column. This does
NOT reopen the rest of F3 — `dowel_tie` (Story 6) still stops 50mm below
T.O.F. exactly as before (no ties placed above T.O.F., the column's own
tie logic still owns that), and this tool still details nothing about the
column's own longitudinal bars or the column's own ties above T.O.F.

**Scope this ruling opens (not yet ticketed):** a new `FootingInputs.
dowel_splice_length_mm` field (append-only), `positioned_dowel_bar_
geometry`'s `top` point extended from `bend_z_mm + embedment.a_dowel_mm`
to `+ splice_length_mm`, and a live-host verification specifically for a
bar hosted on a footing whose geometry extends past that footing's own
top face into open space above it (a related, but not identical, question
to #197 Sec 2's "may a footing-hosted bar extend beyond the footing's own
top face" kept-write proof — that proof covers extending to the column
base; extending further, through/past the column's own solid geometry, is
a new combination, unverified until its own tracer bullet runs).

## R13 — Top mat hook direction: bends toward the bottom mat (downward)

**Spec Ref:** `rft.core.footing_mesh.bottom_mesh_bar_geometry`'s own
docstring named this gap explicitly: "the top mat's own hook direction
(would it bend up, toward the bottom mat, or down, toward the top face?)
is not stated anywhere in the spec and the top mat has no placement
adapter yet... guessing that direction now, with no consumer to verify it
against, is exactly the guessing REUSE_GUIDELINES.md Sec 3 refuses" —
issue #233 is that consumer, so the gap is resolved here rather than left
open again.

**Ruling (Essam, 2026-09-24):** the top mat's hooked ends bend DOWNWARD,
toward the bottom mat — the mirror image of the bottom mat's own
"bend the bar up" rule (Sec 5), not a repeat of it. A hooked end's
vertical leg therefore runs from the top mat's own elevation DOWN by the
hook leg length, toward the bottom mat, rather than up toward the top
face.

**Scope this ruling opens (not yet ticketed until #233 lands):** the top
mat needs its own bent-centreline builder, mirroring
`bottom_mesh_bar_geometry`/`_mesh_bar_hook_points` but with the hook leg
subtracted from (not added to) each hooked end's own elevation. The
straight-run span and elevations themselves are unchanged
(`local_top_mesh_bar_endpoints`, R3-confirmed) — only the hook leg's
own sign flips relative to the bottom mat's rule.

## R14 — `perimeter_tie` splice: modeled as TWO separate open bars, not one closed loop with a BOM-only split

**Spec Ref:** `rft.core.footing_perimeter_tie.py`'s own docstring
("The splice's own open question -- RESOLVED (R5)") already resolved
*how the total length divides into two cut lengths* (a direct two-field
engineer input, R5) but never stated *how the two resulting bars should
look in the Revit model itself* when `PerimeterTieSplice.bar_count == 2`
— a genuinely separate question from R5, since a placement adapter has
to choose an actual geometric shape for "two bars," not just a cut-list
number.

**Ruling (Essam, 2026-09-25):** model the split as TWO separate physical
`Rebar` elements in the 3D model — not one continuous closed loop with
the split only noted in the report. This is more realistic (matches what
actually gets fabricated and tied on site) at the cost of being a new
shape this tool has not built before.

**Scope this ruling opens (not yet ticketed until #244 lands):**
`perimeter_tie_geometry`'s own docstring already reads Sec 10's splice as
"the perimeter treated as one long UNROLLED length, cut at a single
point, exactly like a straight bar lap-spliced along its run" — this
ruling is the placement adapter that reading was always pointing at.
Concretely: pick a fixed unroll start point (the SW corner,
`local_perimeter_tie_corners_mm`'s own first-wound corner, arc-length
position `s = 0`), walk the closed rectangle's own perimeter by arc
length through its four corners (SW→SE→NE→NW→back to SW at
`s = length_mm`), and place:
- **Bar 1**: from `s = 0` to `s = first_bar_length_mm` (an OPEN
  multi-segment polyline, turning at whichever corners `s` passes
  through — not a closed shape).
- **Bar 2**: from `s = first_bar_length_mm - lap_mm` to
  `s = length_mm` (which is the SAME physical point as `s = 0`, closing
  the loop) — so bar 2's own end meets bar 1's own start exactly where
  the rectangle closes on itself (no gap, no separate overlap needed
  there), while the two bars overlap by `lap_mm` in the middle of the
  unrolled run, at the single splice point Sec 10 describes. This
  arithmetic is self-consistent with `perimeter_tie_splice`'s own
  `total_length_mm = length_mm + lap_mm` formula (verify algebraically
  before implementing, don't just trust this summary).

When `PerimeterTieSplice.bar_count == 1` (loop at or under the 12m stock
length, the common case), this ruling does not apply — place the single
closed loop exactly as before, unaffected.

## R16 — Top mat bar diameter: set independently of the bottom mat's, never coupled

**Spec Ref:** specs/isolated-footing.md §7/Story 4 never names bar
diameter as a shared-vs-independent choice at all — the same kind of
silence R13 and the `top_mat_shape_mode` toggle (§7's "set separately,
never coupled" wording) already closed for hook direction and U/L shape
respectively. #201/#233 built the top mat reusing the BOTTOM mat's own
`mesh_bar_x_dia_mm`/`mesh_bar_y_dia_mm` throughout, unchallenged until
issue #253 raised it.

**Ruling (Essam, 2026-09-25):** the top mat's bar diameter, in both
directions, is set INDEPENDENTLY of the bottom mat's — the same
"set separately, never coupled" principle §7 already states for the
BTM-only/TOP+BTM reinforcement toggle and the U/L-shape toggle. A top mat
commonly runs a smaller bar than the bottom mat (the reinforcement it
resists is smaller), so silently reusing the bottom mat's own diameter
would be wrong in the common case, not just a missing convenience.

**Scope this ruling opens (issue #253):** two new `FootingInputs` fields,
`top_mesh_bar_x_dia_mm`/`top_mesh_bar_y_dia_mm`, both defaulting to
`None` so every caller that predates #253 (BTM-only plans, and every
existing TOP+BTM test that never named its own top diameters) is
unchanged. Once `top_reinforcement == TOP_REINFORCEMENT_TOP_AND_BTM`,
both become REQUIRED — `build_footing_plan` raises
`TopMeshBarTypeRequiredError` rather than silently falling back to the
bottom mat's own `mesh_bar_x_dia_mm`/`mesh_bar_y_dia_mm`. The top mat's
own lengths, endpoints and hook plan (`_build_mesh_mat_plan`) and its own
bent geometry (`top_mesh_bar_geometry`) all use these new fields
throughout, never the bottom mat's diameters. The UI (`FootingWindow`)
grows its own `top_mesh_bar_x_type_cb`/`top_mesh_bar_y_type_cb` combos,
only required (refused on `Build plan` if unset) when TOP+BTM is
selected, and the batch path (`footing_batch.BatchInputs`) carries the
SAME two fields so a batch run gives every footing in the group the same
top-mat bar type rather than reusing the bottom mat's.
