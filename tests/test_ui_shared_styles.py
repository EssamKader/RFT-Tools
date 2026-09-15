# -*- coding: utf-8 -*-
"""#86 -- the substitution that points a window XAML at the shared palette.

Everything here runs under plain CPython because the module is pure text
and paths. What it cannot prove is the far side: that WPF then parses the
result and resolves the keys. #86 verified *that* live on Revit 2024 (a
loose ResourceDictionary loads from an absolute file:/// URI and
``TryFindResource`` returns the brush); these tests cover the string this
project actually hands it.
"""

import io
import os
import re

import pytest

from rft.ui.shared_styles import (
    PLACEHOLDER_SOURCE,
    SHARED_STYLES_FILENAME,
    file_uri,
    resolve_shared_styles,
    shared_styles_path,
    window_xaml,
)
from xaml_keys import BEAM_XAML_PATH, SHARED_STYLES_PATH, declared_keys_in

# The palette as #60 shipped it, transcribed from the beam window before
# the move. Hard-coded rather than read back from the file, because a test
# that reads the file it is checking proves only that the file equals
# itself -- and "the colours are unchanged" is the one claim #86's
# acceptance makes that nothing else here can make.
PALETTE_AS_SHIPPED = {
    "SurfaceWhite": "#FFFFFFFF",
    "SurfaceTint": "#FFF2F9FD",
    "SurfaceDisabled": "#FFEDF1F3",
    "SkyBlue": "#FF87CEEB",
    "SkyBlueHover": "#FFD6EEF9",
    "SkyBlueDeep": "#FF1F6F94",
    "BorderSubtle": "#FFC9DFEA",
    "InkPrimary": "#FF1B2A33",
    "InkMuted": "#FF5A6B75",
    "InkDisabled": "#FF8A9AA4",
    "WarningAmber": "#FFB05A00",
    "DangerRed": "#FFB00000",
    "PassGreen": "#FF2E7D32",
}


def _brushes_in(path):
    text = io.open(path, encoding="utf-8").read()
    return dict(re.findall(
        r'<SolidColorBrush\s+x:Key="([A-Za-z0-9_]+)"\s+Color="([^"]+)"', text))


def test_the_shared_palette_is_where_the_module_says_it_is():
    assert os.path.isfile(SHARED_STYLES_PATH), SHARED_STYLES_PATH
    assert os.path.basename(SHARED_STYLES_PATH) == SHARED_STYLES_FILENAME
    assert os.path.basename(os.path.dirname(SHARED_STYLES_PATH)) == "RFT.lib", (
        "the palette must sit in the .lib folder itself -- that directory, "
        "and not a subfolder of it, is what pyRevit puts on every UI "
        "extension's path (RFT.lib/README.md, rule 2)."
    )


def test_every_colour_survived_the_move_byte_for_byte():
    """#86's acceptance: "the beam window must look identical afterwards"."""
    assert _brushes_in(SHARED_STYLES_PATH) == PALETTE_AS_SHIPPED


def test_the_move_left_no_brush_behind():
    """A partial move is worse than none: the window would keep painting
    from its own copy for some brushes and the shared file for others, and
    the two would drift apart one colour at a time.
    """
    left_behind = sorted(_brushes_in(BEAM_XAML_PATH))
    assert not left_behind, (
        "these SolidColorBrush declarations are still in the beam window "
        "after #86 moved the palette out: %s" % left_behind
    )


def test_the_shared_palette_declares_nothing_but_brushes():
    """Styles stay with the window that uses them.

    ``SectionHeading`` and the ``TabItem`` template are beam-window
    decisions about beam-window controls; a column window that merged them
    would inherit a tab template it never asked for. What is genuinely
    shared is the *colour scheme* -- the thing #86's brief names.
    """
    keys = declared_keys_in(io.open(SHARED_STYLES_PATH, encoding="utf-8").read())
    brushes = set(_brushes_in(SHARED_STYLES_PATH))
    assert keys == brushes, (
        "RFT.lib/SharedStyles.xaml declares non-brush resources (%s). Keep "
        "it a palette: a Style belongs to the window whose controls it "
        "describes." % sorted(keys - brushes)
    )


def test_resolve_replaces_the_placeholder_with_an_absolute_uri():
    resolved = resolve_shared_styles(
        '<ResourceDictionary %s/>' % PLACEHOLDER_SOURCE)
    assert PLACEHOLDER_SOURCE not in resolved
    assert 'Source="file:///' in resolved


def test_the_uri_percent_encodes_spaces():
    """This repository's own path is full of them. An unencoded space is
    where a URI silently becomes a different URI.
    """
    uri = file_uri(os.path.join("C:" + os.sep, "BIM & POWER BI", "a.xaml"))
    assert " " not in uri
    assert "&" not in uri, "an unencoded & opens an entity reference in XAML"
    assert uri.startswith("file:///C:/")
    assert uri.endswith("/a.xaml")


def test_a_missing_placeholder_is_refused_loudly():
    """Otherwise the window loads with no palette and throws "Cannot find
    resource" forty frames deep, at button-press time, on a live host.
    """
    with pytest.raises(ValueError) as excinfo:
        resolve_shared_styles("<Window/>")
    assert PLACEHOLDER_SOURCE in str(excinfo.value)
    assert "found 0" in str(excinfo.value)


def test_a_duplicated_placeholder_is_refused_loudly():
    """Two merges of one dictionary: legal WPF, and never what was meant."""
    with pytest.raises(ValueError) as excinfo:
        resolve_shared_styles("%s %s" % (PLACEHOLDER_SOURCE, PLACEHOLDER_SOURCE))
    assert "found 2" in str(excinfo.value)


def test_a_missing_palette_file_is_refused_loudly():
    with pytest.raises(ValueError) as excinfo:
        resolve_shared_styles(
            '<ResourceDictionary %s/>' % PLACEHOLDER_SOURCE,
            shared_path=os.path.join(os.path.dirname(SHARED_STYLES_PATH),
                                     "NoSuchStyles.xaml"),
        )
    assert "NoSuchStyles.xaml" in str(excinfo.value)


def test_the_real_beam_window_resolves_and_still_parses_as_xml():
    """End to end on the file that ships: substitute, then parse. Catches
    a rewrite that produced a URI the attribute cannot hold -- an
    unescaped ``&`` from a folder name being the realistic one.
    """
    import xml.etree.ElementTree as ET

    resolved = window_xaml(BEAM_XAML_PATH)
    ET.fromstring(resolved.encode("utf-8"))
    assert 'Source="file:///' in resolved
    assert shared_styles_path().replace("\\", "/").split("/")[-1] in resolved
