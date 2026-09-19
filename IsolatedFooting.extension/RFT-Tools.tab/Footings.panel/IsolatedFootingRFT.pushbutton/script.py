# -*- coding: utf-8 -*-
"""IsolatedFootingRFT -- bottom-mesh tracer-bullet vertical slice.

Spec Ref: specs/isolated-footing.md Sec 11 item 2. Places ONE mesh_bar_x
bar and ONE mesh_bar_y bar (straight case, no hooks) on a picked isolated
footing, using the API pattern
docs/footing/verification/issue-197-footing-tracer-bullet.md Sec 1
confirmed by a kept write.

SCOPE: this ticket (#198) is core math + the composing module + this
tracer-bullet placement -- NOT a review/report UI. A modeless Review
window, hook logic (#199), L-shape alternation, top mesh, dowels and ties
are later tickets, following the same tracer-bullet-first order the beam
and column tools used (spec Sec 11).

Every input below is asked one at a time and the whole placement happens
in ONE transaction, so a failure anywhere leaves the model exactly as it
was (this repo's transaction hard rule).
"""

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

from rft.core.footing_plan import FootingInputs, build_footing_plan
from rft.revit.bar_types import bar_type_diameter_mm, bar_type_options
from rft.revit.footing_mesh import place_straight_bottom_mesh
from rft.revit.units import internal_to_mm

TRANSACTION_NAME = "Isolated Footing RFT -- bottom mesh (straight case)"

logger = script.get_logger()


def _ask_mm(prompt, default_mm):
    value = forms.ask_for_string(
        default=str(default_mm), prompt=prompt,
        title="Isolated Footing RFT")
    if value is None:
        return None
    return float(value)


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

    a_mm = _ask_mm("Footing dimension a, mm (X-direction)", 1800.0)
    b_mm = _ask_mm("Footing dimension b, mm (Y-direction)", 1200.0)
    cover_mm = _ask_mm("Side cover, mm", 50.0)
    footing_thickness_mm = _ask_mm("Footing thickness, mm", 450.0)
    bottom_cover_mm = _ask_mm("Bottom cover, mm", 50.0)
    top_cover_mm = _ask_mm("Top cover, mm", 50.0)
    x_offset_mm = _ask_mm("Column-face clear offset X, mm", 300.0)
    y_offset_mm = _ask_mm("Column-face clear offset Y, mm", 150.0)
    ld_multiplier = _ask_mm(
        "Development length multiplier (LD = multiplier x db)", 40.0)

    if None in (a_mm, b_mm, cover_mm, footing_thickness_mm,
                bottom_cover_mm, top_cover_mm, x_offset_mm, y_offset_mm,
                ld_multiplier):
        return

    bar_x_type = _ask_bar_type(revit.doc, "mesh_bar_x type (X-direction)")
    if bar_x_type is None:
        return
    bar_y_type = _ask_bar_type(revit.doc, "mesh_bar_y type (Y-direction)")
    if bar_y_type is None:
        return

    mesh_bar_x_dia_mm = bar_type_diameter_mm(bar_x_type, internal_to_mm)
    mesh_bar_y_dia_mm = bar_type_diameter_mm(bar_y_type, internal_to_mm)

    inputs = FootingInputs(
        a_mm=a_mm, b_mm=b_mm, cover_mm=cover_mm,
        footing_thickness_mm=footing_thickness_mm,
        bottom_cover_mm=bottom_cover_mm, top_cover_mm=top_cover_mm,
        mesh_bar_x_dia_mm=mesh_bar_x_dia_mm,
        mesh_bar_y_dia_mm=mesh_bar_y_dia_mm,
        x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm,
        ld_multiplier=ld_multiplier)

    try:
        plan = build_footing_plan(inputs)
    except ValueError as gap:
        forms.alert(str(gap), title="Isolated Footing RFT")
        return

    transaction = Transaction(revit.doc, TRANSACTION_NAME)
    transaction.Start()
    try:
        bar_x, bar_y = place_straight_bottom_mesh(
            revit.doc, footing, plan.bottom_mesh, bar_x_type, bar_y_type)
    except Exception as ex:
        transaction.RollBack()
        logger.error("Isolated Footing RFT placement failed: %s", ex)
        forms.alert("Placement failed: %s" % ex,
                     title="Isolated Footing RFT")
        return
    transaction.Commit()

    forms.alert(
        "Placed mesh_bar_x (id %s) and mesh_bar_y (id %s)."
        % (bar_x.Id, bar_y.Id),
        title="Isolated Footing RFT")


main()
