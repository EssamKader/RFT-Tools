# -*- coding: utf-8 -*-
"""Issue #87 — which columns this tool will detail, decided in pure Python.

PURE. Millimetres in, decisions out. No ``Autodesk`` import, no Revit type:
``rft.revit.column_host`` reads the model and hands the plain numbers here,
so every refusal is unit-testable under CPython and none of them is
discovered for the first time on a live host.

Deliberately NOT reused from the beam side. ``rft.core.plan``'s face model
describes a beam's cross-section as top/bottom/side layers; a column's four
vertical faces are a perimeter, not a top and a bottom (spec §6.2), and
``docs/column/reuse-audit.md`` records that split. The spacing arithmetic
and grade tables ARE shared; this is not.

Spec references are to `specs/column-rft-detailing.md`; refusals R12/R13
are the ones §0 puts out of scope, and the ledger entries are in
`docs/column/spec-amendments.md`.
"""

from collections import namedtuple

#: Faces whose normal is this close to horizontal count as vertical. A
#: column face is either vertical or it is not one of the four this tool
#: details against, so the tolerance only has to survive tessellation
#: noise, not describe a real slope.
VERTICAL_NORMAL_TOL = 1.0e-6

#: Two unit normals are antiparallel when their dot product is this close
#: to -1, and perpendicular when it is this close to 0.
DIRECTION_TOL = 1.0e-3

#: A level this close to an end of the column counts as AT that end rather
#: than between the two. Revit stores elevations exactly, but a level and a
#: column top that were set independently to "3000" can differ in the last
#: bit, and a 0.1 mm difference must not read as a storey.
LEVEL_COINCIDENCE_TOL_MM = 1.0


#: Section dimensions, with the spec's two roles named rather than left to
#: the caller to work out. §2 makes the SMALLER dimension govern S0 (§4)
#: and the LARGER govern L0 (§3); reading them the wrong way round inverts
#: both silently, which is why they are resolved once, here.
ColumnSection = namedtuple(
    "ColumnSection", "b_mm h_mm narrow_mm wide_mm")


#: What the window shows for the vertical extent, and where each end came
#: from. ``base_source``/``top_source`` are one of the SOURCE_* constants
#: below -- the window states them, because "2700" from a support face and
#: "2700" from a level elevation are not the same claim (R5/R6).
ColumnExtent = namedtuple(
    "ColumnExtent",
    "base_z_mm top_z_mm clear_height_mm base_source top_source")

SOURCE_SUPPORT_FACE = "support face"
SOURCE_LEVEL_ELEVATION = "level elevation"


def section_from_dimensions(b_mm, h_mm):
    """Resolve `b`/`h` into the roles §2 gives them.

    `b` is the extent along `HandOrientation` and `h` along
    `FacingOrientation` (#69, proven by rotating the column 35° and
    measuring: both are invariant, the bounding box is not). Which of them
    is the *narrow* one is a property of the numbers, not of the
    directions, so a 600 × 450 column is handled by the same code as a
    450 × 600 one.
    """
    if b_mm <= 0 or h_mm <= 0:
        raise ValueError(
            "column section dimensions must be positive -- got b=%r h=%r. "
            "A zero or negative dimension means the family's parameters "
            "were not read, not that the column is thin." % (b_mm, h_mm))
    return ColumnSection(
        b_mm=b_mm, h_mm=h_mm,
        narrow_mm=min(b_mm, h_mm), wide_mm=max(b_mm, h_mm))


def _is_vertical(normal_xyz):
    return abs(normal_xyz[2]) <= VERTICAL_NORMAL_TOL


def _dot2(a, b):
    return a[0] * b[0] + a[1] * b[1]


def rectangular_section_refusal(face_normals, curved_face_count):
    """``None`` when the solid is a rectangular prism this tool can detail;
    otherwise the reason, in the words the user will read.

    ``face_normals`` is every PLANAR face's unit normal as an ``(x, y, z)``
    triple; ``curved_face_count`` is how many faces were not planar.

    ## The count is the test

    #87's live probe placed a `UC305x305x97` I-section beside the
    rectangular column. Its twelve vertical faces have **exactly the same
    four normal directions** as the rectangle's four -- every flange and
    web face is axis-aligned, in antiparallel perpendicular pairs. A check
    that looks only at directions passes it, and the tool details a
    rectangular cage into a steel UC.

    So the count is checked first and the directions second. The direction
    check still earns its place: it rejects a parallelogram or a trapezoid,
    which has four vertical faces and is not a rectangle.
    """
    if curved_face_count:
        return (
            "This column's solid has %d curved face(s), so it is not "
            "rectangular. The tool details rectangular columns only "
            "(spec section 0)." % curved_face_count)

    vertical = [n for n in face_normals if _is_vertical(n)]
    if len(vertical) != 4:
        return (
            "This column's solid has %d vertical faces, not 4, so it is "
            "not rectangular. The tool details rectangular columns only "
            "(spec section 0). An I-section reports 12." % len(vertical))

    # Two antiparallel pairs, the pairs perpendicular to each other.
    #
    # Indices, not identity or equality: two faces can carry equal normals
    # as distinct objects, and "remove the one I matched" by value would
    # remove the wrong one. There are four of them, so the bookkeeping is
    # cheaper than the subtlety.
    not_a_rectangle = (
        "This column's four vertical faces do not form two opposite pairs, "
        "so the section is not rectangular -- a parallelogram or a trapezoid "
        "reports four vertical faces too.")

    partner = [i for i in range(1, 4)
               if _dot2(vertical[0], vertical[i]) <= -1.0 + DIRECTION_TOL]
    if len(partner) != 1:
        return not_a_rectangle
    rest = [i for i in range(1, 4) if i != partner[0]]
    if _dot2(vertical[rest[0]], vertical[rest[1]]) > -1.0 + DIRECTION_TOL:
        return not_a_rectangle
    if abs(_dot2(vertical[0], vertical[rest[0]])) > DIRECTION_TOL:
        return (
            "This column's opposite face pairs are not perpendicular to "
            "each other, so the section is a parallelogram rather than a "
            "rectangle.")
    return None


def levels_between(base_z_mm, top_z_mm, levels,
                   tol_mm=LEVEL_COINCIDENCE_TOL_MM):
    """The levels lying STRICTLY between the two ends.

    ``levels`` is a sequence of ``(name, elevation_mm)``. The base and top
    levels themselves are excluded by the tolerance rather than by identity,
    because a column can be constrained to a level and still sit a
    hair off it in stored units.
    """
    lo = min(base_z_mm, top_z_mm)
    hi = max(base_z_mm, top_z_mm)
    return [(name, z) for name, z in levels
            if z > lo + tol_mm and z < hi - tol_mm]


def multi_storey_refusal(base_z_mm, top_z_mm, levels,
                         tol_mm=LEVEL_COINCIDENCE_TOL_MM):
    """``None`` for a single-storey column; otherwise the reason, **naming
    the levels**, per #87's brief.

    Spec §0 puts multi-storey columns out of scope (case C2). Naming the
    levels is the difference between a refusal the user can act on and one
    they have to investigate.
    """
    crossed = levels_between(base_z_mm, top_z_mm, levels, tol_mm=tol_mm)
    if not crossed:
        return None
    named = ", ".join("%s (%.0f mm)" % (name, z) for name, z in crossed)
    return (
        "This column passes through %d level(s): %s. The tool details "
        "single-storey columns only (spec section 0, case C2); split it at "
        "each level and detail the storeys separately."
        % (len(crossed), named))


def extent_from_ends(base_face_z_mm, top_face_z_mm,
                     base_level_z_mm, top_level_z_mm):
    """The vertical extent, and an honest account of where each end came
    from.

    Either face may be ``None``: #69 found **nothing** below the test
    column, and that is case C1 (a ground-floor column with no base support
    element), not a search failure. R5/R6 say to show the base datum as the
    base LEVEL elevation and say so, which is why the source travels with
    the number instead of being dropped.

    A tool that returned only the numbers would let "2700 from a soffit"
    and "3000 from a level" reach the Review report as the same claim.
    """
    base_z = base_level_z_mm if base_face_z_mm is None else base_face_z_mm
    top_z = top_level_z_mm if top_face_z_mm is None else top_face_z_mm
    if top_z <= base_z:
        raise ValueError(
            "the column's top (%.1f mm) is not above its base (%.1f mm). "
            "This is a read error, not a geometry this tool should try to "
            "detail." % (top_z, base_z))
    return ColumnExtent(
        base_z_mm=base_z,
        top_z_mm=top_z,
        clear_height_mm=top_z - base_z,
        base_source=(SOURCE_LEVEL_ELEVATION if base_face_z_mm is None
                     else SOURCE_SUPPORT_FACE),
        top_source=(SOURCE_LEVEL_ELEVATION if top_face_z_mm is None
                    else SOURCE_SUPPORT_FACE),
    )
