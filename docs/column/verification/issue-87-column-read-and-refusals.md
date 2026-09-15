# Issue #87 — reading a column, and refusing the ones out of scope

**Status: ANSWERED.** Every parameter the window needs exists and was read
on a live host. Two findings change the design, and both are cases where
the obvious implementation returns a plausible wrong answer rather than an
error.

| | |
|---|---|
| Host | Autodesk Revit **2024**, build 24.3.40.26 |
| Document | `ColumnRFT.Trail.rvt` |
| Test column | id `421967`, `M_Concrete-Rectangular-Column : 450 x 600mm` |
| Writes | one `SubTransaction`, **rolled back** — model unchanged |
| Date | 2026-09-15 |

---

## 1. Everything the window reads, confirmed present

```
RebarHostData null? False   IsValidHost=True   exposed faces = 5
type param 'b' = 450.0 mm   'h' = 600.0 mm   ('Width'/'Depth' ABSENT)
Hand=(1,0,0)  Facing=(0,1,0)
Mirrored=False  HandFlipped=False  FacingFlipped=False
FAMILY_BASE_LEVEL_PARAM        -> Level 1   (z = 0 mm)
FAMILY_TOP_LEVEL_PARAM         -> Level 2   (z = 3000 mm)
FAMILY_BASE/TOP_LEVEL_OFFSET   -> 0.0 mm / 0.0 mm
SLANTED_COLUMN_TYPE_PARAM      -> 0  (vertical)
CLEAR_COVER_OTHER   -> Interior (framing, columns) = 40.0 mm
CLEAR_COVER_BOTTOM  -> Interior (framing, columns)
CLEAR_COVER_TOP     -> ElementId -1   << STILL UNSET (Q5)
```

Levels in the document: `Level 1 @ 0`, `Level 2 @ 3000`, `Level 3 @ 6000`.
The test column spans Level 1 → Level 2, so **no level lies strictly
between** and it is single-storey. The multi-storey refusal therefore has
no positive case in this model and is verified only against its negative;
the rule itself is pure and is unit-tested on fabricated levels.

**Exposed faces = 5, not 6.** The column is joined to the floor above, so
its top face is not exposed. Nothing in #87 depends on this, but a per-face
cover read on a column would hit it, exactly as the beam tool's four-face
case does.

---

## 2. ⚠️ "Four vertical faces in antiparallel perpendicular pairs" — the
   *count* is what does the work, not the pairs

The rectangular column and a UC I-section column (placed inside a
rolled-back `SubTransaction`, since the family was loaded but unplaced):

| | vertical planar faces | curved faces | distinct vertical normals |
|---|---|---|---|
| `450 x 600mm` rectangular | **4** | 0 | `(1,0) (0,-1) (-1,0) (0,1)` |
| `UC305x305x97` I-section | **12** | 4 | `(1,0) (0,-1) (-1,0) (0,1)` |

Read that second row again. **The I-section's vertical faces have exactly
the same four normal directions as the rectangle** — every flange and web
face is axis-aligned, in antiparallel perpendicular pairs. A check that
tests only the *directions* of the normals **passes an I-section**, and the
tool would go on to detail a rectangular cage into a steel UC.

> **The discriminator is `exactly four vertical planar faces and zero
> curved faces`.** #87's brief already says "exactly four"; this records
> that the "exactly" is load-bearing and the "antiparallel perpendicular
> pairs" half, on its own, is not a test at all.

The four curved faces on the UC are its root fillets, which is also why
"count the planar faces" alone (14) would not have separated them either.

---

## 3. ⚠️ `ReferenceIntersector` answers differently per view — and the
   wrong answer is silence, not an error

Same document, same column, same ray, same category filter. Only the
`View3D` differs:

```
view 'Analytical Model'   UP -> NOTHING
view '{3D}'               UP -> Floors z=2700.0
```

#69 used `{3D}` and got the soffit. Picking "the first non-template
`View3D`" — the obvious implementation — picks `Analytical Model` in this
document and gets **nothing**. Per R5/R6 "nothing at this end" is a
*legitimate* outcome that falls back to the level elevation, so the tool
would silently detail to 3000 mm instead of 2700 mm. That is the same
300 mm error #69 warned about, arriving through a different door and
without any of the symptoms that made it findable the first time.

### Category visibility does NOT detect the bad view

```
view 'Analytical Model': Floors=visible Framing=visible Foundation=visible Walls=visible | template=-1 | sectionBox=False
view '{3D}':             Floors=visible Framing=visible Foundation=visible Walls=visible | template=-1 | sectionBox=False
```

Identical on every property inspected, including `GetCategoryHidden` for
all four search categories, `ViewTemplateId` and `IsSectionBoxActive`. The
views differ in `DisplayStyle` (`FlatColors` vs `HLR`) and `DetailLevel`
(`Medium` vs `Fine`), neither of which is a defensible criterion.

**So the view cannot be validated by inspecting its settings.**

### What does work: make the view prove itself

Fire a ray at **the column being detailed**. It is known to be there; a
view that cannot see it cannot be trusted to see a support above it.

```
view 'Analytical Model'  SELF TEST sees the column: NO   (hits=0)
view '{3D}'              SELF TEST sees the column: YES  (hits=2)
```

> **Ruling for the implementation:** choose the search view by **behaviour,
> not by name or by settings**. Try each non-template `View3D`; keep the
> first whose `ReferenceIntersector` can see the host column itself. If
> none can, **refuse** and say so — do not fall back to a level elevation,
> because at that point "no support found" is uninformative rather than
> meaningful.

This also removes the dependence on a view literally named `{3D}`, which is
localised and renameable.

---

## 4. The window itself, constructed on the host

The composed `ColumnWindow.xaml` — placeholder `Source` rewritten to the
real palette path — parsed and constructed in Revit's own WPF:

```
COLUMN WINDOW CONSTRUCTED: Detail Column  880x680
merged dictionaries = 1
all 22 x:Name controls resolved
  longitudinal_tab ships IsEnabled=False
  ties_tab         ships IsEnabled=False
  review_tab       ships IsEnabled=False
  SkyBlue #FF87CEEB   SkyBlueDeep #FF1F6F94
  InkMuted #FF5A6B75  SurfaceWhite #FFFFFFFF
ReadOut / ReadOutSource styles found: True / True
tab count = 4
```

That also closes #86's third acceptance line: a **second** window resolves
the same keys from the same file.

### ⚠️ A `Click="handler"` attribute throws at parse time

The first attempt carried `Click="on_pick_click"` in the markup, the way a
compiled WPF application would. It fails:

```
PARSE FAILED: XamlParseException: 'Failed to create a 'Click' from the text
'on_pick_click'.' Line number '142' and line position '57'.
|| INNER: Cannot bind to the target method because its signature or security
transparency is not compatible with that of the delegate type.
```

A window loaded from a **string** has no code behind, so WPF has nowhere to
resolve the name. The beam window has always wired handlers in Python
(`self.pick_btn.Click += self.on_pick_click`); this is why, written down.
The markup parsed as XML perfectly, so only a host could have found it —
hence a guard over both windows.

## 5. Still unverified

- **Only one non-rectangular family** was tested, and only as a temporary
  instance. Circular columns (a genuinely curved vertical face) and L- or
  T-shaped concrete columns are untested — the count rule should catch
  both, but "should" is not "did".
- `Mirrored` / `HandFlipped` / `FacingFlipped` were all `False`, as in #69.
  Their effect on the `b`→Hand, `h`→Facing mapping remains **untested**.
- `b` and `h` are the parameter names of the **Autodesk metric
  `M_Concrete-Rectangular-Column`** family. Any other family names them
  differently. `SHAPE UNVERIFIED` — the tool must refuse a family whose
  dimensions it cannot read by name rather than guess.
- The multi-storey rule has **no positive case** in this model.
- The self-test was validated on two views in one document. A view that can
  see columns but not floors would defeat it; none was available to build.
- Slanted columns untested (`SLANTED_COLUMN_TYPE_PARAM = 0` throughout).
