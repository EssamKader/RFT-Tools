# -*- coding: utf-8 -*-
"""#205 -- what the footing window remembers between footings.

Mirrors tests/test_ui_persistence.py's own round-trip/plain-data/known-
keys tests, adapted to this tool's own (simpler) field set: no
request-constituting exclusion rule applies here (see ``rft.ui.
footing_persistence``'s own docstring for why -- unlike the beam tool,
nothing here decides whether a section is "requested").
"""

from rft.ui.footing_persistence import (
    CHOICE_FIELDS,
    FOOTING_SCOPED_FIELDS,
    SETTINGS_SLOT,
    SETTINGS_VERSION,
    TEXT_FIELDS,
    TYPE_FIELDS,
    from_store,
    persisted_field_names,
    to_store,
)

FULL_TEXT = {
    "x_offset_tb": "300",
    "y_offset_tb": "150",
    "ld_multiplier_tb": "40",
    "dowel_ld_multiplier_tb": "40",
    "dowel_count_b_face_tb": "3",
    "dowel_count_h_face_tb": "4",
}
FULL_TYPES = {
    "mesh_bar_x_type": "8a1f0c22-0000-0000-0000-000000000001",
    "mesh_bar_y_type": "8a1f0c22-0000-0000-0000-000000000002",
    "dowel_bar_type": "8a1f0c22-0000-0000-0000-000000000003",
    "dowel_tie_bar_type": "8a1f0c22-0000-0000-0000-000000000004",
}


def test_a_full_round_trip_returns_exactly_what_went_in():
    stored = to_store(FULL_TEXT, FULL_TYPES)
    text, types = from_store(stored)
    assert text == FULL_TEXT
    assert types == FULL_TYPES


def test_the_stored_blob_is_plain_data_only():
    """pyRevit's store_data is pickle -- storing nothing but dicts of
    strings means the blob cannot fail to unpickle because a module was
    renamed (the beam tool's own rc3 lesson, reused unchanged here)."""
    stored = to_store(FULL_TEXT, FULL_TYPES)

    def _plain(value):
        if isinstance(value, dict):
            return all(isinstance(k, str) and _plain(v)
                       for k, v in value.items())
        return isinstance(value, (str, int))

    assert _plain(stored), stored
    assert stored["version"] == SETTINGS_VERSION


def test_only_known_keys_are_stored():
    stored = to_store(
        dict(FULL_TEXT, unexpected_tb="should not survive"),
        dict(FULL_TYPES, unexpected_type="should not survive"))
    assert "unexpected_tb" not in stored["text"]
    assert "unexpected_type" not in stored["types"]


def test_a_blank_value_is_dropped_not_stored_as_empty_string():
    stored = to_store(dict(FULL_TEXT, x_offset_tb="   "), FULL_TYPES)
    assert "x_offset_tb" not in stored["text"]


def test_from_store_ignores_a_non_dict_payload():
    assert from_store(None) == ({}, {})
    assert from_store("not a dict") == ({}, {})
    assert from_store([1, 2, 3]) == ({}, {})


def test_from_store_ignores_a_wrong_version():
    stored = to_store(FULL_TEXT, FULL_TYPES)
    stored["version"] = SETTINGS_VERSION + 1
    assert from_store(stored) == ({}, {})


def test_footing_scoped_fields_are_never_persisted():
    """R7/R8: the footing's own geometry and the column's own section/
    cover are read live, never typed -- there is nothing to remember, and
    remembering the LAST footing's numbers in front of a NEW one would be
    the same "plausible but wrong" failure rft.ui.persistence's own
    docstring warns about for a beam's L/b/h."""
    persisted = set(persisted_field_names())
    leaked = sorted(set(FOOTING_SCOPED_FIELDS) & persisted)
    assert not leaked, "footing/column-scoped fields must not be stored: %s" % leaked


def test_no_choice_fields_declared():
    """Every picker in this window is a Revit element selection (a
    TYPE_FIELDS entry), not a plain-choice ComboBox -- unlike the beam
    tool, which has three. Kept as an explicit empty tuple so a reader
    does not have to ask whether it was forgotten."""
    assert CHOICE_FIELDS == ()


def test_the_settings_slot_is_named_for_the_tool():
    assert SETTINGS_SLOT == "IsolatedFootingRFT_inputs"


def test_persisted_field_names_covers_every_declared_field():
    assert set(persisted_field_names()) == (
        set(TEXT_FIELDS) | set(CHOICE_FIELDS) | set(TYPE_FIELDS))
