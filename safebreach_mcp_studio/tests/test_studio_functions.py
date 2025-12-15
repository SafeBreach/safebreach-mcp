"""
Tests for SafeBreach Studio Functions

This module tests the core business logic functions for Studio operations.
"""

import pytest
import time
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_studio.studio_functions import (
    sb_validate_studio_code,
    sb_save_studio_draft,
    sb_get_all_studio_simulations,
    sb_update_studio_draft,
    sb_get_studio_simulation_source,
    sb_run_studio_simulation,
    sb_get_studio_simulation_latest_result,
    studio_draft_cache,
    MAIN_FUNCTION_PATTERN,
    _validate_and_build_parameters,
    VALID_PARAMETER_TYPES,
    VALID_PROTOCOLS
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


class TestSaveStudioDraft:
    """Test the sb_save_studio_draft function."""

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
        result = sb_save_studio_draft(
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
            sb_save_studio_draft(
                name="",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "name parameter is required" in str(exc_info.value)

    def test_save_studio_draft_empty_code(self):
        """Test saving draft with empty python_code parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_draft(
                name="Test Simulation",
                python_code="",
                console="demo"
            )

        assert "python_code parameter is required" in str(exc_info.value)

    def test_save_studio_draft_invalid_timeout(self, sample_valid_python_code):
        """Test saving draft with invalid timeout."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_draft(
                name="Test Simulation",
                python_code=sample_valid_python_code,
                timeout=0,
                console="demo"
            )

        assert "timeout must be at least 1 second" in str(exc_info.value)

    def test_save_studio_draft_invalid_os_constraint(self, sample_valid_python_code):
        """Test saving draft with invalid os_constraint parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_save_studio_draft(
                name="Test Simulation",
                python_code=sample_valid_python_code,
                os_constraint="invalid_os",
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
        result = sb_save_studio_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            description="Test description",
            timeout=300,
            os_constraint="WINDOWS",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "WINDOWS"

        # Verify API was called with targetConstraints
        call_args = mock_post.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' in data
        assert data['targetConstraints'] == '{"os":"WINDOWS"}'

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
        result = sb_save_studio_draft(
            name="Test Simulation",
            python_code=sample_valid_python_code,
            description="Test description",
            timeout=300,
            os_constraint="All",
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
            sb_save_studio_draft(
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
        result = sb_save_studio_draft(
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


class TestGetAllStudioSimulations:
    """Test the sb_get_all_studio_simulations function."""

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
        result = sb_get_all_studio_simulations(console="demo", status_filter="all")

        # Verify
        assert result['total_count'] == 3
        assert result['draft_count'] == 2
        assert result['published_count'] == 1
        assert len(result['simulations']) == 3

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
        result = sb_get_all_studio_simulations(console="demo", status_filter="draft")

        # Verify
        assert result['total_count'] == 2
        assert all(sim['status'] == 'draft' for sim in result['simulations'])

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
        result = sb_get_all_studio_simulations(console="demo", status_filter="published")

        # Verify
        assert result['total_count'] == 1
        assert all(sim['status'] == 'published' for sim in result['simulations'])

    def test_get_all_simulations_invalid_status_filter(self):
        """Test validation of invalid status filter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_all_studio_simulations(console="demo", status_filter="invalid")

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
        result = sb_get_all_studio_simulations(console="demo", name_filter="Draft")

        # Verify
        assert result['total_count'] == 2
        assert all("Draft" in sim['name'] or "draft" in sim['name'] for sim in result['simulations'])

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
        result = sb_get_all_studio_simulations(console="demo", user_id_filter=123)

        # Verify
        assert result['total_count'] == 2
        assert all(sim['user_created'] == 123 for sim in result['simulations'])

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
        result = sb_get_all_studio_simulations(
            console="demo",
            status_filter="draft",
            name_filter="Test",
            user_id_filter=123
        )

        # Verify - should only return ID 1 (draft, "Test" in name, user 123)
        assert result['total_count'] == 1
        assert result['simulations'][0]['id'] == 1
        assert result['simulations'][0]['status'] == 'draft'
        assert "Test" in result['simulations'][0]['name']
        assert result['simulations'][0]['user_created'] == 123

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
            sb_get_all_studio_simulations(console="demo")

        assert "API Error" in str(exc_info.value)


class TestUpdateStudioDraft:
    """Test the sb_update_studio_draft function."""

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
        result = sb_update_studio_draft(
            draft_id=10000298,
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
            sb_update_studio_draft(
                draft_id=0,
                name="Test",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "draft_id must be a positive integer" in str(exc_info.value)

    def test_update_draft_invalid_draft_id_negative(self, sample_valid_python_code):
        """Test updating draft with invalid draft_id (negative)."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_draft(
                draft_id=-1,
                name="Test",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "draft_id must be a positive integer" in str(exc_info.value)

    def test_update_draft_empty_name(self, sample_valid_python_code):
        """Test updating draft with empty name."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_draft(
                draft_id=12345,
                name="",
                python_code=sample_valid_python_code,
                console="demo"
            )

        assert "name parameter is required" in str(exc_info.value)

    def test_update_draft_empty_code(self):
        """Test updating draft with empty python_code."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_draft(
                draft_id=12345,
                name="Test",
                python_code="",
                console="demo"
            )

        assert "python_code parameter is required" in str(exc_info.value)

    def test_update_draft_invalid_timeout(self, sample_valid_python_code):
        """Test updating draft with invalid timeout."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_draft(
                draft_id=12345,
                name="Test",
                python_code=sample_valid_python_code,
                timeout=0,
                console="demo"
            )

        assert "timeout must be at least 1 second" in str(exc_info.value)

    def test_update_draft_invalid_os_constraint(self, sample_valid_python_code):
        """Test updating draft with invalid os_constraint parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_update_studio_draft(
                draft_id=12345,
                name="Test",
                python_code=sample_valid_python_code,
                os_constraint="INVALID",
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
        result = sb_update_studio_draft(
            draft_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            os_constraint="LINUX",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "LINUX"

        # Verify API was called with targetConstraints
        call_args = mock_put.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' in data
        assert data['targetConstraints'] == '{"os":"LINUX"}'

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
        result = sb_update_studio_draft(
            draft_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            os_constraint="MAC",
            console="demo"
        )

        # Verify
        assert result['os_constraint'] == "MAC"

        # Verify API was called with targetConstraints
        call_args = mock_put.call_args
        data = call_args[1]['data']
        assert 'targetConstraints' in data
        assert data['targetConstraints'] == '{"os":"MAC"}'

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
        result = sb_update_studio_draft(
            draft_id=10000298,
            name="Updated Simulation",
            python_code=sample_valid_python_code,
            description="Updated description",
            timeout=600,
            os_constraint="All",
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
            sb_update_studio_draft(
                draft_id=99999,
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
        result = sb_update_studio_draft(
            draft_id=10000298,
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


class TestGetStudioSimulationSource:
    """Test the sb_get_studio_simulation_source function."""

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

        mock_response = MagicMock()
        mock_response.json.return_value = mock_source_response
        mock_get.return_value = mock_response

        # Execute
        result = sb_get_studio_simulation_source(
            simulation_id=10000298,
            console="demo"
        )

        # Verify
        assert result['filename'] == "target.py"
        assert 'content' in result
        assert 'def main(system_data, asset, proxy, *args, **kwargs):' in result['content']
        assert len(result['content']) > 0

        # Verify API was called correctly
        mock_get.assert_called_once()
        call_args = mock_get.call_args
        assert "customMethods/10000298/files/target" in call_args[0][0]
        assert call_args[1]['timeout'] == 120

    def test_get_source_invalid_simulation_id_zero(self):
        """Test getting source with invalid simulation_id (zero)."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_simulation_source(simulation_id=0, console="demo")

        assert "simulation_id must be a positive integer" in str(exc_info.value)

    def test_get_source_invalid_simulation_id_negative(self):
        """Test getting source with invalid simulation_id (negative)."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_simulation_source(simulation_id=-1, console="demo")

        assert "simulation_id must be a positive integer" in str(exc_info.value)

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
            sb_get_studio_simulation_source(simulation_id=99999, console="demo")

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

        # Mock response with empty content
        empty_response = {
            "data": {
                "filename": "target.py",
                "content": ""
            }
        }
        mock_response = MagicMock()
        mock_response.json.return_value = empty_response
        mock_get.return_value = mock_response

        # Execute
        result = sb_get_studio_simulation_source(simulation_id=12345, console="demo")

        # Verify
        assert result['filename'] == "target.py"
        assert result['content'] == ""


class TestRunStudioSimulation:
    """Test the sb_run_studio_simulation function."""

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
        result = sb_run_studio_simulation(
            simulation_id=10000298,
            console="demo"
        )

        # Verify result
        assert result['plan_run_id'] == "1764570357286.4"
        assert result['step_run_id'] == "1764570357287.5"
        assert result['simulation_id'] == 10000298
        assert result['simulator_count'] == 'all connected'
        assert result['draft'] is True

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

        simulator_ids = ["sim-uuid-1", "sim-uuid-2", "sim-uuid-3"]

        # Execute
        result = sb_run_studio_simulation(
            simulation_id=10000298,
            console="demo",
            simulator_ids=simulator_ids
        )

        # Verify result
        assert result['plan_run_id'] == "1764570357286.4"
        assert result['simulator_count'] == 3

        # Verify payload structure for specific simulators
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        assert 'simulators' in payload['plan']['steps'][0]['attackerFilter']
        assert 'simulators' in payload['plan']['steps'][0]['targetFilter']
        assert payload['plan']['steps'][0]['attackerFilter']['simulators']['values'] == simulator_ids
        assert payload['plan']['steps'][0]['targetFilter']['simulators']['values'] == simulator_ids

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
        result = sb_run_studio_simulation(
            simulation_id=10000298,
            console="demo",
            test_name="My Custom Test Name"
        )

        # Verify payload contains custom name
        call_args = mock_post.call_args
        payload = call_args[1]['json']
        assert payload['plan']['name'] == "My Custom Test Name"

    def test_run_simulation_invalid_simulation_id(self):
        """Test running simulation with invalid simulation_id."""
        with pytest.raises(ValueError) as exc_info:
            sb_run_studio_simulation(simulation_id=0, console="demo")

        assert "simulation_id must be a positive integer" in str(exc_info.value)

    def test_run_simulation_empty_simulator_list(self):
        """Test running simulation with empty simulator_ids list."""
        with pytest.raises(ValueError) as exc_info:
            sb_run_studio_simulation(
                simulation_id=10000298,
                console="demo",
                simulator_ids=[]
            )

        assert "simulator_ids cannot be an empty list" in str(exc_info.value)

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
            sb_run_studio_simulation(simulation_id=10000298, console="demo")

        assert "API Error" in str(exc_info.value)


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


class TestGetStudioSimulationLatestResult:
    """Test suite for sb_get_studio_simulation_latest_result function."""

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
        result = sb_get_studio_simulation_latest_result(
            simulation_id=10000291,
            console="demo",
            max_results=1
        )

        # Assertions
        assert result['simulation_id'] == 10000291
        assert result['console'] == "demo"
        assert result['total_found'] == 2
        assert result['returned_count'] == 1
        assert result['has_more'] is True
        assert len(result['executions']) == 1

        # Check first execution details
        execution = result['executions'][0]
        assert execution['execution_id'] == "1463450"
        assert execution['simulation_id'] == 10000291
        assert execution['simulation_name'] == "test registry shuit"
        assert execution['status'] == "SUCCESS"
        assert execution['final_status'] == "missed"
        assert execution['security_action'] == "not_logged"
        assert execution['test_name'] == "test registry shuit"
        assert execution['plan_run_id'] == "1764570357286.4"

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
        result = sb_get_studio_simulation_latest_result(
            simulation_id=10000291,
            console="demo",
            max_results=2
        )

        # Assertions
        assert result['returned_count'] == 2
        assert result['total_found'] == 2
        assert result['has_more'] is False
        assert len(result['executions']) == 2

        # Check ordering (newest first)
        assert result['executions'][0]['execution_id'] == "1463450"
        assert result['executions'][1]['execution_id'] == "1462025"

        # Verify different statuses
        assert result['executions'][0]['status'] == "SUCCESS"
        assert result['executions'][1]['status'] == "FAIL"

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
        result = sb_get_studio_simulation_latest_result(
            simulation_id=99999,
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
            sb_get_studio_simulation_latest_result(simulation_id=0, console="demo")

        assert "simulation_id must be a positive integer" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_simulation_latest_result(simulation_id=-1, console="demo")

        assert "simulation_id must be a positive integer" in str(exc_info.value)

    def test_get_latest_result_invalid_max_results(self):
        """Test with invalid max_results parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_simulation_latest_result(
                simulation_id=10000291,
                console="demo",
                max_results=0
            )

        assert "max_results must be at least 1" in str(exc_info.value)

    def test_get_latest_result_invalid_page_size(self):
        """Test with invalid page_size parameter."""
        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_simulation_latest_result(
                simulation_id=10000291,
                console="demo",
                page_size=0
            )

        assert "page_size must be between 1 and 1000" in str(exc_info.value)

        with pytest.raises(ValueError) as exc_info:
            sb_get_studio_simulation_latest_result(
                simulation_id=10000291,
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
            sb_get_studio_simulation_latest_result(simulation_id=10000291, console="demo")

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
        result = sb_save_studio_draft(
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
        result = sb_save_studio_draft(
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
        result = sb_save_studio_draft(
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
