# -*- coding: utf-8 -*-
"""Prove every text-based guard by mutation: reintroduce the defect it was
written for, and require it to fail.

WHY THIS EXISTS

Several guards in this repo check source code as TEXT, because the pyRevit
script cannot be imported under CPython (it imports `pyrevit`) and no test
can therefore evaluate it. Text checks are the only thing that CAN run --
and a text check that matches nothing passes silently. Two of them did
exactly that: a regex word boundary had been written into the file as a
literal backspace byte, so the pattern matched nothing, the comparison was
empty, and the test passed against the very defect it was written for.

A guard that has never been shown to fail has not been tested. It has only
been written.

WHY IT RESTORES WITH GIT

An earlier version wrote the original bytes back itself and hit an
OSError mid-restore on Windows, leaving a mutated file in the working
tree. A tool that can damage the repo while checking it is worse than no
tool. So: every target must be COMMITTED AND CLEAN before it is touched,
and restoration is `git checkout --`, which is the operation git exists to
make reliable. The clean-tree precondition is what makes that safe.

Run from the repo root:  python tools/prove_guards.py
"""
import io
import subprocess
import sys

SCRIPT = ("SimpleBeamRFT.extension/RFT-Tools.tab/"
          "Beams.panel/Simple Beam.pushbutton/script.py")
BUNDLE = ("SimpleBeamRFT.extension/RFT-Tools.tab/"
          "Beams.panel/Simple Beam.pushbutton/bundle.yaml")
XAML = ("SimpleBeamRFT.extension/RFT-Tools.tab/"
        "Beams.panel/Simple Beam.pushbutton/SimpleBeamWindow.xaml")
PLAN = "RFT.lib/rft/core/plan.py"
REPORT = "RFT.lib/rft/ui/report.py"
GUARDS = "RFT.lib/rft/core/guards.py"
SPACING = "RFT.lib/rft/core/spacing.py"
SKETCH_PALETTE = "RFT.lib/rft/ui/sketch_palette.py"
SHARED_STYLES = "RFT.lib/rft/ui/shared_styles.py"
STYLES_XAML = "RFT.lib/SharedStyles.xaml"

# ---- #87: the second element -------------------------------------
COL_DIR = ("ColumnRFT.extension/RFT-Tools.tab/"
           "Columns.panel/ColumnRFT.pushbutton/")
COL_XAML = COL_DIR + "ColumnWindow.xaml"
COL_SCRIPT = COL_DIR + "script.py"
COL_BUNDLE = COL_DIR + "bundle.yaml"
COL_RULES = "RFT.lib/rft/core/column_host_rules.py"
TC = "tests/test_column_xaml.py::"
TR = "tests/test_column_host_rules.py::"
COL_PLACE_BARS = "RFT.lib/rft/revit/column_place_bars.py"
TPB = "tests/test_column_place_bars.py::"
GRADES = "RFT.lib/rft/core/grades.py"
BAR_TYPES = "RFT.lib/rft/revit/bar_types.py"
COL_INPUTS = "RFT.lib/rft/core/column_inputs.py"
COL_SPACING = "RFT.lib/rft/core/column_spacing.py"
TI = "tests/test_column_inputs.py::"
TS = "tests/test_column_spacing.py::"
COL_LEVELS = "RFT.lib/rft/core/column_tie_levels.py"
COL_REPORT = "RFT.lib/rft/core/column_report.py"
TL = "tests/test_column_tie_levels.py::"
TP = "tests/test_column_report.py::"
COL_PERIM = "RFT.lib/rft/core/column_layout.py"
COL_SKETCH = "RFT.lib/rft/ui/column_sketch.py"
COL_SKETCH_PAL = "RFT.lib/rft/ui/column_sketch_palette.py"
TY = "tests/test_column_layout.py::"
TK = "tests/test_column_sketch.py::"
COL_TIES = "RFT.lib/rft/core/column_ties.py"
COL_PLAN = "RFT.lib/rft/core/column_plan.py"
TT = "tests/test_column_ties.py::"
COL_HOST = "RFT.lib/rft/revit/column_host.py"
TH = "tests/test_column_host_source.py::"
# ---- #140: ResolvedTie.vertices, the one polygon three consumers read --
TV = "tests/test_column_tie_vertices.py::"
# ---- #137: sketch the tie by clicking its bars ----------------------
SKETCH_LAYOUT = "RFT.lib/rft/ui/sketch_layout.py"
TSL = "tests/test_ui_sketch_layout.py::"
# ---- #117: ownership (R24/R26) --------------------------------------
COL_OWNERSHIP = "RFT.lib/rft/revit/column_ownership.py"
TW = "tests/test_column_ownership.py::"
TPL = "tests/test_column_plan.py::"
TRW = "tests/test_column_roof_window.py::"
# ---- #118: the tie placer -------------------------------------
COL_PLACE_TIES = "RFT.lib/rft/revit/column_place_ties.py"
TPT = "tests/test_column_place_ties.py::"
# ---- #120: the Apply path (R23/R25) -----------------------------
COL_PLACER = "RFT.lib/rft/revit/column_placer.py"
TCP = "tests/test_column_placer.py::"
TCA = "tests/test_column_apply.py::"
# ---- #153: batch placement (R33) --------------------------------
COL_BATCH_CORE = "RFT.lib/rft/core/column_batch.py"
COL_ROOF = "RFT.lib/rft/core/column_roof.py"
TCR = "tests/test_column_roof.py::"
COL_BATCH_ADAPTER = "RFT.lib/rft/revit/column_batch.py"
TCB = "tests/test_column_batch.py::"
TCBW = "tests/test_column_batch_window.py::"
# ---- #167: the top-floor slab adapter (R37-R39, R41, R42) -------------
COL_ROOF_RUN = "RFT.lib/rft/core/column_roof_run.py"
TCRR = "tests/test_column_roof_run.py::"
COL_ROOF_SLAB = "RFT.lib/rft/revit/column_roof_slab.py"
TCRS = "tests/test_column_roof_slab.py::"
T = "tests/test_simple_beam_xaml.py::"
WORKFLOW = ".github/workflows/tests.yml"
VERSION_FILE = "SimpleBeamRFT.extension/VERSION"

# Read the CURRENT version rather than naming one. This case broke on the
# very first release after it was written (VERSION had moved to rc3 while
# the case still looked for rc2), which would have quietly become "one
# guard unproven" at every future bump.
VERSION_NOW = io.open(VERSION_FILE, encoding="utf-8").read().strip()

GEOM_ANCHOR = "        # an anchor.\n        self.geometry_mm = None"
CATCH_ANCHOR = ("        except Exception as ex:\n"
                "            # NEVER let this reach the ExternalEvent handler")
CATCH_MUTANT = ("        except ValueError as ex:\n"
                "            # NEVER let this reach the ExternalEvent handler")

# (file, find, replace, test node, what defect this reintroduces)
CASES = [
    # ---- #176: R43's second window ----------------------------------
    # All INVERTING. A disabling mutation on this repo once passed in CI
    # while failing locally on identical content (see R45's case).
    (COL_SCRIPT,
     "if self.top_floor_cb.IsChecked and self.roof_termination is None:",
     "if self.top_floor_cb.IsChecked and self.roof_termination is not None:",
     TRW + "test_apply_is_REFUSED_while_the_top_floor_inputs_are_missing",
     "R36/R43 -- the top-floor gate inverted, so a column MARKED top "
     "floor with no inputs sails through and laps its bars into a storey "
     "that is not there, while every other number stays right"),

    (COL_SCRIPT,
     "        self.roof_termination = None\n"
     "        self.top_floor_cb.IsChecked = False\n",
     "        self.top_floor_cb.IsChecked = False\n",
     TRW + "test_a_re_pick_unticks_the_top_floor_box_and_drops_its_inputs",
     "R43 -- the previous column's termination survives a re-pick, so "
     "the new column is detailed against the OLD column's slab while "
     "every other read-out on screen belongs to the new one"),

    (COL_SCRIPT,
     "        self.owner.accept_roof_termination(plan)\n",
     "        self.owner.roof_termination = plan\n",
     TRW + "test_the_window_hands_the_plan_over_rather_than_keeping_it",
     "R43 -- the second window writes the owner's state directly instead "
     "of handing it over, so the main window never says what it took and "
     "the two can disagree about what is loaded"),

    # ---- #176: the roof assembler, R44 -------------------------------
    # INVERTING, not disabling: a swap cannot be read two ways, and an
    # `if False:` mutation on this repo once passed in CI while failing
    # locally on identical content (see R45's case below).
    (COL_PLAN,
     '    ("bottom", STEP_AXIS_HAND),\n'
     '    ("right", STEP_AXIS_FACING),',
     '    ("bottom", STEP_AXIS_FACING),\n'
     '    ("right", STEP_AXIS_HAND),',
     TPL + "test_each_run_bends_PERPENDICULAR_to_the_axis_it_steps_along",
     "R44 -- the two step axes swapped, so every run bends ALONG the "
     "axis its own bars are arrayed on: the exact CreateFromCurves call "
     "that raised an internal error in #173's part 3"),

    (COL_PLAN,
     '    ("right", STEP_AXIS_FACING),\n'
     '    ("top", STEP_AXIS_HAND),',
     '    ("top", STEP_AXIS_HAND),\n'
     '    ("right", STEP_AXIS_FACING),',
     TPL + "test_the_assembler_states_the_axis_mapping_in_the_PERIMETER_order",
     "R44 -- the run order no longer matches the order "
     "_face_run_slices slices the perimeter in, and column_place_bars "
     "looks its run up BY INDEX: every run would be handed another "
     "run's bend, with no error anywhere"),

    # ---- #119: the bar placer, R22 ----------------------------------
    (COL_PLACE_BARS, 'candidate.SetDistanceToTargetHostFace(-offset_internal)',
     'candidate.SetDistanceToTargetHostFace(offset_internal)',
     TPB + "test_the_face_offset_is_signed_NEGATIVE",
     "R22 -- the offset sign flipped, which on the live host put the "
     "bar 57 mm OUTSIDE the column"),

    (COL_PLACE_BARS, '        if candidate.IsToCover():\n            continue\n',
     '',
     TPB + "test_the_ToCover_candidate_is_rejected_even_when_offered_first",
     "R22 -- the ToCover candidate accepted; it re-points the "
     "constraint and the bar does NOT move, so this must fail on "
     "POSITION, never on the constraint type"),

    (COL_PLACE_BARS, '        mgr.SetPreferredConstraintForHandle(handle, candidate)\n',
     '',
     TPB + "test_removing_the_preferred_constraint_call_would_leave_it_unset",
     "R22 -- the right constraint chosen and never applied"),

    (COL_PLACE_BARS,
     '            return candidate, _axis_of_normal(\n'
     '                (normal.X, normal.Y, normal.Z), hand, facing)\n'
     '    return None, None',
     '            match = (candidate, _axis_of_normal(\n'
     '                (normal.X, normal.Y, normal.Z), hand, facing))\n'
     '    return match',
     TPB + "test_the_FIRST_matching_candidate_is_taken_not_the_last",
     "R22 -- first-match reverted to last-match-wins, picking by an "
     "ordering Revit does not document (47-49 candidates per handle "
     "on the live column)"),

    (SCRIPT, "review.crack_bars.requested", "review.crack.requested",
     "test_every_review_attribute_the_script_uses_exists",
     "wrong derivation attribute (the rc4 live failure)"),

    (SCRIPT, "    window.show()", "    window.ShowDialog()",
     "test_the_window_is_never_shown_modally",
     "modal window via ShowDialog"),

    (SCRIPT, "    window.show()", "    window.show_dialog()",
     "test_the_window_is_never_shown_modally",
     "modal via show_dialog (the branch that never matched)"),

    (SCRIPT, GEOM_ANCHOR, "        # an anchor.",
     "test_every_beam_scoped_attribute_is_cleared_on_pick",
     "beam-scoped state left stale on re-pick"),

    (SCRIPT, "        if not review.any_requested:\n            return missing\n", "",
     "test_place_preflight_consults_the_same_derivation_that_enables_it",
     "Place guard ignoring the derivation"),

    (BUNDLE, "engine:\n  persistent: true\n", "",
     "test_modeless_window_declares_a_persistent_engine",
     "no persistent engine (the rc2 live failure)"),

    # The report moved to rft/ui/report.py, so this case follows it there.
    # The prover reported ANCHOR MISSING rather than passing, which is the
    # behaviour that matters: a case whose anchor has moved must not read
    # as proven.
    (REPORT, "core_plan.face_layer_plans(", "hand_rolled_layer_offsets(",
     "test_report_and_placement_both_use_the_shared_plan",
     "report recomputing ONE of its plan calls by hand"),

    # #49 (U5) added a SECOND ``core_plan.crack_plan(`` call site in this
    # file (``_sketch_crack_plan``, the live sketch's own best-effort
    # crack plan), earlier in the file than the placer's. A bare
    # single-occurrence replace of "core_plan.crack_plan(" now hits that
    # one instead, leaving the placer's call untouched and this case
    # silently unproven -- so the anchor is widened to text unique to the
    # PLACER's call site (``_build_placement_plans``'s own local variable
    # names), which the sketch's call does not share.
    (SCRIPT, 'crack = core_plan.crack_plan(\n                h_mm, b_mm, cover_side_mm, stirrup_dia_mm,',
     'crack = hand_rolled_crack_plan(\n                h_mm, b_mm, cover_side_mm, stirrup_dia_mm,',
     "test_report_and_placement_both_use_the_shared_plan",
     "placer recomputing the crack plan by hand"),

    (SCRIPT, CATCH_ANCHOR, CATCH_MUTANT,
     "test_dispatched_work_cannot_fail_silently",
     "dispatch wrapper narrows what it catches"),

    (XAML, '    <Grid Margin="8" Background="{StaticResource SurfaceWhite}">',
     '    <Grid Margin="8" Background="{StaticResource NoSuchBrush}">',
     "test_every_static_resource_reference_is_defined",
     "a StaticResource key that is never declared"),

    (XAML, '        SizeToContent="Manual">',
     '        SizeToContent="Manual" Background="{StaticResource SurfaceWhite}">',
     "test_the_window_element_itself_uses_no_static_resource",
     "StaticResource back on the Window element (the rc6 crash)"),

    (XAML, "<!-- #86: the palette is no longer declared here.",
     "<!-- #86: the palette is no longer declared here -- it moved.",
     "test_no_xaml_comment_contains_a_double_hyphen",
     "a double hyphen inside a XAML comment"),

    # ---- #86: the shared palette -------------------------------------
    # Every case below leaves the XAML well formed and every OTHER test
    # green, and breaks the window only on a live host.

    (XAML, '                <ResourceDictionary Source="SharedStyles.xaml"/>\n',
     '',
     T + "test_the_window_merges_the_shared_palette",
     "the window no longer merging the shared palette"),

    (XAML, '        <ResourceDictionary>\n',
     '        <ResourceDictionary>\n'
     '            <SolidColorBrush x:Key="SkyBlue" Color="#FF87CEEB"/>\n',
     T + "test_the_window_declares_no_palette_brush_of_its_own",
     "a local brush shadowing the shared one (the drift #86 removes)"),

    (XAML, '        SizeToContent=\"Manual\">',
     '        SizeToContent=\"Manual\" Icon=\"beam.png\">',
     T + "test_the_xaml_carries_no_other_relative_uri",
     "a relative URI that cannot resolve in a string-loaded window"),

    (STYLES_XAML, '<SolidColorBrush x:Key="SkyBlue" Color="#FF87CEEB"/>',
     '<SolidColorBrush x:Key="SkyBlue" Color="#FF87CEEC"/>',
     "tests/test_ui_shared_styles.py::"
     "test_every_colour_survived_the_move_byte_for_byte",
     "a colour that changed while being moved"),

    (STYLES_XAML, '</ResourceDictionary>',
     '    <Style x:Key="SectionHeading" TargetType="TextBlock"/>\n'
     '</ResourceDictionary>',
     "tests/test_ui_shared_styles.py::"
     "test_the_shared_palette_declares_nothing_but_brushes",
     "a window Style leaking into the shared palette"),

    (SHARED_STYLES, "    if occurrences != 1:",
     "    if occurrences < 1:",
     "tests/test_ui_shared_styles.py::"
     "test_a_duplicated_placeholder_is_refused_loudly",
     "a duplicated merge slipping through as one"),

    # ---- the two checks that need no Revit: markup that parses,
    # ---- and a name that exists (the blank sketch, and both windows
    # ---- dying at ResourceDictionary.Source)

    (STYLES_XAML,
     '         tie), so a pending selection is never mistaken for something this',
     '         tie) -- so a pending selection is never mistaken for something',
     "tests/test_xaml_parses_as_xml.py",
     "the house em dash back inside a XAML comment. XML forbids a "
     "double hyphen in a comment body, and this file is merged by BOTH "
     "windows, so it killed the beam tool as well as the column one"),

    (COL_SCRIPT,
     '                r_px = max(shape.r * transform.scale, MIN_BAR_RADIUS_PX)',
     '                r_px = max(shape.r * scale, MIN_BAR_RADIUS_PX)',
     "tests/test_pushbutton_scripts_resolve_their_names.py",
     "the deleted local read back into the drawing loop, which raises "
     "NameError at the FIRST bar circle: concrete, cover and tie draw, "
     "then bars, dimensions and every caption are silently lost"),

    # ---- #141 review: the triangle's winding, on which R21's hook
    # ---- orientation depends

    (COL_TIES,
     '    if _signed_area(points) * _RECTANGLE_WINDING_SIGN < 0.0:',
     '    if False:',
     "tests/test_column_triangular_ties.py::"
     '     "test_the_same_triangle_typed_either_way_round_winds_the_same"',
     "the winding normalisation switched off, so T 1 3 5 and T 5 3 1 "
     "wind oppositely and Left/Left hooks one of them outward (R21)"),

    (COL_TIES,
     '        (ordered_points[i][0] + axes[i][0] * (grow / math.sin(thetas[i] / 2.0)),',
     '        (points[i][0] + axes[i][0] * (grow / math.sin(thetas[i] / 2.0)),',
     "tests/test_column_triangular_ties.py::"
     '     "test_the_same_triangle_typed_either_way_round_winds_the_same"',
     "each vertex pushed along a bisector belonging to a DIFFERENT "
     "vertex, by pairing the typed order with the normalised angles"),

    (COL_TIES,
     '        vertices = _rectangle_corners(centre_u, centre_v, half_u, half_v)',
     '        vertices = list(reversed(_rectangle_corners(centre_u, centre_v, half_u, half_v)))',
     "tests/test_column_triangular_ties.py::"
     '     "test_a_triangle_winds_the_SAME_WAY_a_closed_loop_does"',
     "the closed loop's own winding reversed, which must break the "
     "triangle's agreement with it rather than silently redefining it"),

    # ---- R29 (#146): a diagonal leg is not a branch

    (COL_TIES,
     '    if across > BRANCH_AXIS_TOL_MM:',
     '    if False:',
     "tests/test_column_ties.py::"
     '     "test_a_diagonal_leg_is_NOT_a_branch_on_either_axis"',
     "R29 switched off, so a diagonal leg is credited as a branch on "
     "both axes and section 6.1 passes steel it should block"),

    (COL_TIES,
     '    if along <= BRANCH_AXIS_TOL_MM:',
     '    if False:',
     "tests/test_column_ties.py::"
     '     "test_a_zero_length_leg_is_no_branch_at_all"',
     "a zero-length leg reading as aligned on BOTH axes, inventing "
     "two branches out of one point"),

    # ---- R30 (#146): a diagonal bridges the gap it crosses

    (COL_TIES,
     '                if span is None or span > MAX_TIE_BRANCH_SPACING_MM:',
     '                if True:',
     "tests/test_column_ties.py::"
     '     "test_a_triangles_diagonal_BRIDGES_the_gap_it_crosses"',
     "R30 switched off, so a triangle's diagonals stop bridging and "
     "the tool demands a cross-tie the engineering does not need"),

    (COL_TIES,
     '                if span is None or span > MAX_TIE_BRANCH_SPACING_MM:',
     '                if span is None:',
     "tests/test_column_ties.py::"
     '     "test_a_diagonal_TOO_LONG_to_be_doing_that_job_does_not_bridge"',
     "the 300 mm limit dropped from R30, so ANY diagonal bridges "
     "however long -- a licence rather than a rule"),

    (COL_TIES,
     '    du = max(0.0, abs(bar_a.u_mm - bar_b.u_mm) - bar_diameter_mm)',
     '    du = abs(bar_a.u_mm - bar_b.u_mm) - bar_diameter_mm',
     "tests/test_column_ties.py::"
     '     "test_a_purely_horizontal_leg_reports_its_PLAIN_clear_distance"',
     "the clamp removed, so a leg with no extent on one axis squares "
     "a NEGATIVE clear distance back into its span"),

    # ---- R31 (#149): where the hook closure sits

    (COL_TIES,
     '    return (base + 2) % count',
     '    return base',
     "tests/test_column_ties.py::"
     '     "test_the_apex_is_the_vertex_opposite_the_LONGEST_leg"',
     "the apex taken as an END of the base rather than the vertex "
     "opposite it, so a triangle closes on its base"),

    (COL_TIES,
     '        vertices = rotate_to_closure(vertices, top_index(vertices))',
     '        pass',
     "tests/test_column_ties.py::"
     '     "test_a_rectangle_closes_at_its_top"',
     "the rectangle left closing at the bottom-left corner it used "
     "to, against the owner's ruling"),

    (COL_TIES,
     '    return [vertices[(closure_index + i) % count] for i in range(count)]',
     '    return [vertices[(closure_index - i) % count] for i in range(count)]',
     "tests/test_column_ties.py::"
     '     "test_moving_the_closure_does_NOT_change_the_winding"',
     "the rotation turned into a REVERSAL, which puts both 135 degree "
     "hook tails outside the concrete (R21, and #145's defect again)"),

    (COL_TIES,
     '        elif (abs(vertices[i][1] - vertices[best][1]) <= COINCIDENT_TOL_MM\n'
     '              and vertices[i][0] < vertices[best][0]):',
     '        elif False:',
     "tests/test_column_ties.py::"
     '     "test_the_top_of_a_rectangle_is_unambiguous_when_two_corners_share_it"',
     "the tie-break between the two top corners dropped, so the "
     "closure depends on which corner the list happened to reach first"),
    # ---- R32 (#149): a triangle does not alternate

    (COL_REPORT,
     '        "A TRIANGLE does not alternate (R32): its closure stays at the "',
     '        "A TRIANGLE alternates like any other tie: "',
     "tests/test_column_report.py::test_the_report_says_a_triangle_does_NOT_alternate",
     "the report promising alternation a triangle cannot keep -- its "
     "closure is the apex, fixed by R31, with no second corner to move to"),

    # ---- #87: the column window ---------------------------------

    (COL_XAML, '                <ResourceDictionary Source=\"SharedStyles.xaml\"/>\n',
     '',
     TC + "test_every_window_merges_the_shared_palette",
     "the COLUMN window no longer merging the shared palette"),

    (COL_XAML, '                            <Button x:Name=\"pick_column_btn\"',
     '                            <Button Click=\"on_pick_click\" x:Name=\"pick_column_btn\"',
     TC + "test_no_window_declares_an_event_handler_in_the_markup",
     "a Click handler in markup a string load cannot resolve"),

    (COL_XAML, '<TabItem Header=\"Review\" x:Name=\"review_tab\" IsEnabled=\"False\">',
     '<TabItem Header=\"Review\" x:Name=\"review_tab\">',
     TC + "test_every_gated_tab_in_the_xaml_starts_disabled",
     "a tab shipping enabled before any column is accepted"),

    (COL_SCRIPT, '        self._reset_column_state()\n\n        column = revit.pick_element(',
     '        column = revit.pick_element(',
     TC + "test_the_state_reset_runs_before_the_pick_not_after",
     "stale read-outs surviving a refused re-pick"),

    (COL_SCRIPT, '        except ColumnHostError as refusal:',
     '        except NotImplementedError as refusal:',
     TC + "test_a_refused_column_is_not_reported_as_a_failure",
     "an out-of-scope column reported to the user as a crash"),

    (COL_SCRIPT, '"section_source_tb", "cover_source_tb",',
     '"section_source_tb",',
     TC + "test_every_readout_is_cleared_on_a_re_pick",
     "a read-out that keeps the PREVIOUS column value"),

    (COL_SCRIPT, '        self._dispatch_to_revit_context(self._pick_column_in_context,\n                                        \"Pick column\")',
     '        self._pick_column_in_context()',
     TC + "test_the_pick_handler_does_no_revit_work_directly",
     "Revit work done straight from a modeless click handler"),

    (COL_BUNDLE, '  persistent: true', '  persistent: false',
     TC + "test_the_modeless_window_declares_a_persistent_engine",
     "the persistent engine turned off (silent dead ExternalEvents)"),

    # ---- #89: the tie topology ----------------------------------

    (COL_TIES, '    if narrow >= minimum:',
     '    if True:',
     TT + "test_the_narrow_case_is_decided_by_the_MEASURED_bend_diameter",
     "A1 disabled -- an unbendable loop offered to Revit"),

    (COL_TIES, '    return bend_diameter_mm + tie_dia_mm',
     '    return 10.0 * tie_dia_mm',
     TT + "test_the_threshold_is_bend_plus_tie",
     "the bend diameter guessed as a multiple instead of read"),

    (COL_TIES, '        restrained = [bar.index for bar in layout.bars',
     '        restrained = [bar.index for bar in bars',
     TT + "test_a_tie_corner_restrains_a_bar_it_does_not_ENCLOSE",
     "a bar at a tie corner missed because the subset omits it"),

    (COL_TIES, '        restrained = [bars[0].index, bars[-1].index]',
     '        restrained = [b.index for b in bars]',
     TT + "test_a_cross_tie_restrains_only_its_two_ends",
     "a cross-tie credited with restraining every bar it spans"),

    (COL_TIES, '        if len(run) > 1]',
     '        if len(run) > 99]',
     TT + "test_the_alternate_tier_refuses_two_untied_bars_IN_A_ROW",
     "consecutive untied bars accepted as alternating"),

    # ---- the rc1 live failure: ElementType hides Element.Name ----------
    (COL_HOST, '    return internal_to_mm(cover_type.CoverDistance), element_name(cover_type)',
     '    return internal_to_mm(cover_type.CoverDistance), cover_type.Name',
     TH + "test_no_dot_Name_is_read_on_an_ElementType",
     "RebarCoverType.Name read back -- AttributeError on the first click"),

    (COL_HOST, '        "type_name": element_name(element.Symbol),',
     '        "type_name": element.Symbol.Name,',
     TH + "test_the_two_reads_that_broke_the_live_host_are_gone",
     "FamilySymbol.Name read back -- the exact rc1 defect"),

    (COL_HOST, '        "family_name": element.Symbol.Family.Name,',
     '        "family_name": element_name(element.Symbol.Family),',
     TH + "test_the_family_name_does_NOT_go_through_element_name",
     "Family routed through element_name -- name degraded to a placeholder"),

    (COL_HOST, 'from .bar_types import element_name',
     'from .units import internal_to_mm as element_name',
     TH + "test_element_name_is_imported_from_the_beam_s_verified_helper",
     "the verified helper swapped for a local stand-in"),

    # ---- #117: ownership is a PREFIX test, and one shared constant ----

    (COL_OWNERSHIP, '    return value is not None and value.startswith(OWNERSHIP_PREFIX)',
     '    return value == partition_tag(422078)',
     TW + "test_a_cage_carrying_a_stale_host_id_is_still_ours",
     "ownership narrowed from a PREFIX test to equality -- a copied cage's "
     "stale host id would read as foreign"),

    (COL_OWNERSHIP, '    return "%s%s" % (OWNERSHIP_PREFIX, host_id)',
     '    return "RFT-COLUMN-%s" % host_id',
     TW + "test_the_tag_is_exactly_the_prefix_plus_the_host_id",
     "the write side building its tag from a literal instead of the "
     "shared OWNERSHIP_PREFIX constant"),

    (COL_OWNERSHIP, '    parameter = rebar.LookupParameter(PARTITION_PARAMETER_NAME)',
     '    parameter = rebar.LookupParameter("Partition ")',
     TW + "test_an_element_tagged_by_this_module_is_found_by_it_afterwards",
     "Partition read through a literal instead of the shared "
     "PARTITION_PARAMETER_NAME constant -- a tool that tags with one name "
     "and searches with another silently owns nothing"),

    # ---- #110: the window composes nothing -----------------------
    (COL_SCRIPT, 'from rft.core.column_plan import (',
     'from rft.core.column_spacing import spacing_plan\nfrom rft.core.column_plan import (',
     TC + "test_the_window_reaches_for_the_PLAN_not_the_modules_under_it",
     "the window calling a composed module directly again"),

    (COL_SCRIPT, 'from rft.core.column_layout import tier_summary',
     'from rft.core.column_layout import tier_summary, perimeter_bar_positions',
     TC + "test_the_only_thing_taken_from_column_layout_is_WORDING",
     "the wording exception widened back into a decision"),

    (COL_SCRIPT, '            + ("" if not is_blocked(self.plan) else',
     '            + ("" if not self.plan.findings else',
     TC + "test_section_6_1_s_verdict_has_ONE_reader_in_the_window",
     "the window re-applying section 6.1's test for itself"),

    (COL_PLAN, '                        ladder_inputs.confinement_spacing_mm,',
     '                        ladder_inputs.s0_mm,',
     TPL + "test_the_tie_ladder_is_built_from_the_BUILT_spacings",
     "the ladder following the code limit, not what will be built"),

    (COL_PLAN, '        findings=validate(bars.layout, ties),',
     '        findings=(),',
     TPL + "test_the_findings_belong_to_the_ties_the_plan_CARRIES",
     "a plan carrying ties nobody judged"),

    (COL_PLAN, '        tie_lines=tie_report_lines(ties),',
     '        tie_lines=(),',
     TPL + "test_the_plan_carries_the_tie_LINES_the_report_prints",
     "the report's tie section emptied at the source"),

    # ---- #118: the tie placer, R21 and A1 --------------------------
    (COL_PLACE_TIES, '_HOOK_ORIENTATION = RebarHookOrientation.Left',
     '_HOOK_ORIENTATION = RebarHookOrientation.Right',
     TPT + "test_hook_tails_are_verified_by_reading_the_geometry_back",
     "R21 -- Left flipped to Right, must be caught by the tail assertion "
     "reading the geometry back, not by grepping for the word Left"),

    (COL_PLACE_TIES, '    for tie in plan.ties:\n        _ensure_buildable(tie)\n',
     '',
     TPT + "test_a_subthreshold_loop_is_refused_before_any_element_is_created",
     "A1 -- the pre-check over the whole plan deleted from place_ties"),

    (COL_TIES, '    if tie.kind != KIND_CLOSED_LOOP:\n        return True\n',
     '',
     TPT + "test_a_cross_tie_is_never_gated_by_A1_its_geometry_is_not_a_loop",
     "A1 -- a legitimate cross-tie (narrow < minimum BY DESIGN) wrongly "
     "refused once the CLOSED_LOOP-only guard is removed from core's "
     "is_buildable, which BOTH the tie placer and the Apply path ask"),

    (COL_TIES, '    return tie.narrow_mm >= tie.min_buildable_mm',
     '    return True',
     TPT + "test_a_subthreshold_loop_is_refused_before_any_element_is_created",
     "A1 -- the narrow-vs-minimum comparison itself disabled in core"),

    (COL_PLACER, '        if is_buildable(tie):',
     '        if True:',
     "tests/test_column_placer.py::"
     "test_apply_never_opens_a_transaction_for_an_unbuildable_tie",
     "A1 -- the Apply path's gate made unconditionally permissive, so "
     "an unbuildable loop reaches a transaction even though the tie "
     "placer would go on to refuse it. DELETING the two lines instead "
     "leaves a bare raise in the loop, refusing EVERY tie -- still "
     "raising, still opening nothing, indistinguishable from working, "
     "and that is how this guard came back MISSED the first time."),

    (COL_PLACE_TIES, '    start_tail = curves[0].GetEndPoint(0)',
     '    start_tail, _junk = curves[0]',
     TPT + "test_hook_tails_are_verified_by_reading_the_geometry_back",
     "R21/#127 -- the hook-tail read reverted to UNPACKING a curve, which "
     "is what died on a live host with TypeError: 'Line' object is not "
     "iterable while every test passed"),

    (COL_PLACE_TIES, '    end_tail = curves[len(curves) - 1].GetEndPoint(1)',
     '    end_tail = curves[-1].GetEndPoint(1)',
     TPT + "test_hook_tails_are_verified_by_reading_the_geometry_back",
     "#129 -- negative indexing into what GetCenterlineCurves returns. "
     "Legal Python, and an error on the .NET IList the API actually "
     "hands back"),

    (COL_PLACE_BARS, '        bar.GetShapeDrivenAccessor().SetLayoutAsNumberWithSpacing(',
     '        bar.SetLayoutAsNumberWithSpacing(',
     TPB + "test_bars_are_created_as_four_FACE_RUNS_not_one_element_per_bar",
     "#130 -- the layout method called on the Rebar instead of on its "
     "shape driven accessor, which is where the live API has it"),

    (COL_PLACE_BARS, '    normal = direction',
     '    normal = (-direction[1], direction[0], 0.0)',
     TPB + "test_each_run_is_arrayed_ALONG_its_own_face_not_across_it",
     "#131 -- the set arrayed ACROSS its own face instead of along "
     "it, which put two bars 11.7 mm apart at a corner on the live "
     "column while every test passed"),

    # ---- #137: sketch the tie by clicking its bars ------------------
    (SKETCH_LAYOUT,
     '        return (self.mid_u + (x_px - self.width_px / 2.0) / self.scale,\n'
     '                self.mid_v - (y_px - self.height_px / 2.0) / self.scale)',
     '        return (self.mid_u + (x_px - self.width_px / 2.0) / self.scale,\n'
     '                self.mid_v + (y_px - self.height_px / 2.0) / self.scale)',
     TSL + "test_to_px_round_trips_through_to_mm",
     "the flipped v sign in to_mm reverted, so a click would resolve to "
     "a millimetre point mirrored top-to-bottom from the one drawn there"),

    (COL_SKETCH, '        if distance_sq > limit_sq:\n            continue',
     '        if distance_sq < limit_sq:\n            continue',
     TK + "test_bar_at_point_misses_outside_the_radius",
     "the pick radius comparison inverted -- bar_at_point would hit only "
     "bars OUTSIDE the pick radius and miss the one actually clicked"),

    (COL_SCRIPT, '        if len(self._tie_selection) < 2:',
     '        if len(self._tie_selection) < 1:',
     TC + "test_add_tie_refuses_under_two_bars",
     "the under-2-bars refusal loosened to under-1, letting Add tie "
     "commit a single bar as though it were a tie"),

    # ---- #137 review round: the caption-wiped-on-redraw defect ------
    (COL_SCRIPT,
     '        self._clear_canvases()\n'
     '        # #137: MUST run after _clear_canvases, which blanks this caption\n'
     '        # unconditionally. A handler that sets the caption and then calls\n'
     '        # redraw_sketch would otherwise have it wiped in the same click --\n'
     '        # centralising the write HERE, last, is what makes that ordering\n'
     '        # impossible to get wrong from a call site again.\n'
     '        self._update_tie_selection_caption()\n',
     '        self._update_tie_selection_caption()\n'
     '        self._clear_canvases()\n'
     '        # #137: MUST run after _clear_canvases, which blanks this caption\n'
     '        # unconditionally. A handler that sets the caption and then calls\n'
     '        # redraw_sketch would otherwise have it wiped in the same click --\n'
     '        # centralising the write HERE, last, is what makes that ordering\n'
     '        # impossible to get wrong from a call site again.\n',
     TC + "test_the_selection_caption_is_set_AFTER_the_clear_not_before",
     "the caption written BEFORE _clear_canvases again, so 'selecting: "
     "1 6' is set and then blanked in the same redraw -- the exact review "
     "defect this ordering exists to rule out"),

    (COL_XAML,
     '<Canvas x:Name="section_canvas" ClipToBounds="True"\n'
     '                                Background="Transparent"/>',
     '<Canvas x:Name="section_canvas" ClipToBounds="True"/>',
     TC + "test_the_section_canvas_is_hit_testable_over_empty_area",
     "Background=\"Transparent\" removed from section_canvas, so a WPF "
     "Canvas is no longer hit-testable over empty area and the grown "
     "BAR_PICK_RADIUS_PX buys nothing"),

    # ---- #141: triangular ties -- the Loop / Triangle UI half ---------
    (COL_SCRIPT, '        triangle = self._tie_shape_is_triangle()',
     '        triangle = False',
     TC + "test_add_tie_writes_a_T_marked_line_only_for_triangle",
     "#141 -- Add tie stopped asking which shape is selected, so a "
     "Triangle pick would silently write an unmarked (loop) line"),

    (COL_SCRIPT,
     '        if triangle and len(self._tie_selection) != 3:\n'
     '            self.tie_selection_caption_tb.Text = (\n'
     '                "A triangle touches exactly three bars -- %d selected. "\n'
     '                "Clear the selection and pick exactly three."\n'
     '                % len(self._tie_selection))\n'
     '            return\n',
     '',
     TC + "test_add_tie_refuses_a_triangle_of_the_wrong_bar_count",
     "#141 -- the exactly-three-bars refusal removed, so a Triangle pick "
     "of any count would be written as though it were valid"),

    (COL_SCRIPT, '            line = "T " + line',
     '            pass',
     TC + "test_add_tie_writes_a_T_marked_line_only_for_triangle",
     "#141 -- the T marker dropped, so a Triangle selection would write "
     "an unmarked line indistinguishable from a loop"),

    (COL_SCRIPT, 'TIE_SHAPE_CHOICES = ("Loop", "Triangle")',
     'TIE_SHAPE_CHOICES = ("Triangle", "Loop")',
     TC + "test_the_tie_shape_combo_exists_with_loop_and_triangle",
     "#141 -- the combo's two entries swapped, so _tie_shape_is_triangle "
     "(SelectedIndex == 1) would read Loop as Triangle and vice versa"),

    # ---- #141: triangular ties -- the core geometry ---------------
    (COL_TIES, '    if len(indices) != 3:',
     '    if False:',
     "tests/test_column_triangular_ties.py::"
     "test_a_triangle_needs_exactly_three_bars",
     "#141 -- a triangle subset of any bar count silently accepted, "
     "instead of refusing anything but exactly three"),

    (COL_TIES, '        if leg_lengths[i] < edge_minimums[i]:',
     '        if False:',
     "tests/test_column_triangular_ties.py::"
     "test_an_unbuildable_triangle_is_refused_by_name",
     "#141 -- the generalised A1 bend test disabled, so an unbendable "
     "triangle would be built rather than refused"),

    (COL_TIES, '    if axis == (0.0, 0.0):\n        return None',
     '    if axis == (1.0, 1.0):\n        return None',
     "tests/test_column_triangular_ties.py::"
     "test_collinear_bars_are_refused_not_silently_degenerate",
     "#141 -- the collinear-bisector guard given an anchor that can never "
     "match a unit vector, so three collinear bars would divide by "
     "sin(pi/2) instead of being refused -- which happens to not crash, "
     "so the refusal message and ValueError are what this catches"),

    # ---- #133: fy shown, longitudinal filtered to T ------------------
    (GRADES, '    return type_name.strip().upper().endswith(HIGH_TENSILE_NAME_SUFFIX)',
     '    return True',
     "tests/test_bar_type_grade.py::"
     "test_the_longitudinal_list_takes_T_types_only",
     "#133 -- every type treated as high tensile, so an M bar is offered "
     "for the vertical steel"),

    (BAR_TYPES,
     '        if high_tensile_only and not is_high_tensile_by_name(name):\n'
     '            continue\n',
     '',
     "tests/test_bar_type_grade.py::"
     "test_the_longitudinal_list_takes_T_types_only",
     "#133 -- the longitudinal filter removed from the adapter"),

    (BAR_TYPES, '        yield_mpa = bar_type_yield_mpa(bar_type, document)',
     '        yield_mpa = 420.0',
     "tests/test_bar_type_grade.py::"
     "test_every_label_carries_the_yield_strength",
     "#133 -- fy defaulted to the common value instead of read, so a type "
     "with NO material claims 420 MPa"),

    (COL_SCRIPT, '        options = bar_type_options(revit.doc, internal_to_mm)',
     '        options = bar_type_options(revit.doc, internal_to_mm, high_tensile_only=True)',
     TC + "test_both_bar_pickers_show_EVERY_type",
     "#135 -- the withdrawn T filter reintroduced into the window, which "
     "empties the longitudinal picker on a project with no T-named types"),

    # ---- #120: the Apply path, R23/R25 ------------------------------
    (COL_PLACER, '    refuse_if_not_ready(plan)\n\n    transaction = Transaction(doc, TRANSACTION_NAME)',
     '    transaction = Transaction(doc, TRANSACTION_NAME)',
     TCP + "test_apply_never_opens_a_transaction_when_blocked",
     "R25 -- apply's own refuse_if_not_ready gate deleted, so a "
     "transaction opens on a plan already known to fail"),

    (COL_PLACER,
     '        for element in ours:\n'
     '            doc.Delete(element.Id)\n'
     '\n'
     '        ties_created = _place_ties_by_role(',
     '        for element in ours:\n'
     '            doc.Delete(element.Id)\n'
     '        transaction.Commit()\n'
     '        transaction = Transaction(doc, TRANSACTION_NAME)\n'
     '        transaction.Start()\n'
     '\n'
     '        ties_created = _place_ties_by_role(',
     TCP + "test_a_failed_rebuild_leaves_the_original_cage_intact",
     "R25 -- the deletions committed in their own transaction before the "
     "rebuild, so a failed rebuild cannot restore what is already gone "
     "(the worst state R25 exists to rule out)"),

    (COL_SCRIPT, '        if ours:\n',
     '        if False and ours:\n',
     TCA + "test_the_dialog_is_gated_behind_ours_being_non_empty",
     "R23 -- the replace dialog skipped even when elements of ours exist"),

    # ---- rc2 live failure: Location.Point.Z is not the elevation -------
    (COL_HOST, '                        probe_z)',
     '                        point.Z + 4.0 * RAY_CLEARANCE_INTERNAL)',
     TH + "test_no_ray_origin_is_built_from_Location_Point_Z",
     "self-test ray back at the project base -- upper storey unseeable"),

    (COL_HOST, '        origin = DB.XYZ(point.X, point.Y, max_z - inset)',
     '        origin = DB.XYZ(point.X, point.Y, point.Z + inset)',
     TH + "test_the_support_rays_start_inside_the_column_s_own_ends",
     "upward search from the project base -- ground soffit as the top"),

    (COL_HOST, '        origin = DB.XYZ(point.X, point.Y, min_z + inset)',
     '        origin = DB.XYZ(point.X, point.Y, point.Z - inset)',
     TH + "test_the_support_rays_start_inside_the_column_s_own_ends",
     "downward search from the project base"),

    (COL_HOST, '    probe_z = 0.5 * (min_z + max_z)',
     '    probe_z = max_z',
     TH + "test_the_view_self_test_fires_at_the_column_s_mid_height",
     "self-test grazing the column's top face instead of its middle"),

    (COL_HOST, '    return min(RAY_CLEARANCE_INTERNAL, span / 4.0)',
     '    return RAY_CLEARANCE_INTERNAL',
     TH + "test_a_short_column_cannot_invert_its_two_ray_origins",
     "a short column's two ray origins silently inverted"),

    (COL_HOST, '    box = element.get_BoundingBox(None)',
     '    box = element.Location.Point',
     TH + "test_the_vertical_extent_comes_from_the_bounding_box",
     "the vertical extent taken from the insertion point again"),

    (COL_TIES, '            if upper - lower > MAX_TIE_BRANCH_SPACING_MM:',
     '            if False:',
     TT + "test_the_branch_spacing_limit_bites_on_a_bare_perimeter",
     "the 300 mm tie-branch limit never checked"),

    # ---- R19: a tie is the bars it touches, not a run ------------
    (COL_TIES, '    if len(set(indices)) != len(indices):',
     '    if False:',
     TT + "test_a_repeated_bar_is_refused_rather_than_absorbed",
     "a bar named twice absorbed silently by the bounding box"),

    (COL_TIES, '        if len(parts) < 2:',
     '        if len(parts) < 99:',
     TT + "test_a_cross_tie_line_is_two_bar_numbers",
     "every tie line rejected, so no topology can be stated"),

    # ---- R20: a cross-tie is a leg. Retargeted by R29 (#146): the
    # ---- cross-tie special case these used to mutate is gone, and
    # ---- one leg reading now answers for every kind.
    (COL_TIES, '    if len(points) < 2:',
     '    if len(points) < 3:',
     TT + "test_a_cross_tie_COUNTS_as_a_branch_for_the_300_mm_rule",
     "cross-ties ignored again -- only nested loops can satisfy 300 mm"),

    # R20's 'counted on BOTH axes' case is GONE, deliberately, and this
    # note is what replaces it. Under R29 the defect is unreachable by
    # mutating either line: for a cross-tie's wrong axis the `across`
    # test rejects it, and with that test switched off the `along` test
    # rejects it anyway, and vice versa. Two independent guards, so no
    # single mutation can produce the defect -- which is a property of
    # the code, not a hole in the proving. Each guard is proven
    # separately by R29's diagonal and zero-length cases below, and
    # test_a_cross_tie_is_a_leg_only_on_the_axis_it_SPANS still asserts
    # the behaviour directly. Contriving a two-line mutation to keep the
    # count up would be proving the prover, not the guard.

    # ---- #90: the perimeter model and the sketch ----------------

    (COL_PERIM, '        clear = centre_to_centre - bar_dia_mm',
     '        clear = centre_to_centre',
     TY + "test_the_gap_is_CLEAR_distance_not_centre_to_centre",
     "centre-to-centre reported as a clear distance (mis-tiers 6.1)"),

    (COL_PERIM, '    ordered += [(u, -half_v) for u in us[:-1]]',
     '    ordered += [(u, -half_v) for u in us]',
     TY + "test_the_four_corner_bars_appear_ONCE_each",
     "a corner bar placed twice (eight corners in the model)"),

    (COL_PERIM, '    if clear_mm <= TIER_ALTERNATE_MAX_MM:',
     '    if clear_mm <= TIER_EVERY_BAR_MAX_MM:',
     TY + "test_the_tier_boundaries_are_inclusive_upward",
     "section 6.1 tier 1 widened to swallow tier 2"),

    (COL_PERIM, '    return TIER_EXCEEDED',
     '    return TIER_EVERY_BAR',
     TY + "test_a_bare_four_bar_column_exceeds_every_tier",
     "a gap no tier covers reported as compliant"),

    (COL_PERIM, '    return (b_mm / 2.0 - cover_mm - tie_dia_mm / 2.0,',
     '    return (b_mm / 2.0 - cover_mm,',
     TY + "test_the_tie_centreline_carries_the_HALF_TIE_term",
     "the tie outer face used as its centreline (#67 error)"),

    (COL_SKETCH, '    return "dimension_fail" if tier == TIER_EXCEEDED else "dimension_pass"',
     '    return "dimension_pass"',
     TK + "test_a_section_6_1_violation_is_drawn_in_the_FAIL_style",
     "a 6.1 violation drawn as if it complied"),

    (COL_SKETCH, '            style = "bar_corner"',
     '            style = "bar_main"',
     TK + "test_corner_bars_are_drawn_in_their_OWN_style",
     "corner bars drawn as if they will not move (R15)"),

    (COL_SKETCH_PAL, '    "dimension_fail": "DangerRed",',
     '    "dimension_fail": "NoSuchBrush",',
     TK + "test_every_mapped_brush_exists_in_the_SHARED_palette",
     "a sketch brush the shared palette never declares"),

    # ---- #91: the report and the tie ladder ---------------------

    (COL_LEVELS, '    levels = [TieLevel(index=i, z_mm=z, zone=zone, mirrored=bool(i % 2))',
     '    levels = [TieLevel(index=i, z_mm=z, zone=zone, mirrored=True)',
     TL + "test_section_6_3_alternates_every_other_level",
     "every tie mirrored, so the hook corner never moves"),

    (COL_LEVELS, '    middle_step = span / interval_count',
     '    middle_step = middle_zone_spacing_mm',
     TL + "test_the_middle_run_is_divided_EQUALLY_and_under_the_cap",
     "the middle run stepped from one end, leaving a ragged last bay"),

    (COL_LEVELS, '    z = clear_height_mm - first_tie_offset_mm',
     '    z = clear_height_mm - confinement_spacing_mm',
     TL + "test_the_first_tie_sits_at_exactly_50_from_each_support_face",
     "the top first tie no longer 50 mm from the top face"),

    (COL_LEVELS, '    if 2.0 * l0_mm >= clear_height_mm:',
     '    if False:',
     TL + "test_a_column_shorter_than_two_confinement_zones_is_refused",
     "a silently empty middle zone on a short column"),

    (COL_REPORT, '    sections.append(outstanding_section())\n    return sections',
     '    return sections',
     TP + "test_the_report_says_its_positions_are_IDEALISED",
     "the page dropping what it cannot yet claim"),

    (COL_REPORT, '% _mm(plan.confinement_spacing_mm))',
     '% _mm(plan.s0_mm))',
     TP + "test_the_spacing_section_reads_the_built_values_not_the_limits",
     "the report showing a code limit where the built value belongs"),

    # ---- #88: the inputs ----------------------------------------

    (COL_INPUTS, '    total = 2 * (count_b_face + count_h_face) - 4',
     '    total = 2 * (count_b_face + count_h_face)',
     TI + "test_the_four_corner_bars_are_counted_ONCE_not_twice",
     "the four corner bars counted twice (eight corners in Revit)"),

    (COL_INPUTS, '        if value < MIN_BARS_PER_FACE:',
     '        if value < 1:',
     TI + "test_a_face_cannot_carry_fewer_than_its_two_shared_corners",
     "a face with fewer bars than the corners it shares"),

    (COL_INPUTS, '            length_mm=float(entered_value) * float(bar_diameter_mm),',
     '            length_mm=float(entered_value),',
     TI + "test_ls_as_a_multiplier_uses_the_TYPE_diameter_not_the_name",
     "an Ls multiplier that never multiplies"),

    (COL_SPACING, '    best = min(c.value_mm for c in candidates)',
     '    best = max(c.value_mm for c in candidates)',
     TS + "test_s0_on_the_live_column_and_which_term_governs",
     "S0 taking the LARGEST candidate (under-confining the column)"),

    (COL_SPACING, '    return MIDDLE_ZONE_MULTIPLIER * _positive(s0_mm, \"S0\")',
     '    return min(MIDDLE_ZONE_MULTIPLIER * _positive(s0_mm, \"S0\"), 150.0)',
     TS + "test_middle_zone_is_twice_s0_with_no_150_cap",
     "the 150 mm cap section 5 exists to remove, put back"),

    (COL_SPACING,
     '        built_confinement = _positive(manual_confinement_mm,',
     '        built_confinement = s0.s0_mm  #',
     TS + "test_mode_b_builds_the_USER_value_and_flags_it",
     "Mode B silently building the code limit instead of the input"),

    (COL_SPACING, '        if value_mm > limit_mm:',
     '        if value_mm != limit_mm:',
     TS + "test_a_tighter_manual_spacing_is_not_flagged",
     "a conservative spacing flagged as a violation"),

    (COL_SCRIPT, '        self.spacing_flags_tb.Text = \"\\n\".join(f.message for f in plan.flags)',
     '        self.spacing_flags_tb.Text = \"\"',
     TC + "test_the_section_8_flags_actually_reach_the_screen",
     "section 8 flags computed and then never shown"),

    (COL_XAML,
     '                                   Foreground=\"{StaticResource WarningAmber}\"',
     '                                   Foreground=\"{StaticResource DangerRed}\"',
     TC + "test_a_section_8_flag_is_amber_not_red",
     "a warn-but-place flag painted as a refusal"),

    (COL_RULES, '    if len(vertical) != 4:',
     '    if len(vertical) < 4:',
     TR + "test_the_i_section_is_refused_on_its_face_COUNT",
     "an I-section accepted as rectangular (its normals match)"),

    (COL_RULES, '        base_source=(SOURCE_LEVEL_ELEVATION if base_face_z_mm is None\n                     else SOURCE_SUPPORT_FACE),',
     '        base_source=SOURCE_SUPPORT_FACE,',
     TR + "test_a_missing_base_support_is_normal_and_falls_back_to_the_level",
     "a level elevation reported as a measured support face"),

    (SHARED_STYLES, 'return "file:///" + _quote(normalised, safe="/:")',
     'return "file:///" + normalised',
     "tests/test_ui_shared_styles.py::test_the_uri_percent_encodes_spaces",
     "an unencoded space or ampersand in the palette URI"),

    (SCRIPT, "core_plan.innermost_layer_offset_mm(\n                    geometry[\"cover_top_mm\"]",
     "_face(True).layers[-1].offset_mm  # (\n                    geometry[\"cover_top_mm\"]",
     "test_the_placer_does_not_rebuild_a_face_plan_for_the_crack_offsets",
     "FacePlan rebuilt for the crack offsets (the blank-count crash)"),

    (SCRIPT, "self._support_detection = None\n        self.beam_status_tb.Text", "        self.beam_status_tb.Text",
     "test_every_beam_scoped_attribute_is_cleared_on_pick",
     "cached supports surviving a re-pick"),

    # #49's review finding: the pick handler had grown its own copy of the
    # support-detection dict. It agreed with the original key for key,
    # exactly as plan.py's copy of ZONE_LAYOUT_FLAGS agreed -- for three
    # releases, while the report and the placer built different stirrup
    # sets. This mutation puts a second writer back.
    (SCRIPT, "        self._support_detection = _support_detection(",
     '        self._support_detection = {"support_width_start_mm": None}\n'
     "        _unused = _support_detection(",
     "test_the_support_detection_dict_has_exactly_one_writer",
     "a second writer for the support-detection dict"),

    # The report's own half of the shared-plan rule. Its stirrup and crack
    # sections recomputed everything for three releases, and the guard
    # could not see it because the PLACER's calls satisfied the check.
    (REPORT, "core_plan.stirrup_plan(", "hand_rolled_stirrup_zones(",
     "test_report_and_placement_both_use_the_shared_plan",
     "report recomputing the stirrup zones by hand"),

    (REPORT, "core_plan.crack_plan(", "hand_rolled_crack_layers(",
     "test_report_and_placement_both_use_the_shared_plan",
     "report recomputing the crack plan by hand"),

    # NOT text guards -- ordinary tests over an importable module. Proven
    # here anyway, because a re-typed constant is the one kind of defect
    # that arrives looking exactly like correct code, and this one shipped.
    (PLAN, "ZONE_LAYOUT_FLAGS = ZONE_LAYOUT_FLAGS",
     'ZONE_LAYOUT_FLAGS = {\n    "zone1": (True, True),\n'
     '    "zone2": (False, True),\n    "zone3": (False, True),\n}',
     "tests/test_core_plan.py::"
     "test_the_zone_layout_flags_are_the_tested_ones_not_a_second_copy",
     "plan.py holding its own copy of the zone flags again"),

    # The same mutation with today's CORRECT values: a duplicate that
    # agrees is still a duplicate, and this is the one that would slip
    # past a values-only check.
    (PLAN, "ZONE_LAYOUT_FLAGS = ZONE_LAYOUT_FLAGS",
     'ZONE_LAYOUT_FLAGS = {\n    "zone1": (True, True),\n'
     '    "zone2": (False, False),\n    "zone3": (True, True),\n}',
     "tests/test_core_plan.py::test_only_one_module_defines_the_zone_layout_flags",
     "a second copy of the flags, with the right values (today)"),

    # #45. The text check is the one that catches the FOURTEENTH guard --
    # the per-guard table cannot, since a new guard would not be in it.
    (SPACING, "\n                message=message, severity=SEVERITY_BLOCKING,",
     "\n                message=message,",
     "tests/test_guard_severity.py::"
     "test_every_guardmessage_construction_site_in_the_library_declares_one",
     "a guard built without declaring whether it blocks"),

    # And a severity that is declared but WRONG -- downgrading a refusal
    # to a warning, which is the direction that matters.
    (GUARDS, 'message=message, severity=SEVERITY_BLOCKING,\n    )\n\n\ndef free_end_guard_message',
     'message=message, severity=SEVERITY_WARNING,\n    )\n\n\ndef free_end_guard_message',
     "tests/test_guard_severity.py::"
     "test_each_guard_declares_the_severity_v0_1_0_actually_had",
     "a refusal quietly downgraded to a warning"),

    # #49 (U5). The sketch's style-key -> brush mapping is data, not WPF,
    # so it IS importable and tested directly (tests/test_ui_sketch_
    # palette.py) -- proven anyway, since a missing/stale/mistyped entry
    # here is exactly the class of defect that looks like correct code
    # until it draws invisibly on a live host.
    (SKETCH_PALETTE, '    "bar_main": "InkPrimary",\n', "",
     "tests/test_ui_sketch_palette.py::"
     "test_every_sketch_style_key_has_a_brush_mapping",
     "a sketch style key with no brush mapping at all"),

    (SKETCH_PALETTE, '    "caption": "InkMuted",\n}',
     '    "caption": "InkMuted",\n    "not_a_real_style": "InkMuted",\n}',
     "tests/test_ui_sketch_palette.py::"
     "test_no_stale_brush_mapping_for_a_style_that_no_longer_exists",
     "a stale mapping for a style rft.ui.sketch no longer emits"),

    (SKETCH_PALETTE, '"dimension_fail": "DangerRed",',
     '"dimension_fail": "NoSuchBrushXYZ",',
     "tests/test_ui_sketch_palette.py::"
     "test_every_mapped_brush_is_declared_in_the_xaml",
     "a brush name the XAML never declares with x:Key"),

    # #62. The label width estimate and the drawn font size must be the
    # same number: estimate small, draw large, and the clipped tails come
    # straight back with nothing to say so.
    (SCRIPT, "            text_block.FontSize = SKETCH_FONT_SIZE_PX",
     "            text_block.FontSize = 14.0",
     T + "test_the_label_size_estimate_uses_the_font_the_labels_are_drawn_in",
     "the renderer drawing labels at a size it did not estimate"),

    # And the placement itself must stay in the tested module rather than
    # being inlined back into the renderer, where nothing can run it.
    (SCRIPT, "place_labels(boxes, width_px, height_px)",
     "boxes  # place_labels(boxes, width_px, height_px)",
     T + "test_every_label_is_placed_through_the_tested_layout_module",
     "label placement inlined back into the renderer"),

    # #54 (U10). The rule that a restore cannot arm Place holds because
    # four inputs are never stored. tests/test_ui_persistence.py proves
    # that against the real derivation -- but it can only see the field
    # LISTS. A script that slipped a withheld field in on its way past
    # would leave the pure module looking perfectly correct.
    (SCRIPT, "                self._persistable_type_ids(),",
     '                dict(self._persistable_type_ids(),\n'
     '                     crack_bar_type="resurrected"),',
     T + "test_the_script_persists_only_what_the_persistence_module_allows",
     "the script persisting a field that would arm Place"),

    (SCRIPT, "ui_persistence.SETTINGS_SLOT, data, this_project=True)",
     "ui_persistence.SETTINGS_SLOT, data, this_project=False)",
     T + "test_settings_are_stored_per_project_and_never_globally",
     "one job's conventions leaking into every other job"),

    # pyRevit's load_data opens the file directly and RAISES when nothing
    # has been stored -- which is the normal first run on any project.
    #
    # The mutation DELETES the gate, which is the realistic regression:
    # someone "simplifies" two lines that look redundant. The first
    # version of this case flipped the test to `if False and ...` instead
    # and the prover reported MISSED -- because the guard was grepping for
    # "script.data_exists(", which that mutation leaves in place. The
    # guard now parses the method with ast; all three shapes (deleted,
    # short-circuited, and gating without returning) are caught.
    (SCRIPT, "            if not script.data_exists(\n"
             "                    ui_persistence.SETTINGS_SLOT, this_project=True):\n"
             "                return\n", "",
     T + "test_a_first_run_checks_before_loading_stored_data",
     "loading stored data without checking it exists"),

    # The rc3 rename moved the extension, tab, panel and pushbutton and
    # missed this file, so CI failed on every push while the whole suite
    # stayed green -- the only consumer of those paths is a shell command.
    # The mutation is the rename itself, reapplied: put the old extension
    # folder back and require the guard to notice the path is gone.
    (WORKFLOW, "compileall -q RFT.lib",
     "compileall -q SimpleBeamRFT.extension/lib",
     "tests/test_ironpython_compat.py::test_every_path_the_ci_workflow_names_exists",
     "a CI path left behind by a rename"),

    # The other direction, and it is not redundant: the mutation above
    # produces a token containing ".extension", which the guard's
    # predicate matched from the start. #64 introduced a path that matches
    # NONE of the original patterns -- RFT.lib is not a .py, not a .yml
    # and has no ".extension" in it -- so until the predicate learned
    # ".lib" this case would have been MISSED while the one above passed.
    (WORKFLOW, "compileall -q RFT.lib", "compileall -q RFTlib",
     "tests/test_ironpython_compat.py::test_every_path_the_ci_workflow_names_exists",
     "the shared library path itself mistyped"),

    # #61. The Review report's "REFUSED (section 6.2-6.4)" lines were
    # never consulted at Place, so a face the report said would fail
    # (A43/A44's sub-minimum spacing, A36's option-1-with-multiple-layers)
    # was placed anyway. All the shapes a text guard can miss, per this
    # ticket's own instruction: the check deleted, short-circuited by a
    # constant, present but not returning on a refusal, and (round 3)
    # re-nested behind an enclosing condition that a reachability-based
    # guard cannot see through -- which is why the guard now requires the
    # assign and the gate to be DIRECT statements of on_place_click's own
    # body instead of reasoning about what encloses them.
    (SCRIPT, "        spacing_messages = self._spacing_refusal_messages(review, geometry)\n",
     "",
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the section 6.2-6.4 spacing preflight deleted from Place"),

    (SCRIPT, "        if spacing_messages:",
     "        if False and spacing_messages:",
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the spacing gate short-circuited by a constant"),

    (SCRIPT, '                title="Section 6.2-6.4 spacing violation",\n'
             "            )\n"
             "            return\n",
     '                title="Section 6.2-6.4 spacing violation",\n'
     "            )\n",
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the spacing gate alerting but not returning, so Place proceeds anyway"),

    # This is the hole-A case from round 2, adapted rather than dropped:
    # the ENCLOSING `if` it used to target (`if "error" not in geometry:`)
    # no longer exists, but the same short-circuit-by-constant shape now
    # applies to the geometry-error check itself, which precedes the
    # preflight instead of enclosing it.
    (SCRIPT, "        # statement is a decidable, total check instead: it always runs.\n"
             "        geometry = self._gather_report_geometry(b_mm, h_mm)\n"
             '        if "error" in geometry:',
     "        # statement is a decidable, total check instead: it always runs.\n"
     "        geometry = self._gather_report_geometry(b_mm, h_mm)\n"
     '        if False and "error" in geometry:',
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the geometry-error check short-circuited by a constant"),

    # Round 3's own review: the preceding geometry-error check inverted,
    # so the spacing preflight only ever runs when geometry has ALREADY
    # failed to read -- i.e. never in the normal case. No constant
    # appears anywhere, so the constant-false sweep does not catch this;
    # only requiring the assign to sit directly in on_place_click's body
    # (round 3's fix) can, since the inverted check no longer determines
    # whether that statement is reachable at all -- it is unconditional.
    (SCRIPT, "        # statement is a decidable, total check instead: it always runs.\n"
             "        geometry = self._gather_report_geometry(b_mm, h_mm)\n"
             '        if "error" in geometry:',
     "        # statement is a decidable, total check instead: it always runs.\n"
     "        geometry = self._gather_report_geometry(b_mm, h_mm)\n"
     '        if "error" not in geometry:',
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the preceding geometry-error check inverted, so the preflight "
     "never runs in the normal case"),

    # And the same review found the assign+gate can be RE-NESTED behind a
    # condition that is always false but names no constant a naive sweep
    # would catch (`if 1 == 2:`, not `if False:`). The direct-body check
    # closes this because there is no longer an enclosing `if` for either
    # statement to legally sit inside.
    (SCRIPT, "        spacing_messages = self._spacing_refusal_messages(review, geometry)\n"
             "        if spacing_messages:\n"
             "            forms.alert(\n"
             '                "\\n\\n".join(m.message for m in spacing_messages),\n'
             '                title="Section 6.2-6.4 spacing violation",\n'
             "            )\n"
             "            return\n",
     "        if 1 == 2:\n"
     "            spacing_messages = self._spacing_refusal_messages(review, geometry)\n"
     "            if spacing_messages:\n"
     "                forms.alert(\n"
     '                    "\\n\\n".join(m.message for m in spacing_messages),\n'
     '                    title="Section 6.2-6.4 spacing violation",\n'
     "                )\n"
     "                return\n",
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the preflight re-nested inside an always-false non-constant "
     "condition (if 1 == 2:)"),

    # And the same round-2 review found `return` can be buried under a
    # nested `if False:` inside the gate: it is still reachable by
    # `ast.walk`, so a check that only asks "is a Return present somewhere
    # under here" passes against code that can never execute it.
    (SCRIPT, "        if spacing_messages:\n"
             "            forms.alert(\n"
             '                "\\n\\n".join(m.message for m in spacing_messages),\n'
             '                title="Section 6.2-6.4 spacing violation",\n'
             "            )\n"
             "            return\n",
     "        if spacing_messages:\n"
     "            if False:\n"
     "                forms.alert(\n"
     '                    "\\n\\n".join(m.message for m in spacing_messages),\n'
     '                    title="Section 6.2-6.4 spacing violation",\n'
     "                )\n"
     "                return\n",
     T + "test_place_preflight_checks_spacing_before_the_transaction_opens",
     "the refusal's return buried under a nested if False, so it never runs"),

    # The window has to name the build it is running. Without it, a
    # candidate that does NOT contain the fix under test looks identical
    # to one that does -- which cost a whole round trip during #61's
    # testing.
    (SCRIPT, 'self.Title = "{} -- {}".format(self.Title, _loaded_version())',
     'pass  # title not stamped', 'tests/test_simple_beam_xaml.py::test_the_window_names_the_build_it_is_running',
     "the window not naming its build"),

    # The realistic drift, and why the guard asks WHAT the title is built
    # from rather than merely that it is assigned: someone hard-codes the
    # version and it silently stops matching the checkout.
    (SCRIPT, '.format(self.Title, _loaded_version())',
     '.format(self.Title, "v0.3.1-rc2")', 'tests/test_simple_beam_xaml.py::test_the_window_names_the_build_it_is_running',
     "a hard-coded version in the window title"),

    (XAML, 'Title="Simple Beam"', 'Title="Detail Beam"', 'tests/test_simple_beam_xaml.py::test_the_window_names_the_build_it_is_running',
     "the pre-rc3 window title returning"),

    (VERSION_FILE, VERSION_NOW, "v0.0.0-not-a-release", 'tests/test_simple_beam_xaml.py::test_the_version_file_matches_the_newest_changelog_entry',
     "VERSION bumped out of step with the changelog"),

    # #65: a main face with a bar count entered but missing its bar type
    # and/or layer count was placed as if fully blank, silently -- the
    # live defect this ticket reports. Same four shapes a text guard can
    # miss as #61's spacing preflight above: deleted, short-circuited by a
    # constant, present but not returning, and re-nested behind an
    # always-false non-constant condition.
    (SCRIPT, "        face_gap_messages = self._face_gap_messages()\n",
     "",
     T + "test_place_preflight_checks_face_gaps_before_the_transaction_opens",
     "the issue #65 face-gap preflight deleted from Place"),

    (SCRIPT, "        if face_gap_messages:",
     "        if False and face_gap_messages:",
     T + "test_place_preflight_checks_face_gaps_before_the_transaction_opens",
     "the face-gap gate short-circuited by a constant"),

    (SCRIPT, '                title="Main bar face incomplete",\n'
             "            )\n"
             "            return\n",
     '                title="Main bar face incomplete",\n'
     "            )\n",
     T + "test_place_preflight_checks_face_gaps_before_the_transaction_opens",
     "the face-gap gate alerting but not returning, so Place proceeds "
     "anyway"),

    (SCRIPT, "        face_gap_messages = self._face_gap_messages()\n"
             "        if face_gap_messages:\n"
             "            forms.alert(\n"
             '                "\\n\\n".join(m.message for m in face_gap_messages),\n'
             '                title="Main bar face incomplete",\n'
             "            )\n"
             "            return\n",
     "        if 1 == 2:\n"
     "            face_gap_messages = self._face_gap_messages()\n"
     "            if face_gap_messages:\n"
     "                forms.alert(\n"
     '                    "\\n\\n".join(m.message for m in face_gap_messages),\n'
     '                    title="Main bar face incomplete",\n'
     "                )\n"
     "                return\n",
     T + "test_place_preflight_checks_face_gaps_before_the_transaction_opens",
     "the preflight re-nested inside an always-false non-constant "
     "condition (if 1 == 2:)"),

    # ---- #140: ResolvedTie.vertices is the one polygon three consumers
    # read, instead of each re-deriving the same four corners. Proven
    # against the reordering/dropping this ticket's own guard names.

    (COL_TIES,
     'return [(centre_u - half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v + half_v),\n'
     '            (centre_u - half_u, centre_v + half_v)]',
     'return [(centre_u + half_u, centre_v - half_v),\n'
     '            (centre_u - half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v + half_v),\n'
     '            (centre_u - half_u, centre_v + half_v)]',
     TV + "test_a_closed_loops_vertices_are_the_four_corners_resolve_tie_finds",
     "#140 -- a closed loop's first two vertices swapped, so the polygon "
     "no longer winds consecutive-corner-to-consecutive-corner"),

    (COL_TIES,
     'return [(centre_u - half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v + half_v),\n'
     '            (centre_u - half_u, centre_v + half_v)]',
     'return [(centre_u - half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v - half_v),\n'
     '            (centre_u + half_u, centre_v + half_v)]',
     TV + "test_a_closed_loops_vertices_are_the_four_corners_resolve_tie_finds",
     "#140 -- a closed loop's fourth vertex dropped"),

    (COL_TIES,
     'vertices = [(bars[0].u_mm, bars[0].v_mm),\n'
     '                    (bars[-1].u_mm, bars[-1].v_mm)]',
     'vertices = [(bars[-1].u_mm, bars[-1].v_mm),\n'
     '                    (bars[0].u_mm, bars[0].v_mm)]',
     TV + "test_a_cross_ties_vertices_are_its_two_ends_from_the_layout",
     "#140 -- a cross-tie's two ends swapped, so 'vertices' no longer "
     "names the subset's own first/last bar in the order it was typed"),

    (COL_PLACE_TIES,
     '    corners = tie.vertices\n'
     '    if mirrored:',
     '    cu, cv = tie.centre_u_mm, tie.centre_v_mm\n'
     '    hu, hv = tie.half_u_mm, tie.half_v_mm\n'
     '    corners = [(cu - hu, cv - hv), (cu + hu, cv - hv),\n'
     '               (cu + hu, cv + hv), (cu - hu, cv + hv)]\n'
     '    if mirrored:',
     TV + "test_a_reordered_closed_loop_vertex_list_changes_the_drawn_polygon",
     "#140 -- the placer's curve builder reverted to re-deriving the "
     "closed loop's corners from centre/half instead of reading "
     "tie.vertices, so a mutated vertex order is silently ignored"),

    (COL_PLACE_TIES,
     '    return [(tie.vertices[0], tie.vertices[-1])]',
     '    return [(tie.vertices[-1], tie.vertices[0])]',
     TV + "test_a_cross_ties_vertices_match_the_placers_own_segment_builder",
     "#140 -- the placer's cross-tie segment reversed, so the first "
     "curve point is no longer the subset's first-named bar"),

    (COL_SKETCH,
     '    if tie.kind == KIND_CROSS_TIE:\n'
     '        (u1, v1), (u2, v2) = tie.vertices[0], tie.vertices[-1]\n'
     '        return [SketchLine(u1=u1, v1=v1, u2=u2, v2=v2, style="cross_tie")]\n'
     '    return [SketchPolygon(points=list(tie.vertices), style=loop_style)]',
     '    cu, cv = tie.centre_u_mm, tie.centre_v_mm\n'
     '    hu, hv = tie.half_u_mm, tie.half_v_mm\n'
     '    if tie.kind == KIND_CROSS_TIE:\n'
     '        return [SketchLine(u1=cu - hu, v1=cv - hv, u2=cu + hu, v2=cv + hv,\n'
     '                           style="cross_tie")]\n'
     '    return [SketchPolygon(points=[\n'
     '        (cu - hu, cv - hv), (cu + hu, cv - hv),\n'
     '        (cu + hu, cv + hv), (cu - hu, cv + hv),\n'
     '    ], style=loop_style)]',
     TV + "test_a_reordered_closed_loop_vertex_list_changes_the_drawn_polygon",
     "#140 -- the sketch reverted to re-deriving the tie's corners from "
     "centre/half instead of drawing tie.vertices, so a mutated vertex "
     "order never reaches the canvas"),

    # ---- #153: batch placement, R33 ----------------------------------
    (COL_BATCH_CORE, '        clear_height_mm=extent.clear_height_mm,',
     '        clear_height_mm=0.0,',
     TCB + "test_two_columns_same_type_different_clear_height_land_in_different_groups",
     "R33 -- the grouping key's clear height dropped to a constant, so two "
     "columns with genuinely different clear heights would land in the "
     "SAME group and one of them would get the other's tie ladder"),

    (COL_BATCH_CORE,
     '        top_support_found=(extent.top_source == SOURCE_SUPPORT_FACE))',
     '        top_support_found=True)',
     TCB + "test_same_clear_height_but_different_top_support_split_too",
     "R33 -- the grouping key reduced to the family type in all but name: "
     "whether a top support was found no longer varies the key, so two "
     "columns that #104 measured as needing separate cages would merge"),

    (COL_BATCH_ADAPTER,
     '        try:\n'
     '            refuse_if_not_ready(plan)\n'
     '        except ColumnPlacementError as refusal:\n'
     '            exclusions.append(Exclusion(\n'
     '                element_id=element.Id.IntegerValue, reason=str(refusal)))\n'
     '            continue\n'
     '        candidates.append(\n'
     '            ColumnCandidate(element=element, host=host, plan=plan))',
     '        candidates.append(\n'
     '            ColumnCandidate(element=element, host=host, plan=plan))',
     TCB + "test_plan_candidates_excludes_a_column_refuse_if_not_ready_declines",
     "spec Section 5 -- the per-column refuse_if_not_ready gate skipped in "
     "plan_candidates, so a column the single-column path would refuse "
     "reaches the batch's own candidate list uncaught"),

    (COL_BATCH_ADAPTER,
     '        refuse_if_not_ready(candidate.plan)\n'
     '        if candidate.ours is None or candidate.foreign is None:',
     '        if candidate.ours is None or candidate.foreign is None:',
     TCB + "test_apply_batch_refuses_before_opening_when_a_candidate_plan_is_blocked",
     "R25 extended -- apply_batch's own belt-and-braces refuse_if_not_ready "
     "re-check deleted, so a caller that reached apply_batch with an "
     "already-blocked plan could open the shared transaction anyway"),

    (COL_BATCH_ADAPTER,
     '            per_column.append((host_id, PlacementResult(\n'
     '                ties_created=ties_created, bars_created=bars_created,\n'
     '                replaced_count=len(ours), foreign=foreign)))\n'
     '    except Exception:',
     '            per_column.append((host_id, PlacementResult(\n'
     '                ties_created=ties_created, bars_created=bars_created,\n'
     '                replaced_count=len(ours), foreign=foreign)))\n'
     '            transaction.Commit()\n'
     '            transaction = Transaction(doc, BATCH_TRANSACTION_NAME)\n'
     '            transaction.Start()\n'
     '    except Exception:',
     TCB + "test_apply_batch_uses_exactly_one_transaction_for_every_candidate",
     "spec Section 4 -- the single shared transaction split into one per "
     "candidate, committing after each column instead of once for the "
     "whole batch, so a later column's failure can no longer roll back an "
     "earlier column's own rebuild (R25 extended)"),

    (COL_REPORT,
     '        lines.append(\n'
     '            "Group %d -- clear height %s, %s -- column(s): %s"\n'
     '            % (index, _mm(group.key.clear_height_mm), support,\n'
     '               ", ".join(str(element_id)\n'
     '                        for element_id in group.element_ids)))',
     '        lines.append("Group %d -- %s" % (index, support))',
     TCB + "test_batch_group_section_names_each_group_its_height_and_its_columns",
     "R33 -- the group's clear height and its column ids dropped from the "
     "report line, so a reviewer can no longer see WHICH columns fell in "
     "which group or WHY the run split them"),

    (COL_REPORT,
     '        lines = ["Column %s -- %s" % (exclusion.element_id, exclusion.reason)\n'
     '                 for exclusion in exclusions]',
     '        lines = ["Column %s" % exclusion.element_id\n'
     '                 for exclusion in exclusions]',
     TCB + "test_batch_exclusion_section_names_every_exclusion_and_its_reason",
     "spec Section 5 -- an excluded column's reason dropped from the "
     "report, so the engineer sees THAT a column was excluded but not WHY"),

    (COL_SCRIPT,
     '        self.report_tb.Text = report\n',
     '',
     TCBW + "test_the_batch_report_is_rendered_before_apply_batch_is_called",
     "#153 -- the batch report's assignment removed from before "
     "apply_batch runs, so a refusal or a rolled-back failure would show "
     "no groups or exclusions at all rather than R33's report"),
    # ---- #153 review: spec Section 6 (R23/R24) in the batch

    (COL_BATCH_ADAPTER,
     '        if candidate.ours is None or candidate.foreign is None:',
     '        if False:',
     TCB + "test_apply_batch_refuses_when_read_existing_was_never_run",
     "R23 -- apply_batch allowed to open the shared transaction on "
     "candidates whose existing reinforcement was never read, so it "
     "would delete a cage whose count nobody was ever shown"),

    (COL_BATCH_ADAPTER,
     '            ours, foreign = candidate.ours, candidate.foreign',
     '            ours, foreign = existing_elements(doc, candidate.element)',
     TCB + "test_apply_batch_deletes_exactly_what_read_existing_counted",
     "spec Section 6 -- the existing cage re-read INSIDE the "
     "transaction instead of using the set R23's confirmation "
     "counted, so the batch can delete elements the engineer never "
     "saw (the single-column path passes ours/foreign IN for this "
     "exact reason)"),

    (COL_BATCH_ADAPTER,
     '    groups = group_hosts([(candidate.element.Id.IntegerValue, candidate.host)\n'
     '                          for candidate in candidates])',
     '    groups = group_hosts([(element.Id.IntegerValue, host)\n'
     '                          for element, host in reads])',
     TCB + "test_a_column_excluded_by_the_refusal_gate_is_in_NO_group",
     "R33 -- the groups built from every READ column rather than "
     "the survivors, so the report names a column in a group AND in "
     "the exclusion list, contradicting itself about whether that "
     "column gets steel"),

    (COL_REPORT,
     '        if row.foreign_ids:',
     '        if False:',
     TCB + "test_batch_replacement_section_names_every_column_and_its_count",
     "R24 in the batch -- foreign rebar dropped from the "
     "replacement table, so bars this tool must never delete are "
     "also never named"),

    # The anchor moved when every tab refusal was routed through
    # _refuse_on_tab, and CI caught it as NOT PROVEN: the mutation
    # stopped APPLYING, so the case proved nothing while still
    # reading like coverage. Re-anchored, and INVERTED rather than
    # disabled -- `if False:` is the shape that once passed in CI
    # while failing locally on identical content.
    (COL_SCRIPT,
     '            if not proceed:\n'
     '                self._refuse_on_tab(\n'
     '                    self.batch_status_tb,',
     '            if proceed:\n'
     '                self._refuse_on_tab(\n'
     '                    self.batch_status_tb,',
     TCBW + "test_the_batch_confirmation_is_shown_before_apply_batch_and_can_cancel",
     "R23 -- Cancel on the batch's replacement confirmation ignored, "
     "so declining still deletes and rebuilds every column"),

    (COL_SCRIPT,
     '            batch_replacement_section(existing),\n',
     '',
     TCBW + "test_the_batch_report_carries_the_replacement_table",
     "spec Section 6 -- the replacement table dropped from the batch "
     "report, leaving R23's per-column counts in a dialog that is "
     "gone the moment it is dismissed"),
    # ---- #160: the roof termination math (sections 1-2, R35)

    (COL_ROOF,
     '    a = min(a_formula_mm, nominal - MIN_BEND_LEG_MM)',
     '    a = a_formula_mm',
     TCR + "test_the_bend_leg_never_falls_below_the_minimum",
     "section 2.3's cap on a removed, so a thick slab and a short L_D "
     "leave a bend leg of a few millimetres -- the beam tool's own #14 "
     "finding 3, reintroduced in the column tool"),

    (COL_ROOF,
     '    if ld_mm < MIN_BEND_LEG_MM:',
     '    if False:',
     TCR + "test_an_LD_below_the_minimum_bend_leg_is_refused",
     "a below-minimum L_D allowed through, where the cap goes NEGATIVE "
     "and the straight run reverses direction into the Revit API"),

    (COL_ROOF,
     '    run = column_width_mm - cover_mm * 2.0',
     '    run = column_width_mm - cover_mm',
     TCR + "test_the_free_edge_run_is_the_face_width_less_cover_BOTH_sides",
     "cover counted on ONE side only, so the bend ends one cover short "
     "of the far face -- outside the concrete, by exactly the cover"),

    # R41 collapsed section 2's two return paths into one, and three
    # cases went with it. Two are REMOVED rather than contrived: they
    # mutated `b_edge = min(b, run)` and `achieved = a + b_edge - loss`
    # on the free-edge-only branch, and both defects are now the SAME
    # single mutation as the R41 cases above -- a second case proving
    # the same line proves nothing twice. The third was retargeted at
    # the surviving return.

    (COL_ROOF,
     '        return min(b, direction.available_run_mm)',
     '        return b',
     TCR + "test_an_interior_column_NEAR_the_slab_edge_is_capped_too",
     "R41 -- the available run ignored, so an interior column 500 mm "
     "from the slab edge is handed the full leg and puts about 230 mm "
     "of bar outside the concrete (the owner's own case)"),

    (COL_ROOF,
     '    best = max(directions, key=developed_in)',
     '    best = directions[0]',
     TCR + "test_the_bend_goes_where_the_MOST_room_is_not_merely_where_slab_is",
     "R41 -- the bend forced into the first stated direction rather "
     "than the one with the most room, throwing away anchorage that "
     "was there"),

    (COL_ROOF,
     '        run_limited=b_final < b)',
     '        run_limited=False)',
     TCR + "test_an_interior_column_NEAR_the_slab_edge_is_capped_too",
     "R41 -- a capped leg no longer reported as capped, so the one "
     "thing the engineer must notice about a short run is missing "
     "from the report"),

    (COL_ROOF,
     '        free_edge=not best.has_slab, bend_loss_mm=loss,',
     '        free_edge=True, bend_loss_mm=loss,',
     TCR + "test_an_interior_column_NEAR_the_slab_edge_is_capped_too",
     "R41 -- a measured slab edge reported as a free edge the "
     "engineer flagged, which are different facts and only one of "
     "them is the engineer's own statement"),

    (COL_ROOF,
     '    if leg <= 0.0:',
     '    if False:',
     TCR + "test_a_cover_at_or_above_the_thickness_is_refused_not_negative",
     "a slab whose read cover meets or exceeds its thickness (R37 reads "
     "BOTH) allowed to produce a zero or negative vertical leg"),

    (COL_ROOF,
     'MIN_BEND_LEG_MM = 200.0',
     'from .anchorage import MIN_BEND_LEG_MM',
     TCR + "test_this_module_does_NOT_import_anchorage",
     "the constant imported from anchorage instead of restated, which is "
     "the dependency CONTEXT.md forbids and #99 is open about"),

    # ---- R40: L_D is the DEVELOPED centreline length

    (COL_ROOF,
     '    return 2.0 * tangent - bend_radius_mm * theta',
     '    return 0.0',
     TCR + "test_the_fillet_loss_reproduces_the_LIVE_measurement",
     "R40 -- the fillet allowance dropped to zero, so every top-floor bar "
     "is handed nominal legs summing to L_D and develops about 2% less "
     "than L_D, invisibly, on every bar"),

    (COL_ROOF,
     '    nominal = ld_mm + bend_loss_mm',
     '    nominal = ld_mm',
     TCR + "test_a_and_b_add_up_to_LD_where_slab_continues",
     "R40 -- the allowance computed and then not ADDED to the legs, which "
     "is the same 2% shortfall with the arithmetic still in the file"),

    (COL_ROOF,
     '    achieved = a + b_final - loss',
     '    achieved = a + b_final',
     TCR + "test_a_and_b_add_up_to_LD_where_slab_continues",
     "R40 -- the report's achieved length taken from the NOMINAL legs "
     "rather than the built bar, so the page claims an anchorage the steel "
     "does not have"),

    (COL_ROOF,
     '    if leg_mm < needed:',
     '    if False:',
     TCR + "test_a_leg_shorter_than_the_tangent_is_refused",
     "R40 -- a leg shorter than the bend's own tangent allowed through, so "
     "a narrow free edge asks Revit to build a corner that cannot exist"),

    # ---- #167: the top-floor slab adapter ----------------------------

    (COL_ROOF_RUN,
     '        if nearest is None or crossing < nearest:',
     '        if True:',
     TCRR + "test_every_loop_is_considered_not_only_the_first",
     "R42 -- the LAST crossing found wins instead of the NEAREST one, so "
     "an opening listed after the outer boundary is silently ignored"),

    (COL_ROOF_SLAB,
     '        if not isinstance(element, DB.Floor):',
     '        if False:',
     TCRS + "test_something_that_is_not_a_Floor_does_not_count",
     "R37 -- any joined element (a wall, a beam) accepted as the top-floor "
     "slab, so its thickness/cover would be read off the wrong element"),

    (COL_ROOF_SLAB,
     '        if box.Min.Z <= column_top_z <= box.Max.Z:',
     '        if True:',
     TCRS + "test_a_joined_floor_BELOW_the_column_does_not_count",
     "R37/R39 -- the floor a column stands ON accepted as the slab above "
     "it, so a + b would be measured against the wrong Floor entirely"),

    (COL_ROOF_SLAB,
     '        len(candidates) == 1,',
     '        len(candidates) >= 1,',
     TCRS + "test_two_candidate_floors_is_a_REFUSAL_not_a_pick",
     "an ambiguous top-floor slab silently resolved to whichever Floor "
     "was joined first, rather than refusing"),

    (COL_ROOF_SLAB,
     '    if read_mm != 0.0:',
     '    if True:',
     TCRS + "test_a_zero_cover_opens_the_typed_field",
     "R38 -- a cover reading exactly zero (nobody set one) reported as a "
     "REAL read, so the typed field the engineer needs never opens"),

    (COL_ROOF_SLAB,
     '    return crossing_mm - cover_mm',
     '    return crossing_mm',
     TCRS + "test_a_non_zero_slab_cover_is_SUBTRACTED_from_the_measured_run",
     "R42 -- the slab's own cover no longer subtracted from the measured "
     "run, so a real cover's coincidental match with #170's zero-cover "
     "host is silently inherited on every other slab"),

    (COL_ROOF_SLAB,
     '        if name in flagged:',
     '        if False:',
     TCRS + "test_a_flagged_free_edge_uses_the_free_edge_cap_not_the_measured_run",
     "R41 -- an engineer-flagged free edge ignored in favour of the "
     "measured boundary run, so a genuinely absent slab is still trusted"),

    # ---- #167 review: the TOP face, by the route R42 measured

    (COL_ROOF_SLAB,
     '        if candidate.FaceNormal.Z <= UPWARD_TOL:',
     '        if False:',
     TCRS + "test_the_TOP_face_is_chosen_not_merely_a_planar_one",
     "the upward test dropped, so a slab's SOFFIT can supply the "
     "boundary the run is measured from -- a different outline at a "
     "different elevation, and section 1 measures from the top"),

    (COL_ROOF_SLAB,
     '    _require(face is not None,',
     '    _require(True,',
     TCRS + "test_a_floor_with_only_a_DOWNWARD_face_is_refused",
     "a floor with no upward face allowed through instead of "
     "refused, so the run would be measured from nothing"),

    # ---- #172: the roof termination joined into the plan and the report
    # (R36, R38, R40, R41) ----

    (COL_PLAN,
     'manual_confinement_mm=None, manual_middle_zone_mm=None,\n'
     '                  roof_termination=None):',
     'manual_confinement_mm=None, manual_middle_zone_mm=None,\n'
     '                  roof_termination="unstated"):',
     TPL + "test_an_ordinary_column_carries_no_roof_termination",
     "R36 -- the default for roof_termination changed away from None, so "
     "an ordinary column's plan would carry an opinion about a condition "
     "nobody stated"),

    (COL_PLAN, '        roof_termination=roof_termination,\n    )',
     '        roof_termination=None,\n    )',
     TPL + "test_a_stated_roof_termination_is_carried_through_unexamined",
     "a stated roof termination silently dropped on the way into "
     "ColumnPlan"),

    (COL_REPORT,
     '    if roof_termination is not None:\n'
     '        sections.append(roof_termination_section(roof_termination))\n',
     '    sections.append(roof_termination_section(roof_termination))\n',
     TP + "test_the_section_is_absent_from_an_ordinary_columns_report",
     "R36 -- the roof section rendered unconditionally, so an ordinary "
     "column's report would carry a section about a condition nobody "
     "stated"),

    (COL_REPORT, '        if direction.has_slab:',
     '        if not direction.has_slab:',
     TP + "test_every_direction_is_named_FLAGGED_or_DEFAULTED",
     "R41 -- FLAGGED and DEFAULTED swapped, so a genuinely flagged free "
     "edge would read as the conservative default and vice versa"),

    (COL_REPORT,
     '"the nominal legs" % (_mm(t.achieved_mm), _mm(t.ld_mm), t.bend_loss_mm))',
     '"the nominal legs" % (_mm(t.a_mm + t.b_mm), _mm(t.ld_mm), t.bend_loss_mm))',
     TP + "test_achieved_is_the_BUILT_bar_never_the_nominal_legs",
     "R40 -- the report shows the NOMINAL legs handed to the API instead "
     "of what the built bar actually develops, claiming an anchorage the "
     "steel does not have"),

    (COL_REPORT,
     '               "the FLAGGED free edge" if t.free_edge else\n'
     '               "the MEASURED slab edge"))',
     '               "the FLAGGED free edge" if not t.free_edge else\n'
     '               "the MEASURED slab edge"))',
     TP + "test_a_shortfall_names_WHY_it_is_short_flagged_vs_measured",
     "R41 -- a flagged free edge and a measured slab edge swapped in the "
     "shortfall's own explanation, which are different facts and only "
     "one of them is the engineer's own statement"),

    (COL_REPORT, '    if roof.cover_provenance == "read":',
     '    if roof.cover_provenance != "read":',
     TP + "test_cover_provenance_names_the_slab_READ_vs_TYPED",
     "R38 -- READ and TYPED swapped, so a slab with a real cover would be "
     "reported as typed and a typed exception would be reported as read"),

    (COL_REPORT,
     '        taken = " -- BEND TAKEN" if direction.name == t.direction else ""',
     '        taken = " -- BEND TAKEN"',
     TP + "test_the_bend_taken_is_marked_on_its_own_direction_line",
     "every direction marked as the bend taken, so the marker stops "
     "identifying which one actually was"),

    (COL_REPORT, '    if t.shortfall_mm > 0.0:',
     '    if t.shortfall_mm >= 0.0:',
     TP + "test_a_full_LD_reports_no_shortfall",
     "a full L_D (zero shortfall) reported as a shortfall, flagging a bar "
     "that developed everything it was asked for"),

    # ---- #173: the bent bar's own two curves

    (COL_PLACE_BARS,
     '        z_bend_internal = mm_to_internal(top_z_mm + termination.a_mm)',
     '        z_bend_internal = mm_to_internal(top_z_mm)',
     TPB + "test_the_vertical_leg_runs_from_base_to_the_bend_at_top_plus_a",
     "R40/section 1 -- the bend placed at the slab's SOFFIT instead of "
     "a mm up inside it, so the horizontal leg runs under the slab "
     "rather than within it"),

    (COL_PLACE_BARS,
     '        curves.Add(DB.Line.CreateBound(p_bend, p_bend_end))',
     '        pass',
     TPB + "test_a_roof_terminated_bar_is_built_from_TWO_curves",
     "the horizontal leg dropped, leaving a straight bar that stops "
     "inside the slab with no bend -- section 1's whole anchorage gone "
     "while the bar still looks placed"),

    (COL_PLACE_BARS,
     '        bend_vector = _bend_direction_vector(termination.direction,',
     '        bend_vector = _bend_direction_vector("+Hand",',
     TPB + "test_a_MINUS_facing_bend_moves_the_opposite_way_from_facing",
     "every bend forced along +Hand whatever R41 chose, so a bar bends "
     "toward the face with the LEAST room -- the defect R41 exists to "
     "prevent, reintroduced in the placer"),

    # ---- R45: the bent bar's fifth handle

    (COL_PLACE_BARS,
     '        if axis in pinned_axes:',
     '        if axis not in pinned_axes:',
     TPB + "test_a_SECOND_handle_on_the_same_axis_is_left_alone",
     "R45 -- the skip INVERTED, so the first handle on an axis is passed "
     "over and the REPEAT is pinned: the bent bar's far end takes the pin "
     "meant for its vertical leg, collapsing the horizontal leg and "
     "destroying b. An `if False:` mutation was tried first and PASSED in "
     "CI while failing locally on identical content -- an inversion "
     "cannot be read two ways"),

    (COL_PLACE_BARS,
     '        pinned_axes.add(axis)',
     '        pinned_axes.add(None)',
     TPB + "test_a_SECOND_handle_on_the_same_axis_is_left_alone",
     "R45's bookkeeping recording nothing, so the skip never fires "
     "and every repeated axis is pinned again"),

]


def _git(*args):
    return subprocess.check_output(("git",) + args).decode("utf-8", "replace")


def _require_clean(paths):
    """Refuse to mutate anything that is not committed and clean.

    This is the precondition that makes `git checkout --` a safe restore:
    if the file had uncommitted work, restoring it would destroy that work
    instead of undoing the mutation.
    """
    dirty = []
    for path in sorted(set(paths)):
        if _git("status", "--porcelain", "--", path).strip():
            dirty.append(path)
    if dirty:
        print("REFUSING TO RUN: these targets have uncommitted changes, so a")
        print("git restore would discard real work rather than a mutation:")
        for path in dirty:
            print("  %s" % path)
        sys.exit(2)


def main():
    _require_clean(case[0] for case in CASES)

    missed = []
    for path, find, replace, test, label in CASES:
        original = io.open(path, encoding="utf-8").read()
        if find not in original:
            print("%-56s ANCHOR MISSING" % label)
            missed.append(label)
            continue
        try:
            io.open(path, "w", encoding="utf-8", newline="\n").write(
                original.replace(find, replace, 1))
            # Anything that raises between here and the finally leaves a
            # mutated file behind, which is why the timeout above matters
            # as much as the restore below.
            # A case may name a fully qualified node ("path::test") when
            # its test lives outside the XAML suite; otherwise T applies.
            node = test if "::" in test else T + test
            # ``subprocess.run``, not ``call``, and NOT a bare PIPE.
            #
            # This used to be ``call(..., stdout=PIPE, stderr=STDOUT)``,
            # which hands the child a pipe that nobody ever reads. As long
            # as every failure message was small it worked. Then a guard
            # arrived whose failing assertion printed a 500-line module
            # source as an operand, the child filled the OS pipe buffer,
            # blocked on write, and the parent waited for it forever --
            # with a mutated file sitting in the working tree, because the
            # restore is in the ``finally`` that never ran.
            #
            # ``run`` drains the pipes, and the timeout turns any future
            # hang into a reported failure instead of a stopped tool.
            finished = subprocess.run(
                ["python", "-m", "pytest", node, "-q"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=300,
            )
            rc = finished.returncode
            child_output = finished.stdout.decode("utf-8", "replace")
        finally:
            _git("checkout", "--", path)
            restored = io.open(path, encoding="utf-8").read()
            if restored != original:
                print("RESTORE FAILED for %s -- fix with:" % path)
                print('  git checkout -- "%s"' % path)
                sys.exit(3)
        if rc == 0:
            missed.append(label)
            # A bare MISSED says a guard did not fire and nothing about
            # WHY. That cost a whole afternoon once: a case passed in CI
            # and failed locally on identical content, and the child's
            # own output -- which this tool was throwing away -- was the
            # only thing that could have told the difference. It is
            # printed for a miss, and only for a miss.
            print("%-56s *** MISSED ***" % label)
            print("    the mutated file still passed its test. The child "
                  "said:")
            for line in child_output.strip().splitlines()[-12:]:
                print("      %s" % line)
            print("    mutation applied was:")
            for line in replace.splitlines()[:4]:
                print("      %s" % line)
        else:
            print("%-56s caught" % label)

    print("")
    print("guards proven: %d of %d" % (len(CASES) - len(missed), len(CASES)))
    if missed:
        print("NOT PROVEN: %s" % missed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
