# -*- coding: utf-8 -*-
"""Which resource keys a window XAML can actually resolve (issue #86).

Before #86 this was one line -- scrape ``x:Key`` out of the window file --
and two separate tests inlined it. Once the palette moved to
``RFT.lib/SharedStyles.xaml`` that answer became wrong in the dangerous
direction: the keys are still resolvable on a live host, but no longer
present in the window's own text, so a guard reading only the window would
fail on correct markup and, worse, a guard "fixed" by deleting it would
stop watching anything.

So the question every such guard is really asking is *"will WPF find this
key when it parses this window"*, and the answer spans two files. This
module is that answer, in one place, for both the beam window and (from
#87) the column one.

It is deliberately TEXT scraping, like the guards it serves: nothing here
can execute WPF, and a regex over ``x:Key`` is exactly as much as can be
known under plain CPython. See ``tests/fake_revit_api.py``'s header for
why that is the standing constraint rather than a shortcut.
"""

import io
import os
import re

from rft.ui.shared_styles import PLACEHOLDER_SOURCE, shared_styles_path

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

BEAM_PUSHBUTTON_DIR = os.path.join(
    REPO_ROOT,
    "SimpleBeamRFT.extension", "RFT-Tools.tab",
    "Beams.panel", "Simple Beam.pushbutton",
)
BEAM_XAML_PATH = os.path.join(BEAM_PUSHBUTTON_DIR, "SimpleBeamWindow.xaml")

SHARED_STYLES_PATH = shared_styles_path()

_X_KEY = re.compile(r'x:Key="([A-Za-z0-9_]+)"')


def read(path):
    return io.open(path, encoding="utf-8").read()


def declared_keys_in(text):
    """Every ``x:Key`` declared in one piece of markup."""
    return set(_X_KEY.findall(text))


def merges_shared_styles(text):
    """True when this window carries the placeholder that
    ``rft.ui.shared_styles`` rewrites into the real palette location.
    """
    return PLACEHOLDER_SOURCE in text


def resolvable_keys(window_path):
    """Every key a window can resolve: its own, plus the shared palette's
    when (and only when) it actually merges the shared palette.

    The conditional matters. A window that drops the merge line still
    parses as XML and still declares its own styles -- it simply throws
    "Cannot find resource named 'SkyBlue'" the first time someone presses
    the button. Unioning the shared keys unconditionally would hide
    exactly that.
    """
    text = read(window_path)
    keys = declared_keys_in(text)
    if merges_shared_styles(text):
        keys |= declared_keys_in(read(SHARED_STYLES_PATH))
    return keys
