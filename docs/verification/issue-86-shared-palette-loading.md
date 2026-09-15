# Issue #86 — how a window reaches `RFT.lib/SharedStyles.xaml`, verified live

**Status: ANSWERED, and every prediction in the PR held.** The chosen
mechanism works on the real composed beam window; the two routes it was
chosen over both fail, with the exact exceptions predicted. One incidental
finding removes a third design option permanently.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26 |
| Document | `ColumnRFT.Trail.rvt` (irrelevant here — nothing was written) |
| Thread | **STA**, so WPF construction is legal in this context |
| Writes | **none.** No transaction was opened; only WPF objects were built, then closed |
| Date | 2026-09-15 |

Shared across elements, so this lives in `docs/verification/` rather than
under `docs/beam/` or `docs/column/`.

---

## 0. The incidental finding that settles a design option

```
App.Current = null
```

`System.Windows.Application.Current` is **null inside Revit**. Revit hosts
WPF without a WPF `Application`.

That permanently removes the tidiest-looking alternative: putting the
palette in `Application.Current.Resources`, where `{StaticResource}`
lookup falls through to it during the parse and no markup change would be
needed at all. There is no such dictionary to put it in. Worth recording
because it is the first thing anyone reaching for a second opinion will
propose.

## 1. The palette loads from the percent-encoded absolute URI

The URI `rft.ui.shared_styles.file_uri` actually produces for this working
copy — spaces and an ampersand and all:

```
file:///D:/00.ESSAM/04.ESSAM-SUMMER%202026/10.%20BIM%20%26%20POWER%20BI%20COURSE-V2/1.PyRevit%20Tools/00.RFT-Plugin/RFT.lib/SharedStyles.xaml
```

```
dictionary loaded, keys = 13
ALL 13 BRUSHES CORRECT
```

All thirteen keys present, every `Color` compared against the value #60
shipped, not merely against the file. The percent-encoding is not
decorative: this repository's own path carries three spaces and an `&`
before it reaches the `.lib` folder.

## 2. The real composed window parses, from a STRING, with no BaseUri

Not a reduced sample — `SimpleBeamWindow.xaml` put through
`rft.ui.shared_styles.window_xaml` and handed to `XamlReader.Parse`, which
is the null-`BaseUri` condition `literal_string=True` creates:

```
composed xaml: 32528 chars, from a STRING (no BaseUri)
WINDOW CONSTRUCTED: title=Simple Beam  880x680
merged dictionaries on Window.Resources = 1
  SkyBlue         #FF87CEEB
  SkyBlueDeep     #FF1F6F94
  InkMuted        #FF5A6B75
  BorderSubtle    #FFC9DFEA
  PassGreen       #FF2E7D32
  DangerRed       #FFB00000
  WarningAmber    #FFB05A00
  SurfaceWhite    #FFFFFFFF
  SectionHeading  Style
root Grid background = #FFFFFFFF
x:Name 'tabs' resolved = YES, tabs=5
```

Three things in that output matter beyond "it loaded":

- **`SectionHeading` resolved as a `Style`.** That Style's own setter is
  `{StaticResource SkyBlueDeep}`, resolved *during* the parse against the
  merged dictionary. This is the whole claim, demonstrated rather than
  argued.
- **The root Grid is `#FFFFFFFF`.** The window is painting from the shared
  palette, not from a default.
- **`x:Name` still resolves** (`tabs`, 5 tab items). Loading from a string
  did not cost the name lookup the script depends on throughout.

## 3. Both rejected routes fail, with the predicted exceptions

```
1. NO-MERGE            -> Cannot find resource named 'InkMuted'. Resource names are case sensitive.
2. MERGE-AFTER-LOAD    -> Cannot find resource named 'InkMuted'. Resource names are case sensitive.
3. RELATIVE URI        -> Cannot locate resource 'sharedstyles.xaml'.
```

**1. The merge line is load-bearing.** Delete it and the file is still
well-formed XML with every Style intact — and the window does not open.
This is the failure
`tests/test_simple_beam_xaml.py::test_the_window_merges_the_shared_palette`
exists to catch before a host sees it. The guard's premise is now observed,
not assumed.

**2. pyRevit's own route cannot work here.** `merge_resource_dict` runs
after `LoadComponent`; the parse throws first, so the merge line is never
reached. The reasoning in the PR was right for the right reason — the
failure is at parse time, not a missing-key-at-paint-time problem that a
later merge could repair.

**3. A relative `Source` does not resolve** in a string-loaded window.
Note the lower-cased `'sharedstyles.xaml'` in the message: WPF got as far
as treating it as a resource name, found no `BaseUri`, and gave up. This is
why the rewrite to an absolute URI is the mechanism rather than a
convenience, and why
`test_the_xaml_carries_no_other_relative_uri` guards every *other* URI in
the file.

## 4. What this does NOT cover

- **pyRevit's `wpf.LoadComponent`** was not used — `XamlReader.Parse` was.
  They differ in how `x:Name` is wired to the instance (`FindName` here vs
  fields on `self`), and that wiring is unchanged by #86. The resource
  question, which #86 is about, is identical.
- **The path derivation itself** — three `dirname`s from
  `rft/ui/shared_styles.py` to the `.lib` folder — was exercised only under
  CPython on this machine. Under pyRevit, `rft` is imported from wherever
  pyRevit registered the library extension, and only a live pyRevit session
  can confirm that `__file__` is what this assumes. The composed URI above
  *is* the one that module produced, which is as close as this can get
  without the button.
- **The button has not been pressed.** Opening the beam window from the
  ribbon remains the last step before the next tag.
- One document, one machine, Revit 2024. `SHAPE UNVERIFIED` discipline's
  cousin applies: this is one host's answer.
