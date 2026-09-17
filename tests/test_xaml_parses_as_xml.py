# -*- coding: utf-8 -*-
"""Every .xaml in the repo is handed to an XML parser.

## Why this exists

`SharedStyles.xaml` shipped a brush whose comment used this project's house
em dash:

    <!-- #137: a bar the engineer has clicked, mid-tie. Its own colour --
         neither PassGreen ... nor SkyBlue ... -- so a pending selection
         is never mistaken for something this tool has already judged. -->

**XML 1.0 section 2.5 forbids `--` inside a comment body**, and forbids a
body ending in `-`. So that file was not XML, and `ResourceDictionary.Source`
threw the moment either window tried to merge it:

    An XML comment cannot contain '--', and '-' cannot be the last
    character. Line 60, position 72.

Both tools died at parse time -- the beam's as well as the column's,
because the palette is shared -- and **899 tests and 140 mutation-proven
guards all passed.** Every existing XAML guard is a regex over the text:
`declared_keys_in` scrapes `x:Key`, `merges_shared_styles` looks for a
placeholder, `tests/test_column_xaml.py` searches for element names. Not
one of them ever asked a parser whether the markup was well formed, so the
one defect class that stops the window opening at all was the one nothing
watched.

## What this can and cannot prove

It proves the markup is **well-formed XML**. It does not prove WPF accepts
it as XAML -- an unresolvable `StaticResource`, a bad type name or a
handler attribute on a templated control all parse fine here and still
throw on a live host. Those stay the subject of the existing guards and of
live verification.

That is the whole point: this is the cheap check nobody was making, not a
replacement for the expensive ones.
"""

import io
import os
import re
import xml.etree.ElementTree as ElementTree

import pytest

from xaml_keys import REPO_ROOT

#: A comment body, without its delimiters.
_COMMENT = re.compile(r"<!--(.*?)-->", re.DOTALL)


def _every_xaml_file():
    """Every .xaml in the repo, found by walking rather than by listing.

    Walked, not enumerated from ``xaml_keys.WINDOW_XAML_PATHS``: the file
    that broke both tools was ``SharedStyles.xaml``, which is not a window
    and is not in that tuple. A guard that checks only the files someone
    remembered to list is how this defect reached a live host in the first
    place.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(REPO_ROOT):
        dirnames[:] = [d for d in dirnames
                       if d not in (".git", "__pycache__")]
        for name in filenames:
            if name.endswith(".xaml"):
                found.append(os.path.join(dirpath, name))
    return sorted(found)


XAML_FILES = _every_xaml_file()


def _relative(path):
    return os.path.relpath(path, REPO_ROOT)


def test_the_walk_finds_the_files_we_know_exist():
    """Guards the guard. A walk that silently finds nothing would make
    every parametrised test below pass by vacancy -- the failure mode
    #86's own docstring warns about, one layer up.
    """
    names = set(os.path.basename(p) for p in XAML_FILES)
    assert "SharedStyles.xaml" in names, (
        "the shared palette is the file whose malformed comment killed "
        "both tools; if the walk cannot find it, nothing here is checking "
        "anything")
    assert "ColumnWindow.xaml" in names
    assert "SimpleBeamWindow.xaml" in names


@pytest.mark.parametrize("path", XAML_FILES, ids=_relative)
def test_the_file_is_well_formed_xml(path):
    """The check that would have caught it, in one line of parser."""
    try:
        ElementTree.parse(path)
    except ElementTree.ParseError as broken:
        pytest.fail(
            "%s is not well-formed XML, so WPF cannot load it and the "
            "window will not open: %s" % (_relative(path), broken))


@pytest.mark.parametrize("path", XAML_FILES, ids=_relative)
def test_no_comment_contains_a_double_hyphen(path):
    """The same rule, stated where the author will read it.

    Redundant against the parser above by design. The parser's message
    names a line and column; this one names the offending prose and the
    house habit that produced it, because the fix is to rewrite a comment
    and the author needs to know WHY a sentence that reads perfectly well
    is illegal.
    """
    text = io.open(path, encoding="utf-8").read()
    for match in _COMMENT.finditer(text):
        body = match.group(1)
        line = text.count("\n", 0, match.start()) + 1
        assert "--" not in body, (
            "%s:%d -- an XML comment body may not contain a double hyphen "
            "(XML 1.0 s2.5). This project writes ' -- ' as an em dash "
            "everywhere, which is fine in Python and fatal in XAML. "
            "Rewrite it with a comma or a full stop: %r"
            % (_relative(path), line, body[:120]))
        assert not body.endswith("-"), (
            "%s:%d -- an XML comment body may not end with a hyphen "
            "(XML 1.0 s2.5): %r" % (_relative(path), line, body[-60:]))
