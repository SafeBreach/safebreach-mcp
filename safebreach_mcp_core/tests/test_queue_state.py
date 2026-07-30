"""
Unit tests for safebreach_mcp_core.queue_state.

Covers the SAF-33511 orchestrator queue snapshot reader (T-1, T-2 in the test plan)
plus characterization tests for the pre-existing get_orchestrator_test_state.
"""

import logging
from unittest.mock import MagicMock, patch

import pytest
import requests

from safebreach_mcp_core.queue_state import (
    get_orchestrator_queue_snapshot,
    get_orchestrator_test_state,
)


def _queue_payload():
    """Fresh orchestrator /queue payload modeled on the live pentest01 capture."""
    return {
        "data": {
            "isPause": False,
            "slotState": [
                {
                    "id": "validate-0",
                    "status": "Waiting for execution",
                    "slotStatus": "Running Step",
                    "planRunId": "1785200400269.2",
                },
                {
                    "id": "validate-1",
                    "status": "Idle",
                    "slotStatus": "Idle",
                    "planRunId": None,
                },
            ],
            "queue": [
                {
                    "planRunId": "1785224437040.28",
                    "name": "Queued Plan A",
                    "steps": [{"attacks": ["big"]}, {"attacks": ["big"]}],
                    "actions": [{"a": 1}],
                    "edges": [{"e": 1}],
                    "systemTags": [],
                    "ranBy": 347116670300007,
                    "ranFrom": "API",
                    "retryPolicy": "default",
                    "flowControl": {"x": 1},
                    "priority": "low",
                    "retrySimulations": True,
                    "originalPlan": {"huge": "blob"},
                },
                {
                    "planRunId": "1785224437040.29",
                    "name": "Queued Plan B",
                    "steps": [{"attacks": ["one"]}],
                    "actions": [],
                    "edges": [],
                    "systemTags": ["BAS"],
                    "ranBy": 347116670300008,
                    "ranFrom": "UI",
                    "flowControl": {},
                    "priority": "high",
                    "originalPlan": {"huge": "blob2"},
                },
            ],
            "testRunState": {},
        }
    }


def _mock_response(payload, status_code=200):
    response = MagicMock()
    response.status_code = status_code
    response.json.return_value = payload
    response.raise_for_status.return_value = None
    return response


def _assert_empty_snapshot(snapshot):
    assert snapshot["pending"] == []
    assert len(snapshot["busy_plan_run_ids"]) == 0
    assert snapshot["is_paused"] is False


@pytest.fixture(autouse=True)
def _console_env():
    """Resolve console metadata and auth without real environments or secrets."""
    with patch(
        "safebreach_mcp_core.queue_state.get_api_base_url",
        return_value="https://test.safebreach.com",
    ), patch(
        "safebreach_mcp_core.queue_state.get_api_account_id",
        return_value="1234567890",
    ), patch(
        "safebreach_mcp_core.queue_state.get_auth_headers_for_console",
        return_value={"x-apitoken": "test-token"},
    ):
        yield


class TestGetOrchestratorQueueSnapshot:
    """T-1 — queue snapshot parsing, trimming, and ordering."""

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_pending_preserves_order_and_trims_fields(self, mock_get):
        mock_get.return_value = _mock_response(_queue_payload())

        snapshot = get_orchestrator_queue_snapshot("test-console")

        pending = snapshot["pending"]
        assert [p["planRunId"] for p in pending] == [
            "1785224437040.28",
            "1785224437040.29",
        ]

        first, second = pending
        assert first["name"] == "Queued Plan A"
        assert first["priority"] == "low"
        assert first["ranBy"] == 347116670300007
        assert first["ranFrom"] == "API"
        assert first["systemTags"] == []
        assert first["steps_count"] == 2
        assert second["steps_count"] == 1

        for entry in pending:
            assert "originalPlan" not in entry
            assert "steps" not in entry
            assert "actions" not in entry
            assert "edges" not in entry
            assert "flowControl" not in entry

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_busy_plan_run_ids_excludes_idle_slots(self, mock_get):
        mock_get.return_value = _mock_response(_queue_payload())

        snapshot = get_orchestrator_queue_snapshot("test-console")

        busy = snapshot["busy_plan_run_ids"]
        assert "1785200400269.2" in busy
        assert len(busy) == 1
        assert None not in busy

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_is_paused_mirrors_ispause_flag(self, mock_get):
        payload = _queue_payload()
        payload["data"]["isPause"] = True
        mock_get.return_value = _mock_response(payload)

        snapshot = get_orchestrator_queue_snapshot("test-console")

        assert snapshot["is_paused"] is True

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_calls_queue_endpoint_with_auth_and_timeout(self, mock_get):
        mock_get.return_value = _mock_response(_queue_payload())

        get_orchestrator_queue_snapshot("test-console")

        mock_get.assert_called_once()
        args, kwargs = mock_get.call_args
        url = args[0] if args else kwargs["url"]
        assert url == "https://test.safebreach.com/api/orch/v4/accounts/1234567890/queue"
        headers = kwargs["headers"]
        assert headers["x-apitoken"] == "test-token"
        assert headers["accept"] == "application/json"
        assert kwargs["timeout"] == 30

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_empty_queue_all_slots_idle(self, mock_get, caplog):
        payload = _queue_payload()
        payload["data"]["queue"] = []
        payload["data"]["slotState"] = [
            {"id": "validate-0", "status": "Idle", "slotStatus": "Idle", "planRunId": None},
        ]
        mock_get.return_value = _mock_response(payload)

        with caplog.at_level(logging.WARNING, logger="safebreach_mcp_core.queue_state"):
            snapshot = get_orchestrator_queue_snapshot("test-console")

        _assert_empty_snapshot(snapshot)
        assert not caplog.records


class TestQueueSnapshotGracefulDegradation:
    """T-2 — any snapshot failure yields an empty snapshot, never an exception."""

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_connection_error_returns_empty_snapshot(self, mock_get, caplog):
        mock_get.side_effect = requests.exceptions.ConnectionError("boom")

        with caplog.at_level(logging.WARNING, logger="safebreach_mcp_core.queue_state"):
            snapshot = get_orchestrator_queue_snapshot("test-console")

        _assert_empty_snapshot(snapshot)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_http_404_returns_empty_snapshot(self, mock_get, caplog):
        response = MagicMock()
        response.status_code = 404
        response.url = "https://test.safebreach.com/api/orch/v4/accounts/1234567890/queue"
        response.raise_for_status.side_effect = requests.exceptions.HTTPError("404")
        mock_get.return_value = response

        with caplog.at_level(logging.WARNING, logger="safebreach_mcp_core.queue_state"):
            snapshot = get_orchestrator_queue_snapshot("test-console")

        _assert_empty_snapshot(snapshot)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_rbac_403_returns_empty_snapshot(self, mock_get, caplog):
        response = MagicMock()
        response.status_code = 403
        response.url = "https://test.safebreach.com/api/orch/v4/accounts/1234567890/queue"
        mock_get.return_value = response

        with caplog.at_level(logging.WARNING, logger="safebreach_mcp_core.queue_state"):
            snapshot = get_orchestrator_queue_snapshot("test-console")

        _assert_empty_snapshot(snapshot)
        assert any(r.levelno == logging.WARNING for r in caplog.records)

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_malformed_body_returns_empty_snapshot(self, mock_get, caplog):
        for payload in ({}, {"data": {}}):
            mock_get.return_value = _mock_response(payload)
            snapshot = get_orchestrator_queue_snapshot("test-console")
            _assert_empty_snapshot(snapshot)

        bad_json = MagicMock()
        bad_json.status_code = 200
        bad_json.raise_for_status.return_value = None
        bad_json.json.side_effect = ValueError("bad json")
        mock_get.return_value = bad_json

        with caplog.at_level(logging.WARNING, logger="safebreach_mcp_core.queue_state"):
            snapshot = get_orchestrator_queue_snapshot("test-console")

        _assert_empty_snapshot(snapshot)
        assert any(r.levelno == logging.WARNING for r in caplog.records)


class TestGetOrchestratorTestStateBaseline:
    """Characterization tests for the pre-existing single-test state lookup."""

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_returns_running_for_active_slot(self, mock_get):
        mock_get.return_value = _mock_response(_queue_payload())

        assert get_orchestrator_test_state("1785200400269.2", "test-console") == "RUNNING"

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_returns_paused_when_slot_is_paused(self, mock_get):
        payload = _queue_payload()
        payload["data"]["slotState"][0]["isPaused"] = True
        mock_get.return_value = _mock_response(payload)

        assert get_orchestrator_test_state("1785200400269.2", "test-console") == "PAUSED"

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_returns_none_when_not_in_queue(self, mock_get):
        mock_get.return_value = _mock_response(_queue_payload())

        assert get_orchestrator_test_state("9999999999999.99", "test-console") is None

    @patch("safebreach_mcp_core.queue_state.requests.get")
    def test_returns_none_on_api_error(self, mock_get, caplog):
        mock_get.side_effect = requests.exceptions.ConnectionError("boom")

        with caplog.at_level(logging.WARNING, logger="safebreach_mcp_core.queue_state"):
            assert get_orchestrator_test_state("1785200400269.2", "test-console") is None

        assert any(r.levelno == logging.WARNING for r in caplog.records)
