# -*- coding: utf-8 -*-
"""#90 -- the column sketch, and the brushes it resolves.

Two directions, both load-bearing: every style the sketch can emit must be
mapped (or the renderer draws it in WPF's invisible default), and every
brush the mapping names must exist in the shared palette (or the renderer
throws "Cannot find resource" at paint time on a live host).
"""

import io

import pytest

from rft.core.column_layout import perimeter_bar_positions, tier_summary
from rft.core.column_spacing import FIRST_TIE_OFFSET_MM, MODE_AUTO, spacing_plan
from rft.core.column_tie_levels import tie_levels
from rft.ui.column_sketch import (
    MEASURED_CORNER_SNAP_MM,
    STYLE_KEYS,
    all_style_keys_used,
    cross_section_captions,
    cross_section_shapes,
    zone_strip_shapes,
)
from rft.ui.column_sketch_palette import STYLE_BRUSH_KEYS, brush_key_for_style
from rft.ui.sketch_shapes import SketchCircle, SketchLine, SketchPolygon, SketchText
from xaml_keys import SHARED_STYLES_PATH, declared_keys_in

B, H, COVER, TIE, BAR, HC = 450.0, 600.0, 40.0, 9.5, 15.9, 2700.0


def layout(count_b=3, count_h=4):
    return perimeter_bar_positions(B, H, COVER, TIE, BAR, count_b, count_h)


def section(count_b=3, count_h=4):
    return cross_section_shapes(B, H, COVER, TIE, BAR, layout(count_b, count_h))


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


def test_the_captions_state_both_things_the_sketch_cannot_claim():
    captions = cross_section_captions(layout(), tier_summary(layout()))
    joined = "\n".join(captions)
    assert "%.1f mm inboard" % MEASURED_CORNER_SNAP_MM in joined
    assert "read back after placement" in joined
    assert "Inner ties and cross-ties are NOT drawn" in joined
    assert "#89" in joined and "Q11" in joined


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
    assert imported == {
        "TIER_ALTERNATE", "TIER_EVERY_BAR", "TIER_EXCEEDED", "ZONE_MIDDLE",
        "SketchCircle", "SketchLine", "SketchPolygon", "SketchText",
    }, sorted(imported)
