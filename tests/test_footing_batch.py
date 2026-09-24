# -*- coding: utf-8 -*-
"""Issue #226 -- specs/isolated-footing-batch.md Section 3, and R9
(docs/footing/spec-amendments.md): grouping, PURE, exercised directly
with no Revit stand-in at all -- mirrors tests/test_column_batch.py's own
grouping section for the same reason that file gives (the adapter's own
correctness is a separate, mock-object-driven test file).
"""

from rft.core.footing_batch import BatchGroup, group_hosts, group_key
from rft.core.footing_plan import DowelColumnSection
from rft.revit.footing_host import FootingGeometry


def _geometry(a_mm=1800.0, b_mm=1200.0, footing_thickness_mm=450.0,
             cover_mm=50.0, bottom_cover_mm=50.0, top_cover_mm=50.0):
    return FootingGeometry(
        a_mm=a_mm, b_mm=b_mm, footing_thickness_mm=footing_thickness_mm,
        cover_mm=cover_mm, bottom_cover_mm=bottom_cover_mm,
        top_cover_mm=top_cover_mm)


def _column_section(cw_mm=300.0, cd_mm=600.0, ccover_mm=40.0):
    return DowelColumnSection(Cw_mm=cw_mm, Cd_mm=cd_mm, Ccover_mm=ccover_mm)


def test_two_footings_same_type_pair_different_geometry_land_in_different_groups():
    groups = group_hosts([
        (1, _geometry(), _column_section()),
        (2, _geometry(footing_thickness_mm=600.0), _column_section()),
    ])
    assert len(groups) == 2


def test_two_footings_same_type_pair_different_column_section_land_in_different_groups():
    """The SECOND half of R9's key, isolated: identical footing geometry,
    different live-read column cover -- the exact category of per-instance
    difference R9 exists to catch even when the footing's own dimensions
    match exactly."""
    groups = group_hosts([
        (1, _geometry(), _column_section(ccover_mm=40.0)),
        (2, _geometry(), _column_section(ccover_mm=25.0)),
    ])
    assert len(groups) == 2


def test_two_footings_same_type_pair_same_live_read_tuple_land_in_one_group():
    groups = group_hosts([
        (1, _geometry(), _column_section()),
        (2, _geometry(), _column_section()),
    ])
    assert len(groups) == 1
    assert groups[0].element_ids == [1, 2]


def test_a_group_of_one_is_not_an_error():
    groups = group_hosts([(1, _geometry(), _column_section())])
    assert len(groups) == 1
    assert groups[0].element_ids == [1]


def test_group_order_is_first_seen_not_hash_order():
    groups = group_hosts([
        (3, _geometry(a_mm=1800.0), _column_section()),
        (1, _geometry(a_mm=2400.0), _column_section()),
        (2, _geometry(a_mm=1800.0), _column_section()),
    ])
    assert [g.key.a_mm for g in groups] == [1800.0, 2400.0]
    assert groups[0].element_ids == [3, 2]


def test_group_key_reads_all_nine_fields_off_the_two_live_reads():
    key = group_key(_geometry(), _column_section())
    assert key.a_mm == 1800.0
    assert key.b_mm == 1200.0
    assert key.footing_thickness_mm == 450.0
    assert key.cover_mm == 50.0
    assert key.bottom_cover_mm == 50.0
    assert key.top_cover_mm == 50.0
    assert key.Cw_mm == 300.0
    assert key.Cd_mm == 600.0
    assert key.Ccover_mm == 40.0


def test_group_hosts_returns_BatchGroup_instances():
    groups = group_hosts([(1, _geometry(), _column_section())])
    assert isinstance(groups[0], BatchGroup)
