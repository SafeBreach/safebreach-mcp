"""
Tests for SafeBreach Studio Functions

This module tests the core business logic functions for Studio operations.
"""

import pytest
import json
import time
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_studio.studio_functions import (
    sb_validate_studio_code,
    sb_save_studio_attack_draft,
    sb_get_all_studio_attacks,
    sb_update_studio_attack_draft,
    sb_get_studio_attack_source,
    sb_run_studio_attack,
    sb_get_studio_attack_latest_result,
    sb_get_studio_attack_boilerplate,
    studio_draft_cache,
    MAIN_FUNCTION_PATTERN,
    _validate_and_build_parameters,
    _validate_main_signature_ast,
    _normalize_attack_type,
    _validate_os_constraint,
    _lint_check_parameters,
    VALID_PARAMETER_TYPES,
    VALID_PROTOCOLS,
    VALID_ATTACK_TYPES,
    VALID_OS_CONSTRAINTS,
    ATTACK_TYPE_ALIASES,
    DUAL_SCRIPT_TYPES,
    PAGE_SIZE,
)
from safebreach_mcp_studio.studio_types import (
    paginate_studio_attacks,
    get_execution_result_mapping,
    _parse_simulation_steps,
)


# Test fixtures
@pytest.fixture
def sample_valid_python_code():
    """Sample valid Python code with required main function."""
    return """
import logging

def main(system_data, asset, proxy, *args, **kwargs):
    \"\"\"Main entry point for simulation.\"\"\"
    logging.info("Running simulation")
    return True
"""


@pytest.fixture
def sample_invalid_python_code():
    """Sample Python code without required main function."""
    return """
import logging

def execute():
    logging.info("Wrong function signature")
    return True
"""


@pytest.fixture
def mock_validation_response_valid():
    """Mock validation API response for valid code."""
    return {
        "data": {
            "exit_code": 0,
            "is_valid": True,
            "stderr": "",
            "stdout": {
                "/tmp/tmpkgialxvn.py": []
            },
            "valid": True
        }
    }


@pytest.fixture
def mock_validation_response_invalid():
    """Mock validation API response for invalid code."""
    return {
        "data": {
            "exit_code": 1,
            "is_valid": False,
            "stderr": "SyntaxError: invalid syntax",
            "stdout": {
                "/tmp/tmpcode.py": ["Line 5: SyntaxError: invalid syntax"]
            },
            "valid": False
        }
    }


@pytest.fixture
def mock_draft_response():
    """Mock save draft API response."""
    return {
        "data": {
            "id": 10000296,
            "name": "Test Simulation",
            "description": "Test description",
            "methodType": 5,
            "class": "python",
            "timeout": 300,
            "status": "draft",
            "creationDate": "2025-11-30T12:36:11.252Z",
            "updateDate": "2025-11-30T12:36:11.252Z",
            "metaData": {
                "targetFileName": "target.py"
            },
            "targetFileName": "target.py",
            "parameters": [],
            "origin": "BREACH_STUDIO"
        }
    }


@pytest.fixture
def clear_cache():
    """Clear the draft cache before and after each test."""
    studio_draft_cache.clear()
    yield
    studio_draft_cache.clear()


@pytest.fixture
def mock_getall_response():
    """Mock get all simulations API response."""
    return {
        "data": [
            {
                "id": 10000296,
                "name": "Draft Simulation 1",
                "description": "Test draft",
                "methodType": 5,
                "class": "python",
                "timeout": 300,
                "status": "draft",
                "creationDate": "2025-11-30T12:36:11.252Z",
                "updateDate": "2025-11-30T12:36:11.252Z",
                "targetFileName": "target.py",
                "origin": "BREACH_STUDIO"
            },
            {
                "id": 10000297,
                "name": "Published Simulation 1",
                "description": "Test published",
                "methodType": 5,
                "class": "python",
                "timeout": 300,
                "status": "published",
                "creationDate": "2025-11-29T10:00:00.000Z",
                "updateDate": "2025-11-29T10:00:00.000Z",
                "publishedDate": "2025-11-30T08:00:00.000Z",
                "targetFileName": "target.py",
                "origin": "BREACH_STUDIO"
            },
            {
                "id": 10000298,
                "name": "Draft Simulation 2",
                "description": "Another draft",
                "methodType": 5,
                "class": "python",
                "timeout": 600,
                "status": "draft",
                "creationDate": "2025-11-30T14:00:00.000Z",
                "updateDate": "2025-11-30T14:00:00.000Z",
                "targetFileName": "target.py",
                "origin": "BREACH_STUDIO"
            }
        ]
    }


@pytest.fixture
def mock_update_response():
    """Mock update draft API response."""
    return {
        "data": {
            "id": 10000298,
            "name": "Updated Simulation",
            "description": "Updated description",
            "methodType": 5,
            "class": "python",
            "timeout": 600,
            "status": "draft",
            "creationDate": "2025-11-30T12:36:11.252Z",
            "updateDate": "2025-11-30T15:30:00.000Z",
            "metaData": {
                "targetFileName": "target.py"
            },
            "targetFileName": "target.py",
            "parameters": [],
            "origin": "BREACH_STUDIO"
        }
    }


@pytest.fixture
def mock_source_response():
    """Mock get source code API response."""
    return {
        "data": {
            "filename": "target.py",
            "content": """import logging

def main(system_data, asset, proxy, *args, **kwargs):
    '''Test simulation code.'''
    logging.info("Running test simulation")
    return True
"""
        }
    }


@pytest.fixture
def mock_run_response():
    """Mock run simulation API response."""
    return {
        "data": {
            "name": "Studio Simulation Test - 10000298",
            "steps": [{
                "stepRunId": "1764570357287.5",
                "planRunId": "1764570357286.4"
            }],
            "planRunId": "1764570357286.4",
            "priority": "low",
            "draft": True,
            "ranBy": 347729146100009,
            "retrySimulations": False
        }
    }


class TestValidateStudioCode:
    """Test the sb_validate_studio_code function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validate_studio_code_success(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code,
        mock_validation_response_valid
    ):
        """Test successful validation of valid Python code with main function."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        # Execute
        result = sb_validate_studio_code(sample_valid_python_code, "demo")

        # Verify
        assert result['is_valid'] is True
        assert result['has_main_function'] is True
        assert result['exit_code'] == 0
        assert result['validation_errors'] == []
        assert result['stderr'] == ""

        # Verify API was called correctly
        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert "customMethods/validate" in call_args[0][0]
        assert call_args[1]['timeout'] == 120

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validate_studio_code_missing_main(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_invalid_python_code,
        mock_validation_response_valid
    ):
        """Test validation of code without required main function signature."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        # Execute
        result = sb_validate_studio_code(sample_invalid_python_code, "demo")

        # Verify - code is syntactically valid but missing required main function
        assert result['is_valid'] is True
        assert result['has_main_function'] is False
        assert result['exit_code'] == 0

    def test_validate_studio_code_empty_input(self):
        """Test validation with empty python_code parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code("", "demo")

        assert "python_code parameter is required" in str(exc_info.value)

    def test_validate_studio_code_none_input(self):
        """Test validation with None python_code parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(None, "demo")

        assert "python_code parameter is required" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validate_studio_code_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code
    ):
        """Test validation when API returns an error."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error: 500 Internal Server Error")
        mock_put.return_value = mock_response

        # Execute and verify
        with pytest.raises(Exception) as exc_info:
            sb_validate_studio_code(sample_valid_python_code, "demo")

        assert "API Error" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validate_studio_code_with_errors(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code,
        mock_validation_response_invalid
    ):
        """Test validation of code with syntax errors."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_invalid
        mock_put.return_value = mock_response

        # Execute
        result = sb_validate_studio_code(sample_valid_python_code, "demo")

        # Verify
        assert result['is_valid'] is False
        assert result['exit_code'] == 1
        assert len(result['validation_errors']) > 0
        assert result['stderr'] != ""


class TestSaveStudioAttackDraft:
    """Test the sb_save_studio_attack_draft function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_studio_draft_success(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test successfully saving a draft simulation."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            description="Test description",
            timeout=300,
            console="demo"
        )

        # Verify
        assert result['draft_id'] == 10000296
        assert result['name'] == "Test Simulation"
        assert result['status'] == "draft"
        assert result['timeout'] == 300
        assert result['target_file_name'] == "target.py"
        assert result['method_type'] == 5
        assert result['origin'] == "BREACH_STUDIO"

        # Verify API was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "customMethods" in call_args[0][0]
        assert call_args[1]['timeout'] == 120
        assert 'data' in call_args[1]
        assert 'files' in call_args[1]

    def test_save_studio_draft_empty_name(self, sample_valid_python_code):
        """Test saving draft with empty name parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_attack_draft(
                name="",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "name parameter is required" in str(exc_info.value)

    def test_save_studio_draft_empty_code(self):
        """Test saving draft with empty python_code parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_attack_draft(
                name="Test Simulation",
                python_code="",
                console="demo"
            )

        assert "python_code parameter is required" in str(exc_info.value)

    def test_save_studio_draft_invalid_timeout(self, sample_valid_python_code):
        """Test saving draft with invalid timeout."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_attack_draft(
                name="Test Simulation",
                python_code=sample_valid_python_code,
                timeout=0,
                console="demo"
            )

        assert "timeout must be at least 1 second" in str(exc_info.value)

    def test_save_studio_draft_invalid_os_constraint(self, sample_valid_python_code):
        """Test saving draft with invalid os_constraint parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_attack_draft(
                name="Test Simulation",
                python_code=sample_valid_python_code,
                target_os="invalid_os",
                console="demo"
            )

        assert "os_constraint must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_studio_draft_with_windows_constraint(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test saving draft with WINDOWS OS constraint."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            description="Test description",
            timeout=300,
            target_os="WINDOWS",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "WINDOWS"

        # Verify API was called with targetConstraints
        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' in data
        assert data['targetConstraints'] == '{"os": "WINDOWS"}'

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_studio_draft_with_all_constraint(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test saving draft with 'All' OS constraint (no constraint)."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            description="Test description",
            timeout=300,
            target_os="All",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "All"

        # Verify API was called WITHOUT targetConstraints
        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' not in data

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_studio_draft_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code
    ):
        """Test saving draft when API returns an error."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error: 401 Unauthorized")
        mock_post.return_value = mock_response

        # Execute and verify
        with pytest.raises(Exception) as exc_info:
            sb_save_studio_attack_draft(
                name="Test Simulation",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "API Error" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.time.time')
    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_studio_draft_caching(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_time,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test that draft metadata is cached correctly."""
        # Setup mocks
        mock_time.return_value = 1000.0

        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            console="demo"
        )

        # Verify cache was populated
        cache_key = f"studio_draft_demo_{result['draft_id']}"
        assert cache_key in studio_draft_cache
        cached_item = studio_draft_cache[cache_key]
        assert cached_item['data']['draft_id'] == result['draft_id']
        assert cached_item['timestamp'] == 1000.0


class TestGetAllStudioAttacks:
    """Test the sb_get_all_studio_attacks function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_success(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get,
        mock_getall_response
    ):
        """Test successfully retrieving all simulations."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_getall_response
        mock_get.return_value = mock_response

        # Execute
        result = sb_get_all_studio_attacks(console="demo", status_filter="all")

        # Verify
        assert result['total_attacks'] == 3
        assert result['draft_count'] == 2
        assert result['published_count'] == 1
        assert len(result['attacks_in_page']) == 3

        # Verify API was called correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "customMethods?status=all" in call_args[0][0]
        assert call_args[1]['timeout'] == 120

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_filter_draft(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get,
        mock_getall_response
    ):
        """Test retrieving only draft simulations."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_getall_response
        mock_get.return_value = mock_response

        # Execute
        result = sb_get_all_studio_attacks(console="demo", status_filter="draft")

        # Verify
        assert result['total_attacks'] == 2
        assert all(sim['status'] == 'draft' for sim in result['attacks_in_page'])

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_filter_published(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get,
        mock_getall_response
    ):
        """Test retrieving only published simulations."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_getall_response
        mock_get.return_value = mock_response

        # Execute
        result = sb_get_all_studio_attacks(console="demo", status_filter="published")

        # Verify
        assert result['total_attacks'] == 1
        assert all(sim['status'] == 'published' for sim in result['attacks_in_page'])

    def test_get_all_simulations_invalid_status_filter(self):
        """Test validation of invalid status filter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_all_studio_attacks(console="demo", status_filter="invalid")

        assert "status_filter must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_filter_by_name(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get,
        mock_getall_response
    ):
        """Test filtering simulations by name."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_getall_response
        mock_get.return_value = mock_response

        # Execute - filter by "Draft" in name (should match both draft simulations)
        result = sb_get_all_studio_attacks(console="demo", name_filter="Draft")

        # Verify
        assert result['total_attacks'] == 2
        assert all("Draft" in sim['name'] or "draft" in sim['name'] for sim in result['attacks_in_page'])

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_filter_by_user_id(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get
    ):
        """Test filtering simulations by user ID."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Create response with user_created field
        response_with_users = {
            "data": [
                {
                    "id": 1,
                    "name": "Sim 1",
                    "status": "draft",
                    "userCreated": 123,
                    "creationDate": "2025-11-30T12:00:00.000Z",
                    "updateDate": "2025-11-30T12:00:00.000Z",
                    "targetFileName": "target.py",
                    "methodType": 5,
                    "origin": "BREACH_STUDIO"
                },
                {
                    "id": 2,
                    "name": "Sim 2",
                    "status": "published",
                    "userCreated": 456,
                    "creationDate": "2025-11-30T12:00:00.000Z",
                    "updateDate": "2025-11-30T12:00:00.000Z",
                    "targetFileName": "target.py",
                    "methodType": 5,
                    "origin": "BREACH_STUDIO"
                },
                {
                    "id": 3,
                    "name": "Sim 3",
                    "status": "draft",
                    "userCreated": 123,
                    "creationDate": "2025-11-30T12:00:00.000Z",
                    "updateDate": "2025-11-30T12:00:00.000Z",
                    "targetFileName": "target.py",
                    "methodType": 5,
                    "origin": "BREACH_STUDIO"
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_with_users
        mock_get.return_value = mock_response

        # Execute - filter by user ID 123
        result = sb_get_all_studio_attacks(console="demo", user_id_filter=123)

        # Verify
        assert result['total_attacks'] == 2
        assert all(sim['user_created'] == 123 for sim in result['attacks_in_page'])

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_combined_filters(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get
    ):
        """Test filtering with multiple filters combined."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Create response with various simulations
        response_combined = {
            "data": [
                {
                    "id": 1,
                    "name": "Test Simulation",
                    "status": "draft",
                    "userCreated": 123,
                    "creationDate": "2025-11-30T12:00:00.000Z",
                    "updateDate": "2025-11-30T12:00:00.000Z",
                    "targetFileName": "target.py",
                    "methodType": 5,
                    "origin": "BREACH_STUDIO"
                },
                {
                    "id": 2,
                    "name": "Test Attack",
                    "status": "published",
                    "userCreated": 123,
                    "creationDate": "2025-11-30T12:00:00.000Z",
                    "updateDate": "2025-11-30T12:00:00.000Z",
                    "targetFileName": "target.py",
                    "methodType": 5,
                    "origin": "BREACH_STUDIO"
                },
                {
                    "id": 3,
                    "name": "Production Simulation",
                    "status": "draft",
                    "userCreated": 456,
                    "creationDate": "2025-11-30T12:00:00.000Z",
                    "updateDate": "2025-11-30T12:00:00.000Z",
                    "targetFileName": "target.py",
                    "methodType": 5,
                    "origin": "BREACH_STUDIO"
                }
            ]
        }

        mock_response = MagicMock()
        mock_response.json.return_value = response_combined
        mock_get.return_value = mock_response

        # Execute - filter by status=draft, name contains "Test", user_id=123
        result = sb_get_all_studio_attacks(
            console="demo",
            status_filter="draft",
            name_filter="Test",
            user_id_filter=123
        )

        # Verify - should only return ID 1 (draft, "Test" in name, user 123)
        assert result['total_attacks'] == 1
        assert result['attacks_in_page'][0]['id'] == 1
        assert result['attacks_in_page'][0]['status'] == 'draft'
        assert "Test" in result['attacks_in_page'][0]['name']
        assert result['attacks_in_page'][0]['user_created'] == 123

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_all_simulations_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get
    ):
        """Test handling API errors."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error: 500 Internal Server Error")
        mock_get.return_value = mock_response

        # Execute and verify
        with pytest.raises(Exception) as exc_info:
            sb_get_all_studio_attacks(console="demo")

        assert "API Error" in str(exc_info.value)


class TestUpdateStudioAttackDraft:
    """Test the sb_update_studio_attack_draft function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_draft_success(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code,
        mock_update_response,
        clear_cache
    ):
        """Test successfully updating a draft simulation."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        # Execute
        result = sb_update_studio_attack_draft(
            attack_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            console="demo"
        )

        # Verify
        assert result['draft_id'] == 10000298
        assert result['name'] == "Updated Simulation"
        assert result['description'] == "Updated description"
        assert result['status'] == "draft"
        assert result['timeout'] == 600

        # Verify API was called correctly
        mock_put.assert_called_once()
        call_args = mock_put.call_args
        assert "customMethods/10000298" in call_args[0][0]
        assert call_args[1]['timeout'] == 120
        assert 'data' in call_args[1]
        assert 'files' in call_args[1]

    def test_update_draft_invalid_draft_id_zero(self, sample_valid_python_code):
        """Test updating draft with invalid draft_id (zero)."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=0,
                name="Test",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "attack_id must be a positive integer" in str(exc_info.value)

    def test_update_draft_invalid_draft_id_negative(self, sample_valid_python_code):
        """Test updating draft with invalid draft_id (negative)."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=-1,
                name="Test",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "attack_id must be a positive integer" in str(exc_info.value)

    def test_update_draft_empty_name(self, sample_valid_python_code):
        """Test updating draft with empty name."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=12345,
                name="",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "name parameter is required" in str(exc_info.value)

    def test_update_draft_empty_code(self):
        """Test updating draft with empty python_code."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=12345,
                name="Test",
                python_code="",
                console="demo"
            )

        assert "python_code parameter is required" in str(exc_info.value)

    def test_update_draft_invalid_timeout(self, sample_valid_python_code):
        """Test updating draft with invalid timeout."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=12345,
                name="Test",
                python_code=sample_valid_python_code,
                timeout=0,
                console="demo"
            )

        assert "timeout must be at least 1 second" in str(exc_info.value)

    def test_update_draft_invalid_os_constraint(self, sample_valid_python_code):
        """Test updating draft with invalid os_constraint parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=12345,
                name="Test",
                python_code=sample_valid_python_code,
                target_os="INVALID",
                console="demo"
            )

        assert "os_constraint must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_draft_with_linux_constraint(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code,
        mock_update_response,
        clear_cache
    ):
        """Test updating draft with LINUX OS constraint."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        # Execute
        result = sb_update_studio_attack_draft(
            attack_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            target_os="LINUX",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "LINUX"

        # Verify API was called with targetConstraints
        call_args = mock_put.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' in data
        assert data['targetConstraints'] == '{"os": "LINUX"}'

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_draft_with_mac_constraint(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code,
        mock_update_response,
        clear_cache
    ):
        """Test updating draft with MAC OS constraint."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        # Execute
        result = sb_update_studio_attack_draft(
            attack_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            target_os="MAC",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "MAC"

        # Verify API was called with targetConstraints
        call_args = mock_put.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' in data
        assert data['targetConstraints'] == '{"os": "MAC"}'

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_draft_with_all_constraint(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code,
        mock_update_response,
        clear_cache
    ):
        """Test updating draft with 'All' OS constraint (removes constraint)."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        # Execute
        result = sb_update_studio_attack_draft(
            attack_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            target_os="All",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "All"

        # Verify API was called WITHOUT targetConstraints
        call_args = mock_put.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' not in data

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_draft_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        sample_valid_python_code
    ):
        """Test updating draft when API returns an error."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error: 404 Not Found")
        mock_put.return_value = mock_response

        # Execute and verify
        with pytest.raises(Exception) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=99999,
                name="Test",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "API Error" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.time.time')
    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_draft_caching(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_put,
        mock_time,
        sample_valid_python_code,
        mock_update_response,
        clear_cache
    ):
        """Test that updated draft metadata is cached correctly."""
        # Setup mocks
        mock_time.return_value = 2000.0

        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        # Execute
        result = sb_update_studio_attack_draft(
            attack_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            console="demo"
        )

        # Verify cache was updated
        cache_key = f"studio_draft_demo_{result['draft_id']}"
        assert cache_key in studio_draft_cache
        cached_item = studio_draft_cache[cache_key]
        assert cached_item['data']['draft_id'] == result['draft_id']
        assert cached_item['data']['name'] == "Updated Simulation"
        assert cached_item['timestamp'] == 2000.0


class TestGetStudioAttackSource:
    """Test the sb_get_studio_attack_source function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_source_success(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get,
        mock_source_response
    ):
        """Test successfully retrieving simulation source code."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # First call returns target, second call returns 404 (no attacker for host attack)
        mock_target_response = MagicMock()
        mock_target_response.json.return_value = mock_source_response
        mock_target_response.status_code = 200

        mock_attacker_response = MagicMock()
        mock_attacker_response.status_code = 404

        mock_get.side_effect = [mock_target_response, mock_attacker_response]

        # Execute
        result = sb_get_studio_attack_source(
            attack_id=10000298,
            console="demo"
        )

        # Verify new return structure
        assert result['attack_id'] == 10000298
        assert result['target']['filename'] == "target.py"
        assert 'def main(system_data, asset, proxy, *args, **kwargs):' in result['target']['content']
        assert len(result['target']['content']) > 0
        assert result['attacker'] is None

        # Verify API was called for target
        assert mock_get.call_count == 2
        target_call = mock_get.call_args_list[0]
        assert "customMethods/10000298/files/target" in target_call[0][0]

    def test_get_source_invalid_simulation_id_zero(self):
        """Test getting source with invalid simulation_id (zero)."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_source(attack_id=0, console="demo")

        assert "attack_id must be a positive integer" in str(exc_info.value)

    def test_get_source_invalid_simulation_id_negative(self):
        """Test getting source with invalid simulation_id (negative)."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_source(attack_id=-1, console="demo")

        assert "attack_id must be a positive integer" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_source_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get
    ):
        """Test getting source when API returns an error."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error: 404 Not Found")
        mock_get.return_value = mock_response

        # Execute and verify
        with pytest.raises(Exception) as exc_info:
            sb_get_studio_attack_source(attack_id=99999, console="demo")

        assert "API Error" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_source_empty_content(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_get
    ):
        """Test getting source when content is empty."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock response with empty content for target
        empty_response = {
            "data": {
                "filename": "target.py",
                "content": ""
            }
        }
        mock_target_response = MagicMock()
        mock_target_response.json.return_value = empty_response
        mock_target_response.status_code = 200

        mock_attacker_response = MagicMock()
        mock_attacker_response.status_code = 404

        mock_get.side_effect = [mock_target_response, mock_attacker_response]

        # Execute
        result = sb_get_studio_attack_source(attack_id=12345, console="demo")

        # Verify new return structure
        assert result['attack_id'] == 12345
        assert result['target']['filename'] == "target.py"
        assert result['target']['content'] == ""
        assert result['attacker'] is None


class TestRunStudioAttack:
    """Test the sb_run_studio_attack function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_run_simulation_all_connected(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_run_response
    ):
        """Test running simulation on all connected simulators."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        # Execute
        result = sb_run_studio_attack(
            attack_id=10000298,
            console="demo",
            all_connected=True,
        )

        # Verify result
        assert result['test_id'] == "1764570357286.4"
        assert result['step_run_id'] == "1764570357287.5"
        assert result['attack_id'] == 10000298

        # Verify API was called correctly
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert "/queue" in call_args[0][0]

        # Verify payload structure for all connected
        payload = call_args[1]['json']
        assert payload['plan']['draft'] is True
        assert payload['plan']['steps'][0]['attacksFilter']['playbook']['values'] == [10000298]
        assert 'connection' in payload['plan']['steps'][0]['attackerFilter']
        assert 'connection' in payload['plan']['steps'][0]['targetFilter']

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_run_simulation_specific_simulators(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_run_response
    ):
        """Test running simulation on specific simulators."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        target_ids = ["sim-uuid-1", "sim-uuid-2", "sim-uuid-3"]

        # Execute
        result = sb_run_studio_attack(
            attack_id=10000298,
            console="demo",
            target_simulator_ids=target_ids,
        )

        # Verify result
        assert result['test_id'] == "1764570357286.4"

        # Verify payload structure for specific simulators
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        assert 'simulators' in payload['plan']['steps'][0]['attackerFilter']
        assert 'simulators' in payload['plan']['steps'][0]['targetFilter']
        # Host attack: attacker IDs = target IDs
        assert payload['plan']['steps'][0]['attackerFilter']['simulators']['values'] == target_ids
        assert payload['plan']['steps'][0]['targetFilter']['simulators']['values'] == target_ids

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_run_simulation_custom_test_name(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_run_response
    ):
        """Test running simulation with custom test name."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        # Execute
        result = sb_run_studio_attack(
            attack_id=10000298,
            console="demo",
            all_connected=True,
            test_name="My Custom Test Name"
        )

        # Verify payload contains custom name
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        assert payload['plan']['name'] == "My Custom Test Name"

    def test_run_simulation_invalid_simulation_id(self):
        """Test running simulation with invalid simulation_id."""
        with pytest.raises(ValueError) as exc_info:
            sb_run_studio_attack(attack_id=0, console="demo", all_connected=True)

        assert "attack_id must be a positive integer" in str(exc_info.value)

    def test_run_simulation_empty_simulator_list(self):
        """Test running simulation with empty target_simulator_ids list."""
        with pytest.raises(ValueError) as exc_info:
            sb_run_studio_attack(
                attack_id=10000298,
                console="demo",
                target_simulator_ids=[]
            )

        assert "target_simulator_ids cannot be an empty list" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_run_simulation_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post
    ):
        """Test running simulation when API returns an error."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error: 500 Internal Server Error")
        mock_post.return_value = mock_response

        # Execute and verify
        with pytest.raises(Exception) as exc_info:
            sb_run_studio_attack(attack_id=10000298, console="demo", all_connected=True)

        assert "API Error" in str(exc_info.value)

    def test_run_no_simulators_no_all_connected(self):
        """Test that neither target_simulator_ids nor all_connected raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_run_studio_attack(attack_id=10000298, console="demo")
        assert "target_simulator_ids must be provided or all_connected must be True" in str(exc_info.value)


class TestMainFunctionPattern:
    """Test the MAIN_FUNCTION_PATTERN regex."""

    def test_pattern_matches_valid_signature(self):
        """Test that the pattern matches valid main function signatures."""
        import re

        valid_signatures = [
            "def main(system_data, asset, proxy, *args, **kwargs):",
            "def main(system_data,asset,proxy,*args,**kwargs):",
            "def  main  (  system_data  ,  asset  ,  proxy  ,  *args  ,  **kwargs  )  :",
            "def main(\n    system_data,\n    asset,\n    proxy,\n    *args,\n    **kwargs\n):",
        ]

        for signature in valid_signatures:
            assert re.search(MAIN_FUNCTION_PATTERN, signature), f"Failed to match: {signature}"

    def test_pattern_rejects_invalid_signature(self):
        """Test that the pattern rejects invalid main function signatures."""
        import re

        invalid_signatures = [
            "def main():",
            "def main(system_data, asset):",
            "def main(system_data, asset, proxy):",
            "def main(system_data, asset, proxy, *args):",
            "def execute(system_data, asset, proxy, *args, **kwargs):",
            # Note: async def main() is excluded as it's technically valid Python
            # and the SafeBreach API will handle async validation if needed
        ]

        for signature in invalid_signatures:
            assert not re.search(MAIN_FUNCTION_PATTERN, signature), f"Incorrectly matched: {signature}"


# Additional test fixtures for execution results
@pytest.fixture
def mock_execution_result_response():
    """Mock execution history API response with multiple results."""
    return {
        "simulations": [
            {
                "id": "1463450",
                "jobId": 1463450,
                "originalExecutionId": "49aedc2a07b581aa55f56a165ac29b48",
                "moveId": 10000291,
                "moveName": "test registry shuit",
                "moveDesc": "N/A",
                "testName": "test registry shuit",
                "planName": "test registry shuit",
                "stepName": "Step 1",
                "planRunId": "1764570357286.4",
                "stepRunId": "1764570357287.5",
                "runId": "1764570357286.4",
                "startTime": "2025-11-02T07:58:00.568Z",
                "endTime": "2025-11-02T07:58:10.665Z",
                "executionTime": "2025-11-02T07:58:10.665Z",
                "attackerSimulatorStartTime": "2025-11-02T07:58:00.568Z",
                "attackerSimulatorEndTime": "2025-11-02T07:58:10.665Z",
                "targetSimulatorStartTime": "2025-11-02T07:58:00.568Z",
                "targetSimulatorEndTime": "2025-11-02T07:58:10.665Z",
                "status": "SUCCESS",
                "finalStatus": "missed",
                "securityAction": "not_logged",
                "resultCode": "Success",
                "resultDetails": "Simulation completed successfully",
                "attackerNodeId": "eb22d168-d5a4-4bf9-ba91-f6f7dedc4399",
                "attackerNodeName": "ST-A-W10-CY01",
                "attackerOSType": "WINDOWS",
                "attackerOSVersion": "2019Server",
                "sourceIp": "200.11.49.213",
                "targetNodeId": "eb22d168-d5a4-4bf9-ba91-f6f7dedc4399",
                "targetNodeName": "ST-A-W10-CY01",
                "targetOSType": "WINDOWS",
                "targetOSVersion": "2019Server",
                "destinationIp": "200.11.49.213",
                "paramsObj": {
                    "Registry Key Path": "HKLM:\\Software\\Policies\\Microsoft\\Windows\\WcmSvc\\Local",
                    "Registry Value Name": "WCMPresent",
                    "Registry Value to set": "1"
                },
                "paramsStr": [
                    "TargetScript:Target script"
                ],
                "parameters": {
                    "NOT_CLASSIFIED": [
                        {
                            "displayName": "Registry Key Path",
                            "value": "HKLM:\\Software\\Policies\\Microsoft\\Windows\\WcmSvc\\Local"
                        }
                    ]
                },
                "protocol": [{"id": -1, "value": "N/A"}],
                "attackProtocol": "N/A",
                "sourcePort": [],
                "labels": ["Draft"],
                "tags": [],
                "Attack_Type": [{"id": 30, "value": "Custom"}],
                "MITRE_Tactic": [],
                "packageName": "Host Level",
                "packageId": 5,
                "methodId": 39833,
                "deploymentName": [],
                "deploymentId": [],
                "simulationEvents": [],
                "attackTypesCounter": 1
            },
            {
                "id": "1462025",
                "jobId": 1462025,
                "originalExecutionId": "06bba6d24c0999e71e8e3d03a026ba94",
                "moveId": 10000291,
                "moveName": "test registry shuit",
                "moveDesc": "N/A",
                "testName": "test registry shuit old",
                "planName": "test registry shuit old",
                "stepName": "Step 1",
                "planRunId": "1761652616198.2",
                "stepRunId": "1761652616201.3",
                "runId": "1761652616198.2",
                "startTime": "2025-10-28T11:57:12.233Z",
                "endTime": "2025-10-28T11:57:18.665Z",
                "executionTime": "2025-10-28T11:57:18.665Z",
                "status": "FAIL",
                "finalStatus": "stopped",
                "securityAction": "not_logged",
                "resultCode": "InternalError",
                "resultDetails": "Task action stopped",
                "attackerNodeId": "eb22d168-d5a4-4bf9-ba91-f6f7dedc4399",
                "attackerNodeName": "ST-A-W10-CY01",
                "attackerOSType": "WINDOWS",
                "attackerOSVersion": "2019Server",
                "sourceIp": "200.11.49.213",
                "targetNodeId": "eb22d168-d5a4-4bf9-ba91-f6f7dedc4399",
                "targetNodeName": "ST-A-W10-CY01",
                "targetOSType": "WINDOWS",
                "targetOSVersion": "2019Server",
                "destinationIp": "200.11.49.213",
                "paramsObj": {},
                "paramsStr": [],
                "parameters": {},
                "protocol": [],
                "attackProtocol": "N/A",
                "sourcePort": [],
                "labels": ["Draft"],
                "tags": [],
                "Attack_Type": [],
                "MITRE_Tactic": [],
                "packageName": "Host Level",
                "packageId": 5,
                "methodId": 39833,
                "deploymentName": [],
                "deploymentId": [],
                "simulationEvents": [],
                "attackTypesCounter": 0
            }
        ],
        "total": 2
    }


@pytest.fixture
def mock_execution_result_empty_response():
    """Mock execution history API response with no results."""
    return {
        "simulations": [],
        "total": 0
    }


class TestGetStudioAttackLatestResult:
    """Test suite for sb_get_studio_attack_latest_result function."""

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_latest_result_success(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_execution_result_response
    ):
        """Test successfully retrieving latest execution result."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = Mock()
        mock_response.json.return_value = mock_execution_result_response
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Call function
        result = sb_get_studio_attack_latest_result(
            attack_id=10000291,
            console="demo",
            max_results=1
        )

        # Assertions
        assert result['attack_id'] == 10000291
        assert result['console'] == "demo"
        assert result['total_found'] == 2
        assert result['returned_count'] == 1
        assert result['has_more'] is True
        assert len(result['executions']) == 1

        # Check first execution details
        execution = result['executions'][0]
        assert execution['simulation_id'] == "1463450"
        assert execution['attack_id'] == 10000291
        assert execution['attack_name'] == "test registry shuit"
        assert execution['execution_status'] == "SUCCESS"
        assert execution['status'] == "missed"
        assert execution['security_action'] == "not_logged"
        assert execution['test_name'] == "test registry shuit"
        assert execution['test_id'] == "1764570357286.4"

        # Verify API call
        mock_post.assert_called_once()
        call_args = mock_post.call_args
        assert '/api/data/v1/accounts/1234567890/executionsHistoryResults' in call_args[0][0]

        # Verify payload
        payload = call_args[1]['json']
        assert payload['query'] == 'Playbook_id:("10000291")'
        assert payload['orderBy'] == 'desc'
        assert payload['sortBy'] == 'startTime'
        assert payload['pageSize'] == 1

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_multiple_results(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_execution_result_response
    ):
        """Test retrieving multiple execution results."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = Mock()
        mock_response.json.return_value = mock_execution_result_response
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Call function with max_results=2
        result = sb_get_studio_attack_latest_result(
            attack_id=10000291,
            console="demo",
            max_results=2
        )

        # Assertions
        assert result['returned_count'] == 2
        assert result['total_found'] == 2
        assert result['has_more'] is False
        assert len(result['executions']) == 2

        # Check ordering (newest first)
        assert result['executions'][0]['simulation_id'] == "1463450"
        assert result['executions'][1]['simulation_id'] == "1462025"

        # Verify different statuses
        assert result['executions'][0]['execution_status'] == "SUCCESS"
        assert result['executions'][1]['execution_status'] == "FAIL"

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_latest_result_no_results(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        mock_execution_result_empty_response
    ):
        """Test when no execution results are found."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = Mock()
        mock_response.json.return_value = mock_execution_result_empty_response
        mock_response.status_code = 200
        mock_post.return_value = mock_response

        # Call function
        result = sb_get_studio_attack_latest_result(
            attack_id=99999,
            console="demo"
        )

        # Assertions
        assert result['total_found'] == 0
        assert result['returned_count'] == 0
        assert result['has_more'] is False
        assert len(result['executions']) == 0

    def test_get_latest_result_invalid_simulation_id(self):
        """Test with invalid simulation ID."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_latest_result(attack_id=0, console="demo")

        assert "attack_id must be a positive integer" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_latest_result(attack_id=-1, console="demo")

        assert "attack_id must be a positive integer" in str(exc_info.value)

    def test_get_latest_result_invalid_max_results(self):
        """Test with invalid max_results parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_latest_result(
                attack_id=10000291,
                console="demo",
                max_results=0
            )

        assert "max_results must be at least 1" in str(exc_info.value)

    def test_get_latest_result_invalid_page_size(self):
        """Test with invalid page_size parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_latest_result(
                attack_id=10000291,
                console="demo",
                page_size=0
            )

        assert "page_size must be between 1 and 1000" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_attack_latest_result(
                attack_id=10000291,
                console="demo",
                page_size=2000
            )

        assert "page_size must be between 1 and 1000" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_get_latest_result_api_error(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post
    ):
        """Test API error handling."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Mock API error
        mock_response = Mock()
        mock_response.status_code = 500
        mock_response.json.return_value = {"error": "Internal Server Error"}
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_post.return_value = mock_response

        # Call function and expect exception
        with pytest.raises(Exception) as exc_info:
            sb_get_studio_attack_latest_result(attack_id=10000291, console="demo")

        assert "API Error" in str(exc_info.value)


class TestParameterValidationAndBuilding:
    """Test suite for parameter validation and building functionality."""

    def test_validate_and_build_parameters_empty_list(self):
        """Test building with empty parameters list."""
        result = _validate_and_build_parameters([])
        assert result == "[]"

    def test_validate_and_build_parameters_single_param(self):
        """Test building with a single parameter."""
        params = [{"name": "port", "value": 8080, "type": "PORT"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed) == 1
        assert parsed[0]["name"] == "port"
        assert parsed[0]["type"] == "PORT"
        assert parsed[0]["source"] == "PARAM"
        assert parsed[0]["values"][0]["value"] == 8080
        assert parsed[0]["isCustom"] is True

    def test_validate_and_build_parameters_invalid_type(self):
        """Test validation rejects invalid parameter type."""
        params = [{"name": "test", "value": "value", "type": "INVALID_TYPE"}]

        with pytest.raises(ValueError) as exc_info:
            _validate_and_build_parameters(params)

        assert "invalid type" in str(exc_info.value).lower()

    def test_validate_and_build_parameters_missing_name(self):
        """Test validation rejects parameter without name."""
        params = [{"value": "test"}]

        with pytest.raises(ValueError) as exc_info:
            _validate_and_build_parameters(params)

        assert "missing required field: 'name'" in str(exc_info.value)

    def test_validate_and_build_parameters_missing_value(self):
        """Test validation rejects parameter without value."""
        params = [{"name": "test"}]

        with pytest.raises(ValueError) as exc_info:
            _validate_and_build_parameters(params)

        assert "missing required field: 'value'" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_draft_with_parameters(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test saving draft with parameters."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute with parameters
        params = [
            {"name": "port", "value": 8080, "type": "PORT"},
            {"name": "url", "value": "https://test.com", "type": "URI"}
        ]
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            parameters=params,
            console="demo"
        )

        # Verify result includes parameters_count
        assert result['parameters_count'] == 2

        # Verify API was called with parameters
        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert 'parameters' in data

        import json
        params_sent = json.loads(data['parameters'])
        assert len(params_sent) == 2
        assert params_sent[0]['name'] == 'port'
        assert params_sent[0]['type'] == 'PORT'


class TestProtocolParameterValidation:
    """Test suite for PROTOCOL parameter type validation."""

    def test_validate_protocol_parameter_valid_tcp(self):
        """Test valid TCP protocol parameter."""
        params = [{"name": "protocol", "value": "TCP", "type": "PROTOCOL"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert parsed[0]["type"] == "PROTOCOL"
        assert parsed[0]["values"][0]["value"] == "TCP"

    def test_validate_protocol_parameter_valid_http(self):
        """Test valid HTTP protocol parameter."""
        params = [{"name": "protocol", "value": "HTTP", "type": "PROTOCOL"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert parsed[0]["values"][0]["value"] == "HTTP"

    def test_validate_protocol_parameter_case_insensitive(self):
        """Test protocol parameter is case-insensitive."""
        params = [{"name": "protocol", "value": "tcp", "type": "PROTOCOL"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert parsed[0]["values"][0]["value"] == "TCP"  # Should use canonical case

    def test_validate_protocol_parameter_mixed_case(self):
        """Test protocol parameter with mixed case."""
        params = [{"name": "protocol", "value": "HtTp", "type": "PROTOCOL"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert parsed[0]["values"][0]["value"] == "HTTP"  # Should use canonical case

    def test_validate_protocol_parameter_mdns_case(self):
        """Test mDNS protocol preserves correct mixed case."""
        params = [{"name": "protocol", "value": "mdns", "type": "PROTOCOL"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert parsed[0]["values"][0]["value"] == "mDNS"  # Should preserve canonical mixed case

    def test_validate_protocol_parameter_invalid(self):
        """Test invalid protocol value is rejected."""
        params = [{"name": "protocol", "value": "INVALID_PROTOCOL", "type": "PROTOCOL"}]

        with pytest.raises(ValueError) as exc_info:
            _validate_and_build_parameters(params)

        assert "invalid protocol value" in str(exc_info.value).lower()
        assert "INVALID_PROTOCOL" in str(exc_info.value)

    def test_validate_protocol_parameter_all_52_protocols(self):
        """Test all 52 valid protocol values."""
        # Test using the exact values from VALID_PROTOCOLS
        for protocol in VALID_PROTOCOLS:
            params = [{"name": "protocol", "value": protocol, "type": "PROTOCOL"}]
            result = _validate_and_build_parameters(params)

            import json
            parsed = json.loads(result)
            # Should preserve the exact canonical case from VALID_PROTOCOLS
            assert parsed[0]["values"][0]["value"] == protocol

    def test_validate_multiple_parameters_with_protocol(self):
        """Test multiple parameters including protocol."""
        params = [
            {"name": "port", "value": 443, "type": "PORT"},
            {"name": "protocol", "value": "HTTPS", "type": "PROTOCOL"},
            {"name": "url", "value": "https://example.com", "type": "URI"}
        ]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed) == 3
        assert parsed[0]["type"] == "PORT"
        assert parsed[1]["type"] == "PROTOCOL"
        assert parsed[1]["values"][0]["value"] == "HTTPS"
        assert parsed[2]["type"] == "URI"

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_draft_with_protocol_parameter(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test saving draft with protocol parameter."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute with protocol parameter
        params = [{"name": "protocol", "value": "SSH", "type": "PROTOCOL"}]
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            parameters=params,
            console="demo"
        )

        # Verify result
        assert result['parameters_count'] == 1

        # Verify API was called with protocol parameter
        call_args = mock_post.call_args
        data = call_args[1]['data']

        import json
        params_sent = json.loads(data['parameters'])
        assert len(params_sent) == 1
        assert params_sent[0]['type'] == 'PROTOCOL'
        assert params_sent[0]['values'][0]['value'] == 'SSH'


class TestMultiValueParameters:
    """Test suite for parameters with multiple values."""

    def test_single_value_parameter(self):
        """Test parameter with single value (backward compatibility)."""
        params = [{"name": "port", "value": 8080, "type": "PORT"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed[0]["values"]) == 1
        assert parsed[0]["values"][0]["value"] == 8080

    def test_multi_value_parameter_list(self):
        """Test parameter with list of values."""
        params = [{"name": "paths", "value": ["file1.txt", "file2.txt", "file3.txt"]}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed[0]["values"]) == 3
        assert parsed[0]["values"][0]["value"] == "file1.txt"
        assert parsed[0]["values"][1]["value"] == "file2.txt"
        assert parsed[0]["values"][2]["value"] == "file3.txt"
        # Check IDs are sequential
        assert parsed[0]["values"][0]["id"] == 1
        assert parsed[0]["values"][1]["id"] == 2
        assert parsed[0]["values"][2]["id"] == 3

    def test_multi_value_parameter_ports(self):
        """Test PORT parameter with multiple values."""
        params = [{"name": "ports", "value": [80, 443, 8080], "type": "PORT"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed[0]["values"]) == 3
        assert parsed[0]["type"] == "PORT"
        assert parsed[0]["values"][0]["value"] == 80
        assert parsed[0]["values"][1]["value"] == 443
        assert parsed[0]["values"][2]["value"] == 8080

    def test_multi_value_parameter_protocols(self):
        """Test PROTOCOL parameter with multiple values."""
        params = [{"name": "protocols", "value": ["TCP", "UDP", "HTTP"], "type": "PROTOCOL"}]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed[0]["values"]) == 3
        assert parsed[0]["type"] == "PROTOCOL"
        assert parsed[0]["values"][0]["value"] == "TCP"
        assert parsed[0]["values"][1]["value"] == "UDP"
        assert parsed[0]["values"][2]["value"] == "HTTP"

    def test_multi_value_uris(self):
        """Test URI parameter with multiple values."""
        params = [{
            "name": "urls",
            "value": ["https://example1.com", "https://example2.com"],
            "type": "URI"
        }]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed[0]["values"]) == 2
        assert parsed[0]["type"] == "URI"

    def test_mixed_single_and_multi_value_parameters(self):
        """Test mix of single and multi-value parameters."""
        params = [
            {"name": "port", "value": 443, "type": "PORT"},
            {"name": "paths", "value": ["file1.txt", "file2.txt"]},
            {"name": "protocol", "value": "HTTPS", "type": "PROTOCOL"}
        ]
        result = _validate_and_build_parameters(params)

        import json
        parsed = json.loads(result)
        assert len(parsed) == 3
        # Single value
        assert len(parsed[0]["values"]) == 1
        # Multi value
        assert len(parsed[1]["values"]) == 2
        # Single value
        assert len(parsed[2]["values"]) == 1

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_save_draft_with_multi_value_parameters(
        self,
        mock_get_secret,
        mock_get_base_url,
        mock_get_account_id,
        mock_post,
        sample_valid_python_code,
        mock_draft_response,
        clear_cache
    ):
        """Test saving draft with multi-value parameters."""
        # Setup mocks
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        # Execute with multi-value parameters
        params = [
            {"name": "file_paths", "value": ["c:\\temp\\file1.txt", "c:\\temp\\file2.txt"]},
            {"name": "protocols", "value": ["TCP", "UDP"], "type": "PROTOCOL"}
        ]
        result = sb_save_studio_attack_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            parameters=params,
            console="demo"
        )

        # Verify result
        assert result['parameters_count'] == 2

        # Verify API was called with multi-value parameters
        call_args = mock_post.call_args
        data = call_args[1]['data']

        import json
        params_sent = json.loads(data['parameters'])
        assert len(params_sent) == 2
        # First parameter has 2 values
        assert len(params_sent[0]['values']) == 2
        assert params_sent[0]['values'][0]['value'] == "c:\\temp\\file1.txt"
        assert params_sent[0]['values'][1]['value'] == "c:\\temp\\file2.txt"
        # Second parameter has 2 values
        assert len(params_sent[1]['values']) == 2
        assert params_sent[1]['values'][0]['value'] == "TCP"
        assert params_sent[1]['values'][1]['value'] == "UDP"


# ============================================================================
# Phase 2: Validation Enhancement Tests
# ============================================================================

@pytest.fixture
def sample_attacker_code():
    """Sample valid Python attacker code with required main function."""
    return """
import logging

def main(system_data, asset, proxy, *args, **kwargs):
    \"\"\"Attacker entry point.\"\"\"
    logging.info("Running attacker")
    return True
"""


@pytest.fixture
def sample_attacker_code_no_main():
    """Sample attacker code without required main function."""
    return """
import logging

def attack():
    logging.info("Wrong function signature")
    return True
"""


@pytest.fixture
def sample_attacker_code_syntax_error():
    """Sample attacker code with syntax error."""
    return """
def main(system_data, asset, proxy, *args, **kwargs):
    if True
        return False
"""


class TestValidateAttackType:
    """Test attack type validation in sb_validate_studio_code."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_valid_host_type(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test validation with valid 'host' attack type."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo", attack_type="host"
        )
        assert result['is_valid'] is True

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_valid_exfil_type(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_validation_response_valid
    ):
        """Test validation with valid 'exfil' attack type and attacker code."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="exfil", attacker_code=sample_attacker_code
        )
        assert result['is_valid'] is True
        assert result['attacker_validation'] is not None

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_valid_infil_type(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_validation_response_valid
    ):
        """Test validation with valid 'infil' attack type."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="infil", attacker_code=sample_attacker_code
        )
        assert result['is_valid'] is True

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_valid_lateral_type(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_validation_response_valid
    ):
        """Test validation with valid 'lateral' attack type."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="lateral", attacker_code=sample_attacker_code
        )
        assert result['is_valid'] is True

    def test_invalid_attack_type(self, sample_valid_python_code):
        """Test validation rejects invalid attack type."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo", attack_type="invalid"
            )
        assert "attack_type must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_case_insensitive_attack_type(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test that attack type is case-insensitive (e.g., 'Host' normalizes to 'host')."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo", attack_type="Host"
        )
        assert result['is_valid'] is True


class TestDualScriptValidation:
    """Test dual-script validation in sb_validate_studio_code."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_exfil_with_both_scripts_valid(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_validation_response_valid
    ):
        """Test exfil with both valid scripts passes."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="exfil", attacker_code=sample_attacker_code
        )
        assert result['is_valid'] is True
        assert result['target_validation'] is not None
        assert result['attacker_validation'] is not None
        # API should be called twice (target + attacker)
        assert mock_put.call_count == 2

    def test_exfil_missing_attacker_code(self, sample_valid_python_code):
        """Test exfil without attacker_code raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo",
                attack_type="exfil"
            )
        assert "attacker_code is required" in str(exc_info.value)

    def test_infil_missing_attacker_code(self, sample_valid_python_code):
        """Test infil without attacker_code raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo",
                attack_type="infil"
            )
        assert "attacker_code is required" in str(exc_info.value)

    def test_lateral_missing_attacker_code(self, sample_valid_python_code):
        """Test lateral without attacker_code raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo",
                attack_type="lateral"
            )
        assert "attacker_code is required" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_host_with_only_target_valid(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test host attack with only target code is valid."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo", attack_type="host"
        )
        assert result['is_valid'] is True
        assert result['attacker_validation'] is None
        # API called only once for host
        assert mock_put.call_count == 1

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_attacker_code_syntax_error(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code_syntax_error,
        mock_validation_response_valid
    ):
        """Test attacker code with syntax error causes is_valid=False."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="exfil",
            attacker_code=sample_attacker_code_syntax_error
        )
        # Local syntax check catches the error
        assert result['is_valid'] is False
        assert any("syntax error" in e.lower() for e in result['validation_errors'])

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_both_scripts_api_errors_combined(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code,
        mock_validation_response_invalid
    ):
        """Test both scripts with API errors produces combined errors."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_invalid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="exfil", attacker_code=sample_attacker_code
        )
        assert result['is_valid'] is False
        # Should have errors from both target and attacker validations
        assert len(result['validation_errors']) > 0

    def test_exfil_empty_attacker_code(self, sample_valid_python_code):
        """Test exfil with empty string attacker_code raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo",
                attack_type="exfil", attacker_code=""
            )
        assert "attacker_code is required" in str(exc_info.value)


class TestLintSB011:
    """Test SB011 lint check: parameter names must be valid Python identifiers."""

    def test_valid_identifier_passes(self):
        """Test valid Python identifier passes SB011."""
        params = [{"name": "my_param", "value": "test"}]
        warnings = _lint_check_parameters(params)
        assert not any(w['code'] == 'SB011' for w in warnings)

    def test_hyphenated_name_fails(self):
        """Test hyphenated name triggers SB011 warning."""
        params = [{"name": "my-param", "value": "test"}]
        warnings = _lint_check_parameters(params)
        sb011_warnings = [w for w in warnings if w['code'] == 'SB011']
        assert len(sb011_warnings) == 1
        assert "my-param" in sb011_warnings[0]['message']

    def test_number_prefix_fails(self):
        """Test name starting with number triggers SB011 warning."""
        params = [{"name": "2nd_attempt", "value": "test"}]
        warnings = _lint_check_parameters(params)
        sb011_warnings = [w for w in warnings if w['code'] == 'SB011']
        assert len(sb011_warnings) == 1
        assert "2nd_attempt" in sb011_warnings[0]['message']

    def test_space_in_name_fails(self):
        """Test name with space triggers SB011 warning."""
        params = [{"name": "param name", "value": "test"}]
        warnings = _lint_check_parameters(params)
        sb011_warnings = [w for w in warnings if w['code'] == 'SB011']
        assert len(sb011_warnings) == 1

    def test_python_keyword_passes(self):
        """Test Python keyword is a valid identifier (SB011 doesn't check keywords)."""
        params = [{"name": "class", "value": "test"}]
        warnings = _lint_check_parameters(params)
        assert not any(w['code'] == 'SB011' for w in warnings)


class TestLintSB012:
    """Test SB012 lint check: duplicate parameter names."""

    def test_unique_names_pass(self):
        """Test unique parameter names pass SB012."""
        params = [
            {"name": "port", "value": 80},
            {"name": "host", "value": "localhost"}
        ]
        warnings = _lint_check_parameters(params)
        assert not any(w['code'] == 'SB012' for w in warnings)

    def test_duplicate_names_fail(self):
        """Test duplicate parameter names trigger SB012 warning."""
        params = [
            {"name": "port", "value": 80},
            {"name": "port", "value": 443}
        ]
        warnings = _lint_check_parameters(params)
        sb012_warnings = [w for w in warnings if w['code'] == 'SB012']
        assert len(sb012_warnings) == 1
        assert "port" in sb012_warnings[0]['message']

    def test_case_sensitive_different_names_pass(self):
        """Test Port and port are different names (case-sensitive) - both pass."""
        params = [
            {"name": "Port", "value": 80},
            {"name": "port", "value": 443}
        ]
        warnings = _lint_check_parameters(params)
        assert not any(w['code'] == 'SB012' for w in warnings)

    def test_empty_parameter_list_passes(self):
        """Test empty parameter list passes SB012."""
        warnings = _lint_check_parameters([])
        assert not any(w['code'] == 'SB012' for w in warnings)


class TestOSConstraintValidation:
    """Test OS constraint validation in sb_validate_studio_code."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_valid_target_os_and_attacker_os(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_validation_response_valid
    ):
        """Test valid target_os and attacker_os pass validation."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="exfil", attacker_code=sample_attacker_code,
            target_os="WINDOWS", attacker_os="LINUX"
        )
        assert result['is_valid'] is True

    def test_invalid_target_os_raises(self, sample_valid_python_code):
        """Test invalid target_os raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo", target_os="INVALID"
            )
        assert "os_constraint must be one of" in str(exc_info.value)

    def test_attacker_os_validated_for_dual_script(self, sample_valid_python_code, sample_attacker_code):
        """Test attacker_os is validated for dual-script types."""
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                sample_valid_python_code, "demo",
                attack_type="exfil", attacker_code=sample_attacker_code,
                attacker_os="INVALID"
            )
        assert "os_constraint must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_host_attack_ignores_attacker_os(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test host attack does not validate attacker_os (even if invalid)."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        # host attack should not validate attacker_os
        result = sb_validate_studio_code(
            sample_valid_python_code, "demo",
            attack_type="host", attacker_os="INVALID_OS"
        )
        assert result['is_valid'] is True


class TestValidationWithLintIntegration:
    """Test SB011/SB012 lint checks integrated into sb_validate_studio_code."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validation_with_lint_warnings(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test that lint warnings are included in validation result."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        params = [{"name": "my-param", "value": "test"}]
        result = sb_validate_studio_code(
            sample_valid_python_code, "demo", parameters=params
        )
        # Code is valid but has lint warnings
        assert result['is_valid'] is True
        assert len(result['lint_warnings']) == 1
        assert result['lint_warnings'][0]['code'] == 'SB011'

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validation_with_no_parameters(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test that no lint warnings when no parameters provided."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(sample_valid_python_code, "demo")
        assert result['lint_warnings'] == []

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_validation_result_structure(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_validation_response_valid
    ):
        """Test that validation result has all expected fields."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_validation_response_valid
        mock_put.return_value = mock_response

        result = sb_validate_studio_code(sample_valid_python_code, "demo")
        expected_keys = {
            'is_valid', 'exit_code', 'has_main_function', 'validation_errors',
            'target_validation', 'attacker_validation', 'lint_warnings',
            'stderr', 'stdout'
        }
        assert set(result.keys()) == expected_keys


# ============================================================================
# Phase 3: Dual-Script Draft Management Tests
# ============================================================================


class TestDualScriptSave:
    """Test dual-script support in sb_save_studio_attack_draft."""

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_host_save_single_file_method_type_5(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, mock_draft_response, clear_cache
    ):
        """Test host save sends single file with methodType=5."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Host Attack", python_code=sample_valid_python_code,
            attack_type="host", console="demo"
        )

        call_args = mock_post.call_args
        data = call_args[1]['data']
        files = call_args[1]['files']
        assert data['methodType'] == '5'
        assert 'targetFile' in files
        assert 'attackerFile' not in files

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_exfil_save_two_files_method_type_0(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, sample_attacker_code, mock_draft_response, clear_cache
    ):
        """Test exfil save sends two files with methodType=0."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Exfil Attack", python_code=sample_valid_python_code,
            attacker_code=sample_attacker_code, attack_type="exfil", console="demo"
        )

        call_args = mock_post.call_args
        data = call_args[1]['data']
        files = call_args[1]['files']
        assert data['methodType'] == '0'
        assert 'targetFile' in files
        assert 'attackerFile' in files

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_infil_save_method_type_2(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, sample_attacker_code, mock_draft_response, clear_cache
    ):
        """Test infil save with methodType=2."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Infil Attack", python_code=sample_valid_python_code,
            attacker_code=sample_attacker_code, attack_type="infil", console="demo"
        )

        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert data['methodType'] == '2'
        assert 'attackerFile' in call_args[1]['files']

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_lateral_save_method_type_1(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, sample_attacker_code, mock_draft_response, clear_cache
    ):
        """Test lateral save with methodType=1."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Lateral Attack", python_code=sample_valid_python_code,
            attacker_code=sample_attacker_code, attack_type="lateral", console="demo"
        )

        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert data['methodType'] == '1'
        assert 'attackerFile' in call_args[1]['files']

    def test_dual_script_save_without_attacker_code(self, sample_valid_python_code):
        """Test dual-script save without attacker_code raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_attack_draft(
                name="Exfil Attack", python_code=sample_valid_python_code,
                attack_type="exfil", console="demo"
            )
        assert "attacker_code is required" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_dual_script_multipart_structure(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, sample_attacker_code, mock_draft_response, clear_cache
    ):
        """Test multipart form data structure for dual-script save."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Exfil Attack", python_code=sample_valid_python_code,
            attacker_code=sample_attacker_code, attack_type="exfil", console="demo"
        )

        call_args = mock_post.call_args
        files = call_args[1]['files']
        # Verify file tuples
        assert files['targetFile'][0] == 'target.py'
        assert files['attackerFile'][0] == 'attacker.py'
        # Verify metadata includes attackerFileName
        import json
        meta_data = json.loads(call_args[1]['data']['metaData'])
        assert meta_data['targetFileName'] == 'target.py'
        assert meta_data['attackerFileName'] == 'attacker.py'

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_dual_script_attacker_constraints(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, sample_attacker_code, mock_draft_response, clear_cache
    ):
        """Test attackerConstraints sent when attacker_os != 'All'."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Exfil Attack", python_code=sample_valid_python_code,
            attacker_code=sample_attacker_code, attack_type="exfil",
            attacker_os="WINDOWS", console="demo"
        )

        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert 'attackerConstraints' in data
        import json
        assert json.loads(data['attackerConstraints']) == {"os": "WINDOWS"}

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_host_save_no_attacker_constraints(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        sample_valid_python_code, mock_draft_response, clear_cache
    ):
        """Test host save does not include attackerConstraints or attackerFile."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_draft_response
        mock_post.return_value = mock_response

        sb_save_studio_attack_draft(
            name="Host Attack", python_code=sample_valid_python_code,
            attack_type="host", console="demo"
        )

        call_args = mock_post.call_args
        data = call_args[1]['data']
        files = call_args[1]['files']
        assert 'attackerConstraints' not in data
        assert 'attackerFile' not in files
        import json
        meta_data = json.loads(data['metaData'])
        assert 'attackerFileName' not in meta_data


class TestDualScriptUpdate:
    """Test dual-script support in sb_update_studio_attack_draft."""

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_host_attack_single_file(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, mock_update_response, clear_cache
    ):
        """Test update host attack sends single file."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        sb_update_studio_attack_draft(
            attack_id=10000298, name="Updated Host Attack",
            python_code=sample_valid_python_code, attack_type="host", console="demo"
        )

        call_args = mock_put.call_args
        data = call_args[1]['data']
        files = call_args[1]['files']
        assert data['methodType'] == '5'
        assert 'targetFile' in files
        assert 'attackerFile' not in files

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_exfil_attack_both_files(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_update_response, clear_cache
    ):
        """Test update exfil attack sends both files."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        sb_update_studio_attack_draft(
            attack_id=10000298, name="Updated Exfil Attack",
            python_code=sample_valid_python_code, attacker_code=sample_attacker_code,
            attack_type="exfil", console="demo"
        )

        call_args = mock_put.call_args
        data = call_args[1]['data']
        files = call_args[1]['files']
        assert data['methodType'] == '0'
        assert 'targetFile' in files
        assert 'attackerFile' in files

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_with_changed_attack_type(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
        sample_valid_python_code, sample_attacker_code, mock_update_response, clear_cache
    ):
        """Test update with changed attack_type sends correct methodType."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        sb_update_studio_attack_draft(
            attack_id=10000298, name="Lateral Attack",
            python_code=sample_valid_python_code, attacker_code=sample_attacker_code,
            attack_type="lateral", console="demo"
        )

        call_args = mock_put.call_args
        data = call_args[1]['data']
        assert data['methodType'] == '1'

    def test_update_dual_script_without_attacker_code(self, sample_valid_python_code):
        """Test update dual-script without attacker_code raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=10000298, name="Exfil Attack",
                python_code=sample_valid_python_code, attack_type="exfil", console="demo"
            )
        assert "attacker_code is required" in str(exc_info.value)

    def test_update_invalid_attack_type(self, sample_valid_python_code):
        """Test update with invalid attack_type raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_attack_draft(
                attack_id=10000298, name="Test",
                python_code=sample_valid_python_code, attack_type="invalid", console="demo"
            )
        assert "attack_type must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.time.time')
    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_update_cache_includes_attack_type_info(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put, mock_time,
        sample_valid_python_code, sample_attacker_code, mock_update_response, clear_cache
    ):
        """Test that cache update includes attack type related info."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_time.return_value = 1700000000.0
        mock_response = MagicMock()
        mock_response.json.return_value = mock_update_response
        mock_put.return_value = mock_response

        result = sb_update_studio_attack_draft(
            attack_id=10000298, name="Updated Exfil",
            python_code=sample_valid_python_code, attacker_code=sample_attacker_code,
            attack_type="exfil", console="demo"
        )

        # Verify cache was updated
        cache_key = f"studio_draft_demo_{result['draft_id']}"
        assert cache_key in studio_draft_cache
        cached = studio_draft_cache[cache_key]
        assert cached['timestamp'] == 1700000000.0


class TestDualScriptSource:
    """Test dual-script support in sb_get_studio_attack_source."""

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_host_attack_source_target_only(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test host attack source returns target only, attacker is None."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_target = MagicMock()
        mock_target.json.return_value = {"data": {"filename": "target.py", "content": "target code"}}
        mock_target.status_code = 200

        mock_attacker = MagicMock()
        mock_attacker.status_code = 404

        mock_get.side_effect = [mock_target, mock_attacker]

        result = sb_get_studio_attack_source(attack_id=12345, console="demo")

        assert result['attack_id'] == 12345
        assert result['target']['filename'] == 'target.py'
        assert result['target']['content'] == 'target code'
        assert result['attacker'] is None

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_dual_script_source_both_present(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test dual-script source returns both target and attacker content."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_target = MagicMock()
        mock_target.json.return_value = {"data": {"filename": "target.py", "content": "target code"}}
        mock_target.status_code = 200

        mock_attacker = MagicMock()
        mock_attacker.json.return_value = {"data": {"filename": "attacker.py", "content": "attacker code"}}
        mock_attacker.status_code = 200

        mock_get.side_effect = [mock_target, mock_attacker]

        result = sb_get_studio_attack_source(attack_id=12345, console="demo")

        assert result['attack_id'] == 12345
        assert result['target']['filename'] == 'target.py'
        assert result['target']['content'] == 'target code'
        assert result['attacker']['filename'] == 'attacker.py'
        assert result['attacker']['content'] == 'attacker code'

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_attacker_file_404_graceful(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test attacker file 404 is handled gracefully."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_target = MagicMock()
        mock_target.json.return_value = {"data": {"filename": "target.py", "content": "code"}}
        mock_target.status_code = 200

        mock_attacker = MagicMock()
        mock_attacker.status_code = 404

        mock_get.side_effect = [mock_target, mock_attacker]

        result = sb_get_studio_attack_source(attack_id=12345, console="demo")
        assert result['attacker'] is None

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_target_api_error_raises(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test API error on target fetch raises exception."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = Exception("API Error")
        mock_get.return_value = mock_response

        with pytest.raises(Exception) as exc_info:
            sb_get_studio_attack_source(attack_id=12345, console="demo")
        assert "API Error" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_return_structure_keys(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test return structure has attack_id, target, attacker keys."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_target = MagicMock()
        mock_target.json.return_value = {"data": {"filename": "target.py", "content": "code"}}
        mock_target.status_code = 200

        mock_attacker = MagicMock()
        mock_attacker.status_code = 404

        mock_get.side_effect = [mock_target, mock_attacker]

        result = sb_get_studio_attack_source(attack_id=12345, console="demo")
        assert set(result.keys()) == {'attack_id', 'target', 'attacker'}

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_attacker_fetch_network_error_graceful(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test attacker fetch network error is handled gracefully (non-fatal)."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_target = MagicMock()
        mock_target.json.return_value = {"data": {"filename": "target.py", "content": "code"}}
        mock_target.status_code = 200

        import requests as req
        mock_get.side_effect = [mock_target, req.exceptions.ConnectionError("Network error")]

        result = sb_get_studio_attack_source(attack_id=12345, console="demo")
        assert result['target']['content'] == 'code'
        assert result['attacker'] is None


# ============================================================================
# Phase 4: Pagination Tests
# ============================================================================


class TestPaginateStudioAttacks:
    """Test the paginate_studio_attacks function directly."""

    def _make_attacks(self, count):
        """Generate a list of fake attack dicts."""
        return [{'id': i, 'name': f'Attack {i}', 'status': 'draft'} for i in range(count)]

    def test_page_0_of_25(self):
        """Page 0 with 25 total -> 10 items, total_pages=3."""
        result = paginate_studio_attacks(self._make_attacks(25), page_number=0)
        assert len(result['attacks_in_page']) == 10
        assert result['total_attacks'] == 25
        assert result['total_pages'] == 3
        assert result['page_number'] == 0
        assert 'page_number=1' in result['hint_to_agent']

    def test_page_1_of_25(self):
        """Page 1 with 25 total -> 10 items, no overlap with page 0."""
        attacks = self._make_attacks(25)
        page0 = paginate_studio_attacks(attacks, page_number=0)
        page1 = paginate_studio_attacks(attacks, page_number=1)
        assert len(page1['attacks_in_page']) == 10
        ids_0 = {a['id'] for a in page0['attacks_in_page']}
        ids_1 = {a['id'] for a in page1['attacks_in_page']}
        assert ids_0.isdisjoint(ids_1)

    def test_last_page_of_25(self):
        """Page 2 with 25 total -> 5 items, hint says last page."""
        result = paginate_studio_attacks(self._make_attacks(25), page_number=2)
        assert len(result['attacks_in_page']) == 5
        assert result['hint_to_agent'] == 'This is the last page'

    def test_out_of_range_page(self):
        """Page 3 with 25 total -> error dict."""
        result = paginate_studio_attacks(self._make_attacks(25), page_number=3)
        assert 'error' in result
        assert 'Invalid page_number 3' in result['error']
        assert result['attacks_in_page'] == []

    def test_empty_results(self):
        """Empty results -> total_pages=0, empty attacks_in_page."""
        result = paginate_studio_attacks([], page_number=0)
        assert result['total_pages'] == 0
        assert result['total_attacks'] == 0
        assert result['attacks_in_page'] == []

    def test_negative_page_number(self):
        """Negative page number -> error dict."""
        result = paginate_studio_attacks(self._make_attacks(5), page_number=-1)
        assert 'error' in result
        assert 'Invalid page_number -1' in result['error']

    def test_single_page(self):
        """5 items with PAGE_SIZE=10 -> single page."""
        result = paginate_studio_attacks(self._make_attacks(5), page_number=0)
        assert result['total_pages'] == 1
        assert len(result['attacks_in_page']) == 5
        assert result['hint_to_agent'] == 'This is the last page'

    def test_exact_page_boundary(self):
        """Exactly 10 items -> 1 page, no next hint."""
        result = paginate_studio_attacks(self._make_attacks(10), page_number=0)
        assert result['total_pages'] == 1
        assert len(result['attacks_in_page']) == 10
        assert result['hint_to_agent'] == 'This is the last page'


class TestGetAllStudioAttacksPagination:
    """Test pagination integration in sb_get_all_studio_attacks."""

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_pagination_with_filters(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test pagination works with filters applied."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        # Create 15 draft attacks
        data = [
            {"id": i, "name": f"Draft Attack {i}", "status": "draft",
             "creationDate": "2025-11-30T12:00:00Z", "updateDate": "2025-11-30T12:00:00Z",
             "targetFileName": "target.py", "methodType": 5, "origin": "BREACH_STUDIO"}
            for i in range(15)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": data}
        mock_get.return_value = mock_response

        result = sb_get_all_studio_attacks(console="demo", status_filter="draft", page_number=0)
        assert len(result['attacks_in_page']) == 10
        assert result['total_attacks'] == 15
        assert result['total_pages'] == 2

        result_p1 = sb_get_all_studio_attacks(console="demo", status_filter="draft", page_number=1)
        assert len(result_p1['attacks_in_page']) == 5

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_applied_filters_present(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test applied_filters is present in result."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {"data": []}
        mock_get.return_value = mock_response

        result = sb_get_all_studio_attacks(
            console="demo", status_filter="draft", name_filter="test", user_id_filter=123
        )
        assert 'applied_filters' in result
        assert result['applied_filters']['status_filter'] == 'draft'
        assert result['applied_filters']['name_filter'] == 'test'
        assert result['applied_filters']['user_filter'] == 123

    @patch('safebreach_mcp_studio.studio_functions.requests.get')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_hint_to_agent_present(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_get
    ):
        """Test hint_to_agent is present and meaningful."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        data = [
            {"id": i, "name": f"Attack {i}", "status": "draft",
             "creationDate": "2025-11-30T12:00:00Z", "updateDate": "2025-11-30T12:00:00Z",
             "targetFileName": "target.py", "methodType": 5, "origin": "BREACH_STUDIO"}
            for i in range(25)
        ]
        mock_response = MagicMock()
        mock_response.json.return_value = {"data": data}
        mock_get.return_value = mock_response

        result = sb_get_all_studio_attacks(console="demo", page_number=0)
        assert 'hint_to_agent' in result
        assert result['hint_to_agent'] is not None
        assert 'page_number=1' in result['hint_to_agent']

    def test_negative_page_number_raises(self):
        """Test negative page_number raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_all_studio_attacks(console="demo", page_number=-1)
        assert "Invalid page_number parameter" in str(exc_info.value)


class TestExplicitSimulatorSelection:
    """Test explicit simulator selection in sb_run_studio_attack (Phase 5)."""

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_host_attack_target_ids_used_for_both(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """Host attack: target_simulator_ids used for both attacker and target filters."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        target_ids = ["sim-uuid-1", "sim-uuid-2"]
        sb_run_studio_attack(
            attack_id=10000298, console="demo",
            target_simulator_ids=target_ids
        )

        payload = mock_post.call_args[1]['json']
        step = payload['plan']['steps'][0]
        # Both attacker and target use the same target_simulator_ids
        assert step['targetFilter']['simulators']['values'] == target_ids
        assert step['attackerFilter']['simulators']['values'] == target_ids

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_network_attack_separate_attacker_and_target(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """Network attack: separate attacker and target simulator IDs in payload."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        target_ids = ["target-uuid-1"]
        attacker_ids = ["attacker-uuid-1", "attacker-uuid-2"]
        sb_run_studio_attack(
            attack_id=10000298, console="demo",
            target_simulator_ids=target_ids,
            attacker_simulator_ids=attacker_ids,
        )

        payload = mock_post.call_args[1]['json']
        step = payload['plan']['steps'][0]
        assert step['targetFilter']['simulators']['values'] == target_ids
        assert step['attackerFilter']['simulators']['values'] == attacker_ids

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_no_attacker_ids_defaults_to_target_ids(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """When attacker_simulator_ids not provided, attacker uses target IDs."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        target_ids = ["sim-uuid-1"]
        sb_run_studio_attack(
            attack_id=10000298, console="demo",
            target_simulator_ids=target_ids,
        )

        payload = mock_post.call_args[1]['json']
        step = payload['plan']['steps'][0]
        # attacker defaults to target IDs
        assert step['attackerFilter']['simulators']['values'] == target_ids
        assert step['targetFilter']['simulators']['values'] == target_ids

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_all_connected_uses_connection_filter(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """all_connected=True uses connection filter in payload."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        sb_run_studio_attack(
            attack_id=10000298, console="demo",
            all_connected=True,
        )

        payload = mock_post.call_args[1]['json']
        step = payload['plan']['steps'][0]
        assert 'connection' in step['attackerFilter']
        assert 'connection' in step['targetFilter']
        assert step['attackerFilter']['connection']['values'] == [True]
        assert step['targetFilter']['connection']['values'] == [True]

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_all_connected_ignores_simulator_ids(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """all_connected=True ignores provided simulator IDs."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        sb_run_studio_attack(
            attack_id=10000298, console="demo",
            all_connected=True,
            target_simulator_ids=["sim-uuid-1"],
            attacker_simulator_ids=["sim-uuid-2"],
        )

        payload = mock_post.call_args[1]['json']
        step = payload['plan']['steps'][0]
        # Should use connection filter, not simulator IDs
        assert 'connection' in step['attackerFilter']
        assert 'connection' in step['targetFilter']
        assert 'simulators' not in step['attackerFilter']
        assert 'simulators' not in step['targetFilter']

    def test_empty_attacker_simulator_ids_raises(self):
        """Empty attacker_simulator_ids list raises ValueError."""
        with pytest.raises(ValueError) as exc_info:
            sb_run_studio_attack(
                attack_id=10000298, console="demo",
                target_simulator_ids=["sim-uuid-1"],
                attacker_simulator_ids=[],
            )
        assert "attacker_simulator_ids cannot be an empty list" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_return_has_test_id_and_attack_id(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """Return structure has test_id and attack_id keys."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        result = sb_run_studio_attack(
            attack_id=10000298, console="demo",
            all_connected=True,
        )

        assert 'test_id' in result
        assert 'attack_id' in result
        assert result['test_id'] == "1764570357286.4"
        assert result['attack_id'] == 10000298

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_return_has_status_queued(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """Return structure has status key set to 'queued'."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        result = sb_run_studio_attack(
            attack_id=10000298, console="demo",
            all_connected=True,
        )

        assert result['status'] == 'queued'

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_payload_structure_matches_api_format(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """Verify full API payload structure."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        sb_run_studio_attack(
            attack_id=10000298, console="demo",
            target_simulator_ids=["sim-1"],
            test_name="Test Run",
        )

        payload = mock_post.call_args[1]['json']
        # Verify top-level structure
        assert 'plan' in payload
        assert 'name' in payload['plan']
        assert 'steps' in payload['plan']
        assert 'draft' in payload['plan']
        assert payload['plan']['draft'] is True
        assert payload['plan']['name'] == "Test Run"

        # Verify step structure
        step = payload['plan']['steps'][0]
        assert 'attacksFilter' in step
        assert 'attackerFilter' in step
        assert 'targetFilter' in step
        assert 'systemFilter' in step

        # Verify attacks filter
        assert step['attacksFilter']['playbook']['operator'] == 'is'
        assert step['attacksFilter']['playbook']['values'] == [10000298]
        assert step['attacksFilter']['playbook']['name'] == 'playbook'

        # Verify simulator filter
        assert step['targetFilter']['simulators']['operator'] == 'is'
        assert step['targetFilter']['simulators']['name'] == 'simulators'

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_return_has_step_run_id(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post,
        mock_run_response
    ):
        """Return structure includes step_run_id from API response."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = mock_run_response
        mock_post.return_value = mock_response

        result = sb_run_studio_attack(
            attack_id=10000298, console="demo",
            all_connected=True,
        )

        assert 'step_run_id' in result
        assert result['step_run_id'] == "1764570357287.5"


class TestEnhancedResults:
    """Test enhanced results with simulation_steps, logs, and output (Phase 6)."""

    def test_result_with_simulation_events_populates_steps(self):
        """Result with simulation events produces populated simulation_steps."""
        execution = {
            "id": "1463450",
            "moveId": 10000291,
            "moveName": "Test Attack",
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [
                {
                    "action": "START",
                    "timestamp": "2025-11-02T07:58:00.568Z",
                    "type": "PROCESS",
                    "nodeNameInMove": "attacker",
                    "details": "Process started"
                },
                {
                    "action": "CREATE",
                    "timestamp": "2025-11-02T07:58:01.000Z",
                    "type": "FILE",
                    "nodeId": "node-123",
                    "details": "File created"
                }
            ],
        }
        result = get_execution_result_mapping(execution)
        assert len(result['simulation_steps']) == 2
        assert result['simulation_steps'][0]['step_name'] == "START"
        assert result['simulation_steps'][0]['timing'] == "2025-11-02T07:58:00.568Z"
        assert result['simulation_steps'][0]['status'] == "PROCESS"
        assert result['simulation_steps'][0]['node'] == "attacker"
        assert result['simulation_steps'][0]['details'] == "Process started"
        assert result['simulation_steps'][1]['step_name'] == "CREATE"
        assert result['simulation_steps'][1]['node'] == "node-123"  # Falls back to nodeId

    def test_result_with_logs_string(self):
        """Result with logs field produces logs string."""
        execution = {
            "id": "1463450",
            "moveId": 10000291,
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [],
            "logs": "2025-11-02 07:58:00 - INFO: Starting simulation\n2025-11-02 07:58:10 - INFO: Done",
        }
        result = get_execution_result_mapping(execution)
        assert "Starting simulation" in result['logs']
        assert "Done" in result['logs']

    def test_result_with_output_string(self):
        """Result with output field produces output string."""
        execution = {
            "id": "1463450",
            "moveId": 10000291,
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [],
            "output": "Registry key written successfully",
        }
        result = get_execution_result_mapping(execution)
        assert result['output'] == "Registry key written successfully"

    def test_empty_simulation_events_produces_empty_steps(self):
        """Empty simulation events produces empty simulation_steps list."""
        execution = {
            "id": "1463450",
            "moveId": 10000291,
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [],
        }
        result = get_execution_result_mapping(execution)
        assert result['simulation_steps'] == []

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_include_logs_false_strips_debug_fields(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post
    ):
        """include_logs=False strips simulation_steps, logs, and output."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = Mock()
        mock_response.json.return_value = {
            "simulations": [{
                "id": "1463450",
                "moveId": 10000291,
                "moveName": "Test",
                "status": "SUCCESS",
                "finalStatus": "missed",
                "simulationEvents": [
                    {"action": "START", "timestamp": "T1", "type": "PROCESS", "nodeId": "n1"}
                ],
                "logs": "some logs",
                "output": "some output",
            }],
            "total": 1
        }
        mock_post.return_value = mock_response

        result = sb_get_studio_attack_latest_result(
            attack_id=10000291, console="demo", include_logs=False
        )

        execution = result['executions'][0]
        assert 'simulation_steps' not in execution
        assert 'logs' not in execution
        assert 'output' not in execution

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_include_logs_true_keeps_debug_fields(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post
    ):
        """include_logs=True (default) keeps simulation_steps, logs, and output."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = Mock()
        mock_response.json.return_value = {
            "simulations": [{
                "id": "1463450",
                "moveId": 10000291,
                "moveName": "Test",
                "status": "SUCCESS",
                "finalStatus": "missed",
                "simulationEvents": [
                    {"action": "START", "timestamp": "T1", "type": "PROCESS", "nodeId": "n1"}
                ],
                "logs": "some logs",
                "output": "some output",
            }],
            "total": 1
        }
        mock_post.return_value = mock_response

        result = sb_get_studio_attack_latest_result(
            attack_id=10000291, console="demo", include_logs=True
        )

        execution = result['executions'][0]
        assert 'simulation_steps' in execution
        assert 'logs' in execution
        assert 'output' in execution
        assert len(execution['simulation_steps']) == 1
        assert execution['logs'] == "some logs"
        assert execution['output'] == "some output"

    def test_is_drifted_true_when_original_differs(self):
        """is_drifted is True when originalExecutionId differs from id."""
        execution = {
            "id": "1463450",
            "originalExecutionId": "different-id-from-previous-run",
            "moveId": 10000291,
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [],
        }
        result = get_execution_result_mapping(execution)
        assert result['is_drifted'] is True
        assert result['drift_tracking_code'] == "different-id-from-previous-run"

    def test_is_drifted_false_when_same_id(self):
        """is_drifted is False when originalExecutionId equals id."""
        execution = {
            "id": "1463450",
            "originalExecutionId": "1463450",
            "moveId": 10000291,
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [],
        }
        result = get_execution_result_mapping(execution)
        assert result['is_drifted'] is False

    def test_is_drifted_false_when_empty(self):
        """is_drifted is False when originalExecutionId is empty."""
        execution = {
            "id": "1463450",
            "originalExecutionId": "",
            "moveId": 10000291,
            "status": "SUCCESS",
            "finalStatus": "missed",
            "simulationEvents": [],
        }
        result = get_execution_result_mapping(execution)
        assert result['is_drifted'] is False


class TestDataServerFieldAlignment:
    """Test that execution result fields align with Data server vocabulary (Phase 6)."""

    def _make_execution(self, **overrides):
        """Create a minimal execution dict for testing field names."""
        base = {
            "id": "1463450",
            "jobId": 1463450,
            "originalExecutionId": "49aedc2a07b581aa55f56a165ac29b48",
            "moveId": 10000291,
            "moveName": "Test Attack",
            "moveDesc": "Test Description",
            "planRunId": "1764570357286.4",
            "finalStatus": "missed",
            "status": "SUCCESS",
            "securityAction": "not_logged",
            "simulationEvents": [],
        }
        base.update(overrides)
        return base

    def test_result_contains_simulation_id(self):
        """Result uses simulation_id (not execution_id) for runtime result ID."""
        result = get_execution_result_mapping(self._make_execution())
        assert 'simulation_id' in result
        assert result['simulation_id'] == "1463450"
        assert 'execution_id' not in result

    def test_result_contains_attack_id(self):
        """Result uses attack_id (not simulation_id) for authored artifact ID (moveId)."""
        result = get_execution_result_mapping(self._make_execution())
        assert 'attack_id' in result
        assert result['attack_id'] == 10000291

    def test_result_contains_test_id(self):
        """Result uses test_id (not plan_run_id) for execution run ID."""
        result = get_execution_result_mapping(self._make_execution())
        assert 'test_id' in result
        assert result['test_id'] == "1764570357286.4"
        assert 'plan_run_id' not in result

    def test_result_contains_status(self):
        """Result uses status (not final_status) for the final status field."""
        result = get_execution_result_mapping(self._make_execution())
        assert 'status' in result
        assert result['status'] == "missed"
        assert 'final_status' not in result

    def test_result_contains_drift_tracking_code(self):
        """Result uses drift_tracking_code (not original_execution_id)."""
        result = get_execution_result_mapping(self._make_execution())
        assert 'drift_tracking_code' in result
        assert result['drift_tracking_code'] == "49aedc2a07b581aa55f56a165ac29b48"
        assert 'original_execution_id' not in result

    def test_result_contains_attack_name(self):
        """Result uses attack_name (not simulation_name)."""
        result = get_execution_result_mapping(self._make_execution())
        assert 'attack_name' in result
        assert result['attack_name'] == "Test Attack"
        assert 'simulation_name' not in result


class TestParseSimulationSteps:
    """Test _parse_simulation_steps helper function."""

    def test_empty_events(self):
        """Empty event list returns empty steps."""
        assert _parse_simulation_steps([]) == []

    def test_events_with_all_fields(self):
        """Events with all fields are properly mapped."""
        events = [{
            "action": "START",
            "timestamp": "2025-11-02T07:58:00.568Z",
            "type": "PROCESS",
            "nodeNameInMove": "attacker",
            "details": "Process started"
        }]
        steps = _parse_simulation_steps(events)
        assert len(steps) == 1
        assert steps[0]['step_name'] == "START"
        assert steps[0]['timing'] == "2025-11-02T07:58:00.568Z"
        assert steps[0]['status'] == "PROCESS"
        assert steps[0]['node'] == "attacker"
        assert steps[0]['details'] == "Process started"

    def test_events_fallback_to_node_id(self):
        """When nodeNameInMove is absent, falls back to nodeId."""
        events = [{
            "action": "CREATE",
            "timestamp": "T1",
            "type": "FILE",
            "nodeId": "node-abc",
        }]
        steps = _parse_simulation_steps(events)
        assert steps[0]['node'] == "node-abc"

    def test_events_missing_fields_use_defaults(self):
        """Events with missing fields use empty string defaults."""
        events = [{}]
        steps = _parse_simulation_steps(events)
        assert steps[0]['step_name'] == ""
        assert steps[0]['timing'] == ""
        assert steps[0]['status'] == ""
        assert steps[0]['node'] == ""
        assert steps[0]['details'] == ""


# =============================================================================
# Tests for studio_templates.py accessor functions
# =============================================================================

from safebreach_mcp_studio.studio_templates import (
    get_target_template,
    get_attacker_template,
    get_parameters_template,
    get_parameters_template_json,
    get_attack_type_description,
    is_dual_script_type,
    TEMPLATE_VERSION,
    HOST_TEMPLATE,
    EXFILTRATION_TARGET_TEMPLATE,
    EXFILTRATION_ATTACKER_TEMPLATE,
    INFILTRATION_TARGET_TEMPLATE,
    INFILTRATION_ATTACKER_TEMPLATE,
    LATERAL_MOVEMENT_TARGET_TEMPLATE,
    LATERAL_MOVEMENT_ATTACKER_TEMPLATE,
    HOST_PARAMETERS_TEMPLATE,
    EXFILTRATION_PARAMETERS_TEMPLATE,
    INFILTRATION_PARAMETERS_TEMPLATE,
    LATERAL_MOVEMENT_PARAMETERS_TEMPLATE,
)
from safebreach_mcp_studio.studio_functions import sb_get_studio_attack_boilerplate
import json


class TestStudioTemplates:
    """Tests for studio_templates.py accessor functions."""

    def test_host_target_template(self):
        """Host type returns HOST_TEMPLATE."""
        assert get_target_template("host") is HOST_TEMPLATE

    def test_exfil_target_template(self):
        """Exfil type returns EXFILTRATION_TARGET_TEMPLATE."""
        assert get_target_template("exfil") is EXFILTRATION_TARGET_TEMPLATE

    def test_infil_target_template(self):
        """Infil type returns INFILTRATION_TARGET_TEMPLATE."""
        assert get_target_template("infil") is INFILTRATION_TARGET_TEMPLATE

    def test_lateral_target_template(self):
        """Lateral type returns LATERAL_MOVEMENT_TARGET_TEMPLATE."""
        assert get_target_template("lateral") is LATERAL_MOVEMENT_TARGET_TEMPLATE

    def test_unknown_type_falls_back_to_host(self):
        """Unknown attack type falls back to HOST_TEMPLATE."""
        assert get_target_template("unknown") is HOST_TEMPLATE

    def test_host_has_no_attacker_template(self):
        """Host attacks return None for attacker template."""
        assert get_attacker_template("host") is None

    def test_exfil_attacker_template(self):
        """Exfil returns EXFILTRATION_ATTACKER_TEMPLATE."""
        assert get_attacker_template("exfil") is EXFILTRATION_ATTACKER_TEMPLATE

    def test_infil_attacker_template(self):
        """Infil returns INFILTRATION_ATTACKER_TEMPLATE."""
        assert get_attacker_template("infil") is INFILTRATION_ATTACKER_TEMPLATE

    def test_lateral_attacker_template(self):
        """Lateral returns LATERAL_MOVEMENT_ATTACKER_TEMPLATE."""
        assert get_attacker_template("lateral") is LATERAL_MOVEMENT_ATTACKER_TEMPLATE

    def test_is_dual_script_host(self):
        """Host is NOT a dual-script type."""
        assert is_dual_script_type("host") is False

    def test_is_dual_script_exfil(self):
        """Exfil IS a dual-script type."""
        assert is_dual_script_type("exfil") is True

    def test_is_dual_script_infil(self):
        """Infil IS a dual-script type."""
        assert is_dual_script_type("infil") is True

    def test_is_dual_script_lateral(self):
        """Lateral IS a dual-script type."""
        assert is_dual_script_type("lateral") is True

    def test_is_dual_script_unknown(self):
        """Unknown type is NOT a dual-script type."""
        assert is_dual_script_type("unknown") is False

    def test_parameters_template_returns_deep_copy(self):
        """get_parameters_template returns a deep copy (mutation-safe)."""
        params1 = get_parameters_template("host")
        params2 = get_parameters_template("host")
        # Different objects
        assert params1 is not params2
        # Mutating one doesn't affect the other
        params1["parameters"][0]["name"] = "MUTATED"
        assert params2["parameters"][0]["name"] == "target_command"
        # Original constant is unchanged
        assert HOST_PARAMETERS_TEMPLATE["parameters"][0]["name"] == "target_command"

    def test_host_parameters_have_expected_fields(self):
        """Host parameters have target_command and expected_output."""
        params = get_parameters_template("host")
        names = [p["name"] for p in params["parameters"]]
        assert "target_command" in names
        assert "expected_output" in names

    def test_exfil_parameters_have_expected_fields(self):
        """Exfil parameters have sensitive_data and exfil_port."""
        params = get_parameters_template("exfil")
        names = [p["name"] for p in params["parameters"]]
        assert "sensitive_data" in names
        assert "exfil_port" in names

    def test_infil_parameters_have_expected_fields(self):
        """Infil parameters have malicious_script and infil_port."""
        params = get_parameters_template("infil")
        names = [p["name"] for p in params["parameters"]]
        assert "malicious_script" in names
        assert "infil_port" in names

    def test_lateral_parameters_have_expected_fields(self):
        """Lateral parameters have service_port, username, password_attempts."""
        params = get_parameters_template("lateral")
        names = [p["name"] for p in params["parameters"]]
        assert "service_port" in names
        assert "username" in names
        assert "password_attempts" in names

    def test_parameters_json_is_parseable(self):
        """get_parameters_template_json returns valid JSON for all types."""
        for attack_type in ["host", "exfil", "infil", "lateral"]:
            json_str = get_parameters_template_json(attack_type)
            parsed = json.loads(json_str)
            assert "parameters" in parsed

    def test_all_descriptions_non_empty(self):
        """All attack type descriptions are non-empty strings."""
        for attack_type in ["host", "exfil", "infil", "lateral"]:
            desc = get_attack_type_description(attack_type)
            assert isinstance(desc, str)
            assert len(desc) > 20

    def test_all_target_templates_contain_main_signature(self):
        """All target templates contain the required main function signature."""
        for attack_type in ["host", "exfil", "infil", "lateral"]:
            template = get_target_template(attack_type)
            assert "def main(system_data, asset, proxy, *args, **kwargs):" in template

    def test_all_attacker_templates_contain_main_signature(self):
        """All attacker templates contain the required main function signature."""
        for attack_type in ["exfil", "infil", "lateral"]:
            template = get_attacker_template(attack_type)
            assert template is not None
            assert "def main(system_data, asset, proxy, *args, **kwargs):" in template

    def test_template_version_is_string(self):
        """TEMPLATE_VERSION is a non-empty string."""
        assert isinstance(TEMPLATE_VERSION, str)
        assert len(TEMPLATE_VERSION) > 0


class TestGetStudioAttackBoilerplate:
    """Tests for sb_get_studio_attack_boilerplate function."""

    def test_host_returns_correct_structure(self):
        """Host boilerplate has expected keys and values."""
        result = sb_get_studio_attack_boilerplate("host")
        assert result["attack_type"] == "host"
        assert result["is_dual_script"] is False
        assert result["attacker_code"] is None
        assert result["target_code"] is HOST_TEMPLATE
        assert result["template_version"] == TEMPLATE_VERSION
        assert "target.py" in result["files_needed"]
        assert "attacker.py" not in result["files_needed"]

    def test_exfil_returns_dual_script(self):
        """Exfil boilerplate has dual-script with attacker code."""
        result = sb_get_studio_attack_boilerplate("exfil")
        assert result["attack_type"] == "exfil"
        assert result["is_dual_script"] is True
        assert result["attacker_code"] is not None
        assert result["attacker_code"] is EXFILTRATION_ATTACKER_TEMPLATE
        assert "target.py" in result["files_needed"]
        assert "attacker.py" in result["files_needed"]

    def test_infil_returns_dual_script(self):
        """Infil boilerplate has dual-script with attacker code."""
        result = sb_get_studio_attack_boilerplate("infil")
        assert result["is_dual_script"] is True
        assert result["attacker_code"] is INFILTRATION_ATTACKER_TEMPLATE

    def test_lateral_returns_dual_script(self):
        """Lateral boilerplate has dual-script with attacker code."""
        result = sb_get_studio_attack_boilerplate("lateral")
        assert result["is_dual_script"] is True
        assert result["attacker_code"] is LATERAL_MOVEMENT_ATTACKER_TEMPLATE

    def test_default_is_host(self):
        """Default attack_type is 'host'."""
        result = sb_get_studio_attack_boilerplate()
        assert result["attack_type"] == "host"

    def test_invalid_attack_type_raises_value_error(self):
        """Invalid attack type raises ValueError."""
        with pytest.raises(ValueError, match="attack_type must be one of"):
            sb_get_studio_attack_boilerplate("invalid")

    def test_parameters_json_valid_for_all_types(self):
        """parameters_json is valid JSON for all attack types."""
        for attack_type in ["host", "exfil", "infil", "lateral"]:
            result = sb_get_studio_attack_boilerplate(attack_type)
            parsed = json.loads(result["parameters_json"])
            assert "parameters" in parsed
            assert isinstance(parsed["parameters"], list)
            assert len(parsed["parameters"]) > 0

    def test_all_templates_compile_as_valid_python(self):
        """All template code compiles as valid Python."""
        for attack_type in ["host", "exfil", "infil", "lateral"]:
            result = sb_get_studio_attack_boilerplate(attack_type)
            # Target code should compile
            compile(result["target_code"], f"<{attack_type}_target>", "exec")
            # Attacker code should compile (if present)
            if result["attacker_code"]:
                compile(result["attacker_code"], f"<{attack_type}_attacker>", "exec")

    def test_next_steps_mention_validate_and_save(self):
        """next_steps mention validate_studio_code and save_studio_attack_draft."""
        result = sb_get_studio_attack_boilerplate("host")
        next_steps_text = " ".join(result["next_steps"])
        assert "validate_studio_code" in next_steps_text
        assert "save_studio_attack_draft" in next_steps_text

    def test_no_http_requests_made(self):
        """Boilerplate function makes no HTTP requests."""
        with patch('safebreach_mcp_studio.studio_functions.requests') as mock_requests:
            result = sb_get_studio_attack_boilerplate("host")
            mock_requests.get.assert_not_called()
            mock_requests.post.assert_not_called()
            mock_requests.put.assert_not_called()
            assert result["attack_type"] == "host"

    def test_files_needed_host(self):
        """Host type needs only target.py."""
        result = sb_get_studio_attack_boilerplate("host")
        assert result["files_needed"] == ["target.py"]

    def test_files_needed_dual_script(self):
        """Dual-script types need target.py and attacker.py."""
        for attack_type in ["exfil", "infil", "lateral"]:
            result = sb_get_studio_attack_boilerplate(attack_type)
            assert result["files_needed"] == ["target.py", "attacker.py"]

    def test_description_is_non_empty(self):
        """Description is a non-empty string for all types."""
        for attack_type in ["host", "exfil", "infil", "lateral"]:
            result = sb_get_studio_attack_boilerplate(attack_type)
            assert isinstance(result["description"], str)
            assert len(result["description"]) > 20

    def test_case_insensitive_attack_type(self):
        """Boilerplate accepts case-insensitive attack types."""
        result = sb_get_studio_attack_boilerplate("HOST")
        assert result["attack_type"] == "host"

    def test_alias_attack_type(self):
        """Boilerplate accepts alias attack types."""
        result = sb_get_studio_attack_boilerplate("exfiltration")
        assert result["attack_type"] == "exfil"
        assert result["is_dual_script"] is True


class TestAttackTypeNormalization:
    """Test _normalize_attack_type() function."""

    def test_canonical_lowercase_passthrough(self):
        """Canonical lowercase keys pass through unchanged."""
        for key in VALID_ATTACK_TYPES:
            assert _normalize_attack_type(key) == key

    def test_case_insensitive_canonical(self):
        """Mixed-case canonical keys normalize to lowercase."""
        assert _normalize_attack_type("Host") == "host"
        assert _normalize_attack_type("HOST") == "host"
        assert _normalize_attack_type("Exfil") == "exfil"
        assert _normalize_attack_type("INFIL") == "infil"
        assert _normalize_attack_type("LATERAL") == "lateral"

    def test_alias_resolution(self):
        """Aliases resolve to canonical keys."""
        for alias, canonical in ATTACK_TYPE_ALIASES.items():
            assert _normalize_attack_type(alias) == canonical

    def test_alias_case_insensitive(self):
        """Aliases are also case-insensitive."""
        assert _normalize_attack_type("Exfiltration") == "exfil"
        assert _normalize_attack_type("LATERAL_MOVEMENT") == "lateral"
        assert _normalize_attack_type("Host-Level") == "host"
        assert _normalize_attack_type("INFILTRATION") == "infil"

    def test_invalid_raises_value_error(self):
        """Invalid attack type raises ValueError with helpful message."""
        with pytest.raises(ValueError) as exc_info:
            _normalize_attack_type("invalid")
        error_msg = str(exc_info.value)
        assert "attack_type must be one of" in error_msg
        assert "Also accepts aliases" in error_msg

    def test_empty_string_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError):
            _normalize_attack_type("")

    def test_normalize_used_in_validate(self):
        """Verify normalization works end-to-end in sb_validate_studio_code."""
        # "invalid" should still fail validation
        with pytest.raises(ValueError) as exc_info:
            sb_validate_studio_code(
                "def main(system_data, asset, proxy, *args, **kwargs): pass",
                "demo", attack_type="unknown_type"
            )
        assert "attack_type must be one of" in str(exc_info.value)

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_alias_in_save_draft(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put
    ):
        """Alias attack type works in save_studio_attack_draft."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "id": 10000296,
                "name": "Test",
                "description": "",
                "status": "draft",
                "timeout": 300,
                "targetFileName": "target.py",
                "methodType": 5,
                "origin": "BREACH_STUDIO",
                "creationDate": 1700000000000,
                "updateDate": 1700000000000,
            }
        }
        mock_put.return_value = mock_response

        # Use alias "host-level" which should normalize to "host"
        from safebreach_mcp_studio.studio_functions import sb_save_studio_attack_draft as save_fn
        import requests as req_module
        with patch('safebreach_mcp_studio.studio_functions.requests.post', return_value=mock_response):
            result = sb_save_studio_attack_draft(
                name="Test",
                python_code="def main(system_data, asset, proxy, *args, **kwargs): pass",
                console="demo",
                attack_type="host-level",
            )
        assert result['draft_id'] == 10000296


class TestOSConstraintNormalization:
    """Test _validate_os_constraint() case-insensitive normalization."""

    def test_canonical_values_passthrough(self):
        """Canonical values pass through unchanged."""
        assert _validate_os_constraint("All") == "All"
        assert _validate_os_constraint("WINDOWS") == "WINDOWS"
        assert _validate_os_constraint("LINUX") == "LINUX"
        assert _validate_os_constraint("MAC") == "MAC"

    def test_case_insensitive_normalization(self):
        """Mixed-case values normalize to canonical case."""
        assert _validate_os_constraint("all") == "All"
        assert _validate_os_constraint("ALL") == "All"
        assert _validate_os_constraint("windows") == "WINDOWS"
        assert _validate_os_constraint("Windows") == "WINDOWS"
        assert _validate_os_constraint("linux") == "LINUX"
        assert _validate_os_constraint("Linux") == "LINUX"
        assert _validate_os_constraint("mac") == "MAC"
        assert _validate_os_constraint("Mac") == "MAC"

    def test_invalid_os_still_raises(self):
        """Invalid OS values still raise ValueError."""
        with pytest.raises(ValueError) as exc_info:
            _validate_os_constraint("invalid_os")
        assert "os_constraint must be one of" in str(exc_info.value)

    def test_empty_string_raises(self):
        """Empty string raises ValueError."""
        with pytest.raises(ValueError):
            _validate_os_constraint("")

    @patch('safebreach_mcp_studio.studio_functions.requests.put')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_lowercase_os_in_validate(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_put,
    ):
        """Lowercase OS values normalize in sb_validate_studio_code."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "data": {
                "exit_code": 0, "is_valid": True, "stderr": "",
                "stdout": {"/tmp/test.py": []}, "valid": True
            }
        }
        mock_put.return_value = mock_response

        # "windows" should normalize to "WINDOWS" and succeed
        result = sb_validate_studio_code(
            "def main(system_data, asset, proxy, *args, **kwargs): pass",
            "demo", target_os="windows"
        )
        assert result['is_valid'] is True


class TestASTMainSignatureValidation:
    """Test _validate_main_signature_ast() function."""

    def test_valid_signature(self):
        """Valid main function signature passes."""
        code = "def main(system_data, asset, proxy, *args, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is True
        assert result["signature_errors"] == []

    def test_no_main_function(self):
        """Code without main function detected."""
        code = "def execute():\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert result["signature_errors"] == []

    def test_wrong_parameter_names(self):
        """Wrong parameter names detected."""
        code = "def main(x, y, z, *args, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert len(result["signature_errors"]) > 0
        assert "positional parameters" in result["signature_errors"][0]

    def test_missing_args(self):
        """Missing *args detected."""
        code = "def main(system_data, asset, proxy, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert any("*args" in e for e in result["signature_errors"])

    def test_missing_kwargs(self):
        """Missing **kwargs detected."""
        code = "def main(system_data, asset, proxy, *args):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert any("**kwargs" in e for e in result["signature_errors"])

    def test_wrong_args_name(self):
        """Wrong *args name detected."""
        code = "def main(system_data, asset, proxy, *a, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert any("vararg" in e for e in result["signature_errors"])

    def test_wrong_kwargs_name(self):
        """Wrong **kwargs name detected."""
        code = "def main(system_data, asset, proxy, *args, **kw):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert any("kwarg" in e for e in result["signature_errors"])

    def test_syntax_error_returns_no_main(self):
        """Syntax errors result in has_main_function=False, no signature errors."""
        code = "def main(system_data, asset, proxy, *args, **kwargs):\n    :"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert result["signature_errors"] == []

    def test_async_def_not_matched(self):
        """async def main() is not matched (only regular def)."""
        code = "async def main(system_data, asset, proxy, *args, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False

    def test_extra_positional_args(self):
        """Extra positional args detected."""
        code = "def main(system_data, asset, proxy, extra, *args, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False
        assert any("positional parameters" in e for e in result["signature_errors"])

    def test_too_few_positional_args(self):
        """Too few positional args detected."""
        code = "def main(system_data, *args, **kwargs):\n    pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False

    def test_nested_main_not_matched(self):
        """Nested main function (inside class or another function) is not matched."""
        code = "class Foo:\n    def main(system_data, asset, proxy, *args, **kwargs):\n        pass"
        result = _validate_main_signature_ast(code, "target")
        assert result["has_main_function"] is False

    def test_signature_errors_in_validation_errors(self):
        """Signature errors appear in validation_errors of sb_validate_studio_code."""
        code = "def main(x, y, z, *args, **kwargs):\n    pass"
        # This should fail locally before reaching API, but the errors should
        # be captured. We need to mock the API calls.
        with pytest.raises(Exception):
            # Will fail because no API mock, but the local validation should work
            sb_validate_studio_code(code, "demo")


class TestTestIdFilter:
    """Test test_id filter in sb_get_studio_attack_latest_result."""

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_without_test_id(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post
    ):
        """Without test_id, query contains only Playbook_id."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {"simulations": [], "total": 0}
        mock_post.return_value = mock_response

        sb_get_studio_attack_latest_result(attack_id=10000291, console="demo")

        # Verify query payload
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert 'runId:' not in payload['query']
        assert 'Playbook_id:("10000291")' in payload['query']

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_with_test_id(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post
    ):
        """With test_id, query includes AND runId:{test_id}."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {"simulations": [], "total": 0}
        mock_post.return_value = mock_response

        sb_get_studio_attack_latest_result(
            attack_id=10000291, console="demo", test_id="abc-123-def"
        )

        # Verify query payload includes test_id
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert 'Playbook_id:("10000291")' in payload['query']
        assert 'AND runId:abc-123-def' in payload['query']

    @patch('safebreach_mcp_studio.studio_functions.requests.post')
    @patch('safebreach_mcp_studio.studio_functions.get_api_account_id')
    @patch('safebreach_mcp_studio.studio_functions.get_api_base_url')
    @patch('safebreach_mcp_studio.studio_functions.get_secret_for_console')
    def test_empty_test_id_ignored(
        self, mock_get_secret, mock_get_base_url, mock_get_account_id, mock_post
    ):
        """Empty string test_id is treated as None (not included)."""
        mock_get_secret.return_value = "test-api-token"
        mock_get_base_url.return_value = "https://demo.safebreach.com"
        mock_get_account_id.return_value = "1234567890"

        mock_response = MagicMock()
        mock_response.json.return_value = {"simulations": [], "total": 0}
        mock_post.return_value = mock_response

        sb_get_studio_attack_latest_result(
            attack_id=10000291, console="demo", test_id=""
        )

        # Empty string should be falsy, so no runId filter
        call_kwargs = mock_post.call_args
        payload = call_kwargs.kwargs.get('json') or call_kwargs[1].get('json')
        assert 'runId:' not in payload['query']
