# Project Context — RFT-Tools

## Which context applies to the work in front of you

This repo holds **more than one element**. This file carries **only** the
rules that are true of every element. Anything that names beams, spans,
`h > 700`, anchorage or the three-zone stirrup rule is the **beam tool's** and
lives in the beam tool's own file — see the table.

| Working on | Read |
|---|---|
| **Any element** | this file's *repo-wide* rules (below), plus [`REUSE_GUIDELINES.md`](REUSE_GUIDELINES.md) |
| **Beam** | [`SimpleBeamRFT.extension/CONTEXT.md`](SimpleBeamRFT.extension/CONTEXT.md) + [`specs/beam-rft-detailing.md`](specs/beam-rft-detailing.md) |
| **Column** | [`ColumnRFT.extension/CONTEXT.md`](ColumnRFT.extension/CONTEXT.md) + [`specs/column-rft-detailing.md`](specs/column-rft-detailing.md) |
| **Shared `RFT.lib`** | [`docs/column/reuse-audit.md`](docs/column/reuse-audit.md) — what is genuinely element-agnostic, and what only looks it |
| **Adding a new element** | [`docs/reuse-for-new-elements.md`](docs/reuse-for-new-elements.md) + [`docs/token-efficient-expansion.md`](docs/token-efficient-expansion.md) |

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

> **Note on the "no live Revit host" rule:** that constraint is the **beam
> tool's** development reality and is still true of it — see
> [`SimpleBeamRFT.extension/CONTEXT.md`](SimpleBeamRFT.extension/CONTEXT.md).
> The **column** tool has a live Revit host reachable over MCP — see
> [`ColumnRFT.extension/CONTEXT.md`](ColumnRFT.extension/CONTEXT.md). The
> verification discipline does not relax either way; only the reason for
> guessing goes away.
