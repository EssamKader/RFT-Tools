# -*- coding: utf-8 -*-
"""Issue #226 -- specs/isolated-footing-batch.md Section 6: "which rebar
on this footing is ours?"

Mirrors ``rft.revit.column_ownership`` EXACTLY IN PATTERN -- the
``Partition``-parameter tagging, the prefix-based ownership test, the
``(ours, foreign)`` split -- but is NOT a literal reuse of that module: its
own ``OWNERSHIP_PREFIX = "RFT-COL-"`` is a hardcoded module constant, not
a parameter, so there is no way to ask it for a footing's own
``RFT-FTG-`` prefix without editing a column-tool file, which this repo's
element-isolation convention (`IsolatedFooting.extension/CONTEXT.md`,
`REUSE_GUIDELINES.md`) forbids. This is a new, footing-specific module
with the SAME shape, per the ticket's own instruction ("reuse the
pattern/module directly IF IT IS GENERIC ENOUGH... rather than forking a
footing-specific copy" -- it is not generic enough, so this is that
fork).

Nothing here creates or deletes anything -- that is the batch
orchestrator's job (``rft.revit.footing_batch``), one transaction, a
separate module. This module only answers the question every placement
step after it depends on: given a host footing, which of its rebar did
THIS TOOL place, and which did not.

``Rebar.LookupParameter("Partition")``/``OST_Rebar``/``GetHostId()``/
``GetTypeId()``/``Quantity`` are the SAME accessors ``column_ownership.py``
already verified live (issue #109/#117) -- a ``Rebar`` element's own shape
does not depend on which tool or which host category placed it, so no new
live-host proof is needed for the accessors themselves, only for the
``RFT-FTG-`` prefix round-tripping the same way ``RFT-COL-`` already did.
"""

from Autodesk.Revit import DB

from .bar_types import element_name

#: Same literal parameter name ``column_ownership.py`` uses -- R26's own
#: finding (never ``Comments``, confirmed ``Partition`` by name) is a fact
#: about the ``Rebar`` class, not about which element hosts it.
PARTITION_PARAMETER_NAME = "Partition"

#: This tool's own ownership prefix -- footing-specific, mirroring R26's
#: ``RFT-COL-`` shape exactly (`specs/isolated-footing-batch.md` Sec 6).
OWNERSHIP_PREFIX = "RFT-FTG-"


class FootingOwnershipError(Exception):
    """A rebar element this module cannot tag or recognise, and why."""


def _require(condition, message):
    if not condition:
        raise FootingOwnershipError(message)


def partition_tag(host_id):
    """This tool's own value for one host: ``RFT-FTG-<hostId>``."""
    return "%s%s" % (OWNERSHIP_PREFIX, host_id)


def _partition_parameter(rebar):
    parameter = rebar.LookupParameter(PARTITION_PARAMETER_NAME)
    _require(
        parameter is not None,
        "Rebar element %s has no 'Partition' parameter, so this tool "
        "cannot mark or recognise its own reinforcement on it."
        % getattr(getattr(rebar, "Id", None), "IntegerValue", rebar))
    return parameter


def tag_as_ours(rebar, host_id):
    """Writes this tool's tag into ``rebar``. Called once per element the
    batch placer creates, so that a later run's ownership test
    (:func:`is_ours`) finds it again."""
    _partition_parameter(rebar).Set(partition_tag(host_id))


def read_partition(rebar):
    """The rebar's current ``Partition`` value, or ``None`` if unset or
    blank."""
    value = _partition_parameter(rebar).AsString()
    return value if value else None


def is_ours(rebar):
    """Ownership is tested by PREFIX, never by the whole string -- same
    reasoning R26 gives for the column tool: a footing copied together
    with its cage keeps a stale host id in ``Partition`` and must still
    read as ours; only an equality test would break on that case.
    """
    value = read_partition(rebar)
    return value is not None and value.startswith(OWNERSHIP_PREFIX)


class ForeignRebar(object):
    """A rebar element this tool did not place, described well enough for
    the batch report to name it -- id, bar type name, quantity."""

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
    footing's own id."""
    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_Rebar)
        .WhereElementIsNotElementType())
    host_id = host.Id
    return [rebar for rebar in collector if rebar.GetHostId() == host_id]


def partition_host_rebar(doc, host):
    """Split this host footing's own rebar into ``(ours, foreign)``.

    ``ours`` -- hosted by this footing AND tagged with the ``RFT-FTG-``
    prefix. The batch's replacement confirmation counts it, its apply
    step deletes it.

    ``foreign`` -- hosted by this footing, anything else. Returned as
    :class:`ForeignRebar` -- never deleted, named in the report.
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
