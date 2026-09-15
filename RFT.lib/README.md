# `RFT.lib` — the shared library extension

This is a pyRevit **library extension**, not a folder of loose modules.
Any folder whose name ends in `.lib` is collected by
`get_installed_ui_extensions` and added to the module path of **every** UI
extension under the same registered search root:

```python
# pyrevitlib/pyrevit/extensions/extensionmgr.py
def _update_extension_search_paths(ui_ext, lib_ext_list, pyrvt_paths):
    for lib_ext in lib_ext_list:
        ui_ext.add_module_path(lib_ext.directory)
```

That is why `rft` lives here and not in `SimpleBeamRFT.extension/lib/`,
where only the Simple Beam button could have imported it.

Three rules, each guarded by `tests/test_library_extension_layout.py`
because each fails **silently** — the beam tool keeps working on this
machine while a second element cannot import anything:

1. **The folder name must end in `.lib`.** `LibraryExtension.matches` is a
   suffix test. `RFT-lib` is an ordinary folder pyRevit says nothing about.
2. **The package sits at `RFT.lib/rft`, never `RFT.lib/lib/rft`.** The path
   added is this directory itself.
3. **No UI extension may contain its own `rft` copy.** pyRevit's own
   comment: paths internal to an extension "will take precedence over
   paths added by this method." The shadowing copy is the one that drifts.

`RFT.lib` needs no `extension.json` — `LibraryExtension` reads only the
directory name.

## What is in here

| package | contents |
|---|---|
| `rft/core` | pure spec logic in millimetres — no Revit import, no UI. Fully unit-tested |
| `rft/revit` | the Revit API boundary: host validation, bar types, geometry, placement, units |
| `rft/ui` | window-agnostic UI logic: input parsing, review derivation, the report, sketch geometry, label layout, persistence |

`rft/core` and `rft/ui/sketch*` import nothing outside the standard
library, which is what makes them testable under CPython. `rft/revit`
imports `Autodesk.Revit.DB` and can only run inside Revit;
`tests/fake_revit_api.py` stands in for it.

**Which of these a new element can reuse, and which it cannot, is
audited per module in `docs/reuse-for-new-elements.md`.** Read that before
importing from here for a column, wall, slab or footing.

Everything here runs under **IronPython 2.7** in production. The
constraints that implies — the PEP 263 encoding cookie, no f-strings, no
Python-3-only stdlib — are enforced by
`tests/test_ironpython_compat.py`, which walks this folder and the UI
extension.

---

## `SharedStyles.xaml` — the one file that is not Python

`RFT.lib/SharedStyles.xaml` holds the RFT colour palette: thirteen
`SolidColorBrush` entries and nothing else. Every element's window merges
it, so a colour change repaints every tool and no two windows can drift
(#86).

It sits **beside** `rft/`, in the `.lib` folder itself, for the same
reason rule 2 above puts the package there — that directory is what
pyRevit adds to the path.

**But that path is Python's, not WPF's.** Nothing resolves this file by
name, and a window cannot simply write `Source="SharedStyles.xaml"` and
expect it to load. Two facts decide the mechanism, and both are the
opposite of the obvious guess:

1. **The merge must happen before the parse, not after.** pyRevit's own
   `WPFWindow.merge_resource_dict` runs *after* `wpf.LoadComponent`, which
   is right for localisation strings (looked up later, through
   `FindResource`) and useless for brushes — `{StaticResource}` resolves
   *during* the parse, and a window's `Style` setters resolve it eleven
   times before `LoadComponent` returns.
2. **The URI must be absolute.** A relative one resolves against the
   loading file's `BaseUri`, i.e. the pushbutton folder — which would
   demand a copy of the palette beside every window.

So the window's markup carries a fixed placeholder `Source`,
`rft.ui.shared_styles` rewrites it to an absolute `file:///` URI derived
from its own location, and the window is loaded from the resulting
**string** (`literal_string=True`).

The cost of loading from a string is that there is no `BaseUri` at all,
so **a window XAML may carry no other relative URI** — no image, no
icon, no second dictionary. That is guarded per window
(`tests/test_simple_beam_xaml.py::test_the_xaml_carries_no_other_relative_uri`),
along with "the merge line is still there" and "no local brush shadows a
shared one", because each of those leaves the file well formed and every
other test green while breaking the window on a live host.
