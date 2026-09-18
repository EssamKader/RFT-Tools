# -*- coding: utf-8 -*-
"""Every mutation case must still be able to APPLY its mutation.

## The failure this exists to stop

`tools/prove_guards.py` proves a guard by editing the source, running one
test, and requiring it to fail. If the text it searches for is no longer
there, the edit silently does nothing, the test passes -- and the case
reports as a guard that proved nothing while still reading like coverage.

That is not hypothetical. It has happened repeatedly on this project as
refactors moved the anchored lines, most recently when every tab refusal
was routed through `_refuse_on_tab` and the R23 batch-cancel case stopped
applying. **CI found it, after a six-minute full prover run.** This file
finds the same class of defect in a fraction of a second, and finds it
before the change is pushed.

## Why it reads the module rather than re-parsing the text

Importing gives the real `CASES` list with every path constant already
resolved -- `COL_SCRIPT` is `COL_DIR + "script.py"`, a concatenation that
a naive AST scan skips. A scan written that way missed exactly the case
CI caught, which is the whole argument for doing it this way instead.
"""

import importlib.util
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROVER_PATH = os.path.join(REPO_ROOT, "tools", "prove_guards.py")


def _prover():
    """The prover module, imported without running it.

    It guards its entry point with ``if __name__ == "__main__"``, so an
    import is inert.
    """
    spec = importlib.util.spec_from_file_location("prove_guards_under_test",
                                                  PROVER_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _cases():
    return list(_prover().CASES)


def test_there_are_cases_at_all():
    """Guards the guard: an empty list would make every assertion below
    vacuously true, and vacuous checks are worse than absent ones because
    they read as coverage."""
    assert len(_cases()) > 100, "the prover's case list looks truncated"


@pytest.mark.parametrize("index", range(len(_cases())))
def test_every_mutation_anchor_still_EXISTS_in_the_file_it_targets(index):
    """A case whose anchor has moved cannot mutate anything, so it proves
    nothing -- silently."""
    path, find = _cases()[index][0], _cases()[index][1]
    full = os.path.join(REPO_ROOT, path)
    assert os.path.isfile(full), "%s: no such file" % path
    text = io.open(full, encoding="utf-8").read()
    assert find in text, (
        "prove_guards case %d targets %s, but its anchor is no longer "
        "there -- the mutation would apply nothing and the case would "
        "report as proving a guard it never exercised. Anchor:\n%r"
        % (index, path, find))


@pytest.mark.parametrize("index", range(len(_cases())))
def test_every_mutation_actually_CHANGES_the_file(index):
    """`find` and `replace` being equal is the same defect wearing a
    different hat: the case runs, edits nothing, and the test passes."""
    case = _cases()[index]
    find, replace = case[1], case[2]
    assert find != replace, (
        "prove_guards case %d replaces its anchor with itself" % index)
