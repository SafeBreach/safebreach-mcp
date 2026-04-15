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
            "id": 444,
            "name": "Custom Data Exfil Scenario",
            "description": "A custom scenario for testing data exfiltration",
            "source_type": "custom",
            "createdBy": None,
            "recommended": False,
            "category_names": [],
            "tags": None,
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
            "category_names", "tags", "step_count", "is_ready_to_run",
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
        assert result["tags"] is None
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
            "category_names", "tags", "step_count", "is_ready_to_run",
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

    def test_empty_tags_list_becomes_none(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["tags"] is None  # empty list normalized to None

    def test_integer_id_preserved(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["id"] == 119
        assert isinstance(result["id"], int)

    def test_step_count_computed_for_plans(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["step_count"] == 1

    def test_is_ready_to_run_for_plans(self, sample_plan):
        result = get_reduced_plan_mapping(sample_plan)
        assert result["is_ready_to_run"] is True


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
        assert result["hint_to_agent"] is None

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
        assert result["hint_to_agent"] is None
