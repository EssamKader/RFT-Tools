# -*- coding: utf-8 -*-
"""#87 -- the column window, checked the only ways it can be without Revit.

``script.py`` cannot be imported here: it imports ``pyrevit``, which is not
installed under plain CPython (see ``tests/fake_revit_api.py``'s header).
So both files are parsed as TEXT and cross-checked, which is exactly what
catches the defects that would otherwise surface as an ``AttributeError``
on a live host, after the window is already open.

Several guards here are the beam window's, applied to the second element.
They are written against ``WINDOW_XAML_PATHS`` rather than one file, so a
third element inherits them by being added to that tuple instead of by
somebody remembering to copy a test.
"""

import ast
import io
import os
import re
import xml.etree.ElementTree as ET

import pytest

from rft.ui.shared_styles import (
    PLACEHOLDER_SOURCE, SHARED_STYLES_FILENAME, window_xaml,
)
from xaml_keys import (
    COLUMN_PUSHBUTTON_DIR, COLUMN_XAML_PATH, SHARED_STYLES_PATH,
    WINDOW_XAML_PATHS, declared_keys_in, merges_shared_styles, read,
    resolvable_keys,
)

SCRIPT_PATH = os.path.join(COLUMN_PUSHBUTTON_DIR, "script.py")
BUNDLE_PATH = os.path.join(COLUMN_PUSHBUTTON_DIR, "bundle.yaml")

X_NAME = "{http://schemas.microsoft.com/winfx/2006/xaml}Name"


def _script():
    return io.open(SCRIPT_PATH, encoding="utf-8").read()


def _x_names(path):
    tree = ET.fromstring(read(path).encode("utf-8"))
    return set(element.attrib[X_NAME] for element in tree.iter()
               if X_NAME in element.attrib)


def _reset_body(script):
    """``_reset_column_state``'s body, PLUS the bodies of the private
    helpers it calls.

    #90 cleared the sketch caption inside ``_clear_canvases`` rather than
    inline, and a guard reading only the reset's own text called that a
    field nobody clears. Demanding everything be inline would be the
    guard dictating the shape of the code it watches; following one level
    of calls is what "is this actually reset" means.
    """
    body = re.search(r"def _reset_column_state\(.*?\n(.*?)\n    # ---",
                     script, re.DOTALL).group(1)
    for helper_name in set(re.findall(r"self\.(_[a-z_]+)\(", body)):
        found = re.search(r"def %s\(.*?\n(.*?)\n    (?:def |# ---)"
                          % helper_name, script, re.DOTALL)
        if found:
            body += "\n" + found.group(1)
    return body


def _code_of(function_name):
    """``(names called, string literals)`` inside one function, DOCSTRING
    EXCLUDED.

    Four guards in this project have now failed against their own
    explanation -- a test that forbids a string, in a function whose
    docstring explains why that string is forbidden, flags itself. Reading
    the parsed code instead of the raw text ends the class of problem
    rather than each instance of it.
    """
    for node in ast.walk(ast.parse(_script())):
        if isinstance(node, ast.FunctionDef) and node.name == function_name:
            body = node.body
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                body = body[1:]           # drop the docstring
            called, literals = set(), []
            for statement in body:
                for inner in ast.walk(statement):
                    if isinstance(inner, ast.Name):
                        called.add(inner.id)
                    elif isinstance(inner, ast.Attribute):
                        called.add(inner.attr)
                    elif (isinstance(inner, ast.Constant)
                          and isinstance(inner.value, str)):
                        literals.append(inner.value)
            return called, literals
    raise AssertionError("no function named %r in script.py" % function_name)


def test_the_two_bar_pickers_are_filled_from_DIFFERENT_lists():
    """#133. The longitudinal picker takes T-named types only; the tie
    picker takes everything. Filling both from one list is the defect
    this guards -- it would silently offer an M type for the vertical
    bars, which is the whole thing the ruling exists to prevent.

    Source-level because ``script.py`` imports ``pyrevit`` and cannot be
    executed here. The FILTER itself is tested by execution in
    ``tests/test_bar_type_grade.py``; this only checks the window asks
    for it.
    """
    source = _script()
    assert "high_tensile_only=True" in source, (
        "the longitudinal picker must ask for the filtered list")
    assert source.count("bar_type_options(") >= 2, (
        "two pickers, two calls -- one filtered, one not")


def test_the_column_xaml_parses():
    ET.fromstring(read(COLUMN_XAML_PATH).encode("utf-8"))


def test_no_xaml_comment_contains_a_double_hyphen():
    """"--" is illegal inside an XML comment and makes the whole file
    unparseable. It has happened three times on the beam window, every time
    from writing a XAML comment in the same prose style as the Python
    comments next door, where "--" is ordinary punctuation. The parse test
    catches it as "invalid token: line 24"; this says the cause.
    """
    for path in WINDOW_XAML_PATHS:
        text = read(path)
        offenders = [text[:m.start()].count("\n") + 1
                     for m in re.finditer(r"<!--(.*?)-->", text, re.DOTALL)
                     if re.search(r"-{2,}", m.group(1))]
        assert not offenders, (
            "%s: XAML comment(s) at line(s) %s contain '--'. Use a single "
            "hyphen; '--' is fine in the Python comments next door, which "
            "is exactly why this keeps happening."
            % (os.path.basename(path), offenders))


def test_the_window_element_itself_uses_no_static_resource():
    """The defect that broke the beam tool's v0.2.0-rc6 the moment the
    button was pressed. A ``<Window>``'s own attributes are resolved BEFORE
    its ``Window.Resources`` exists, so a StaticResource up there is a
    forward reference -- and StaticResource does not do forward references.

    The XML parses perfectly, so this is a WPF SEMANTIC error inside
    well-formed markup. Put window-level brushes on the root panel.
    """
    for path in WINDOW_XAML_PATHS:
        text = read(path)
        assert "StaticResource" not in text[:text.index(">")], (
            "%s: the <Window> element cannot reference Window.Resources."
            % os.path.basename(path))


def test_every_static_resource_reference_is_defined():
    """Any StaticResource whose key is never declared -- here or in the
    merged palette -- throws only when the window is constructed, on a live
    host, forty frames deep.
    """
    for path in WINDOW_XAML_PATHS:
        used = set(re.findall(r"\{StaticResource\s+([A-Za-z0-9_]+)\s*\}",
                              read(path)))
        assert used, "%s: no StaticResource references -- pattern broken?" % path
        missing = sorted(used - resolvable_keys(path))
        assert not missing, (
            "%s: these StaticResource keys are referenced but never "
            "declared: %s" % (os.path.basename(path), missing))


def test_every_window_merges_the_shared_palette():
    """#86's whole point, now that there are two windows. Delete the merge
    line and the file still parses, still declares every Style, and throws
    "Cannot find resource named 'InkMuted'" on the first button press --
    observed live, see docs/verification/issue-86-shared-palette-loading.md.
    """
    for path in WINDOW_XAML_PATHS:
        assert merges_shared_styles(read(path)), (
            "%s does not merge the shared palette (expected %r)."
            % (os.path.basename(path), PLACEHOLDER_SOURCE))


def test_no_window_declares_a_palette_brush_of_its_own():
    """The drift #86 removes, caught in the act on either window.

    A local key beats a merged dictionary, so a copied brush would make one
    window quietly stop following the palette while every other test stayed
    green -- agreeing on the day of the copy, diverging on the first change
    after it.
    """
    shared = declared_keys_in(read(SHARED_STYLES_PATH))
    for path in WINDOW_XAML_PATHS:
        shadowed = sorted(declared_keys_in(read(path)) & shared)
        assert not shadowed, (
            "%s re-declares shared palette keys %s; a local key wins over a "
            "merged dictionary." % (os.path.basename(path), shadowed))


def test_no_window_carries_another_relative_uri():
    """Both windows load from a STRING, which has no BaseUri, so every
    other relative URI would resolve against nothing and throw at load.
    The placeholder is the exception: it is rewritten to an absolute URI
    before WPF sees it.
    """
    uri_attrs = r"(?<![A-Za-z])(?:Source|UriSource|Icon|BaseUri)"
    for path in WINDOW_XAML_PATHS:
        found = re.findall(uri_attrs + r'="([^"]+)"', read(path))
        relative = [s for s in found
                    if s != SHARED_STYLES_FILENAME
                    and "://" not in s
                    and not s.startswith("/")
                    and not s.startswith("pack:")
                    and not s.startswith("{")]
        assert not relative, (
            "%s: these relative URIs cannot resolve in a string-loaded "
            "window: %s" % (os.path.basename(path), relative))


def test_no_window_declares_an_event_handler_in_the_markup():
    """A Click="handler" attribute throws at PARSE time in both windows.

    They are loaded from a string, which has no code behind, so WPF has
    nowhere to resolve the handler name and reports "Failed to create a
    'Click' from the text 'on_pick_click'" -- observed live on Revit 2024
    while building #87, on markup that parsed as XML perfectly.

    Handlers are wired in Python instead (``self.btn.Click += self.on_x``),
    which is what the beam window has always done.
    """
    for path in WINDOW_XAML_PATHS:
        # Comments stripped first. The XAML explains, in a comment, why a
        # Click attribute is wrong -- and a guard that flags its own
        # explanation is a guard nobody can document. (This is the second
        # time: the modal-window guard had to learn it too.) A
        # commented-out handler is also genuinely harmless.
        markup = re.sub(r"<!--.*?-->", "", read(path), flags=re.DOTALL)
        handlers = re.findall(r'\s((?:Click|Checked|Unchecked|SelectionChanged'
                              r'|TextChanged|Loaded|Closing)=")', markup)
        assert not handlers, (
            "%s declares event handler attribute(s) %s in the markup. A "
            "string-loaded window has no code behind: wire them in Python."
            % (os.path.basename(path), sorted(set(handlers))))


def test_the_column_window_resolves_and_still_parses():
    """End to end on the file that ships: substitute the palette path, then
    parse.
    """
    resolved = window_xaml(COLUMN_XAML_PATH)
    ET.fromstring(resolved.encode("utf-8"))
    assert 'Source="file:///' in resolved


# --------------------------------------------------------------------- #
# XAML <-> script cross-checks


def test_every_control_the_script_touches_exists_in_the_xaml():
    """The defect class this guard exists for: a renamed x:Name that
    pyRevit's WPFWindow surfaces only as an AttributeError, on a live host,
    inside an ExternalEvent whose handler swallows it -- so the engineer
    sees nothing happen at all.
    """
    names = _x_names(COLUMN_XAML_PATH)
    script = _script()
    # Attributes assigned in __init__ that are ordinary Python state, not
    # controls. Listed rather than pattern-matched: the point is that
    # adding one is a deliberate act.
    not_controls = {
        "column", "column_data", "bar_type_options", "Title",
        "_api_call_in_flight",
    }
    used = set(re.findall(r"self\.([a-zA-Z_][a-zA-Z0-9_]*)", script))
    used -= not_controls
    used -= set(re.findall(r"def ([a-zA-Z_][a-zA-Z0-9_]*)", script))
    missing = sorted(n for n in used if n.endswith(("_tb", "_cb", "_btn", "_tab"))
                     and n not in names)
    assert not missing, (
        "script.py reads these as window controls, but ColumnWindow.xaml "
        "declares no such x:Name: %s" % missing)


def test_every_gated_tab_named_in_the_script_exists():
    """``GATED_TAB_NAMES`` is the single list that enables and disables the
    tabs. A name in it that the XAML does not declare fails only on the
    first pick -- i.e. after the refusal logic it guards has already run.
    """
    listed = re.search(r"GATED_TAB_NAMES = \(([^)]*)\)", _script()).group(1)
    tabs = set(re.findall(r'"([a-z_]+)"', listed))
    assert tabs, "GATED_TAB_NAMES did not parse -- pattern broken?"
    assert tabs <= _x_names(COLUMN_XAML_PATH), sorted(tabs - _x_names(COLUMN_XAML_PATH))


def test_every_gated_tab_in_the_xaml_starts_disabled():
    """A tab that ships enabled is a tab the user can fill in before a
    column has been accepted -- which is the beam tool's A35 rule, and the
    reason its geometry fields stay disabled until a beam is picked.
    """
    tree = ET.fromstring(read(COLUMN_XAML_PATH).encode("utf-8"))
    listed = re.search(r"GATED_TAB_NAMES = \(([^)]*)\)", _script()).group(1)
    gated = set(re.findall(r'"([a-z_]+)"', listed))
    for element in tree.iter():
        if element.attrib.get(X_NAME) in gated:
            assert element.attrib.get("IsEnabled") == "False", (
                "%s ships enabled; it must stay disabled until a column is "
                "accepted." % element.attrib[X_NAME])


def test_the_pick_handler_does_no_revit_work_directly():
    """A modeless window's click handlers run OUTSIDE Revit's API context,
    where PickObject and Transaction both raise. The click handler may only
    dispatch.
    """
    body = re.search(r"def on_pick_click\(.*?\n(.*?)\n    def ",
                     _script(), re.DOTALL).group(1)
    for forbidden in ("pick_element", "Transaction", "read_column"):
        assert forbidden not in body, (
            "on_pick_click calls %s directly; it must go through "
            "_dispatch_to_revit_context." % forbidden)
    # Naming the forbidden calls is not enough, and tools/prove_guards.py
    # proved it: replacing the dispatch with a plain
    # self._pick_column_in_context() mentions none of them and still runs
    # every one of them outside Revit's API context. So the handler must
    # POSITIVELY go through the dispatcher.
    assert "_dispatch_to_revit_context" in body, (
        "on_pick_click must dispatch through _dispatch_to_revit_context; "
        "calling the worker directly runs PickObject outside Revit's API "
        "context, where it raises.")


def test_dispatched_work_cannot_fail_silently():
    """``execute_in_revit_context``'s handler swallows exceptions into
    pyRevit's log. An error would reach the engineer as NOTHING HAPPENING,
    which is the worst failure mode there is and one this project has paid
    for repeatedly.
    """
    body = re.search(r"def _run_in_revit_context\(.*?\n(.*?)\n    # ---",
                     _script(), re.DOTALL).group(1)
    assert "except Exception" in body, (
        "_run_in_revit_context must catch everything; anything escaping it "
        "is logged and shown to nobody.")
    assert "forms.alert" in body, "a swallowed error must reach the screen"


def test_a_refused_column_is_not_reported_as_a_failure():
    """A column this tool declines is an EXPECTED outcome, not a crash. It
    gets the reason; it must not get a stack trace or the word "failed",
    which would send the user looking for a bug that is not there.
    """
    body = re.search(r"def _run_in_revit_context\(.*?\n(.*?)\n    # ---",
                     _script(), re.DOTALL).group(1)
    assert "except ColumnHostError" in body, (
        "a refusal must be handled separately from a crash")
    assert body.index("except ColumnHostError") < body.index("except Exception"), (
        "the broad handler must come second, or every refusal is reported "
        "as a failure")


def test_the_state_reset_runs_before_the_pick_not_after():
    """Reset-on-success leaves the PREVIOUS column's numbers on screen when
    the new one is refused halfway through the read.
    """
    body = re.search(r"def _pick_column_in_context\(.*?\n(.*?)\n    # ---",
                     _script(), re.DOTALL).group(1)
    assert body.index("_reset_column_state") < body.index("pick_element"), (
        "the reset must happen before the pick, so a refusal cannot leave "
        "stale read-outs beside a new column's name")


def test_every_readout_is_cleared_on_a_re_pick():
    """#87's acceptance says the cover read-out "refreshes when a different
    column is picked". A read-out added to the XAML and forgotten in
    READOUT_NAMES keeps the old column's number.
    """
    script = _script()
    # Every module-level *_NAMES tuple, discovered rather than listed:
    # #88 added a third one (DERIVED_NAMES) and this guard caught the
    # omission, which is the point -- but only because it was edited.
    # Discovering them means a FOURTH list is covered on the day it is
    # written.
    groups = re.findall(r"^([A-Z_]+_NAMES) = \(([^)]*)\)", script,
                        re.MULTILINE)
    assert groups, "no *_NAMES tuples found -- pattern broken?"
    listed = set()
    for name, body in groups:
        listed |= set(re.findall(r'"([a-z_]+)"', body))

    # ...and each of those tuples must actually be cleared. A list that
    # exists but is never iterated in the reset is worse than no list:
    # it reads, to the next person, as though the clearing is handled.
    reset = _reset_body(script)
    unused = sorted(name for name, _ in groups
                    if name != "GATED_TAB_NAMES" and name not in reset)
    assert not unused, (
        "these read-out lists are never cleared in _reset_column_state, "
        "so the fields in them keep the previous column's values: %s"
        % unused)
    written = set(re.findall(r"self\.([a-z_]+_tb)\.Text = ", script))

    # Status LINES carry a message rather than a column value, so they
    # are not listed -- but they must still be reset, or the last
    # column's "Applied." survives into the next pick. So they are
    # excused from the lists and held to the reset instead.
    status_lines = set(name for name in written
                       if name.endswith("status_tb"))
    # The window-level status line belongs to the dispatcher, which
    # overwrites it on every action ("Pick column -- waiting for
    # Revit..."). It is not column state.
    status_lines.discard("status_tb")
    # Reset either by a direct assignment, or by being named in one of
    # the lists the reset loops over with getattr -- both clear it, and
    # a check that only saw the literal assignment would demand the
    # lists be abandoned.
    not_reset = sorted(
        name for name in status_lines
        if ("self.%s.Text" % name) not in reset and name not in listed)
    assert not not_reset, (
        "these status lines are written on one column and never reset "
        "for the next: %s" % not_reset)
    written -= status_lines | {"status_tb"}
    # A field is cleared either by being in one of the lists, or by a
    # direct assignment in the reset (possibly inside a helper it
    # calls). Both clear it; only "cleared nowhere" is a defect.
    cleared_directly = set(re.findall(r"self\.([a-z_]+_tb)\.Text = ", reset))
    missing = sorted(written - listed - cleared_directly)
    assert not missing, (
        "these read-outs are populated on pick but never cleared on the "
        "next one, so they would show the previous column's value: %s"
        % missing)


def test_the_modeless_window_declares_a_persistent_engine():
    """Without ``engine: persistent: true`` pyRevit tears the IronPython
    engine down when the script returns. The window survives as a CLR
    object and still repaints, but every ExternalEvent is raised into a
    dead engine and silently never delivers -- a button that waits forever
    with no error. It cost the beam tool a release candidate.

    Parsed with a real YAML parser, because what matters is what pyRevit
    will read, not what the text looks like.
    """
    yaml = pytest.importorskip("yaml")
    bundle = yaml.safe_load(io.open(BUNDLE_PATH, encoding="utf-8").read())
    assert bundle.get("engine", {}).get("persistent") is True, (
        "bundle.yaml must set engine.persistent: true for a modeless window")


def test_the_window_is_never_shown_modally():
    """ShowDialog() disables every other top-level window in the process,
    Revit's main window included, so PickObject could never receive a
    viewport click.
    """
    # A CALL, not the word: this file's own docstring explains why
    # ShowDialog is wrong, and a substring test flags its own explanation.
    calls = re.findall(r"\.ShowDialog\s*\(", _script())
    assert not calls, "the window must never be shown modally"
    assert "window.show()" in _script()


# --------------------------------------------------------------------- #
# #88 -- the inputs


def test_the_two_hook_dropdowns_are_structurally_separate():
    """Section 7 keeps them separate "so one dropdown's selection can never
    silently apply to the other role".

    Two `Items` collections, filled from the same option list -- which is
    deliberate duplication, not an oversight to be tidied into one shared
    ItemsSource. A shared source is one binding away from a shared
    selection.
    """
    script = _script()
    assert "outer_hook_cb" in script and "inner_hook_cb" in script
    for forbidden in ("ItemsSource", "self.inner_hook_cb.SelectedIndex = "
                                      "self.outer_hook_cb.SelectedIndex"):
        assert forbidden not in script, (
            "%s couples the two hook dropdowns; section 7 requires them "
            "independent." % forbidden)


def test_the_column_tool_never_imports_the_beam_135_degree_GUARD():
    """The beam REFUSES anything but 135; column section 7 DEFAULTS to it
    and permits any available hook type. Importing that guard here would
    refuse what this spec allows -- the reuse audit's clearest
    do-not-reuse.
    """
    tree = ast.parse(_script())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported |= set(a.name for a in node.names)
    assert "hook_angle_guard_message" not in imported
    assert "HOOK_ANGLE_REQUIRED_DEG" not in imported


def test_the_default_hook_is_chosen_by_ANGLE_not_by_name():
    """Names lie: the live model carries a `Stirrup/Tie - 45` whose stored
    style is 0, and a `Standard - 135 deg.` in the wrong family. A
    substring match on "135" believes them.
    """
    called, literals = _code_of("_default_hook_candidates")
    assert "hook_angle_deg" in called, (
        "the default must be matched on the angle read back off the type")
    assert not [s for s in literals if "135" in s], (
        "a string literal containing 135 means the label text is being "
        "matched, which trusts the type's name")


def test_the_manual_spacing_boxes_ship_disabled():
    """An editable box whose value is ignored is a lie the window tells
    every time Mode A is selected. They open disabled, and only Mode B
    enables them.
    """
    tree = ET.fromstring(read(COLUMN_XAML_PATH).encode("utf-8"))
    found = 0
    for element in tree.iter():
        if element.attrib.get(X_NAME) in ("manual_confinement_tb",
                                          "manual_middle_tb"):
            found += 1
            assert element.attrib.get("IsEnabled") == "False", (
                "%s ships enabled in Mode A" % element.attrib[X_NAME])
    assert found == 2, "both manual spacing boxes must exist"
    assert "def on_spacing_mode_changed" in _script(), (
        "nothing re-enables them when Mode B is selected")


def test_mode_a_is_the_one_checked_at_load():
    tree = ET.fromstring(read(COLUMN_XAML_PATH).encode("utf-8"))
    checked = [e.attrib[X_NAME] for e in tree.iter()
               if e.attrib.get(X_NAME) in ("mode_a_rb", "mode_b_rb")
               and e.attrib.get("IsChecked") == "True"]
    assert checked == ["mode_a_rb"], (
        "Mode A (auto) is the default; opening in manual would ask the "
        "engineer for numbers before showing them the code maximums")


def test_a_section_8_flag_is_amber_not_red():
    """"Warn but place". A Mode B violation is flagged and then BUILT, so
    painting it in DangerRed would describe a refusal that does not
    happen -- and the beam palette keeps red for failures on purpose.
    """
    text = read(COLUMN_XAML_PATH)
    flags = re.search(r'x:Name="spacing_flags_tb".*?/>', text, re.DOTALL)
    assert flags, "spacing_flags_tb not found"
    assert "WarningAmber" in flags.group(0)
    assert "DangerRed" not in flags.group(0)


def test_the_section_8_flags_actually_reach_the_screen():
    """Computing the flags and never showing them is section 8's exact
    failure mode: the spec requires the code limit displayed "ALONGSIDE
    the user's manual value as a visible flag", and a plan whose flags
    stay in memory is silent compliance wearing a warning's clothes.

    Checked on the ASSIGNMENT's own subtree, not on the function's text.
    tools/prove_guards.py refused two weaker versions of this guard: the
    mutant replaces the assignment with an empty string while the status
    line two lines below still says "plan.flags", so both "does the
    function mention flags" and "does it touch spacing_flags_tb" stay
    true. Only the value being assigned distinguishes them.
    """
    assigned = _assigned_value_names("spacing_flags_tb")
    assert assigned is not None, (
        "nothing assigns to self.spacing_flags_tb.Text")
    assert "flags" in assigned, (
        "the flag line is assigned something that never reads the plan's "
        "flags, so a Mode B violation is computed and then shown to "
        "nobody")


def _assigned_value_names(control_name):
    """Every name appearing in the value assigned to
    ``self.<control_name>.Text``, or ``None`` if nothing assigns to it.
    """
    for node in ast.walk(ast.parse(_script())):
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if (isinstance(target, ast.Attribute) and target.attr == "Text"
                    and isinstance(target.value, ast.Attribute)
                    and target.value.attr == control_name):
                names = set()
                for inner in ast.walk(node.value):
                    if isinstance(inner, ast.Name):
                        names.add(inner.id)
                    elif isinstance(inner, ast.Attribute):
                        names.add(inner.attr)
                return names
    return None


def test_the_placer_facing_fields_are_what_the_window_shows():
    """Section 8's single-source rule reaching the UI: the two "to build"
    read-outs must come from the plan's built fields, not from s0_mm and
    the middle-zone maximum -- which are the CODE LIMITS and differ in
    Mode B, the only mode where it matters.
    """
    script = _script()
    assert "plan.confinement_spacing_mm" in script
    assert "plan.middle_zone_spacing_mm" in script
    built = re.search(r"self\.confinement_built_tb\.Text = [^\n]*\n[^\n]*",
                      script).group(0)
    assert "confinement_spacing_mm" in built, (
        "the 'to build' read-out must show what will be built, not the "
        "code limit")


def test_the_corner_sharing_convention_is_stated_in_the_WINDOW():
    """The reuse audit calls corner double-counting "exactly the kind of
    thing that would pass a unit test per-face and produce eight corner
    bars in Revit". A convention only the docstring knows is a convention
    the user cannot check.
    """
    text = read(COLUMN_XAML_PATH)
    assert "INCLUDES the two corner bars" in text
    assert "counted once in the total" in text


# --------------------------------------------------------------------- #
# #91 -- the Review report


def test_the_report_refuses_to_render_a_PARTIAL_page():
    """A page with missing sections is still read as the page, and this
    one's whole purpose is being trusted before Place. It names what is
    still needed instead of filling the gaps with blanks.
    """
    body = re.search(r"def on_build_report_click\(.*?\n(.*?)\n    # ---",
                     _script(), re.DOTALL).group(1)
    assert "missing" in body and "return" in body, (
        "nothing stops a report being rendered from half-filled state")
    for required in ("column_data", "self.longitudinal", "self.spacing"):
        assert required in body, (
            "%s is never checked before rendering" % required)


def test_the_report_is_selectable_so_it_can_leave_the_window():
    """A report that cannot be copied is a report that gets retyped. It is
    a read-only TextBox rather than a TextBlock for that reason, and
    monospaced because the tie level table is columnar.
    """
    text = read(COLUMN_XAML_PATH)
    box = re.search(r'<TextBox[^>]*x:Name="report_tb".*?/>', text, re.DOTALL)
    assert box, "report_tb is not a TextBox"
    assert 'IsReadOnly="True"' in box.group(0)
    assert "Consolas" in box.group(0), (
        "proportional digits destroy the tie level table")


# --------------------------------------------------------------------- #
# #90 -- the live sketch


def test_the_sketch_redraws_from_BOTH_apply_handlers():
    """#90's acceptance: the sketch redraws as inputs change. Bar counts
    change the cross-section; the tie spacing changes the zone strip. A
    redraw on only one leaves the other stale and believable.
    """
    for handler in ("on_apply_longitudinal_click", "on_apply_ties_click"):
        called, _literals = _code_of(handler)
        assert "redraw_sketch" in called, (
            "%s does not redraw the sketch" % handler)


def test_the_renderer_computes_no_POSITIONS_of_its_own():
    """A48, applied to a second element. The renderer fits millimetres
    into pixels and nothing else -- every coordinate arrives decided, from
    the same modules the report reads, so the sketch cannot draw a layout
    the page denies.
    """
    called, _literals = _code_of("_render")
    for forbidden in ("perimeter_bar_positions", "tie_levels", "spacing_plan",
                      "bar_centre_offset_mm", "tie_half_dimensions_mm"):
        assert forbidden not in called, (
            "_render calls %s; it must receive shapes, not build them"
            % forbidden)


def test_the_sketch_uses_the_COLUMN_palette_not_the_beams():
    """rft.ui.sketch_palette is guarded both ways against the BEAM's style
    keys, so a column key added to it fails the beam's own test. The
    brushes are shared (#86); the mappings are per-element.
    """
    tree = ast.parse(_script())
    modules = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            modules.add(node.module or "")
    assert "rft.ui.column_sketch_palette" in modules
    assert "rft.ui.sketch_palette" not in modules


def test_the_window_still_opens_when_the_WPF_shapes_are_missing():
    """The sketch is a verification surface, not a load-bearing part of
    placement. A column that cannot be DRAWN can still be reviewed, so an
    import failure must not take the window with it.
    """
    script = _script()
    assert "_WPF_SHAPES_AVAILABLE = False" in script, (
        "the WPF shape imports are not wrapped")
    called, _literals = _code_of("redraw_sketch")
    assert "_WPF_SHAPES_AVAILABLE" in called, (
        "redraw_sketch does not check whether the shape types loaded")


def test_the_two_canvases_are_separate():
    """The cross-section and the zone strip share no scale. One canvas
    with both would misrepresent whichever lost the fit.
    """
    names = _x_names(COLUMN_XAML_PATH)
    assert {"section_canvas", "strip_canvas"} <= names


# --------------------------------------------------------------------- #
# #89 -- the tie topology control


def test_the_bend_diameter_is_READ_from_the_bar_type():
    """A1. The live model's 10M reads 40.00 mm against a 9.50 mm bar and
    its 19M reads 115.00 against 19.10 -- 4.2x against 6.0x. A constant
    multiplier would be wrong across most of the range, and being wrong
    here offers Revit a loop it refuses with a modal dialog.
    """
    called, literals = _code_of("_selected_tie_bend_diameter_mm")
    assert "bar_type_bend_diameter_mm" in called
    body = re.search(r"def _selected_tie_bend_diameter_mm\(.*?\n(.*?)\n    def ",
                     _script(), re.DOTALL).group(1)
    for multiplier in ("* 4", "* 6", "* 8", "* 10"):
        assert multiplier not in body, (
            "the bend diameter must be read, not multiplied out of the bar "
            "diameter")


def test_a_refused_topology_is_shown_and_does_not_look_like_a_flag():
    """Section 6.1's refusal and section 8's Mode B flags are different
    things: one declines to place, the other warns and then places. They
    must not share a colour.
    """
    text = read(COLUMN_XAML_PATH)
    findings = re.search(r'x:Name="tie_findings_tb".*?/>', text, re.DOTALL)
    flags = re.search(r'x:Name="spacing_flags_tb".*?/>', text, re.DOTALL)
    assert findings and flags
    assert "DangerRed" in findings.group(0)
    assert "WarningAmber" in flags.group(0)


def test_the_tie_box_says_how_bars_are_NUMBERED():
    """A tie is "bars 1 and 6". Without knowing where bar 0 is and which
    way the numbering runs, that is not an instruction anyone can follow
    -- and the answer is on a different tab.
    """
    text = read(COLUMN_XAML_PATH)
    assert "the bar numbers it touches" in text
    assert "anticlockwise from the bottom-left corner" in text
    assert "Sketch tab" in text


def test_the_tie_box_shows_BOTH_kinds_of_tie():
    """R19's whole point. A user who reads only "bar numbers" will write
    runs, because that is what the old notation allowed and what every
    example showed; the cross-tie has to be named as an example or it
    stays invisible.
    """
    text = read(COLUMN_XAML_PATH)
    assert "cross-tie (1 6)" in text
    assert "closed loop (0 1 2 3)" in text


def test_the_ties_tab_refuses_before_the_bars_exist():
    """A tie arrangement is stated in bar indices. Applying it before the
    Longitudinal tab has built the perimeter would index into nothing.
    """
    body = re.search(r"def on_apply_ties_click\(.*?\n(.*?)\n    # ---",
                     _script(), re.DOTALL).group(1)
    assert "self.layout is None" in body
    assert "Longitudinal bars tab first" in body


# --------------------------------------------------------------------- #
# #110 -- the window composes nothing


#: The modules whose results the window must take from the plan rather
#: than compute for itself. Each one decides a detailing value; a second
#: call site for any of them is a second answer waiting to diverge.
COMPOSED_BY_THE_PLAN = (
    "column_layout",
    "column_spacing",
    "column_tie_levels",
    "column_ties",
)


def test_the_window_reaches_for_the_PLAN_not_the_modules_under_it():
    """#110's whole point, and the beam tool's costliest defect stated as
    a rule.

    ``ZONE_LAYOUT_FLAGS`` drifted between the report and the placer
    because each independently called the same underlying logic. The
    repair was one composing object -- written after both consumers
    existed, which is the expensive way round. The column has one consumer
    and no placer yet, so the rule is enforced here while it still costs
    nothing.

    Four assertions that used to live in this file now run for real in
    ``tests/test_column_plan.py``: the composition moved, and being pure
    it can be executed rather than grepped.
    """
    script = _script()
    offenders = [name for name in COMPOSED_BY_THE_PLAN
                 if ("from rft.core.%s import" % name) in script]
    assert offenders == ["column_layout"], (
        "script.py imports %s directly. Those decisions belong to "
        "rft.core.column_plan, which composes them once; a second call "
        "site is a second answer waiting to disagree with the report. "
        "(column_layout is allowed for tier_summary alone, which is "
        "wording, not a decision.)" % ", ".join(offenders))


def test_the_only_thing_taken_from_column_layout_is_WORDING():
    """The one permitted exception, kept narrow. ``tier_summary`` turns a
    layout the plan already built into a sentence; it decides nothing. If
    anything else is imported from that module the exception has widened
    into the hole it was carved out of.
    """
    line = re.search(r"from rft\.core\.column_layout import ([^\n]+)",
                     _script())
    assert line is not None
    imported = [name.strip() for name in line.group(1).split(",")]
    assert imported == ["tier_summary"], (
        "only tier_summary may come from column_layout; %s decide things "
        "the plan has already decided" % imported)


def test_the_window_builds_the_plan_in_its_two_Apply_handlers():
    """The rule needs a positive half: forbidding the four modules is
    satisfied by a window that computes nothing at all."""
    longitudinal, _ = _code_of("on_apply_longitudinal_click")
    ties, _ = _code_of("on_apply_ties_click")
    assert "bar_plan" in longitudinal, "the perimeter is never composed"
    assert "complete_plan" in ties, "the ties are never composed"


def test_section_6_1_s_verdict_has_ONE_reader_in_the_window():
    """``is_blocked(plan)`` rather than the window applying its own test
    to ``findings``. The placer's gate and the report's wording must
    agree, and the cheapest guarantee is leaving them nothing to disagree
    with.
    """
    script = _script()
    assert "is_blocked(" in script
    assert "is_blocking(" not in script, (
        "the window must ask the plan, not re-apply the test itself")
