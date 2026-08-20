"""
Tests for SafeBreach Config Types - Scenario Transforms

TDD RED phase: These tests define the expected behavior of scenario transform,
filter, ordering, and pagination functions. All tests should fail initially
because the functions do not exist yet in config_types.py.
"""

import pytest
from safebreach_mcp_config.config_types import (
    compute_is_ready_to_run,
    get_reduced_scenario_mapping,
    get_reduced_plan_mapping,
    filter_scenarios_by_criteria,
    apply_scenario_ordering,
    paginate_scenarios,
)


# --- Fixtures ---

@pytest.fixture
def sample_scenario_ready():
    """A scenario where ALL steps have real targetFilter AND attackerFilter criteria."""
    return {
        "id": "3b8eade5-9285-43b8-b3e7-6350420983a5",
        "name": "Step 1 - Fortify your Network Perimeter",
        "description": "Test scenario that is ready to run",
        "createdBy": "SafeBreach",
        "recommended": True,
        "categories": [4],
        "tags": ["network", "perimeter"],
        "createdAt": "2025-01-01T00:00:00.000Z",
        "updatedAt": "2025-06-01T00:00:00.000Z",
        "steps": [
            {
                "name": "Exploitation",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {
                    "os": {
                        "name": "os",
                        "values": ["WINDOWS", "MAC", "LINUX"],
                        "operator": "is"
                    }
                },
                "attackerFilter": {
                    "role": {
                        "name": "role",
                        "values": ["isInfiltration"],
                        "operator": "is"
                    }
                },
                "attacksFilter": {}
            },
            {
                "name": "Brute Force",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {
                    "os": {
                        "name": "os",
                        "values": ["WINDOWS", "LINUX"],
                        "operator": "is"
                    }
                },
                "attackerFilter": {
                    "role": {
                        "name": "role",
                        "values": ["isInfiltration"],
                        "operator": "is"
                    }
                },
                "attacksFilter": {}
            }
        ],
        "order": None,
        "actions": None,
        "edges": None,
        "phases": {}
    }


@pytest.fixture
def sample_scenario_not_ready():
    """A scenario where steps have empty simulator values (NOT ready to run)."""
    return {
        "id": "66d023d9-cc16-4c8d-9f29-7fb5e6db91af",
        "name": "AI Generated Malware",
        "description": "Scenario with empty simulator filter values",
        "createdBy": "SafeBreach",
        "recommended": False,
        "categories": [2],
        "tags": None,
        "createdAt": "2025-03-01T00:00:00.000Z",
        "updatedAt": "2025-07-01T00:00:00.000Z",
        "steps": [
            {
                "name": "Host Level Actions",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {
                    "simulators": {
                        "name": "simulators",
                        "values": [],
                        "operator": "is"
                    }
                },
                "attackerFilter": {
                    "simulators": {
                        "name": "simulators",
                        "values": [],
                        "operator": "is"
                    }
                },
                "attacksFilter": {}
            },
            {
                "name": "Malware Transfer",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {
                    "simulators": {
                        "name": "simulators",
                        "values": [],
                        "operator": "is"
                    }
                },
                "attackerFilter": {
                    "simulators": {
                        "name": "simulators",
                        "values": [],
                        "operator": "is"
                    }
                },
                "attacksFilter": {}
            }
        ],
        "order": None,
        "actions": None,
        "edges": None,
        "phases": {}
    }


@pytest.fixture
def sample_categories_map():
    """Category ID to name mapping."""
    return {
        2: "Known Threats Series",
        3: "Threat Groups",
        4: "Baseline Scenarios",
        11: "Getting Started",
    }


@pytest.fixture
def sample_reduced_scenarios():
    """Pre-transformed reduced scenario dicts for filter/ordering/pagination tests."""
    return [
        {
            "id": "aaa-111",
            "name": "CISA Alert AA24 (StopRansomware: Akira Ransomware)",
            "description": "Based on a joint Cybersecurity Advisory",
            "source_type": "oob",
            "createdBy": "SafeBreach",
            "recommended": True,
            "category_names": ["Known Threats Series"],
            "tags": ["ransomware", "Akira"],
            "step_count": 5,
            "is_ready_to_run": False,
            "createdAt": "2025-11-14T11:29:13.000Z",
            "updatedAt": "2026-01-22T14:25:18.000Z",
        },
        {
            "id": "bbb-222",
            "name": "KongTuke",
            "description": None,
            "source_type": "oob",
            "createdBy": "SafeBreach",
            "recommended": False,
            "category_names": ["Threat Groups"],
            "tags": ["KongTuke"],
            "step_count": 4,
            "is_ready_to_run": False,
            "createdAt": "2026-02-10T09:42:06.000Z",
            "updatedAt": "2026-02-10T09:42:06.000Z",
        },
        {
            "id": "ccc-333",
            "name": "Step 1 - Fortify your Network Perimeter",
            "description": "Fortify network perimeter defenses",
            "source_type": "oob",
            "createdBy": "SafeBreach",
            "recommended": False,
            "category_names": ["Baseline Scenarios"],
            "tags": ["network", "perimeter"],
            "step_count": 5,
            "is_ready_to_run": True,
            "createdAt": "2024-06-01T00:00:00.000Z",
            "updatedAt": "2025-12-01T00:00:00.000Z",
        },
        {
            "id": "444",
            "name": "Custom Data Exfil Scenario",
            "description": "A custom scenario for testing data exfiltration",
            "source_type": "custom",
            "createdBy": None,
            "recommended": False,
            "category_names": [],
            "tags": [],
            "step_count": 2,
            "is_ready_to_run": False,
            "createdAt": "2026-03-01T00:00:00.000Z",
            "updatedAt": "2026-03-15T00:00:00.000Z",
        },
        {
            "id": "eee-555",
            "name": "Email - Attachment - Infiltration - Baseline",
            "description": "Email attachment infiltration baseline scenario",
            "source_type": "oob",
            "createdBy": "SafeBreach",
            "recommended": True,
            "category_names": ["Getting Started"],
            "tags": ["email", "infiltration"],
            "step_count": 1,
            "is_ready_to_run": True,
            "createdAt": "2025-01-15T00:00:00.000Z",
            "updatedAt": "2025-09-01T00:00:00.000Z",
        },
    ]


# --- Test Classes ---

class TestComputeIsReadyToRun:
    """Test the compute_is_ready_to_run function."""

    def test_ready_all_steps_have_os_role_criteria(self, sample_scenario_ready):
        assert compute_is_ready_to_run(sample_scenario_ready) is True

    def test_not_ready_empty_simulator_values(self, sample_scenario_not_ready):
        assert compute_is_ready_to_run(sample_scenario_not_ready) is False

    def test_not_ready_no_steps(self):
        scenario = {"steps": []}
        assert compute_is_ready_to_run(scenario) is False

    def test_not_ready_mixed_steps(self, sample_scenario_ready):
        """One step has real criteria, another has empty simulators."""
        scenario = sample_scenario_ready.copy()
        scenario["steps"] = [
            sample_scenario_ready["steps"][0],
            {
                "name": "Bad Step",
                "draft": False,
                "systemFilter": {},
                "targetFilter": {
                    "simulators": {"name": "simulators", "values": [], "operator": "is"}
                },
                "attackerFilter": {
                    "simulators": {"name": "simulators", "values": [], "operator": "is"}
                },
                "attacksFilter": {}
            }
        ]
        assert compute_is_ready_to_run(scenario) is False

    def test_not_ready_target_only_no_attacker(self):
        """Step has targetFilter with real values but empty attackerFilter."""
        scenario = {
            "steps": [
                {
                    "name": "Partial Step",
                    "draft": False,
                    "systemFilter": {},
                    "targetFilter": {
                        "os": {"name": "os", "values": ["WINDOWS"], "operator": "is"}
                    },
                    "attackerFilter": {},
                    "attacksFilter": {}
                }
            ]
        }
        assert compute_is_ready_to_run(scenario) is False


class TestGetReducedScenarioMapping:
    """Test the get_reduced_scenario_mapping function."""

    def test_all_expected_keys_present(self, sample_scenario_ready, sample_categories_map):
        result = get_reduced_scenario_mapping(sample_scenario_ready, sample_categories_map)
        expected_keys = {
            "id", "source_type", "name", "description", "createdBy", "recommended",
            "category_names", "tags", "step_count", "total_attack_count", "is_ready_to_run",
            "createdAt", "updatedAt", "userId", "originalScenarioId"
        }
        assert set(result.keys()) == expected_keys
        assert result["source_type"] == "oob"

    def test_description_truncation(self, sample_categories_map):
        scenario = {
            "id": "trunc-test",
            "name": "Truncation Test",
            "description": "A" * 300,
            "createdBy": "SafeBreach",
            "recommended": False,
            "categories": [2],
            "tags": None,
            "createdAt": "2025-01-01T00:00:00.000Z",
            "updatedAt": "2025-01-01T00:00:00.000Z",
            "steps": [],
        }
        result = get_reduced_scenario_mapping(scenario, sample_categories_map)
        assert len(result["description"]) == 203  # 200 + "..."
        assert result["description"].endswith("...")

    def test_category_names_resolved(self, sample_scenario_ready, sample_categories_map):
        result = get_reduced_scenario_mapping(sample_scenario_ready, sample_categories_map)
        assert result["category_names"] == ["Baseline Scenarios"]

    def test_step_count_computed(self, sample_scenario_ready, sample_categories_map):
        result = get_reduced_scenario_mapping(sample_scenario_ready, sample_categories_map)
        assert result["step_count"] == 2

    def test_null_tags_and_description(self, sample_scenario_not_ready, sample_categories_map):
        result = get_reduced_scenario_mapping(sample_scenario_not_ready, sample_categories_map)
        assert result["tags"] == []
        assert result["description"] == "Scenario with empty simulator filter values"

    def test_unknown_category_id_skipped(self, sample_categories_map):
        scenario = {
            "id": "unknown-cat",
            "name": "Unknown Category Test",
            "description": None,
            "createdBy": "SafeBreach",
            "recommended": False,
            "categories": [2, 999],
            "tags": None,
            "createdAt": "2025-01-01T00:00:00.000Z",
            "updatedAt": "2025-01-01T00:00:00.000Z",
            "steps": [],
        }
        result = get_reduced_scenario_mapping(scenario, sample_categories_map)
        assert result["category_names"] == ["Known Threats Series"]

    # T-1 (SAF-34228) — `steps` present with value null. `.get("steps", [])` returns None
    # (the default applies only to a MISSING key), so len() raised TypeError and took down
    # the whole get_scenarios listing.
    def test_null_steps_yields_zero_step_count(self, sample_categories_map):
        scenario = {
            "id": "278b6968-676e-4940-bbd2-59c933437238",
            "name": "Adversary Reconnaissance",
            "description": None,
            "createdBy": "SafeBreach",
            "recommended": False,
            "categories": [2],
            "tags": None,
            "createdAt": "2026-07-29T06:45:57.000Z",
            "updatedAt": "2026-07-29T07:19:06.000Z",
            "steps": None,
        }
        result = get_reduced_scenario_mapping(scenario, sample_categories_map)
        assert result["step_count"] == 0
        assert result["total_attack_count"] == 0
        assert result["is_ready_to_run"] is False

    # T-3 (SAF-34228) — the pre-existing missing-key path must keep working.
    def test_absent_steps_key_yields_zero_step_count(self, sample_categories_map):
        scenario = {
            "id": "no-steps-key",
            "name": "No Steps Key",
            "description": None,
            "createdBy": "SafeBreach",
            "recommended": False,
            "categories": [2],
            "tags": None,
            "createdAt": "2025-01-01T00:00:00.000Z",
            "updatedAt": "2025-01-01T00:00:00.000Z",
        }
        result = get_reduced_scenario_mapping(scenario, sample_categories_map)
        assert result["step_count"] == 0


class TestGetReducedPlanMapping:
    """Test the get_reduced_plan_mapping function for custom plans."""

    @pytest.fixture
    def sample_plan(self):
        """A custom plan from the /plans endpoint."""
        return {
            "id": 119,
            "name": "CISA Alert AA23-347A (APT29)",
            "description": "A custom scenario description",
            "accountId": 3471166703,
            "originalScenarioId": "938be06a-1e47-4a68-a10d-a4d04167896b",
            "userId": 347116670300054,
            "deploymentId": None,
            "systemFilter": None,
            "tags": [],
            "emailRecipients": None,
            "successCriteria": None,
            "actions": [],
            "edges": [],
            "createdAt": "2026-02-23T08:19:46.295Z",
            "updatedAt": "2026-02-23T08:19:46.295Z",
            "steps": [
                {
                    "name": "Step 1",
                    "systemFilter": {},
                    "targetFilter": {"os": {"values": ["WINDOWS"]}},
                    "attackerFilter": {"role": {"values": ["isInfiltration"]}},
                    "attacksFilter": {},
                }
            ],
        }

    def test_source_type_is_custom(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["source_type"] == "custom"

    def test_all_expected_keys_present(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        expected_keys = {
            "id", "source_type", "name", "description", "createdBy", "recommended",
            "category_names", "tags", "step_count", "total_attack_count", "is_ready_to_run",
            "createdAt", "updatedAt", "userId", "originalScenarioId"
        }
        assert set(result.keys()) == expected_keys

    def test_custom_has_no_categories_or_recommended(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["category_names"] == []
        assert result["recommended"] is False
        assert result["createdBy"] is None

    def test_custom_preserves_user_and_original(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["userId"] == 347116670300054
        assert result["originalScenarioId"] == "938be06a-1e47-4a68-a10d-a4d04167896b"

    def test_empty_tags_list_becomes_empty_list(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["tags"] == []

    def test_id_is_always_string(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["id"] == "119"
        assert isinstance(result["id"], str)

    def test_step_count_computed_for_plans(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["step_count"] == 1

    def test_is_ready_to_run_for_plans(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["is_ready_to_run"] is True

    # T-2 (SAF-34228) — same null-vs-missing defect on the custom-plan mapper. Plans are
    # user-editable, so a null steps field is at least as reachable here as on OOB scenarios.
    def test_null_steps_yields_zero_step_count(self, sample_plan):
        sample_plan["steps"] = None
        result = get_reduced_plan_mapping(sample_plan)
        assert result["step_count"] == 0
        assert result["total_attack_count"] == 0
        assert result["is_ready_to_run"] is False

    # T-3 (SAF-34228) — missing-key path unchanged.
    def test_absent_steps_key_yields_zero_step_count(self, sample_plan):
        del sample_plan["steps"]
        result = get_reduced_plan_mapping(sample_plan)
        assert result["step_count"] == 0


class TestFilterScenariosByCriteria:
    """Test the filter_scenarios_by_criteria function."""

    def test_no_filters_returns_all(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(sample_reduced_scenarios)
        assert len(result) == 5

    def test_name_filter_partial_match(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(sample_reduced_scenarios, name_filter="Akira")
        assert len(result) == 1
        assert "Akira" in result[0]["name"]

    def test_name_filter_case_insensitive(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(sample_reduced_scenarios, name_filter="akira")
        assert len(result) == 1

    def test_creator_filter_safebreach(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(
            sample_reduced_scenarios, creator_filter="safebreach"
        )
        assert len(result) == 4
        assert all(s["source_type"] == "oob" for s in result)

    def test_creator_filter_custom(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(
            sample_reduced_scenarios, creator_filter="custom"
        )
        assert len(result) == 1
        assert result[0]["source_type"] == "custom"
        assert result[0]["name"] == "Custom Data Exfil Scenario"

    def test_category_filter_partial(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(
            sample_reduced_scenarios, category_filter="Groups"
        )
        assert len(result) == 1
        assert "Threat Groups" in result[0]["category_names"]

    def test_recommended_filter_true(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(
            sample_reduced_scenarios, recommended_filter=True
        )
        assert len(result) == 2
        assert all(s["recommended"] is True for s in result)

    def test_tag_filter_excludes_null_tags(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(
            sample_reduced_scenarios, tag_filter="ransomware"
        )
        assert len(result) == 1
        assert result[0]["id"] == "aaa-111"

    def test_combined_filters_and_logic(self, sample_reduced_scenarios):
        result = filter_scenarios_by_criteria(
            sample_reduced_scenarios,
            creator_filter="safebreach",
            recommended_filter=True,
        )
        assert len(result) == 2
        assert all(s["createdBy"] == "SafeBreach" and s["recommended"] for s in result)


class TestApplyScenarioOrdering:
    """Test the apply_scenario_ordering function."""

    def test_order_by_name_asc(self, sample_reduced_scenarios):
        result = apply_scenario_ordering(
            sample_reduced_scenarios, order_by="name", order_direction="asc"
        )
        names = [s["name"] for s in result]
        assert names == sorted(names, key=str.lower)

    def test_order_by_name_desc(self, sample_reduced_scenarios):
        result = apply_scenario_ordering(
            sample_reduced_scenarios, order_by="name", order_direction="desc"
        )
        names = [s["name"] for s in result]
        assert names == sorted(names, key=str.lower, reverse=True)

    def test_order_by_step_count(self, sample_reduced_scenarios):
        result = apply_scenario_ordering(
            sample_reduced_scenarios, order_by="step_count", order_direction="asc"
        )
        counts = [s["step_count"] for s in result]
        assert counts == sorted(counts)

    def test_order_by_created_at_desc(self, sample_reduced_scenarios):
        result = apply_scenario_ordering(
            sample_reduced_scenarios, order_by="createdAt", order_direction="desc"
        )
        dates = [s["createdAt"] for s in result]
        assert dates == sorted(dates, reverse=True)


class TestPaginateScenarios:
    """Test the paginate_scenarios function."""

    @pytest.fixture
    def large_scenario_list(self):
        """Generate 25 reduced scenario dicts for pagination testing."""
        return [
            {
                "id": f"scenario-{i}",
                "name": f"Scenario {i}",
                "description": f"Description {i}",
                "createdBy": "SafeBreach",
                "recommended": False,
                "category_names": ["Test"],
                "tags": None,
                "step_count": i,
                "is_ready_to_run": False,
                "createdAt": "2025-01-01T00:00:00.000Z",
                "updatedAt": "2025-01-01T00:00:00.000Z",
            }
            for i in range(25)
        ]

    def test_first_page(self, large_scenario_list):
        result = paginate_scenarios(large_scenario_list, page_number=0, page_size=10)
        assert result["page_number"] == 0
        assert result["total_pages"] == 3
        assert result["total_scenarios"] == 25
        assert len(result["scenarios_in_page"]) == 10
        assert result["hint_to_agent"] is not None

    def test_last_page(self, large_scenario_list):
        result = paginate_scenarios(large_scenario_list, page_number=2, page_size=10)
        assert result["page_number"] == 2
        assert len(result["scenarios_in_page"]) == 5
        # No pagination hint on last page (may still have attack count hint)
        hint = result["hint_to_agent"]
        assert hint is None or 'page_number=' not in hint

    def test_empty_list(self):
        result = paginate_scenarios([], page_number=0, page_size=10)
        assert result["page_number"] == 0
        assert result["total_pages"] == 0
        assert result["total_scenarios"] == 0
        assert len(result["scenarios_in_page"]) == 0

    def test_invalid_page_beyond_total(self, large_scenario_list):
        result = paginate_scenarios(large_scenario_list, page_number=10, page_size=10)
        assert "error" in result
        assert "Invalid page_number 10" in result["error"]
        assert result["total_scenarios"] == 25
        assert len(result["scenarios_in_page"]) == 0

    def test_single_page_result(self, sample_reduced_scenarios):
        result = paginate_scenarios(sample_reduced_scenarios, page_number=0, page_size=10)
        assert result["page_number"] == 0
        assert result["total_pages"] == 1
        assert result["total_scenarios"] == 5
        assert len(result["scenarios_in_page"]) == 5
        # No pagination hint on single page (may still have attack count hint)
        hint = result["hint_to_agent"]
        assert hint is None or 'page_number=' not in hint

    @pytest.fixture
    def page0_not_ready_list(self):
        """25 scenarios where page 0 (first 10) are all not-ready, but the last 5 are ready."""
        return [
            {
                "id": f"scenario-{i}",
                "name": f"Scenario {i}",
                "category_names": ["Test"],
                "tags": None,
                "step_count": 1,
                "is_ready_to_run": i >= 20,
                "createdAt": "2025-01-01T00:00:00.000Z",
                "updatedAt": "2025-01-01T00:00:00.000Z",
            }
            for i in range(25)
        ]

    def test_ready_to_run_hint_when_ready_scenarios_beyond_page(self, page0_not_ready_list):
        """SAF-32210: page 0 shows no ready scenarios, but ready ones exist later — the hint must
        surface the true ready count (so the agent doesn't conclude 'none are ready') AND make
        clear the non-ready scenarios are still runnable via step_overrides (not steer to ready-only)."""
        result = paginate_scenarios(page0_not_ready_list, page_number=0, page_size=10)
        hint = result["hint_to_agent"]
        assert "5 of 25" in hint
        assert "step_overrides" in hint
        assert "ready_to_run_filter=True" in hint

    def test_no_ready_hint_when_filter_already_applied(self, page0_not_ready_list):
        """When ready_to_run_filter was applied, don't nudge toward it again."""
        result = paginate_scenarios(
            page0_not_ready_list, page_number=0, page_size=10, ready_to_run_filter_applied=True
        )
        hint = result["hint_to_agent"] or ""
        assert "ready_to_run_filter=True" not in hint

    def test_no_ready_hint_when_all_ready_shown(self, sample_reduced_scenarios):
        """Single page where every ready scenario is already visible — no nudge needed."""
        result = paginate_scenarios(sample_reduced_scenarios, page_number=0, page_size=10)
        hint = result["hint_to_agent"] or ""
        assert "ready_to_run_filter=True" not in hint

    def test_no_ready_hint_when_none_ready(self, large_scenario_list):
        """No ready-to-run scenarios at all — no nudge."""
        result = paginate_scenarios(large_scenario_list, page_number=0, page_size=10)
        hint = result["hint_to_agent"] or ""
        assert "ready_to_run_filter=True" not in hint


class TestMalformedScenarioSteps:
    """Regression tests for malformed scenario data from content-manager API.

    Staging (scenario index 218) has a scenario with id=None where steps[0]
    is a list instead of a dict, causing 'list' object has no attribute 'get'.
    """

    def test_compute_is_ready_to_run_with_list_step(self):
        """Steps containing a list instead of dict should not crash."""
        scenario = {
            "id": None,
            "name": "Malformed scenario",
            "steps": [
                [{"name": "inner step", "targetFilter": {}, "attackerFilter": {}}]
            ],
        }
        result = compute_is_ready_to_run(scenario)
        assert result is False

    def test_get_reduced_scenario_mapping_with_list_step(self):
        """get_reduced_scenario_mapping should handle scenario with list-type step."""
        scenario = {
            "id": "abc-123",
            "name": "Malformed scenario",
            "steps": [
                [{"name": "inner step"}]
            ],
            "categories": [],
        }
        result = get_reduced_scenario_mapping(scenario, {})
        assert result["is_ready_to_run"] is False
        assert result["step_count"] == 1


# --- Integration-discovery transforms (SAF-32798) ---

from safebreach_mcp_config.config_types import get_integration_catalog_entry


class TestIntegrationCatalogEntry:
    """T-1 — catalog entry transform exposes the public allow-list only."""

    def _raw(self):
        # Modeled on the pentest01 /config/integrations type-def shape.
        return {
            "displayName": "Splunk (REST)",
            "description": "Splunk SIEM over REST",
            "category": "siem",
            "vendor": "Splunk Inc.",
            "product": "Splunk",
            "isTi": False,
            "isTiV2": False,
            "isVm": False,
            # internal fields that must NOT leak through:
            "fields": [{"key": "token", "sensitive": True}],
            "featureFlag": "feature.mcpToolsConfig",
            "guideLink": "https://internal/guide",
        }

    def test_maps_public_fields_only(self):
        entry = get_integration_catalog_entry("custom_splunkrest", self._raw())
        assert entry == {
            "type": "custom_splunkrest",
            "name": "Splunk (REST)",
            "description": "Splunk SIEM over REST",
            "category": "siem",
            "vendor": "Splunk Inc.",
            "product": "Splunk",
            "is_ti": False,
            "is_vm": False,
        }
        # no internal keys leaked
        for leaked in ("fields", "featureFlag", "guideLink", "isTiV2"):
            assert leaked not in entry

    def test_name_falls_back_to_type_when_no_display_name(self):
        raw = self._raw()
        del raw["displayName"]
        entry = get_integration_catalog_entry("custom_splunkrest", raw)
        assert entry["name"] == "custom_splunkrest"

    def test_is_ti_derives_from_isTiV2(self):
        raw = self._raw()
        raw["isTiV2"] = True
        entry = get_integration_catalog_entry("alienvault", raw)
        assert entry["is_ti"] is True

    def test_is_vm_flag(self):
        raw = self._raw()
        raw["isVm"] = True
        entry = get_integration_catalog_entry("wiz", raw)
        assert entry["is_vm"] is True


from safebreach_mcp_config.config_types import get_minimal_installed_integration


class TestMinimalInstalledIntegration:
    """T-2 — installed transform returns the slim shape, no secrets."""

    def test_slim_shape_only(self):
        raw = {
            "id": "AQKPdodinKdfTCJT8kp8Y",
            "type": "custom_splunkrest",
            "name": "Splunk Prod",
            "enabled": True,
            # sensitive / config fields that must NOT survive:
            "token": "$PAM:INTERNAL_VAULT:abc/token",
            "password": "$PAM:INTERNAL_VAULT:abc/password",
            "host": "splunk.internal",
            "headers": {"Authorization": "Bearer x"},
        }
        result = get_minimal_installed_integration(raw)
        assert result == {"id": "AQKPdodinKdfTCJT8kp8Y", "type": "custom_splunkrest",
                          "name": "Splunk Prod", "enabled": True}
        for leaked in ("token", "password", "host", "headers"):
            assert leaked not in result

    def test_missing_enabled_defaults_false(self):
        result = get_minimal_installed_integration({"id": "x", "type": "t", "name": "n"})
        assert result["enabled"] is False


from safebreach_mcp_config.config_types import (
    redact_sensitive_fields,
    get_installed_integration_detail_view,
    REDACTED_PLACEHOLDER,
)


def _catalog_with_sensitive():
    """Catalog keyed by type; fields[].sensitive marks the secret fields per type."""
    return {
        "custom_splunkrest": {
            "displayName": "Splunk REST",
            "fields": [
                {"key": "host", "sensitive": False},
                {"key": "token", "sensitive": True},
                {"key": "password", "sensitive": True},
            ],
        },
        "custom_wiz": {
            "displayName": "Wiz",
            # headers deliberately NOT flagged sensitive — must be force-masked anyway
            "fields": [{"key": "clientId", "sensitive": False}],
        },
    }


class TestRedaction:
    """T-3/T-4/T-5 — sensitive-field redaction for get_installed_integration."""

    def test_masks_schema_sensitive_fields(self):
        connector = {
            "id": "a1", "type": "custom_splunkrest", "name": "Splunk", "enabled": True,
            "host": "splunk.internal",
            "token": "$PAM:INTERNAL_VAULT:abc/token",
            "password": "$PAM:INTERNAL_VAULT:abc/password",
        }
        result = redact_sensitive_fields(connector, _catalog_with_sensitive())
        assert result["token"] == REDACTED_PLACEHOLDER
        assert result["password"] == REDACTED_PLACEHOLDER
        assert result["host"] == "splunk.internal"  # non-sensitive untouched
        # no vault ref survives anywhere
        assert not any(isinstance(v, str) and v.startswith("$PAM:") for v in result.values())
        # original not mutated
        assert connector["token"].startswith("$PAM:")

    def test_force_masks_headers_and_proxypass(self):
        connector = {
            "id": "w1", "type": "custom_wiz", "name": "Wiz", "enabled": True,
            "clientId": "public-client-id",
            "headers": {"Authorization": "Bearer super-secret"},
            "proxyPass": "$PAM:INTERNAL_VAULT:xyz/proxyPass",
        }
        result = redact_sensitive_fields(connector, _catalog_with_sensitive())
        assert result["headers"] == REDACTED_PLACEHOLDER
        assert result["proxyPass"] == REDACTED_PLACEHOLDER
        assert result["clientId"] == "public-client-id"
        # the bearer token must not appear anywhere in the serialized result
        import json as _json
        assert "super-secret" not in _json.dumps(result)

    def test_fail_safe_unknown_type(self):
        connector = {
            "id": "u1", "type": "totally_unknown_type", "name": "Mystery", "enabled": True,
            "token": "$PAM:INTERNAL_VAULT:q/token",
            "apiSecret": "$PAM:INTERNAL_VAULT:q/apiSecret",
            "headers": {"X-Auth": "leak-me"},
            "proxyPass": "$PAM:INTERNAL_VAULT:q/proxyPass",
            "host": "mystery.internal",
        }
        result = redact_sensitive_fields(connector, _catalog_with_sensitive())
        assert result["token"] == REDACTED_PLACEHOLDER
        assert result["apiSecret"] == REDACTED_PLACEHOLDER
        assert result["headers"] == REDACTED_PLACEHOLDER
        assert result["proxyPass"] == REDACTED_PLACEHOLDER
        import json as _json
        dumped = _json.dumps(result)
        assert "$PAM:" not in dumped
        assert "leak-me" not in dumped

    def test_masks_nested_vault_refs(self):
        # a secret hidden in a nested dict/list must not leak (defense-in-depth)
        connector = {
            "id": "n1", "type": "custom_splunkrest", "name": "Nested", "enabled": True,
            "deployments": [{"name": "prod", "apiKey": "$PAM:INTERNAL_VAULT:n/apiKey"}],
            "nested": {"inner": {"secretRef": "$PAM:INTERNAL_VAULT:n/inner"}},
        }
        result = redact_sensitive_fields(connector, _catalog_with_sensitive())
        import json as _json
        assert "$PAM:" not in _json.dumps(result)
        assert result["deployments"][0]["apiKey"] == REDACTED_PLACEHOLDER
        assert result["nested"]["inner"]["secretRef"] == REDACTED_PLACEHOLDER
        assert result["deployments"][0]["name"] == "prod"  # non-secret preserved

    def test_masks_plaintext_secret_on_partially_flagged_type(self):
        # Bug 1: a known type whose schema omits `sensitive: true` on a secret field must
        # still fall back to the default set. `password` is a _DEFAULT_SENSITIVE_FIELDS name
        # but is NOT flagged sensitive on custom_wiz's schema — a plaintext value must not leak.
        connector = {
            "id": "w2", "type": "custom_wiz", "name": "Wiz", "enabled": True,
            "clientId": "public-client-id",
            "password": "clear-text-pw",  # pragma: allowlist secret  # plaintext test fixture, no $PAM:/@enc: prefix
        }
        result = redact_sensitive_fields(connector, _catalog_with_sensitive())
        assert result["password"] == REDACTED_PLACEHOLDER
        assert result["clientId"] == "public-client-id"
        import json as _json
        assert "clear-text-pw" not in _json.dumps(result)

    def test_masks_nested_plaintext_headers(self):
        # Bug 2: a `headers` block nested under a non-sensitive parent carries a plaintext
        # bearer token (no $PAM:/@enc: prefix) — it must be masked at any depth.
        connector = {
            "id": "s2", "type": "custom_splunkrest", "name": "Splunk", "enabled": True,
            "settings": {"headers": {"Authorization": "Bearer TOKEN"}},
        }
        result = redact_sensitive_fields(connector, _catalog_with_sensitive())
        assert result["settings"]["headers"] == REDACTED_PLACEHOLDER
        import json as _json
        dumped = _json.dumps(result)
        assert "Bearer TOKEN" not in dumped
        assert "TOKEN" not in dumped

    def test_detail_view_delegates_to_redaction(self):
        connector = {"id": "a1", "type": "custom_splunkrest", "name": "S", "enabled": True,
                     "token": "$PAM:INTERNAL_VAULT:abc/token"}
        view = get_installed_integration_detail_view(connector, _catalog_with_sensitive())
        assert view["token"] == REDACTED_PLACEHOLDER
        assert view["id"] == "a1"


from safebreach_mcp_config.config_types import get_minimal_ti_integration, select_ti_connectors


class TestTiTransforms:
    """T-6 — slim TI transform; TI derivation via catalog isTiV2."""

    def test_minimal_ti_slim_shape(self):
        raw = {"id": "c3", "type": "alienvault", "name": "AlienVault", "enabled": True,
               "apiToken": "$PAM:INTERNAL_VAULT:x/apiToken"}
        result = get_minimal_ti_integration(raw)
        assert result == {"id": "c3", "type": "alienvault", "name": "AlienVault", "enabled": True}

    def test_select_ti_connectors_by_isTiV2(self):
        installed = [
            {"id": "1", "type": "alienvault", "name": "AV", "enabled": True},
            {"id": "2", "type": "splunkrest", "name": "Splunk", "enabled": True},
            {"id": "3", "type": "threatconnect", "name": "TC", "enabled": False},
        ]
        catalog = {
            "alienvault": {"isTiV2": True},
            "splunkrest": {"isTiV2": False},
            "threatconnect": {"isTiV2": True},
        }
        ti = select_ti_connectors(installed, catalog)
        assert sorted(c["id"] for c in ti) == ["1", "3"]
