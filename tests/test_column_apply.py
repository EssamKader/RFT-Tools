# -*- coding: utf-8 -*-
"""#120 -- A3/R23/R25's Apply path, the parts that live in ``script.py``.

``script.py`` imports ``pyrevit``, which is not installed under plain
CPython (see ``tests/fake_revit_api.py``'s header), so its WPF wiring
cannot be executed. This file checks it the way ``test_column_xaml.py``
already checks the rest of the window: as TEXT, matching the exact shape
the ordering rules require -- because the order carries the rulings
(``docs/column/spec-amendments.md``, "The order the placer runs in"), and
a guard that only checks the words are PRESENT, not in what order, would
pass a handler that showed R23's dialog after the transaction had already
run.

Everything ``column_placer`` itself owns (the refuse gates, the one
transaction, R25's rollback guarantee) is proven by
``tests/test_column_placer.py`` against the real module. This file's job
is only the half that module deliberately leaves to the window: showing
the dialog, and reading the two hook pickers separately.
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
    """One method's source text, from its ``def`` line to the next method
    at the same indentation -- the same "read one function's own text"
    convention ``test_column_xaml.py``'s ``_reset_body`` uses, needed here
    because the ORDER of statements is exactly what A3 states as the
    ruling, and an AST walk (as ``_code_of`` does) discards order.
    """
    match = re.search(
        r"    def %s\(.*?\n(.*?)\n    def [a-zA-Z_]" % re.escape(name),
        _script(), re.DOTALL)
    assert match, "no method named %r found in script.py" % name
    return match.group(1)


# --------------------------------------------------------------------- #
# The button exists and is wired


def test_apply_button_is_wired_to_on_apply_click():
    assert "self.apply_place_btn.Click += self.on_apply_click" in _script()


# --------------------------------------------------------------------- #
# A3 steps 2-3: refused before step 4 even reads the host


def test_refuse_if_not_ready_runs_before_existing_elements_is_read():
    body = _method_body("_apply_in_context")
    refuse_at = body.index("column_placer.refuse_if_not_ready(plan)")
    existing_at = body.index("column_placer.existing_elements(")
    assert refuse_at < existing_at, (
        "A3 states steps 2/3 (refuse) before step 4 (find existing "
        "elements) -- refuse_if_not_ready must run first")


# --------------------------------------------------------------------- #
# A3 step 5 / R23: the dialog is shown ONLY when elements of ours exist,
# and it is the LAST thing checked before Apply -- steps 6-10.


def test_the_dialog_is_gated_behind_ours_being_non_empty():
    body = _method_body("_apply_in_context")
    assert re.search(r"\n\s*if ours:\n", body), (
        "R23's dialog must be gated behind 'if ours:' -- shown only when "
        "elements of ours exist; a first placement shows nothing")


def test_cancel_returns_without_reaching_column_placer_apply():
    """The dialog's Cancel path must ``return`` before ``column_placer.
    apply`` is ever reached -- Cancel changes nothing (A3 acceptance)."""
    body = _method_body("_apply_in_context")
    cancel_block = re.search(
        r"if not proceed:\n(.*?)\n\n", body, re.DOTALL)
    assert cancel_block, "no 'if not proceed:' branch found"
    assert "return" in cancel_block.group(1)
    assert "column_placer.apply(" not in cancel_block.group(1)


def test_the_dialog_gate_appears_before_column_placer_apply_is_called():
    body = _method_body("_apply_in_context")
    gate_at = body.index("if ours:")
    apply_at = body.index("column_placer.apply(")
    assert gate_at < apply_at, (
        "R23's dialog (step 5) must be checked before Apply's own steps "
        "6-10; a dialog shown after the transaction already ran would be "
        "asking about a cage that no longer exists")


# --------------------------------------------------------------------- #
# Section 7: outer and inner hook types are read independently


def test_outer_and_inner_hook_types_are_read_from_their_own_combos():
    body = _method_body("on_apply_click")
    assert "self._selected_hook_type_object(self.outer_hook_cb)" in body
    assert "self._selected_hook_type_object(self.inner_hook_cb)" in body


# --------------------------------------------------------------------- #
# R24: foreign rebar, if any, is named in what the engineer is told


def test_a_successful_apply_names_foreign_rebar_when_any_is_left():
    body = _method_body("_apply_in_context")
    assert "result.foreign" in body
    assert "element_id" in body
