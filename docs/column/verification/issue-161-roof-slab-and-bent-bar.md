# #161 — can a longitudinal bar be BENT, and what is above a roof column?

> **Half answered, and the answered half is the one that was blocking.**
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

## Part 1 — NOT answered: nothing is modelled above that column

The ray was fired twice at column **424596** (450 x 600, top of its bounding
box at 3000 mm):

| categories | result |
|---|---|
| the shipped `SUPPORT_CATEGORIES` (floors, framing, foundations, walls) | **nothing found** |
| the same **plus `OST_Roofs`** | **nothing found** |

Both empty means this is **not** the category question — it is an empty sky.
Nothing at all sits over that column in this document, so the probe could not
reach the questions it was built for:

- which parameter carries a slab's **thickness**, per element class;
- which carries its **cover**, and whether top and bottom differ;
- whether `OST_Roofs` needs adding to `SUPPORT_CATEGORIES` — **still open**,
  and still a real risk, because the shipped list genuinely does not include
  it.

**R37 stays unverified.** What it needs is a column with something actually
over it: in this document, one of the columns reading a 2700 mm clear height
(421967, 422316, 422078) is cut by a beam or slab above, which is exactly the
element the ray should find.

## Reproducing it

`RFTProbe.extension/Probe.tab/Probe.panel/RoofBar.pushbutton`, outside the
repo like the other probes, and to be deleted once R37's half is answered too.
