# Project Context — Column RFT Tool

Companion project to the Simple Beam RFT tool, in the same monorepo, sharing
`RFT.lib`. **Read this before writing any code.**

> **Conversion note:** markdown form of
> `technical-material/column/CONTEXT.docx`. Wording is preserved; the only
> edits are (a) paths updated to where files actually live after the
> repository restructure, and (b) the packaging question this document asked
> the reader to "confirm before the first ticket" is now marked as answered,
> with the answer. Both are marked inline as **[RESOLVED]** or **[PATH]**.

---

## Standing rule: the spec is the source of truth — the CADS manual is NOT

All detailing logic (confinement length/spacing, first-tie offset, middle-zone
spacing, horizontal restraint tiers, inner-tie topology, hook alternation,
splice geometry) is governed by
[`specs/column-rft-detailing.md`](../specs/column-rft-detailing.md). **[PATH]**

Do not treat the attached CADS Rebar Extensions manual as a source of detailing
rules. It is provided for exactly ONE purpose: to explain the subset-based tie
convention referenced in spec §6.2 (an initial bar index + a count of tied bars,
generating closed rectangular loops) — a **MODELING CONVENTION, not a code
requirement**. No numeric limit, spacing value, or detailing rule should ever be
sourced from the CADS manual. If the CADS manual and the spec ever appear to
disagree on anything beyond that one convention, **the spec wins, full stop**,
and the discrepancy is a Grill ticket, not a silent pick.

Every rule implemented in code must trace back to a numbered section of the
column spec (e.g. "per §4", "per §6.1"). Do not invent detailing rules that
aren't in the spec.

§12's citations are chapter/figure-level (ECP 203 Chapter 8; Egyptian Detailing
Guide 2001, Figure 13-3), not numbered sub-clauses. Refining these to exact
sub-clause numbers is a welcome improvement at any point, but is **not a
blocker** — do not hold up implementation waiting for it.

## Spec open items — status

- **§6.2 tie topology (auto-derive vs. template selection)** — DEFERRED BY
  DECISION, not an oversight. Do not implement either approach without raising
  it as a ticket first; the spec explicitly defers this until after the tracer
  bullet (§11) proves the underlying API mechanics. *(The tracer bullet is now
  done — this decision is live and open.)*
- **§12 citation granularity** — open, non-blocking. Sub-clause numbers may be
  added later without a spec amendment cycle.

## Standing rule: reuse from the beam tool is earned, not assumed

`RFT.lib` is shared. That does NOT mean this tool imports whatever it finds
convenient. Per spec §2, §6, and §10:

- **`rft.core.column_layout` is a NEW module.** Column bars are modeled as one
  perimeter layout (spec §2), not the beam's independent-face model. Do not
  attempt to reuse `rft.core.layout`'s `FacePlan`/`LayerPlan` functions by
  adapting their arguments — re-derive from the perimeter model instead.
- **`rft.core.anchorage` is explicitly NOT reused** (spec §10). Column bar ends
  are governed entirely by the floor-to-floor splice override (spec §9). Do not
  import or call into `anchorage.py` for any reason without raising it as a
  ticket first.
- **`rft.core.stirrups` does not cover inner ties.** Spec §6.2's overlapping
  closed-loop, subset-defined ties are new geometry. The outer tie MAY reuse
  `stirrup_curve_endpoints_mm`-style logic where the shape genuinely matches a
  beam's single closed rectangle — confirm this per-function before reusing, do
  not assume the whole module applies.

Genuinely reusable candidates worth auditing first (not guaranteed, worth
checking): `rft.core.spacing`, `rft.core.grades`, `rft.ui.sketch_palette` and
the AST-guard/mutation-prover infrastructure in `rft.core.guards` /
`tools/prove_guards.py`. Do an honest per-module audit before importing — state
the audit result in the module's docstring the way `rft.core.plan` states its
own reasoning.

> **[RESOLVED] That audit is done:**
> [`docs/column/reuse-audit.md`](../docs/column/reuse-audit.md). Read it before
> importing anything. It found a **blocking** problem: `rft.core.spacing`
> imports `rft.core.guards`, which imports `rft.core.anchorage` — so the best
> reuse candidate currently drags in the one module §10 forbids.

## Standing rule: pyRevit extension only

Same convention as the beam tool — no `.addin`, no compiled DLL, no installer.
Python only, against pyRevit's engine.

> **[RESOLVED] Layout.** This document originally asked the reader to confirm
> whether the column tool ships as its own `ColumnRFT.extension/` or as a
> `Columns.panel/` inside the beam extension. **Answer: its own extension.**
>
> ```
> ColumnRFT.extension/
> └── RFT-Tools.tab/            <- same TITLE as the beam extension's tab;
>     └── Columns.panel/           pyRevit merges tabs by title
>         └── ColumnRFT.pushbutton/
>             ├── bundle.yaml   <- engine: persistent: true (modeless window)
>             └── script.py
> ```
>
> Shared code is imported from `RFT.lib` exactly as the beam tool does.
> Releases are tagged **`column/vX.Y.Z`**, independently of `beam/vX.Y.Z`.

## Standing rule: a live Revit host IS reachable — this changes the verification workflow from the beam project

Unlike the beam tool's development environment, this project has a Revit MCP
connection available, giving direct read (and possibly write, depending on which
MCP server is wired in) access to a real, running Revit session during
development.

This does NOT relax the discipline that got the beam tool through six release
candidates of wrong API assumptions — it removes the reason those assumptions
had to be guessed at all:

- Spec §11's tracer bullet is not optional and not deferred. **[RESOLVED — done
  2026-09-14, see `docs/column/verification/issue-69-column-tracer-bullet.md`.]**
- Every new Revit-API shape this tool relies on (reading a point-based
  `FamilyInstance`'s rotation, generating multiple closed `Rebar` loops per bar
  set, per-level hook-corner placement) should be confirmed live via MCP
  **BEFORE** the corresponding core/revit module is written against an
  assumption — not after, as a bug-fix.
- **Still write it down.** A value confirmed via MCP this session is not
  automatically true in every Revit version or every future host. Keep the
  `SHAPE UNVERIFIED` / verified-per-release discipline from the beam project's
  `tests/fake_revit_api.py` and changelog — MCP access speeds up finding the
  truth, it doesn't replace recording it for whoever reads this repo without an
  MCP connection of their own.
- If the MCP connection is read-only for a given session, treat placement logic
  exactly as unverified as the beam project always did, and gate
  placement-related tickets accordingly.

> **Practical note learned the hard way (from #69/#70):** the MCP code executor
> already holds an **open transaction** (`document.IsModifiable == True` on
> entry), so `Transaction.Start()` throws an opaque invocation error. Use a
> `SubTransaction` — and a **rolled-back** one is how a write-bearing experiment
> is run without leaving anything in the model.

## Standing rule: mutation-proven guards, same bar as the beam tool

Any guard added for logic that cannot be executed directly under CPython
(anything touching `pyrevit`, WPF, or the live Revit API) must be provable by
`tools/prove_guards.py`-style mutation — reintroduce the defect, show the guard
catches it — before it counts as tested. **A guard that has never been shown to
fail has only been written, not tested.** This bar does not lower for a second
tool.
