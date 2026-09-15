# -*- coding: utf-8 -*-
"""Issue #86 -- how a window XAML reaches ``RFT.lib/SharedStyles.xaml``.

PURE TEXT AND PATHS. No ``pyrevit``, ``Autodesk`` or WPF import, so every
decision below is testable under plain CPython; the only thing this module
cannot check is whether WPF then parses what it produced.

## Why the obvious route does not work

pyRevit already has a resource-dictionary merge, and it is the wrong shape
for a palette. ``forms.WPFWindow.load_xaml`` merges **after**
``wpf.LoadComponent``, with its own comment saying it must::

    wpf.LoadComponent(self, self._determine_xaml(xaml_source))
    if getattr(self, '_pending_resource_merge', None):
        self.merge_resource_dict(self._pending_resource_merge)

That is correct for localisation strings, which are looked up at runtime
through ``FindResource``. It is useless for brushes, because
``{StaticResource}`` is resolved **while the XAML is being parsed** -- and
``SimpleBeamWindow.xaml`` resolves eleven of them inside ``Style`` setters
in its own ``Window.Resources``. A dictionary merged one line after
``LoadComponent`` returns has already missed them, and the load throws
"Cannot find resource named 'SkyBlue'". This project has been bitten by
``StaticResource``'s refusal to do forward references once already (the
rc6 defect, guarded by
``tests/test_simple_beam_xaml.py::test_the_window_element_itself_uses_no_static_resource``).

So the dictionary has to be in place **before** the parse, which means it
has to be declared in the markup itself, in
``ResourceDictionary.MergedDictionaries``.

## Why the Source has to be rewritten

A ``.lib`` folder is on every UI extension's **Python** module path.  It is
not on any WPF search path, so ``Source="SharedStyles.xaml"`` cannot resolve
by name, and a relative URI would resolve against the loading file's
``BaseUri`` -- i.e. the pushbutton folder, which would demand a copy of the
palette next to every window and reintroduce exactly the duplication this
ticket removes.

An **absolute** ``file:///`` URI resolves with no search path and no
``BaseUri`` at all, and #86 verified live on Revit 2024 that WPF loads a
loose ``ResourceDictionary`` from one. It cannot be written into the XAML,
because it is a different string on every machine.

Hence: the XAML carries a fixed placeholder, this module swaps in the real
absolute URI, and the window is loaded from the resulting string with
pyRevit's documented ``literal_string=True``.

The XAML file therefore stays well formed and independently viewable --
``Source="SharedStyles.xaml"`` is a real relative reference that a XAML
editor resolves if a copy sits beside it -- while what Revit actually parses
points at the one true file.

**Consequence, guarded in the tests:** loading from a string leaves
``BaseUri`` null, so a window XAML may carry **no other** relative URI
(images, fonts, further dictionaries). Only the placeholder, and only once.
"""

import os

try:                                  # IronPython 2.7 under pyRevit
    from urllib import quote as _quote
except ImportError:                   # CPython 3, for the test suite
    from urllib.parse import quote as _quote


#: The file name, and the exact ``Source`` value a window XAML must carry.
SHARED_STYLES_FILENAME = "SharedStyles.xaml"

#: The one substitution this module performs. Matched as a literal, not a
#: regex: a regex over markup invites the "it also rewrote a comment" class
#: of bug, and there is exactly one thing to find.
PLACEHOLDER_SOURCE = 'Source="%s"' % SHARED_STYLES_FILENAME


def shared_styles_path():
    """Absolute path of ``RFT.lib/SharedStyles.xaml``.

    Derived from this module's own location, not from a configured root:
    this file is at ``RFT.lib/rft/ui/shared_styles.py``, so three
    ``dirname``s reach the ``.lib`` folder. That holds wherever pyRevit
    found the library extension, which is the property that matters --
    ``RFT.lib`` and a UI extension need not be siblings, and on a real
    install they often are not.

    Does not check existence: a caller that wants to fail loudly gets a
    better message from :func:`resolve_shared_styles`, and a caller that
    only wants the path should not be forced to touch the disk.
    """
    ui_dir = os.path.dirname(os.path.abspath(__file__))
    lib_root = os.path.dirname(os.path.dirname(ui_dir))
    return os.path.join(lib_root, SHARED_STYLES_FILENAME)


def file_uri(path):
    """An absolute ``file:///`` URI for a local path, safe to paste into a
    XAML attribute.

    Percent-encoding is not optional here. This repository's own working
    copy lives under ``.../04.ESSAM-SUMMER 2026/10. BIM & POWER BI
    COURSE-V2/...`` -- spaces in nearly every segment -- and an unencoded
    space is where a URI silently becomes a different URI. Encoding also
    settles the XAML side: ``&`` in a folder name becomes ``%26`` and can
    no longer open an entity reference in the attribute value.
    """
    normalised = os.path.abspath(path).replace("\\", "/")
    # Keep the drive colon and the separators; encode everything else that
    # is not URI-unreserved, which includes the space and the ampersand.
    return "file:///" + _quote(normalised, safe="/:")


def resolve_shared_styles(xaml_text, shared_path=None):
    """``xaml_text`` with its placeholder ``Source`` pointing at the real
    ``SharedStyles.xaml``.

    Raises ``ValueError`` -- naming the count it found -- when the
    placeholder is absent or appears more than once. Both are silent
    failures otherwise: absent means the window loads with no palette and
    throws a resource error forty frames deep, twice means one window is
    quietly merging the dictionary twice.
    """
    occurrences = xaml_text.count(PLACEHOLDER_SOURCE)
    if occurrences != 1:
        raise ValueError(
            "window XAML must contain {!r} exactly once so the shared "
            "palette can be located at load time -- found {}. Without it "
            "every {{StaticResource}} in the file is unresolved and the "
            "window does not open.".format(PLACEHOLDER_SOURCE, occurrences)
        )
    if shared_path is None:
        shared_path = shared_styles_path()
    if not os.path.isfile(shared_path):
        raise ValueError(
            "the shared palette is not at {!r}. RFT.lib/SharedStyles.xaml "
            "is what every RFT window merges; without it no window "
            "opens.".format(shared_path)
        )
    return xaml_text.replace(
        PLACEHOLDER_SOURCE, 'Source="%s"' % file_uri(shared_path)
    )


def window_xaml(xaml_path, shared_path=None):
    """Read a window XAML and return it ready for
    ``forms.WPFWindow.__init__(..., literal_string=True)``.

    The one call a script makes. Reading as UTF-8 and handing WPF a string
    rather than a path is what makes the substitution possible at all.
    """
    handle = open(xaml_path, "rb")
    try:
        text = handle.read().decode("utf-8")
    finally:
        handle.close()
    return resolve_shared_styles(text, shared_path=shared_path)
