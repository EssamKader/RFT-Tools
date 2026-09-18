# -*- coding: utf-8 -*-
"""Issue #153 -- the parts of the batch path that live in ``script.py``.

``script.py`` imports ``pyrevit``, which is not importable under plain
CPython (see ``tests/fake_revit_api.py``'s header), so its WPF wiring
cannot be executed. This file checks it as TEXT, the same convention
``test_column_apply.py`` already uses for the single-column Apply path --
everything ``rft.revit.column_batch`` itself owns (the refuse gates, the
one transaction, R25 extended) is proven by ``tests/test_column_batch.py``
against the real module; this file's job is only the half the adapter
deliberately leaves to the window: building the shared inputs from the
tabs, and showing R33's report whether or not the batch succeeds.
"""

import io
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
COLUMN_PUSHBUTTON_DIR = os.path.join(
    REPO_ROOT, "ColumnRFT.extension", "RFT-Tools.tab",
    "Columns.panel", "ColumnRFT.pushbutton")
SCRIPT_PATH = os.path.join(COLUMN_PUSHBUTTON_DIR, "script.py")


def _script():
    return io.open(SCRIPT_PATH, encoding="utf-8").read()


def _method_body(name):
    match = re.search(
        r"    def %s\(.*?\n(.*?)\n    def [a-zA-Z_]" % re.escape(name),
        _script(), re.DOTALL)
    assert match, "no method named %r found in script.py" % name
    return match.group(1)


# --------------------------------------------------------------------- #
# The button exists and is wired


def test_apply_batch_button_is_wired_to_on_apply_batch_click():
    assert "self.apply_batch_btn.Click += self.on_apply_batch_click" in _script()


# --------------------------------------------------------------------- #
# R33: the report is shown whether or not the transaction succeeds


def test_the_batch_report_is_rendered_before_apply_batch_is_called():
    """R33 is only safe if the report is readable EVEN WHEN the run fails
    or refuses -- so it must be built and shown before
    ``column_batch.apply_batch`` runs, not after a success path only.
    """
    body = _method_body("_apply_batch_in_context")
    report_at = body.index("self.report_tb.Text = report")
    apply_at = body.index("column_batch.apply_batch(")
    assert report_at < apply_at, (
        "the batch report must be shown BEFORE apply_batch runs, so a "
        "refusal or a rolled-back failure still leaves the groups and "
        "exclusions visible")


def test_the_batch_report_is_built_from_groups_and_exclusions():
    body = _method_body("_apply_batch_in_context")
    assert "batch_group_section(batch_plan.groups)" in body
    assert "batch_exclusion_section(batch_plan.exclusions)" in body


def test_a_batch_refusal_does_not_swallow_the_report():
    """The refusal branch must return AFTER the report was already
    written, never replace it with only a status line."""
    body = _method_body("_apply_batch_in_context")
    refusal_branch = re.search(
        r"except column_placer\.ColumnPlacementError as ex:\n(.*?)\n\n",
        body, re.DOTALL)
    assert refusal_branch, "no ColumnPlacementError branch found"
    assert "self.report_tb.Text" not in refusal_branch.group(1), (
        "the refusal branch must not overwrite the report already shown")


# --------------------------------------------------------------------- #
# Shared inputs are read the SAME way the single-column plan reads them


def test_batch_inputs_reads_the_same_fields_the_single_column_plan_used():
    body = _method_body("_batch_inputs")
    for field in ("self.longitudinal", "self.splice",
                  "self.bars.bar_diameter_mm", "self.bars.tie_diameter_mm",
                  "self.tie_subsets_tb.Text"):
        assert field in body, "%r not read by _batch_inputs" % field


# --------------------------------------------------------------------- #
# R23 per column (spec Section 6): counted, shown, and cancellable


def test_existing_reinforcement_is_read_BEFORE_apply_batch():
    """Spec Section 6: the count R23 shows and the set apply_batch deletes
    must be one read, taken outside the transaction -- the same shape the
    single-column path uses when it passes ``ours``/``foreign`` in."""
    body = _method_body("_apply_batch_in_context")
    read_at = body.index("column_batch.read_existing(")
    apply_at = body.index("column_batch.apply_batch(")
    assert read_at < apply_at


def test_the_batch_confirmation_is_shown_before_apply_batch_and_can_cancel():
    """R23 for a batch: a table, then a confirmation, then placement --
    and Cancel must return before ``apply_batch`` is ever called, with
    nothing touched."""
    body = _method_body("_apply_batch_in_context")
    alert_at = body.index("title=\"Replace existing reinforcement in")
    apply_at = body.index("column_batch.apply_batch(")
    assert alert_at < apply_at, (
        "the replacement confirmation must be shown before any placement")
    cancel = re.search(r"if not proceed:\n(.*?)\n\n", body, re.DOTALL)
    assert cancel, "no cancel branch found"
    assert "return" in cancel.group(1)
    assert "Cancelled" in cancel.group(1)


def test_the_batch_report_carries_the_replacement_table():
    body = _method_body("_apply_batch_in_context")
    assert "batch_replacement_section(existing)" in body


def test_the_batch_status_names_foreign_rebar_it_left_alone():
    """R24 in the batch too -- foreign rebar is reported, never silent."""
    body = _method_body("_apply_batch_in_context")
    assert "foreign_ids" in body
    assert "left untouched" in body
