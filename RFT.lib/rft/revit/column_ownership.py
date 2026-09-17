# -*- coding: utf-8 -*-
"""Issue #117 -- R24/R26 (docs/column/spec-amendments.md, A3, section 13
Placement): "which rebar in this column is ours?"

Nothing here creates or deletes anything -- that is R25's orchestrator,
one transaction, a separate ticket. This module only answers the question
every placement ticket after it depends on: given a host column, which of
its rebar did THIS TOOL place, and which did not.

**Ownership is a visible tag, not hidden data (R26).** Every element the
placer creates gets its host and the tool's mark written into the rebar
``Partition`` parameter -- confirmed live (issue #109/#117) as a writable,
currently-empty ``String`` parameter on ``Rebar``::

    Partition = RFT-COL-422078

**The test is the prefix, ``RFT-COL-``, never the value as a whole.** The
host id after it exists so the value is self-describing in a schedule; a
column copied together with its cage carries a STALE host id and must
still be recognised as ours (R26). Testing by equality would treat that
stale-but-genuinely-ours cage as foreign, which is exactly the case a
prefix test exists to survive.

**Foreign rebar is reported, never deleted (R24).** Anything hosted by the
column whose ``Partition`` does not carry the prefix -- hand-modelled bars,
another tool's output, a colleague's correction, or this tool's own tag
hand-edited away -- is left alone and returned with enough detail for the
Review report to name it: element id, bar type name, quantity.

VERIFIED LIVE (Revit 2024 build 24.3.40.26, RevitAPI 24.3.40.0, column
422078 in ``ColumnRFT.Trail.rvt``). These three were written as SHAPE
UNVERIFIED and have since been probed:

- ``Rebar.LookupParameter("Partition")`` returns a **writable String**
  parameter, and a ``Set`` round-trips: written ``RFT-COL-422078``, read
  back identically, restored to empty on rollback. The accessor is the one
  this module uses, not merely the one it guessed.
- ``BuiltInCategory.OST_Rebar`` filters placed ``Rebar`` through a
  ``FilteredElementCollector``: 99 elements in the document, 4 of them
  hosted by 422078 (three ties and one bar set) — so the collector and the
  ``GetHostId()`` narrowing agree with what is actually there.
- ``Rebar.GetTypeId()`` returns the ``RebarBarType`` (53673), whose name
  reads ``16M`` through :func:`rft.revit.bar_types.element_name`.
  ``element_name`` is used rather than ``.Name`` because ``ElementType.Name``
  is **setter-only** and IronPython exposes only the most-derived property,
  so ``bar_type.Name`` raises ``AttributeError`` on a live host while
  passing against any fake that defines it.

``Rebar.Quantity`` and ``Rebar.GetHostId()`` were already confirmed by
issue #109.
"""

from Autodesk.Revit import DB

from .bar_types import element_name

#: R26's literal parameter name. Never a ``BuiltInParameter`` -- R26 rules
#: out ``Comments`` specifically and confirms ``Partition`` by name; there
#: is no evidence a built-in enum member for it was ever probed.
PARTITION_PARAMETER_NAME = "Partition"

#: R26's ownership test. Read through this constant everywhere, by both the
#: writer and the reader -- a tool that tags with one string and searches
#: for another silently owns nothing, and R23's count would read zero on a
#: cage it placed itself.
OWNERSHIP_PREFIX = "RFT-COL-"


class ColumnOwnershipError(Exception):
    """A rebar element this module cannot tag or recognise, and why."""


def _require(condition, message):
    if not condition:
        raise ColumnOwnershipError(message)


def partition_tag(host_id):
    """R26's value for one host: ``RFT-COL-<hostId>``."""
    return "%s%s" % (OWNERSHIP_PREFIX, host_id)


def _partition_parameter(rebar):
    parameter = rebar.LookupParameter(PARTITION_PARAMETER_NAME)
    _require(
        parameter is not None,
        "Rebar element %s has no 'Partition' parameter, so this tool "
        "cannot mark or recognise its own reinforcement on it (R26)."
        % getattr(getattr(rebar, "Id", None), "IntegerValue", rebar))
    return parameter


def tag_as_ours(rebar, host_id):
    """Writes R26's tag into ``rebar``. Called once per element the placer
    creates, so that a later run's ownership test (:func:`is_ours`) finds
    it again."""
    _partition_parameter(rebar).Set(partition_tag(host_id))


def read_partition(rebar):
    """The rebar's current ``Partition`` value, or ``None`` if unset or
    blank."""
    value = _partition_parameter(rebar).AsString()
    return value if value else None


def is_ours(rebar):
    """R26: ownership is tested by PREFIX, never by the whole string.

    A column copied together with its cage keeps a stale host id in
    ``Partition`` and must still read as ours; only an equality test would
    break on that case.
    """
    value = read_partition(rebar)
    return value is not None and value.startswith(OWNERSHIP_PREFIX)


class ForeignRebar(object):
    """R24: a rebar element this tool did not place, described well enough
    for the Review report to name it -- id, bar type name, quantity."""

    def __init__(self, element_id, bar_type_name, quantity):
        self.element_id = element_id
        self.bar_type_name = bar_type_name
        self.quantity = quantity


def _bar_type_name(doc, rebar):
    bar_type = doc.GetElement(rebar.GetTypeId())
    if bar_type is None:
        return "<unknown bar type>"
    return element_name(bar_type)


def hosted_rebar(doc, host):
    """Every placed ``Rebar`` element whose ``GetHostId()`` is this
    column's own id -- confirmed live (issue #109) that ``GetHostId()``
    reports the host a rebar was created against.
    """
    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_Rebar)
        .WhereElementIsNotElementType())
    host_id = host.Id
    return [rebar for rebar in collector if rebar.GetHostId() == host_id]


def partition_host_rebar(doc, host):
    """R24/R26: split this host's own rebar into ``(ours, foreign)``.

    ``ours`` -- hosted by this column AND tagged with the ``RFT-COL-``
    prefix. R23 counts it, R25 deletes it.

    ``foreign`` -- hosted by this column, anything else. Returned as
    :class:`ForeignRebar` -- never deleted (R24), named in the report.
    """
    ours = []
    foreign = []
    for rebar in hosted_rebar(doc, host):
        if is_ours(rebar):
            ours.append(rebar)
        else:
            foreign.append(ForeignRebar(
                element_id=rebar.Id.IntegerValue,
                bar_type_name=_bar_type_name(doc, rebar),
                quantity=rebar.Quantity,
            ))
    return ours, foreign
