# -*- coding: utf-8 -*-
"""#90 -- the column sketch, and the brushes it resolves.

Two directions, both load-bearing: every style the sketch can emit must be
mapped (or the renderer draws it in WPF's invisible default), and every
brush the mapping names must exist in the shared palette (or the renderer
throws "Cannot find resource" at paint time on a live host).
"""

import io

import pytest

from rft.core.column_layout import Bar, perimeter_bar_positions, tier_summary
from rft.core.column_spacing import FIRST_TIE_OFFSET_MM, MODE_AUTO, spacing_plan
from rft.core.column_ties import TieSubset, resolve_ties
from rft.core.column_tie_levels import tie_levels
from rft.ui.column_sketch import (
    MEASURED_CORNER_SNAP_MM,
    STYLE_KEYS,
    all_style_keys_used,
    bar_at_point,
    cross_section_captions,
    cross_section_shapes,
    format_tie_selection,
    selected_bar_shapes,
    toggle_bar_selection,
    zone_strip_shapes,
)
from rft.ui.column_sketch_palette import STYLE_BRUSH_KEYS, brush_key_for_style
from rft.ui.sketch_shapes import SketchCircle, SketchLine, SketchPolygon, SketchText
from xaml_keys import SHARED_STYLES_PATH, declared_keys_in

B, H, COVER, TIE, BAR, HC = 450.0, 600.0, 40.0, 9.5, 15.9, 2700.0


def layout(count_b=3, count_h=4):
    return perimeter_bar_positions(B, H, COVER, TIE, BAR, count_b, count_h)


#: One of the many valid coverings of the live layout.
VALID_SUBSETS = [TieSubset((0, 1, 2, 3)), TieSubset((0, 1, 2, 3, 4)),
                 TieSubset((1, 2, 3, 4, 5))]

BEND = 40.0   # 10M StirrupTieBendDiameter, measured live


def _ties(subsets, lay=None):
    return resolve_ties(subsets, lay or layout(), TIE, BAR, BEND)


def section(count_b=3, count_h=4, ties=()):
    lay = layout(count_b, count_h)
    return cross_section_shapes(B, H, COVER, TIE, BAR, lay, ties)


def strip():
    plan = spacing_plan(MODE_AUTO, HC, 450.0, 600.0, BAR, TIE)
    ladder = tie_levels(HC, plan.l0_mm, plan.confinement_spacing_mm,
                        plan.middle_zone_spacing_mm, FIRST_TIE_OFFSET_MM)
    return zone_strip_shapes(HC, plan.l0_mm, ladder), ladder


# --------------------------------------------------------------------- #
# The two guards #86 and #90 both depend on


def test_every_style_the_sketch_EMITS_is_declared():
    emitted = all_style_keys_used(section()) | all_style_keys_used(strip()[0])
    assert not emitted - STYLE_KEYS, sorted(emitted - STYLE_KEYS)


def test_every_declared_style_has_a_brush():
    """A key declared without a mapping draws in WPF's default -- black on
    white, on a live host, which nothing here can execute to notice.
    """
    missing = sorted(STYLE_KEYS - set(STYLE_BRUSH_KEYS))
    assert not missing, missing


def test_no_stale_brush_mapping():
    stale = sorted(set(STYLE_BRUSH_KEYS) - STYLE_KEYS)
    assert not stale, stale


def test_every_mapped_brush_exists_in_the_SHARED_palette():
    """#86's dictionary is the one both windows merge, so this is also the
    check that the column sketch cannot invent a colour of its own.
    """
    declared = declared_keys_in(io.open(SHARED_STYLES_PATH,
                                        encoding="utf-8").read())
    missing = sorted(set(STYLE_BRUSH_KEYS.values()) - declared)
    assert not missing, (
        "these brushes are named by the column sketch but not declared in "
        "RFT.lib/SharedStyles.xaml: %s" % missing)


def test_an_unmapped_style_raises_and_never_falls_back():
    """A default brush is how an unmapped key becomes a shape drawn in the
    wrong colour that nobody ever notices.
    """
    with pytest.raises(KeyError) as excinfo:
        brush_key_for_style("not_a_real_style")
    assert "not_a_real_style" in str(excinfo.value)


def test_the_column_palette_is_separate_from_the_beams():
    """Adding a column key to rft.ui.sketch_palette would fail the beam's
    own "no stale mapping" test, which is guarded against the BEAM's
    STYLE_KEYS -- and mixing two elements' vocabularies is what the
    workspace rules forbid. The brushes are shared; the mappings are not.
    """
    from rft.ui import sketch_palette
    assert "tie_outer" not in sketch_palette.STYLE_BRUSH_KEYS
    assert "stirrup" not in STYLE_BRUSH_KEYS


# --------------------------------------------------------------------- #
# What the cross-section draws


def test_the_section_draws_concrete_cover_and_the_tie():
    styles = all_style_keys_used(section())
    for required in ("concrete", "cover", "tie_outer"):
        assert required in styles


def test_every_bar_is_drawn_once():
    circles = [s for s in section() if isinstance(s, SketchCircle)]
    assert len(circles) == 10
    assert len(set((round(c.u, 6), round(c.v, 6)) for c in circles)) == 10


def test_corner_bars_are_drawn_in_their_OWN_style():
    """R15 says they will move. Giving them the same weight as a bar that
    stays put would overstate what the sketch knows.
    """
    circles = [s for s in section() if isinstance(s, SketchCircle)]
    corners = [c for c in circles if c.style == "bar_corner"]
    assert len(corners) == 4


def test_the_cover_band_uses_the_ELEMENTS_cover():
    """A2: cover is read from the element, so the band is the element's
    value and not a number anyone typed.
    """
    shapes = cross_section_shapes(B, H, 60.0, TIE, BAR,
                                  perimeter_bar_positions(B, H, 60.0, TIE,
                                                          BAR, 3, 4))
    cover_rect = [s for s in shapes
                  if isinstance(s, SketchPolygon) and s.style == "cover"][0]
    assert max(u for u, _v in cover_rect.points) == pytest.approx(B / 2.0 - 60.0)


def test_a_section_6_1_violation_is_drawn_in_the_FAIL_style():
    """#90's acceptance: a tier violation is visibly red before Place is
    available.
    """
    passing = all_style_keys_used(section(count_b=3, count_h=4))
    failing = all_style_keys_used(section(count_b=2, count_h=2))
    assert "dimension_fail" not in passing
    assert "dimension_fail" in failing
    assert STYLE_BRUSH_KEYS["dimension_fail"] == "DangerRed"


def test_a_clear_distance_is_labelled_ON_the_gap_it_measures():
    """Not in a legend. A violation belongs where the eye already is."""
    texts = [s for s in section(count_b=2, count_h=2)
             if isinstance(s, SketchText) and s.style == "dimension_fail"]
    assert texts, "no failing clear distance was labelled"
    lines = [s for s in section(count_b=2, count_h=2)
             if isinstance(s, SketchLine) and s.style == "dimension_fail"]
    assert len(lines) == len(texts)


def test_the_sketch_applies_NO_correction_it_cannot_justify():
    """#80 measured -167.55 asked for and -164.02 landed, and explicitly
    did NOT derive the closed form: "the tool must read the value back
    rather than predict it". So the drawn coordinate is the computed one,
    and the caption carries the warning.
    """
    circles = [s for s in section() if s.style == "bar_corner"]
    assert any(abs(c.u) == pytest.approx(167.55, abs=0.01) for c in circles)
    assert not any(abs(c.u) == pytest.approx(164.02, abs=0.01) for c in circles)


def test_the_captions_still_state_what_the_POSITIONS_cannot_claim():
    """R15 has not gone away. #89 removed the OTHER caption -- the one
    saying inner ties could not be drawn -- because they can be now; this
    one stays until as-built read-back exists.
    """
    captions = cross_section_captions(layout(), tier_summary(layout()))
    joined = "\n".join(captions)
    assert "%.1f mm inboard" % MEASURED_CORNER_SNAP_MM in joined
    assert "read back after placement" in joined


def test_with_no_ties_stated_the_caption_says_so():
    """Silence would read as "the ties are handled". The perimeter tie
    alone IS what the column has, and section 6.1's verdict says whether
    that is enough.
    """
    joined = "\n".join(cross_section_captions(layout(), tier_summary(layout())))
    assert "No inner ties stated" in joined


def test_the_caption_names_the_bars_no_tie_HOLDS():
    resolved = _ties(VALID_SUBSETS)
    joined = "\n".join(
        cross_section_captions(layout(), tier_summary(layout()), resolved))
    assert "nothing here derives a topology" in joined
    assert "marked: none" in joined

    bare = _ties([])
    joined = "\n".join(
        cross_section_captions(layout(), tier_summary(layout()), bare))
    assert "marked: 1, 3, 4, 6, 8, 9" in joined


def test_the_tier_sentence_is_on_the_sketch():
    captions = cross_section_captions(layout(), tier_summary(layout()))
    assert "EVERY bar must be restrained" in captions[0]


# --------------------------------------------------------------------- #
# The zone strip


def test_the_strip_draws_both_confinement_zones_and_the_middle():
    shapes, _ladder = strip()
    zones = [s for s in shapes if s.style in ("zone_dense", "zone_normal")]
    assert len([s for s in zones if s.style == "zone_dense"]) == 2
    assert len([s for s in zones if s.style == "zone_normal"]) == 1


def test_the_strip_ticks_every_tie_level():
    shapes, ladder = strip()
    ticks = [s for s in shapes
             if isinstance(s, SketchLine) and s.style == "tie_outer"]
    assert len(ticks) == len(ladder.levels) == 16


def test_the_strip_labels_the_first_tie_offset_and_L0():
    shapes, _ladder = strip()
    labels = " ".join(s.text for s in shapes if isinstance(s, SketchText))
    assert "first tie 50" in labels
    assert "L0 600" in labels
    assert "middle @" in labels


def test_the_strip_uses_its_own_frame_not_the_sections():
    """`v` is height above the base face, so it runs 0..Hc rather than
    +/-h/2. Overlaying the two frames would misrepresent both.
    """
    shapes, _ladder = strip()
    vs = [v for s in shapes if isinstance(s, SketchPolygon)
          for _u, v in s.points]
    assert min(vs) == 0.0
    assert max(vs) == pytest.approx(HC)


def test_the_sketch_imports_no_arithmetic_of_its_own():
    """A48, applied to a second element: the renderer walks a list and maps
    a style to a brush. Everything else arrives decided, which is what
    makes the sketch, the report and the placer agree by construction.
    """
    import ast

    import rft.ui.column_sketch as module
    path = module.__file__
    if path.endswith(("c", "o")):
        path = path[:-1]
    imported = set()
    for node in ast.walk(ast.parse(io.open(path, encoding="utf-8").read())):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imported |= set(alias.name for alias in node.names)
    # KIND_CROSS_TIE is a constant and restrained_bar_indices is a set
    # union over already-decided data. Neither computes a POSITION, which
    # is what this guard is about -- and both arrive from the module that
    # already made the decision.
    assert imported == {
        "TIER_ALTERNATE", "TIER_EVERY_BAR", "TIER_EXCEEDED", "ZONE_MIDDLE",
        "KIND_CROSS_TIE", "restrained_bar_indices",
        "SketchCircle", "SketchLine", "SketchPolygon", "SketchText",
    }, sorted(imported)


# --------------------------------------------------------------------- #
# #89 -- the ties the engineer stated


def test_every_stated_tie_is_drawn():
    """Three inner ties plus the implied perimeter."""
    shapes = section(ties=_ties(VALID_SUBSETS))
    loops = [s for s in shapes if s.style in ("tie_outer", "tie_inner")]
    assert len(loops) == 4
    assert len([s for s in loops if s.style == "tie_outer"]) == 1


def test_a_cross_tie_is_a_LEG_not_a_thin_rectangle():
    """A1 makes it a cross-tie because the rectangle cannot be bent, so
    drawing one would picture exactly the geometry Revit refuses with a
    modal dialog.
    """
    shapes = section(ties=resolve_ties([], layout(), TIE, BAR, 900.0))
    cross = [s for s in shapes if s.style == "cross_tie"]
    assert len(cross) == 1
    assert isinstance(cross[0], SketchLine)
    assert not [s for s in shapes if isinstance(s, SketchPolygon)
                and s.style == "cross_tie"]


def test_unrestrained_bars_are_MARKED():
    """Section 6.1 is about these bars. Leaving the reader to work them
    out from the tie rectangles is how a violation gets missed on the one
    drawing meant to reveal it.
    """
    bare = [s for s in section(ties=_ties([]))
            if s.style == "bar_unrestrained"]
    assert len(bare) == 6, "the perimeter tie holds only its four corners"
    covered = [s for s in section(ties=_ties(VALID_SUBSETS))
               if s.style == "bar_unrestrained"]
    assert covered == []


def test_an_unrestrained_bar_is_drawn_in_the_REFUSAL_colour():
    assert STYLE_BRUSH_KEYS["bar_unrestrained"] == "DangerRed"


def test_the_sketch_derives_no_topology_of_its_own():
    """R4 and R17: the user states it. With no subsets the sketch shows
    the perimeter tie alone -- it does not invent inner ties to make the
    picture look complete.
    """
    shapes = section(ties=())
    assert not [s for s in shapes if s.style in ("tie_inner", "cross_tie")]
    assert len([s for s in shapes if s.style == "tie_outer"]) == 1


# --------------------------------------------------------------------- #
# #137 -- sketch the tie by clicking its bars

_BARS = (
    Bar(index=0, u_mm=-100.0, v_mm=0.0, is_corner=True),
    Bar(index=1, u_mm=0.0, v_mm=0.0, is_corner=False),
    Bar(index=2, u_mm=100.0, v_mm=0.0, is_corner=True),
)


def test_bar_at_point_hits_the_bar_within_its_radius():
    assert bar_at_point(_BARS, 2.0, 3.0, pick_radius_mm=10.0) == 1


def test_bar_at_point_misses_outside_the_radius():
    assert bar_at_point(_BARS, 50.0, 0.0, pick_radius_mm=10.0) is None


def test_bar_at_point_chooses_the_NEARER_of_two():
    """A point between two bars, both within the radius, resolves to
    whichever centre is actually closer -- not the first in the list.
    """
    # 6 mm from bar 1 (index 1, at u=0), 94 mm from bar 2 (index 2, u=100).
    assert bar_at_point(_BARS, 6.0, 0.0, pick_radius_mm=95.0) == 1
    # Now closer to bar 2 than bar 1.
    assert bar_at_point(_BARS, 94.0, 0.0, pick_radius_mm=95.0) == 2


def test_bar_at_point_returns_none_with_no_bars():
    assert bar_at_point((), 0.0, 0.0, pick_radius_mm=100.0) is None


def test_toggle_bar_selection_adds_an_unselected_bar():
    assert toggle_bar_selection([], 1) == [1]
    assert toggle_bar_selection([1], 6) == [1, 6]


def test_toggle_bar_selection_removes_a_selected_bar():
    """A second click on the same bar deselects it -- acceptance 2."""
    assert toggle_bar_selection([1, 6], 1) == [6]
    assert toggle_bar_selection([1, 6], 6) == [1]


def test_toggle_bar_selection_keeps_CLICK_ORDER_not_sorted():
    """R19: a two-bar tie is FROM the first click TO the second. Sorting
    would silently rewrite what the tie means.
    """
    assert toggle_bar_selection([6], 1) == [6, 1]


def test_toggle_bar_selection_never_mutates_its_argument():
    original = [1, 6]
    toggle_bar_selection(original, 9)
    assert original == [1, 6]


def test_format_tie_selection_is_space_joined_in_order():
    assert format_tie_selection([1, 6]) == "1 6"
    assert format_tie_selection([0, 1, 2, 3]) == "0 1 2 3"
    assert format_tie_selection([]) == ""


def test_selected_bar_shapes_draws_only_the_selected_bars():
    lay = layout()
    shapes = selected_bar_shapes(lay, [1, 6], radius_mm=8.0)
    assert len(shapes) == 2
    assert all(s.style == "bar_selected" for s in shapes)
    positions = set((round(s.u, 2), round(s.v, 2)) for s in shapes)
    expected = set((round(b.u_mm, 2), round(b.v_mm, 2))
                  for b in lay.bars if b.index in (1, 6))
    assert positions == expected


def test_selected_bar_shapes_with_no_selection_draws_nothing():
    assert selected_bar_shapes(layout(), [], radius_mm=8.0) == []


def test_bar_selected_is_a_declared_style_with_its_own_brush():
    assert "bar_selected" in STYLE_KEYS
    from rft.ui.column_sketch_palette import STYLE_BRUSH_KEYS
    assert STYLE_BRUSH_KEYS["bar_selected"] not in (
        STYLE_BRUSH_KEYS["bar_main"], STYLE_BRUSH_KEYS["bar_unrestrained"])
