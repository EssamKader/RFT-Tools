# -*- coding: utf-8 -*-
"""IsolatedFootingRFT -- the modeless window shell (#205).

Wires everything #198-#228 built into ONE window: pick a footing, its
column auto-detects (#220) and both refuse before any tab enables (R7/
R8), state the mesh/dowel-array inputs, review the plan, then Place (one
footing) or Batch (#226, every footing sharing this footing+column type
pair). Nothing here re-derives a detailing rule -- every number comes
from `rft.core.footing_plan.build_footing_plan`/`rft.revit.footing_batch`,
the SAME functions the report and the placement both read
(REUSE_GUIDELINES.md Sec 1).

## Scope -- what this window does NOT expose, and why

The perimeter-tie bar (#204) has core math (`footing_perimeter_tie`) but
no Revit placement adapter yet (`IsolatedFooting.extension/CONTEXT.md`'s
own "Not yet in" list) -- adding input fields for it here would let an
engineer configure something this tool cannot place. This window wires
what #198-#242 actually PLACE (bottom mesh, the top mesh, the dowel
array, the dowel_tie closed loop, single or batch); it does not
implement new placement logic for the rest, which stays out of scope per
REUSE_GUIDELINES.md Sec 3 ("Zero API Guessing") the same way every other
undelivered piece in this tool has been treated all session.

#242: `dowel_tie`'s own closed-loop shape and Revit placement are now
wired -- `dowel_tie_spacing_tb`/`dowel_tie_hook_type_cb` on the Mesh &
Dowels tab, threaded into `FootingInputs`/`BatchInputs`, and placed by
`rft.revit.footing_dowel_ties.place_dowel_ties` in the SAME transaction
as the bottom mesh/dowels -- only when the resulting plan actually
carries a loop (`plan.dowel_ties.loop is not None`, i.e. a real dowel
array plus a live-read tie bend diameter, per `rft.core.footing_plan.
DowelTiePlan`'s own docstring).

#233 (R13, docs/footing/spec-amendments.md): the top mat (Sec 3 Story 4,
Sec 7) is now wired -- `top_reinforcement_cb`/`top_mat_shape_cb` on the
Mesh & Dowels tab, threaded into `FootingInputs`/`BatchInputs`, and
placed by `rft.revit.footing_mesh.place_straight_top_mesh` in the SAME
transaction as the bottom mesh/dowels. It reuses the SAME `mesh_bar_x`/
`mesh_bar_y` bar types as the bottom mat (Sec 7 names no top-mat-specific
bar type) -- no new bar-type combo was added for it.

## The two settings that are not visible in this file

- **MODELESS** (``window.show()``, never ``ShowDialog()``). A modal
  window disables every other top-level window in the process, Revit's
  included, so ``PickObject`` could never receive a viewport click.
- **``engine: persistent: true``** in ``bundle.yaml``. Without it pyRevit
  tears the IronPython engine down when this script returns; the window
  survives as a CLR object and still repaints, but every
  ``ExternalEvent`` is raised into a dead engine and silently never
  delivers -- a button that waits forever with no error. ColumnRFT's own
  ``bundle.yaml`` records the same lesson; this tool had explicitly
  deferred setting it until a modeless window existed (see this file's
  git history) -- that moment is now.
"""

import os

from pyrevit import forms, revit, script
from Autodesk.Revit.DB import Transaction

from rft.core.footing_plan import FootingInputs, build_footing_plan
from rft.core.footing_plan import MAT_SHAPE_L_ALTERNATING, MAT_SHAPE_U
from rft.core.footing_plan import (
    TOP_REINFORCEMENT_BTM_ONLY, TOP_REINFORCEMENT_TOP_AND_BTM,
)
from rft.core import footing_report
from rft.revit import footing_batch
from rft.revit.bar_types import (
    bar_type_bend_diameter_mm, bar_type_diameter_mm, bar_type_options,
    hook_type_options, list_stirrup_hook_types,
)
from rft.revit.column_host import ColumnHostError
from rft.revit.footing_dowel_ties import place_dowel_ties
from rft.revit.footing_dowels import place_dowel_bars
from rft.revit.footing_host import (
    FootingHostError, find_column_above, read_dowel_column_section_mm,
    read_footing_geometry_mm,
)
from rft.revit.footing_mesh import (
    place_bottom_mesh_bars, place_straight_top_mesh,
)
from rft.revit.units import internal_to_mm
from rft.ui import footing_persistence as ui_persistence
from rft.ui.inputs import (
    parse_optional_positive_float, parse_optional_positive_int,
    parse_positive_float,
)
from rft.ui.shared_styles import window_xaml

TRANSACTION_NAME = (
    "Isolated Footing RFT -- bottom mesh (straight case) + dowel array")

logger = script.get_logger()


class FootingWindow(forms.WPFWindow):
    """The three-tab shell: Footing & Column, Mesh & Dowels, Review."""

    def __init__(self):
        # Loaded as a STRING so the shared palette's absolute location can
        # be substituted into the markup before WPF parses it -- see
        # rft.ui.shared_styles for why a merge after LoadComponent is too
        # late. ColumnRFT's own window uses the identical pattern.
        forms.WPFWindow.__init__(
            self,
            window_xaml(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "FootingWindow.xaml",
            )),
            literal_string=True,
        )

        self.footing = None
        self.column = None
        self.geometry = None
        self.column_section = None
        self.plan = None
        self._footing_inputs = None
        self._batch_inputs = None
        self._bar_types = {}
        self._bar_type_options = []
        self._hook_type_options = []
        self._api_call_in_flight = False

        # Wired HERE, not with a Click="..." attribute in the XAML -- a
        # window loaded from a string has no code behind, so WPF cannot
        # resolve a handler name in the markup (ColumnWindow.xaml's own
        # comment, verified live on Revit 2024).
        self.pick_footing_btn.Click += self.on_pick_click
        self.build_report_btn.Click += self.on_build_report_click
        self.place_btn.Click += self.on_place_click
        self.Closing += self._on_closing

        self._restore_project_inputs()

    # ---------------------------------------------------------- dispatch
    def _dispatch_to_revit_context(self, func, action_label):
        """Run ``func`` where Revit's API is legal -- a modeless window's
        handlers run OUTSIDE Revit's own API context, where ``PickObject``
        and ``Transaction`` both raise. Same
        ``revit.events.execute_in_revit_context`` precedent ColumnRFT's
        own window follows, not an inference.
        """
        if self._api_call_in_flight:
            return
        self._api_call_in_flight = True
        self.status_tb.Text = "{} -- waiting for Revit...".format(
            action_label)
        revit.events.execute_in_revit_context(
            self._run_in_revit_context, func, action_label)

    def _run_in_revit_context(self, func, action_label):
        try:
            func()
            if self.status_tb.Text.endswith("waiting for Revit..."):
                self.status_tb.Text = "ready"
        except (FootingHostError, ColumnHostError) as refusal:
            # An EXPECTED outcome, not a crash -- a footing/column this
            # tool declines to detail (R7/R8's own refusals).
            self._reset_footing_state()
            self.status_tb.Text = str(refusal)
            forms.alert(str(refusal), title="Footing out of scope",
                        warn_icon=True)
        except Exception as ex:
            # NEVER let this reach the ExternalEvent handler, which would
            # log it and show the engineer nothing at all.
            message = "{} failed -- {}: {}".format(
                action_label, type(ex).__name__, ex)
            self.status_tb.Text = message
            forms.alert(message, title="{} failed".format(action_label))
        finally:
            self._api_call_in_flight = False

    def _refuse_on_tab(self, status_control, message):
        """A refusal the engineer cannot see is a silent failure -- every
        tab's own status line, plus the always-visible footer
        ``status_tb`` (ColumnWindow.xaml's own lesson: a refusal written
        only below the fold reads as a button that does nothing)."""
        status_control.Text = message
        self.status_tb.Text = message

    # ------------------------------------------------------------ picking
    def on_pick_click(self, sender, args):
        self._dispatch_to_revit_context(
            self._pick_footing_in_context, "Pick footing")

    def _reset_footing_state(self, message="No footing picked yet."):
        self.footing = None
        self.column = None
        self.geometry = None
        self.column_section = None
        self.plan = None
        self.footing_status_tb.Text = message
        self.footing_ab_tb.Text = "--"
        self.footing_thickness_tb.Text = "--"
        self.footing_cover_tb.Text = "--"
        self.footing_bt_cover_tb.Text = "--"
        self.column_cwcd_tb.Text = "--"
        self.column_ccover_tb.Text = "--"
        self.mesh_dowels_tab.IsEnabled = False
        self.review_tab.IsEnabled = False

    def _pick_footing_in_context(self):
        # Reset FIRST, regardless of how far the previous pick got.
        self._reset_footing_state()

        footing = revit.pick_element(
            message="Select an isolated footing to detail.")
        if footing is None:
            self._refuse_on_tab(self.footing_status_tb,
                                "No footing picked yet.")
            return

        # R7 (#220/#221) then R8 (#228) -- BOTH refuse BEFORE any tab
        # enables and before any reads populate the window: a window
        # showing numbers for a footing it is about to decline is worse
        # than one showing none.
        column = find_column_above(revit.doc, footing)
        column_section = read_dowel_column_section_mm(column)
        geometry = read_footing_geometry_mm(footing)

        self.footing = footing
        self.column = column
        self.geometry = geometry
        self.column_section = column_section
        self._populate_footing_readouts()
        self._populate_bar_type_combos()
        self.mesh_dowels_tab.IsEnabled = True
        self.footing_status_tb.Text = (
            "Footing %s, column %s accepted."
            % (footing.Id.IntegerValue, column.Id.IntegerValue))

    def _populate_footing_readouts(self):
        geometry = self.geometry
        column_section = self.column_section
        self.footing_ab_tb.Text = "%.0f x %.0f mm" % (
            geometry.a_mm, geometry.b_mm)
        self.footing_thickness_tb.Text = "%.0f mm" % (
            geometry.footing_thickness_mm)
        self.footing_cover_tb.Text = "%.0f mm" % geometry.cover_mm
        self.footing_bt_cover_tb.Text = "%.0f / %.0f mm" % (
            geometry.bottom_cover_mm, geometry.top_cover_mm)
        self.column_cwcd_tb.Text = "%.0f x %.0f mm" % (
            column_section.Cw_mm, column_section.Cd_mm)
        self.column_ccover_tb.Text = "%.0f mm" % column_section.Ccover_mm

    # -------------------------------------------------------- bar types
    def _populate_bar_type_combos(self):
        """One shared option list for all four bar-type pickers -- unlike
        ColumnRFT's main/tie split, this tool filters no role out of
        ``bar_type_options``'s own list, so every combo indexes the same
        list (``_selected_bar_type_object`` needs no per-combo dispatch).

        #242: the tie hook-type picker is a SEPARATE list/combo, filtered
        to the Stirrup/Tie family (`bar_types.list_stirrup_hook_types`) --
        a hook type is not a bar type, and offering an unfiltered hook
        list would invite the exact opaque ``InternalException``
        ``list_stirrup_hook_types``'s own docstring names (A45).
        """
        options = bar_type_options(revit.doc, internal_to_mm)
        for combo in (self.mesh_bar_x_type_cb, self.mesh_bar_y_type_cb,
                     self.dowel_bar_type_cb, self.dowel_tie_bar_type_cb):
            combo.Items.Clear()
            for label, _bar_type in options:
                combo.Items.Add(label)
        self._bar_type_options = options

        hook_options = hook_type_options(list_stirrup_hook_types(revit.doc))
        self.dowel_tie_hook_type_cb.Items.Clear()
        for label, _hook_type in hook_options:
            self.dowel_tie_hook_type_cb.Items.Add(label)
        self._hook_type_options = hook_options

        self._restore_bar_type_selections()

    def _selected_bottom_mat_shape_mode(self):
        """#229: ``bottom_mat_shape_cb``'s own three options -> the SAME
        ``None``/``MAT_SHAPE_U``/``MAT_SHAPE_L_ALTERNATING`` values
        ``FootingInputs.bottom_mat_shape_mode`` already accepts (Sec 3
        Story 3/Sec 6's direct user override) -- "Auto" maps to ``None``
        so #199's own per-end LD comparison keeps deciding, exactly the
        default every caller had before this combo existed."""
        index = self.bottom_mat_shape_cb.SelectedIndex
        if index == 1:
            return MAT_SHAPE_U
        if index == 2:
            return MAT_SHAPE_L_ALTERNATING
        return None

    def _selected_top_reinforcement(self):
        """#233 (Sec 3 Story 4, Sec 7): ``top_reinforcement_cb``'s own two
        options -> the SAME ``TOP_REINFORCEMENT_BTM_ONLY``/
        ``TOP_REINFORCEMENT_TOP_AND_BTM`` values ``FootingInputs.
        top_reinforcement`` already accepts -- index 0 (the default) is
        BTM-only, matching the trailing default every caller that
        predates this ticket already got.
        """
        if self.top_reinforcement_cb.SelectedIndex == 1:
            return TOP_REINFORCEMENT_TOP_AND_BTM
        return TOP_REINFORCEMENT_BTM_ONLY

    def _selected_top_mat_shape_mode(self):
        """The top mat's OWN U/L-alternating override -- set independently
        of ``_selected_bottom_mat_shape_mode`` (Sec 7: "set separately,
        never coupled"), same three-option mapping."""
        index = self.top_mat_shape_cb.SelectedIndex
        if index == 1:
            return MAT_SHAPE_U
        if index == 2:
            return MAT_SHAPE_L_ALTERNATING
        return None

    def _selected_bar_type_object(self, combo):
        """The actual ``RebarBarType`` behind a combo -- never parsed out
        of the name (the live model's ``16M`` is 15.90mm, ``25M`` is
        25.40mm)."""
        index = combo.SelectedIndex
        if index < 0 or index >= len(self._bar_type_options):
            return None
        return self._bar_type_options[index][1]

    def _selected_hook_type_object(self, combo):
        """The actual ``RebarHookType`` behind the tie hook-type combo --
        mirrors ``_selected_bar_type_object`` for the SEPARATE, family-
        filtered hook-type list (#242)."""
        index = combo.SelectedIndex
        if index < 0 or index >= len(self._hook_type_options):
            return None
        return self._hook_type_options[index][1]

    # ---------------------------------------------------- mesh & dowels
    def on_build_report_click(self, sender, args):
        """Parses every shared input, builds ``FootingInputs`` from them
        PLUS this footing's own live reads, calls the SAME
        ``build_footing_plan`` the placer will use, and shows the report
        -- WPF-only work, no Revit API call, so this handler does not
        need ``_dispatch_to_revit_context``.
        """
        try:
            x_offset_mm = parse_positive_float(
                self.x_offset_tb.Text, "Column-face clear offset X")
            y_offset_mm = parse_positive_float(
                self.y_offset_tb.Text, "Column-face clear offset Y")
            ld_multiplier = parse_positive_float(
                self.ld_multiplier_tb.Text, "LD multiplier (mesh)")
            dowel_ld_multiplier = parse_positive_float(
                self.dowel_ld_multiplier_tb.Text, "LD multiplier (dowel)")
            mesh_bar_x_spacing_mm = parse_positive_float(
                self.mesh_bar_x_spacing_tb.Text, "mesh_bar_x spacing")
            mesh_bar_y_spacing_mm = parse_positive_float(
                self.mesh_bar_y_spacing_tb.Text, "mesh_bar_y spacing")
            dowel_count_b_face = parse_optional_positive_int(
                self.dowel_count_b_face_tb.Text,
                "Dowel count on each Cw-face")
            dowel_count_h_face = parse_optional_positive_int(
                self.dowel_count_h_face_tb.Text,
                "Dowel count on each Cd-face")
            dowel_splice_length_mm = parse_optional_positive_float(
                self.dowel_splice_length_tb.Text,
                "Splice length Ls (dowel)")
            dowel_tie_spacing_mm = parse_positive_float(
                self.dowel_tie_spacing_tb.Text, "Dowel tie spacing")
        except ValueError as ex:
            self._refuse_on_tab(self.mesh_dowels_status_tb, str(ex))
            return

        if dowel_count_b_face is None or dowel_count_h_face is None:
            self._refuse_on_tab(
                self.mesh_dowels_status_tb,
                "Dowel counts must be given -- the array is always built "
                "from the live column section (R6).")
            return

        mesh_bar_x_type = self._selected_bar_type_object(
            self.mesh_bar_x_type_cb)
        mesh_bar_y_type = self._selected_bar_type_object(
            self.mesh_bar_y_type_cb)
        dowel_bar_type = self._selected_bar_type_object(
            self.dowel_bar_type_cb)
        dowel_tie_bar_type = self._selected_bar_type_object(
            self.dowel_tie_bar_type_cb)
        dowel_tie_hook_type = self._selected_hook_type_object(
            self.dowel_tie_hook_type_cb)
        if None in (mesh_bar_x_type, mesh_bar_y_type, dowel_bar_type,
                    dowel_tie_bar_type):
            self._refuse_on_tab(self.mesh_dowels_status_tb,
                                "Every bar type must be selected.")
            return
        if dowel_tie_hook_type is None:
            self._refuse_on_tab(
                self.mesh_dowels_status_tb,
                "A dowel tie hook type must be selected (#242).")
            return

        mesh_bar_x_dia_mm = bar_type_diameter_mm(
            mesh_bar_x_type, internal_to_mm)
        mesh_bar_y_dia_mm = bar_type_diameter_mm(
            mesh_bar_y_type, internal_to_mm)
        dowel_bar_dia_mm = bar_type_diameter_mm(
            dowel_bar_type, internal_to_mm)
        dowel_tie_dia_mm = bar_type_diameter_mm(
            dowel_tie_bar_type, internal_to_mm)
        # #242: read live, passed alongside `inputs` -- the SAME "read
        # live, pass in as a plain argument" shape `column_section`
        # already established (see `footing_plan.build_footing_plan`'s
        # own docstring).
        dowel_tie_bend_diameter_mm = bar_type_bend_diameter_mm(
            dowel_tie_bar_type, internal_to_mm)

        geometry = self.geometry
        inputs = FootingInputs(
            a_mm=geometry.a_mm, b_mm=geometry.b_mm,
            cover_mm=geometry.cover_mm,
            footing_thickness_mm=geometry.footing_thickness_mm,
            bottom_cover_mm=geometry.bottom_cover_mm,
            top_cover_mm=geometry.top_cover_mm,
            mesh_bar_x_dia_mm=mesh_bar_x_dia_mm,
            mesh_bar_y_dia_mm=mesh_bar_y_dia_mm,
            x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm,
            ld_multiplier=ld_multiplier,
            bottom_mat_shape_mode=self._selected_bottom_mat_shape_mode(),
            dowel_bar_dia_mm=dowel_bar_dia_mm,
            dowel_ld_multiplier=dowel_ld_multiplier,
            dowel_tie_dia_mm=dowel_tie_dia_mm,
            dowel_tie_spacing_mm=dowel_tie_spacing_mm,
            dowel_count_b_face=dowel_count_b_face,
            dowel_count_h_face=dowel_count_h_face,
            mesh_bar_x_spacing_mm=mesh_bar_x_spacing_mm,
            mesh_bar_y_spacing_mm=mesh_bar_y_spacing_mm,
            dowel_splice_length_mm=dowel_splice_length_mm,
            top_reinforcement=self._selected_top_reinforcement(),
            top_mat_shape_mode=self._selected_top_mat_shape_mode())

        try:
            plan = build_footing_plan(
                inputs, column_section=self.column_section,
                dowel_tie_bend_diameter_mm=dowel_tie_bend_diameter_mm)
        except ValueError as ex:
            self._refuse_on_tab(self.mesh_dowels_status_tb, str(ex))
            return

        self.plan = plan
        self._footing_inputs = inputs
        self._bar_types = {
            "mesh_bar_x_type": mesh_bar_x_type,
            "mesh_bar_y_type": mesh_bar_y_type,
            "dowel_bar_type": dowel_bar_type,
            "dowel_tie_bar_type": dowel_tie_bar_type,
            "dowel_tie_hook_type": dowel_tie_hook_type,
        }
        # Spec Ref: specs/isolated-footing-batch.md Sec 1 -- the shared
        # inputs a batch states once, carried as one object so
        # footing_batch never has to remember which caller supplied what.
        self._batch_inputs = footing_batch.BatchInputs(
            x_offset_mm=x_offset_mm, y_offset_mm=y_offset_mm,
            ld_multiplier=ld_multiplier,
            bottom_mat_shape_mode=self._selected_bottom_mat_shape_mode(),
            bar_x_type=mesh_bar_x_type, bar_y_type=mesh_bar_y_type,
            dowel_bar_type=dowel_bar_type,
            dowel_tie_bar_type=dowel_tie_bar_type,
            dowel_tie_hook_type=dowel_tie_hook_type,
            dowel_tie_spacing_mm=dowel_tie_spacing_mm,
            dowel_ld_multiplier=dowel_ld_multiplier,
            dowel_count_b_face=dowel_count_b_face,
            dowel_count_h_face=dowel_count_h_face,
            mesh_bar_x_spacing_mm=mesh_bar_x_spacing_mm,
            mesh_bar_y_spacing_mm=mesh_bar_y_spacing_mm,
            dowel_splice_length_mm=dowel_splice_length_mm,
            top_reinforcement=self._selected_top_reinforcement(),
            top_mat_shape_mode=self._selected_top_mat_shape_mode())

        sections = [
            footing_report.footing_geometry_section(geometry),
            footing_report.column_section_section(self.column_section),
            footing_report.mesh_section(plan),
        ]
        if plan.top_mesh is not None:
            sections.append(footing_report.top_mesh_section(plan))
        sections.append(footing_report.dowel_array_section(plan))
        if plan.dowel_ties is not None:
            sections.append(footing_report.dowel_tie_section(plan))
        sections.append(footing_report.not_yet_placed_section())
        self.report_tb.Text = footing_report.render(sections)
        self.review_tab.IsEnabled = True
        self.tabs.SelectedItem = self.review_tab
        self.mesh_dowels_status_tb.Text = "Plan built -- see Review."
        self.status_tb.Text = "ready"

    # -------------------------------------------------------------- place
    def on_place_click(self, sender, args):
        self._dispatch_to_revit_context(self._place_in_context, "Place")

    def _place_in_context(self):
        if self.batch_cb.IsChecked:
            self._place_batch_in_context()
        else:
            self._place_single_in_context()

    def _place_single_in_context(self):
        """One footing, ONE transaction, all-or-nothing (this repo's own
        transaction hard rule) -- the exact placement sequence #223 wired,
        now called from the window instead of a sequential script.
        """
        doc = revit.doc
        bar_types = self._bar_types
        transaction = Transaction(doc, TRANSACTION_NAME)
        transaction.Start()
        try:
            bars_x, bars_y = place_bottom_mesh_bars(
                doc, self.footing, self.plan.bottom_mesh,
                bar_types["mesh_bar_x_type"], bar_types["mesh_bar_y_type"])
            dowel_bars = place_dowel_bars(
                doc, self.footing, self.plan.dowel,
                bar_types["dowel_bar_type"])
            # #233 (R13): the top mat, same transaction, same footing
            # host as the bottom mesh -- only when the engineer asked for
            # TOP+BTM (self.plan.top_mesh is not None).
            top_bar_x, top_bar_y = None, None
            if self.plan.top_mesh is not None:
                top_bar_x, top_bar_y = place_straight_top_mesh(
                    doc, self.footing, self.plan.top_mesh,
                    bar_types["mesh_bar_x_type"], bar_types["mesh_bar_y_type"])
            # #242: the dowel_tie closed loop, same transaction, same
            # footing host as the bottom mesh/dowels -- only when the
            # plan actually carries a loop (a real dowel array plus a
            # live-read tie bend diameter; see DowelTiePlan's own
            # docstring).
            dowel_ties = []
            if (self.plan.dowel_ties is not None
                    and self.plan.dowel_ties.loop is not None):
                dowel_ties = place_dowel_ties(
                    doc, self.footing, self.plan.dowel_ties,
                    bar_types["dowel_tie_bar_type"],
                    bar_types["dowel_tie_hook_type"])
        except Exception as ex:
            transaction.RollBack()
            message = "Placement FAILED and was rolled back -- {}: {}".format(
                type(ex).__name__, ex)
            logger.error(message)
            self._refuse_on_tab(self.review_status_tb, message)
            forms.alert(message, title="Placement failed -- rolled back")
            return
        transaction.Commit()

        top_mesh_message = ""
        if top_bar_x is not None:
            top_mesh_message = " Placed the top mat's mesh_bar_x/mesh_bar_y."
        dowel_tie_message = ""
        if dowel_ties:
            dowel_tie_message = " Placed %d dowel_tie(s)." % len(dowel_ties)
        message = (
            "Placed %d mesh_bar_x bar(s), %d mesh_bar_y bar(s), and %d "
            "dowel bar(s).%s%s" % (
                len(bars_x), len(bars_y), len(dowel_bars), top_mesh_message,
                dowel_tie_message))
        self.review_status_tb.Text = message
        self.status_tb.Text = message
        forms.alert(message, title="Isolated Footing RFT")

    def _place_batch_in_context(self):
        """Spec Ref: specs/isolated-footing-batch.md Sec 2-6 (#226) --
        collect, read/group, plan/refuse, report, confirm a replacement,
        then place every survivor inside ONE transaction.
        """
        doc = revit.doc
        batch_plan = footing_batch.plan_candidates(
            doc, self.footing, self._batch_inputs)
        existing = footing_batch.read_existing(doc, batch_plan)

        sections = [
            footing_report.batch_group_section(batch_plan.groups),
            footing_report.batch_exclusion_section(batch_plan.exclusions),
            footing_report.batch_replacement_section(existing),
        ]
        report = footing_report.render(sections)
        self.report_tb.Text = report

        replacing = [row for row in existing if row.replaced_count]
        if replacing:
            proceed = forms.alert(
                "{}\nApply will DELETE this tool's own existing elements "
                "on {} footing(s) and rebuild them. Proceed?".format(
                    report, len(replacing)),
                title="Replace existing reinforcement in {} footing(s)?"
                     .format(len(replacing)),
                ok=False, yes=True, no=True)
            if not proceed:
                self._refuse_on_tab(
                    self.review_status_tb,
                    "Batch cancelled -- nothing changed.")
                return

        try:
            result = footing_batch.apply_batch(
                doc, batch_plan, self._bar_types["mesh_bar_x_type"],
                self._bar_types["mesh_bar_y_type"],
                self._bar_types["dowel_bar_type"],
                dowel_tie_bar_type=self._bar_types["dowel_tie_bar_type"],
                dowel_tie_hook_type=self._bar_types["dowel_tie_hook_type"])
        except footing_batch.FootingBatchError as ex:
            self._refuse_on_tab(self.review_status_tb, str(ex))
            forms.alert(str(ex), title="Batch refused")
            return
        except Exception as ex:
            message = "Batch FAILED and was rolled back -- {}: {}".format(
                type(ex).__name__, ex)
            logger.error(message)
            self._refuse_on_tab(self.review_status_tb, message)
            forms.alert(message, title="Batch failed -- rolled back")
            return

        message = "Placed {} footing(s) in {} group(s). {} excluded.".format(
            len(result.per_footing), len(batch_plan.groups),
            len(batch_plan.exclusions))
        self.review_status_tb.Text = message
        self.status_tb.Text = message
        forms.alert(message, title="Isolated Footing RFT Batch")

    # --------------------------------------------------------- persistence
    def _store_project_inputs(self):
        """Remember this project's shared conventions (#205, U10-style).
        Never raises -- failing to save a convenience must not turn into
        a failed Place or a window that cannot close.
        """
        try:
            data = ui_persistence.to_store(
                dict((name, getattr(self, name).Text)
                     for name in ui_persistence.TEXT_FIELDS),
                self._persistable_type_ids())
            script.store_data(
                ui_persistence.SETTINGS_SLOT, data, this_project=True)
        except Exception:
            pass

    def _persistable_type_ids(self):
        ids = {}
        combo_by_field = {
            "mesh_bar_x_type": self.mesh_bar_x_type_cb,
            "mesh_bar_y_type": self.mesh_bar_y_type_cb,
            "dowel_bar_type": self.dowel_bar_type_cb,
            "dowel_tie_bar_type": self.dowel_tie_bar_type_cb,
        }
        for field_name in ui_persistence.TYPE_FIELDS:
            if field_name == "dowel_tie_hook_type":
                # #242: a SEPARATE, family-filtered options list
                # (`_hook_type_options`), not `_bar_type_options` --
                # `_selected_bar_type_object` would index the wrong list.
                hook_type = self._selected_hook_type_object(
                    self.dowel_tie_hook_type_cb)
                if hook_type is not None:
                    ids[field_name] = hook_type.UniqueId
                continue
            combo = combo_by_field.get(field_name)
            bar_type = (self._selected_bar_type_object(combo)
                       if combo is not None else None)
            if bar_type is not None:
                ids[field_name] = bar_type.UniqueId
        return ids

    def _restore_project_inputs(self):
        """Never raises, never half-applies a field -- a settings file is
        not worth failing to open the tool over."""
        try:
            if not script.data_exists(
                    ui_persistence.SETTINGS_SLOT, this_project=True):
                return
            raw = script.load_data(
                ui_persistence.SETTINGS_SLOT, this_project=True)
        except Exception:
            return

        text, self._pending_type_ids = ui_persistence.from_store(raw)
        for name, value in text.items():
            getattr(self, name).Text = value

    def _restore_bar_type_selections(self):
        """Re-select each remembered bar type by ``UniqueId``, matched
        against THIS combo's own freshly-populated options -- a deleted
        type, or one that now belongs to something else, simply fails to
        match and the role stays "not selected" (the normal state of a
        freshly opened window).
        """
        unique_ids = getattr(self, "_pending_type_ids", None)
        if not unique_ids:
            return
        combo_by_field = {
            "mesh_bar_x_type": self.mesh_bar_x_type_cb,
            "mesh_bar_y_type": self.mesh_bar_y_type_cb,
            "dowel_bar_type": self.dowel_bar_type_cb,
            "dowel_tie_bar_type": self.dowel_tie_bar_type_cb,
        }
        for field_name, unique_id in unique_ids.items():
            if field_name == "dowel_tie_hook_type":
                # #242: matched against `_hook_type_options`, the SAME
                # separate list `_persistable_type_ids` reads it from.
                for index, (_label, hook_type) in enumerate(
                        self._hook_type_options):
                    if hook_type.UniqueId == unique_id:
                        self.dowel_tie_hook_type_cb.SelectedIndex = index
                        break
                continue
            combo = combo_by_field.get(field_name)
            if combo is None:
                continue
            for index, (_label, bar_type) in enumerate(
                    self._bar_type_options):
                if bar_type.UniqueId == unique_id:
                    combo.SelectedIndex = index
                    break

    def _on_closing(self, sender, args):
        self._store_project_inputs()


window = None


def main():
    global window
    window = FootingWindow()
    # MODELESS. ShowDialog() would disable Revit's main window, so
    # PickObject could never receive a viewport click.
    window.show()


if __name__ == "__main__":
    main()
