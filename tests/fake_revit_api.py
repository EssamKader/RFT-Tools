"""Installs minimal fake ``Autodesk.Revit.DB`` / ``Autodesk.Revit.DB.Structure``
modules into ``sys.modules`` so ``rft.revit.*`` (which imports the real
Revit API at module scope) can be imported and exercised under plain
CPython.

This is the mechanism behind the mock-object verification tests
(``test_mock_revit_adapter.py``) required by CONTEXT.md: it runs the actual
adapter source, not a re-implementation of its logic, against stand-in
Revit types.

WHAT THESE FAKES DO NOT PROVE
-----------------------------
These stand-ins are written to match the API shape the adapter *assumes*.
A passing test therefore proves the adapter's **logic** is self-consistent —
it does **not** validate that the real Revit API has those members, those
signatures, or those return types. If an assumed shape is wrong, these tests
pass and the tool still throws on its first real run.

Every fake standing in for an API whose shape is not documentation-confirmed
must carry an inline ``SHAPE UNVERIFIED`` note naming what is assumed, so a
green suite is never mistaken for API validation.

VERIFIED LIVE (issue #30, Revit 2024, ``RevitAPI 24.3.40.0`` — see issue
#23's live probe) and so REMOVED from the list below:

- ``Document.Delete(ElementId)`` and transaction rollback of a DELETE
  (issue #120, R25), on Revit 2024 build 24.3.40.26. The method exists
  and returns ``ICollection<ElementId>`` (1 id for a lone tie);
  ``rft.revit.column_placer`` discards it.

  **The semantic R25 rests on was probed separately, because deleting
  something CREATED in the same transaction proves nothing.** A
  pre-existing element (422280) was deleted inside a ``SubTransaction``
  and the transaction rolled back: rebar count 95 -> 94 -> **95**, and
  ``GetElement`` returned the element again. That is exactly what
  ``FakeDocument.Delete``/``FakeTransaction`` model, and exactly what
  makes "a failed rebuild leaves the original cage intact" true rather
  than hoped for. The document was left unchanged.

- ``RebarConstraint`` and ``RebarConstraintsManager`` (issue #119, R22)
  were enumerated by reflection on Revit 2024 build 24.3.40.26.
  ``GetRebarConstraintsManager()``, ``GetAllHandles()``,
  ``GetConstraintCandidatesForHandle(handle)``,
  ``SetPreferredConstraintForHandle(handle, constraint)``,
  ``IsToHostFaceOrCover()``, ``IsToCover()``, ``GetTargetElement()``,
  ``GetTargetHostFaceAndTransform(index, transform)`` and
  ``SetDistanceToTargetHostFace(offset)`` all exist.
  **``GetTargetElementId()`` and a ``PlanarFace`` property do not**,
  and the bar placer called both until reflection caught it -- with a
  green suite throughout, because this file had been written to match
  the invention. It is the clearest case yet for why a fake is
  evidence about the ADAPTER and never about the API.

- ``Rebar.GetCenterlineCurves(adjustForSelfIntersection, suppressHooks,
  suppressBendRadius, multiplanarOption, tolerance)`` (issue #118) -- the
  5-argument signature, the tolerance argument and
  ``MultiplanarOption.IncludeOnlyPlanarCurves`` are all confirmed on Revit
  2024 build 24.3.40.26. Called on tie 423209 in one execution:
  ``(False, False, False, ...)`` returned **11 curves including 5 arcs**
  (hooks and bend radii present) and ``(False, True, True, ...)`` returned
  **4** (suppressed). The hooks-included read returns the tails R21 was
  decided on, so the flag settings ``rft.revit.column_place_ties`` uses are
  the ones that were measured.
- ``Rebar.LookupParameter("Partition")``, ``BuiltInCategory.OST_Rebar``
  and ``Rebar.GetTypeId()`` (issue #117) -- all three were written as
  assumptions and have since been probed on Revit 2024 build 24.3.40.26
  against column 422078. ``LookupParameter("Partition")`` returns a
  writable ``String`` parameter and a ``Set`` round-trips.
  ``OfCategory(OST_Rebar)`` collects placed rebar: 99 in the document, 4
  hosted by 422078, matching what is actually there. ``GetTypeId()``
  returns the ``RebarBarType``, named ``16M`` through
  ``rft.revit.bar_types.element_name`` -- which is used instead of
  ``.Name`` because ``ElementType.Name`` is setter-only and would raise
  ``AttributeError`` live while passing against any fake defining it.

- ``RebarHostData`` does NOT expose ``GetFaces(RebarFaceType)`` /
  ``GetCoverType(face) -> ElementId`` — that whole shape, including the
  ``RebarFaceType`` enum itself, does not exist. The real shape is
  ``GetExposedFaces() -> IList<Reference>`` and
  ``GetCoverType(Reference) -> RebarCoverType`` (the ``RebarCoverType``
  object itself, not an ``ElementId`` needing a further ``doc.GetElement``
  round trip). ``FakeRebarHostData`` and every scenario-specific host-data
  stub below are now built to this shape.
- ``face.ComputeNormal(UV) -> XYZ`` and
  ``Element.GetGeometryObjectFromReference(Reference) -> Face`` both work
  live and were how the probe recovered each exposed face's normal.
- ``RebarCoverType.CoverDistance`` (internal units) is a real, readable
  property — confirmed live. ``RebarCoverType.Id``/``.Name`` are assumed to
  be the standard ``Element`` members (not specifically probed, but not a
  new assumption either).

Currently ``SHAPE UNVERIFIED``:

- ``FamilyInstance.get_Geometry() -> GeometryInstance`` for a structural
  column OR BEAM, used by the rotation-aware support-width path and, since
  issue #18's review, by the beam's own section width and centroid datum.
  The projection math is tested; the extraction step is not. If the real API
  returns already-transformed ``Solid``s instead, both datum paths fall back
  to the world AABB and the rotated-beam case regresses silently.
- ``Transform.OfPoint(XYZ) -> XYZ`` and ``Transform.BasisZ``/``Origin``,
  used to map a local bounding-box centre to world space
  (``beam_section_centre_offsets``). Assumed to be the standard affine
  mapping; not confirmed against a live host.
- ``Rebar.GetShapeDrivenAccessor() -> RebarShapeDrivenAccessor`` and
  ``RebarShapeDrivenAccessor.SetLayoutAsMaximumSpacing(spacing, arrayLength,
  barsOnNormalSide, includeFirstBar, includeLastBar)``. Assumed from
  docs/beam/research/revit-api-strategy.md's documentation-only research (issue
  #18, S5 stirrups); no live-host confirmation of the accessor's exact
  parameter order, or that `GetShapeDrivenAccessor` is even the correct
  accessor name for a `CreateFromCurves`-built stirrup (vs. a distinct
  accessor for shape-driven vs. free-form rebar).
- ``RebarStyle.StirrupTie`` and ``RebarHookType`` (angle/multiplier-bearing
  hook object passed to `Rebar.CreateFromCurves`). This fake does not and
  cannot validate real `Rebar.CreateFromCurves` acceptance behaviour; it
  only lets `rft.revit.stirrups` import and run under CPython. CONTEXT.md's
  original "does StirrupTie permit 180 deg" load-bearing unknown was
  resolved live for issue #25/#31 (A45): it is the hook's
  `REBAR_HOOK_STYLE` FAMILY that StirrupTie constrains (must be 1 =
  Stirrup/Tie), not any particular angle -- confirmed against Revit 2024.
  See the `REBAR_HOOK_STYLE` entry below for what that live probe did and
  did not confirm about the exact read-back accessor.
- ``Wall.Width`` (issue #15, S2) -- assumed to be a read-only property
  returning the wall's total thickness directly in internal units (feet).
  Not confirmed against a live host; this fake only carries whatever a
  test assigns.
- ``BuiltInCategory.OST_Walls`` / ``OST_StructuralFraming`` as valid
  ``FilteredElementCollector.OfCategory`` arguments for support detection
  (issue #15, S2) -- assumed to exist and behave like ``OST_StructuralColumns``
  already did; not newly confirmed here.
- A SECOND, independently-picked ``OST_StructuralFraming`` neighbour
  (issue #22, S9 continuous-run guard) exposing ``Location.Curve`` the same
  way the beam being detailed does. ``beam_axis_direction``/``beam_endpoints``
  already carried this assumption for the beam itself; this is the first
  place it is relied on for a second framing element, and that has not been
  confirmed against a live host either -- see
  ``rft/revit/guards.py:neighbour_axis_dot_product``.
- ``RebarBarType.BarNominalDiameter`` (issue #20, S7; more load-bearing
  since A42/ticket #27 made it the SOLE diameter source, not one side of a
  cross-check) -- assumed to be a read-only property in internal units
  carrying the catalog/nominal bar diameter. Documentation also lists
  ``BarModelDiameter`` as a plausible alternative; not confirmed against a
  live host which one every downstream mm computation should read. See
  ``rft/revit/bar_types.py``.
- ``RebarHookType.get_Parameter(BuiltInParameter.REBAR_HOOK_ANGLE)
  .AsDouble()`` (issue #25) -- VERIFIED LIVE against Revit 2024
  (``RevitAPI 24.3.40.0``, issue #25/#31 probe): returns the hook's own
  angle in RADIANS, exactly as assumed. Not a new SHAPE UNVERIFIED item
  any more; kept in this list only as a record of what was confirmed and
  when. See ``rft/revit/bar_types.py``.
- ``RebarHookType.get_Parameter(BuiltInParameter.REBAR_HOOK_STYLE)
  .AsInteger()`` (issue #25/#31, A45) -- the live probe VERIFIED that
  `BuiltInParameter.REBAR_HOOK_STYLE` distinguishes Standard (0) from
  Stirrup/Tie (1) hook families and that `RebarStyle.StirrupTie` rejects a
  Standard-family hook with an opaque `InternalException` regardless of
  angle. What the probe did NOT independently confirm is this exact
  accessor call (`get_Parameter(...).AsInteger()`) -- the 0/1 meaning was
  read from the Revit UI/API browser, not by re-probing this specific
  method. Still SHAPE UNVERIFIED on that narrower point. See
  ``rft/revit/bar_types.py``.
- ``pyrevit.forms.SelectFromList.show(items, multiselect=False,
  name_attr=..., title=..., button_name=...)`` (issue #20, S7) -- the
  explicit dropdown/list picker used to select bar and hook types. This is
  NOT faked here at all (``pyrevit`` itself is not importable in this
  environment) -- the three pushbuttons' selection helpers are therefore
  UNEXECUTED, not merely shape-unverified. See each pushbutton's own
  module docstring and docs/beam/verification/s7-grades.md.
- ``Rebar.GetCenterlineCurves(...)`` was listed here by issue #118 and has
  since been VERIFIED LIVE -- see the entry in the verified list above. The
  API is confirmed; what follows is about this FAKE, which is a different
  claim and remains true.

  **This fake's hook-tail geometry is NOT a model of Revit's real hook
  math.** Real hook placement depends on the hook type's angle, length
  multiplier and the bend radius, none of which this fake computes. What
  it DOES reproduce, deliberately, is the qualitative fact
  issue-109 Finding 4 and issue-78 measured live: for a fixed loop
  winding, ``RebarHookOrientation.Left`` on both ends turns a tail INWARD
  (toward the column's own vertical centreline) and ``Right`` turns it
  OUTWARD. It does this by offsetting each tail from its anchor point
  toward or away from ``host.Location.Point``'s (X, Y) -- a shortcut valid
  only because a column's plan centre lies on that line at every
  elevation, which is NOT how the real API computes a hook tail. A test
  built on this fake proves the ADAPTER's assertion logic is
  self-consistent (Left passes, Right/mixed fails); it does not and cannot
  prove Revit's real hooks land where this fake says they do.
- ``Rebar.SetLayoutAsNumberWithSpacing(numberOfBarPositions, spacing,
  barsOnNormalSide, includeFirstBar, includeLastBar)`` (issue #119) -- the
  ticket's own reading of published Revit API documentation. The method
  NAME is not in doubt; the parameter order is, and a wrong order here
  would place a bar set that builds and is spaced wrongly. Not live
  confirmed.
- ``Rebar.CreateFromCurves``'s ``normal`` argument for a STRAIGHT,
  unhooked bar (issue #119). ``StirrupTie`` loops were confirmed live by
  #109; a standard bar was not. R22's face pin overrides the resulting
  position either way, which is why this is recorded rather than blocking.

  The rest of #119's constraint surface is no longer on this list:
  ``GetRebarConstraintsManager``, ``GetAllHandles``,
  ``GetConstraintCandidatesForHandle``,
  ``SetPreferredConstraintForHandle``, ``IsToHostFaceOrCover``,
  ``IsToCover``, ``GetTargetElement``, ``GetTargetHostFaceAndTransform``
  and ``SetDistanceToTargetHostFace`` were all confirmed by reflection over
  the live types -- see the verified list above, and the two members that
  reflection showed do NOT exist.
- ``Document.Delete(ElementId)`` (issue #120, R23/R25) was listed here
  and has since been VERIFIED LIVE -- see the verified list above, which
  also records the rollback semantic R25 actually depends on. ``FakeDocument.Delete`` below
  additionally models something no real API call needs to: undoing itself
  on ``FakeTransaction.RollBack()``. That is not part of the real
  `Document.Delete` shape -- Revit's own transaction machinery does that
  restoration natively -- it is this FAKE's only way to let a test prove
  R25's central claim (a rolled-back delete leaves the model exactly as
  it was) without a real Revit session.
"""

import math
import sys
import types


class FakeXYZ(object):
    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.X, self.Y, self.Z = x, y, z

    def __sub__(self, other):
        return FakeXYZ(self.X - other.X, self.Y - other.Y, self.Z - other.Z)

    def __add__(self, other):
        return FakeXYZ(self.X + other.X, self.Y + other.Y, self.Z + other.Z)

    def Normalize(self):
        n = math.sqrt(self.X ** 2 + self.Y ** 2 + self.Z ** 2) or 1.0
        return FakeXYZ(self.X / n, self.Y / n, self.Z / n)

    def Multiply(self, scalar):
        return FakeXYZ(self.X * scalar, self.Y * scalar, self.Z * scalar)

    def Negate(self):
        return FakeXYZ(-self.X, -self.Y, -self.Z)

    def DotProduct(self, other):
        return self.X * other.X + self.Y * other.Y + self.Z * other.Z

    def CrossProduct(self, other):
        return FakeXYZ(
            self.Y * other.Z - self.Z * other.Y,
            self.Z * other.X - self.X * other.Z,
            self.X * other.Y - self.Y * other.X,
        )

    def __eq__(self, other):
        return (self.X, self.Y, self.Z) == (other.X, other.Y, other.Z)


FakeXYZ.BasisZ = FakeXYZ(0.0, 0.0, 1.0)
# The column adapter fires rays along +X (the view self-test) and along
# -Z (the downward support search), so both the axis constants and unary
# negation are real API surface it depends on.
FakeXYZ.BasisX = FakeXYZ(1.0, 0.0, 0.0)
FakeXYZ.BasisY = FakeXYZ(0.0, 1.0, 0.0)
FakeXYZ.__neg__ = lambda self: FakeXYZ(-self.X, -self.Y, -self.Z)


class FakeUV(object):
    """Stand-in for ``Autodesk.Revit.DB.UV``, the 2D parameter passed to
    ``Face.ComputeNormal`` (confirmed live, issue #23/#30). Only ``U``/``V``
    are exposed; ``rft.revit.host`` never reads them back, it only
    round-trips the object to a fake ``Face.ComputeNormal``."""

    def __init__(self, u=0.0, v=0.0):
        self.U, self.V = u, v


class FakeReference(object):
    """Stand-in for ``Autodesk.Revit.DB.Reference`` -- the geometric
    handle ``RebarHostData.GetExposedFaces()`` returns (confirmed live,
    issue #23). Opaque in the real API; this fake carries a ``label`` only
    for test diagnostics, never read by adapter code."""

    def __init__(self, label):
        self.label = label

    def __repr__(self):
        return "FakeReference({!r})".format(self.label)


class FakeFace(object):
    """Stand-in for the ``Face`` object
    ``Element.GetGeometryObjectFromReference(Reference)`` resolves a
    ``Reference`` into (confirmed live, issue #23). Only ``ComputeNormal``
    is exercised; the real object carries far more (area, curve loops,
    etc.) that this project has no use for."""

    def __init__(self, normal):
        self._normal = normal

    def ComputeNormal(self, _uv):
        return self._normal


class FakeRebarCoverType(object):
    """Stand-in for ``Autodesk.Revit.DB.Structure.RebarCoverType``, the
    object ``RebarHostData.GetCoverType(Reference)`` returns DIRECTLY
    (confirmed live, issue #23/#30 -- NOT an ``ElementId`` needing a
    ``doc.GetElement`` round trip, which was this project's earlier,
    now-corrected assumption). ``CoverDistance`` is confirmed live. The live model carried two
    DIFFERENT ``RebarCoverType`` elements sharing the identical ``Name``
    (``"Interior (framing, columns)"``, 38.1 mm and 40 mm) -- callers must
    compare by ``Id``, never ``Name``; this fake supports constructing two
    such distinct-id, same-name instances for exactly that test.

    **DELIBERATELY HAS NO READABLE ``.Name``** (#106), for the same reason
    ``FakeRebarBarType`` does not. ``RebarCoverType`` derives from
    ``ElementType``, which re-declares ``Name`` with a setter and no
    getter; IronPython exposes only the most-derived property, so the read
    raises ``AttributeError``.

    An earlier version of this fake set ``self.Name = name``, and its own
    docstring called that "not independently probed but not a new
    assumption either". It WAS a new assumption and it was wrong --
    ``column/v0.1.0-rc1`` died on its first live click reading exactly
    this. Verified live afterwards: ``Name`` declared by ``ElementType``,
    ``CanRead=False``, while ``SYMBOL_NAME_PARAM`` returns the identical
    string C# ``Element.Name`` gives.
    """

    _next_id = [1]

    def __init__(self, cover_distance_internal, name=None, id_value=None):
        self.CoverDistance = cover_distance_internal
        self._name = name
        if id_value is None:
            id_value = FakeRebarCoverType._next_id[0]
            FakeRebarCoverType._next_id[0] += 1
        self.Id = FakeElementId(id_value)

    def get_Parameter(self, built_in):
        if built_in is FakeBuiltInParameter.SYMBOL_NAME_PARAM:
            return FakeStringParameter(self._name)
        return None


class FakeCurve(object):
    """What ``Line.CreateBound`` returns. **Carries ``GetEndPoint(i)``,
    which is the real API**, and that is the point of this class.

    Until issue #127 this fake returned a bare tuple ``("Line", p0, p1)``.
    The column tie placer was written against that shape and unpacked real
    curves the same way, so on a live host R21's hook-tail assertion --
    the whole reason #118 exists -- died with
    ``TypeError: 'Line' object is not iterable`` before it could check
    anything. Every test passed throughout.

    Indexing is kept ONLY for the older beam tests that already read
    ``curves[0][1]``. It is not the Revit API and new code must not use
    it: a real ``Line`` is not indexable and not iterable.
    """

    def __init__(self, p0, p1):
        self._points = (p0, p1)

    def GetEndPoint(self, index):
        return self._points[index]

    #: Legacy tuple view -- see the class docstring. 0 is the tag the old
    #: tuple carried, 1 and 2 are the endpoints.
    def __getitem__(self, index):
        return ("Line", self._points[0], self._points[1])[index]

    def __repr__(self):
        return "FakeCurve(%r, %r)" % self._points


class FakeLine(object):
    @staticmethod
    def CreateBound(p0, p1):
        return FakeCurve(p0, p1)


class FakeElementId(object):
    def __init__(self, value=-1):
        self.value = value

    @property
    def IntegerValue(self):
        """What ``read_column`` puts in its result, and what a fake
        document keys on. The real member; ``value`` is this fake's own."""
        return self.value

    def __eq__(self, other):
        return isinstance(other, FakeElementId) and other.value == self.value

    def __hash__(self):
        # Defining __eq__ without __hash__ makes a class unhashable in
        # Python 3, and a fake document keyed by ElementId needs both.
        return hash(self.value)

    def __repr__(self):
        return "FakeElementId({!r})".format(self.value)


FakeElementId.InvalidElementId = FakeElementId(-1)


class FakeUnitTypeId(object):
    Millimeters = object()
    #: issue #133 -- stress, for a bar type's yield strength.
    Megapascals = object()


#: Internal units per unit, by FakeUnitTypeId member. LENGTH is 1 foot ==
#: 304.8 mm. STRESS is measured from the live model: ASTM A615M Grade 420
#: reads 128016000.0 internally, and 128016000.0 / 420 == 304800.
_INTERNAL_PER_UNIT = {
    id(FakeUnitTypeId.Millimeters): 1.0 / 304.8,
    id(FakeUnitTypeId.Megapascals): 304800.0,
}


class FakeUnitUtils(object):
    """Converts ACCORDING TO THE UNIT TYPE.

    It used to ignore the unit argument and always apply the length
    factor, which meant a yield strength in MPa came back as a length in
    millimetres and the tests could not see it (issue #133). A fake that
    accepts an argument and ignores it is the same failure as a fake that
    offers a member the API does not have.
    """

    @staticmethod
    def _factor(unit_type_id):
        try:
            return _INTERNAL_PER_UNIT[id(unit_type_id)]
        except KeyError:
            raise AssertionError(
                "FakeUnitUtils was handed a unit it does not model. Add it "
                "to _INTERNAL_PER_UNIT with the factor measured live, "
                "rather than letting it convert as a length.")

    @staticmethod
    def ConvertToInternalUnits(value, unit_type_id):
        return value * FakeUnitUtils._factor(unit_type_id)

    @staticmethod
    def ConvertFromInternalUnits(value, unit_type_id):
        return value / FakeUnitUtils._factor(unit_type_id)


class FakeTransaction(object):
    """Issue #120, R25: unlike every earlier use of this fake (the beam
    tool's own `run_in_transaction`, which never deletes anything), this
    ticket's whole point is that a ROLLED-BACK delete must leave the
    original elements in place. ``doc`` therefore needs to know which
    transaction is currently open, so `FakeDocument.Delete` can log what
    left the collector and this class can put it back on `RollBack`.

    ``doc`` may be ``None`` (every pre-#120 caller passes it that way) --
    guarded below so this remains a no-op for anything that never deletes.
    """

    def __init__(self, doc, name):
        self.doc = doc
        self.name = name
        self.started = False
        self.committed = False
        self.rolled_back = False
        #: Elements `FakeDocument.Delete` removed from the collector while
        #: THIS transaction was the active one -- put back verbatim on
        #: `RollBack`, forgotten on `Commit`.
        self.deleted_items = []

    def Start(self):
        self.started = True
        if self.doc is not None:
            self.doc._active_transaction = self

    def Commit(self):
        self.committed = True
        self.deleted_items = []
        if self.doc is not None:
            self.doc._active_transaction = None

    def RollBack(self):
        self.rolled_back = True
        FakeFilteredElementCollector._ITEMS.extend(self.deleted_items)
        self.deleted_items = []
        if self.doc is not None:
            self.doc._active_transaction = None


class FakeBuiltInCategory(object):
    OST_StructuralColumns = object()
    OST_Walls = object()
    OST_StructuralFraming = object()
    OST_Floors = object()
    OST_StructuralFoundation = object()
    OST_Levels = object()
    OST_Rebar = object()


class FakeFilteredElementCollector(object):
    """Test bodies monkeypatch ``_ITEMS`` per scenario.

    ``OfCategory`` filters ``_ITEMS`` by each item's own ``_category``
    attribute when one is set on the collector; items with no ``_category``
    attribute (the pre-#15 test bodies) match ANY category, preserving the
    original permissive behaviour those tests relied on.
    """

    _ITEMS = []

    def __init__(self, doc):
        self._doc = doc
        self._category = None

    def OfCategory(self, cat):
        self._category = cat
        return self

    def OfClass(self, _cls):
        return self

    def WhereElementIsNotElementType(self):
        return self

    def __iter__(self):
        if self._category is None:
            return iter(FakeFilteredElementCollector._ITEMS)
        return iter(
            item for item in FakeFilteredElementCollector._ITEMS
            if getattr(item, "_category", self._category) is self._category
        )


class FakeRebarHostData(object):
    """Replaced wholesale (monkeypatched) per test scenario."""

    @staticmethod
    def GetRebarHostData(_element):
        raise NotImplementedError("monkeypatch per test")


class FakeRebarStyle(object):
    Standard = object()
    StirrupTie = object()


class FakeRebarHookOrientation(object):
    Left = object()
    # #118 (R21): the column tie placer must offer Revit `Left`/`Left`
    # ONLY -- `Right` bent both 135deg hook tails out of the core, live
    # (issue #109 Finding 4, issue #78). Added here so a mutation
    # (`Left` -> `Right`) is something the fake can actually distinguish,
    # rather than a value the fake would have rejected outright.
    Right = object()


class FakeMultiplanarOption(object):
    """SHAPE UNVERIFIED -- `Autodesk.Revit.DB.Structure.MultiplanarOption`,
    an argument to `Rebar.GetCenterlineCurves` quoted in
    `docs/column/verification/issue-109-kept-write-tracer-bullet.md` from a
    live call. Only doc-quoted, never independently confirmed to exist
    with this member or spelling."""

    IncludeOnlyPlanarCurves = object()


class FakeRebarHookAngleParameter(object):
    """SHAPE UNVERIFIED -- stand-in for the ``Parameter`` object
    ``RebarHookType.get_Parameter(BuiltInParameter.REBAR_HOOK_ANGLE)`` is
    assumed to return (issue #25). Real return type/member name not
    confirmed; this only carries whatever angle a test assigns, in
    radians, matching ``AsDouble()``'s assumed unit."""

    def __init__(self, angle_deg):
        self._angle_deg = angle_deg

    def AsDouble(self):
        return math.radians(self._angle_deg)


class FakeRebarHookStyleParameter(object):
    """SHAPE UNVERIFIED -- stand-in for the ``Parameter`` object
    ``RebarHookType.get_Parameter(BuiltInParameter.REBAR_HOOK_STYLE)`` is
    assumed to return (issue #25/#31, A45). The 0/1 MEANING (0 = Standard,
    1 = Stirrup/Tie) is VERIFIED LIVE; this specific accessor
    (``AsInteger()``) is not independently re-confirmed. Carries whatever
    style int a test assigns."""

    def __init__(self, style):
        self._style = style

    def AsInteger(self):
        return self._style


class FakeStringParameter(object):
    """A ``StorageType.String`` parameter, as ``SYMBOL_NAME_PARAM`` is.

    VERIFIED LIVE (Revit 2024, ``RevitAPI 24.3.40.0``): reading an
    ``ElementType``'s ``SYMBOL_NAME_PARAM`` returns a String-storage
    parameter whose ``AsString()`` equals what C# ``Element.Name`` returns
    -- ``'10M'``, ``'Stirrup/Tie - 135 deg.'``.
    """

    def __init__(self, value):
        self._value = value

    def AsString(self):
        return self._value


class FakeRebarHookType(object):
    """SHAPE UNVERIFIED (narrowed by issue #25/#31's live probe -- see
    module header) -- stand-in for `Autodesk.Revit.DB.Structure.
    RebarHookType`. Real hook angle/style live on the Revit-side object;
    this fake only carries whatever a test assigns for assertion purposes.

    ``angle_deg=None`` simulates a hook type whose angle CANNOT be read
    back at all (``get_Parameter`` returns None for
    ``REBAR_HOOK_ANGLE``) -- issue #25's "unreadable angle" case, distinct
    from an angle that reads back and fails the 135-degree check.

    ``style=None`` (the default) simulates a hook type whose
    ``REBAR_HOOK_STYLE`` CANNOT be read back at all -- issue #25/#31's
    "unreadable style" case, which must REFUSE rather than proceed (see
    ``rft.core.grades.unreadable_hook_style_message``). Pass ``style=1``
    (``HOOK_STYLE_STIRRUP_TIE``) or ``style=0`` (``HOOK_STYLE_STANDARD``)
    to simulate a readable family.

    DELIBERATELY HAS NO ``.Name`` ATTRIBUTE, for the same reason
    ``FakeRebarBarType`` does not -- ``RebarHookType.Name`` also declares
    on ``ElementType`` and is also unreachable from IronPython. The name is
    exposed only through ``SYMBOL_NAME_PARAM``.
    """

    def __init__(self, angle_deg=None, name=None, style=None, id_value=None):
        self.angle_deg = angle_deg
        self._name = name
        self.style = style
        self.Id = id_value

    def get_Parameter(self, built_in_parameter):
        if built_in_parameter is FakeBuiltInParameter.REBAR_HOOK_STYLE:
            if self.style is None:
                return None
            return FakeRebarHookStyleParameter(self.style)
        if built_in_parameter is FakeBuiltInParameter.SYMBOL_NAME_PARAM:
            if self._name is None:
                return None
            return FakeStringParameter(self._name)
        if self.angle_deg is None:
            return None
        return FakeRebarHookAngleParameter(self.angle_deg)


class FakeRebarShapeDrivenAccessor(object):
    """``Rebar.GetShapeDrivenAccessor()``'s return value.

    ``SetLayoutAsNumberWithSpacing`` lives HERE and nowhere else --
    VERIFIED by reflection over the live ``RebarShapeDrivenAccessor``,
    which also confirmed the parameter order. ``Rebar`` itself has no
    such member. Until #130 this fake offered it on BOTH objects, so
    the bar placer called it on the ``Rebar``, passed every test, and
    died with ``AttributeError`` on the first live Apply.
    """

    def __init__(self):
        self.calls = []
        #: What the bar placer set, read by tests.
        self.layout_calls = []

    def SetLayoutAsNumberWithSpacing(self, number_of_bar_positions, spacing,
                                     bars_on_normal_side, include_first_bar,
                                     include_last_bar):
        self.layout_calls.append({
            "number_of_bar_positions": number_of_bar_positions,
            "spacing": spacing,
            "bars_on_normal_side": bars_on_normal_side,
            "include_first_bar": include_first_bar,
            "include_last_bar": include_last_bar,
        })

    def SetLayoutAsMaximumSpacing(self, spacing, array_length, bars_on_normal_side,
                                   include_first_bar, include_last_bar):
        self.calls.append(
            {
                "spacing": spacing,
                "array_length": array_length,
                "bars_on_normal_side": bars_on_normal_side,
                "include_first_bar": include_first_bar,
                "include_last_bar": include_last_bar,
            }
        )


#: How far a synthetic hook tail moves from its anchor point, toward or
#: away from the column's own vertical centreline -- see
#: `FakeRebarInstance.GetCenterlineCurves`'s docstring and the module
#: header's "This fake's hook-tail geometry is NOT a model of Revit's real
#: hook math" note. An arbitrary but generous offset: large enough that a
#: tie corner near the column's cover moves clearly outside the host's
#: bounding box when pushed outward, on every column this suite builds.
_FAKE_HOOK_TAIL_OFFSET_INTERNAL = 200.0 / 304.8
class FakeConstraintTarget(object):
    """What ``RebarConstraint.GetTargetElement()`` returns -- an Element.
    Only ``.Id`` is read, so only ``.Id`` is offered: a fake that invented
    more of the Element surface would be back to guessing.
    """

    def __init__(self, element_id):
        self.Id = element_id


class FakeRebarConstraintCandidate(object):
    """Stand-in for what
    ``RebarConstraintsManager.GetConstraintCandidatesForHandle`` returns.
    ``IsToHostFaceOrCover()``, ``IsToCover()``, ``GetTargetElement()``,
    ``GetTargetHostFaceAndTransform(index, transform)`` and
    ``SetDistanceToTargetHostFace(offset)`` are all VERIFIED to exist by
    reflection over the live ``RebarConstraint``.

    **What is NOT verified is the behaviour.** This fake returns the
    candidates a test hands it, in that order. The live column returned
    47-49 per handle in an order Revit does not document, and nothing here
    models how it decides what to offer.

    An earlier version of this fake exposed ``GetTargetElementId()`` and a
    ``PlanarFace`` property. **Neither exists on the real class**, and
    because the fake offered them the suite passed on code that could not
    run. That is the failure mode this module's header exists to prevent,
    caught only by reflecting over the live type.
    """

    def __init__(self, to_host_face_or_cover=True, to_cover=False,
                target_element_id=None, planar_face=None, label=None):
        self._to_host_face_or_cover = to_host_face_or_cover
        self._to_cover = to_cover
        self._target_element_id = target_element_id
        self._planar_face = planar_face
        self.label = label
        #: What the module under test actually called this with -- the
        #: mutation-proving surface for R22's sign rule.
        self.distance_to_target_host_face = None

    def IsToHostFaceOrCover(self):
        return self._to_host_face_or_cover

    def IsToCover(self):
        return self._to_cover

    def GetTargetElement(self):
        if self._target_element_id is None:
            return None
        return FakeConstraintTarget(self._target_element_id)

    def GetTargetHostFaceAndTransform(self, index, transform):
        return self._planar_face

    def SetDistanceToTargetHostFace(self, value):
        self.distance_to_target_host_face = value

    def __repr__(self):
        return "FakeRebarConstraintCandidate({!r})".format(self.label)


class FakeRebarHandle(object):
    """An opaque handle, as ``RebarConstraintsManager.GetAllHandles()``
    returns (verified to exist by reflection). Only carries a diagnostic
    label, which is honest rather than lazy: the module under test never
    inspects a handle, so a fake that invented fields would be asserting
    something about the real class that nobody checked."""

    def __init__(self, label):
        self.label = label

    def __repr__(self):
        return "FakeRebarHandle({!r})".format(self.label)


class FakeRebarConstraintsManager(object):
    """Stand-in for ``Rebar.GetRebarConstraintsManager()``'s return
    value; the methods used here are verified to exist by reflection. A
    test builds one with the handles/candidates a scenario needs and hands
    it to ``FakeRebar.PENDING_CONSTRAINTS_MANAGERS`` so the NEXT
    ``CreateFromCurves`` call returns it.

    Note ``IsRebarConstrainedPlacementEnabled`` is deliberately absent. It
    is a STATIC on the real class, it read ``False`` on the live host, and
    the bar snapped anyway (#92) -- so it governs nothing this adapter
    does, and a fake offering it would invite someone to reach for it.
    """

    def __init__(self, handles=None, candidates=None):
        self._handles = list(handles or [])
        #: {handle: [candidate, ...]}
        self._candidates = dict(candidates or {})
        #: {handle: candidate} -- what the module under test set, the
        #: mutation-proving surface for "removing SetPreferredConstraint
        #: ForHandle must fail a test".
        self.preferred = {}

    def GetAllHandles(self):
        return list(self._handles)

    def GetConstraintCandidatesForHandle(self, handle):
        return list(self._candidates.get(handle, []))

    def SetPreferredConstraintForHandle(self, handle, candidate):
        self.preferred[handle] = candidate


class FakeRebarInstance(object):
    """SHAPE UNVERIFIED -- stand-in for the `Rebar` element returned by
    `CreateFromCurves`. Real return type/members not confirmed; this only
    records constructor args and hands back a fresh accessor per call.

    ``GetRebarConstraintsManager()`` returns the next manager queued in
    ``FakeRebar.PENDING_CONSTRAINTS_MANAGERS`` (per-scenario, popped in
    creation order) or a fresh, empty one -- an empty manager offers no
    handles, so a test that never arms one simply exercises the "nothing to
    pin" path rather than raising.

    ``LookupParameter("Partition")`` (issue #120): a freshly-created
    element must carry the SAME writable ``Partition`` parameter
    ``FakeRebarElement`` gives an already-placed one, because R26's
    `tag_as_ours` runs on whatever `Rebar.CreateFromCurves` just returned
    -- ties from `place_ties`, bars from `place_bars` -- not on a
    separately-queried element. The parameter shape itself is the one
    `column_ownership.py`'s own docstring already records as VERIFIED LIVE
    (issue #109/#117); what is new here is only that THIS fake, and not
    only `FakeRebarElement`, now exposes it.
    """

    _next_id = [500000]

    def __init__(self, *args, **kwargs):
        self.args = args
        self.kwargs = kwargs
        self._accessor = FakeRebarShapeDrivenAccessor()
        self.Id = FakeElementId(FakeRebarInstance._next_id[0])
        FakeRebarInstance._next_id[0] += 1
        self._partition = FakeRebarPartitionParameter("")
        if FakeRebar.PENDING_CONSTRAINTS_MANAGERS:
            self._constraints_manager = \
                FakeRebar.PENDING_CONSTRAINTS_MANAGERS.pop(0)
        else:
            self._constraints_manager = FakeRebarConstraintsManager()

    def LookupParameter(self, name):
        if name == PARTITION_PARAMETER_NAME_FOR_FAKE:
            return self._partition
        return None

    def GetShapeDrivenAccessor(self):
        return self._accessor

    def GetCenterlineCurves(self, adjust_for_self_intersection, suppress_hooks,
                            suppress_bend_radius, multiplanar_option, tolerance):
        """SHAPE UNVERIFIED -- see tests/fake_revit_api.py's module header
        for the full caveat. Reproduces only the qualitative fact issue-109
        Finding 4 / issue-78 measured live: with hooks included
        (`suppress_hooks=False`), `RebarHookOrientation.Left` moves a tail
        toward the host's own `Location.Point` (X, Y) -- inward, toward the
        column's vertical centreline -- and `Right` moves it away.

        Positional args below mirror exactly what
        `rft.revit.column_place_ties._place_one_tie` passes to
        `Rebar.CreateFromCurves`: `args[5]` is `host`, `args[6]` is `norm`,
        `args[7]` is `curves`, `args[8]`/`args[9]` are the start/end
        `RebarHookOrientation`. A caller passing a differently-shaped call
        gets a wrong answer from this fake, not a loud failure -- this is
        exactly the kind of coupling `SHAPE UNVERIFIED` exists to flag.
        """
        curves = list(self.args[7])
        if suppress_hooks or not curves:
            return curves

        host = self.args[5]
        centre = host.Location.Point
        orient_start, orient_end = self.args[8], self.args[9]

        def tail(anchor, orientation):
            direction = FakeXYZ(centre.X - anchor.X, centre.Y - anchor.Y, 0.0)
            if direction.X == 0.0 and direction.Y == 0.0:
                direction = FakeXYZ(1.0, 0.0, 0.0)
            direction = direction.Normalize()
            sign = 1.0 if orientation is FakeRebarHookOrientation.Left else -1.0
            return anchor + direction.Multiply(sign * _FAKE_HOOK_TAIL_OFFSET_INTERNAL)

        start_anchor = curves[0].GetEndPoint(0)
        end_anchor = curves[-1].GetEndPoint(1)
        start_hook = FakeLine.CreateBound(tail(start_anchor, orient_start), start_anchor)
        end_hook = FakeLine.CreateBound(end_anchor, tail(end_anchor, orient_end))
        # A .NET-shaped list, not a Python one: the adapter reads this
        # back and must meet the same indexing rules the real
        # `GetCenterlineCurves` imposes (PR #129).
        return FakeGenericList([start_hook] + list(curves) + [end_hook])
    def GetRebarConstraintsManager(self):
        return self._constraints_manager

    #: NOT SetLayoutAsNumberWithSpacing -- that is on the shape driven
    #: accessor. Offering it here too is what let #130 reach a host.
    @property
    def layout_calls(self):
        return self._accessor.layout_calls


class FakeRebar(object):
    #: Popped in creation order by ``FakeRebarInstance.__init__`` -- see
    #: its docstring. A test arms this before calling ``place_bars``.
    PENDING_CONSTRAINTS_MANAGERS = []

    @staticmethod
    def CreateFromCurves(*args, **kwargs):
        return FakeRebarInstance(*args, **kwargs)


class FakeRebarPartitionParameter(object):
    """SHAPE UNVERIFIED -- stand-in for the ``Parameter`` object
    ``Rebar.LookupParameter("Partition")`` is assumed to return (issue
    #117/R26). The parameter's NAME, storage type and empty default ARE
    confirmed live; this accessor is not. Writable, unlike every other
    parameter fake in this module -- R26 is specifically about a value
    THIS TOOL writes, not one it only reads.
    """

    def __init__(self, value=""):
        self._value = value

    def AsString(self):
        return self._value

    def Set(self, value):
        self._value = value


class FakeRebarElement(object):
    """SHAPE UNVERIFIED except where noted -- stand-in for a placed
    ``Rebar`` element already sitting in a host, as ``column_ownership``
    reads (and tags) one (issue #117).

    ``GetHostId()`` and ``Quantity`` are VERIFIED LIVE (issue #109,
    ``issue-109-kept-write-tracer-bullet.md``): a closed tie built against
    a column reported ``GetHostId() == 422078`` (the host's own id) and
    ``Quantity == 1``. ``GetTypeId()`` and reaching ``Partition`` through
    ``LookupParameter`` are NOT independently confirmed -- see this
    module's header.
    """

    def __init__(self, host_id, id_value, bar_type_id=None, quantity=1,
                partition=""):
        self.Id = FakeElementId(id_value)
        self._host_id = host_id
        self.Quantity = quantity
        self._bar_type_id = bar_type_id
        self._partition = FakeRebarPartitionParameter(partition)
        self._category = FakeBuiltInCategory.OST_Rebar

    def GetHostId(self):
        return self._host_id

    def GetTypeId(self):
        return self._bar_type_id

    def LookupParameter(self, name):
        if name == PARTITION_PARAMETER_NAME_FOR_FAKE:
            return self._partition
        return None


#: Kept as a module-level constant, deliberately NOT imported from
#: ``rft.revit.column_ownership`` -- this fake must recognise the parameter
#: name the way the real Revit API would (by the literal string "Partition"
#: the ticket confirmed live), not by sharing the adapter's own constant.
#: Sharing it would let a typo in BOTH places cancel out and still pass.
PARTITION_PARAMETER_NAME_FOR_FAKE = "Partition"


class FakeRebarBarType(object):
    """SHAPE UNVERIFIED -- ``BarNominalDiameter`` (issue #20, S7). See
    tests/fake_revit_api.py header.

    DELIBERATELY HAS NO ``.Name`` ATTRIBUTE. The real
    ``RebarBarType.Name`` is inaccessible from pyRevit's IronPython 2.7
    engine -- ``Name``'s declaring type is ``ElementType``, which hides
    ``Element.Name``, and IronPython's binder does not expose a property
    shadowed that way (``AttributeError: 'RebarBarType' object has no
    attribute 'Name'``, live, v0.1.0-rc3). An earlier version of this fake
    set ``self.Name = name``, which is exactly why the test suite could
    not see that failure coming: the fake modelled an attribute the real
    language binding does not provide. The name is reachable here only the
    way it is reachable live -- through ``SYMBOL_NAME_PARAM``.
    """

    def __init__(self, bar_nominal_diameter=None, name=None, id_value=None,
                 material_id=None):
        self.BarNominalDiameter = bar_nominal_diameter
        self._name = name
        self.Id = id_value
        #: issue #133. ``None`` models a type with NO material assigned --
        #: which is not hypothetical: 10T and 14T are like that in the
        #: verification model, and their yield strength is unknown to
        #: Revit itself.
        self._material_id = material_id

    def get_Parameter(self, built_in_parameter):
        if built_in_parameter is FakeBuiltInParameter.SYMBOL_NAME_PARAM:
            if self._name is None:
                return None
            return FakeStringParameter(self._name)
        if built_in_parameter is FakeBuiltInParameter.MATERIAL_ID_PARAM:
            if self._material_id is None:
                return None
            return FakeElementIdParameter(self._material_id)
        return None


class FakeStructuralAsset(object):
    """``PropertySetElement.GetStructuralAsset()``'s return value.

    Only ``MinimumYieldStress`` is modelled, in INTERNAL units, because
    that is the only member the adapter reads and inventing more of the
    asset surface would be guessing (issue #133).
    """

    def __init__(self, minimum_yield_stress):
        self.MinimumYieldStress = minimum_yield_stress


class FakePropertySetElement(object):
    """What ``Material.StructuralAssetId`` resolves to."""

    def __init__(self, asset):
        self._asset = asset

    def GetStructuralAsset(self):
        return self._asset


class FakeMaterial(object):
    """A structural material. ``StructuralAssetId`` may be ``None``: a
    material with no structural asset is as real as a bar type with no
    material, and both end at "fy unknown"."""

    def __init__(self, structural_asset_id=None, name="Fake Material"):
        self.StructuralAssetId = structural_asset_id
        self.Name = name


class FakeBuiltInParameter(object):
    """SHAPE UNVERIFIED -- ``REBAR_HOOK_ANGLE`` (issue #25) is verified
    live to return radians; ``REBAR_HOOK_STYLE`` (issue #25/#31, A45) is
    verified live for its 0/1 meaning but not this exact accessor. See
    tests/fake_revit_api.py header."""

    REBAR_HOOK_ANGLE = object()
    REBAR_HOOK_STYLE = object()
    # VERIFIED LIVE (Revit 2024): holds an ElementType's name as a
    # StorageType.String parameter, for both RebarBarType and
    # RebarHookType -- the only route to a name from IronPython, since
    # ``.Name`` is hidden behind ElementType (see FakeRebarBarType).
    SYMBOL_NAME_PARAM = object()
    # VERIFIED LIVE (issue #133): a RebarBarType's Material, the first
    # link in the chain to its yield strength.
    MATERIAL_ID_PARAM = object()
    # The column adapter's reads (#106). Each is exercised live.
    CLEAR_COVER_OTHER = object()
    CLEAR_COVER_TOP = object()
    FAMILY_BASE_LEVEL_PARAM = object()
    FAMILY_TOP_LEVEL_PARAM = object()
    FAMILY_BASE_LEVEL_OFFSET_PARAM = object()
    FAMILY_TOP_LEVEL_OFFSET_PARAM = object()


class FakeOptions(object):
    pass


class FakeWall(object):
    """SHAPE UNVERIFIED -- stand-in for `Autodesk.Revit.DB.Wall`, used only
    so ``isinstance(support, Wall)`` (rft.revit.geometry.
    support_width_along_axis_mm, issue #15/S2) can be exercised under
    CPython. Real wall subclassing/`Width` semantics not confirmed -- see
    tests/fake_revit_api.py header."""

    def __init__(self, width_internal, id_value=None, location=None):
        self.Width = width_internal
        self.Id = id_value
        self.Location = location

    def get_BoundingBox(self, _view):
        return None


class FakeGeometryElement(object):
    """Stand-in for `Autodesk.Revit.DB.GeometryElement`.

    VERIFIED LIVE (Revit 2024): this -- NOT ``GeometryInstance`` -- is
    where ``GetBoundingBox()`` is declared, confirmed by reflection on the
    live assembly.
    """

    def __init__(self, bbox=None):
        self._bbox = bbox

    def GetBoundingBox(self):
        return self._bbox


class FakeGeometryInstance(object):
    """Stand-in for `Autodesk.Revit.DB.GeometryInstance`.

    DELIBERATELY HAS NO ``GetBoundingBox()``. The real class does not
    declare one -- verified live by reflection, its entire public surface
    being GetSymbolGeometry / GetInstanceGeometry / Transform /
    GetSymbolGeometryId / GetDocument -- and an earlier version of this
    fake DID offer ``GetBoundingBox()``, which is why the test suite could
    not see the failure coming. v0.1.0-rc4 raised
    ``AttributeError: 'GeometryInstance' object has no attribute
    'GetBoundingBox'`` on the live host while these tests were green.

    That is the third time a fake modelled something the real API does not
    provide (after ``RebarFaceType`` in issue #23 and ``.Name`` on an
    ``ElementType`` in v0.1.0-rc3), so the shape is mirrored exactly now:
    the local bbox is reachable only through ``GetSymbolGeometry()``, as it
    is live.

    ``local_bbox`` is kept as the constructor argument so existing tests
    read unchanged -- they never called ``GetBoundingBox()`` directly, so
    they now exercise the real two-step path for free.

    VERIFIED LIVE for the values it stands in for: on both the 0-degree and
    45-degree 300x900 beams, ``GetSymbolGeometry().GetBoundingBox()``
    measures 9000 x 300 x 900 mm -- identical regardless of rotation --
    while ``Transform.BasisX`` differs, (1, 0, 0) versus (0.7071, 0.7071, 0).
    """

    def __init__(self, local_bbox=None, transform=None):
        self._symbol_geometry = FakeGeometryElement(local_bbox)
        self.Transform = transform

    def GetSymbolGeometry(self):
        return self._symbol_geometry

    def GetInstanceGeometry(self):
        """Present because the real class has it, and raising here states
        the contract: this returns WORLD-space geometry, so using it for
        the local bbox would reintroduce the rotation error that
        ``_rotation_aware_local_bbox`` exists to avoid.
        """
        raise AssertionError(
            "GetInstanceGeometry returns world-space geometry -- "
            "_rotation_aware_local_bbox must use GetSymbolGeometry"
        )


# ===================================================================== #
# The column adapter (#106)
#
# Every shape below is either verified live in this session or carries a
# SHAPE UNVERIFIED note. The two that cost a release candidate each are
# the ones with no readable ``.Name`` and the one whose ``Location.Point``
# reports Z = 0 whatever storey it stands on.
# ===================================================================== #


class FakeGenericList(object):
    """``System.Collections.Generic.List[T]``, as IronPython sees it.

    ``DB.List[DB.BuiltInCategory]`` does NOT exist -- an earlier version of
    the adapter tried it and failed. The real import is
    ``from System.Collections.Generic import List``, and the subscript
    returns a constructible type.

    **Negative indices raise here, because they raise on a real .NET
    list.** ``curves[-1]`` is ordinary Python and is an error on any
    ``IList<T>``: IronPython surfaces it as
    ``ValueError: Index was out of range ... Parameter name: index``.
    PR #129 fixed exactly that, after it shipped to a live host, because this fake
    delegated to a Python list and answered happily. A fake that is more
    permissive than the API is not a safe fake -- it is a fake that
    certifies code the API will reject.
    """

    def __init__(self, items=None):
        self._items = list(items or [])

    def __class_getitem__(cls, _item_type):
        return cls

    def __getitem__(self, index):
        if index < 0:
            raise IndexError(
                "negative index %d: a .NET IList<T> has no negative "
                "indexing and raises 'Index was out of range'. Use "
                "len(x) - 1. See PR #129." % index)
        return self._items[index]

    def Add(self, item):
        self._items.append(item)

    def __iter__(self):
        return iter(self._items)

    def __len__(self):
        return len(self._items)


class FakeBoundingBox(object):
    """``get_BoundingBox(None)`` -- the column's own vertical extent.

    The ONLY trustworthy source for where a column is vertically. See
    ``FakeColumnLocation``.
    """

    def __init__(self, min_xyz, max_xyz):
        self.Min = min_xyz
        self.Max = max_xyz


class FakeColumnLocation(object):
    """``LocationPoint``. **Z is 0 whatever storey the column stands on.**

    VERIFIED LIVE (#107), on four columns in the test model::

        421967  Zspan    0..3000   Location.Point.Z = 0
        422078  Zspan 3000..6000   Location.Point.Z = 0   <-- upper storey
        422316  Zspan    0..3000   Location.Point.Z = 0
        422840  Zspan 3000..6000   Location.Point.Z = 0   <-- upper storey

    This fake reproduces that deliberately: a fake that put the real
    elevation here would let a ray built from ``Location.Point.Z`` pass
    every test and still fire at the project base on a host.
    """

    def __init__(self, point):
        self.Point = point


class FakeFamily(object):
    """``Family``. Its ``Name`` IS readable -- declared by ``Element``.

    VERIFIED LIVE: ``Name`` decl=``Element``, ``CanRead=True``, returning
    ``"M_Concrete-Rectangular-Column"``. Its ``SYMBOL_NAME_PARAM`` exists
    but is EMPTY, which is why the adapter must NOT route it through
    ``element_name`` -- doing so degrades a working name to a placeholder.
    That mistake was made and reverted while fixing #105.
    """

    _next_id = [9000]

    def __init__(self, name):
        self.Name = name
        self.Id = FakeElementId(FakeFamily._next_id[0])
        FakeFamily._next_id[0] += 1

    def get_Parameter(self, built_in):
        if built_in is FakeBuiltInParameter.SYMBOL_NAME_PARAM:
            return FakeStringParameter("")     # present, and empty
        return None


class FakeFamilySymbol(object):
    """``FamilySymbol``. **NO READABLE ``.Name``** -- an ``ElementType``.

    VERIFIED LIVE: ``Name`` decl=``ElementType``, ``CanRead=False``, while
    ``Element.Name`` in C# reads ``"450 x 600mm"`` and
    ``SYMBOL_NAME_PARAM`` returns the identical string.

    ``Id`` (issue #153): every ``Element`` has one, the same base-class
    member this fake already relies on for ``FakeFamily``, ``FakeColumn``
    and ``FakeRebarCoverType`` -- not a new assumption, just the first place
    a ``FamilySymbol``'s own id is read (batch collection compares
    candidates' ``Symbol.Id`` to the picked column's).
    """

    _next_id = [7000]

    def __init__(self, name, family_name="M_Concrete-Rectangular-Column",
                 parameters=None, id_value=None):
        self._name = name
        self.Family = FakeFamily(family_name)
        self._parameters = dict(parameters or {})
        if id_value is None:
            id_value = FakeFamilySymbol._next_id[0]
            FakeFamilySymbol._next_id[0] += 1
        self.Id = FakeElementId(id_value)

    def get_Parameter(self, built_in):
        if built_in is FakeBuiltInParameter.SYMBOL_NAME_PARAM:
            return FakeStringParameter(self._name)
        return None

    def LookupParameter(self, name):
        if name not in self._parameters:
            return None
        return FakeDoubleParameter(self._parameters[name])


class FakeDoubleParameter(object):
    def __init__(self, value):
        self._value = value

    def AsDouble(self):
        return self._value


class FakeElementIdParameter(object):
    """A parameter holding an ``ElementId`` -- covers, levels, offsets."""

    def __init__(self, element_id):
        self._element_id = element_id

    def AsElementId(self):
        return self._element_id

    def AsDouble(self):
        return 0.0


class FakeLevel(object):
    """``Level``. ``Name`` readable -- declared by ``Element`` (verified
    live: ``CanRead=True``, ``"Level 1"``)."""

    def __init__(self, name, elevation_internal):
        self.Name = name
        self.Elevation = elevation_internal
        self._category = FakeBuiltInCategory.OST_Levels


class FakeView3D(object):
    """``View3D``. ``Name`` readable -- declared by ``Element``.

    ``IsTemplate`` is what the adapter filters on. Whether the view can
    actually SEE anything is not a property -- it is decided by firing a
    ray, which is what ``FakeReferenceIntersector`` models.
    """

    def __init__(self, name, is_template=False, blind=False):
        self.Name = name
        self.IsTemplate = is_template
        #: Not a Revit member. Drives FakeReferenceIntersector so a test
        #: can build the `Analytical Model` case -- a view whose settings
        #: are identical and which returns nothing.
        self.blind = blind


class FakeSolid(object):
    def __init__(self, faces, volume=1.0):
        self.Faces = list(faces)
        self.Volume = volume


class FakeTransform(object):
    """Only ``Transform.Identity`` is used -- it is passed to
    ``GetTargetHostFaceAndTransform`` as the transform to fill in, and this
    module never reads it back. VERIFIED to exist on the live API.
    """

    Identity = None


FakeTransform.Identity = FakeTransform()


class FakePlanarFace(object):
    def __init__(self, normal):
        self.FaceNormal = normal


class FakeCurvedFace(object):
    """Anything that is not a ``PlanarFace``. The adapter counts these."""

    def __init__(self):
        self.FaceNormal = None


class FakeViewDetailLevel(object):
    Fine = object()


class FakeFindReferenceTarget(object):
    Element = object()


class FakeElementCategoryFilter(object):
    def __init__(self, category):
        self.category = category


class FakeElementMulticategoryFilter(object):
    def __init__(self, categories):
        self.categories = list(categories)


class FakeReferenceWithContext(object):
    """What ``ReferenceIntersector.Find`` returns per hit."""

    def __init__(self, element_id, global_z):
        self._reference = FakeHitReference(element_id, global_z)

    def GetReference(self):
        return self._reference


class FakeHitReference(object):
    def __init__(self, element_id, global_z):
        self.ElementId = element_id
        self.GlobalPoint = FakeXYZ(0.0, 0.0, global_z)


class FakeReferenceIntersector(object):
    """``ReferenceIntersector``, driven by a per-test scenario.

    The real object's answer depends on the VIEW, which is the finding
    #69 rested on and #107 nearly foundered on: two 3D views with identical
    ``GetCategoryHidden``, ``ViewTemplateId`` and ``IsSectionBoxActive``
    return different results. There is no property to inspect, so the
    adapter fires a ray -- and this fake models exactly that.

    ``HITS`` is a list of ``(predicate, hits)``. The first predicate that
    accepts ``(view, origin, direction)`` supplies the hits. A blind view
    always yields nothing, whatever the ray.
    """

    HITS = []

    def __init__(self, element_filter, target, view):
        self.filter = element_filter
        self.target = target
        self.view = view
        self.FindReferencesInRevitLinks = True

    def _hits(self, origin, direction):
        if getattr(self.view, "blind", False):
            return []
        for predicate, hits in FakeReferenceIntersector.HITS:
            result = predicate(self.view, origin, direction)
            if result is not None:
                return result
        return []

    def Find(self, origin, direction):
        return self._hits(origin, direction)

    def FindNearest(self, origin, direction):
        hits = self._hits(origin, direction)
        return hits[0] if hits else None


class FakeColumn(object):
    """A structural column, as the adapter reads one.

    Defaults are the live 450 x 600 on Level 2 that this session detailed:
    unflipped, axis-aligned, spanning 3000-6000 mm, with its
    ``Location.Point.Z`` at 0 exactly as the real one reports.
    """

    def __init__(self, document=None, symbol=None, solid=None,
                 base_z_internal=0.0, top_z_internal=3000.0 / 304.8,
                 mirrored=False, hand_flipped=False, facing_flipped=False,
                 parameters=None, element_id=421967, bounding_box=True):
        self.Document = document
        self.Symbol = symbol if symbol is not None else FakeFamilySymbol(
            "450 x 600mm",
            parameters={"b": 450.0 / 304.8, "h": 600.0 / 304.8})
        self.Id = FakeElementId(element_id)
        self.Mirrored = mirrored
        self.HandFlipped = hand_flipped
        self.FacingFlipped = facing_flipped
        self.HandOrientation = FakeXYZ(1.0, 0.0, 0.0)
        self.FacingOrientation = FakeXYZ(0.0, 1.0, 0.0)
        # Z = 0 on purpose. See FakeColumnLocation.
        self.Location = FakeColumnLocation(FakeXYZ(0.0, 0.0, 0.0))
        self._solid = solid
        self._box = FakeBoundingBox(
            FakeXYZ(-0.75, -0.75, base_z_internal),
            FakeXYZ(0.75, 0.75, top_z_internal)) if bounding_box else None
        self._parameters = dict(parameters or {})
        self._category = FakeBuiltInCategory.OST_StructuralColumns

    def get_BoundingBox(self, _view):
        return self._box

    def get_Geometry(self, _options):
        return [] if self._solid is None else [self._solid]

    def get_Parameter(self, built_in):
        return self._parameters.get(built_in)


class FakeDocument(object):
    """``GetElement`` plus, since issue #120 (R23/R25), ``Delete`` --
    collectors read the module-level ``_ITEMS``, and that is what
    ``Delete`` mutates."""

    def __init__(self, elements=None):
        self._elements = dict(elements or {})
        #: Set by ``FakeTransaction.Start()``; ``None`` outside any
        #: transaction. Lets ``Delete`` log what it removed so a rollback
        #: can restore it -- see ``FakeTransaction``'s own docstring.
        self._active_transaction = None
        #: Every id ever handed to ``Delete``, committed or not -- purely
        #: a diagnostic a test can inspect; the adapter never reads this.
        self.deleted_ids = []

    def GetElement(self, element_id):
        if element_id is None:
            return None
        return self._elements.get(getattr(element_id, "IntegerValue",
                                          element_id))

    def Delete(self, element_id):
        """SHAPE UNVERIFIED -- see this module's header. Removes the
        matching element from ``FakeFilteredElementCollector._ITEMS`` (the
        list every ``hosted_rebar`` query reads) and, if a transaction is
        currently open, remembers it so ``FakeTransaction.RollBack`` can
        put it back -- R25's guarantee that a failed rebuild leaves the
        original cage intact cannot be tested any other way.
        """
        self.deleted_ids.append(element_id)
        items = FakeFilteredElementCollector._ITEMS
        removed = [item for item in items if item.Id == element_id]
        for item in removed:
            items.remove(item)
        if self._active_transaction is not None:
            self._active_transaction.deleted_items.extend(removed)
        return [element_id]


def install():
    db = types.ModuleType("Autodesk.Revit.DB")
    structure = types.ModuleType("Autodesk.Revit.DB.Structure")
    revit_pkg = types.ModuleType("Autodesk.Revit")
    autodesk_pkg = types.ModuleType("Autodesk")

    db.XYZ = FakeXYZ
    db.UV = FakeUV
    db.Line = FakeLine
    db.Curve = object
    db.ElementId = FakeElementId
    db.UnitTypeId = FakeUnitTypeId
    db.UnitUtils = FakeUnitUtils
    db.Transaction = FakeTransaction
    db.BuiltInCategory = FakeBuiltInCategory
    db.FilteredElementCollector = FakeFilteredElementCollector
    db.Options = FakeOptions
    db.GeometryInstance = FakeGeometryInstance
    db.Wall = FakeWall
    db.BuiltInParameter = FakeBuiltInParameter
    db.Structure = structure

    structure.RebarHostData = FakeRebarHostData
    structure.RebarStyle = FakeRebarStyle
    structure.RebarHookOrientation = FakeRebarHookOrientation
    structure.MultiplanarOption = FakeMultiplanarOption
    structure.Rebar = FakeRebar
    structure.RebarBarType = FakeRebarBarType
    structure.RebarHookType = FakeRebarHookType

    # The column adapter (#106)
    db.Level = FakeLevel
    db.View3D = FakeView3D
    db.View = FakeView3D
    db.Solid = FakeSolid
    db.PlanarFace = FakePlanarFace
    db.Transform = FakeTransform
    db.ViewDetailLevel = FakeViewDetailLevel
    db.FindReferenceTarget = FakeFindReferenceTarget
    db.ElementCategoryFilter = FakeElementCategoryFilter
    db.ElementMulticategoryFilter = FakeElementMulticategoryFilter
    db.ReferenceIntersector = FakeReferenceIntersector
    db.FamilyInstance = FakeColumn
    db.FamilySymbol = FakeFamilySymbol
    db.Family = FakeFamily
    structure.RebarCoverType = FakeRebarCoverType

    generic = types.ModuleType("System.Collections.Generic")
    collections_pkg = types.ModuleType("System.Collections")
    system_pkg = types.ModuleType("System")
    generic.List = FakeGenericList
    collections_pkg.Generic = generic
    system_pkg.Collections = collections_pkg
    sys.modules["System"] = system_pkg
    sys.modules["System.Collections"] = collections_pkg
    sys.modules["System.Collections.Generic"] = generic

    revit_pkg.DB = db
    autodesk_pkg.Revit = revit_pkg

    sys.modules["Autodesk"] = autodesk_pkg
    sys.modules["Autodesk.Revit"] = revit_pkg
    sys.modules["Autodesk.Revit.DB"] = db
    sys.modules["Autodesk.Revit.DB.Structure"] = structure
