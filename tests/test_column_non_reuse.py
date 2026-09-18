# -*- coding: utf-8 -*-
"""#99 -- section 10's non-reuse rule, checked against the REAL import graph.

`CONTEXT.md`: *"This tool does NOT call or reuse `rft.core.anchorage`."*

## Why this file exists rather than one assertion in one test

The original guard read `column_inputs.py`'s own import statements with
the AST and asserted that "anchorage" was not among them. It passed. The
dependency existed anyway, two hops down::

    rft.core.column_inputs
      -> rft.core.grades
        -> rft.core.guards
          -> rft.core.anchorage

A guard that inspects one file can only ever see that file's first hop, so
it cannot answer the question it was written to answer. **The question is
about the resolved graph, so the check has to be about the resolved
graph.**

Two further properties this file has, and the old guard did not:

- **Every column module, found by WALKING the package**, not by a list
  someone must remember to extend. A new column module is covered the
  moment it exists, which is the only version of this guard that survives
  contact with a growing tool.
- **A fresh interpreter per module.** By the time pytest runs, the suite
  has imported most of the library, so an in-process check would find
  `anchorage` loaded no matter what the module under test does -- passing
  or failing for reasons that have nothing to do with it.
"""

import os
import subprocess
import sys

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LIB_ROOT = os.path.join(REPO_ROOT, "RFT.lib")
CORE_DIR = os.path.join(LIB_ROOT, "rft", "core")

#: What section 10 forbids, by full module key. 'anchorage' as a bare
#: substring would also match 'rft.core.column_anchorage' if one is ever
#: written, and a guard that fires on a name it was not aimed at gets
#: relaxed rather than fixed.
FORBIDDEN = "rft.core.anchorage"


def _column_modules():
    """Every `rft.core.column_*` module, by walking the package."""
    names = []
    for entry in sorted(os.listdir(CORE_DIR)):
        if entry.startswith("column_") and entry.endswith(".py"):
            names.append("rft.core." + entry[:-3])
    assert names, "no column modules found -- has the layout moved?"
    return names


def _import_graph_of(module_name):
    """Every `rft.` module loaded by importing ``module_name`` alone."""
    code = (
        "import sys; sys.path.insert(0, %r); import %s; "
        "print(' '.join(sorted(k for k in sys.modules "
        "if k.startswith('rft.'))))" % (LIB_ROOT, module_name))
    finished = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True)
    assert finished.returncode == 0, (
        "importing %s failed:\n%s" % (module_name, finished.stderr))
    return set(finished.stdout.split())


@pytest.mark.parametrize("module_name", _column_modules())
def test_no_column_module_pulls_in_anchorage(module_name):
    """Section 10, as a property of what actually gets imported.

    Nothing was ever miscalculated by the old chain -- no anchorage
    function was evaluated. The rule exists to stop the coupling BEFORE
    something comes to rely on it, which is why an unused import still
    counts as a violation.
    """
    graph = _import_graph_of(module_name)
    assert FORBIDDEN not in graph, (
        "%s pulls in %s. The chain is not necessarily direct -- check the "
        "whole path, which is how this was missed the first time. Loaded: "
        "%s" % (module_name, FORBIDDEN, sorted(graph)))


def test_the_walk_finds_the_modules_we_know_exist():
    """Guards the guard. A walk that quietly found nothing would make
    every assertion above vacuous, and vacuous guards are worse than
    absent ones because they read as coverage."""
    found = set(_column_modules())
    for expected in ("rft.core.column_inputs", "rft.core.column_plan",
                     "rft.core.column_roof", "rft.core.column_report"):
        assert expected in found, "%s not found by the walk" % expected


def test_the_check_would_actually_FAIL_on_a_violation():
    """The assertion above is only worth something if the mechanism it
    uses can see a violation at all. `rft.core.guards` is a module that
    genuinely does import anchorage, so it stands in for a column module
    that had gone wrong.
    """
    graph = _import_graph_of("rft.core.guards")
    assert FORBIDDEN in graph, (
        "rft.core.guards imports anchorage directly; if this cannot see "
        "it, the guard above proves nothing")
