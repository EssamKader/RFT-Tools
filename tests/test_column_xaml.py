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
    listed = set()
    for group in re.findall(r"(?:READOUT_NAMES|PROVENANCE_NAMES) = \(([^)]*)\)",
                            script):
        listed |= set(re.findall(r'"([a-z_]+)"', group))
    assert listed, "READOUT_NAMES did not parse -- pattern broken?"
    written = set(re.findall(r"self\.([a-z_]+_tb)\.Text = ", script))
    # The two status lines are messages, not column read-outs.
    written -= {"status_tb", "column_status_tb"}
    missing = sorted(written - listed)
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
