# -*- coding: utf-8 -*-
"""IsolatedFootingRFT -- bottom-mesh + dowel-array tracer-bullet slice.

Spec Ref: specs/isolated-footing.md Sec 11 item 2 (bottom mesh);
specs/isolated-footing-dowel-array.md Sec 3 Story 4, Sec 4 (dowel array,
#223). Places ONE mesh_bar_x bar and ONE mesh_bar_y bar (straight case, no
hooks), plus every dowel bar the auto-detected column's own live section
calls for, on a picked isolated footing, using the API pattern
docs/footing/verification/issue-197-footing-tracer-bullet.md Sec 1
confirmed by a kept write.

SCOPE: this ticket (#198, extended by #223) is core math + the composing
module + this tracer-bullet placement -- NOT a review/report UI. A modeless
Review window (#205), hook logic (#199), L-shape alternation, top mesh, and
dowel ties/perimeter tie placement are separate tickets, following the same
tracer-bullet-first order the beam and column tools used (spec Sec 11).

Every input below is asked one at a time and the whole placement (mesh AND
dowel array) happens in ONE transaction, so a failure anywhere -- including
partway through the dowel array loop -- leaves the model exactly as it was
(this repo's transaction hard rule; spec Ref: isolated-footing-dowel-array
Sec 3 Story 4, "roll back the WHOLE transaction").

The column is auto-detected (#220) and its Cw/Cd/cover read live (#221),
and the footing's OWN plan dimensions/thickness/covers are read live off
the picked FamilyInstance (#228) -- all BEFORE any remaining dimension is
asked and before any transaction opens. R7's own ruling ("no manual
pick/typed fallback") and R8's own ruling ("read dimension from revit not
from typed inputs") both apply: a footing with no column above it, or with
a geometry/cover parameter this tool cannot read, refuses immediately,
never reaching a half-asked dialog.
"""

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

from rft.core.footing_plan import FootingInputs, build_footing_plan
from rft.revit.bar_types import bar_type_diameter_mm, bar_type_options
from rft.revit.column_host import ColumnHostError
from rft.revit.footing_dowels import place_dowel_bars
from rft.revit.footing_host import (
    FootingHostError, find_column_above, read_dowel_column_section_mm,
    read_footing_geometry_mm,
)
from rft.revit.footing_mesh import place_straight_bottom_mesh
from rft.revit.units import internal_to_mm

TRANSACTION_NAME = (
    "Isolated Footing RFT -- bottom mesh (straight case) + dowel array")

logger = script.get_logger()


def _ask_mm(prompt, default_mm):
    value = forms.ask_for_string(
        default=str(default_mm), prompt=prompt,
        title="Isolated Footing RFT")
    if value is None:
        return None
    return float(value)


def _ask_count(prompt, default_count):
    """Same one-at-a-time string prompt as ``_ask_mm``, but for a dowel
    face count -- ``perimeter_bar_positions`` (#222's own reuse target)
    indexes a range with this value, so it must be an ``int``, not the
    ``float`` every other ``_ask_mm`` input is."""
    value = forms.ask_for_string(
        default=str(default_count), prompt=prompt,
        title="Isolated Footing RFT")
    if value is None:
        return None
    return int(value)


def _ask_bar_type(document, prompt):
    options = bar_type_options(document, internal_to_mm)
    if not options:
        forms.alert("No RebarBarType found in this document.",
                     title="Isolated Footing RFT")
        return None
    labels = [label for label, _bar_type in options]
    chosen = forms.SelectFromList.show(
        labels, title=prompt, button_name="Select")
    if chosen is None:
        return None
    for label, bar_type in options:
        if label == chosen:
            return bar_type
    return None


def main():
    footing = revit.pick_element("Pick an isolated footing")
    if footing is None:
        return

    # Spec Ref: specs/isolated-footing-dowel-array.md Sec 3 Story 1 (R7) +
    # docs/footing/spec-amendments.md R8. Both run BEFORE any dimension is
    # asked and before any transaction opens, so a footing with no column
    # above it, or missing/unset geometry parameters, refuses immediately
    # rather than after a half-filled dialog.
    try:
        column = find_column_above(revit.doc, footing)
        column_section = read_dowel_column_section_mm(column)
        geometry = read_footing_geometry_mm(footing)
    except (FootingHostError, ColumnHostError) as gap:
        forms.alert(str(gap), title="Isolated Footing RFT")
        return

    x_offset_mm = _ask_mm("Column-face clear offset X, mm", 300.0)
    y_offset_mm = _ask_mm("Column-face clear offset Y, mm", 150.0)
    ld_multiplier = _ask_mm(
        "Development length multiplier (LD = multiplier x db)", 40.0)

    if None in (x_offset_mm, y_offset_mm, ld_multiplier):
        return

    bar_x_type = _ask_bar_type(revit.doc, "mesh_bar_x type (X-direction)")
    if bar_x_type is None:
        return
    bar_y_type = _ask_bar_type(revit.doc, "mesh_bar_y type (Y-direction)")
    if bar_y_type is None:
        return
    dowel_bar_type = _ask_bar_type(revit.doc, "Dowel bar type")
    if dowel_bar_type is None:
        return
    dowel_tie_bar_type = _ask_bar_type(
        revit.doc, "Dowel tie bar type (array spacing only -- the tie "
                   "ladder itself is a separate ticket)")
    if dowel_tie_bar_type is None:
        return

    dowel_ld_multiplier = _ask_mm(
        "Dowel development length multiplier (LD = multiplier x db)", 40.0)
    dowel_count_b_face = _ask_count(
        "Dowel count on each Cw-face, incl. corners", 3)
    dowel_count_h_face = _ask_count(
        "Dowel count on each Cd-face, incl. corners", 3)

    if None in (dowel_ld_multiplier, dowel_count_b_face,
                dowel_count_h_face):
        return

    mesh_bar_x_dia_mm = bar_type_diameter_mm(bar_x_type, internal_to_mm)
    mesh_bar_y_dia_mm = bar_type_diameter_mm(bar_y_type, internal_to_mm)
    dowel_bar_dia_mm = bar_type_diameter_mm(dowel_bar_type, internal_to_mm)
    dowel_tie_dia_mm = bar_type_diameter_mm(
        dowel_tie_bar_type, internal_to_mm)

    inputs = FootingInputs(
        a_mm=geometry.a_mm, b_mm=geometry.b_mm, cover_mm=geometry.cover_mm,
        footing_thickness_mm=geometry.footing_thickness_mm,
        bottom_cover_mm=geometry.bottom_cover_mm,
        top_cover_mm=geometry.top_cover_mm,
        mesh_bar_x_dia_mm=mesh_bar_x_dia_mm,
        mesh_bar_y_dia_mm=mesh_bar_y_dia_mm,
        x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm,
        ld_multiplier=ld_multiplier,
        dowel_bar_dia_mm=dowel_bar_dia_mm,
        dowel_ld_multiplier=dowel_ld_multiplier,
        dowel_tie_dia_mm=dowel_tie_dia_mm,
        dowel_count_b_face=dowel_count_b_face,
        dowel_count_h_face=dowel_count_h_face)

    try:
        plan = build_footing_plan(inputs, column_section=column_section)
    except ValueError as gap:
        forms.alert(str(gap), title="Isolated Footing RFT")
        return

    transaction = Transaction(revit.doc, TRANSACTION_NAME)
    transaction.Start()
    try:
        bar_x, bar_y = place_straight_bottom_mesh(
            revit.doc, footing, plan.bottom_mesh, bar_x_type, bar_y_type)
        dowel_bars = place_dowel_bars(
            revit.doc, footing, plan.dowel, dowel_bar_type)
    except Exception as ex:
        transaction.RollBack()
        logger.error("Isolated Footing RFT placement failed: %s", ex)
        forms.alert("Placement failed: %s" % ex,
                     title="Isolated Footing RFT")
        return
    transaction.Commit()

    forms.alert(
        "Placed mesh_bar_x (id %s), mesh_bar_y (id %s), and %d dowel "
        "bar(s)." % (bar_x.Id, bar_y.Id, len(dowel_bars)),
        title="Isolated Footing RFT")


main()
