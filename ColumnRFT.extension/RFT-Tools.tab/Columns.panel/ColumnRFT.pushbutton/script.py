# -*- coding: utf-8 -*-
"""Column RFT -- the window shell (issue #87).

Picks a column, refuses the ones spec section 0 puts out of scope, and
shows what was read. It places NOTHING: the longitudinal inputs (#88), the
tie topology (#89, blocked on Q11), the sketch (#90) and the Review report
(#91) are separate tickets, and their tabs are present but disabled so the
window's shape is the shape it will keep.

## Why this file stays thin

Every judgement lives in ``rft.core.column_host_rules`` (pure, unit-tested)
and every Revit read in ``rft.revit.column_host`` (the adapter). This
script does three things only: dispatch to an API context, call the
adapter, and put strings into TextBlocks. That is the split
`REUSE_GUIDELINES.md` requires, and it is why #87's refusals were tested
before a host ever saw them.

## The two settings that are not visible in this file

- **MODELESS** (``window.show()``, never ``ShowDialog()``). A modal window
  disables every other top-level window in the process, Revit's included,
  so ``PickObject`` could never receive a viewport click.
- **``engine: persistent: true``** in ``bundle.yaml``. Without it pyRevit
  tears the IronPython engine down when this script returns; the window
  survives as a CLR object and still repaints, but every ``ExternalEvent``
  is raised into a dead engine and silently never delivers. The symptom is
  a button that waits forever with no error. It cost the beam tool a
  release candidate, and reading the script alone cannot reveal it --
  which is why it is named here.
"""

import os

from pyrevit import forms, revit

from rft.core.column_inputs import (
    DEFAULT_HOOK_ANGLE_DEG,
    LS_MODE_CHOICES,
    LS_MODE_DIAMETERS,
    ROLE_LONGITUDINAL,
    ROLE_TIE,
    perimeter_bars,
    role_picker_label,
    splice_length,
    splice_length_report_line,
)
from rft.core.column_spacing import MODE_AUTO, MODE_MANUAL, spacing_plan
from rft.revit.bar_types import (
    bar_type_diameter_mm, bar_type_options, hook_angle_deg,
    hook_type_options, list_stirrup_hook_types,
)
from rft.revit.column_host import ColumnHostError, read_column
from rft.revit.units import internal_to_mm
from rft.ui.inputs import parse_optional_positive_int, parse_positive_float
from rft.ui.shared_styles import window_xaml

#: Tabs that stay disabled until a column has been accepted. Named once,
#: here, so "enable everything" and "disable everything" cannot drift
#: apart -- the beam tool's A35 rule, applied before there is anything to
#: enable.
GATED_TAB_NAMES = ("longitudinal_tab", "ties_tab", "review_tab")

#: Read-outs cleared on every pick. Listed rather than cleared one by one
#: for the same reason: a field added to the XAML and forgotten here shows
#: the PREVIOUS column's number beside the new column's name.
READOUT_NAMES = ("type_tb", "section_tb", "narrow_wide_tb", "cover_tb",
                 "base_tb", "top_tb", "clear_height_tb")

PROVENANCE_NAMES = ("section_source_tb", "cover_source_tb", "base_source_tb",
                    "top_source_tb", "clear_height_source_tb", "notes_tb",
                    "total_bars_source_tb", "ls_source_tb", "l0_source_tb",
                    "s0_source_tb", "spacing_flags_tb",
                    "longitudinal_status_tb", "ties_status_tb")

#: Read-outs on the two input tabs. Cleared with the rest on a re-pick:
#: a new column changes L0, S0 and the middle-zone maximum, so leaving
#: them is the same defect as leaving the section behind.
DERIVED_NAMES = ("total_bars_tb", "ls_applied_tb", "l0_tb", "s0_tb",
                 "confinement_built_tb", "middle_built_tb", "middle_max_tb")


def _loaded_version():
    """The build actually loaded, from the extension's VERSION file.

    Four ``dirname``s: this file sits in
    ``<ext>/RFT-Tools.tab/Columns.panel/ColumnRFT.pushbutton/``. Degrades
    to a named "unversioned build" rather than raising -- a title is never
    worth failing a load over, and an unversioned build is exactly the
    state worth SEEING. The beam tool learned this the expensive way: a
    candidate that did not contain the fix under test looked identical to
    one that did.
    """
    try:
        extension_root = os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.dirname(os.path.abspath(__file__)))))
        handle = open(os.path.join(extension_root, "VERSION"), "rb")
        try:
            text = handle.read().decode("utf-8").strip()
        finally:
            handle.close()
        return text or "unversioned build"
    except Exception:
        return "unversioned build"


class ColumnWindow(forms.WPFWindow):
    """The four-tab shell. Only the first tab does anything yet."""

    def __init__(self):
        # #86: loaded as a STRING so the shared palette's absolute location
        # can be substituted into the markup before WPF parses it. See
        # rft.ui.shared_styles for why a merge after LoadComponent is too
        # late. That trades away WPFWindow._determine_xaml's bare-filename
        # resolution, so the path is derived here.
        forms.WPFWindow.__init__(
            self,
            window_xaml(os.path.join(
                os.path.dirname(os.path.abspath(__file__)),
                "ColumnWindow.xaml",
            )),
            literal_string=True,
        )
        self.Title = "{} -- {}".format(self.Title, _loaded_version())

        # Wired HERE, not with a Click="..." attribute in the XAML. The
        # window is loaded from a string, which has no code behind, so WPF
        # cannot resolve a handler name in the markup -- it throws "Failed
        # to create a 'Click' from the text 'on_pick_click'" at parse time.
        # Observed live on Revit 2024; the beam window has always done it
        # this way.
        self.pick_column_btn.Click += self.on_pick_click
        self.apply_longitudinal_btn.Click += self.on_apply_longitudinal_click
        self.apply_ties_btn.Click += self.on_apply_ties_click
        self.mode_a_rb.Checked += self.on_spacing_mode_changed
        self.mode_b_rb.Checked += self.on_spacing_mode_changed

        # Filled once, from the module that owns the choice, so the label
        # and the parse can never disagree about what "diameters" means.
        for _value, label in LS_MODE_CHOICES:
            self.ls_mode_cb.Items.Add(label)
        self.ls_mode_cb.SelectedIndex = 1   # opens on "x bar diameter"

        # R7's grades, in front of the engineer at the moment of choosing.
        self.main_bar_role_lbl.Text = role_picker_label(ROLE_LONGITUDINAL)
        self.tie_bar_role_lbl.Text = role_picker_label(ROLE_TIE)

        self.column = None
        self.column_data = None
        self.bar_type_options = []
        self.hook_type_options = []
        self.longitudinal = None
        self.splice = None
        self.spacing = None
        self._api_call_in_flight = False
        self._reset_column_state()

    # ------------------------------------------------------------- state
    def _reset_column_state(self, message="No column picked yet."):
        """Clear EVERYTHING derived from a column.

        Called before every pick, not after a successful one. A refusal
        discovered halfway through a read must not leave the previous
        column's numbers on screen beside the new column's name -- which is
        precisely what "clear on success" would do.
        """
        self.column = None
        self.column_data = None
        self.column_status_tb.Text = message
        for name in READOUT_NAMES + DERIVED_NAMES:
            getattr(self, name).Text = "--"
        for name in PROVENANCE_NAMES:
            getattr(self, name).Text = ""
        for name in GATED_TAB_NAMES:
            getattr(self, name).IsEnabled = False
        self.main_bar_type_cb.IsEnabled = False
        self.tie_bar_type_cb.IsEnabled = False
        self.longitudinal = None
        self.splice = None
        self.spacing = None

    # ---------------------------------------------------------- dispatch
    def _dispatch_to_revit_context(self, func, action_label):
        """Run ``func`` where Revit's API is legal.

        A modeless window's handlers run OUTSIDE Revit's API context, where
        ``PickObject`` and ``Transaction`` both raise. pyRevit's own
        modeless tool solves this with
        ``revit.events.execute_in_revit_context``, which hands the call to
        an ``ExternalEvent``; that is the precedent followed here rather
        than an inference.

        Two properties of that helper shape this method: it is
        ASYNCHRONOUS and returns nothing, so ``func`` must update the
        window itself; and its handler SWALLOWS exceptions into pyRevit's
        log, so an error would reach the engineer as nothing happening at
        all. Hence the catch-everything below.
        """
        if self._api_call_in_flight:
            return
        self._api_call_in_flight = True
        self.status_tb.Text = "{} -- waiting for Revit...".format(action_label)
        revit.events.execute_in_revit_context(
            self._run_in_revit_context, func, action_label)

    def _run_in_revit_context(self, func, action_label):
        try:
            func()
            if self.status_tb.Text.endswith("waiting for Revit..."):
                self.status_tb.Text = "ready"
        except ColumnHostError as refusal:
            # An EXPECTED outcome, not a crash: a column this tool declines
            # to detail. It gets the reason and nothing else -- no stack
            # trace, no "failed", because nothing failed.
            self._reset_column_state(message="Column refused.")
            self.status_tb.Text = str(refusal)
            forms.alert(str(refusal), title="Column out of scope",
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

    # ------------------------------------------------------------ picking
    def on_pick_click(self, sender, args):
        """WPF click handler. Does no Revit work itself -- it only asks for
        the pick to happen in an API context."""
        self._dispatch_to_revit_context(self._pick_column_in_context,
                                        "Pick column")

    def _pick_column_in_context(self):
        # Reset FIRST, regardless of how far the previous pick got.
        self._reset_column_state()

        column = revit.pick_element(
            message="Select a rectangular concrete column to detail.")
        if column is None:
            self.column_status_tb.Text = "No column picked yet."
            return

        # read_column refuses BEFORE it reads: a window showing numbers for
        # a column it is about to decline is worse than one showing none.
        data = read_column(revit.doc, column)

        self.column = column
        self.column_data = data
        self._populate(data)

    # --------------------------------------------------------- read-outs
    def _populate(self, data):
        section = data["section"]
        extent = data["extent"]

        self.column_status_tb.Text = "Column {} accepted.".format(
            data["element_id"])
        self.type_tb.Text = "{} : {}".format(data["family_name"],
                                             data["type_name"])
        self.section_tb.Text = "{:.0f} x {:.0f} mm".format(
            section.b_mm, section.h_mm)
        self.section_source_tb.Text = (
            "b along HandOrientation, h along FacingOrientation, both from "
            "the type parameters -- never the bounding box")
        self.narrow_wide_tb.Text = "{:.0f} / {:.0f} mm".format(
            section.narrow_mm, section.wide_mm)

        self.cover_tb.Text = "{:.0f} mm".format(data["cover_mm"])
        self.cover_source_tb.Text = (
            "read from the element -- cover type '{}' (amendment A2: never "
            "typed, never defaulted)".format(data["cover_type_name"]))

        base_name, base_z = data["base_level"]
        top_name, top_z = data["top_level"]
        self.base_tb.Text = "{:.0f} mm".format(extent.base_z_mm)
        self.base_source_tb.Text = "{} (level {} at {:.0f} mm)".format(
            extent.base_source, base_name, base_z)
        self.top_tb.Text = "{:.0f} mm".format(extent.top_z_mm)
        self.top_source_tb.Text = "{} (level {} at {:.0f} mm)".format(
            extent.top_source, top_name, top_z)
        self.clear_height_tb.Text = "{:.0f} mm".format(extent.clear_height_mm)
        self.clear_height_source_tb.Text = (
            "measured top-to-base, NOT the Length parameter -- they differ "
            "by the slab thickness")

        self._populate_notes(data)
        self._populate_bar_types()
        self._populate_hook_types()

        for name in GATED_TAB_NAMES:
            getattr(self, name).IsEnabled = True

    def _populate_notes(self, data):
        """The things worth saying out loud about this particular column.

        Each one is a case where the number above is correct but incomplete,
        and where silence would let the user assume more was measured than
        was.
        """
        notes = []
        extent = data["extent"]
        if extent.base_source != "support face":
            notes.append(
                "No support element was found below this column, so the "
                "base is the level elevation. That is normal for a "
                "ground-floor column (case C1) -- foundation dowels are out "
                "of scope.")
        if extent.top_source != "support face":
            notes.append(
                "No support element was found above this column, so the top "
                "is the level elevation rather than a measured soffit.")
        if not data["top_face_cover_is_set"]:
            # Q5, still an owner ruling. SAID, never acted on.
            notes.append(
                "This column's 'Rebar Cover - Top Face' is not set. Nothing "
                "here depends on it -- the ties are measured from 'Other "
                "Faces' -- but open question Q5 has not been answered, so it "
                "is reported rather than assumed.")
        notes.append("Support search used the 3D view '{}'.".format(
            data["search_view_name"]))
        self.notes_tb.Text = "\n".join(notes)

    def _populate_bar_types(self):
        """Fill the two pickers from the project's own bar types.

        Labels carry the type's ACTUAL diameter, because a bar type's name
        routinely disagrees with it -- the live model's ``16M`` is 15.9 mm.
        ``bar_type_options`` is generic and the reuse audit clears it for
        reuse, so this is shared with the beam tool rather than copied.
        """
        options = bar_type_options(revit.doc, internal_to_mm)
        for combo in (self.main_bar_type_cb, self.tie_bar_type_cb):
            combo.Items.Clear()
            for label, _bar_type in options:
                combo.Items.Add(label)
            combo.IsEnabled = True
        self.bar_type_options = options

    def _populate_hook_types(self):
        """Fill BOTH hook dropdowns, separately.

        Section 7 keeps them "structurally separate so one dropdown's
        selection can never silently apply to the other role", so they get
        two `Items` collections rather than one shared source -- the same
        list of options, added twice, deliberately.

        Each opens on a 135 degree entry when the project has one. That is
        a DEFAULT and not a requirement: unlike the beam, nothing here
        refuses another angle, which is why the beam's
        ``hook_angle_guard_message`` is not imported.
        """
        options = hook_type_options(list_stirrup_hook_types(revit.doc))
        self.hook_type_options = options
        candidates = self._default_hook_candidates(options)
        for combo in (self.outer_hook_cb, self.inner_hook_cb):
            combo.Items.Clear()
            for label, _hook_type in options:
                combo.Items.Add(label)
            combo.SelectedIndex = candidates[0] if candidates else (
                0 if options else -1)
        self._note_hook_default(options, candidates)

    @staticmethod
    def _default_hook_candidates(options):
        """Indices of every hook type at the section 7 default angle.

        Matched on the ANGLE read back off the type, never on its name or
        its label text. The live model carries a ``Stirrup/Tie - 45`` whose
        stored style is 0 and a ``Standard - 135 deg.`` in the wrong
        family: names lie, and a substring match on "135" would believe
        them.
        """
        found = []
        for index, (_label, hook_type) in enumerate(options):
            angle = hook_angle_deg(hook_type)
            if angle is not None and abs(angle - DEFAULT_HOOK_ANGLE_DEG) < 0.5:
                found.append(index)
        return found

    def _note_hook_default(self, options, candidates):
        """Say which default was chosen, and say when the choice was not
        obvious.

        This project carries BOTH ``Stirrup/Tie - 135 deg.`` and
        ``Stirrup/Tie Seismic - 135 deg.`` -- two types at the same angle,
        and section 7's rationale specifically discusses seismic practice
        for inner ties. Picking the first silently would be the tool making
        a detailing decision in the dark, so it picks one and SAYS so.
        """
        if not candidates:
            self.ties_status_tb.Text = (
                "No hook type in this project reads back as %.0f degrees, so "
                "both dropdowns opened on the first available type. Section 7 "
                "defaults to %.0f -- check both before placing."
                % (DEFAULT_HOOK_ANGLE_DEG, DEFAULT_HOOK_ANGLE_DEG))
        elif len(candidates) > 1:
            names = ", ".join(options[i][0].split("  --  ")[0]
                              for i in candidates)
            self.ties_status_tb.Text = (
                "This project has %d hook types at %.0f degrees (%s). Both "
                "dropdowns opened on the first; section 7 lets you change "
                "either independently."
                % (len(candidates), DEFAULT_HOOK_ANGLE_DEG, names))

    # ------------------------------------------------------------ inputs
    def on_spacing_mode_changed(self, sender, args):
        """Mode B's two boxes are live only in Mode B.

        An editable box whose value is ignored is a lie the window tells
        every time Mode A is selected.
        """
        manual = bool(self.mode_b_rb.IsChecked)
        self.manual_confinement_tb.IsEnabled = manual
        self.manual_middle_tb.IsEnabled = manual

    def on_apply_longitudinal_click(self, sender, args):
        """Section 1 counts and section 9's Ls. No Revit work, so no
        dispatch: every number here is pure arithmetic on values already
        read."""
        try:
            counts = perimeter_bars(
                parse_optional_positive_int(self.b_face_count_tb.Text,
                                            "Bars per b-face"),
                parse_optional_positive_int(self.h_face_count_tb.Text,
                                            "Bars per h-face"))
            bar_diameter_mm = self._selected_bar_diameter_mm()
            splice = splice_length(
                parse_positive_float(self.ls_value_tb.Text, "Ls"),
                self._selected_ls_mode(), bar_diameter_mm)
        except ValueError as ex:
            self.longitudinal_status_tb.Text = str(ex)
            return

        self.longitudinal = counts
        self.splice = splice
        self.total_bars_tb.Text = "{}".format(counts.total_count)
        self.total_bars_source_tb.Text = (
            "2 x ({} + {}) - 4: the four corner bars are shared between "
            "faces and counted once".format(counts.count_b_face,
                                            counts.count_h_face))
        self.ls_applied_tb.Text = "{:.0f} mm".format(splice.length_mm)
        self.ls_source_tb.Text = splice_length_report_line(splice,
                                                           bar_diameter_mm)
        self.longitudinal_status_tb.Text = "Applied."

    def on_apply_ties_click(self, sender, args):
        """Section 7's two hooks and section 8's spacing."""
        if self.column_data is None:
            self.ties_status_tb.Text = "Pick a column first."
            return
        section = self.column_data["section"]
        extent = self.column_data["extent"]
        mode = MODE_MANUAL if self.mode_b_rb.IsChecked else MODE_AUTO
        try:
            manual_confinement = manual_middle = None
            if mode == MODE_MANUAL:
                manual_confinement = parse_positive_float(
                    self.manual_confinement_tb.Text,
                    "Confinement spacing")
                manual_middle = parse_positive_float(
                    self.manual_middle_tb.Text, "Middle-zone spacing")
            plan = spacing_plan(
                mode,
                clear_height_mm=extent.clear_height_mm,
                narrow_mm=section.narrow_mm,
                wide_mm=section.wide_mm,
                smallest_long_bar_dia_mm=self._selected_bar_diameter_mm(),
                tie_dia_mm=self._selected_tie_diameter_mm(),
                manual_confinement_mm=manual_confinement,
                manual_middle_zone_mm=manual_middle)
        except ValueError as ex:
            self.ties_status_tb.Text = str(ex)
            return

        self.spacing = plan
        self.l0_tb.Text = "{:.0f} mm".format(plan.l0_mm)
        self.l0_source_tb.Text = "max of " + ", ".join(
            "{} {:.0f}".format(c.label, c.value_mm) for c in plan.l0_candidates)
        self.s0_tb.Text = "{:.0f} mm".format(plan.s0_mm)
        self.s0_source_tb.Text = "governed by {} (min of {})".format(
            plan.s0_governing_label,
            ", ".join("{:.0f}".format(c.value_mm) for c in plan.s0_candidates))
        self.confinement_built_tb.Text = "{:.0f} mm".format(
            plan.confinement_spacing_mm)
        self.middle_built_tb.Text = "{:.0f} mm".format(
            plan.middle_zone_spacing_mm)
        self.middle_max_tb.Text = "{:.0f} mm".format(plan.middle_zone_max_mm)

        # Section 8: the flags are shown, and the values are still the ones
        # that will be built. Never "refused", never silently swallowed.
        self.spacing_flags_tb.Text = "\n".join(f.message for f in plan.flags)
        self.ties_status_tb.Text = (
            "Applied (Mode {}).".format(plan.mode)
            + ("" if not plan.flags else
               " {} value(s) exceed the code maximum and will be built as "
               "entered.".format(len(plan.flags))))

    # ------------------------------------------------------- selections
    def _selected_ls_mode(self):
        index = self.ls_mode_cb.SelectedIndex
        if index < 0:
            return LS_MODE_DIAMETERS
        return LS_MODE_CHOICES[index][0]

    def _selected_bar_diameter_mm(self):
        return self._diameter_of(self.main_bar_type_cb)

    def _selected_tie_diameter_mm(self):
        return self._diameter_of(self.tie_bar_type_cb)

    def _diameter_of(self, combo):
        """The selected type's ACTUAL diameter, from the type.

        Never parsed out of the name: the live model's ``16M`` is 15.90 mm
        and its ``25M`` is 25.40 mm -- Imperial bars wearing metric names.
        Returns ``None`` when nothing is selected, and the pure modules
        refuse on that rather than substituting a plausible number.
        """
        index = combo.SelectedIndex
        if index < 0 or index >= len(self.bar_type_options):
            return None
        _label, bar_type = self.bar_type_options[index]
        return bar_type_diameter_mm(bar_type, internal_to_mm)


# The window must outlive main(). A modeless window whose only reference is
# a local goes out of scope the moment the script returns -- the same
# module-level-handle pattern pyRevit's own modeless tools use.
window = None


def main():
    global window
    window = ColumnWindow()
    # MODELESS. ShowDialog() would disable Revit's main window, so
    # PickObject could never receive a viewport click.
    window.show()


if __name__ == "__main__":
    main()
