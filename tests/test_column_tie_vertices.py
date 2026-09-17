# -*- coding: utf-8 -*-
"""#140 -- ``ResolvedTie.vertices`` is the ONE centreline polygon a closed
loop or a cross-tie carries, read by all three consumers instead of each
re-deriving corners from ``centre_u_mm``/``centre_v_mm``/``half_u_mm``/
``half_v_mm``.

This ticket changes NO geometry. Every test below proves that against the
derivation the three consumers used BEFORE ``vertices`` existed:

- ``rft.core.column_ties.resolve_tie``'s own ``corner_uv`` scan (closed
  loop corners, restrained-bar test);
- ``rft.revit.column_place_ties._cross_tie_uv_segments_mm``'s bar-to-bar
  endpoints (cross-tie);
- ``rft.ui.column_sketch``'s drawn shapes, which must now draw exactly
  ``tie.vertices``.

Nothing here hand-writes a coordinate: every expectation is derived from
the same fixtures ``tests/test_column_ties.py`` and
``tests/test_column_place_ties.py`` already use.
"""

import rft.revit.column_place_ties as place_ties_module
from rft.core.column_layout import perimeter_bar_positions
from rft.core.column_ties import (
    KIND_CLOSED_LOOP,
    KIND_CROSS_TIE,
    TieSubset,
    outer_perimeter_subset,
    resolve_tie,
)
from rft.ui.column_sketch import cross_section_shapes
from rft.ui.sketch_shapes import SketchLine, SketchPolygon

B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM = 450.0, 600.0, 40.0, 9.5, 15.9
BEND_DIAMETER_MM = 40.0  # 10M StirrupTieBendDiameter, measured live


def _layout(count_b=3, count_h=4):
    return perimeter_bar_positions(
        B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM, count_b, count_h)


def _independent_closed_loop_corners(tie, layout):
    """`rft.ui.column_sketch`'s and `rft.revit.column_place_ties`'s OWN
    pre-#140 corner derivation -- `centre`/`half` alone, no `grow`
    adjustment -- rebuilt here rather than imported, so this test does not
    simply compare a value against itself.

    NOT `resolve_tie`'s internal `corner_uv`/`corner_bar_uv`: that variable
    is deliberately grow-adjusted INBOARD to land on a bar's own position
    for the restrained-bar test, and is a different question from where
    the tie's steel centreline actually runs.
    """
    cu, cv, hu, hv = (tie.centre_u_mm, tie.centre_v_mm,
                     tie.half_u_mm, tie.half_v_mm)
    return [(cu - hu, cv - hv), (cu + hu, cv - hv),
            (cu + hu, cv + hv), (cu - hu, cv + hv)]


def _independent_cross_tie_endpoints(tie, layout):
    """The pre-#140 placer derivation
    (`_cross_tie_uv_segments_mm`), rebuilt independently: the enclosed
    subset's first and last bar, read straight off the layout.
    """
    start_bar = layout.bars[tie.enclosed_indices[0]]
    end_bar = layout.bars[tie.enclosed_indices[-1]]
    return [(start_bar.u_mm, start_bar.v_mm), (end_bar.u_mm, end_bar.v_mm)]


def _same_cycle(actual, expected):
    """The same closed polygon, wound the same way, allowed to START
    anywhere.

    #140's claim is that a loop's vertices ARE its four corners. R31 then
    ruled where the hook closure sits, which is ``vertices[0]`` -- so the
    starting point is now a separate decision with its own tests, and
    pinning it here as well would make these two tests fail for a reason
    they are not about.

    Rotation only, never reversal: the winding is load-bearing (R21's
    hook orientation reads it) and is still compared exactly.
    """
    if len(actual) != len(expected):
        return False
    return any(list(actual) == [expected[(start + i) % len(expected)]
                                for i in range(len(expected))]
               for start in range(len(expected)))


# --------------------------------------------------------------------- #
# A closed loop's vertices are the four corners resolve_tie always found.


def test_a_closed_loops_vertices_are_the_four_corners_resolve_tie_finds():
    layout = _layout()
    tie = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                      TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    assert tie.kind == KIND_CLOSED_LOOP
    assert _same_cycle(tie.vertices,
                       _independent_closed_loop_corners(tie, layout))
    assert len(tie.vertices) == 4


def test_an_inner_closed_loops_vertices_match_too():
    """Not just the outer perimeter -- any closed loop the engineer states."""
    layout = _layout()
    tie = resolve_tie(TieSubset((0, 1, 2, 3)), layout, TIE_DIA_MM, BAR_DIA_MM,
                      BEND_DIAMETER_MM)
    assert tie.kind == KIND_CLOSED_LOOP
    assert _same_cycle(tie.vertices,
                       _independent_closed_loop_corners(tie, layout))


# --------------------------------------------------------------------- #
# A cross-tie's vertices are its two named ends, read off the layout --
# exactly what the placer's own segment builder has always used.


def test_a_cross_ties_vertices_are_its_two_ends_from_the_layout():
    layout = _layout()
    tie = resolve_tie(TieSubset((1, 6)), layout, TIE_DIA_MM, BAR_DIA_MM,
                      BEND_DIAMETER_MM)
    assert tie.kind == KIND_CROSS_TIE
    assert tie.vertices == _independent_cross_tie_endpoints(tie, layout)
    assert len(tie.vertices) == 2


def test_a_cross_ties_vertices_match_the_placers_own_segment_builder():
    """Driven from the placer's real function, not a re-implementation of
    it -- `_cross_tie_uv_segments_mm` is #140's cited source of truth for
    a cross-tie's two points.
    """
    layout = _layout()
    tie = resolve_tie(TieSubset((1, 6)), layout, TIE_DIA_MM, BAR_DIA_MM,
                      BEND_DIAMETER_MM)
    segments = place_ties_module._cross_tie_uv_segments_mm(tie, layout)
    assert len(segments) == 1
    assert (tie.vertices[0], tie.vertices[-1]) == segments[0]


def test_a_forced_cross_tie_outer_perimeter_still_matches_the_layout():
    """The outer tie itself can be forced into KIND_CROSS_TIE (an
    unbuildable narrow dimension) -- exercised because #89's own suite
    covers exactly this case (`test_the_report_states_the_bend_test_for_a
    _cross_tie`), and it multi-bar-encloses rather than being a plain
    2-bar subset.
    """
    layout = _layout()
    tie = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                      TIE_DIA_MM, BAR_DIA_MM, bend_diameter_mm=900.0)
    assert tie.kind == KIND_CROSS_TIE
    assert tie.vertices == _independent_cross_tie_endpoints(tie, layout)


# --------------------------------------------------------------------- #
# The placer's curve builder reads vertices, not centre/half.


def test_the_closed_loop_curve_builder_reads_vertices_not_centre_half():
    layout = _layout()
    tie = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                      TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    segments = place_ties_module._closed_loop_uv_segments_mm(tie)
    corners = tie.vertices
    n = len(corners)
    assert segments == [(corners[i], corners[(i + 1) % n])
                        for i in range(n)]


def test_the_dispatcher_still_tells_loop_from_cross_tie_by_kind():
    layout = _layout()
    loop = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                       TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    cross = resolve_tie(TieSubset((1, 6)), layout, TIE_DIA_MM, BAR_DIA_MM,
                        BEND_DIAMETER_MM)
    assert (place_ties_module._uv_segments_mm(loop, layout)
            == place_ties_module._closed_loop_uv_segments_mm(loop))
    assert (place_ties_module._uv_segments_mm(cross, layout)
            == place_ties_module._cross_tie_uv_segments_mm(cross, layout))


# --------------------------------------------------------------------- #
# The sketch draws exactly tie.vertices.


def test_the_sketch_draws_the_closed_loops_vertices_directly():
    layout = _layout()
    tie = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                      TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    shapes = cross_section_shapes(B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM,
                                  layout, [tie])
    loops = [s for s in shapes if isinstance(s, SketchPolygon)
            and s.style == "tie_outer"]
    assert len(loops) == 1
    assert loops[0].points == list(tie.vertices)


def test_the_sketch_draws_the_cross_ties_vertices_directly():
    layout = _layout()
    tie = resolve_tie(TieSubset((1, 6)), layout, TIE_DIA_MM, BAR_DIA_MM,
                      BEND_DIAMETER_MM)
    outer = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                        TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    shapes = cross_section_shapes(B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM,
                                  layout, [outer, tie])
    lines = [s for s in shapes if isinstance(s, SketchLine)
            and s.style == "cross_tie"]
    assert len(lines) == 1
    line = lines[0]
    assert (line.u1, line.v1) == tie.vertices[0]
    assert (line.u2, line.v2) == tie.vertices[-1]


# --------------------------------------------------------------------- #
# A mutation that reorders or drops a vertex must fail (issue #140's own
# guard requirement) -- proven directly here, since these consumers are
# ordinary importable Python and do not need tools/prove_guards.py's
# text-mutation machinery.


def test_a_reordered_closed_loop_vertex_list_changes_the_drawn_polygon():
    layout = _layout()
    tie = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                      TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    reordered = tie._replace(
        vertices=[tie.vertices[1], tie.vertices[0],
                 tie.vertices[2], tie.vertices[3]])
    shapes = cross_section_shapes(B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM,
                                  layout, [reordered])
    loop = [s for s in shapes if isinstance(s, SketchPolygon)
           and s.style == "tie_outer"][0]
    assert loop.points != list(tie.vertices)
    assert loop.points == list(reordered.vertices)

    segments = place_ties_module._closed_loop_uv_segments_mm(tie)
    reordered_segments = place_ties_module._closed_loop_uv_segments_mm(
        reordered)
    assert segments != reordered_segments


def test_a_dropped_closed_loop_vertex_is_visible_in_both_consumers():
    layout = _layout()
    tie = resolve_tie(outer_perimeter_subset(len(layout.bars)), layout,
                      TIE_DIA_MM, BAR_DIA_MM, BEND_DIAMETER_MM)
    dropped = tie._replace(vertices=list(tie.vertices)[:3])

    shapes = cross_section_shapes(B_MM, H_MM, COVER_MM, TIE_DIA_MM, BAR_DIA_MM,
                                  layout, [dropped])
    loop = [s for s in shapes if isinstance(s, SketchPolygon)
           and s.style == "tie_outer"][0]
    assert len(loop.points) == 3

    segments = place_ties_module._closed_loop_uv_segments_mm(dropped)
    assert len(segments) == 3


def test_a_swapped_cross_tie_endpoint_changes_the_placed_segment():
    layout = _layout()
    tie = resolve_tie(TieSubset((1, 6)), layout, TIE_DIA_MM, BAR_DIA_MM,
                      BEND_DIAMETER_MM)
    swapped = tie._replace(vertices=[tie.vertices[1], tie.vertices[0]])

    segments = place_ties_module._cross_tie_uv_segments_mm(tie, layout)
    swapped_segments = place_ties_module._cross_tie_uv_segments_mm(
        swapped, layout)
    assert segments != swapped_segments
    assert segments[0] == (swapped_segments[0][1], swapped_segments[0][0])
