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
TPL = "tests/test_column_plan.py::"
# ---- #118: the tie placer -------------------------------------
COL_PLACE_TIES = "RFT.lib/rft/revit/column_place_ties.py"
TPT = "tests/test_column_place_ties.py::"
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

    (COL_PLACE_TIES, '    if tie.kind != KIND_CLOSED_LOOP:\n        return\n',
     '',
     TPT + "test_a_cross_tie_is_never_gated_by_A1_its_geometry_is_not_a_loop",
     "A1 -- a legitimate cross-tie (narrow < minimum BY DESIGN) wrongly "
     "refused once the CLOSED_LOOP-only guard is removed"),

    (COL_PLACE_TIES, '    if tie.narrow_mm < tie.min_buildable_mm:',
     '    if False:',
     TPT + "test_a_subthreshold_loop_is_refused_before_any_element_is_created",
     "A1 -- the narrow-vs-minimum comparison itself disabled"),

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

    # ---- R20: a cross-tie is a leg -------------------------------
    (COL_TIES, '                if half <= other_half:',
     '                if False:',
     TT + "test_a_cross_tie_COUNTS_as_a_branch_for_the_300_mm_rule",
     "cross-ties ignored again -- only nested loops can satisfy 300 mm"),

    (COL_TIES, '                other_half = tie.half_v_mm if axis == 0 else tie.half_u_mm',
     '                other_half = half',
     TT + "test_a_cross_tie_is_a_leg_only_on_the_axis_it_SPANS",
     "a cross-tie counted on BOTH axes -- a branch no steel provides"),

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

    (COL_REPORT, '        outstanding_section(),',
     '',
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
            rc = subprocess.run(
                ["python", "-m", "pytest", node, "-q"],
                stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                timeout=300,
            ).returncode
        finally:
            _git("checkout", "--", path)
            restored = io.open(path, encoding="utf-8").read()
            if restored != original:
                print("RESTORE FAILED for %s -- fix with:" % path)
                print('  git checkout -- "%s"' % path)
                sys.exit(3)
        if rc == 0:
            missed.append(label)
        print("%-56s %s" % (label, "caught" if rc else "*** MISSED ***"))

    print("")
    print("guards proven: %d of %d" % (len(CASES) - len(missed), len(CASES)))
    if missed:
        print("NOT PROVEN: %s" % missed)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
