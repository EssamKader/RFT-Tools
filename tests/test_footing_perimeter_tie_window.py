# -*- coding: utf-8 -*-
"""Issue #244 -- the parts of the `perimeter_tie` UI wiring that live in
``script.py``.

Mirrors ``tests/test_footing_window.py``'s own convention (text-scraping,
since ``script.py`` imports ``pyrevit`` and cannot be executed under plain
CPython): the actual math and the actual placement call are proven by
``tests/test_footing_plan.py``/``tests/test_footing_revit_perimeter_tie.py``/
``tests/test_footing_revit_batch.py`` against the real modules; this file's
job is only the half the adapter deliberately leaves to the window --
reading the new controls, threading them into ``FootingInputs``/
``BatchInputs``, and placing `perimeter_tie` inside the SAME transaction as
everything else.
"""

import io
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FOOTING_PUSHBUTTON_DIR = os.path.join(
    REPO_ROOT, "IsolatedFooting.extension", "RFT-Tools.tab",
    "Footings.panel", "IsolatedFootingRFT.pushbutton")
SCRIPT_PATH = os.path.join(FOOTING_PUSHBUTTON_DIR, "script.py")
XAML_PATH = os.path.join(FOOTING_PUSHBUTTON_DIR, "FootingWindow.xaml")


def _script():
    return io.open(SCRIPT_PATH, encoding="utf-8").read()


def _xaml():
    return io.open(XAML_PATH, encoding="utf-8").read()


def _method_body(name):
    match = re.search(
        r"    def %s\(.*?\n(.*?)\n    def [a-zA-Z_]" % re.escape(name),
        _script(), re.DOTALL)
    assert match, "no method named %r found in script.py" % name
    return match.group(1)


# --------------------------------------------------------------------- #
# The controls exist in the markup script.py refers to


def test_perimeter_tie_bar_type_combo_exists_in_the_xaml():
    assert 'x:Name="perimeter_tie_bar_type_cb"' in _xaml()


def test_perimeter_tie_hook_type_combo_exists_in_the_xaml():
    assert 'x:Name="perimeter_tie_hook_type_cb"' in _xaml()


def test_perimeter_tie_spacing_and_quantity_textboxes_exist_in_the_xaml():
    assert 'x:Name="perimeter_tie_spacing_tb"' in _xaml()
    assert 'x:Name="perimeter_tie_quantity_tb"' in _xaml()


def test_perimeter_tie_lap_and_bar_length_textboxes_exist_in_the_xaml():
    assert 'x:Name="perimeter_tie_lap_tb"' in _xaml()
    assert 'x:Name="perimeter_tie_first_bar_length_tb"' in _xaml()
    assert 'x:Name="perimeter_tie_second_bar_length_tb"' in _xaml()


def test_the_window_no_longer_claims_perimeter_tie_is_unwired():
    """This ticket wires perimeter_tie -- the old #205-era note claiming
    it is not yet placed must not still be shown to the engineer."""
    assert "not yet wired to placement" not in _xaml()


# --------------------------------------------------------------------- #
# Reading the combos -> the SAME FootingInputs/BatchInputs values


def test_perimeter_tie_bar_type_combo_is_populated_alongside_every_other():
    body = _method_body("_populate_bar_type_combos")
    assert "self.perimeter_tie_bar_type_cb" in body
    assert "self.perimeter_tie_hook_type_cb" in body


def test_on_build_report_click_gates_on_perimeter_tie_bar_type_selection():
    body = _method_body("on_build_report_click")
    assert "perimeter_tie_bar_type = self._selected_bar_type_object(" in body
    assert "perimeter_tie_hook_type = self._selected_hook_type_object(" in body
    assert "if (perimeter_tie_bar_type is not None" in body


def test_on_build_report_click_threads_perimeter_tie_into_footing_inputs():
    body = _method_body("on_build_report_click")
    # Two FootingInputs(...)/BatchInputs(...) constructions live in this
    # method; both must thread the SAME perimeter_tie fields, never only
    # one of the two (which would silently revert the OTHER path to
    # no perimeter_tie at all).
    assert body.count("perimeter_tie_dia_mm=perimeter_tie_dia_mm") == 1
    assert body.count(
        "perimeter_tie_bar_type=perimeter_tie_bar_type") == 1
    assert body.count(
        "perimeter_tie_spacing_mm=perimeter_tie_spacing_mm") == 2
    assert body.count(
        "perimeter_tie_quantity=perimeter_tie_quantity") == 2


def test_on_build_report_click_shows_the_perimeter_tie_section_only_when_present():
    body = _method_body("on_build_report_click")
    assert "if plan.perimeter_tie is not None:" in body
    assert "footing_report.perimeter_tie_section(plan)" in body


# --------------------------------------------------------------------- #
# Placement: perimeter_tie is placed in the SAME transaction, single-
# footing path


def test_place_perimeter_ties_is_imported():
    assert "place_perimeter_ties" in _script()


def test_single_footing_placement_places_perimeter_ties_before_commit():
    """This repo's hard transaction rule: a module that creates elements
    does not open its own transaction, and the whole footing is ONE
    transaction so a failure leaves the model exactly as it was. The
    perimeter_tie placement call must therefore sit inside the SAME
    try/except block as the bottom mesh/dowels, BEFORE
    ``transaction.Commit()`` -- never a second transaction, never after
    commit.
    """
    body = _method_body("_place_single_in_context")
    commit_at = body.index("transaction.Commit()")
    perimeter_tie_call_at = body.index("place_perimeter_ties(")
    assert perimeter_tie_call_at < commit_at, (
        "perimeter_tie must be placed BEFORE the single transaction commits")


def test_single_footing_placement_gates_on_the_plans_own_perimeter_tie():
    body = _method_body("_place_single_in_context")
    assert "if self.plan.perimeter_tie is not None:" in body


def test_single_footing_placement_gates_a_split_loop_on_split_bars():
    """R14: a split loop must not be placed until both R5 bar lengths are
    typed (``split_bars is not None``) -- a required split with no bar
    lengths yet must place nothing, not a wrong/guessed shape."""
    body = _method_body("_place_single_in_context")
    assert "self.plan.perimeter_tie.split_bars is not None" in body


def test_apply_batch_call_threads_perimeter_tie_bar_and_hook_type():
    body = _method_body("_place_batch_in_context")
    assert "perimeter_tie_bar_type=" in body
    assert "perimeter_tie_hook_type=" in body
