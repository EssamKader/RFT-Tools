# -*- coding: utf-8 -*-
"""The window title must name the build it is actually running.

## The failure this exists to stop, twice over

`CHANGELOG.md` already records it once: `v0.3.0` was released on a
reported test of `v0.3.0-rc4` that had in fact been run against
`v0.3.0-rc3`, because the deployed worktree was never moved.

It happened again on the column side. The build tested immediately before
`column/v0.1.0` reported **`v0.1.0-rc4`** in its title while running more
than twenty commits past that tag, because
`ColumnRFT.extension/VERSION` was never bumped. Everything observed in
that session was therefore, strictly, an observation about an unidentified
build.

A version stamp that can drift is worse than none: a build with no stamp
is obviously unidentified, while a build with a stale one **claims** to be
something it is not, and the claim is believed.

## What this can and cannot check

It CANNOT check that the deployed worktree is at the right commit -- that
is a property of a folder on someone's machine, not of the repository.
That one is guarded by the checklist at the top of `CHANGELOG.md`.

It CAN check that the version the extension stamps into its title is the
version the changelog says is current. When they disagree, one of the two
was forgotten, and forgetting either is how the failure above starts.
"""

import io
import os
import re

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

VERSION_FILES = {
    "column": os.path.join(REPO_ROOT, "ColumnRFT.extension", "VERSION"),
    "beam": os.path.join(REPO_ROOT, "SimpleBeamRFT.extension", "VERSION"),
}
CHANGELOG = os.path.join(REPO_ROOT, "CHANGELOG.md")


def _read(path):
    return io.open(path, encoding="utf-8").read()


def _stamped(tool):
    return _read(VERSION_FILES[tool]).strip()


def _changelog_versions():
    """Every version heading, newest first, in the order they appear."""
    return re.findall(r"^## \[([^\]]+)\]", _read(CHANGELOG), re.MULTILINE)


def test_every_extension_carries_a_version_file():
    for tool, path in VERSION_FILES.items():
        assert os.path.isfile(path), "%s has no VERSION file" % tool
        assert _stamped(tool), "%s's VERSION file is empty" % tool


def test_the_version_stamp_looks_like_a_version():
    for tool in VERSION_FILES:
        assert re.match(r"^v\d+\.\d+\.\d+(-rc\d+)?$", _stamped(tool)), (
            "%s stamps %r, which is not a version this project releases"
            % (tool, _stamped(tool)))


def test_the_COLUMN_stamp_matches_the_newest_column_entry():
    """The check that would have caught the stale rc4.

    The column tool's changelog headings are prefixed `column/`, because
    it versions independently of the beam.
    """
    column_entries = [v for v in _changelog_versions()
                      if v.startswith("column/")]
    assert column_entries, "no column entry in CHANGELOG.md"
    newest = column_entries[0].split("/", 1)[1]
    assert _stamped("column") == newest, (
        "ColumnRFT.extension/VERSION stamps %r while the newest changelog "
        "entry is %r. One of the two was forgotten, and a build whose "
        "title CLAIMS a version it is not is how this project has already "
        "shipped an unverified release once."
        % (_stamped("column"), newest))


# The BEAM's stamp is asserted by
# `tests/test_simple_beam_xaml.py::test_the_version_file_matches_the_newest_changelog_entry`,
# which is that tool's own file. A second copy here would be free to
# drift from it, and two guards disagreeing about one rule is worse
# than one guard.


def test_BOTH_tools_appear_in_the_changelog():
    """They version independently, in one repository, so each needs its own
    entries -- a tool with none has no released version anyone can check a
    window title against."""
    column_entries = [v for v in _changelog_versions()
                      if v.startswith("column/")]
    beam_entries = [v for v in _changelog_versions()
                    if not v.startswith("column/")]
    assert column_entries, "no column entries in CHANGELOG.md"
    assert beam_entries, "no beam entries in CHANGELOG.md"
