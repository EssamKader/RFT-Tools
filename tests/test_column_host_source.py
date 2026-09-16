# -*- coding: utf-8 -*-
"""``rft.revit.column_host`` checked as SOURCE, because it cannot be run here.

The module imports ``Autodesk.Revit.DB`` and ``System.Collections.Generic``,
so plain CPython cannot import it and no test in this suite ever has. That
gap is real and is tracked separately -- these guards are not a substitute
for a mock-adapter suite, they are the one class of defect that can be
caught by reading the text.

## Why this file exists at all

``column/v0.1.0-rc1`` opened on a live host and the first click failed:

    Pick column failed -- AttributeError: Name

``Autodesk.Revit.DB.ElementType`` re-declares ``Name`` with a **setter and
no getter**, hiding the readable ``Element.Name`` beneath it. IronPython's
binder exposes only the most-derived property, so ``.Name`` on ANY
``ElementType`` subclass raises ``AttributeError`` -- while C# reads it
happily, which is why reflection, not a Revit exception, is what finally
named it.

The beam tool had already hit this, documented at length on
``rft.revit.bar_types.element_name`` and in ``tests/fake_revit_api.py``
("``RebarBarType``... ``RebarHookType``... it killed the picker in
v0.1.0-rc3"). The column then re-introduced it on two DIFFERENT
``ElementType`` subclasses -- ``FamilySymbol`` and ``RebarCoverType`` --
because the knowledge lived in a docstring beside the beam's own types
rather than in a guard that reads every adapter.

So the guard is written against the RULE, not against the two names that
broke: any ``.Name`` read in this module must be on an object whose ``Name``
is declared by ``Element``, and every such object is listed here with the
live evidence for it.

## Evidence (Revit 2024.3, reflected on the live model, this ticket)

Readable -- ``Name`` declared by ``Element``, ``CanRead=True``::

    Family      "M_Concrete-Rectangular-Column"
    Level       "Level 1"
    View3D      "{3D}"

NOT readable -- ``Name`` declared by ``ElementType``, ``CanRead=False``::

    FamilySymbol     Element.Name == "450 x 600mm"
    RebarCoverType   Element.Name == "Interior (framing, columns)"

For those two, ``SYMBOL_NAME_PARAM`` returns the identical string and is
what ``element_name`` reads. ``Family`` is deliberately NOT routed through
``element_name``: its ``SYMBOL_NAME_PARAM`` is present but **empty**, so
doing so would silently degrade a working name to ``<unnamed, id N>``.
"""

import ast
import io
import os

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HOST_PATH = os.path.join(REPO_ROOT, "RFT.lib", "rft", "revit", "column_host.py")

#: Every expression in this module allowed to read ``.Name`` directly,
#: each one an object whose ``Name`` is declared by ``Element`` and proven
#: readable live (see the module docstring). A new entry is a claim about
#: the API and needs its own live evidence -- which is the point: the list
#: is short and adding to it is deliberate.
ELEMENT_NAME_IS_READABLE = frozenset([
    "level.Name",
    "view.Name",
    "symbol.Family.Name",
    "element.Symbol.Family.Name",
])

#: The two reads that broke on the host, kept by name so the specific
#: regression is named in the failure and not only the general rule.
KNOWN_ELEMENT_TYPE_READS = {
    "element.Symbol.Name": "FamilySymbol",
    "cover_type.Name": "RebarCoverType",
}


def _source():
    return io.open(HOST_PATH, encoding="utf-8").read()


def _name_reads(source):
    """Every ``<expr>.Name`` READ in the module, as source text.

    Loads only: an assignment to ``.Name`` would be a write, which is the
    half of the property that does exist on ``ElementType``.
    """
    tree = ast.parse(source)
    reads = []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Attribute)
                and node.attr == "Name"
                and isinstance(node.ctx, ast.Load)):
            segment = ast.get_source_segment(source, node)
            if segment is not None:
                reads.append(segment)
    return reads


def test_no_dot_Name_is_read_on_an_ElementType():
    """The guard that would have caught the rc1 failure before deployment.

    Stated as an allow-list rather than a deny-list of the two classes that
    broke: ``ElementType`` has many subclasses and the next one to arrive
    in this adapter -- a ``WallType``, a ``FloorType`` -- fails exactly the
    same way, so a guard naming only ``FamilySymbol`` and
    ``RebarCoverType`` would let it through.
    """
    unexpected = sorted(set(_name_reads(_source())) - ELEMENT_NAME_IS_READABLE)
    assert not unexpected, (
        "column_host.py reads .Name on {!r}. If that object is an "
        "ElementType subclass (FamilySymbol, RebarCoverType, WallType, "
        "...) this raises AttributeError: Name under IronPython, because "
        "ElementType hides Element.Name with a setter-only property -- the "
        "defect that broke column/v0.1.0-rc1 on its first live click. Use "
        "rft.revit.bar_types.element_name(), which reads SYMBOL_NAME_PARAM. "
        "If the object's Name IS declared by Element, add it to "
        "ELEMENT_NAME_IS_READABLE together with the live evidence."
        .format(unexpected))


@pytest.mark.parametrize("expression,revit_class",
                         sorted(KNOWN_ELEMENT_TYPE_READS.items()))
def test_the_two_reads_that_broke_the_live_host_are_gone(expression, revit_class):
    """Named individually, so a regression says WHICH one came back."""
    assert expression not in _source(), (
        "{} is an ElementType subclass, so {} raises AttributeError: Name "
        "on a live host. This exact read broke column/v0.1.0-rc1."
        .format(revit_class, expression))


def test_element_name_is_imported_from_the_beam_s_verified_helper():
    """Not re-implemented here.

    ``bar_types.element_name`` carries the live verification and the
    reason. A second copy in this module would be a second place for the
    knowledge to go stale, which is how the defect arrived in the first
    place.
    """
    source = _source()
    assert "from .bar_types import element_name" in source, (
        "column_host must import element_name from rft.revit.bar_types "
        "rather than re-deriving a type name, so the live evidence and the "
        "workaround stay in one place.")


def test_the_cover_type_name_goes_through_element_name():
    """The read the user's own column exercised on the first click."""
    assert "element_name(cover_type)" in _source(), (
        "read_cover_mm must resolve the cover type's name through "
        "element_name -- RebarCoverType is an ElementType.")


def test_the_type_name_goes_through_element_name():
    assert "element_name(element.Symbol)" in _source(), (
        "read_column must resolve the type name through element_name -- "
        "FamilySymbol is an ElementType.")


def test_the_family_name_does_NOT_go_through_element_name():
    """The opposite mistake, and it is not hypothetical -- it was made and
    reverted while fixing this.

    ``Family`` is not an ``ElementType``; its ``Name`` reads correctly. Its
    ``SYMBOL_NAME_PARAM`` exists but is EMPTY, so routing it through
    ``element_name`` returns ``<unnamed, id N>`` -- a working read replaced
    by a placeholder, and one that no test would notice because nothing
    asserts the family name's content.
    """
    source = _source()
    assert "element_name(element.Symbol.Family)" not in source, (
        "Family.SYMBOL_NAME_PARAM is empty on a live host, so element_name "
        "degrades a perfectly good Family.Name to a placeholder.")
    assert "element.Symbol.Family.Name" in source, (
        "the family name is read directly, because Family declares Name on "
        "Element where it is readable.")


# ---------------------------------------------------------------------------
# Ray origins: Location.Point.Z is not the column's elevation (rc2 defect)
# ---------------------------------------------------------------------------
#
# Measured live on four columns in the test model, two of them standing on
# Level 2 and spanning 3000-6000 mm:
#
#     421967  Zspan    0..3000   Location.Point.Z = 0
#     422078  Zspan 3000..6000   Location.Point.Z = 0     <-- upper storey
#     422316  Zspan    0..3000   Location.Point.Z = 0
#     422840  Zspan 3000..6000   Location.Point.Z = 0     <-- upper storey
#
# Every ray built from ``Location.Point.Z`` therefore fires at roughly the
# same height whatever column is picked. Two failures followed, and the
# second is the one that matters:
#
#   * the view self-test's ray passed UNDERNEATH an upper-storey column and
#     hit the one below, so every 3D view was declared blind and the tool
#     refused a column it could see perfectly well;
#   * the support search returned 2700 mm -- the GROUND floor's soffit --
#     for a column whose real top support is at 5700 mm. A refusal is
#     visible. A confident wrong elevation is not.


def test_no_ray_origin_is_built_from_Location_Point_Z():
    """The rc2 defect, stated as the rule that prevents it.

    ``Location.Point`` is still read -- it carries the column's PLAN
    position, which is correct and needed. What must never come from it is
    a Z.
    """
    source = _source()
    offenders = [line.strip() for line in source.splitlines()
                 if "point.Z" in line and not line.strip().startswith("#")]
    assert not offenders, (
        "column_host.py builds a ray origin from {!r}. A structural "
        "column's Location.Point reports Z = 0 whatever storey it stands "
        "on (measured live on four columns), so this fires every ray at "
        "the project base: it refused an upper-storey column as invisible "
        "and reported the ground floor's soffit as its top support. Take "
        "the height from vertical_extent_internal() instead."
        .format(offenders))


def test_the_vertical_extent_comes_from_the_bounding_box():
    assert "box = element.get_BoundingBox(None)" in _source(), (
        "vertical_extent_internal must read the column's own solid extent; "
        "it is the only source in this module for where the column "
        "actually is vertically.")


def test_the_view_self_test_fires_at_the_column_s_mid_height():
    """Mid-height, not either end: an origin at exactly ``max_z`` or
    ``min_z`` sits on the boundary, and a face-grazing ray is the kind of
    thing that works in one model and not the next."""
    source = _source()
    assert "probe_z = 0.5 * (min_z + max_z)" in source
    assert "probe_z)" in source, (
        "find_search_view must fire its self-test ray at the column's "
        "mid-height so it meets the column wherever it stands.")


def test_the_support_rays_start_inside_the_column_s_own_ends():
    source = _source()
    assert "origin = DB.XYZ(point.X, point.Y, max_z - inset)" in source, (
        "the upward search must start just inside the column's own top, "
        "so the first face it meets is the soffit supporting THIS column.")
    assert "origin = DB.XYZ(point.X, point.Y, min_z + inset)" in source, (
        "the downward search must start just inside the column's own base.")


def test_a_short_column_cannot_invert_its_two_ray_origins():
    """``_inset_internal`` scales down rather than letting the upward ray
    start below the downward one -- which would search the wrong direction
    at both ends and report two plausible, swapped elevations."""
    assert "span / 4.0" in _source(), (
        "the inset must scale with the column's span; a fixed clearance "
        "inverts the two origins on a column shorter than four of them.")
