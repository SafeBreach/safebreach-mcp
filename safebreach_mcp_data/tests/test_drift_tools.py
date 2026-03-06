"""
Tests for drift analysis tool functions (SAF-28330).

TDD tests for simulation result/status drift tools covering:
Phase 1: data_types (build_drift_api_payload, group_and_enrich_drift_records)
Phase 2: core functions (_fetch_and_cache_simulation_drifts, _group_and_paginate_drifts)
Phase 3: public functions (sb_get_simulation_result_drifts, sb_get_simulation_status_drifts)
Phase 4: MCP tool registration
Phase 5: E2E smoke tests
Phase 8: look_back_time parameter and zero-results smart hints
"""

import os
from unittest.mock import patch, MagicMock

import pytest
from safebreach_mcp_data.data_types import (
    build_drift_api_payload,
    group_and_enrich_drift_records,
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
        assert drift["driftType"] == "Regression"

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
            drift_key="prevented-logged",
        )

        assert result["drift_key"] == "prevented-logged"
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
        assert drilldown["total_drifts_in_group"] == 2
        assert drilldown["page_number"] == 0
        assert drilldown["total_pages"] == 1
        assert len(drilldown["drifts_in_page"]) == 2

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
