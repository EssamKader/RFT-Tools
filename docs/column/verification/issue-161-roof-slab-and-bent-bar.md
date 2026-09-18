# #161 — can a longitudinal bar be BENT, and what is above a roof column?

> **Both halves answered.** The bent bar works; the slab above reads its",
"> thickness two ways that agree — and reports a cover of **zero**, which is",
"> the finding that needs a ruling.
>
> **Superseded below:**
> `CreateFromCurves` takes a two-curve bar and returns a **shape-driven**
> rebar. R37's read is still unmeasured — the probe found nothing above the
> column it was pointed at, because nothing is modelled there.

## What ran, and against what

Revit **2024**, build **24.3.40.26**. Document **`ColumnRFT.Trail`**, active
view `{3D}`. Raw transcript: `issue-161-transcript.txt`.

Part 1 reads. Part 2 **writes**, inside a transaction that was **rolled
back** — #69's pattern; the created bar (id 424651) does not exist.

## Part 2 — a bent bar is accepted, and Revit fillets the corner

Two curves went in: a **500 mm** vertical leg and a **400 mm** horizontal leg
along `+Hand`, meeting at a sharp corner, with `Facing` passed as the normal
(the bend turns in the Z/Hand plane). What came back:

| # | curve | length |
|---|---|---|
| 0 | `Line` | **453.7 mm** |
| 1 | **`Arc`** | **72.8 mm** |
| 2 | `Line` | **353.7 mm** |

- **`Rebar.CreateFromCurves` accepts the two-curve array** for a
  `RebarStyle.Standard` bar. Section 1 does not need a `RebarShape` or a
  hook.
- **The result is still shape-driven** — `GetShapeDrivenAccessor()` returned
  a `RebarShapeDrivenAccessor`. That matters more than it looks: the layout
  call and R22's face pinning both go through that accessor, so a bent bar
  stays inside the machinery the straight bar already uses.
- **`normal = Facing` was accepted** for a bar bending in the Z/Hand plane.
  `column_place_bars.py`'s header flags this argument as SHAPE UNVERIFIED for
  a straight bar; for a bent one it is now measured, in one plane.

### The finding that changes section 1's arithmetic

**Revit replaced the sharp corner with an arc, and shortened BOTH legs to
suit.** The numbers are exact:

    500.0 - 453.7 = 46.3      400.0 - 353.7 = 46.3

Both legs lost the same **46.3 mm**, which is the bend's **tangent length**,
and the arc that replaced the corner is **72.8 mm**. For a 90° bend the
tangent equals the radius, so the bar type's bend radius here is **≈ 46.3 mm**
— and `46.3 x π/2 = 72.7`, which is the arc, to within the printed
precision. The geometry is self-consistent.

So for a **13M** bar (12.7 mm), `r ≈ 3.6 d_b`.

**What this means for `a + b = L_D`.** The legs the tool hands
`CreateFromCurves` are **corner-to-corner**, but the bar that gets built is
shorter through the corner and curved round it:

    requested, corner to corner   500.0 + 400.0        = 900.0 mm
    built, developed              453.7 + 72.8 + 353.7 = 880.2 mm

**A 19.8 mm difference on one bend** — about 2%, and it is a *shortfall*, so
a bar asked for exactly `L_D` develops slightly less than `L_D`.

This is the same relationship `rft.core.column_ties` already handles for tie
corners: `tangent_length_mm`, `t = r / tan(θ/2)`, which at 90° reduces to
`t = r`. The math exists; what is now established is that **the roof
termination needs it too**, and that the difference is not negligible enough
to ignore.

> **Open, and it is a ruling rather than a measurement.** Is `L_D` the
> **developed centreline length** of the built bar, or the sum of the two
> nominal legs? Codes state development length as a length OF BAR, which
> argues for the centreline — but this is a detailing decision and the ledger
> has no entry for it. Until it is ruled on, `rft.core.column_roof` computes
> the nominal `a + b`, which is what section 1 literally says.

## Part 1, first attempt — WRONG, and worth keeping

> Two runs reported "nothing found". Neither was true, and neither failure
> was in the API. **The probe's own mistakes**, recorded because both are
> the kind that produce a confident empty answer.

### Mistake 1 — the probe chose the view

`ReferenceIntersector` runs only in a `View3D`. Run from an elevation it
raised `TypeError: expected View3D, got ViewSection`; run from `{3D}` before
the slab existed it found nothing honestly. The tool never uses the active
view either: `find_search_view` picks a 3D view **by behaviour**, firing a
test ray at the column and rejecting any view that cannot see it. The probe
now imports that function, and the tool's own ray origin and clearance with
it.

### Mistake 2 — a good theory, measured and false

The owner observed that a column joined to a floor reads differently, and
that a beam joined to the floor above it cannot read its top cover (#164).
The obvious inference was that the join merges the two solids, dissolves the
face between them, and that the ray therefore passed through the junction
unnoticed.

**It does not.** This column IS joined to the floor — and the ray finds the
soffit at 2700.0 mm anyway, from the same view, in the same run. The join
was not why the earlier attempts came back empty. The beam's problem in #164
is therefore NOT explained by this, and that ticket should not inherit the
theory.

## Part 1 — answered: the floor above, read two independent ways

Column **424596** (450 x 600, top at 3000 mm) sits under **Floor 424637**,
type `Generic 300mm`, spanning **2700..3000 mm**. Two mechanisms found it,
independently:

| mechanism | result |
|---|---|
| `JoinGeometryUtils.GetJoinedElements` | **Floor 424637**, and `IsCuttingElementInJoin(column, floor)` is **False** — the floor cuts the column, not the reverse |
| the upward ray, shipped categories | **Floor 424637**, face z **2700.0 mm** (the soffit) |
| the upward ray, `+OST_Roofs` | identical |

**`OST_Roofs` was not needed here**, because this roof is modelled as a
Floor. The question of whether `SUPPORT_CATEGORIES` needs it stays open for
a model that uses an actual Revit Roof — the shipped list still excludes
the category, and nothing here says that is safe.

### Thickness — three sources, all agreeing

| source | value |
|---|---|
| `FLOOR_ATTR_THICKNESS_PARAM` | **300.0 mm** |
| `STRUCTURAL_FLOOR_CORE_THICKNESS` | **300.0 mm** |
| the type's compound structure | **300.0 mm**, 1 layer |

`ROOF_ATTR_THICKNESS_PARAM` is absent on a Floor, as expected. Agreement
across three sources is what makes this safe to read; a disagreement would
have been the finding instead.

### Cover — **every parameter answers, and every answer is ZERO**

| parameter | value |
|---|---|
| `CLEAR_COVER_TOP` | **0.0 mm** |
| `CLEAR_COVER_BOTTOM` | **0.0 mm** |
| `CLEAR_COVER_OTHER` | **0.0 mm** |
| `CLEAR_COVER` | absent |

**This is the dangerous case, and it is dangerous precisely because it
succeeds.** The parameter is present and readable, so a read that only
checks “did I get a number?” gets one. Section 1 then computes

    a = thickness - cover = 300 - 0 = 300 mm

and puts the bar's horizontal leg **on the top surface of the slab** —
outside the concrete, with nothing over it. A cage that looks placed and is
exposed.

Zero is not a cover. On this `Generic 300mm` floor it means **nobody set
one**, and A2's “cover is READ, never typed” assumed the model would have
something to read. **R37 needs a rule for the unset case**, and it is the
one thing standing between this and an implementable section 1.

## Reproducing it

`RFTProbe.extension/Probe.tab/Probe.panel/RoofBar.pushbutton`, outside the
repo like the other probes, and to be deleted once R37's half is answered too.
