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

from rft.revit.bar_types import bar_type_options
from rft.revit.column_host import ColumnHostError, read_column
from rft.revit.units import internal_to_mm
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
                    "top_source_tb", "clear_height_source_tb", "notes_tb")


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

        self.column = None
        self.column_data = None
        self.bar_type_options = []
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
        for name in READOUT_NAMES:
            getattr(self, name).Text = "--"
        for name in PROVENANCE_NAMES:
            getattr(self, name).Text = ""
        for name in GATED_TAB_NAMES:
            getattr(self, name).IsEnabled = False
        self.main_bar_type_cb.IsEnabled = False
        self.tie_bar_type_cb.IsEnabled = False

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
