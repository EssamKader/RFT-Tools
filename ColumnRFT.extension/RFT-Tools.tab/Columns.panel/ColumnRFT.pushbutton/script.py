# -*- coding: utf-8 -*-
"""Column RFT -- PLACEHOLDER. Deliberately does nothing.

This button exists so the extension's folder structure, ribbon placement
and bundle settings are real and loadable before any detailing logic is
written. It is NOT a stub to be "filled in later" by guesswork: the column
spec (`specs/column-rft-detailing.md`) is LOCKED and authorises exactly one
next step, and several of its decisions are still open tickets.

Per `REUSE_GUIDELINES.md` §3 and `ColumnRFT.extension/CONTEXT.md`, this
refuses loudly rather than doing something approximate.

Open decisions blocking implementation (see the issue tracker):
  - tie topology, §6.2: auto-derived from §6.1's tiers vs a template picker
  - out-of-scope behaviour: what the tool does with a C1/C2/C3 column
  - tie bar grade vs the §7 135 degree hook default
  - hook-corner alternation, §6.3: diagonal (180 deg) vs adjacent corner

Already settled and verified on a live host, for whoever implements this:
  - `b` lies along `HandOrientation`, `h` along `FacingOrientation`;
    dimensions come from the type parameters, NEVER from the bounding box
    (docs/column/verification/issue-69-column-tracer-bullet.md)
  - clear height comes from a support-FACE search, never from
    `INSTANCE_LENGTH_PARAM` -- they differ by the slab thickness
  - the vertical search may legitimately find NOTHING at the base
  - per-level hook rotation is ONE rebar set plus `MoveBarInSet`, and any
    layout change silently scrambles it unless the whole rotation map is
    re-applied (docs/column/verification/issue-70-hook-corner-alternation.md)
"""

from pyrevit import forms

forms.alert(
    "Column RFT is not implemented yet.\n\n"
    "This button is a placeholder. The column detailing spec is locked, "
    "but several of its decisions are still open tickets -- placing rebar "
    "now would mean guessing them.\n\n"
    "See specs/column-rft-detailing.md and the open issues labelled "
    "element:column.",
    title="Column RFT -- not implemented",
    warn_icon=True,
)
