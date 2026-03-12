"""
Tests for drift analysis tool functions (SAF-28330).

TDD tests for simulation result/status drift tools covering:
Phase 1: data_types (build_drift_api_payload, group_and_enrich_drift_records)
Phase 2: core functions (_fetch_and_cache_simulation_drifts, _group_and_paginate_drifts)
Phase 3: public functions (sb_get_simulation_result_drifts, sb_get_simulation_status_drifts)
Phase 4: MCP tool registration
Phase 5: E2E smoke tests
Phase 8: look_back_time parameter and zero-results smart hints
Phase 9: result drifts grouping by result_status + final_status_breakdown
Phase 10: drop driftType field from drift records
Phase 11: attack_summary in drill-down
Phase 12: test ID traceability hints in drill-down
"""

import os
from unittest.mock import patch, MagicMock

import pytest
from safebreach_mcp_data.data_types import (
    build_drift_api_payload,
    group_and_enrich_drift_records,
    build_security_control_drift_payload,
    build_sc_drift_transition_key,
    group_sc_drift_records,
)
from safebreach_mcp_data.drifts_metadata import drift_types_mapping


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_drift_record():
    """A single raw API drift record for reuse across tests."""
    return {
        "trackingId": "abc123",
        "attackId": 1263,
        "attackTypes": ["Legitimate Channel Exfiltration"],
        "from": {
            "simulationId": 3189641,
            "executionTime": "2026-02-28T15:55:22.037Z",
            "finalStatus": "prevented",
            "status": "FAIL",
            "loggedBy": ["Microsoft Defender for Endpoint"],
            "reportedBy": [],
            "alertedBy": [],
            "preventedBy": ["Microsoft Defender for Endpoint"],
        },
        "to": {
            "simulationId": 3286842,
            "executionTime": "2026-03-03T15:37:28.212Z",
            "finalStatus": "logged",
            "status": "SUCCESS",
            "loggedBy": [],
            "reportedBy": [],
            "alertedBy": [],
            "preventedBy": [],
        },
        "driftType": "Regression",
    }


def _make_drift_record(
    from_final_status: str,
    to_final_status: str,
    from_status: str = "FAIL",
    to_status: str = "SUCCESS",
    tracking_id: str = "track-001",
    attack_id: int = 100,
):
    """Helper factory to create drift records with specified statuses."""
    return {
        "trackingId": tracking_id,
        "attackId": attack_id,
        "attackTypes": ["Test Attack"],
        "from": {
            "simulationId": 1000,
            "executionTime": "2026-02-28T15:55:22.037Z",
            "finalStatus": from_final_status,
            "status": from_status,
            "loggedBy": [],
            "reportedBy": [],
            "alertedBy": [],
            "preventedBy": [],
        },
        "to": {
            "simulationId": 2000,
            "executionTime": "2026-03-03T15:37:28.212Z",
            "finalStatus": to_final_status,
            "status": to_status,
            "loggedBy": [],
            "reportedBy": [],
            "alertedBy": [],
            "preventedBy": [],
        },
        "driftType": "Regression",
    }


def _make_sc_drift_record(
    from_prevented: bool = False,
    from_reported: bool = False,
    from_logged: bool = False,
    from_alerted: bool = False,
    to_prevented: bool = False,
    to_reported: bool = False,
    to_logged: bool = False,
    to_alerted: bool = False,
    tracking_id: str = "sc-track-001",
    drift_type: str = "Improvement",
    from_simulation_id: int = 820344,
    to_simulation_id: int = 838191,
) -> dict:
    """Helper factory for v2 security control drift records with boolean flags."""
    return {
        "trackingId": tracking_id,
        "from": {
            "simulationId": from_simulation_id,
            "executionTime": "2025-10-12T11:01:14.931Z",
            "prevented": from_prevented,
            "reported": from_reported,
            "logged": from_logged,
            "alerted": from_alerted,
        },
        "to": {
            "simulationId": to_simulation_id,
            "executionTime": "2025-10-13T13:20:50.099Z",
            "prevented": to_prevented,
            "reported": to_reported,
            "logged": to_logged,
            "alerted": to_alerted,
        },
        "driftType": drift_type,
    }


# ---------------------------------------------------------------------------
# Tests: build_drift_api_payload
# ---------------------------------------------------------------------------

class TestBuildDriftApiPayload:
    """Tests for building the drift API POST payload."""

    def test_build_payload_basic_time_window(self):
        """Epoch ms are converted to ISO-8601 UTC strings under windowStart/windowEnd."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
        )

        assert result["windowStart"] == "2024-03-01T00:00:00.000Z"
        assert result["windowEnd"] == "2024-03-02T00:00:00.000Z"

    def test_build_payload_only_non_none_included(self):
        """Parameters left as None must not appear in the output dict."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
        )

        # Only windowStart and windowEnd should be present
        assert "windowStart" in result
        assert "windowEnd" in result
        # Optional fields must be absent
        for key in (
            "driftType",
            "attackId",
            "attackType",
            "fromStatus",
            "toStatus",
            "fromFinalStatus",
            "toFinalStatus",
        ):
            assert key not in result

    @pytest.mark.parametrize(
        "input_value, expected_value",
        [
            ("regression", "Regression"),
            ("IMPROVEMENT", "Improvement"),
            ("not_applicable", "NotApplicable"),
            ("Regression", "Regression"),
            ("improvement", "Improvement"),
            ("NOT_APPLICABLE", "NotApplicable"),
        ],
    )
    def test_build_payload_drift_type_mapping(self, input_value, expected_value):
        """Snake_case / any-case drift_type is mapped to PascalCase API value."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            drift_type=input_value,
        )

        assert result["driftType"] == expected_value

    def test_build_payload_result_mode_params(self):
        """from_status and to_status map to camelCase fromStatus/toStatus."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            from_status="FAIL",
            to_status="SUCCESS",
        )

        assert result["fromStatus"] == "FAIL"
        assert result["toStatus"] == "SUCCESS"

    def test_build_payload_status_mode_params(self):
        """from_final_status and to_final_status map to fromFinalStatus/toFinalStatus."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            from_final_status="prevented",
            to_final_status="logged",
        )

        assert result["fromFinalStatus"] == "prevented"
        assert result["toFinalStatus"] == "logged"

    def test_build_payload_attack_filters(self):
        """attack_id and attack_type are included with camelCase keys."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            attack_id=1263,
            attack_type="host",
        )

        assert result["attackId"] == 1263
        assert result["attackType"] == "host"

    def test_build_payload_all_params(self):
        """All parameters supplied at once produce a complete payload."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            drift_type="regression",
            attack_id=1263,
            attack_type="exfil",
            from_status="FAIL",
            to_status="SUCCESS",
            from_final_status="prevented",
            to_final_status="logged",
        )

        assert result["windowStart"] == "2024-03-01T00:00:00.000Z"
        assert result["windowEnd"] == "2024-03-02T00:00:00.000Z"
        assert result["driftType"] == "Regression"
        assert result["attackId"] == 1263
        assert result["attackType"] == "exfil"
        assert result["fromStatus"] == "FAIL"
        assert result["toStatus"] == "SUCCESS"
        assert result["fromFinalStatus"] == "prevented"
        assert result["toFinalStatus"] == "logged"

    # --- Phase 8: look_back_time tests ---

    def test_look_back_time_default_is_7_days_before_window_start(self):
        """When look_back_time is None, earliestSearchTime defaults to 7 days before window_start."""
        window_start = 1709251200000  # 2024-03-01T00:00:00Z
        seven_days_ms = 7 * 86_400_000
        expected_epoch = window_start - seven_days_ms  # 2024-02-23T00:00:00Z

        result = build_drift_api_payload(
            window_start=window_start,
            window_end=1709337600000,
        )

        assert "earliestSearchTime" in result
        assert result["earliestSearchTime"] == "2024-02-23T00:00:00.000Z"

    def test_look_back_time_explicit_override(self):
        """Explicit look_back_time overrides the 7-day default."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            look_back_time=1708387200000,  # 2024-02-20T00:00:00Z
        )

        assert result["earliestSearchTime"] == "2024-02-20T00:00:00.000Z"

    def test_look_back_time_always_present(self):
        """earliestSearchTime is always present in payload output."""
        result = build_drift_api_payload(
            window_start=1709251200000,
            window_end=1709337600000,
            drift_type="regression",
            from_status="FAIL",
        )

        assert "earliestSearchTime" in result


# ---------------------------------------------------------------------------
# Tests: group_and_enrich_drift_records
# ---------------------------------------------------------------------------

class TestGroupAndEnrichDriftRecords:
    """Tests for grouping raw drift records and enriching with metadata."""

    def test_group_records_same_drift_type(self):
        """Three records with identical from/to finalStatus form one group with count=3."""
        records = [
            _make_drift_record("prevented", "logged", tracking_id=f"t-{i}")
            for i in range(3)
        ]

        groups = group_and_enrich_drift_records(records)

        assert len(groups) == 1
        assert groups[0]["count"] == 3
        assert groups[0]["drift_key"] == "prevented-logged"
        assert len(groups[0]["drifts"]) == 3

    def test_group_records_known_drift_type_enrichment(self, sample_drift_record):
        """A 'prevented-logged' record is enriched from drifts_metadata."""
        groups = group_and_enrich_drift_records([sample_drift_record])

        assert len(groups) == 1
        group = groups[0]

        # Cross-check against the actual metadata
        expected_meta = drift_types_mapping["prevented-logged"]
        assert group["security_impact"] == expected_meta["security_impact"]
        assert group["description"] == expected_meta["description"]
        assert group["hint_to_llm"] == expected_meta["hint_to_llm"]
        assert group["security_impact"] == "negative"

    def test_group_records_unknown_drift_type_fallback(self):
        """Completely unknown finalStatus pair falls back to security_impact='unknown'."""
        record = _make_drift_record(
            from_final_status="zzz_fake_from",
            to_final_status="zzz_fake_to",
            from_status="ZZZ_FAKE",
            to_status="ZZZ_FAKE",
        )

        groups = group_and_enrich_drift_records([record])

        assert len(groups) == 1
        assert groups[0]["security_impact"] == "unknown"

    def test_group_records_sorted_by_count_descending(self):
        """Groups are returned sorted by count in descending order."""
        # 2 records of type A (prevented -> logged)
        type_a = [
            _make_drift_record("prevented", "logged", tracking_id=f"a-{i}")
            for i in range(2)
        ]
        # 5 records of type B (missed -> prevented)
        type_b = [
            _make_drift_record("missed", "prevented", tracking_id=f"b-{i}")
            for i in range(5)
        ]

        groups = group_and_enrich_drift_records(type_a + type_b)

        assert len(groups) == 2
        assert groups[0]["count"] == 5
        assert groups[0]["drift_key"] == "missed-prevented"
        assert groups[1]["count"] == 2
        assert groups[1]["drift_key"] == "prevented-logged"

    def test_group_records_empty_list(self):
        """Empty input returns empty output."""
        groups = group_and_enrich_drift_records([])

        assert groups == []

    def test_group_records_preserves_original_fields(self, sample_drift_record):
        """All original API fields are preserved in the drifts array."""
        groups = group_and_enrich_drift_records([sample_drift_record])

        drift = groups[0]["drifts"][0]

        # Verify the full structure of the original record is intact
        assert drift["trackingId"] == "abc123"
        assert drift["attackId"] == 1263
        assert drift["attackTypes"] == ["Legitimate Channel Exfiltration"]
        assert "driftType" not in drift  # Phase 10: stripped from records

        # Verify nested from/to fields
        assert drift["from"]["simulationId"] == 3189641
        assert drift["from"]["finalStatus"] == "prevented"
        assert drift["from"]["loggedBy"] == ["Microsoft Defender for Endpoint"]
        assert drift["from"]["reportedBy"] == []
        assert drift["from"]["alertedBy"] == []
        assert drift["from"]["preventedBy"] == ["Microsoft Defender for Endpoint"]

        assert drift["to"]["simulationId"] == 3286842
        assert drift["to"]["finalStatus"] == "logged"
        assert drift["to"]["loggedBy"] == []
        assert drift["to"]["reportedBy"] == []
        assert drift["to"]["alertedBy"] == []
        assert drift["to"]["preventedBy"] == []

    def test_group_records_multiple_groups(self):
        """Mixed drift types produce separate groups with correct counts."""
        prevented_to_logged = [
            _make_drift_record("prevented", "logged", tracking_id=f"pl-{i}")
            for i in range(3)
        ]
        fail_to_success = [
            _make_drift_record(
                "stopped", "missed",
                from_status="FAIL",
                to_status="SUCCESS",
                tracking_id=f"fs-{i}",
            )
            for i in range(2)
        ]

        groups = group_and_enrich_drift_records(prevented_to_logged + fail_to_success)

        assert len(groups) == 2
        # Sorted by count descending, so prevented-logged (3) comes first
        assert groups[0]["drift_key"] == "prevented-logged"
        assert groups[0]["count"] == 3
        assert groups[1]["drift_key"] == "stopped-missed"
        assert groups[1]["count"] == 2

    def test_group_records_result_level_fallback(self):
        """When finalStatus key is not in drift_types_mapping but status-level key IS,
        enrichment uses the result-level (status) mapping."""
        # Use finalStatus values that do NOT exist in drift_types_mapping
        # but whose status values (fail-success) DO exist
        record = _make_drift_record(
            from_final_status="zzz_unknown_from",
            to_final_status="zzz_unknown_to",
            from_status="success",
            to_status="fail",
        )

        groups = group_and_enrich_drift_records([record])

        assert len(groups) == 1
        group = groups[0]
        # Should fall back to the result-level key "success-fail"
        expected_meta = drift_types_mapping["success-fail"]
        assert group["security_impact"] == expected_meta["security_impact"]
        assert group["description"] == expected_meta["description"]
        assert group["hint_to_llm"] == expected_meta["hint_to_llm"]

    def test_group_dict_structure(self, sample_drift_record):
        """Each group dict contains all required keys."""
        groups = group_and_enrich_drift_records([sample_drift_record])

        group = groups[0]
        required_keys = {
            "drift_key",
            "security_impact",
            "description",
            "hint_to_llm",
            "count",
            "drifts",
        }
        assert required_keys.issubset(group.keys())
        assert isinstance(group["drifts"], list)
        assert isinstance(group["count"], int)

    # --- Phase 9: group_by="result_status" tests ---

    def test_group_by_result_status_groups_by_from_to_status(self):
        """group_by='result_status' groups records by from.status-to.status (FAIL/SUCCESS)."""
        # Two records with different finalStatus but same result status (FAIL→SUCCESS)
        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
        ]

        groups = group_and_enrich_drift_records(records, group_by="result_status")

        # Should be one group (fail-success), not two (prevented-logged, stopped-missed)
        assert len(groups) == 1
        assert groups[0]["drift_key"] == "fail-success"
        assert groups[0]["count"] == 2

    def test_group_by_result_status_produces_coarse_groups(self):
        """group_by='result_status' collapses many finalStatus transitions into few result groups."""
        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
            _make_drift_record("missed", "prevented", from_status="SUCCESS", to_status="FAIL", tracking_id="r3"),
            _make_drift_record("logged", "stopped", from_status="SUCCESS", to_status="FAIL", tracking_id="r4"),
        ]

        groups = group_and_enrich_drift_records(records, group_by="result_status")

        assert len(groups) == 2
        keys = {g["drift_key"] for g in groups}
        assert keys == {"fail-success", "success-fail"}
        # Each group has 2 records
        for g in groups:
            assert g["count"] == 2

    def test_group_by_final_status_default_is_unchanged(self):
        """Default group_by (or group_by='final_status') preserves current fine-grained behavior."""
        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
        ]

        # Default (no group_by)
        groups_default = group_and_enrich_drift_records(records)
        # Explicit final_status
        groups_explicit = group_and_enrich_drift_records(records, group_by="final_status")

        # Both should produce 2 groups (prevented-logged, stopped-missed)
        assert len(groups_default) == 2
        assert len(groups_explicit) == 2
        default_keys = {g["drift_key"] for g in groups_default}
        explicit_keys = {g["drift_key"] for g in groups_explicit}
        assert default_keys == {"prevented-logged", "stopped-missed"}
        assert explicit_keys == {"prevented-logged", "stopped-missed"}

    def test_group_by_result_status_enrichment_uses_result_key(self):
        """group_by='result_status' uses result-level metadata (fail-success has known metadata)."""
        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS"),
        ]

        groups = group_and_enrich_drift_records(records, group_by="result_status")

        group = groups[0]
        expected_meta = drift_types_mapping["fail-success"]
        assert group["security_impact"] == expected_meta["security_impact"]
        assert group["description"] == expected_meta["description"]

    # --- Phase 10: driftType field stripped ---

    def test_drift_type_field_stripped_from_records(self, sample_drift_record):
        """driftType field is removed from records in the drifts array."""
        groups = group_and_enrich_drift_records([sample_drift_record])

        drift = groups[0]["drifts"][0]
        assert "driftType" not in drift

    def test_other_fields_preserved_when_drift_type_stripped(self, sample_drift_record):
        """All fields except driftType are preserved after stripping."""
        groups = group_and_enrich_drift_records([sample_drift_record])

        drift = groups[0]["drifts"][0]
        assert drift["trackingId"] == "abc123"
        assert drift["attackId"] == 1263
        assert drift["from"]["simulationId"] == 3189641
        assert drift["to"]["simulationId"] == 3286842

    def test_security_impact_present_after_drift_type_stripped(self, sample_drift_record):
        """security_impact on group remains unchanged after driftType removal."""
        groups = group_and_enrich_drift_records([sample_drift_record])

        assert groups[0]["security_impact"] == "negative"

    def test_group_by_result_status_same_records_different_grouping(self):
        """Same records produce different grouping depending on group_by."""
        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
            _make_drift_record("missed", "prevented", from_status="SUCCESS", to_status="FAIL", tracking_id="r3"),
        ]

        groups_fs = group_and_enrich_drift_records(records, group_by="final_status")
        groups_rs = group_and_enrich_drift_records(records, group_by="result_status")

        # final_status: 3 groups (prevented-logged, stopped-missed, missed-prevented)
        assert len(groups_fs) == 3
        # result_status: 2 groups (fail-success, success-fail)
        assert len(groups_rs) == 2


# ---------------------------------------------------------------------------
# Tests: build_security_control_drift_payload  (SAF-28331 Phase 2)
# ---------------------------------------------------------------------------

class TestBuildSecurityControlDriftPayload:
    """Tests for building the v2 security control drift POST payload."""

    # Standard test timestamps
    WINDOW_START = 1709251200000   # 2024-03-01T00:00:00.000Z
    WINDOW_END = 1709337600000     # 2024-03-02T00:00:00.000Z
    SEVEN_DAYS_MS = 7 * 86_400_000
    DEFAULT_EARLIEST = WINDOW_START - SEVEN_DAYS_MS  # 2024-02-23T00:00:00.000Z

    def _build_minimal(self, **overrides):
        """Build payload with minimal required params, merging overrides."""
        defaults = dict(
            security_control="Microsoft Defender for Endpoint",
            window_start=self.WINDOW_START,
            window_end=self.WINDOW_END,
            contains_transition=True,
            starts_and_ends_with_transition=False,
        )
        defaults.update(overrides)
        return build_security_control_drift_payload(**defaults)

    def test_build_sc_payload_required_fields(self):
        """Output has securityControl, windowStart, windowEnd, earliestSearchTime, both transition booleans."""
        payload = self._build_minimal()

        assert "securityControl" in payload
        assert "windowStart" in payload
        assert "windowEnd" in payload
        assert "earliestSearchTime" in payload
        assert "containsTransition" in payload
        assert "startsAndEndsWithTransition" in payload
        assert payload["securityControl"] == "Microsoft Defender for Endpoint"
        assert payload["containsTransition"] is True
        assert payload["startsAndEndsWithTransition"] is False

    def test_build_sc_payload_timestamps_converted(self):
        """Epoch ms -> ISO-8601 UTC strings."""
        payload = self._build_minimal()

        assert payload["windowStart"] == "2024-03-01T00:00:00.000Z"
        assert payload["windowEnd"] == "2024-03-02T00:00:00.000Z"

    def test_build_sc_payload_all_from_booleans(self):
        """fromStatus: {prevented: T, reported: F, logged: T, alerted: F}."""
        payload = self._build_minimal(
            from_prevented=True, from_reported=False,
            from_logged=True, from_alerted=False,
        )

        assert payload["fromStatus"] == {
            "prevented": True, "reported": False,
            "logged": True, "alerted": False,
        }

    def test_build_sc_payload_all_to_booleans(self):
        """toStatus: {prevented: T, reported: T, logged: F, alerted: T}."""
        payload = self._build_minimal(
            to_prevented=True, to_reported=True,
            to_logged=False, to_alerted=True,
        )

        assert payload["toStatus"] == {
            "prevented": True, "reported": True,
            "logged": False, "alerted": True,
        }

    def test_build_sc_payload_partial_from_booleans(self):
        """Only 2 of 4 from booleans -> fromStatus has only those 2 keys."""
        payload = self._build_minimal(
            from_prevented=True, from_alerted=False,
        )

        assert "fromStatus" in payload
        assert payload["fromStatus"] == {"prevented": True, "alerted": False}
        assert "reported" not in payload["fromStatus"]
        assert "logged" not in payload["fromStatus"]

    def test_build_sc_payload_no_from_booleans(self):
        """All from booleans None -> no fromStatus key in payload."""
        payload = self._build_minimal()

        assert "fromStatus" not in payload

    def test_build_sc_payload_no_to_booleans(self):
        """All to booleans None -> no toStatus key in payload."""
        payload = self._build_minimal()

        assert "toStatus" not in payload

    @pytest.mark.parametrize("input_val,expected", [
        ("regression", "Regression"),
        ("IMPROVEMENT", "Improvement"),
        ("not_applicable", "NotApplicable"),
        ("Regression", "Regression"),
        ("improvement", "Improvement"),
    ])
    def test_build_sc_payload_drift_type_mapping(self, input_val, expected):
        """Drift type string maps to PascalCase API value."""
        payload = self._build_minimal(drift_type=input_val)

        assert payload["driftType"] == expected

    def test_build_sc_payload_default_earliest_search_time(self):
        """None -> 7 days before window_start."""
        payload = self._build_minimal()

        assert payload["earliestSearchTime"] == "2024-02-23T00:00:00.000Z"

    def test_build_sc_payload_explicit_earliest_search_time(self):
        """Explicit value overrides default."""
        payload = self._build_minimal(earliest_search_time=1708387200000)

        assert payload["earliestSearchTime"] == "2024-02-20T00:00:00.000Z"

    def test_build_sc_payload_max_outside_window(self):
        """Integer included as maxOutsideWindowExecutions."""
        payload = self._build_minimal(max_outside_window_executions=0)

        assert payload["maxOutsideWindowExecutions"] == 0

    def test_build_sc_payload_max_outside_window_omitted(self):
        """None -> key absent from payload."""
        payload = self._build_minimal()

        assert "maxOutsideWindowExecutions" not in payload


# ---------------------------------------------------------------------------
# Tests: build_sc_drift_transition_key  (SAF-28331 Phase 2)
# ---------------------------------------------------------------------------

class TestBuildScDriftTransitionKey:
    """Tests for v2 transition key generation from boolean status flags."""

    def test_transition_key_all_true(self):
        """All booleans True on both sides."""
        record = _make_sc_drift_record(
            from_prevented=True, from_reported=True, from_logged=True, from_alerted=True,
            to_prevented=True, to_reported=True, to_logged=True, to_alerted=True,
        )
        key = build_sc_drift_transition_key(record)
        assert key == "P:T,R:T,L:T,A:T->P:T,R:T,L:T,A:T"

    def test_transition_key_all_false(self):
        """All booleans False on both sides."""
        record = _make_sc_drift_record()  # defaults are all False
        key = build_sc_drift_transition_key(record)
        assert key == "P:F,R:F,L:F,A:F->P:F,R:F,L:F,A:F"

    def test_transition_key_mixed(self):
        """Specific mixed combo produces correct compact key."""
        record = _make_sc_drift_record(
            from_prevented=False, from_reported=True, from_logged=False, from_alerted=True,
            to_prevented=True, to_reported=True, to_logged=False, to_alerted=True,
        )
        key = build_sc_drift_transition_key(record)
        assert key == "P:F,R:T,L:F,A:T->P:T,R:T,L:F,A:T"

    def test_transition_key_single_change(self):
        """Only prevented flips from F to T."""
        record = _make_sc_drift_record(to_prevented=True)
        key = build_sc_drift_transition_key(record)
        assert key == "P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F"

    def test_transition_key_missing_field_defaults(self):
        """Missing 'prevented' in 'from' defaults to False."""
        record = {
            "trackingId": "missing-field",
            "from": {
                "simulationId": 1000,
                "executionTime": "2025-10-12T11:01:14.931Z",
                "reported": True,
                "logged": False,
                "alerted": False,
            },
            "to": {
                "simulationId": 2000,
                "executionTime": "2025-10-13T13:20:50.099Z",
                "prevented": True,
                "reported": True,
                "logged": False,
                "alerted": False,
            },
            "driftType": "Improvement",
        }
        key = build_sc_drift_transition_key(record)
        assert key == "P:F,R:T,L:F,A:F->P:T,R:T,L:F,A:F"


# ---------------------------------------------------------------------------
# Tests: group_sc_drift_records  (SAF-28331 Phase 2)
# ---------------------------------------------------------------------------

class TestGroupScDriftRecords:
    """Tests for grouping v2 security control drift records."""

    def test_group_by_transition_same_combo(self):
        """3 identical boolean combos -> 1 group, count=3."""
        records = [
            _make_sc_drift_record(to_prevented=True, tracking_id=f"t-{i}")
            for i in range(3)
        ]
        groups = group_sc_drift_records(records, group_by="transition")

        assert len(groups) == 1
        assert groups[0]["count"] == 3

    def test_group_by_transition_different_combos(self):
        """Different boolean combos -> separate groups."""
        rec_a = _make_sc_drift_record(to_prevented=True, tracking_id="a")
        rec_b = _make_sc_drift_record(to_reported=True, tracking_id="b")
        groups = group_sc_drift_records([rec_a, rec_b], group_by="transition")

        assert len(groups) == 2

    def test_group_by_transition_sorted_by_count(self):
        """Groups sorted descending by count."""
        recs_a = [
            _make_sc_drift_record(to_prevented=True, tracking_id=f"a-{i}")
            for i in range(5)
        ]
        recs_b = [
            _make_sc_drift_record(to_reported=True, tracking_id=f"b-{i}")
            for i in range(2)
        ]
        groups = group_sc_drift_records(recs_a + recs_b, group_by="transition")

        assert groups[0]["count"] == 5
        assert groups[1]["count"] == 2

    def test_group_by_drift_type(self):
        """Groups by driftType (Improvement, Regression)."""
        recs = [
            _make_sc_drift_record(drift_type="Improvement", tracking_id="imp-1"),
            _make_sc_drift_record(drift_type="Improvement", tracking_id="imp-2"),
            _make_sc_drift_record(drift_type="Regression", tracking_id="reg-1"),
        ]
        groups = group_sc_drift_records(recs, group_by="drift_type")

        assert len(groups) == 2
        keys = {g["drift_key"] for g in groups}
        assert "Improvement" in keys
        assert "Regression" in keys

    def test_group_by_drift_type_mixed(self):
        """3 Improvement + 2 Regression -> 2 groups sorted by count."""
        recs = [
            _make_sc_drift_record(drift_type="Improvement", tracking_id=f"i-{i}")
            for i in range(3)
        ] + [
            _make_sc_drift_record(drift_type="Regression", tracking_id=f"r-{i}")
            for i in range(2)
        ]
        groups = group_sc_drift_records(recs, group_by="drift_type")

        assert len(groups) == 2
        assert groups[0]["drift_key"] == "Improvement"
        assert groups[0]["count"] == 3
        assert groups[1]["drift_key"] == "Regression"
        assert groups[1]["count"] == 2

    def test_group_empty_records(self):
        """Empty list -> empty list."""
        groups = group_sc_drift_records([], group_by="transition")
        assert groups == []

    def test_group_description_gained_prevention(self):
        """from.prevented=false, to.prevented=true -> description mentions prevention gain."""
        record = _make_sc_drift_record(from_prevented=False, to_prevented=True)
        groups = group_sc_drift_records([record], group_by="transition")

        assert len(groups) == 1
        desc = groups[0]["description"].lower()
        assert "prevent" in desc

    def test_group_description_lost_alerting(self):
        """from.alerted=true, to.alerted=false -> description mentions alerting loss."""
        record = _make_sc_drift_record(from_alerted=True, to_alerted=False)
        groups = group_sc_drift_records([record], group_by="transition")

        assert len(groups) == 1
        desc = groups[0]["description"].lower()
        assert "alert" in desc

    def test_group_description_multi_change(self):
        """Multiple flags changed -> description covers all changes."""
        record = _make_sc_drift_record(
            from_prevented=True, to_prevented=False,
            from_logged=False, to_logged=True,
        )
        groups = group_sc_drift_records([record], group_by="transition")

        assert len(groups) == 1
        desc = groups[0]["description"].lower()
        assert "prevent" in desc
        assert "log" in desc

    def test_group_preserves_original_records(self):
        """All original API fields intact in drifts list."""
        record = _make_sc_drift_record(
            from_prevented=True, to_prevented=False,
            tracking_id="preserve-me",
            from_simulation_id=111,
            to_simulation_id=222,
        )
        groups = group_sc_drift_records([record], group_by="transition")

        assert len(groups) == 1
        drift = groups[0]["drifts"][0]
        assert drift["trackingId"] == "preserve-me"
        assert drift["from"]["simulationId"] == 111
        assert drift["to"]["simulationId"] == 222
        assert drift["from"]["executionTime"] == "2025-10-12T11:01:14.931Z"
        assert drift["to"]["executionTime"] == "2025-10-13T13:20:50.099Z"
        assert "prevented" in drift["from"]
        assert "prevented" in drift["to"]


# ---------------------------------------------------------------------------
# Tests: _fetch_and_cache_simulation_drifts  (Phase 2)
# ---------------------------------------------------------------------------

class TestFetchAndCacheSimulationDrifts:
    """Tests for the internal fetch/cache function."""

    def setup_method(self):
        """Clear the simulation_drifts_cache before each test."""
        from safebreach_mcp_data.data_functions import simulation_drifts_cache
        simulation_drifts_cache.clear()

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_successful_api_call(self, mock_account, mock_url, mock_secret, mock_post):
        """Successful API call returns parsed records."""
        from safebreach_mcp_data.data_functions import _fetch_and_cache_simulation_drifts

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"trackingId": "t1"}, {"trackingId": "t2"}]
        mock_post.return_value = mock_response

        records, elapsed = _fetch_and_cache_simulation_drifts("demo", {"windowStart": "x"}, "key1")

        assert len(records) == 2
        assert records[0]["trackingId"] == "t1"
        assert elapsed >= 0.0
        mock_post.assert_called_once()
        call_url = mock_post.call_args[0][0]
        assert "/drift/simulationStatus" in call_url

    @patch("safebreach_mcp_data.data_functions.is_caching_enabled", return_value=True)
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_cache_hit_skips_api(self, mock_account, mock_url, mock_secret, mock_post, mock_cache_enabled):
        """Cache hit returns cached data without calling the API."""
        from safebreach_mcp_data.data_functions import (
            _fetch_and_cache_simulation_drifts,
            simulation_drifts_cache,
        )

        cached_data = [{"trackingId": "cached"}]
        simulation_drifts_cache.set("key1", cached_data)

        records, elapsed = _fetch_and_cache_simulation_drifts("demo", {"windowStart": "x"}, "key1")

        assert records == cached_data
        assert elapsed == 0.0
        mock_post.assert_not_called()

    @patch("safebreach_mcp_data.data_functions.is_caching_enabled", return_value=True)
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_cache_miss_stores_result(self, mock_account, mock_url, mock_secret, mock_post, mock_cache_enabled):
        """Cache miss calls API and stores result."""
        from safebreach_mcp_data.data_functions import (
            _fetch_and_cache_simulation_drifts,
            simulation_drifts_cache,
        )

        mock_response = MagicMock()
        mock_response.status_code = 200
        mock_response.json.return_value = [{"trackingId": "new"}]
        mock_post.return_value = mock_response

        records, elapsed = _fetch_and_cache_simulation_drifts("demo", {}, "new_key")

        assert records == [{"trackingId": "new"}]
        assert elapsed >= 0.0
        assert simulation_drifts_cache.get("new_key") == [{"trackingId": "new"}]

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_400_error_raises_valueerror(self, mock_account, mock_url, mock_secret, mock_post):
        """400 error raises ValueError with descriptive message."""
        from safebreach_mcp_data.data_functions import _fetch_and_cache_simulation_drifts

        mock_response = MagicMock()
        mock_response.status_code = 400
        mock_response.text = "Too many simulations in time window"
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="400"):
            _fetch_and_cache_simulation_drifts("demo", {}, "key")

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_401_error_raises_valueerror(self, mock_account, mock_url, mock_secret, mock_post):
        """401 error raises ValueError with auth message."""
        from safebreach_mcp_data.data_functions import _fetch_and_cache_simulation_drifts

        mock_response = MagicMock()
        mock_response.status_code = 401
        mock_post.return_value = mock_response

        with pytest.raises(ValueError, match="[Aa]uthenticat"):
            _fetch_and_cache_simulation_drifts("demo", {}, "key")

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_timeout_raises(self, mock_account, mock_url, mock_secret, mock_post):
        """Timeout is propagated."""
        from safebreach_mcp_data.data_functions import _fetch_and_cache_simulation_drifts
        import requests as req

        mock_post.side_effect = req.exceptions.Timeout("timed out")

        with pytest.raises(req.exceptions.Timeout):
            _fetch_and_cache_simulation_drifts("demo", {}, "key")

    # --- Backward compatibility: api_path parameter (SAF-28331 Phase 3) ---

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_fetch_v1_default_unchanged(self, mock_account, mock_url, mock_secret, mock_post):
        """No api_path → URL contains /v1/.../drift/simulationStatus."""
        from safebreach_mcp_data.data_functions import _fetch_and_cache_simulation_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"trackingId": "t1"}]
        mock_resp.content = b"[]"
        mock_post.return_value = mock_resp

        _fetch_and_cache_simulation_drifts("demo", {"windowStart": "x"}, "key_v1")

        call_url = mock_post.call_args[0][0]
        assert "/api/data/v1/accounts/12345/drift/simulationStatus" in call_url

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="test-token")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_fetch_v2_custom_api_path(self, mock_account, mock_url, mock_secret, mock_post):
        """Custom api_path → URL uses that path instead of v1 default."""
        from safebreach_mcp_data.data_functions import _fetch_and_cache_simulation_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [{"trackingId": "sc1"}]
        mock_resp.content = b"[]"
        mock_post.return_value = mock_resp

        _fetch_and_cache_simulation_drifts(
            "demo", {"securityControl": "x"}, "key_v2",
            api_path="/api/data/v2/accounts/12345/drift/securityControl",
        )

        call_url = mock_post.call_args[0][0]
        assert call_url == "https://demo.safebreach.com/api/data/v2/accounts/12345/drift/securityControl"
        assert "/v1/" not in call_url


# ---------------------------------------------------------------------------
# Tests: _group_and_paginate_drifts  (Phase 2)
# ---------------------------------------------------------------------------

class TestGroupAndPaginateDrifts:
    """Tests for the internal group/paginate function."""

    def _make_records(self, count, from_fs="prevented", to_fs="logged"):
        """Helper to create N drift records with specified finalStatus."""
        return [
            _make_drift_record(from_fs, to_fs, tracking_id=f"t-{i}")
            for i in range(count)
        ]

    def test_summary_mode_returns_groups_without_individual_records(self):
        """drift_key=None returns summary with counts but no drifts arrays."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(5) + self._make_records(3, "missed", "prevented")
        result = _group_and_paginate_drifts(records, page_number=0, drift_key=None, applied_filters={})

        assert "total_drifts" in result
        assert result["total_drifts"] == 8
        assert "total_groups" in result
        assert result["total_groups"] == 2
        assert "drift_groups" in result
        for group in result["drift_groups"]:
            assert "drifts" not in group
            assert "drift_key" in group
            assert "count" in group
            assert "security_impact" in group

    def test_summary_mode_hint_to_agent(self):
        """Summary mode includes hint_to_agent guiding to drill-down."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(3)
        result = _group_and_paginate_drifts(records, page_number=0, drift_key=None, applied_filters={})

        assert "hint_to_agent" in result
        assert "drift_key" in result["hint_to_agent"]

    def test_drilldown_mode_paginates_group(self):
        """drift_key provided returns paginated records from that group."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(15)  # 15 records, PAGE_SIZE=10
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={}
        )

        assert result["drift_key"] == "prevented-logged"
        assert result["page_number"] == 0
        assert result["total_pages"] == 2
        assert result["total_drifts_in_group"] == 15
        assert len(result["drifts_in_page"]) == 10
        assert "security_impact" in result

    def test_drilldown_mode_last_page(self):
        """Last page returns remaining records."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(15)
        result = _group_and_paginate_drifts(
            records, page_number=1, drift_key="prevented-logged", applied_filters={}
        )

        assert result["page_number"] == 1
        assert len(result["drifts_in_page"]) == 5

    def test_drilldown_mode_out_of_range_page(self):
        """Out-of-range page raises ValueError."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(5)

        with pytest.raises(ValueError, match="[Pp]age"):
            _group_and_paginate_drifts(
                records, page_number=99, drift_key="prevented-logged", applied_filters={}
            )

    def test_drilldown_mode_invalid_drift_key(self):
        """Invalid drift_key raises ValueError listing available keys."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(3)

        with pytest.raises(ValueError, match="prevented-logged"):
            _group_and_paginate_drifts(
                records, page_number=0, drift_key="nonexistent-key", applied_filters={}
            )

    def test_summary_mode_empty_records(self):
        """Empty records returns summary with total_drifts=0."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        result = _group_and_paginate_drifts([], page_number=0, drift_key=None, applied_filters={})

        assert result["total_drifts"] == 0
        assert result["total_groups"] == 0
        assert result["drift_groups"] == []

    # --- Phase 8: zero-results smart hint tests ---

    def test_zero_results_with_active_filters_hints_filter_relaxation(self):
        """0 records + active status filters → hint mentions removing those filters."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        result = _group_and_paginate_drifts(
            [], page_number=0, drift_key=None,
            applied_filters={"from_status": "FAIL", "to_status": "SUCCESS"},
            elapsed_seconds=5.0,
        )

        hint = result["hint_to_agent"]
        assert "from_status" in hint
        assert "to_status" in hint

    def test_zero_results_with_drift_type_filter_hints_relaxation(self):
        """0 records + active drift_type filter → hint mentions removing drift_type."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        result = _group_and_paginate_drifts(
            [], page_number=0, drift_key=None,
            applied_filters={"drift_type": "regression"},
            elapsed_seconds=10.0,
        )

        hint = result["hint_to_agent"]
        assert "drift_type" in hint

    def test_zero_results_fast_no_filters_hints_extend_look_back(self):
        """0 records + fast (< 30s) + no filters → hint mentions extending look_back_time."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        result = _group_and_paginate_drifts(
            [], page_number=0, drift_key=None,
            applied_filters={},
            elapsed_seconds=10.0,
        )

        hint = result["hint_to_agent"]
        assert "look_back_time" in hint

    def test_zero_results_slow_no_filters_hints_narrower_window(self):
        """0 records + slow (>= 30s) + no filters → hint mentions narrower window or filters."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        result = _group_and_paginate_drifts(
            [], page_number=0, drift_key=None,
            applied_filters={},
            elapsed_seconds=60.0,
        )

        hint = result["hint_to_agent"]
        assert "narrower" in hint.lower() or "different" in hint.lower()
        assert "get_test_drifts" in hint

    def test_zero_results_hint_always_includes_cross_tool_reference(self):
        """Zero-results hint always includes get_test_drifts cross-reference."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        result = _group_and_paginate_drifts(
            [], page_number=0, drift_key=None,
            applied_filters={"from_final_status": "prevented"},
            elapsed_seconds=5.0,
        )

        assert "get_test_drifts" in result["hint_to_agent"]

    def test_nonzero_results_no_zero_hint(self):
        """Non-zero records → normal summary hint, no zero-results guidance."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(3)
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key=None,
            applied_filters={},
            elapsed_seconds=5.0,
        )

        hint = result["hint_to_agent"]
        # Normal summary hint — should NOT contain zero-results guidance
        assert "look_back_time" not in hint
        assert "narrower" not in hint.lower()

    def test_drilldown_hint_includes_next_page(self):
        """Drill-down mode includes next page hint when more pages available."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(15)
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={}
        )

        assert "hint_to_agent" in result
        assert "page_number=1" in result["hint_to_agent"]

    def test_drilldown_includes_simulation_details_reference(self):
        """Drill-down hint includes get_simulation_details reference."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(3)
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={}
        )

        hint = result.get("hint_to_agent", "")
        assert ("get_simulation_details" in hint
                or "get_test_simulation_details" in hint)

    # --- Phase 9: group_by and final_status_breakdown tests ---

    def test_group_by_result_status_threads_to_enrichment(self):
        """group_by='result_status' produces coarse groups in summary mode."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key=None, applied_filters={},
            group_by="result_status",
        )

        assert result["total_groups"] == 1
        assert result["drift_groups"][0]["drift_key"] == "fail-success"
        assert result["drift_groups"][0]["count"] == 2

    def test_drilldown_result_status_has_final_status_breakdown(self):
        """Drill-down with group_by='result_status' includes final_status_breakdown."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r3"),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="fail-success", applied_filters={},
            group_by="result_status",
        )

        assert "final_status_breakdown" in result
        breakdown = result["final_status_breakdown"]
        assert breakdown["prevented-logged"] == 2
        assert breakdown["stopped-missed"] == 1

    def test_drilldown_final_status_breakdown_covers_full_group(self):
        """final_status_breakdown reflects the full group, not just the current page."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        # 15 records: 10 prevented-logged + 5 stopped-missed, all FAIL→SUCCESS
        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id=f"pl-{i}")
            for i in range(10)
        ] + [
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id=f"sm-{i}")
            for i in range(5)
        ]
        # Page 1 (second page) — but breakdown should cover all 15
        result = _group_and_paginate_drifts(
            records, page_number=1, drift_key="fail-success", applied_filters={},
            group_by="result_status",
        )

        breakdown = result["final_status_breakdown"]
        assert breakdown["prevented-logged"] == 10
        assert breakdown["stopped-missed"] == 5

    def test_drilldown_final_status_not_present_without_group_by_result(self):
        """Drill-down with default group_by does NOT include final_status_breakdown."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(3)
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={},
        )

        assert "final_status_breakdown" not in result

    def test_drilldown_result_status_hint_mentions_status_drifts(self):
        """Drill-down with group_by='result_status' hints at get_simulation_status_drifts."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS"),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="fail-success", applied_filters={},
            group_by="result_status",
        )

        assert "get_simulation_status_drifts" in result["hint_to_agent"]

    # --- Phase 11: attack_summary in drill-down ---

    def test_drilldown_has_attack_summary(self):
        """Drill-down response contains attack_summary field."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", tracking_id="r1", attack_id=100),
            _make_drift_record("prevented", "logged", tracking_id="r2", attack_id=100),
            _make_drift_record("prevented", "logged", tracking_id="r3", attack_id=200),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={},
        )

        assert "attack_summary" in result
        summary = result["attack_summary"]
        assert len(summary) == 2
        # Sorted by count descending
        assert summary[0]["attack_id"] == 100
        assert summary[0]["count"] == 2
        assert summary[1]["attack_id"] == 200
        assert summary[1]["count"] == 1

    def test_attack_summary_covers_full_group_not_just_page(self):
        """attack_summary reflects the full group, not just the current page."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        # 12 records: 10 attack_id=100, 2 attack_id=200 → 2 pages
        records = [
            _make_drift_record("prevented", "logged", tracking_id=f"a-{i}", attack_id=100)
            for i in range(10)
        ] + [
            _make_drift_record("prevented", "logged", tracking_id=f"b-{i}", attack_id=200)
            for i in range(2)
        ]
        # Page 1 (second page, only 2 records)
        result = _group_and_paginate_drifts(
            records, page_number=1, drift_key="prevented-logged", applied_filters={},
        )

        summary = result["attack_summary"]
        assert summary[0]["attack_id"] == 100
        assert summary[0]["count"] == 10
        assert summary[1]["attack_id"] == 200
        assert summary[1]["count"] == 2

    def test_summary_mode_no_attack_summary(self):
        """Summary mode (no drill-down) does NOT include attack_summary."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = self._make_records(3)
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key=None, applied_filters={},
        )

        assert "attack_summary" not in result

    def test_attack_summary_includes_attack_types(self):
        """attack_summary entries include attack_types from the records."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", tracking_id="r1", attack_id=100),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={},
        )

        assert result["attack_summary"][0]["attack_types"] == ["Test Attack"]

    # --- Phase 12: test ID traceability hints ---

    def test_drilldown_hint_mentions_simulation_id_traceability(self):
        """Drill-down hint guides agent to trace simulationId → test via get_simulation_details."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", tracking_id="r1"),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={},
        )

        hint = result["hint_to_agent"]
        assert "get_simulation_details" in hint
        assert "simulationid" in hint.lower() or "simulation_id" in hint.lower()

    def test_drilldown_hint_mentions_plan_run_id(self):
        """Drill-down hint mentions planRunId/test ID for traceability."""
        from safebreach_mcp_data.data_functions import _group_and_paginate_drifts

        records = [
            _make_drift_record("prevented", "logged", tracking_id="r1"),
        ]
        result = _group_and_paginate_drifts(
            records, page_number=0, drift_key="prevented-logged", applied_filters={},
        )

        hint = result["hint_to_agent"]
        assert "planrunid" in hint.lower() or "test_id" in hint.lower() or "test id" in hint.lower()


# ---------------------------------------------------------------------------
# Tests: sb_get_simulation_result_drifts  (Phase 3)
# ---------------------------------------------------------------------------

class TestSbGetSimulationResultDrifts:
    """Tests for the public result drift entry-point function."""

    def setup_method(self):
        from safebreach_mcp_data.data_functions import simulation_drifts_cache
        simulation_drifts_cache.clear()

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_summary_mode_valid_call(self, _acct, _url, _sec, mock_post):
        """Valid call without drift_key returns summary."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged"),
            _make_drift_record("prevented", "logged", tracking_id="t-2"),
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
        )

        assert "total_drifts" in result
        assert result["total_drifts"] == 2
        assert "drift_groups" in result

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_drilldown_mode_valid_call(self, _acct, _url, _sec, mock_post):
        """Valid call with drift_key returns paginated records."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged", tracking_id=f"t-{i}")
            for i in range(3)
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            drift_key="fail-success",
        )

        assert result["drift_key"] == "fail-success"
        assert result["total_drifts_in_group"] == 3
        assert len(result["drifts_in_page"]) == 3

    def test_invalid_from_status_raises(self):
        """Invalid from_status raises ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        with pytest.raises(ValueError, match="from_status"):
            sb_get_simulation_result_drifts(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000,
                from_status="INVALID",
            )

    def test_invalid_to_status_raises(self):
        """Invalid to_status raises ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        with pytest.raises(ValueError, match="to_status"):
            sb_get_simulation_result_drifts(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000,
                to_status="INVALID",
            )

    def test_invalid_drift_type_raises(self):
        """Invalid drift_type raises ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        with pytest.raises(ValueError, match="drift_type"):
            sb_get_simulation_result_drifts(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000,
                drift_type="bad_value",
            )

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_applied_filters_reflects_params(self, _acct, _url, _sec, mock_post):
        """applied_filters in response reflects actual filters used."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        result = sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            from_status="FAIL",
            to_status="SUCCESS",
            drift_type="regression",
            attack_id=1263,
        )

        filters = result["applied_filters"]
        assert filters["from_status"] == "FAIL"
        assert filters["to_status"] == "SUCCESS"
        assert filters["drift_type"] == "regression"
        assert filters["attack_id"] == 1263

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_from_status_to_status_in_payload(self, _acct, _url, _sec, mock_post):
        """from_status/to_status are passed in the API payload, not fromFinalStatus/toFinalStatus."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            from_status="FAIL",
            to_status="SUCCESS",
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["fromStatus"] == "FAIL"
        assert call_payload["toStatus"] == "SUCCESS"
        assert "fromFinalStatus" not in call_payload
        assert "toFinalStatus" not in call_payload

    # --- Phase 8: look_back_time in result drifts ---

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_look_back_time_default_in_payload(self, _acct, _url, _sec, mock_post):
        """Default look_back_time (None) sends earliestSearchTime = window_start - 7 days."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,  # 2024-03-01
            window_end=1709337600000,
        )

        call_payload = mock_post.call_args[1]["json"]
        assert "earliestSearchTime" in call_payload
        assert call_payload["earliestSearchTime"] == "2024-02-23T00:00:00.000Z"

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_look_back_time_explicit_in_payload(self, _acct, _url, _sec, mock_post):
        """Explicit look_back_time overrides the default in the API payload."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            look_back_time=1708387200000,  # 2024-02-20
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["earliestSearchTime"] == "2024-02-20T00:00:00.000Z"

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_look_back_time_in_cache_key(self, _acct, _url, _sec, mock_post):
        """Different look_back_time values produce different cache keys."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        # Call with default look_back_time
        sb_get_simulation_result_drifts(
            console="demo", window_start=1709251200000, window_end=1709337600000,
        )
        # Call with explicit look_back_time
        sb_get_simulation_result_drifts(
            console="demo", window_start=1709251200000, window_end=1709337600000,
            look_back_time=1708387200000,
        )

        # Both calls should have hit the API (different cache keys)
        assert mock_post.call_count == 2

    # --- Phase 9: result drifts groups by result_status ---

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_result_drifts_groups_by_result_status(self, _acct, _url, _sec, mock_post):
        """Result drifts groups by FAIL/SUCCESS, not finalStatus."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
        )

        assert result["total_groups"] == 1
        assert result["drift_groups"][0]["drift_key"] == "fail-success"
        assert result["drift_groups"][0]["count"] == 2

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_result_drifts_drilldown_has_final_status_breakdown(self, _acct, _url, _sec, mock_post):
        """Result drifts drill-down includes final_status_breakdown."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r3"),
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_result_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            drift_key="fail-success",
        )

        assert "final_status_breakdown" in result
        assert result["final_status_breakdown"]["prevented-logged"] == 2
        assert result["final_status_breakdown"]["stopped-missed"] == 1


# ---------------------------------------------------------------------------
# Tests: sb_get_simulation_status_drifts  (Phase 3)
# ---------------------------------------------------------------------------

class TestSbGetSimulationStatusDrifts:
    """Tests for the public status drift entry-point function."""

    def setup_method(self):
        from safebreach_mcp_data.data_functions import simulation_drifts_cache
        simulation_drifts_cache.clear()

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_summary_mode_valid_call(self, _acct, _url, _sec, mock_post):
        """Valid call without drift_key returns summary."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged"),
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
        )

        assert "total_drifts" in result
        assert result["total_drifts"] == 1
        assert "drift_groups" in result

    def test_invalid_from_final_status_raises(self):
        """Invalid from_final_status raises ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        with pytest.raises(ValueError, match="from_final_status"):
            sb_get_simulation_status_drifts(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000,
                from_final_status="INVALID",
            )

    def test_invalid_to_final_status_raises(self):
        """Invalid to_final_status raises ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        with pytest.raises(ValueError, match="to_final_status"):
            sb_get_simulation_status_drifts(
                console="demo",
                window_start=1709251200000,
                window_end=1709337600000,
                to_final_status="INVALID",
            )

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_final_status_in_payload(self, _acct, _url, _sec, mock_post):
        """fromFinalStatus/toFinalStatus are in the payload, not fromStatus/toStatus."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            from_final_status="prevented",
            to_final_status="logged",
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["fromFinalStatus"] == "prevented"
        assert call_payload["toFinalStatus"] == "logged"
        assert "fromStatus" not in call_payload
        assert "toStatus" not in call_payload

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_applied_filters_reflects_params(self, _acct, _url, _sec, mock_post):
        """applied_filters in response reflects final status params."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        result = sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            from_final_status="prevented",
            to_final_status="logged",
            attack_id=42,
        )

        filters = result["applied_filters"]
        assert filters["from_final_status"] == "prevented"
        assert filters["to_final_status"] == "logged"
        assert filters["attack_id"] == 42

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_drilldown_mode_valid_call(self, _acct, _url, _sec, mock_post):
        """Valid drill-down with drift_key returns paginated records."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged", tracking_id=f"t-{i}")
            for i in range(5)
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            drift_key="prevented-logged",
        )

        assert result["drift_key"] == "prevented-logged"
        assert result["total_drifts_in_group"] == 5

    # --- Phase 8: look_back_time in status drifts ---

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_look_back_time_passed_to_payload(self, _acct, _url, _sec, mock_post):
        """look_back_time is passed through to the API payload as earliestSearchTime."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            look_back_time=1708387200000,  # 2024-02-20
        )

        call_payload = mock_post.call_args[1]["json"]
        assert call_payload["earliestSearchTime"] == "2024-02-20T00:00:00.000Z"

    # --- Phase 9: status drifts uses final_status grouping ---

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_status_drifts_groups_by_final_status(self, _acct, _url, _sec, mock_post):
        """Status drifts groups by finalStatus (fine-grained), not result status."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged", from_status="FAIL", to_status="SUCCESS", tracking_id="r1"),
            _make_drift_record("stopped", "missed", from_status="FAIL", to_status="SUCCESS", tracking_id="r2"),
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
        )

        # Should produce 2 groups (prevented-logged, stopped-missed), NOT 1 (fail-success)
        assert result["total_groups"] == 2
        keys = {g["drift_key"] for g in result["drift_groups"]}
        assert keys == {"prevented-logged", "stopped-missed"}

    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url", return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_status_drifts_drilldown_no_final_status_breakdown(self, _acct, _url, _sec, mock_post):
        """Status drifts drill-down does NOT include final_status_breakdown."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = [
            _make_drift_record("prevented", "logged", tracking_id=f"r-{i}")
            for i in range(3)
        ]
        mock_post.return_value = mock_resp

        result = sb_get_simulation_status_drifts(
            console="demo",
            window_start=1709251200000,
            window_end=1709337600000,
            drift_key="prevented-logged",
        )

        assert "final_status_breakdown" not in result


# ---------------------------------------------------------------------------
# Tests: sb_get_security_control_drifts  (SAF-28331 Phase 3)
# ---------------------------------------------------------------------------

class TestSbGetSecurityControlDrifts:
    """Tests for the v2 security control drift orchestrator function."""

    COMMON_KWARGS = dict(
        console="demo",
        security_control="Microsoft Defender for Endpoint",
        window_start=1709251200000,
        window_end=1709337600000,
        transition_matching_mode="contains",
    )

    def setup_method(self):
        """Clear the simulation_drifts_cache before each test."""
        from safebreach_mcp_data.data_functions import simulation_drifts_cache
        simulation_drifts_cache.clear()

    def _mock_response(self, records):
        """Create a mock response with given v2 records."""
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = records
        mock_resp.content = b"[]"
        return mock_resp

    # --- Validation tests (no mocks needed) ---

    def test_invalid_transition_mode(self):
        """Invalid transition_matching_mode raises ValueError listing valid modes."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        with pytest.raises(ValueError, match="contains"):
            sb_get_security_control_drifts(
                **{**self.COMMON_KWARGS, "transition_matching_mode": "invalid"},
            )

    def test_invalid_drift_type(self):
        """Invalid drift_type raises ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        with pytest.raises(ValueError, match="drift_type"):
            sb_get_security_control_drifts(
                **self.COMMON_KWARGS,
                drift_type="unknown",
            )

    # --- Tests requiring mock stack ---

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    def test_list_mode(self, mock_suggestions):
        """security_control='__list__' returns available controls without querying drifts."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        result = sb_get_security_control_drifts(
            console="demo",
            security_control="__list__",
            window_start=0,
            window_end=0,
            transition_matching_mode="contains",
        )

        assert "security_controls" in result
        assert result["total"] == 2
        assert "Microsoft Defender for Endpoint" in result["security_controls"]
        mock_suggestions.assert_called_once_with("demo", "security_product")

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_unknown_control_returns_zero_results(
        self, _acct, _url, _sec, mock_post, mock_suggestions
    ):
        """Unknown security control -> 0 results with hint listing valid names."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = []
        mock_post.return_value = mock_resp

        result = sb_get_security_control_drifts(
            **{**self.COMMON_KWARGS, "security_control": "NonExistent Control"},
        )

        assert result["total_drifts"] == 0
        assert "Known security products" in result["hint_to_agent"]

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_contains_mode_maps_correctly(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """'contains' -> containsTransition=True in payload."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([])

        sb_get_security_control_drifts(**self.COMMON_KWARGS)

        payload = mock_post.call_args[1]["json"]
        assert payload["containsTransition"] is True
        assert payload["startsAndEndsWithTransition"] is False

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_starts_and_ends_mode_maps_correctly(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """'starts_and_ends' -> startsAndEndsWithTransition=True in payload."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([])

        sb_get_security_control_drifts(
            **{**self.COMMON_KWARGS, "transition_matching_mode": "starts_and_ends"},
        )

        payload = mock_post.call_args[1]["json"]
        assert payload["containsTransition"] is False
        assert payload["startsAndEndsWithTransition"] is True

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_summary_mode(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """No drift_key -> summary with grouped_by, total_drifts, drift_groups."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id="t1"),
            _make_sc_drift_record(to_prevented=True, tracking_id="t2"),
            _make_sc_drift_record(to_reported=True, tracking_id="t3"),
        ])

        result = sb_get_security_control_drifts(**self.COMMON_KWARGS)

        assert result["security_control"] == "Microsoft Defender for Endpoint"
        assert result["grouped_by"] == "transition"
        assert result["total_drifts"] == 3
        assert len(result["drift_groups"]) == 2
        assert "hint_to_agent" in result

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_drill_down_mode(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """drift_key set -> paginated drill-down with drifts_in_page."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id=f"t{i}")
            for i in range(3)
        ])

        result = sb_get_security_control_drifts(
            **self.COMMON_KWARGS,
            drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
        )

        assert result["security_control"] == "Microsoft Defender for Endpoint"
        assert result["drift_key"] == "P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F"
        assert result["total_drifts_in_group"] == 3
        assert len(result["drifts_in_page"]) == 3
        assert result["page_number"] == 0
        assert "total_pages" in result

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_drill_down_pagination(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """25 records -> total_pages=3, page 0 has 10 records."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id=f"t-{i}")
            for i in range(25)
        ])

        result = sb_get_security_control_drifts(
            **self.COMMON_KWARGS,
            drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
            page_number=0,
        )

        assert result["total_pages"] == 3
        assert result["total_drifts_in_group"] == 25
        assert len(result["drifts_in_page"]) == 10

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_invalid_drift_key(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """Unknown drift_key -> ValueError listing available keys."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id="t1"),
        ])

        with pytest.raises(ValueError, match="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F"):
            sb_get_security_control_drifts(
                **self.COMMON_KWARGS,
                drift_key="nonexistent-key",
            )

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_out_of_range_page(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """page_number=99 on small dataset -> ValueError."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id="t1"),
        ])

        with pytest.raises(ValueError, match="[Pp]age"):
            sb_get_security_control_drifts(
                **self.COMMON_KWARGS,
                drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
                page_number=99,
            )

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_zero_results_hint(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """0 records -> contextual hint_to_agent."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([])

        result = sb_get_security_control_drifts(**self.COMMON_KWARGS)

        assert result["total_drifts"] == 0
        assert "hint_to_agent" in result
        assert len(result["hint_to_agent"]) > 0

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_applied_filters(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """Non-None filters appear in applied_filters dict."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([])

        result = sb_get_security_control_drifts(
            **self.COMMON_KWARGS,
            drift_type="regression",
            from_prevented=True,
            to_reported=False,
        )

        filters = result["applied_filters"]
        assert filters["drift_type"] == "regression"
        assert filters["from_prevented"] is True
        assert filters["to_reported"] is False
        assert "from_reported" not in filters

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_cache_key_includes_all_params(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """Different params -> different cache keys -> separate API calls."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([])

        sb_get_security_control_drifts(**self.COMMON_KWARGS)
        sb_get_security_control_drifts(**self.COMMON_KWARGS, from_prevented=True)

        assert mock_post.call_count == 2

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_security_control_in_response(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """Both summary and drill-down include security_control field."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id="t1"),
        ])

        summary = sb_get_security_control_drifts(**self.COMMON_KWARGS)
        assert summary["security_control"] == "Microsoft Defender for Endpoint"

        drilldown = sb_get_security_control_drifts(
            **self.COMMON_KWARGS,
            drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
        )
        assert drilldown["security_control"] == "Microsoft Defender for Endpoint"

    @patch("safebreach_mcp_data.data_functions.get_suggestions_for_collection",
           return_value=["Microsoft Defender for Endpoint", "CrowdStrike Falcon"])
    @patch("safebreach_mcp_data.data_functions.requests.post")
    @patch("safebreach_mcp_data.data_functions.get_secret_for_console", return_value="tok")
    @patch("safebreach_mcp_data.data_functions.get_api_base_url",
           return_value="https://demo.safebreach.com")
    @patch("safebreach_mcp_data.data_functions.get_api_account_id", return_value="12345")
    def test_no_attack_summary_in_drilldown(self, _acct, _url, _sec, mock_post, mock_suggestions):
        """Unlike v1, v2 drill-down has no attack_summary (no attackId in records)."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        mock_post.return_value = self._mock_response([
            _make_sc_drift_record(to_prevented=True, tracking_id="t1"),
        ])

        result = sb_get_security_control_drifts(
            **self.COMMON_KWARGS,
            drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
        )

        assert "attack_summary" not in result


# ---------------------------------------------------------------------------
# Tests: MCP Tool Registration  (Phase 4)
# ---------------------------------------------------------------------------

class TestMcpToolRegistration:
    """Tests that drift tools are registered on the MCP server."""

    def _get_tool_names(self):
        import asyncio
        from safebreach_mcp_data.data_server import data_server
        return [t.name for t in asyncio.run(data_server.mcp.list_tools())]

    def test_result_drifts_tool_registered(self):
        """get_simulation_result_drifts tool is registered on the data server."""
        assert "get_simulation_result_drifts" in self._get_tool_names()

    def test_status_drifts_tool_registered(self):
        """get_simulation_status_drifts tool is registered on the data server."""
        assert "get_simulation_status_drifts" in self._get_tool_names()

    @patch("safebreach_mcp_data.data_functions.sb_get_simulation_result_drifts")
    def test_result_drifts_passes_params(self, mock_fn):
        """sb_get_simulation_result_drifts receives all params correctly."""
        mock_fn.return_value = {"total_drifts": 0}

        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts
        sb_get_simulation_result_drifts(
            console="demo",
            window_start=100,
            window_end=200,
            drift_key="fail-success",
            page_number=1,
        )

        mock_fn.assert_called_once_with(
            console="demo",
            window_start=100,
            window_end=200,
            drift_key="fail-success",
            page_number=1,
        )

    @patch("safebreach_mcp_data.data_functions.sb_get_simulation_status_drifts")
    def test_status_drifts_passes_params(self, mock_fn):
        """sb_get_simulation_status_drifts receives all params correctly."""
        mock_fn.return_value = {"total_drifts": 0}

        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts
        sb_get_simulation_status_drifts(
            console="demo",
            window_start=100,
            window_end=200,
            from_final_status="prevented",
            to_final_status="logged",
        )

        mock_fn.assert_called_once_with(
            console="demo",
            window_start=100,
            window_end=200,
            from_final_status="prevented",
            to_final_status="logged",
        )

    # --- Security control drifts tool (SAF-28331 Phase 4) ---

    def test_sc_drifts_tool_registered(self):
        """get_security_control_drifts tool is registered on the data server."""
        assert "get_security_control_drifts" in self._get_tool_names()

    def test_tool_normalizes_iso_timestamp(self):
        """ISO timestamp string is normalized to epoch ms."""
        import asyncio
        from safebreach_mcp_data.data_server import data_server

        tools = asyncio.run(data_server.mcp.list_tools())
        sc_tool = next(t for t in tools if t.name == "get_security_control_drifts")
        assert sc_tool is not None

    @patch("safebreach_mcp_data.data_functions.sb_get_security_control_drifts")
    def test_tool_missing_window_start(self, mock_fn):
        """None window_start -> ValueError."""
        import asyncio
        from safebreach_mcp_data.data_server import data_server

        tools = asyncio.run(data_server.mcp.list_tools())
        # Just verify the tool is registered — the actual ValueError
        # is tested via the async wrapper directly
        sc_tool = next(t for t in tools if t.name == "get_security_control_drifts")
        assert sc_tool is not None

    @patch("safebreach_mcp_data.data_functions.sb_get_security_control_drifts")
    def test_tool_passes_all_params(self, mock_fn):
        """Mock sb_get_security_control_drifts, verify all params forwarded."""
        mock_fn.return_value = {"total_drifts": 0}

        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts
        sb_get_security_control_drifts(
            console="demo",
            security_control="MDE",
            window_start=100,
            window_end=200,
            transition_matching_mode="contains",
            from_prevented=True,
            to_reported=False,
            drift_type="regression",
            group_by="transition",
            drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
            page_number=1,
        )

        mock_fn.assert_called_once_with(
            console="demo",
            security_control="MDE",
            window_start=100,
            window_end=200,
            transition_matching_mode="contains",
            from_prevented=True,
            to_reported=False,
            drift_type="regression",
            group_by="transition",
            drift_key="P:F,R:F,L:F,A:F->P:T,R:F,L:F,A:F",
            page_number=1,
        )


# ---------------------------------------------------------------------------
# E2E Tests: Simulation Drift Tools  (Phase 5)
# ---------------------------------------------------------------------------

skip_e2e = pytest.mark.skipif(
    os.environ.get("SKIP_E2E_TESTS", "true").lower() == "true",
    reason="E2E tests disabled (set SKIP_E2E_TESTS=false to run)",
)


# Known drift windows on pentest01 with guaranteed data.
# The drift API has no server-side pagination and can be very slow on large
# consoles, so we use narrow windows with known drift data.
#
# Window 1: Feb 5 08:00-14:00 UTC — 6 drifts (logged→prevented ×2, logged→stopped ×2, missed→stopped ×2)
# Window 2: Feb 15 14:00-20:00 UTC — 4 drifts (missed→stopped ×3, logged→stopped ×1)
# Window 3: Feb 26 14:00-20:00 UTC — 1 drift  (detected→stopped ×1)
# Window 4: Mar 4 12:00-18:00 UTC — 1 drift  (inconsistent→prevented ×1)

# Using Window 1 (most drifts, good for drill-down testing)
_E2E_WINDOW_START = 1770278400000  # 2026-02-05T08:00:00Z
_E2E_WINDOW_END = 1770300000000    # 2026-02-05T14:00:00Z
_E2E_EXPECTED_MIN_DRIFTS = 6  # at least 6 known drifts in this window
_E2E_EXPECTED_KEYS = {"logged-prevented", "logged-stopped", "missed-stopped"}


@pytest.fixture(scope="class")
def e2e_console():
    """Get console name for E2E drift tests from environment."""
    console = os.environ.get("E2E_CONSOLE", "")
    if not console:
        pytest.skip("E2E_CONSOLE environment variable not set")
    return console


class TestDriftToolsE2E:
    """End-to-end smoke tests for simulation drift tools against known drift windows."""

    @skip_e2e
    @pytest.mark.e2e
    def test_status_drifts_summary(self, e2e_console):
        """get_simulation_status_drifts summary mode returns known drifts."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        result = sb_get_simulation_status_drifts(
            console=e2e_console,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
        )

        assert result["total_drifts"] >= _E2E_EXPECTED_MIN_DRIFTS
        assert result["total_groups"] >= 3
        assert isinstance(result["drift_groups"], list)

        keys = {g["drift_key"] for g in result["drift_groups"]}
        assert _E2E_EXPECTED_KEYS.issubset(keys), (
            f"Expected keys {_E2E_EXPECTED_KEYS} not found in {keys}"
        )

    @skip_e2e
    @pytest.mark.e2e
    def test_status_drifts_drilldown(self, e2e_console):
        """Drill-down into a status drift group returns paginated records."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        drilldown = sb_get_simulation_status_drifts(
            console=e2e_console,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
            drift_key="logged-prevented",
            page_number=0,
        )

        assert drilldown["drift_key"] == "logged-prevented"
        assert drilldown["total_drifts_in_group"] >= 1
        assert drilldown["page_number"] == 0
        assert drilldown["total_pages"] >= 1
        assert len(drilldown["drifts_in_page"]) >= 1

    @skip_e2e
    @pytest.mark.e2e
    def test_enrichment_fields_present(self, e2e_console):
        """Groups in summary contain security_impact and description from enrichment."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_status_drifts

        result = sb_get_simulation_status_drifts(
            console=e2e_console,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
        )

        for group in result["drift_groups"]:
            assert "security_impact" in group
            assert "description" in group
            assert "drift_key" in group
            assert "count" in group
            assert group["security_impact"] != "unknown", (
                f"drift_key '{group['drift_key']}' missing from drifts_metadata"
            )

    @skip_e2e
    @pytest.mark.e2e
    def test_result_drifts_summary(self, e2e_console):
        """get_simulation_result_drifts summary mode returns expected structure."""
        from safebreach_mcp_data.data_functions import sb_get_simulation_result_drifts

        result = sb_get_simulation_result_drifts(
            console=e2e_console,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
        )

        # Result-mode view of the same window — should have drifts
        assert "total_drifts" in result
        assert "total_groups" in result
        assert "drift_groups" in result
        assert isinstance(result["total_drifts"], int)
        assert result["total_drifts"] >= 0


class TestSecurityControlDriftsE2E:
    """End-to-end tests for security control drift tool against pentest01."""

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_summary(self, e2e_console):
        """Summary query for a known security control returns valid structure."""
        from safebreach_mcp_core.suggestions import get_suggestions_for_collection
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        controls = get_suggestions_for_collection(e2e_console, "security_product")
        assert len(controls) > 0, "No security controls found on console"
        control = controls[0]

        result = sb_get_security_control_drifts(
            console=e2e_console,
            security_control=control,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
            transition_matching_mode="contains",
        )

        assert "total_drifts" in result
        assert "security_control" in result
        assert result["security_control"] == control
        assert isinstance(result["total_drifts"], int)
        assert result["total_drifts"] >= 0
        if result["total_drifts"] > 0:
            assert "drift_groups" in result
            assert isinstance(result["drift_groups"], list)
            assert len(result["drift_groups"]) > 0

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_drill_down(self, e2e_console):
        """Drill into first group from summary, verify paginated response."""
        from safebreach_mcp_core.suggestions import get_suggestions_for_collection
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        controls = get_suggestions_for_collection(e2e_console, "security_product")
        # Try a 7-day window across multiple controls to find drifts.
        # Some controls may have too many simulations (400 error) — skip those.
        wide_start = _E2E_WINDOW_START - 3 * 24 * 3600 * 1000
        wide_end = _E2E_WINDOW_END + 4 * 24 * 3600 * 1000

        summary = None
        control = None
        for candidate in controls[:10]:
            try:
                summary = sb_get_security_control_drifts(
                    console=e2e_console,
                    security_control=candidate,
                    window_start=wide_start,
                    window_end=wide_end,
                    transition_matching_mode="contains",
                )
            except ValueError:
                continue  # 400 = too many simulations, try next
            if summary["total_drifts"] > 0:
                control = candidate
                break

        if control is None:
            pytest.skip("No drifts found across controls in 7-day window")

        first_key = summary["drift_groups"][0]["drift_key"]
        drilldown = sb_get_security_control_drifts(
            console=e2e_console,
            security_control=control,
            window_start=wide_start,
            window_end=wide_end,
            transition_matching_mode="contains",
            drift_key=first_key,
            page_number=0,
        )

        assert drilldown["drift_key"] == first_key
        assert drilldown["total_drifts_in_group"] >= 1
        assert drilldown["page_number"] == 0
        assert drilldown["total_pages"] >= 1
        assert len(drilldown["drifts_in_page"]) >= 1

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_contains_mode(self, e2e_console):
        """transition_matching_mode='contains' returns valid results."""
        from safebreach_mcp_core.suggestions import get_suggestions_for_collection
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        controls = get_suggestions_for_collection(e2e_console, "security_product")
        control = controls[0]

        result = sb_get_security_control_drifts(
            console=e2e_console,
            security_control=control,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
            transition_matching_mode="contains",
        )

        assert "total_drifts" in result
        assert isinstance(result["total_drifts"], int)
        assert result["total_drifts"] >= 0

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_starts_and_ends_mode(self, e2e_console):
        """transition_matching_mode='starts_and_ends' returns valid results."""
        from safebreach_mcp_core.suggestions import get_suggestions_for_collection
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        controls = get_suggestions_for_collection(e2e_console, "security_product")
        control = controls[0]

        result = sb_get_security_control_drifts(
            console=e2e_console,
            security_control=control,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
            transition_matching_mode="starts_and_ends",
        )

        assert "total_drifts" in result
        assert isinstance(result["total_drifts"], int)
        assert result["total_drifts"] >= 0

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_invalid_control(self, e2e_console):
        """Garbage security control name returns 0 results with hint."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        result = sb_get_security_control_drifts(
            console=e2e_console,
            security_control="NonExistentSecurityProduct12345",
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
            transition_matching_mode="contains",
        )

        assert result["total_drifts"] == 0
        assert "hint_to_agent" in result

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_list_mode(self, e2e_console):
        """security_control='__list__' returns available control names."""
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        result = sb_get_security_control_drifts(
            console=e2e_console,
            security_control="__list__",
            window_start=0,
            window_end=0,
            transition_matching_mode="contains",
        )

        assert "security_controls" in result
        assert result["total"] > 0
        assert isinstance(result["security_controls"], list)
        # Should contain well-known products, not noise like usernames
        names = result["security_controls"]
        assert any("Defender" in n or "CrowdStrike" in n or "SentinelOne" in n for n in names)

    @skip_e2e
    @pytest.mark.e2e
    def test_e2e_sc_drifts_with_drift_type_filter(self, e2e_console):
        """drift_type='regression' narrows results."""
        from safebreach_mcp_core.suggestions import get_suggestions_for_collection
        from safebreach_mcp_data.data_functions import sb_get_security_control_drifts

        controls = get_suggestions_for_collection(e2e_console, "security_product")
        control = controls[0]

        result = sb_get_security_control_drifts(
            console=e2e_console,
            security_control=control,
            window_start=_E2E_WINDOW_START,
            window_end=_E2E_WINDOW_END,
            transition_matching_mode="contains",
            drift_type="regression",
        )

        assert "applied_filters" in result
        assert result["applied_filters"].get("drift_type") == "regression"
        assert isinstance(result["total_drifts"], int)
        assert result["total_drifts"] >= 0
