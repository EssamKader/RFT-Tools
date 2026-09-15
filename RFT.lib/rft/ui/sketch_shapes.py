# -*- coding: utf-8 -*-
"""The shape vocabulary every RFT sketch speaks (issue #90).

Four namedtuples and nothing else. They carry no element knowledge at all
-- a line is a line whether it bounds a beam's elevation or a column's
cross-section -- so they are shared, in the same spirit as #86's palette:
one vocabulary, two renderers that already know how to draw it.

Extracted from ``rft.ui.sketch``, which re-exports them so the beam tool
is untouched. The beam's *functions* stay there and are not reused: the
column reuse audit marks ``sketch.py`` do-not-reuse for its sections,
faces, zones and hook details, and that verdict is about the drawing
logic, not about what a line is.

Coordinates are MILLIMETRES in the element's own section-local frame,
never pixels. Scaling to a canvas is the window's job, which is what keeps
these testable under plain CPython.
"""

from collections import namedtuple

SketchLine = namedtuple("SketchLine", ["u1", "v1", "u2", "v2", "style"])
SketchCircle = namedtuple("SketchCircle", ["u", "v", "r", "style"])
SketchText = namedtuple("SketchText", ["u", "v", "text", "style"])
#: ``points`` is a list of (u, v) pairs, implicitly closed (first and last
#: are joined) -- matching WPF ``Polygon``, which closes itself.
SketchPolygon = namedtuple("SketchPolygon", ["points", "style"])
