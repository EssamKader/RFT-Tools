# R42 — measuring how far the slab extends

> **Answered, by two independent mechanisms agreeing to 0.1 mm.** The run is
> readable per bend direction, and the owner's near-the-edge case is real: the
> probed column has **127.5 mm** of slab in one direction and **5059.7 mm** in
> another.

## What ran

Revit **2024**, build **24.3.40.26**, document **`ColumnRFT.Trail`**,
read-only, no transaction. Transcript: `r42-slab-run-transcript.txt`.

Column **424596** (450 x 600, `Hand = (1,0,0)`, `Facing = (0,1,0)`) under
**Floor 424637**, top face at 3000 mm, area 20.30 m².

## The two mechanisms agree exactly

| direction | boundary loops | horizontal ray |
|---|---|---|
| **+Hand** | **127.5 mm** | **127.5 mm** |
| −Hand | 2922.5 mm | 2922.5 mm |
| +Facing | 5059.7 mm | 5059.7 mm |
| **−Facing** | **140.3 mm** | **140.3 mm** |

- **the boundary read** — the floor's top `PlanarFace`,
  `GetEdgesAsCurveLoops()`, and the nearest crossing of a 20 m probe line
  from the column's own face;
- **the ray** — a `ReferenceIntersector` with `FindReferenceTarget.Face`,
  fired horizontally through the slab.

Nothing distinguishes them on this host, so **R42 may be built on either**.
The boundary read is the better primary: it needs no `View3D`, which is the
dependency that made two of #161's runs report an empty sky.

## The owner's case, measured

This column is exactly the one the case was raised about. It sits **127.5 mm**
from the slab edge in `+Hand` and **140.3 mm** in `−Facing` — a corner column
in everything but name, while its family type and its extent say nothing about
that.

With `L_D = 960` (60 x 16), `a = 275` and the 19.87 mm fillet allowance, the
bend needs about **705 mm** of run:

| if the bar bent | run | develops | verdict |
|---|---|---|---|
| `+Hand` | 127.5 | 382.6 | **577 mm short** |
| `−Facing` | 140.3 | 395.4 | 565 mm short |
| `−Hand` | 2922.5 | 960.0 | full `L_D` |
| **`+Facing`** | **5059.7** | **960.0** | full `L_D`, and the most room |

**R41 picks `+Facing`, and that is right.** Under the old binary rule every
one of these four directions read “slab continues” and the first-stated would
have won — which, listed `+Hand` first, would have put 577 mm of bar into
fresh air.

## What still needs subtracting, and is NOT in these numbers

The probe measures **to the boundary**. R42 says the run is that distance
**less the slab's edge cover**, and this floor's cover reads **0.0** (R38), so
the two happen to coincide here. They will not on a slab with cover set, and
the adapter must subtract it rather than inherit this coincidence.

## What this probe did NOT establish

1. **Openings.** This face has **one** loop. The code takes the nearest
   crossing across every loop, so a stair void beside a column should count as
   an edge — but that is a reading of the code, not a measurement. A slab with
   a hole in it has never been tested.
2. **A rotated column.** `Hand`/`Facing` here are the world axes. The four
   runs are measured along the column's own frame, which #103 proved exact at
   45° and 315° — but no rotated column has been run through THIS probe.
3. **A non-rectangular slab**, or one whose boundary curves are arcs. Every
   crossing here came from a straight edge.

None of the three blocks the adapter. All three are worth a second run when a
model offers them.

## Reproducing it

`RFTProbe.extension/Probe.tab/Probe.panel/SlabRun.pushbutton`, outside the
repo, to be deleted with the rest once the adapter lands.
