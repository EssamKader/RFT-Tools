# Project Context — RFT-Tools

## Which context applies to the work in front of you

This repo holds **more than one element**. Rules below that name beams, spans,
`h > 700`, anchorage or the three-zone stirrup rule are the **beam tool's**
rules and do not govern another element.

| Working on | Read |
|---|---|
| **Any element** | this file's *repo-wide* rules (below), plus [`REUSE_GUIDELINES.md`](REUSE_GUIDELINES.md) |
| **Beam** | the beam sections of this file + [`specs/beam-rft-detailing.md`](specs/beam-rft-detailing.md) |
| **Column** | [`ColumnRFT.extension/CONTEXT.md`](ColumnRFT.extension/CONTEXT.md) + [`specs/column-rft-detailing.md`](specs/column-rft-detailing.md) |
| **Shared `RFT.lib`** | [`docs/column/reuse-audit.md`](docs/column/reuse-audit.md) — what is genuinely element-agnostic, and what only looks it |
| **Adding a new element** | [`docs/reuse-for-new-elements.md`](docs/reuse-for-new-elements.md) |

### Repo-wide rules, true for every element

1. **The spec is the source of truth.** Every rule in code cites its numbered
   spec section. A gap is a decision ticket, never a silent guess.
2. **pyRevit extensions only** — no `.addin`, no compiled DLL, no installer, no
   C# port. Python against pyRevit's engine.
3. **Element isolation.** An element's core module, extension and docs are its
   own. Shared code lives in `RFT.lib` and is reused only where an audit has
   earned it. A ticket never mixes two elements; issues carry `element:beam`,
   `element:column` or `element:shared`.
4. **Mutation-proven guards.** Any guard over code that cannot run under CPython
   must be proven by `tools/prove_guards.py`-style mutation. A guard that has
   never been shown to fail has only been written, not tested.
5. **`master` means the code exists; a tag means it was verified on a live host.**
   Only a tagged commit is ever loaded into Revit. Tags are per tool —
   `beam/vX.Y.Z`, `column/vX.Y.Z`.

> **Note on the "no live Revit host" rule below:** that constraint is the **beam
> tool's** development reality and is still true of it. The **column** tool has
> a live Revit host reachable over MCP — see `ColumnRFT.extension/CONTEXT.md`.
> The verification discipline does not relax either way; only the reason for
> guessing goes away.

---

# Beam tool — standing rules

## Standing rule: the spec is the source of truth

All detailing logic (development length & anchorage, stirrup distribution,
main bar layer offsets, crack/skin reinforcement, bar spacing rules, stirrup
closure types) is governed by
[`technical-material/beam/beam_rebar_detailing_spec_v2.docx`](technical-material/beam/beam_rebar_detailing_spec_v2.docx).

**Revision 2 is the source of truth.** `beam_rebar_detailing_spec.docx`
(revision 1) is kept only as the historical baseline — do not implement from
it. Rev 2 incorporates 40 amendments from the Wayfinder cycle, each traced to
its deciding ticket in [`docs/beam/spec-amendments.md`](docs/beam/spec-amendments.md).

- Every rule implemented in code must trace back to a numbered section of
  the spec (e.g. "per §2.1", "per §6.2"). Do not invent detailing rules that
  aren't in the spec — if a gap is found, it becomes a Grill-type decision
  ticket, not a silent guess.
- If a future change conflicts with the spec, the spec wins unless the user
  explicitly amends it first (and the doc is updated to match).

### Spec §9 open items — status after the Wayfinder cycle (2026-09-08)

1. **Bottom bar anchorage bend geometry (`a_btm`, §2.2)** — **CLOSED.**
   Confirmed correct as written; rationale recorded in rev 2 §2.2.
2. **Multi-span beam behavior** — **STILL DEFERRED.** Single-span is the hard
   scope boundary. Do not propose multi-span features unless the user raises
   them. The tool should warn on, or refuse, a beam in a continuous run
   rather than silently detailing it as simply supported.
3. **Stirrup leg dimensioning formulas (§7)** — **CLOSED for the outer
   perimeter** (rev 2 §7.1). The **inner loop of stirrup type 3** remains
   undefined, which is why **type 3 is parked** and the stirrup type input is
   (1, 2, 4) in v1.

### Residual questions R1–R6 — must not be guessed

Rev 2 §11 lists six questions the cycle deliberately left open. Any ticket
touching one of them must surface it as an explicit acceptance criterion and
get an answer from the user — it may **not** be resolved by assumption, and
such a ticket may not be marked `ready-for-agent` until it is.

## Standing rule: pyRevit extension only

This ships as a **pyRevit extension**. It is **not** a standalone application
and **not** a Revit `.addin` / compiled add-in.

- No `.addin` manifest, no `.csproj`/`.sln`, no compiled DLL, no installer —
  do not add any, and do not propose a C# port.
- Python only, against pyRevit's engine.
- Layout stays pyRevit-conventional:
  `SimpleBeamRFT.extension/` → `<Name>.tab/` → `<Name>.panel/` →
  `<Name>.pushbutton/script.py`, with shared code under the extension's
  `lib/` (pyRevit puts that on `sys.path` automatically, which is why
  `rft.core` / `rft.revit` import without path juggling).
- Deployment is `pyrevit extend <path>` or registering the folder in
  pyRevit's extension manager, then reloading — always from a tagged commit.

## Standing rule: no live Revit host

Nothing in this environment can execute Revit API code, so no rebar logic can
be verified by running it. Every API decision in rev 2 §10 rests on
documentation and is flagged unverified.

Consequently, **any ticket touching Revit-API-dependent logic requires a
mock-object simulation write-up** demonstrating the logic is correct before it
can close in review. That write-up is the actual safety net here, not optional
polish.

### Mock fakes must declare unverified API shapes

Mock objects are written to match the API shape the adapter *assumes*. A green
test suite therefore proves the adapter's **logic** is self-consistent — it does
**not** prove the real Revit API has those members, signatures or return types.
When an assumed shape is wrong, the tests pass and the tool still throws on its
first real run.

So: every fake standing in for an API whose shape is not
documentation-confirmed **must carry an inline `SHAPE UNVERIFIED` note** naming
what is assumed and what the documentation suggests instead. Never let a
passing suite be mistaken for API validation. See the header of
`tests/fake_revit_api.py` for the running list.

The load-bearing unknown: if `RebarStyle.StirrupTie` disallows 180° hooks, the
mild-steel hook decision (rev 2 §7.3) must be revisited.
