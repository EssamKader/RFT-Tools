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

# The renderer's ONLY WPF imports. Plain WPF/CLR types, not the Revit API,
# so constructing them needs no API context -- same as every other direct
# control write in this file. Wrapped for the same reason the beam tool
# wraps them: if this import ever fails on a live host, the WINDOW must
# still open. The sketch is a verification surface, not a load-bearing
# part of placement, and a column that cannot be drawn can still be
# reviewed.
try:
    from System.Windows import Point
    from System.Windows.Media import PointCollection
    from System.Windows.Controls import TextBlock as WpfTextBlock
    from System.Windows.Controls import Canvas as WpfCanvas
    from System.Windows.Shapes import Ellipse as WpfEllipse
    from System.Windows.Shapes import Line as WpfLine
    from System.Windows.Shapes import Polygon as WpfPolygon
    _WPF_SHAPES_AVAILABLE = True
except Exception:
    _WPF_SHAPES_AVAILABLE = False

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
from rft.core.column_layout import tier_summary
from rft.core.column_plan import (
    MODE_AUTO, MODE_MANUAL, bar_plan, complete_plan, is_blocked,
)
from rft.core.column_report import build_report, render
from rft.revit.bar_types import (
    bar_type_bend_diameter_mm, bar_type_diameter_mm, bar_type_options,
    hook_angle_deg, hook_type_options, list_stirrup_hook_types,
)
from rft.revit.column_host import ColumnHostError, read_column
from rft.revit import column_placer
from rft.revit.units import internal_to_mm
from rft.ui.column_sketch import (
    cross_section_captions, cross_section_shapes, zone_strip_shapes,
)
from rft.ui.column_sketch_palette import brush_key_for_style
from rft.ui.inputs import parse_optional_positive_int, parse_positive_float
from rft.ui.sketch_layout import LabelBox, estimate_text_size_px, place_labels
from rft.ui.sketch_shapes import (
    SketchCircle, SketchLine, SketchPolygon, SketchText,
)
from rft.ui.shared_styles import window_xaml

#: Tabs that stay disabled until a column has been accepted. Named once,
#: here, so "enable everything" and "disable everything" cannot drift
#: apart -- the beam tool's A35 rule, applied before there is anything to
#: enable.
GATED_TAB_NAMES = ("longitudinal_tab", "ties_tab", "review_tab",
                   "sketch_tab")

#: A bar's POSITION is exact; its drawn size is a symbol. Without a
#: floor, a 16 mm bar on a 600 mm section fitted to this canvas is about
#: two pixels across -- correct to scale, and invisible.
MIN_BAR_RADIUS_PX = 3.0
#: Must match rft.ui.sketch_layout's own default: that module estimates
#: a label's width from this number, and an estimate made at one size
#: and drawn at another clips the tails.
SKETCH_FONT_SIZE_PX = 11.0

#: Read-outs cleared on every pick. Listed rather than cleared one by one
#: for the same reason: a field added to the XAML and forgotten here shows
#: the PREVIOUS column's number beside the new column's name.
READOUT_NAMES = ("type_tb", "section_tb", "narrow_wide_tb", "cover_tb",
                 "base_tb", "top_tb", "clear_height_tb")

PROVENANCE_NAMES = ("section_source_tb", "cover_source_tb", "base_source_tb",
                    "top_source_tb", "clear_height_source_tb", "notes_tb",
                    "total_bars_source_tb", "ls_source_tb", "l0_source_tb",
                    "s0_source_tb", "spacing_flags_tb",
                    "longitudinal_status_tb", "ties_status_tb",
                    "report_tb", "tie_findings_tb", "place_status_tb")

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
        self.build_report_btn.Click += self.on_build_report_click
        self.apply_place_btn.Click += self.on_apply_click
        # The sketch redraws when the canvas is first sized, which is
        # after the window is laid out -- a canvas has no ActualWidth
        # before that, and scaling to zero draws nothing.
        self.section_canvas.SizeChanged += self.on_canvas_size_changed
        self.strip_canvas.SizeChanged += self.on_canvas_size_changed

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
        #: The TIE picker's list: every type in the project.
        self.bar_type_options = []
        #: The LONGITUDINAL picker's list: T-named types only (#133).
        self.main_bar_type_options = []
        self.hook_type_options = []
        self.bars = None
        self.plan = None
        self.longitudinal = None
        self.splice = None
        self.spacing = None
        self.ladder = None
        self.layout = None
        self.ties = None
        self.tie_findings = []
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
        self.bars = None
        self.plan = None
        self.longitudinal = None
        self.splice = None
        self.spacing = None
        self.ladder = None
        self.layout = None
        self.ties = None
        self.tie_findings = []
        self.review_status_tb.Text = "Apply the bar and tie inputs first."
        self.place_status_tb.Text = "Apply the bar and tie inputs first."
        self._clear_canvases()

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
        routinely disagrees with it -- the live model's ``16M`` is 15.9 mm
        -- and, since #133, its yield strength, because the name disagrees
        with that too: every ``M`` type in the live model is ASTM A615M
        **Grade 420**, where the M means METRIC, not mild.

        BOTH pickers get EVERY type (#135, withdrawing #133's filter).

        R27 briefly filtered the longitudinal picker to T-named types. On
        the live model that emptied it: `ColumnRFT.Trail.rvt` holds eleven
        bar types, all named `..M`, all ASTM A615M Grade 420. The filter
        was written against a probe of a DIFFERENT document that happened
        to be active on the connection, and no T type has ever existed
        here.

        The grade is still SHOWN beside every type, which is the half that
        survives: hiding a bar the engineer needs is worse than showing one
        they must judge, and the label is what lets them judge it.

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
        self.main_bar_type_options = options

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

        # One composing call (#110). The window states the inputs and
        # reads the plan back; it never builds the perimeter itself, so
        # the sketch cannot draw a layout the report denies.
        self.bars = bar_plan(
            self.column_data, counts, splice, bar_diameter_mm,
            self._selected_tie_diameter_mm(),
            self._selected_bar_type_name(self.main_bar_type_cb),
            self._selected_bar_type_name(self.tie_bar_type_cb))
        self.longitudinal = counts
        self.splice = splice
        self.layout = self.bars.layout
        self.total_bars_tb.Text = "{}".format(counts.total_count)
        self.total_bars_source_tb.Text = (
            "2 x ({} + {}) - 4: the four corner bars are shared between "
            "faces and counted once".format(counts.count_b_face,
                                            counts.count_h_face))
        self.ls_applied_tb.Text = "{:.0f} mm".format(splice.length_mm)
        self.ls_source_tb.Text = splice_length_report_line(splice,
                                                           bar_diameter_mm)
        self.longitudinal_status_tb.Text = "Applied."
        self.redraw_sketch()

    def on_apply_ties_click(self, sender, args):
        """Section 7's two hooks and section 8's spacing."""
        if self.column_data is None:
            self.ties_status_tb.Text = "Pick a column first."
            return
        if self.layout is None:
            self.ties_status_tb.Text = (
                "Apply the Longitudinal bars tab first -- a tie arrangement "
                "is stated in bar indices, and there are no bars yet.")
            return
        mode = MODE_MANUAL if self.mode_b_rb.IsChecked else MODE_AUTO
        try:
            manual_confinement = manual_middle = None
            if mode == MODE_MANUAL:
                manual_confinement = parse_positive_float(
                    self.manual_confinement_tb.Text,
                    "Confinement spacing")
                manual_middle = parse_positive_float(
                    self.manual_middle_tb.Text, "Middle-zone spacing")
            # The second composing call (#110): spacing, the ladder built
            # from the BUILT spacings, the stated topology and section
            # 6.1's verdict, in one place and in one order.
            self.plan = complete_plan(
                self.bars, mode,
                self._selected_tie_bend_diameter_mm(),
                self.tie_subsets_tb.Text,
                manual_confinement_mm=manual_confinement,
                manual_middle_zone_mm=manual_middle)
        except ValueError as ex:
            self.ties_status_tb.Text = str(ex)
            return

        plan = self.plan.spacing
        findings = self.plan.findings
        self.spacing = plan
        self.ladder = self.plan.ladder
        self.ties = self.plan.ties
        self.tie_findings = findings
        self.tie_findings_tb.Text = "\n".join(f.message for f in findings)
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
        self.redraw_sketch()
        self.ties_status_tb.Text = (
            "Applied (Mode {}).".format(plan.mode)
            + ("" if not plan.flags else
               " {} value(s) exceed the code maximum and will be built as "
               "entered.".format(len(plan.flags)))
            + ("" if not is_blocked(self.plan) else
               "  Section 6.1 REFUSES this tie arrangement -- see below.")
            + ("  No inner ties stated." if not self.plan.ties[1:] else ""))

    def on_build_report_click(self, sender, args):
        """Render the page. No Revit work -- every value is already read.

        Refuses to render a PARTIAL report rather than filling the gaps
        with blanks: a page with missing sections is still read as the
        page, and this one's whole purpose is being trusted before Place.
        """
        missing = [label for label, value in (
            ("a picked column", self.column_data),
            ("the Longitudinal bars tab (press Apply)", self.longitudinal),
            ("the Ties tab (press Apply)", self.spacing)) if value is None]
        if missing:
            self.review_status_tb.Text = (
                "Cannot build the report yet -- still needed: %s."
                % "; ".join(missing))
            return

        plan = self.plan
        self.report_tb.Text = render(build_report(
            plan.host, plan.counts, plan.splice,
            splice_length_report_line(plan.splice, plan.bar_diameter_mm),
            plan.bar_type_name, plan.bar_diameter_mm,
            plan.spacing, plan.ladder,
            findings=plan.findings, tie_lines=plan.tie_lines))
        self.review_status_tb.Text = (
            "Built from the same values the placer will use."
            + ("" if not self.spacing.flags else
               "  %d spacing flag(s) -- see the report."
               % len(self.spacing.flags)))

    # ------------------------------------------------------------ apply
    def on_apply_click(self, sender, args):
        """WPF click handler for A3's Apply path (#120, R23/R25). No Revit
        work itself -- everything from step 4 (finding this tool's own
        elements) onward must run in an API context, same as Pick (#57)."""
        if self.column is None or self.plan is None:
            self.place_status_tb.Text = (
                "Pick a column and Apply both the Longitudinal and Ties "
                "tabs first.")
            return

        main_bar_type = self._selected_bar_type_object(self.main_bar_type_cb)
        tie_bar_type = self._selected_bar_type_object(self.tie_bar_type_cb)
        outer_hook_type = self._selected_hook_type_object(self.outer_hook_cb)
        inner_hook_type = self._selected_hook_type_object(self.inner_hook_cb)
        missing = [label for label, value in (
            ("a main bar type", main_bar_type),
            ("a tie bar type", tie_bar_type),
            ("an outer hook type", outer_hook_type),
            ("an inner hook type", inner_hook_type)) if value is None]
        if missing:
            self.place_status_tb.Text = (
                "Select %s before Apply." % " and ".join(missing))
            return

        self._dispatch_to_revit_context(
            lambda: self._apply_in_context(
                main_bar_type, tie_bar_type, outer_hook_type,
                inner_hook_type),
            "Apply")

    def _apply_in_context(self, bar_type, tie_bar_type, outer_hook_type,
                          inner_hook_type):
        """A3 steps 2-10. Steps 2/3 (refuse) and 6-10 (the transaction) are
        `column_placer`'s; this method's own job is steps 4/5 -- read what
        exists, and show R23's dialog -- because a WPF dialog is UI, and
        `column_placer` never shows one.
        """
        plan = self.plan
        host_element = self.column
        doc = revit.doc

        try:
            column_placer.refuse_if_not_ready(plan)
        except column_placer.ColumnPlacementError as ex:
            self.place_status_tb.Text = str(ex)
            forms.alert(str(ex), title="Apply refused")
            return

        # A3 step 4: this tool's own elements, and the foreign rebar R24
        # requires reporting -- ONE read, so the count the dialog shows
        # below and the set Apply deletes/reports can never disagree.
        ours, foreign = column_placer.existing_elements(doc, host_element)

        # A3 step 5 / R23: shown ONLY when elements of ours exist -- a
        # first placement shows nothing. Stops on Cancel, before anything
        # is touched.
        if ours:
            proceed = forms.alert(
                "This column already holds {} element{} placed by this "
                "tool.\nApply will DELETE them and rebuild.".format(
                    len(ours), "" if len(ours) == 1 else "s"),
                title="Replace existing reinforcement?",
                ok=False, yes=True, no=True)
            if not proceed:
                self.place_status_tb.Text = "Cancelled -- nothing changed."
                return

        try:
            # A3 steps 6-10, one transaction (R25): column_placer.apply
            # re-checks steps 2/3 itself, so a plan this method's own
            # refuse_if_not_ready call somehow missed still cannot reach a
            # transaction.
            result = column_placer.apply(
                doc, host_element, plan, ours, foreign,
                bar_type, tie_bar_type, outer_hook_type, inner_hook_type)
        except column_placer.ColumnPlacementError as ex:
            self.place_status_tb.Text = str(ex)
            forms.alert(str(ex), title="Apply refused")
            return
        except Exception as ex:
            # R25: the transaction has already rolled back, so the model
            # is unchanged -- only the diagnosis differs.
            message = "Apply FAILED and was rolled back -- {}: {}".format(
                type(ex).__name__, ex)
            self.place_status_tb.Text = message
            forms.alert(message, title="Apply failed -- rolled back")
            return

        message = "Placed {} tie(s) and {} bar set(s).".format(
            len(result.ties_created), len(result.bars_created))
        if result.replaced_count:
            message = "Replaced {} element(s). {}".format(
                result.replaced_count, message)
        if result.foreign:
            # R24: named, never silently present.
            message += " {} foreign rebar element(s) left untouched (id {}).".format(
                len(result.foreign),
                ", ".join(str(f.element_id) for f in result.foreign))
        self.place_status_tb.Text = message

    # --------------------------------------------------------- sketch
    def on_canvas_size_changed(self, sender, args):
        self.redraw_sketch()

    def _clear_canvases(self):
        for canvas in (self.section_canvas, self.strip_canvas):
            canvas.Children.Clear()
        self.sketch_captions_tb.Text = ""

    def redraw_sketch(self):
        """#90's acceptance: the sketch redraws as the inputs change.

        Draws nothing and says nothing when there is nothing to draw --
        a half-drawn section is a picture of a column that does not exist.
        """
        if not _WPF_SHAPES_AVAILABLE:
            self.sketch_captions_tb.Text = (
                "WPF shape types are unavailable in this engine, so the "
                "sketch cannot draw. Everything else still works.")
            return
        self._clear_canvases()
        if self.column_data is None or self.layout is None:
            return

        bars = self.bars
        self._render(self.section_canvas, cross_section_shapes(
            bars.section.b_mm, bars.section.h_mm, bars.cover_mm,
            bars.tie_diameter_mm, bars.bar_diameter_mm,
            bars.layout, self.ties or ()))
        self.sketch_captions_tb.Text = "\n".join(cross_section_captions(
            self.layout, tier_summary(self.layout), self.ties or ()))

        if self.spacing is not None and self.ladder is not None:
            self._render(self.strip_canvas, zone_strip_shapes(
                self.column_data["extent"].clear_height_mm,
                self.spacing.l0_mm, self.ladder))

    def _render(self, canvas, shapes):
        """Walk the shapes, map a style to a brush, draw. No arithmetic of
        its own beyond fitting millimetres into pixels (A48).

        SHAPE UNVERIFIED: ``FindResource``, ``Canvas.SetLeft/SetTop`` and
        ``PointCollection`` are real WPF members, but this project has only
        ever exercised them from the beam window. The failure mode is a
        blank canvas, not a wrong number.
        """
        width_px = canvas.ActualWidth
        height_px = canvas.ActualHeight
        if width_px <= 1.0 or height_px <= 1.0:
            return

        us = []
        vs = []
        for shape in shapes:
            if isinstance(shape, SketchPolygon):
                us += [u for u, _v in shape.points]
                vs += [v for _u, v in shape.points]
            elif isinstance(shape, SketchLine):
                us += [shape.u1, shape.u2]
                vs += [shape.v1, shape.v2]
            else:
                us.append(shape.u)
                vs.append(shape.v)
        if not us:
            return
        span_u = max(max(us) - min(us), 1.0)
        span_v = max(max(vs) - min(vs), 1.0)
        margin = 18.0
        scale = min((width_px - 2 * margin) / span_u,
                    (height_px - 2 * margin) / span_v)
        mid_u = (max(us) + min(us)) / 2.0
        mid_v = (max(vs) + min(vs)) / 2.0

        def to_px(u_mm, v_mm):
            # v is flipped: millimetres run up, pixels run down.
            return (width_px / 2.0 + (u_mm - mid_u) * scale,
                    height_px / 2.0 - (v_mm - mid_v) * scale)

        text_shapes = []
        for shape in shapes:
            brush = self.FindResource(brush_key_for_style(shape.style))
            if isinstance(shape, SketchLine):
                line = WpfLine()
                line.X1, line.Y1 = to_px(shape.u1, shape.v1)
                line.X2, line.Y2 = to_px(shape.u2, shape.v2)
                line.Stroke = brush
                line.StrokeThickness = 1.2
                canvas.Children.Add(line)
            elif isinstance(shape, SketchCircle):
                x, y = to_px(shape.u, shape.v)
                r_px = max(shape.r * scale, MIN_BAR_RADIUS_PX)
                ellipse = WpfEllipse()
                ellipse.Width = 2.0 * r_px
                ellipse.Height = 2.0 * r_px
                WpfCanvas.SetLeft(ellipse, x - r_px)
                WpfCanvas.SetTop(ellipse, y - r_px)
                ellipse.Fill = brush
                canvas.Children.Add(ellipse)
            elif isinstance(shape, SketchPolygon):
                points = PointCollection()
                for u_mm, v_mm in shape.points:
                    x, y = to_px(u_mm, v_mm)
                    points.Add(Point(x, y))
                polygon = WpfPolygon()
                polygon.Points = points
                polygon.Stroke = brush
                polygon.StrokeThickness = 1.2
                canvas.Children.Add(polygon)
            elif isinstance(shape, SketchText):
                # Collected, not drawn: every label's position is decided
                # together, below, so none is clipped and none lands on
                # another.
                text_shapes.append(shape)

        boxes = []
        for shape in text_shapes:
            x, y = to_px(shape.u, shape.v)
            text_width_px, text_height_px = estimate_text_size_px(
                shape.text, SKETCH_FONT_SIZE_PX)
            boxes.append(LabelBox(x - text_width_px / 2.0, y - text_height_px,
                                  text_width_px, text_height_px))
        placed = place_labels(boxes, width_px, height_px)
        for shape, box in zip(text_shapes, placed):
            text_block = WpfTextBlock()
            text_block.Text = shape.text
            text_block.FontSize = SKETCH_FONT_SIZE_PX
            text_block.Foreground = self.FindResource(
                brush_key_for_style(shape.style))
            WpfCanvas.SetLeft(text_block, box.x)
            WpfCanvas.SetTop(text_block, box.y)
            canvas.Children.Add(text_block)

    # ------------------------------------------------------- selections
    def _options_for(self, combo):
        """The option list a combo's ``SelectedIndex`` indexes into.

        The two bar pickers hold different lists since #133, so an index
        is only meaningful against its own combo's list. One accessor
        rather than each call site remembering which -- reading the wrong
        list would silently return a DIFFERENT bar type, not an error.
        """
        if combo is self.main_bar_type_cb:
            return self.main_bar_type_options
        return self.bar_type_options

    def _selected_bar_type_name(self, combo):
        options = self._options_for(combo)
        index = combo.SelectedIndex
        if index < 0 or index >= len(options):
            return "(none selected)"
        return options[index][0].split("  --  ")[0]

    def _selected_ls_mode(self):
        index = self.ls_mode_cb.SelectedIndex
        if index < 0:
            return LS_MODE_DIAMETERS
        return LS_MODE_CHOICES[index][0]

    def _selected_bar_diameter_mm(self):
        return self._diameter_of(self.main_bar_type_cb)

    def _selected_tie_diameter_mm(self):
        return self._diameter_of(self.tie_bar_type_cb)

    def _selected_tie_bend_diameter_mm(self):
        """The tie type's own ``StirrupTieBendDiameter``.

        A1 reads it, never assumes it: the live model's 10M is 40.00 mm
        against a 9.50 mm bar (4.2x) while its 19M is 115.00 against 19.10
        (6.0x). A constant multiplier would be wrong across most of the
        range, and being wrong here means offering a loop Revit will
        refuse with a modal dialog.
        """
        options = self._options_for(self.tie_bar_type_cb)
        index = self.tie_bar_type_cb.SelectedIndex
        if index < 0 or index >= len(options):
            return None
        _label, bar_type = options[index]
        return bar_type_bend_diameter_mm(bar_type, internal_to_mm)

    def _diameter_of(self, combo):
        """The selected type's ACTUAL diameter, from the type.

        Never parsed out of the name: the live model's ``16M`` is 15.90 mm
        and its ``25M`` is 25.40 mm -- Imperial bars wearing metric names.
        Returns ``None`` when nothing is selected, and the pure modules
        refuse on that rather than substituting a plausible number.
        """
        options = self._options_for(combo)
        index = combo.SelectedIndex
        if index < 0 or index >= len(options):
            return None
        _label, bar_type = options[index]
        return bar_type_diameter_mm(bar_type, internal_to_mm)

    def _selected_bar_type_object(self, combo):
        """The actual ``RebarBarType`` behind a bar-type combo, for #120's
        Apply -- the placer needs the Revit object itself, not the label
        ``_selected_bar_type_name`` derives from it."""
        options = self._options_for(combo)
        index = combo.SelectedIndex
        if index < 0 or index >= len(options):
            return None
        return options[index][1]

    def _selected_hook_type_object(self, combo):
        """The actual ``RebarHookType`` behind a hook combo. Section 7
        keeps the outer/inner pickers independently selectable, and #120's
        Apply reads each combo separately rather than assuming one applies
        to both roles."""
        index = combo.SelectedIndex
        if index < 0 or index >= len(self.hook_type_options):
            return None
        return self.hook_type_options[index][1]


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
