# -*- coding: utf-8 -*-
"""#176 -- R43's second window, as far as source can be checked.

``script.py`` imports ``pyrevit``, which is not importable under plain
CPython, so its WPF wiring cannot be executed here. This file checks it as
TEXT, the convention ``test_column_batch_window.py`` already uses. What
the window DELEGATES is executable and is tested against the real modules:
the run-to-axis mapping and the four terminations in
``tests/test_column_plan.py``, the bend radius in
``tests/test_bar_type_bend_radius.py``, the slab read in
``tests/test_column_roof_slab.py``.

That split is the design: this window states inputs and composes nothing,
so there is very little here that only source can see -- and the little
there is, is exactly the wiring that has failed silently on this project
twice.
"""

import io
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SCRIPT_PATH = os.path.join(
    REPO_ROOT, "ColumnRFT.extension", "RFT-Tools.tab",
    "Columns.panel", "ColumnRFT.pushbutton", "script.py")


def _script():
    return io.open(SCRIPT_PATH, encoding="utf-8").read()


def _class_source(name):
    script = _script()
    start = script.index("class %s(" % name)
    rest = script[start:]
    end = rest.find("\nclass ", 1)
    return rest if end == -1 else rest[:end]


def _method_body(class_name, method_name):
    match = re.search(
        r"    def %s\(.*?\n(.*?)(?=\n    def |\Z)" % re.escape(method_name),
        _class_source(class_name), re.DOTALL)
    assert match, "no %s.%s" % (class_name, method_name)
    return match.group(1)


# --------------------------------------------------------------------- #
# R36: declared, never detected


def test_the_top_floor_box_opens_the_second_window():
    assert "self.top_floor_cb.Checked += self.on_top_floor_checked" in _script()
    assert ("self.top_floor_cb.Unchecked += self.on_top_floor_unchecked"
            in _script())


def test_a_top_floor_column_cannot_be_declared_before_one_is_picked():
    """The inputs are read from the floor above THIS column, so the box
    means nothing until there is a column."""
    body = _method_body("ColumnWindow", "on_top_floor_checked")
    assert "if self.column is None:" in body
    assert "self.top_floor_cb.IsChecked = False" in body


def test_the_second_window_is_MODELESS_like_the_first():
    """A modal second window would disable Revit, and the slab read runs
    through an ExternalEvent that needs Revit alive to service it."""
    body = _method_body("ColumnWindow", "on_top_floor_checked")
    assert ".show()" in body
    # A CALL, not the word: both classes carry comments explaining why
    # modal is wrong, and a substring test flags its own explanation --
    # the trap `test_column_xaml.py` already documents for the main
    # window.
    for class_name in ("ColumnWindow", "RoofWindow"):
        assert not re.findall(r"\.ShowDialog\s*\(",
                              _class_source(class_name)), (
            "%s must never be shown modally" % class_name)


# --------------------------------------------------------------------- #
# R43: unticking DROPS the inputs


def test_unticking_the_box_drops_the_termination_and_closes_the_window():
    """R43's own words. A parked termination would be carried into the
    next plan without appearing in the window that states it, and section
    4 would report a bend nobody asked for."""
    body = _method_body("ColumnWindow", "on_top_floor_unchecked")
    assert "self.roof_termination = None" in body
    assert ".Close()" in body


def test_a_re_pick_unticks_the_top_floor_box_and_drops_its_inputs():
    """A new column is a new slab. Carrying the previous column's
    termination would be the worst kind of wrong here: every other number
    on screen would belong to the new column."""
    body = _method_body("ColumnWindow", "_reset_column_state")
    assert "self.roof_termination = None" in body
    assert "self.top_floor_cb.IsChecked = False" in body


def test_the_window_closes_by_UNTICKING_rather_than_closing_itself():
    """One path out, not two: Cancel asks the owner to untick, and the
    owner's handler does the dropping and the closing. A window that
    closed itself would leave the box ticked with nothing behind it."""
    body = _method_body("RoofWindow", "on_cancel_click")
    assert "self.owner.top_floor_cb.IsChecked = False" in body
    assert ".Close()" not in body


# --------------------------------------------------------------------- #
# The refusals, and that they NAME what is missing


def test_apply_is_REFUSED_while_the_top_floor_inputs_are_missing():
    """A ticked box with nothing handed back means the engineer asked for
    a termination the tool does not have. Building the plan anyway laps
    the bars into a storey that is not there -- silently, because every
    other number would be right."""
    body = _method_body("ColumnWindow", "on_apply_ties_click")
    assert ("if self.top_floor_cb.IsChecked and self.roof_termination is None:"
            in body)
    refusal = body[body.index("self.top_floor_cb.IsChecked"):]
    assert "read the slab" in refusal, (
        "the refusal must name what is missing and how to supply it")


def test_the_refusal_comes_BEFORE_the_plan_is_composed():
    """Order is the whole guarantee: a plan built first would be a plan
    with no termination in it, and the refusal would arrive too late to
    prevent anything."""
    body = _method_body("ColumnWindow", "on_apply_ties_click")
    assert (body.index("self.top_floor_cb.IsChecked")
            < body.index("complete_plan("))


def test_place_refuses_too_because_the_plan_may_predate_the_tick():
    body = _method_body("ColumnWindow", "on_apply_click")
    assert "self.plan.roof_termination is None" in body


# --------------------------------------------------------------------- #
# One object, composed once


def test_the_termination_reaches_the_plan_through_complete_plan():
    """#110's rule. The window states inputs; `complete_plan` composes.
    A second place that half-composed it is how the report and the placer
    drift apart."""
    body = _method_body("ColumnWindow", "on_apply_ties_click")
    assert "roof_termination=self.roof_termination" in body


def test_the_second_window_composes_NOTHING_itself():
    """It calls the core assembler and does not reimplement it: no
    terminate_run, no step axes, no per-run mapping in the window."""
    source = _class_source("RoofWindow")
    assert "roof_termination_plan(" in source
    for forbidden in ("terminate_run(", "STEP_AXIS_", "terminate_bar("):
        assert forbidden not in source, (
            "%s belongs to rft.core, where it can be tested" % forbidden)


def test_the_window_hands_the_plan_over_rather_than_keeping_it():
    body = _method_body("RoofWindow", "on_use_click")
    assert "self.owner.accept_roof_termination(plan)" in body


# --------------------------------------------------------------------- #
# R35 / R38 / R42, as the window applies them


def test_L_D_has_NO_default_and_is_never_inherited_from_the_beam():
    """R35: the engineer states it. The markup's box starts empty, and
    nothing here supplies 55 or 60 -- those are the beam spec's numbers
    for bars in bending."""
    source = _class_source("RoofWindow")
    assert "DEFAULT_LD" not in source
    for beam_default in ("55", "60"):
        assert ("= %s" % beam_default) not in source


def test_the_typed_cover_box_opens_ONLY_when_the_slab_reads_zero():
    """R38. A typed box that is always open invites a number that
    disagrees with the model."""
    body = _method_body("RoofWindow", "_show_read")
    assert 'slab["cover_provenance"] == "read"' in body
    assert "Visibility.Collapsed" in body
    assert "Visibility.Visible" in body
    assert body.index("Visibility.Collapsed") < body.index("Visibility.Visible")


def test_a_free_edge_is_FLAGGED_by_the_engineer_not_inferred_from_the_run():
    """Section 3 + R42: a flagged free edge and a measured short run are
    different facts, and section 4 reports which one shortened a bar."""
    body = _method_body("RoofWindow", "free_edge_names")
    assert "IsChecked" in body
    assert "available_run_mm" not in body


def test_changing_a_free_edge_INVALIDATES_the_read():
    """A free edge changes the run its face is allowed, so a read taken
    before the tick is stale. Leaving the old number on screen is the
    failure this prevents."""
    body = _method_body("RoofWindow", "on_free_edge_changed")
    assert "self.slab = None" in body
    assert "self.use_btn.IsEnabled = False" in body


# --------------------------------------------------------------------- #
# The dispatcher, and what it swallows


def test_the_slab_read_runs_in_REVIT_S_context():
    """Reading walks geometry and fires a ReferenceIntersector, both
    illegal outside Revit's API context in a modeless window."""
    body = _method_body("RoofWindow", "on_read_slab_click")
    assert "revit.events.execute_in_revit_context" in body


def test_the_read_catches_EVERYTHING_because_the_dispatcher_swallows():
    """``execute_in_revit_context``'s handler swallows exceptions into
    pyRevit's log, so an uncaught failure reaches the engineer as nothing
    happening at all -- this project's own silent-failure shape."""
    body = _method_body("RoofWindow", "_read_slab_in_context")
    assert "except ColumnRoofSlabError" in body
    assert "except Exception" in body
    assert body.index("except ColumnRoofSlabError") < body.index(
        "except Exception"), (
        "the expected refusal must be caught before the catch-all, or it "
        "is reported as a crash")


# --------------------------------------------------------------------- #
# A refusal the engineer cannot SEE is a silent failure


def test_every_tab_refusal_also_reaches_the_ALWAYS_VISIBLE_status_line():
    """Reported live: "Apply in the main window for ties does not work".

    It worked. It REFUSED, and wrote the reason to `ties_status_tb`, which
    lives INSIDE the Ties tab's ScrollViewer beneath the Apply button --
    below the fold on a short window -- while `status_tb`, which sits
    outside the TabControl and is always visible, still read "ready". A
    working refusal was therefore reported as a broken button.

    A REFUSAL is what this checks, not every message: a refusal is a write
    to a tab's status line followed by an early ``return``, and it is the
    one the engineer must see. A SUCCESS line ("Applied (Mode A)...")
    rightly stays on its own tab, where it is read in context.
    """
    lines = _script().split(chr(10))
    offenders = []
    for index, line in enumerate(lines):
        stripped = line.strip()
        if "_status_tb.Text = " not in stripped:
            continue
        if not stripped.startswith("self."):
            continue
        name = stripped.split(".")[1]
        if name == "roof_status_tb":
            # The second window has no tabs and no scrolled status line:
            # its footer is always visible, so it IS the visible line.
            continue
        # Look ahead over this statement and its continuation lines for
        # the early return that makes it a refusal.
        for follower in lines[index + 1:index + 8]:
            following = follower.strip()
            if following == "return":
                offenders.append(name)
                break
            if following and not following.startswith(
                    ("\"", "'", ")", "%", "+", "." , "if ", "else")):
                break
    assert not offenders, (
        "these refusals are written ONLY to their own tab, which can be "
        "scrolled out of view while status_tb still reads 'ready'. Route "
        "them through _refuse_on_tab: " + repr(sorted(set(offenders))))


def test_the_helper_writes_BOTH_lines():
    body = _method_body("ColumnWindow", "_refuse_on_tab")
    assert "status_control.Text = message" in body
    assert "self.status_tb.Text = message" in body
