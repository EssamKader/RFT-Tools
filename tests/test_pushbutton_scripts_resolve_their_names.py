# -*- coding: utf-8 -*-
"""Every pushbutton script is checked for names that do not exist.

## Why this exists

`_render` in the column window read a local that had been deleted:

    r_px = max(shape.r * scale, MIN_BAR_RADIUS_PX)

`scale` was a local of `_render` until #137 replaced it with
`SketchTransform`; the circle branch was never updated. On a live host that
raised `NameError` at the FIRST bar circle, so the sketch drew the concrete
outline, the cover band and the tie rectangle -- the polygons that come
earlier in the shape list -- and then silently stopped. No bars, no section
6.1 dimensions, no captions, and no error message, because the exception
died inside a WPF handler.

**906 tests and 140 mutation-proven guards all passed.** They could not do
otherwise: `script.py` imports `pyrevit`, so nothing in this suite can
execute it, and every guard over it is a regex looking for text that IS
there rather than a check that the text means anything.

## What this checks, and why pyflakes

A name that is read but never bound is decidable without running anything,
and `pyflakes` decides it. Over both pushbutton scripts it reported exactly
one problem -- the line above -- and nothing else, so this is a signal
without a false-positive tax.

It is NOT a linter gate. Only undefined names are failed, because that is
the class that stops the window working. Unused imports, shadowing and
style are pyflakes' business and not this project's.

## What it cannot prove

That the names which DO resolve are the right ones, that a Revit API member
exists, or that WPF accepts the markup. Those stay with the existing guards
and with live verification. This is the cheap check nobody was making.
"""

import os

import pytest

from xaml_keys import (
    BEAM_PUSHBUTTON_DIR, COLUMN_PUSHBUTTON_DIR, FOOTING_PUSHBUTTON_DIR)

#: Every script pyRevit executes as a button. Listed rather than walked:
#: these are the files that cannot be imported by the suite, which is
#: exactly why they need this.
PUSHBUTTON_SCRIPTS = (
    os.path.join(COLUMN_PUSHBUTTON_DIR, "script.py"),
    os.path.join(BEAM_PUSHBUTTON_DIR, "script.py"),
    os.path.join(FOOTING_PUSHBUTTON_DIR, "script.py"),
)


def _undefined_names(path):
    """Every "undefined name" pyflakes reports for one file.

    pyflakes is imported here rather than shelled out to, so a missing
    install fails loudly at collection instead of quietly reporting
    nothing.
    """
    from pyflakes.api import check
    from pyflakes.reporter import Reporter

    class _Collect(object):
        """Reporter protocol: pyflakes calls these, we keep what matters."""

        def __init__(self):
            self.problems = []
            self.errors = []

        def unexpectedError(self, filename, msg):
            self.errors.append("%s: %s" % (filename, msg))

        def syntaxError(self, filename, msg, lineno, offset, text):
            self.errors.append("%s:%s: %s" % (filename, lineno, msg))

        def flake(self, message):
            self.problems.append(message)

    del Reporter  # imported only to assert the API shape is present
    collector = _Collect()
    import io
    source = io.open(path, encoding="utf-8").read()
    check(source, path, collector)
    assert not collector.errors, (
        "pyflakes could not analyse %s: %s" % (path, collector.errors))
    return [str(problem) for problem in collector.problems
            if "undefined name" in str(problem)]


@pytest.mark.parametrize("path", PUSHBUTTON_SCRIPTS,
                         ids=lambda p: os.path.basename(
                             os.path.dirname(p)))
def test_the_script_reads_no_name_it_never_binds(path):
    """The check that would have caught the blank sketch."""
    undefined = _undefined_names(path)
    assert not undefined, (
        "a pushbutton script reads a name that does not exist. This cannot "
        "be caught by running the suite -- the file imports pyrevit -- and "
        "on a live host it raises NameError wherever the line happens to "
        "sit, which for a drawing loop means a half-drawn picture and no "
        "error message:\n  " + "\n  ".join(undefined))


def test_pyflakes_actually_reports_an_undefined_name():
    """Guards the guard.

    If `_undefined_names` silently returned nothing -- a changed reporter
    protocol, a filter that matches no message -- the test above would pass
    for every file forever. So feed it a source with a known undefined name
    and require that it is found.
    """
    import io
    import tempfile

    handle, path = tempfile.mkstemp(suffix=".py")
    os.close(handle)
    try:
        io.open(path, "w", encoding="utf-8").write(
            u"def f():\n    return missing_name\n")
        found = _undefined_names(path)
    finally:
        os.remove(path)
    assert any("missing_name" in problem for problem in found), (
        "pyflakes did not report a name that is plainly undefined, so the "
        "guard above is watching nothing: %r" % (found,))
