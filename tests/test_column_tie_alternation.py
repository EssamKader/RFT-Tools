# -*- coding: utf-8 -*-
"""#195 / R48 — section 6.3's alternation, BUILT rather than only reported.

Before this, `TieLevel.mirrored` was computed, printed as an `M` in the
report, and read by nobody who built anything. Every tie at every level
was placed identically, hook in the same corner all the way up the column
— which is the one thing §6.3 exists to prevent — while the report
asserted otherwise.

The transform is not invented here. #78 measured it on a live host: a
reflection whose mirror plane normal is `HandOrientation`, through the
**tie's own centre**, flipping `u` and leaving `v`. That moves the hook
corner SW → SE, which is the **adjacent** corner the owner ruled for on
2026-09-14 — a 180° rotation was rejected because it gives the diagonal.
"""

import pytest

from rft.core.column_ties import mirrored_vertices


RECTANGLE = ((-185.0, -260.0), (185.0, -260.0), (185.0, 260.0), (-185.0, 260.0))


def test_the_reflection_flips_u_and_leaves_v_alone():
    """#78's measured transform, exactly: SW (-185, -260) becomes
    SE (+185, -260) — the adjacent corner, not the diagonal one."""
    assert mirrored_vertices(RECTANGLE) == (
        (185.0, -260.0), (-185.0, -260.0), (-185.0, 260.0), (185.0, 260.0))


def test_the_polygon_OCCUPIES_THE_SAME_SPACE():
    """An alternated tie wraps the same bars. If the reflection moved the
    polygon it would be a different tie, not an alternated one."""
    assert set(mirrored_vertices(RECTANGLE)) == set(RECTANGLE)


def test_it_reflects_about_the_TIE_s_own_centre_not_the_COLUMN_s():
    """The load-bearing detail. A subset tie need not be centred on the
    column, and reflecting such a tie about ``u = 0`` would MOVE it —
    it would wrap different bars entirely.
    """
    off_centre = ((100.0, -50.0), (300.0, -50.0), (300.0, 50.0), (100.0, 50.0))
    mirrored = mirrored_vertices(off_centre)
    assert set(mirrored) == set(off_centre), (
        "the tie moved: it was reflected about the wrong centre")
    # About u = 0 it would have landed at -100 .. -300, on the far side.
    assert all(u > 0 for u, _v in mirrored)


def test_mirroring_TWICE_returns_the_original():
    """A reflection is its own inverse, so an even level and the level two
    above it carry the same hook corner — which is what alternation
    means."""
    assert mirrored_vertices(mirrored_vertices(RECTANGLE)) == RECTANGLE


def test_a_TRIANGLE_is_never_handed_to_this_at_all():
    """R32: a triangle's closure stays at the apex. The exception is
    enforced in `_uv_segments_mm`, which never passes `mirrored` on for a
    triangle — this asserts the maths would not silently do something
    plausible if that guard were removed."""
    triangle = ((-100.0, -100.0), (100.0, -100.0), (0.0, 100.0))
    assert mirrored_vertices(triangle) != triangle, (
        "reflecting a triangle DOES change it, which is why R32's "
        "exception has to be enforced by the caller rather than by luck")


def test_an_empty_polygon_is_returned_unchanged_rather_than_raising():
    assert mirrored_vertices(()) == tuple()


@pytest.mark.parametrize("vertices", [RECTANGLE, ((0.0, 0.0), (10.0, 0.0))])
def test_the_vertex_COUNT_never_changes(vertices):
    """A reflection reorders nothing and drops nothing: the polygon has
    the same corners, so the tie has the same number of legs."""
    assert len(mirrored_vertices(vertices)) == len(vertices)
