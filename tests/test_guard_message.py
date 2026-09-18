# -*- coding: utf-8 -*-
"""#99 -- the shared refusal contract, and the one rule it must keep.

`rft.core.guard_message` exists so a tool can take `GuardMessage` and the
severity constants WITHOUT taking the module that owns the beam's section
9 policy -- which reaches `rft.core.anchorage`, the module the column spec
section 10 forbids outright.

That property is worth exactly as much as it is enforced, so it is
enforced here against the RESOLVED import graph rather than against the
file's own import lines. Checking the file was what let the original
defect through: `column_inputs.py` never mentioned anchorage, and imported
it anyway, two hops down.
"""

import subprocess
import sys

import pytest

from rft.core.guard_message import (
    GuardMessage, SEVERITY_BLOCKING, SEVERITY_WARNING, is_blocking,
)


def _modules_pulled_in_by(module_name):
    """Every `rft.` module that ends up in ``sys.modules`` after importing
    ``module_name`` -- in a FRESH interpreter.

    A subprocess, not an import here: by the time this test runs, pytest
    has imported most of the package already, so an in-process check would
    find `anchorage` loaded no matter what the module under test does, and
    would pass or fail for reasons unrelated to it.
    """
    code = (
        "import sys; sys.path.insert(0, %r); import %s; "
        "print(' '.join(sorted(k for k in sys.modules "
        "if k.startswith('rft.'))))" % ("RFT.lib", module_name))
    finished = subprocess.run([sys.executable, "-c", code],
                              capture_output=True, text=True)
    assert finished.returncode == 0, finished.stderr
    return set(finished.stdout.split())


def test_the_shared_contract_imports_NOTHING_from_this_package():
    """Its whole reason to exist. Any `rft.` import added here re-creates
    the coupling it was split out to remove -- and would do it silently,
    because nothing would change at the call sites."""
    pulled = _modules_pulled_in_by("rft.core.guard_message")
    # Its own package chain is not a dependency -- Python registers the
    # parent packages for any import at all. Anything ELSE is.
    extra = pulled - {"rft", "rft.core", "rft.core.guard_message"}
    assert not extra, (
        "rft.core.guard_message must stand alone; it pulled in %s"
        % sorted(extra))


def test_the_contract_still_carries_all_four_fields_with_NO_default():
    """The severity is stated at every construction site, never defaulted:
    a default would silently label whatever a migration missed."""
    with pytest.raises(TypeError):
        GuardMessage(condition="c", spec_section="s", message="m")


def test_is_blocking_is_a_FUNCTION_not_a_comparison_at_each_call_site():
    blocking = GuardMessage("c", "s", "m", SEVERITY_BLOCKING)
    warning = GuardMessage("c", "s", "m", SEVERITY_WARNING)
    assert is_blocking(blocking)
    assert not is_blocking(warning)


def test_the_beam_s_own_imports_still_work_through_guards():
    """The split must not break a single beam call site: `rft.core.guards`
    re-exports the contract unchanged."""
    from rft.core import guards
    assert guards.GuardMessage is GuardMessage
    assert guards.SEVERITY_BLOCKING == SEVERITY_BLOCKING
    assert guards.SEVERITY_WARNING == SEVERITY_WARNING
    assert guards.is_blocking is is_blocking
