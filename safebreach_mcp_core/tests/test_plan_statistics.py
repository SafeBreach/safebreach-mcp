"""
Unit tests for safebreach_mcp_core.plan_statistics.

Covers the SAF-35508 plan/statistics fetch core (T-6 … T-12 in the test plan):
ad-hoc scoring, scenario_id passthrough, the step-less guard, full parameter
passthrough, limit-reached null-safety, error-body propagation, and the absence
of any MCP-side cache.
"""

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

import pytest
import requests

from safebreach_mcp_core.plan_statistics import (
    fetch_plan_statistics,
    PastRunHasNoScenarioError,
)


def _two_step_payload():
    """A normal, fully-computed two-step response."""
    return {
        "data": {
            "constraintCatalog": {
                "incompatible_os": {"description": "  Simulator OS mismatch  "},
            },
            "steps": [
                {
                    "simulationCount": 120,
                    "moves": {"281": 100, "226": 20},
                    "simulators": {"sim-1": 60, "sim-2": 60},
                    "attackerSimulators": {"sim-1": 60},
                    "targetSimulators": {"sim-2": 60},
                    "simulatorConstraints": {
                        "targetConstraints": {"sim-2": {"226": [{"reason": "incompatible_os"}]}},
                        "attackerConstraints": {},
                    },
                    "isLimitReached": False,
                },
                {
                    "simulationCount": 0,
                    "moves": {"999": 0},
                    "simulators": {},
                    "attackerSimulators": {},
                    "targetSimulators": {},
                    "simulatorConstraints": {},
                    "isLimitReached": False,
                },
            ],
        }
    }


def _limit_reached_payload():
    """Core pushed a sentinel step and returned early: one step, every count null."""
    return {
        "data": {
            "steps": [
                {
                    "simulationCount": None,
                    "moves": {"281": None, "226": None},
                    "simulators": {"sim-1": None},
                    "attackerSimulators": {"sim-1": None},
                    "targetSimulators": {"sim-1": None},
                    "simulatorConstraints": {},
                    "isLimitReached": True,
                },
            ],
        }
    }


def _plan_body(step_count=2):
    return {"name": "ad-hoc", "steps": [{"n": i} for i in range(step_count)]}


def _mock_response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _query(mock_post):
    """Parsed query string of the URL the fetch core actually posted to."""
    url = mock_post.call_args[0][0]
    return parse_qs(urlparse(url).query)


def _posted_body(mock_post):
    return mock_post.call_args.kwargs["json"]


_CACHE_TYPE_NAMES = {
    "SafeBreachCache", "TTLCache", "LRUCache", "LFUCache", "Cache",
    "_lru_cache_wrapper",
}


@pytest.fixture(autouse=True)
def _console_env():
    """Resolve console metadata and auth without real environments or secrets."""
    with patch(
        "safebreach_mcp_core.plan_statistics.get_api_base_url",
        return_value="https://test.safebreach.com",
    ), patch(
        "safebreach_mcp_core.plan_statistics.get_api_account_id",
        return_value="1234567890",
    ), patch(
        "safebreach_mcp_core.plan_statistics.get_auth_headers_for_console",
        return_value={"x-apitoken": "test-token"},
    ):
        yield


class TestAdHocPlanBodyIsScoredUnreduced:
    """T-6 — an ad-hoc plan body is scored and the response returned unreduced."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_posted_body_carries_the_supplied_steps_and_no_id(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())
        body = _plan_body()

        fetch_plan_statistics(console="test-console", plan=body)

        posted = _posted_body(mock_post)
        assert posted["steps"] == body["steps"]
        assert "id" not in posted

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_name_defaults_to_empty_string_when_absent(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", plan={"steps": [{"n": 0}]})

        assert _posted_body(mock_post)["name"] == ""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_caller_supplied_name_is_used_as_is(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert _posted_body(mock_post)["name"] == "ad-hoc"

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_each_step_exposes_all_seven_response_fields_unmodified(self, mock_post):
        payload = _two_step_payload()
        mock_post.return_value = _mock_response(payload)

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        raw = payload["data"]["steps"][0]
        step = result["steps"][0]
        assert step["simulationCount"] == raw["simulationCount"]
        assert step["moves"] == raw["moves"]
        assert step["simulators"] == raw["simulators"]
        assert step["attackerSimulators"] == raw["attackerSimulators"]
        assert step["targetSimulators"] == raw["targetSimulators"]
        assert step["simulatorConstraints"] == raw["simulatorConstraints"]
        assert step["isLimitReached"] == raw["isLimitReached"]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_map_values_are_not_rebuilt_or_reduced(self, mock_post):
        """The union `simulators` map and the sparse constraints survive intact."""
        payload = _two_step_payload()
        mock_post.return_value = _mock_response(payload)

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        step = result["steps"][0]
        assert step["simulators"] == {"sim-1": 60, "sim-2": 60}
        assert step["simulatorConstraints"]["targetConstraints"]["sim-2"]["226"] == [
            {"reason": "incompatible_os"}
        ]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_two_step_plan_returns_two_steps_in_response_order(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert len(result["steps"]) == 2
        assert [s["simulationCount"] for s in result["steps"]] == [120, 0]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_response_root_constraint_catalog_is_relayed_verbatim(self, mock_post):
        """Phase 1's relay is only reachable through this layer from Phase 3 on."""
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert result["constraint_catalog"] == {
            "incompatible_os": {"description": "  Simulator OS mismatch  "}
        }

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_absent_catalog_is_none_and_empty_catalog_is_empty_dict(self, mock_post):
        """`None` (not supplied) stays distinct from `{}` (supplied, empty)."""
        no_catalog = _two_step_payload()
        del no_catalog["data"]["constraintCatalog"]
        mock_post.return_value = _mock_response(no_catalog)
        assert fetch_plan_statistics(
            console="test-console", plan=_plan_body()
        )["constraint_catalog"] is None

        empty_catalog = _two_step_payload()
        empty_catalog["data"]["constraintCatalog"] = {}
        mock_post.return_value = _mock_response(empty_catalog)
        assert fetch_plan_statistics(
            console="test-console", plan=_plan_body()
        )["constraint_catalog"] == {}


class TestScenarioIdIsPassedForNativeResolution:
    """T-7 — a scenario_id is passed to Core for native resolution, never via planId."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_body_carries_id_and_name_for_a_scenario_id(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", scenario_id="abc-123")

        posted = _posted_body(mock_post)
        assert posted["id"] == "abc-123"
        assert posted["name"] == ""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_plan_id_is_never_present_in_the_posted_body(self, mock_post):
        """The controller ignores planId — sending it scores an empty ad-hoc plan."""
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", scenario_id="abc-123")

        assert "planId" not in _posted_body(mock_post)

    @patch("safebreach_mcp_core.plan_statistics.requests.get")
    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_no_scenario_or_plan_lookup_is_issued(self, mock_post, mock_get):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", scenario_id="abc-123")

        mock_get.assert_not_called()
        assert mock_post.call_count == 1

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_scenario_id_path_is_not_rejected_for_absent_steps(self, mock_post):
        """The step-less guard applies to an ad-hoc body, not to a saved scenario."""
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", scenario_id="abc-123")

        assert result["plan_step_count"] is None
        assert result["returned_step_count"] == 2


class TestStepLessPlanRejectedBeforeAnyCall:
    """T-8 — a step-less plan is rejected before any network call is made."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_missing_steps_key_raises_before_the_call(self, mock_post):
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan={"name": "wip"})

        assert "steps" in str(excinfo.value).lower()
        mock_post.assert_not_called()

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_empty_steps_list_raises_before_the_call(self, mock_post):
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan={"name": "wip", "steps": []})

        assert "steps" in str(excinfo.value).lower()
        mock_post.assert_not_called()

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_error_explains_the_expected_upstream_rejection(self, mock_post):
        """A mid-construction plan is normal — the message must say so, not read as a fault."""
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan={"steps": []})

        message = str(excinfo.value)
        assert "400" in message or "NOT_ALLOWED" in message
        mock_post.assert_not_called()


class TestAllFiveQueryParametersArePassedThrough:
    """T-9 — all five query parameters are sent, with documented defaults and honoured overrides."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_default_call_sends_all_five_documented_defaults(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", plan=_plan_body())

        query = _query(mock_post)
        assert query["limit"] == ["500000"]
        assert query["includeDisabled"] == ["false"]
        assert query["getConstraints"] == ["true"]
        assert query["getAllConstraints"] == ["true"]
        assert query["useCache"] == ["true"]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_each_override_replaces_its_default(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(
            console="test-console",
            plan=_plan_body(),
            include_disabled=True,
            get_constraints=False,
            get_all_constraints=False,
            limit=25,
            use_cache=False,
        )

        query = _query(mock_post)
        assert query["includeDisabled"] == ["true"]
        assert query["getConstraints"] == ["false"]
        assert query["getAllConstraints"] == ["false"]
        assert query["limit"] == ["25"]
        assert query["useCache"] == ["false"]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_no_parameter_is_omitted_when_only_one_is_overridden(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", plan=_plan_body(), limit=10)

        query = _query(mock_post)
        assert set(query) == {
            "limit", "includeDisabled", "getConstraints", "getAllConstraints", "useCache",
        }

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_params_used_reports_the_effective_parameter_set(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(
            console="test-console", plan=_plan_body(), include_disabled=True
        )

        assert result["params_used"] == {
            "includeDisabled": True,
            "getConstraints": True,
            "getAllConstraints": True,
            "limit": 500000,
            "useCache": True,
        }


class TestLimitReachedResponseKeepsNullDistinctFromZero:
    """T-10 — a limit-reached response is survived, and null is kept distinct from zero."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_limit_reached_response_does_not_raise(self, mock_post):
        mock_post.return_value = _mock_response(_limit_reached_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body(3))

        assert result["steps"]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_null_simulation_count_is_not_defaulted_to_zero(self, mock_post):
        mock_post.return_value = _mock_response(_limit_reached_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body(3))

        count = result["steps"][0]["simulationCount"]
        assert count is None
        assert count != 0

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_counts_computed_is_false_when_simulation_count_is_null(self, mock_post):
        mock_post.return_value = _mock_response(_limit_reached_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body(3))

        assert result["steps"][0]["counts_computed"] is False

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_integer_zero_count_is_still_reported_as_computed(self, mock_post):
        """0 means 'in scope, runs nowhere' — a computed answer, unlike null."""
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        zero_step = result["steps"][1]
        assert zero_step["simulationCount"] == 0
        assert zero_step["counts_computed"] is True

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_every_null_move_value_stays_null(self, mock_post):
        mock_post.return_value = _mock_response(_limit_reached_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body(3))

        moves = result["steps"][0]["moves"]
        assert moves == {"281": None, "226": None}
        assert all(v is None for v in moves.values())

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_plan_and_returned_step_counts_and_truncation_flag(self, mock_post):
        mock_post.return_value = _mock_response(_limit_reached_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body(3))

        assert result["plan_step_count"] == 3
        assert result["returned_step_count"] == 1
        assert result["truncated"] is True

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_index_is_into_the_returned_list_not_the_plan(self, mock_post):
        """Core's sentinel step is returned-list position 0, not plan step 0."""
        mock_post.return_value = _mock_response(_limit_reached_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body(3))

        assert [s["response_step_index"] for s in result["steps"]] == [0]
        assert "step_index" not in result["steps"][0]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_untruncated_response_is_not_flagged(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert result["truncated"] is False
        assert result["plan_step_count"] == 2
        assert result["returned_step_count"] == 2


class TestApiFailureSurfacesTheFullResponseBody:
    """T-11 — an API failure surfaces the full response body, not just a status code."""

    @staticmethod
    def _failing_response(status_code=400, text='{"error":"NOT_ALLOWED: plan has no steps"}'):
        response = MagicMock()
        response.status_code = status_code
        response.text = text
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            f"{status_code} Client Error"
        )
        return response

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_error_message_contains_the_status_code(self, mock_post):
        mock_post.return_value = self._failing_response()

        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert "400" in str(excinfo.value)

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_error_message_contains_the_identifiable_body_string(self, mock_post):
        mock_post.return_value = self._failing_response()

        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert "NOT_ALLOWED: plan has no steps" in str(excinfo.value)

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_rbac_403_propagates_as_permission_error(self, mock_post):
        """Only HTTPError is caught, so the 403 hint reaches the caller unchanged."""
        forbidden = MagicMock()
        forbidden.status_code = 403
        forbidden.url = "https://test.safebreach.com/plan/statistics"
        mock_post.return_value = forbidden

        with pytest.raises(PermissionError):
            fetch_plan_statistics(console="test-console", plan=_plan_body())

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_non_json_body_on_a_2xx_is_reported_not_raised_raw(self, mock_post):
        """A gateway HTML page must not surface as a bare JSONDecodeError."""
        gateway = MagicMock()
        gateway.status_code = 200
        gateway.text = "<html>502 Bad Gateway</html>"
        gateway.raise_for_status.return_value = None
        gateway.json.side_effect = ValueError("Expecting value")
        mock_post.return_value = gateway

        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert "non-JSON" in str(excinfo.value)

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_raised_error_is_a_value_error(self, mock_post):
        """studio's shipped e2e asserts ValueError + 'Statistics API error'."""
        mock_post.return_value = self._failing_response()

        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert "Statistics API error" in str(excinfo.value)


class TestMutuallyExclusiveInputs:
    """Neither `plan` nor `scenario_id`, or both, is a caller error caught before any I/O."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_neither_plan_nor_scenario_id_is_rejected(self, mock_post):
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console")

        assert "scenario_id" in str(excinfo.value)
        mock_post.assert_not_called()

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_both_plan_and_scenario_id_is_rejected(self, mock_post):
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(
                console="test-console", plan=_plan_body(), scenario_id="abc-123"
            )

        assert "scenario_id" in str(excinfo.value)
        mock_post.assert_not_called()

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_test_id_alongside_another_input_is_rejected(self, mock_post):
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(
                console="test-console", scenario_id="abc-123", test_id="1764165600525.2"
            )

        assert "test_id" in str(excinfo.value)
        mock_post.assert_not_called()

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_all_three_inputs_together_is_rejected(self, mock_post):
        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(
                console="test-console", plan=_plan_body(), scenario_id="abc-123",
                test_id="1764165600525.2",
            )

        assert "test_id" in str(excinfo.value)
        mock_post.assert_not_called()


class TestPastRunIsScoredByTestId:
    """A planRunId is passed through as `testId` for native resolution."""

    PLAN_RUN_ID = "1764165600525.2"

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_body_carries_test_id_and_name(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        body = _posted_body(mock_post)
        assert body["testId"] == self.PLAN_RUN_ID
        # ValidatePlan requires `name`, and the request is validated at the edge,
        # so an id-only body that omits it is rejected before the controller.
        assert body["name"] == ""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_neither_id_nor_plan_id_is_present(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        body = _posted_body(mock_post)
        # planId is in the ValidatePlan schema but the controller destructures
        # only {id, testId}; sending it falls through to the inline branch.
        assert "planId" not in body
        assert "id" not in body

    @patch("safebreach_mcp_core.plan_statistics.requests.get")
    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_no_lookup_is_issued_to_resolve_the_run(self, mock_post, mock_get):
        mock_post.return_value = _mock_response(_two_step_payload())

        fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        mock_get.assert_not_called()

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_step_less_guard_does_not_apply(self, mock_post):
        """The run's scenario is expanded server-side; there are no local steps to check."""
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        assert result["returned_step_count"] == 2

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_plan_step_count_is_unknown_and_does_not_fake_truncation(self, mock_post):
        """Keying plan_step_count off `scenario_id is None` would raise KeyError here."""
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        assert result["plan_step_count"] is None
        assert result["truncated"] is False

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_missing_original_plan_is_reported_as_its_own_error(self, mock_post):
        response = _mock_response({}, status_code=500)
        response.text = f"TestSummary {self.PLAN_RUN_ID} doesn't have originalPlan"
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
        mock_post.return_value = response

        with pytest.raises(PastRunHasNoScenarioError) as excinfo:
            fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        message = str(excinfo.value)
        assert self.PLAN_RUN_ID in message
        assert "scenario_id" in message

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_an_unrelated_failure_is_not_reported_as_a_missing_scenario(self, mock_post):
        response = _mock_response({}, status_code=500)
        response.text = "upstream timeout"
        response.raise_for_status.side_effect = requests.exceptions.HTTPError(
            response=response
        )
        mock_post.return_value = response

        with pytest.raises(ValueError) as excinfo:
            fetch_plan_statistics(console="test-console", test_id=self.PLAN_RUN_ID)

        assert not isinstance(excinfo.value, PastRunHasNoScenarioError)
        assert "upstream timeout" in str(excinfo.value)


class TestResponseEnvelopeIsAcceptedInEitherShape:
    """SAF-32019 — swagger documents a `data` wrapper; the endpoint may omit it.

    Reading an unwrapped body as absent would report a scored plan as having no
    steps at all — a silent empty result, which is the precise failure the
    null-versus-zero rule exists to prevent.
    """

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_wrapped_response_is_read_from_the_data_envelope(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert result["returned_step_count"] == 2
        assert result["steps"][0]["simulationCount"] == 120

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_unwrapped_response_is_read_from_the_top_level(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload()["data"])

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert result["returned_step_count"] == 2
        assert result["steps"][0]["simulationCount"] == 120

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_unwrapped_response_still_relays_the_constraint_catalog(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload()["data"])

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert "incompatible_os" in result["constraint_catalog"]

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_an_explicit_null_data_envelope_yields_no_steps(self, mock_post):
        mock_post.return_value = _mock_response({"data": None})

        result = fetch_plan_statistics(console="test-console", plan=_plan_body())

        assert result["steps"] == []


class TestNoMcpSideCaching:
    """T-12 — repeated identical calls each hit the API, proving no MCP-side cache."""

    @patch("safebreach_mcp_core.plan_statistics.requests.post")
    def test_two_identical_calls_issue_two_http_requests(self, mock_post):
        mock_post.return_value = _mock_response(_two_step_payload())
        body = _plan_body()

        fetch_plan_statistics(console="test-console", plan=body)
        fetch_plan_statistics(console="test-console", plan=body)

        assert mock_post.call_count == 2

    def test_module_exposes_no_cache_object(self):
        """A TTL cache here would serve numbers for a config the user already edited.

        Keyed on the *type*, not the name: a cache is an object that stores
        results, so a scalar like DEFAULT_USE_CACHE — which names Core's own
        server-side query parameter — is not one.
        """
        import safebreach_mcp_core.plan_statistics as plan_statistics

        suspicious = []
        for name, value in vars(plan_statistics).items():
            if name.startswith("__"):
                continue
            if isinstance(value, (bool, int, float, str, tuple, type(None))):
                continue
            if type(value).__name__ in _CACHE_TYPE_NAMES or "cache" in name.lower():
                suspicious.append(f"{name} ({type(value).__name__})")
        assert suspicious == [], f"cache-like module globals found: {suspicious}"


class TestSingleStatisticsCallSite:
    """T-16 — the statistics endpoint is reached from exactly one place in the repo."""

    @staticmethod
    def _source_files():
        """Every first-party Python source file, excluding tests and virtualenvs."""
        from pathlib import Path

        repo_root = Path(__file__).resolve().parents[2]
        for path in repo_root.rglob("*.py"):
            # Relative to the repo root: an absolute path may itself sit under a
            # dot-directory (a git worktree lives under .claude/worktrees/).
            parts = path.relative_to(repo_root).parts
            if any(p.startswith(".") or p == "__pycache__" for p in parts):
                continue
            if "tests" in parts or path.name.startswith("test_"):
                continue
            yield path

    def _endpoint_matches(self):
        matches = []
        for path in self._source_files():
            for lineno, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if "/plan/statistics" in line:
                    matches.append(f"{path}:{lineno}")
        return matches

    def test_endpoint_path_appears_in_exactly_one_source_file(self):
        """A second estimation path is what the parent requirement forbids."""
        matches = self._endpoint_matches()
        files = {m.rsplit(":", 1)[0] for m in matches}
        assert len(files) == 1, f"plan/statistics reached from {len(files)} files: {matches}"

    def test_that_file_is_the_fetch_core(self):
        matches = self._endpoint_matches()
        assert matches, "the endpoint path was not found at all"
        for match in matches:
            assert match.rsplit(":", 1)[0].endswith("safebreach_mcp_core/plan_statistics.py"), (
                f"unexpected statistics call site: {match}"
            )
