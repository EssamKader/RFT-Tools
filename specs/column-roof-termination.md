# Column RFT — Roof-Level Termination Addendum

> **Status: READY TO IMPLEMENT.** Every gate this file has carried is down.
> §7's citation is **named** (ECP Detailing Code for Concrete Structures,
> Figure 3-14 — #102; the edition/year is still unconfirmed and changes
> nothing about `a + b = L_D`). §5's tracer bullet is **complete** (#103): the
> pick runs, a picked face maps exactly to one of `column_layout`'s four, that
> survives rotation, a slab face and an end face are **unpickable**, and Escape
> raises `OperationCanceledException`. The three decisions left open are now
> owner rulings — **R35** (`L_D` is stated), **R36** (the engineer states the
> roof condition) and **R37** (the slab's thickness and cover are read).

**A roof column is not a new element — it is a *condition* an ordinary column
can be in.** It has the same section, the same cage, the same confinement, and
is detailed by the same tool; the only thing the condition changes is where the
longitudinal bar ends. So this is an **addendum to
[`specs/column-rft-detailing.md`](column-rft-detailing.md), not a replacement**,
and not a second element: no separate core module, no separate extension, no
`element:` label of its own. It covers ONLY the top of a column that has no
storey above it.
Every other rule in the main spec — confinement `L0`/`S0`, horizontal restraint,
hook types, Mode A/B — is unchanged and still governs a roof-level column's
body. **Only the longitudinal bar's TOP TERMINATION changes at roof level;
nothing here touches ties or stirrups.**

Tracked by **#77**. Amendments, once this is unblocked, are recorded in
[`docs/column/spec-amendments.md`](../docs/column/spec-amendments.md).

---

## 0. Why this exists

The main spec's splice override (§9) assumes a storey above to splice into. At
roof level there is no storey above — the bar has to terminate into the roof
slab instead. This addendum defines that termination.

## 1. Base geometry — bend into slab

> **R35**: the engineer states the **multiplier** — `L_D = multiplier × bar
> diameter`, as in the beam tool (60Ø, 50Ø, whatever the job calls for) — or a
> plain value. The tool does the multiplication; it never picks the multiplier,
> and it never inherits the beam's 55/60 defaults, which are for bars in
> bending.
> **R37**: the slab's **thickness and cover are READ** from the element the
> upward support search locates; if it finds no slab, the tool refuses.
> **R38**: a slab whose cover reads **zero** has none set — measured on a live
> host (#161) — and only then may the engineer type one. An empty field is a
> refusal, and the report names which of the two it was.

> **R40**: `L_D` is the **developed centreline length of the built bar**.
> Revit fillets the corner, so the legs handed to the API are longer than
> `L_D` by `Δ = r(2 - π/2)`, with `r` read from the bar type. Measured in
> #161: 900 mm of nominal leg builds an 880.2 mm bar.

The longitudinal bar's development length `L_D` is split into two legs:

    a + b = L_D + Δ        (R40; Δ = 0 only if the corner were unfilleted)

where `a` is the vertical run from the slab's bottom face up to
(floor thickness − cover), starting from the floor's bottom face, and
`b = L_D − a` is the horizontal leg bent into the slab.

This is the baseline case — full `L_D` achieved via the bend — and applies
whenever slab genuinely continues in the bar's bend direction (§2).

## 2. Generalized per-face rule

**Replaces separate Interior / Edge / Corner cases.** For each longitudinal
bar, evaluate whether slab continues beyond the column in that bar's bend
direction:

> **R41 supersedes the binary below.** Every direction carries an available
> **run**, and the run always governs: the column's own width at a free edge,
> the distance to the slab edge for an interior column near one, and no limit
> at all deep inside. The bend takes the direction with the most room, a
> capped leg places and reports its shortfall, and the report says whether the
> run was short because of a flagged free edge or a measured slab edge.
> **R42**: that distance is measured from the floor's boundary, never typed.

- **Slab continues** → the bend achieves full `L_D` via `a + b = L_D` (§1).
- **No slab continues in that direction** (a free building edge) → accept the
  reduced `a_E + b_E` instead, where `b_E` is capped to whatever horizontal run
  actually fits within the column's own width at that face:
  `b_E = column width at that face − cover × 2`.

A bar with more than one available bend direction (a true corner bar) **may
bend into whichever available direction has slab**, achieving full `L_D` — it is
not forced into a fixed "default" direction that happens to face a free edge.

**No preferred direction** when more than one open direction is available for a
corner bar. Any valid slab-facing direction is acceptable; there is no rule
preferring one over another for consistency or for bar length.

"Interior / Edge / Corner column" are now **descriptive labels** for how many
free-edge faces a column happens to have (0 / 1 / 2 adjacent), **not three
separately-implemented logic paths.**

## 3. How the tool knows which faces have slab — pick the exception

> **R36**: the tool does not infer that a column is at roof level. **The
> engineer states it**, and an unticked box means §9's ordinary splice,
> whatever sits above the column.
>
> **§5 is satisfied** — see
> [`docs/column/verification/issue-103-face-references.md`](../docs/column/verification/issue-103-face-references.md).
> The pick runs, a picked face maps exactly to one of `column_layout`'s four,
> that survives rotation, an end face and a slab face are **unpickable** at
> pick time via `ISelectionFilter`, and Escape raises
> `OperationCanceledException`. One constraint from it: the filter must match
> the **picked column's own element id**, not merely the structural-column
> category, or a free edge could be flagged on the neighbouring column.

**Default: every face is assumed to have slab continuing (full `L_D`)**, unless
the engineer explicitly flags it otherwise.

This is the conservative default — assuming slab continues produces the
**longer** development length. An un-flagged genuine free edge produces a bar
bent assuming slab that isn't there, which is a real error but tends to be
**visible in the model** (a bar extending into open space) rather than a
silently-wrong buried number.

The engineer flags a free edge by picking **the column's own face** in the Revit
view where slab does not continue — not the slab, because there is nothing to
click where slab is absent. **Multi-pick:** the engineer may pick more than one
face in a single selection action (e.g. both free-edge faces of a corner column
at once), rather than repeating a single-pick interaction per face.

**Why pick-the-exception** rather than pick-every-face or a compass/grid
dropdown: an interior column — the common case — requires **zero clicks**. Only
edge and corner columns, where a real judgment call exists, need any input at
all.

Labelling schemes considered and **rejected as the primary input method**:

- **Compass (N/S/E/W)** — ambiguous without a locator diagram, and depends on
  Project North vs. True North being stated explicitly if ever reintroduced as a
  display convention.
- **Grid reference ("faces Grid A")** — natural vocabulary for a structural
  engineer, but requires a new nearest-gridline lookup per face and a defined
  fallback for a column not cleanly between two gridlines.

Neither is needed as the *input* mechanism now that picking targets the actual
geometry directly. Either could still be considered later as a **display label**
alongside a picked result, if reading the report ever proves confusing without
one.

## 4. Report requirement

Mirrors Mode A/B's warn-but-place discipline. The Review report must list, per
column, **which faces were flagged by the user** (free edge, `a_E + b_E`) versus
**defaulted** (slab continues, full `L_D`).

A reviewer must be able to catch a missed pick by **reading the report**, not
only by noticing a stray bar in the 3D view.

## 5. Prerequisite: a new tracer bullet, separate from #69

#69 proved **passive reads** — section orientation, vertical neighbour search —
inside a rolled-back `SubTransaction`. **Interactive face picking is a
different, unverified API surface:** `PickObjects` (plural, per §3's multi-pick
decision) with a face reference filter, run against a real structural column and
a real adjacent slab, confirming the returned reference **reliably correlates
back to one of the four faces** in `column_layout`'s perimeter model.

This must be proven on a live host, scoped as its own tracer bullet, **before
this addendum's logic is implemented** — the same discipline §11 of the main
spec already established for reads, extended here to interactive selection.

## 6. Explicitly out of scope

**Batch / automated placement across multiple columns is explicitly NOT
attempted for roof-level columns.** The pick-the-exception interaction in §3
requires a human decision per column with a free edge, which is incompatible
with unattended batch placement. This is an accepted, deliberate limitation —
roof columns are placed one at a time.

This addendum does **not** change confinement (`L0`/`S0`), horizontal restraint,
or hook-type rules from the main spec. It covers only the longitudinal bar's top
termination.

> **Note — batch automation for NON-roof columns is a separate, real interest,
> not designed here.** Automating placement across multiple columns sharing the
> same type (e.g. every 600×300 column in one run) has been raised as a desired
> future capability for ordinary floor-to-floor columns, which have no
> pick-the-exception step to block it. This is deliberately **not** scoped or
> designed in this addendum — it touches placement batching, not roof
> termination, and per this project's own rule (a ticket never mixes two
> unrelated concerns) it deserves its own spec and its own tracer bullet
> (confirming how reliably columns of the same nominal type can be identified
> and grouped) before design starts.

## 7. Citations — NAMED, edition pending (#102)

**Source: ECP Detailing Code for Concrete Structures, Figure 3-14** — Arabic
title *"شكل رقم (٣-١٤) — نموذج تفاصيل اتصال حائط منتهى بالسقف"*, roughly
*"Figure 3-14 — model of wall-to-roof connection details"*. Named by the owner
(#102).

- **§1's base bend geometry (`a + b = L_D`)** — that figure, plus the owner's
  original manual sketch which agrees with it.
- **§2's per-face rule** — derived from the same figure: whether slab continues
  beyond the column is what selects full `L_D` against the reduced
  `a_E + b_E`.

### The numbering objection that blocked this, and why it is answered

This section was OPEN because **"3-14" does not match the "13-3" / "13-4"**
numbering cited in the main spec, and a wrong provenance is worse than no
provenance — a bad citation stops anyone looking again. The answer is that they
are different chapters of a *detailing* code: 13-3 is a **column** figure,
3-14 is a **wall-to-roof connection** figure. Not a mismatch.

### What remains open, deliberately recorded rather than assumed

**The edition/year**, and whether the *Detailing Code for Concrete Structures*
is the same publication as the *Egyptian Detailing Guide (2001)* cited for
Figure 13-3. They very likely are. **That is not written here as fact**, and no
year is stated anywhere in this file, because a citation is precisely the kind
of line nobody re-checks once it looks complete.

This does not block implementation: `a + b = L_D` is the same geometry in any
edition. **#103's tracer bullet is the live blocker** — §5 requires
`PickObjects` proven against a real host before §3's input is built, and as of
writing only the face-correlation half has been run (see
`docs/column/verification/issue-103-face-references.md`).

The main spec's own §12 note applies here too: no more granular clause number
than the figure is claimed.

If the figure is added to the repo it belongs in `technical-material/column/`;
**this** document is what cites it.

If the wall-detail figure referenced above is added to the repo, that image
belongs in `technical-material/column/`; **this** document is what cites it.
