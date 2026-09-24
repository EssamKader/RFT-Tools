# -*- coding: utf-8 -*-
"""Issue #226 -- specs/isolated-footing-batch.md: running the isolated
footing tool over every footing+column type pair matching the picked
footing, instead of one.

THE ADAPTER for the batch. Grouping is ``rft.core.footing_batch``'s
(pure); this module does only the Revit-touching parts the spec's
Sections 1, 2, 4 and 5 add on top of the single-footing path:

    1. collect every ``OST_StructuralFoundation`` instance of the SAME
       family TYPE as the picked footing (Sec 2) -- the footing type is
       part of the filter a person selects with, never the grouping key;
    2. for each, auto-detect its own column (#220) and exclude it (before
       any transaction) if #220 refuses OR the detected column is a
       DIFFERENT family type than the picked footing's own column (Sec 2
       -- new logic this ticket adds; #220 alone has no concept of "wrong
       column type"), with the reason kept (Sec 5);
    3. read each survivor's own live geometry (#228) and column section
       (#221) -- excluding whatever either refuses, same as step 2;
    4. group the survivors by ``rft.core.footing_batch.group_hosts`` --
       the computed live-read tuple, never a second derivation (Sec 3,
       R9);
    5. plan each survivor with the SAME ``rft.core.footing_plan.
       build_footing_plan`` the single-footing script calls, off the SAME
       shared inputs -- excluding whatever ``ValueError``/
       ``DowelArrayLayoutError`` it raises (Sec 5), same report;
    6. read what each survivor's host ALREADY holds -- once, before any
       dialog and before any transaction, via ``footing_ownership.
       partition_host_rebar`` -- so the replacement count and the
       elements apply deletes are the same query (Sec 6);
    7. place every remaining candidate (bottom mesh + full dowel array)
       inside ONE transaction, all-or-nothing (Sec 5) -- refusing the
       whole run rather than opening an empty transaction if nothing
       survived.

Nothing here re-derives a detailing rule: every ``FootingPlan`` is built
by the exact function the single-footing script already calls, so a batch
and a single run cannot compute two different plans for the same host.
Mirrors ``rft.revit.column_batch`` in SHAPE, not by importing it --
element isolation (`IsolatedFooting.extension/CONTEXT.md`) keeps this
tool's own batch adapter self-contained rather than cross-coupling two
elements' Revit adapters for what is, underneath, the same orchestration
pattern with different placement calls.
"""

from collections import namedtuple

from Autodesk.Revit import DB
from Autodesk.Revit.DB import Transaction

from ..core.footing_batch import BatchExisting, Exclusion, group_hosts
from ..core.footing_plan import FootingInputs, build_footing_plan
from .bar_types import bar_type_diameter_mm
from .column_host import ColumnHostError
from .footing_dowels import place_dowel_bars
from .footing_host import (
    FootingHostError, find_column_above, read_dowel_column_section_mm,
    read_footing_geometry_mm,
)
from .footing_mesh import place_bottom_mesh_bars
from .footing_ownership import partition_host_rebar, tag_as_ours
from .units import internal_to_mm

#: Named separately from the single-footing path's own TRANSACTION_NAME
#: so the undo menu tells the two apart -- same reasoning
#: ``column_batch.BATCH_TRANSACTION_NAME`` already states.
BATCH_TRANSACTION_NAME = "RFT Detail Footing Batch"

#: What the engineer states ONCE for the whole batch (spec Sec 1) --
#: carried as one object so ``plan_candidates`` never has to remember
#: which caller supplied which shared input. Everything HOST-derived (the
#: detected column, its own live section, the footing's own live
#: geometry, the resulting plan) is instead read/built per footing.
#: ``bar_x_type``/``bar_y_type``/``dowel_bar_type``/``dowel_tie_bar_type``
#: are the actual ``RebarBarType`` elements (not just their diameters) --
#: ``plan_candidates`` derives the diameters from them once, and
#: ``apply_batch`` needs the types themselves to place bars.
#: #229: ``bottom_mat_shape_mode`` is the SAME ``None``/``footing_mesh.
#: MAT_SHAPE_U``/``footing_mesh.MAT_SHAPE_L_ALTERNATING`` override
#: ``FootingInputs.bottom_mat_shape_mode`` already accepts for the
#: single-footing path -- carried here too so a batch run honours the
#: SAME shape choice the engineer made on the Mesh & Dowels tab, rather
#: than silently reverting every OTHER footing in the group back to
#: "auto". Defaults to ``None`` so every caller that predates #229 keeps
#: building a batch with no override, unchanged.
#: #232 (R11): ``mesh_bar_x_spacing_mm``/``mesh_bar_y_spacing_mm`` are the
#: SAME direct per-direction spacing inputs ``FootingInputs`` already
#: accepts for the single-footing path, carried here too so a batch run
#: builds the SAME real bottom-mesh array for every footing in the group
#: rather than silently reverting every one back to the one-bar fallback.
#: Both default to ``None`` so every caller that predates #232 keeps
#: building a batch with no array, unchanged.
BatchInputs = namedtuple(
    "BatchInputs",
    ["x_offset_mm", "y_offset_mm", "ld_multiplier",
     "bar_x_type", "bar_y_type",
     "dowel_bar_type", "dowel_tie_bar_type", "dowel_ld_multiplier",
     "dowel_count_b_face", "dowel_count_h_face", "bottom_mat_shape_mode",
     "mesh_bar_x_spacing_mm", "mesh_bar_y_spacing_mm"])
BatchInputs.__new__.__defaults__ = (None, None, None)


class FootingBatchError(Exception):
    """A refusal at the batch level -- an empty candidate set, or existing
    reinforcement never read before ``apply_batch`` -- mirrors
    ``column_placer.ColumnPlacementError``'s role for the column batch
    path."""


class FootingCandidate(object):
    """One footing that survived reading and refusal: its element, its
    own live reads, and the ``FootingPlan`` built from them -- ready for
    the transaction.

    ``ours``/``foreign`` stay ``None`` until :func:`read_existing` fills
    them, for the SAME reason ``column_batch.ColumnCandidate`` keeps them
    ``None`` until then: the count the engineer confirms and the elements
    ``apply_batch`` deletes must be the same read, not two independent
    queries.
    """

    def __init__(self, element, geometry, column_section, plan):
        self.element = element
        self.geometry = geometry
        self.column_section = column_section
        self.plan = plan
        self.ours = None
        self.foreign = None


class BatchPlan(object):
    """Everything :func:`plan_candidates` produced -- the ONE object the
    report and :func:`apply_batch` both read, so neither can disagree
    about which footings were grouped how, or which were excluded and
    why."""

    def __init__(self, groups, exclusions, candidates):
        self.groups = groups
        self.exclusions = exclusions
        self.candidates = candidates


class FootingPlacementResult(object):
    """What one footing's own placement actually built -- the report
    material Sec 6 needs.

    #232 (R11): ``bars_x``/``bars_y`` are LISTS -- every bar placed for
    that direction, one entry when no array was built (spacing not
    supplied, the SAME single-bar-per-direction shape every caller that
    predates #232 already got), N entries for a real array.
    """

    def __init__(self, bars_x, bars_y, dowel_bars, replaced_count, foreign):
        self.bars_x = bars_x
        self.bars_y = bars_y
        self.dowel_bars = dowel_bars
        self.replaced_count = replaced_count
        self.foreign = foreign


class BatchPlacementResult(object):
    """What the transaction actually built, per footing."""

    def __init__(self, per_footing):
        #: ``[(element_id, FootingPlacementResult), ...]``, in the order
        #: the candidates were placed.
        self.per_footing = per_footing


def collect_candidates(doc, host_footing):
    """Every ``OST_StructuralFoundation`` instance of the SAME family
    TYPE as ``host_footing`` (spec Sec 2) -- footing-type match only. The
    auto-detected column's own type match is checked per candidate in
    :func:`read_candidates`, since it needs a per-element ray-cast this
    cheap ``Symbol.Id`` filter cannot perform.

    ``host_footing`` is included in the result: the engineer picked it as
    one of the footings to detail by asking for the batch, and there is
    no reason for it to be the one footing excluded from its own run.
    """
    collector = (
        DB.FilteredElementCollector(doc)
        .OfCategory(DB.BuiltInCategory.OST_StructuralFoundation)
        .WhereElementIsNotElementType())
    symbol_id = host_footing.Symbol.Id
    return [element for element in collector
            if getattr(element, "Symbol", None) is not None
            and element.Symbol.Id == symbol_id]


def read_candidates(doc, elements, host_column_symbol_id):
    """Read every candidate through the SAME ``find_column_above``/
    ``read_dowel_column_section_mm``/``read_footing_geometry_mm`` the
    single-footing script calls (spec Sec 2/5). A footing any of these
    three refuses is excluded here, before any plan is built and before
    any transaction opens, with its reason kept for the report.

    A candidate whose own detected column is a DIFFERENT family type than
    the picked footing's own detected column is excluded too -- spec
    Sec 2's own new check, since #220 alone has no concept of "wrong
    column type," only "no column at all."
    """
    reads = []
    exclusions = []
    for element in elements:
        try:
            column = find_column_above(doc, element)
        except FootingHostError as refusal:
            exclusions.append(Exclusion(
                element_id=element.Id.IntegerValue, reason=str(refusal)))
            continue
        if column.Symbol.Id != host_column_symbol_id:
            exclusions.append(Exclusion(
                element_id=element.Id.IntegerValue,
                reason="This footing's own column is a different family "
                       "type than the picked footing's column, so it is "
                       "not part of this footing+column type pair "
                       "(specs/isolated-footing-batch.md Sec 2)."))
            continue
        try:
            column_section = read_dowel_column_section_mm(column)
            geometry = read_footing_geometry_mm(element)
        except (ColumnHostError, FootingHostError) as refusal:
            exclusions.append(Exclusion(
                element_id=element.Id.IntegerValue, reason=str(refusal)))
            continue
        reads.append((element, geometry, column_section))
    return reads, exclusions


def plan_candidates(doc, host_footing, inputs):
    """Spec Sections 2/3/5: collect, read and group, plan per footing,
    and refuse per footing -- everything that must happen BEFORE the
    transaction can open.

    A footing ``build_footing_plan`` raises ``ValueError``/
    ``DowelArrayLayoutError`` for is excluded here too (spec Sec 5), by
    the exact function the single-footing script calls -- never a second
    opinion about buildability.
    """
    host_column = find_column_above(doc, host_footing)
    elements = collect_candidates(doc, host_footing)
    reads, exclusions = read_candidates(
        doc, elements, host_column.Symbol.Id)

    mesh_bar_x_dia_mm = bar_type_diameter_mm(
        inputs.bar_x_type, internal_to_mm)
    mesh_bar_y_dia_mm = bar_type_diameter_mm(
        inputs.bar_y_type, internal_to_mm)
    dowel_bar_dia_mm = bar_type_diameter_mm(
        inputs.dowel_bar_type, internal_to_mm)
    dowel_tie_dia_mm = bar_type_diameter_mm(
        inputs.dowel_tie_bar_type, internal_to_mm)

    candidates = []
    for element, geometry, column_section in reads:
        footing_inputs = FootingInputs(
            a_mm=geometry.a_mm, b_mm=geometry.b_mm,
            cover_mm=geometry.cover_mm,
            footing_thickness_mm=geometry.footing_thickness_mm,
            bottom_cover_mm=geometry.bottom_cover_mm,
            top_cover_mm=geometry.top_cover_mm,
            mesh_bar_x_dia_mm=mesh_bar_x_dia_mm,
            mesh_bar_y_dia_mm=mesh_bar_y_dia_mm,
            x_offset_mm=inputs.x_offset_mm, y_offset_mm=inputs.y_offset_mm,
            ld_multiplier=inputs.ld_multiplier,
            bottom_mat_shape_mode=inputs.bottom_mat_shape_mode,
            dowel_bar_dia_mm=dowel_bar_dia_mm,
            dowel_ld_multiplier=inputs.dowel_ld_multiplier,
            dowel_tie_dia_mm=dowel_tie_dia_mm,
            dowel_count_b_face=inputs.dowel_count_b_face,
            dowel_count_h_face=inputs.dowel_count_h_face,
            mesh_bar_x_spacing_mm=inputs.mesh_bar_x_spacing_mm,
            mesh_bar_y_spacing_mm=inputs.mesh_bar_y_spacing_mm)
        try:
            plan = build_footing_plan(
                footing_inputs, column_section=column_section)
        except ValueError as refusal:
            exclusions.append(Exclusion(
                element_id=element.Id.IntegerValue, reason=str(refusal)))
            continue
        candidates.append(FootingCandidate(
            element=element, geometry=geometry,
            column_section=column_section, plan=plan))

    # Grouped from the SURVIVORS, never from every read -- same reasoning
    # column_batch.plan_candidates states: a footing named in a group must
    # be a footing that gets steel, or the report would contradict itself.
    groups = group_hosts([
        (candidate.element.Id.IntegerValue, candidate.geometry,
         candidate.column_section)
        for candidate in candidates])

    return BatchPlan(groups=groups, exclusions=exclusions,
                     candidates=candidates)


def read_existing(doc, batch_plan):
    """Spec Sec 6, per footing and BEFORE any transaction: this tool's
    own elements on each candidate's host, and the foreign rebar left
    alone -- through the SAME ``footing_ownership.partition_host_rebar``
    :func:`apply_batch` relies on having already been called.
    """
    rows = []
    for candidate in batch_plan.candidates:
        candidate.ours, candidate.foreign = partition_host_rebar(
            doc, candidate.element)
        rows.append(BatchExisting(
            element_id=candidate.element.Id.IntegerValue,
            replaced_count=len(candidate.ours),
            foreign_ids=[found.element_id for found in candidate.foreign]))
    return rows


def apply_batch(doc, batch_plan, bar_x_type, bar_y_type, dowel_bar_type):
    """Spec Sec 5: ONE transaction for the whole batch, all-or-nothing.
    If every candidate was excluded, the run refuses as a whole rather
    than opening an empty transaction -- checked before ``Transaction``
    is ever constructed, the same "refuse before opening" shape
    ``column_batch.apply_batch`` already uses.
    """
    if not batch_plan.candidates:
        raise FootingBatchError(
            "Every candidate footing in this batch was excluded -- see "
            "the report. Nothing to place, so no transaction was opened "
            "(specs/isolated-footing-batch.md Sec 5).")

    for candidate in batch_plan.candidates:
        if candidate.ours is None or candidate.foreign is None:
            # Same R23-mirroring guard column_batch.apply_batch applies:
            # a caller that never ran read_existing never showed the
            # engineer a count, so this run would delete reinforcement
            # nobody confirmed.
            raise FootingBatchError(
                "Footing %s: existing reinforcement was never read, so "
                "the replacement count was never shown. Call "
                "read_existing before apply_batch."
                % candidate.element.Id.IntegerValue)

    transaction = Transaction(doc, BATCH_TRANSACTION_NAME)
    transaction.Start()
    try:
        per_footing = []
        for candidate in batch_plan.candidates:
            ours, foreign = candidate.ours, candidate.foreign
            for element in ours:
                doc.Delete(element.Id)

            bars_x, bars_y = place_bottom_mesh_bars(
                doc, candidate.element, candidate.plan.bottom_mesh,
                bar_x_type, bar_y_type)
            dowel_bars = place_dowel_bars(
                doc, candidate.element, candidate.plan.dowel,
                dowel_bar_type)

            host_id = candidate.element.Id.IntegerValue
            for rebar in list(bars_x) + list(bars_y) + list(dowel_bars):
                tag_as_ours(rebar, host_id)

            per_footing.append((host_id, FootingPlacementResult(
                bars_x=bars_x, bars_y=bars_y, dowel_bars=dowel_bars,
                replaced_count=len(ours), foreign=foreign)))
    except Exception:
        transaction.RollBack()
        raise
    transaction.Commit()

    return BatchPlacementResult(per_footing=per_footing)
