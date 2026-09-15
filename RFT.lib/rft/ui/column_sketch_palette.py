# -*- coding: utf-8 -*-
"""The column sketch's style-key -> brush-name mapping (issue #90).

PURE DATA. A dict of strings, in its own module so the mapping is checked
two ways under plain CPython:

1. every key ``rft.ui.column_sketch`` can emit has an entry here, so a new
   style key added to the drawing without a brush cannot reach a live host
   silently -- it would draw in WPF's default black-on-white, which
   nothing here can execute to notice;
2. every brush name here is declared with an ``x:Key`` in
   ``RFT.lib/SharedStyles.xaml``, which is how a typo'd resource name is
   caught before it becomes "Cannot find resource" at paint time.

Separate from ``rft.ui.sketch_palette`` on purpose. That module's dict is
guarded BOTH ways against the beam's ``rft.ui.sketch.STYLE_KEYS``, so a
column key added to it would fail the beam's own "no stale mapping" test
-- and mixing two elements' style vocabularies in one table is what the
workspace rules forbid. The BRUSHES are shared (#86); the mappings are
per-element, exactly as the roles are.

The renderer looks a style key up here and then resolves the brush NAME
through the window's resources. It never holds a WPF object, which is what
makes this file testable at all.
"""

#: style key (from rft.ui.column_sketch.STYLE_KEYS) -> XAML x:Key brush.
STYLE_BRUSH_KEYS = {
    "concrete": "InkPrimary",
    "cover": "InkMuted",
    "tie_outer": "SkyBlueDeep",
    # Reserved for #89. Mapped now so that ticket adds geometry and not a
    # palette hunt -- and so the guard proves the brushes exist before
    # anything depends on them.
    "tie_inner": "SkyBlue",
    "cross_tie": "WarningAmber",
    "bar_main": "InkPrimary",
    # Corner bars are drawn in the muted ink, not the primary: R15 says
    # they WILL move, and giving them the same weight as a bar that stays
    # put would overstate what the sketch knows.
    "bar_corner": "InkMuted",
    "dimension": "InkMuted",
    "dimension_pass": "PassGreen",
    "dimension_fail": "DangerRed",
    "zone_dense": "SkyBlueHover",
    "zone_normal": "SurfaceTint",
    "caption": "InkMuted",
}


def brush_key_for_style(style_key):
    """The brush name for one style key.

    Raises ``KeyError`` naming the style key itself -- never falls back to
    a default brush, because a default is how an unmapped key becomes a
    shape that draws in the wrong colour and is never noticed.
    """
    try:
        return STYLE_BRUSH_KEYS[style_key]
    except KeyError:
        raise KeyError(
            "no brush mapped for column sketch style key %r -- add it to "
            "rft.ui.column_sketch_palette.STYLE_BRUSH_KEYS, and make sure "
            "the brush exists in RFT.lib/SharedStyles.xaml" % (style_key,))
