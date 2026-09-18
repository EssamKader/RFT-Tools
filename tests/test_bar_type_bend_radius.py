# -*- coding: utf-8 -*-
"""#176 -- the bend radius R40 has always called for, and nobody read.

`rft.core.column_roof.fillet_loss_mm` has said since R40 that the radius
"comes from the BAR TYPE, never from a typed input". Nothing read it:
every other test passes a number in. The second window is the first
caller that has to obtain one, and CONTEXT.md forbids guessing an API
name.

**The obvious reading is wrong**, and these rows are why. They are the
LIVE MEASUREMENT (Revit 2024 build 24.3.40.26, document
``ColumnRFT.Trail``): a bent bar was built per type inside a rolled-back
sub-transaction and its arc read back off ``GetCenterlineCurves``. For a
90-degree bend the arc is ``r * pi / 2``, so the arc gives the radius.

Reproducing the measured arcs is what this file tests. A formula that
merely looks plausible cannot pass it.
"""

import math

import pytest

from fake_revit_api import FakeRebarBarType

from rft.revit.bar_types import (
    bar_type_centreline_bend_radius_mm, bar_type_diameter_mm,
)


def _mm(value):
    """The bar types below are built in millimetres already, so the
    conversion the adapter takes is the identity here. The conversion
    itself is `rft.revit.units`' business and is tested there."""
    return value


#: name, BarNominalDiameter, StandardBendDiameter, StirrupTieBendDiameter,
#: and the ARC MEASURED on the live host.
MEASURED = (
    ("13M", 12.70, 80.00, 50.00, 72.806),
    ("19M", 19.10, 115.00, 115.00, 105.322),
    ("12T", 12.00, 72.00, 155.00, 65.973),
    ("16T", 16.00, 96.00, 155.00, 87.965),
)


def _bar_type(row):
    _, nominal, standard, stirrup, _arc = row
    return FakeRebarBarType(
        bar_nominal_diameter=nominal, name=row[0],
        standard_bend_diameter=standard,
        stirrup_tie_bend_diameter=stirrup)


@pytest.mark.parametrize("row", MEASURED, ids=[r[0] for r in MEASURED])
def test_the_radius_REPRODUCES_the_arc_measured_on_the_live_host(row):
    """The whole point. The arc of a 90-degree bend is ``r * pi / 2``, so
    a correct radius reproduces the number Revit actually built."""
    name, _nominal, _standard, _stirrup, measured_arc_mm = row
    radius = bar_type_centreline_bend_radius_mm(_bar_type(row), _mm)
    assert radius * math.pi / 2.0 == pytest.approx(measured_arc_mm, abs=0.01), (
        "%s: a radius of %.3f mm implies a %.3f mm arc, but the live host "
        "built %.3f mm" % (name, radius, radius * math.pi / 2.0,
                           measured_arc_mm))


@pytest.mark.parametrize("row", MEASURED, ids=[r[0] for r in MEASURED])
def test_HALF_the_standard_bend_diameter_is_NOT_the_radius(row):
    """The reading a careful person would reach for first, and it is
    wrong by half a bar diameter every time.

    ``StandardBendDiameter`` is measured to the bar's INNER face; the
    centreline runs half a bar outside it. For 13M that is 40.00 against
    the measured 46.35 -- a 13.7% error in the fillet loss, which is
    SUBTRACTED from the development length the report certifies. So this
    is not a rounding matter: it makes the tool overstate what it built.
    """
    name, nominal, standard, _stirrup, measured_arc_mm = row
    naive = standard / 2.0
    assert naive * math.pi / 2.0 != pytest.approx(measured_arc_mm, abs=0.01)
    correct = bar_type_centreline_bend_radius_mm(_bar_type(row), _mm)
    assert correct - naive == pytest.approx(nominal / 2.0, abs=1e-9), (
        "%s: the difference must be exactly half a bar diameter" % name)


def test_the_STIRRUP_bend_diameter_is_ruled_out_by_12T_and_16T():
    """12T and 16T read 155.00 for ``StirrupTieBendDiameter`` while
    measuring 42.00 and 56.00 -- which is what makes the choice a
    measurement rather than a preference. 13M alone could not settle it.
    """
    for row in MEASURED:
        name, nominal, _standard, stirrup, _arc = row
        if name not in ("12T", "16T"):
            continue
        radius = bar_type_centreline_bend_radius_mm(_bar_type(row), _mm)
        assert radius != pytest.approx((stirrup + nominal) / 2.0, abs=0.01)


def test_the_bend_radius_is_NOT_the_bar_diameter_reader_under_another_name():
    """Guards a refactor that quietly points one at the other: they read
    different members and must keep answering differently."""
    row = MEASURED[0]
    bar_type = _bar_type(row)
    assert (bar_type_centreline_bend_radius_mm(bar_type, _mm)
            != pytest.approx(bar_type_diameter_mm(bar_type, _mm)))


def test_13M_reproduces_the_INDEPENDENTLY_measured_arc_from_issue_161():
    """#161 read 72.8 mm off a 13M bar months before this measurement, on
    a different probe and for a different question. Two independent
    readings agreeing is what made #161's slab read trustworthy, and the
    same standard applies here."""
    radius = bar_type_centreline_bend_radius_mm(_bar_type(MEASURED[0]), _mm)
    assert radius * math.pi / 2.0 == pytest.approx(72.8, abs=0.05)
