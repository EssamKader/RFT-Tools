# -*- coding: utf-8 -*-
"""Issue #233 -- the parts of the top-mesh UI wiring that live in
``script.py``.

``script.py`` imports ``pyrevit``, which is not importable under plain
CPython (see ``tests/fake_revit_api.py``'s header), so its WPF wiring
cannot be executed. This file checks it as TEXT, the same convention
``tests/test_column_batch_window.py`` already uses for the column tool's
own batch-path wiring -- everything ``rft.core.footing_plan``/``rft.revit.
footing_mesh``/``footing_batch`` themselves own (the actual math, the
actual placement call) is proven by ``tests/test_footing_plan.py``/
``tests/test_footing_revit_mesh.py``/``tests/test_footing_revit_batch.py``
against the real modules; this file's job is only the half the adapter
deliberately leaves to the window: reading the new TOP+BTM toggle off its
own combo, threading it into ``FootingInputs``/``BatchInputs``, and
placing the top mat inside the SAME transaction as the bottom mesh/dowels
(this repo's hard "one transaction, all-or-nothing" rule).
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


def test_top_reinforcement_combo_exists_in_the_xaml():
    assert 'x:Name="top_reinforcement_cb"' in _xaml()


def test_top_mat_shape_combo_exists_in_the_xaml():
    assert 'x:Name="top_mat_shape_cb"' in _xaml()


# --------------------------------------------------------------------- #
# Reading the combo -> the SAME FootingInputs/BatchInputs values


def test_selected_top_reinforcement_maps_index_zero_to_btm_only():
    body = _method_body("_selected_top_reinforcement")
    assert "TOP_REINFORCEMENT_BTM_ONLY" in body
    assert "TOP_REINFORCEMENT_TOP_AND_BTM" in body
    assert "top_reinforcement_cb.SelectedIndex" in body


def test_selected_top_mat_shape_mode_mirrors_the_bottom_mats_own_mapping():
    body = _method_body("_selected_top_mat_shape_mode")
    assert "top_mat_shape_cb.SelectedIndex" in body
    assert "MAT_SHAPE_U" in body
    assert "MAT_SHAPE_L_ALTERNATING" in body


def test_on_build_report_click_threads_top_reinforcement_into_footing_inputs():
    body = _method_body("on_build_report_click")
    # Two FootingInputs(...)/BatchInputs(...) constructions live in this
    # method; both must thread the SAME two selector calls, never only one
    # of the two (which would silently revert the OTHER path to BTM-only).
    assert body.count("top_reinforcement=self._selected_top_reinforcement()") == 2
    assert body.count("top_mat_shape_mode=self._selected_top_mat_shape_mode()") == 2


def test_on_build_report_click_shows_the_top_mesh_section_only_when_present():
    body = _method_body("on_build_report_click")
    assert "if plan.top_mesh is not None:" in body
    assert "footing_report.top_mesh_section(plan)" in body


# --------------------------------------------------------------------- #
# Placement: the top mat is placed in the SAME transaction, single-footing
# path


def test_place_straight_top_mesh_is_imported():
    assert "place_straight_top_mesh" in _script()


def test_single_footing_placement_places_the_top_mat_before_commit():
    """This repo's hard transaction rule: a module that creates elements
    does not open its own transaction, and the whole footing (mesh +
    dowels + top mesh) is ONE transaction so a failure leaves the model
    exactly as it was. The top-mat placement call must therefore sit
    inside the SAME try/except block as the bottom mesh/dowels, BEFORE
    ``transaction.Commit()`` -- never a second transaction, never after
    commit.
    """
    body = _method_body("_place_single_in_context")
    commit_at = body.index("transaction.Commit()")
    top_mesh_call_at = body.index("place_straight_top_mesh(")
    assert top_mesh_call_at < commit_at, (
        "the top mat must be placed BEFORE the single transaction commits")


def test_single_footing_placement_gates_the_top_mat_on_plan_top_mesh():
    body = _method_body("_place_single_in_context")
    assert "if self.plan.top_mesh is not None:" in body
