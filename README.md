# RFT-Tools

A monorepo of **pyRevit** tools for automated reinforcement (RFT) detailing in
Revit, sharing one library. Each structural element is its own extension, its
own spec, its own docs and its own release tag — they never reach into each
other.

These tools perform **pure detailing logic** (bar geometry, placement,
quantities). They do **no** flexural or shear design calculation: bar sizes,
counts and base dimensions are user inputs.

## Elements

| Element | Extension | Spec | Status |
|---|---|---|---|
| **Beam** — single-span, rectangular | `SimpleBeamRFT.extension/` | [`specs/beam-rft-detailing.md`](specs/beam-rft-detailing.md) | Shipping · `v0.3.1-rc3` |
| **Column** — one floor-to-floor segment, rectangular | `ColumnRFT.extension/` | [`specs/column-rft-detailing.md`](specs/column-rft-detailing.md) | Scoping · spec LOCKED, button is a placeholder |

**Beam scope:** development length & end anchorage, 3-zone stirrup distribution,
main bar layer offsets, crack/skin reinforcement for deep beams (h > 700 mm),
bar spacing rules, stirrup closure/hook types.
Source document: [`technical-material/beam/beam_rebar_detailing_spec_v2.docx`](technical-material/beam/beam_rebar_detailing_spec_v2.docx)
(**revision 2 is the source of truth**).

**Column scope:** one floor-to-floor segment — longitudinal bars as a single
perimeter layout, confinement zone `L₀` and spacing `S₀`, middle-zone spacing,
horizontal restraint tiers, subset-defined overlapping closed ties, per-level
hook-corner alternation, and the top-of-support splice. Foundation dowels,
multi-storey stacks and non-rectangular sections are **out of scope by
decision**.

## Repository layout

Every element has the **same four homes**, so where a new file belongs is never
a judgement call:

```
RFT-Tools/
├── RFT.lib/                          SHARED library — a pyRevit *library
│   └── rft/                          extension*: the ".lib" suffix is what
│       ├── core/                     puts it on every extension's sys.path
│       ├── revit/                    (see docs/reuse-for-new-elements.md §1)
│       └── ui/
│
├── SimpleBeamRFT.extension/          ── ELEMENT: BEAM ──────────────────
│   └── RFT-Tools.tab/                   tab TITLE is shared; pyRevit merges
│       └── Beams.panel/                 tabs by title across extensions
│           └── Simple Beam.pushbutton/
│
├── ColumnRFT.extension/              ── ELEMENT: COLUMN ────────────────
│   ├── CONTEXT.md                       standing rules for THIS tool
│   └── RFT-Tools.tab/
│       └── Columns.panel/
│           └── ColumnRFT.pushbutton/
│
├── specs/                            WHAT each tool must do
│   ├── beam-rft-detailing.md
│   ├── column-rft-detailing.md
│   └── ui-single-window.md
│
├── docs/
│   ├── beam/                         amendments, verification, research
│   ├── column/                       amendments, verification, reuse audit
│   ├── deployment.md                 shared
│   └── reuse-for-new-elements.md     shared — read before adding an element
│
├── technical-material/               SOURCE documents (.docx / .pdf)
│   ├── beam/
│   └── column/
│
├── tests/                            pytest — pure-Python core only
├── tools/prove_guards.py             the mutation prover
│
├── CONTEXT.md                        repo-wide standing rules
├── REUSE_GUIDELINES.md               architectural standards, all elements
└── CHANGELOG.md
```

### The rule the layout encodes

> **The tab names the domain, the panel names the element, the button names the
> case.**

Both extensions declare the tab title `RFT-Tools`, so they land on one ribbon
tab while staying separately installable and separately versioned. A future
element (walls, footings) adds a *fourth* set of the same four homes and changes
nothing that already exists.

## Versioning

Tags are **per tool**, over the shared library:

- `beam/vX.Y.Z`
- `column/vX.Y.Z`

A monorepo tag is a commit, so a tool's tag pins the exact `RFT.lib` state it
was verified against.

> `master` means **the code exists**. A tag means **it was verified on a live
> Revit host**. Only a tagged commit is ever loaded into Revit.

## Working on this repo

1. Read [`CONTEXT.md`](CONTEXT.md) and [`REUSE_GUIDELINES.md`](REUSE_GUIDELINES.md).
2. Read the element's own spec and, where present, its `CONTEXT.md`.
3. Before adding a new element, read
   [`docs/reuse-for-new-elements.md`](docs/reuse-for-new-elements.md).
4. Issues are labelled by element — `element:beam`, `element:column`,
   `element:shared`. **A ticket never mixes two elements.**

Local `.rvt` / `.rfa` test fixtures are gitignored on purpose: the repo records
what was *measured* against them (`docs/*/verification/`), not the models.
