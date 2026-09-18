# -*- coding: utf-8 -*-
"""The refusal/warning contract every RFT tool shares -- and NOTHING else.

**This module imports nothing.** That is its entire reason to exist, and
any import added here re-creates the defect it was split out to fix.

## Why it was split out (#99, `docs/column/reuse-audit.md` section 3)

`GuardMessage`, the severity constants and :func:`is_blocking` are generic:
a message carrying the condition that triggered it, the spec section it
comes from, and whether it STOPS the run. Every element needs them.

They used to live in `rft.core.guards`, which also owns the beam's section
9 policy and therefore does::

    from .anchorage import free_end_configuration_warning
    from .stirrups import TYPE3_PARKED_MESSAGE

So importing the shared contract dragged in `rft.core.anchorage` -- the one
module the column spec section 10 and `CONTEXT.md` forbid the column tool
from importing **for any reason**. The prohibition is not honoured by never
calling into it: *the import is already the dependency*.

The chain that was measured, not inferred (`import rft.core.column_inputs`
then ``'rft.core.anchorage' in sys.modules`` -> ``True``)::

    rft.core.column_inputs
      -> rft.core.grades
        -> rft.core.guards
          -> rft.core.anchorage

Nothing was miscalculated by it. It is unwanted coupling, filed and fixed
before a future change could come to rely on it -- which is the whole point
of the non-reuse rule.

## What belongs here, and what never will

Here: the shape of a guard message, and the question "does this stop the
run?".

Not here: any guard, any threshold, any message TEXT, and any rule about
any structural element. Those are the element's own -- `rft.core.guards`
keeps the beam's section 9 policy, and the column's live beside the column
modules. A shared module that starts holding one element's rules is how two
tools begin detailing each other's steel.
"""

from collections import namedtuple

# Whether a guard STOPS the run or merely deserves the engineer's
# attention (issue #45, U1).
#
# Until #45 severity was implicit -- it lived in whether the CALL SITE
# happened to follow the message with ``script.exit()``. That worked for
# as long as one could read the call sites, and stopped working the moment
# the three pushbuttons were replaced by one window: the exits went away
# and nothing carried the distinction, so a refusal and a warning became
# indistinguishable to any code that received one.
SEVERITY_BLOCKING = "blocking"
SEVERITY_WARNING = "warning"

#: Declared at every construction site with NO DEFAULT. A default is
#: exactly wrong here: it would silently label whatever a migration
#: missed, and the point is that the label is a statement someone made
#: rather than one that fell out of a field ordering. Omitting it is a
#: TypeError.
GuardMessage = namedtuple(
    "GuardMessage", ["condition", "spec_section", "message", "severity"])


def is_blocking(guard_message):
    """True when this guard STOPS the run.

    A function rather than a comparison spelled out at every call site, so
    that the set of blocking severities can grow (an "unverified" tier has
    already been discussed for A45's unreadable hook angle) without
    hunting down every ``== SEVERITY_BLOCKING`` in the codebase.
    """
    return guard_message.severity == SEVERITY_BLOCKING
