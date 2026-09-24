# -*- coding: utf-8 -*-
"""Isolated Footing RFT's own per-project persistence (#205).

Mirrors ``rft.ui.persistence``'s SHAPE exactly (``to_store``/``from_store``,
the ``script.store_data(SETTINGS_SLOT, ...)`` call pattern) -- but is NOT a
fork of that module's own field CONSTANTS, which are hardcoded to
SimpleBeamRFT's own TextBox/ComboBox names. This tool has a different
field set entirely, so a new module with the same shape is the correct
reuse, per this ticket's own instruction ("do not fork [the UI
infrastructure] per-element unless a genuine footing-specific gap is
found").

WHAT IS NOT HERE, AND WHY (same reasoning ``rft.ui.persistence`` states
for the beam tool):

- **The picked footing/column, and every live-read geometry value**
  (``a_mm``/``b_mm``/``footing_thickness_mm``/covers, ``Cw_mm``/``Cd_mm``/
  ``Ccover_mm``). R7/R8 (docs/footing/spec-amendments.md) already made
  these live reads, never typed -- there is nothing here to remember,
  and remembering the LAST footing's numbers in front of a NEW one would
  be exactly the "plausible but wrong" failure ``rft.ui.persistence``'s
  own docstring warns about for a beam's `L`/`b`/`h`.
- **``dowel_count_b_face``/``dowel_count_h_face``** are NOT excluded --
  unlike the beam tool's bar/layer counts (A44's "blank ships blank so a
  restore cannot silently request a section"), there is no footing-tool
  derivation rule that treats a non-blank count as "the array is
  requested" versus "not requested" -- the array is always attempted once
  every OTHER gating field (live column section, dowel bar/tie types) is
  present, so remembering the count carries no such risk here.

STORE PLAIN DATA ONLY -- ``script.store_data`` is pickle; this module
stores nothing but dicts of strings, matching ``rft.ui.persistence``'s
own reasoning verbatim.

Python 2/3 compatible: IronPython 2.7 is the runtime that loads this in
production.
"""

# The pyRevit data slot. Named for the tool, not the ticket.
SETTINGS_SLOT = "IsolatedFootingRFT_inputs"

# Bumped whenever the field set or a stored value's MEANING changes.
# #232 (R11): bumped to 2 -- mesh_bar_x_spacing_tb/mesh_bar_y_spacing_tb
# joined TEXT_FIELDS below, per this module's own rule.
# #242: bumped to 3 -- dowel_tie_spacing_tb joined TEXT_FIELDS and
# dowel_tie_hook_type joined TYPE_FIELDS below.
# #244 (R14): bumped to 4 -- perimeter_tie_spacing_tb/perimeter_tie_
# quantity_tb/perimeter_tie_lap_tb/perimeter_tie_first_bar_length_tb/
# perimeter_tie_second_bar_length_tb joined TEXT_FIELDS and
# perimeter_tie_bar_type joined TYPE_FIELDS below.
SETTINGS_VERSION = 4

# Free-text inputs (TextBox contents, stored verbatim as typed) -- the
# window's own parsers (rft.ui.inputs) already turn text into values and
# already say which field is unreadable and why; storing a parsed number
# would give that judgement a second opinion.
TEXT_FIELDS = (
    "x_offset_tb",
    "y_offset_tb",
    "ld_multiplier_tb",
    "dowel_ld_multiplier_tb",
    "dowel_count_b_face_tb",
    "dowel_count_h_face_tb",
    "mesh_bar_x_spacing_tb",
    "mesh_bar_y_spacing_tb",
    "dowel_tie_spacing_tb",
    "perimeter_tie_spacing_tb",
    "perimeter_tie_quantity_tb",
    "perimeter_tie_lap_tb",
    "perimeter_tie_first_bar_length_tb",
    "perimeter_tie_second_bar_length_tb",
)

# No plain-choice ComboBoxes in this window (every picker is a Revit
# element selection -- see TYPE_FIELDS) -- kept as an explicit empty tuple,
# matching rft.ui.persistence's own three-list shape, rather than omitted,
# so a reader does not have to ask "was this forgotten?".
CHOICE_FIELDS = ()

# Revit element selections, stored by UniqueId -- survives reopening the
# model; an ElementId or a name would not (rft.ui.persistence's own
# reasoning, unchanged).
TYPE_FIELDS = (
    "mesh_bar_x_type",
    "mesh_bar_y_type",
    "dowel_bar_type",
    "dowel_tie_bar_type",
    "dowel_tie_hook_type",
    "perimeter_tie_bar_type",
)

# Footing/column-scoped, read from the model every run, never remembered
# -- listed so the exclusion is testable instead of implied, mirroring
# rft.ui.persistence.BEAM_SCOPED_FIELDS.
FOOTING_SCOPED_FIELDS = (
    "a_mm", "b_mm", "footing_thickness_mm", "cover_mm",
    "bottom_cover_mm", "top_cover_mm", "Cw_mm", "Cd_mm", "Ccover_mm",
)


def to_store(text_values, type_unique_ids):
    """Build the dict handed to ``script.store_data``.

    Only known keys survive, so a caller cannot widen what is persisted
    by passing extra entries.
    """
    return {
        "version": SETTINGS_VERSION,
        "text": _kept(text_values, TEXT_FIELDS),
        "types": _kept(type_unique_ids, TYPE_FIELDS),
    }


def from_store(raw):
    """Validate what came back from ``script.load_data``.

    Returns ``(text, types)`` -- two dicts, empty when there is nothing
    usable. Never raises: this runs while the window is opening, and a
    settings file is not worth failing to open a tool over.
    """
    if not isinstance(raw, dict):
        return {}, {}
    if raw.get("version") != SETTINGS_VERSION:
        return {}, {}
    return (
        _kept(raw.get("text"), TEXT_FIELDS),
        _kept(raw.get("types"), TYPE_FIELDS),
    )


def _kept(values, allowed):
    """The subset of ``values`` whose keys are allowed and whose values
    are non-empty strings."""
    if not isinstance(values, dict):
        return {}
    kept = {}
    for key in allowed:
        value = values.get(key)
        if isinstance(value, str) and value.strip():
            kept[key] = value
        else:
            # IronPython 2.7: a stored value may come back as `unicode`
            # rather than `str`, and both are text.
            try:
                is_text = isinstance(value, unicode)  # noqa: F821
            except NameError:
                is_text = False
            if is_text and value.strip():
                kept[key] = value
    return kept


def persisted_field_names():
    """Every field this module will store, for tests."""
    return tuple(TEXT_FIELDS) + tuple(CHOICE_FIELDS) + tuple(TYPE_FIELDS)
