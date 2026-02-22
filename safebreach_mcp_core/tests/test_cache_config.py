"""
Tests for cache_config per-server toggle logic.

Covers per-server toggles, env var value parsing, and reset behavior.
"""

import os

from safebreach_mcp_core.cache_config import is_caching_enabled, reset_cache_config


def _clean_env():
    """Remove all cache-related env vars."""
    for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
        os.environ.pop(f"SB_MCP_CACHE_{suffix}", None)


class TestNoServerName:
    """Test is_caching_enabled() with no server_name argument."""

    def setup_method(self):
        reset_cache_config()
        _clean_env()

    def teardown_method(self):
        reset_cache_config()
        _clean_env()

    def test_no_args_returns_false(self):
        assert is_caching_enabled() is False

    def test_no_args_returns_false_even_with_per_server_set(self):
        os.environ["SB_MCP_CACHE_DATA"] = "true"
        reset_cache_config()
        assert is_caching_enabled() is False


class TestPerServerToggle:
    """Test per-server SB_MCP_CACHE_{SERVER} toggles."""

    def setup_method(self):
        reset_cache_config()
        _clean_env()

    def teardown_method(self):
        reset_cache_config()
        _clean_env()

    def test_server_enabled(self):
        os.environ["SB_MCP_CACHE_DATA"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is True

    def test_server_disabled(self):
        os.environ["SB_MCP_CACHE_DATA"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is False

    def test_server_unset_defaults_to_false(self):
        reset_cache_config()
        for name in ("config", "data", "playbook", "studio"):
            assert is_caching_enabled(server_name=name) is False

    def test_one_enabled_others_disabled(self):
        os.environ["SB_MCP_CACHE_DATA"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is True
        assert is_caching_enabled(server_name="config") is False
        assert is_caching_enabled(server_name="playbook") is False
        assert is_caching_enabled(server_name="studio") is False

    def test_multiple_servers_independently_controlled(self):
        os.environ["SB_MCP_CACHE_CONFIG"] = "true"
        os.environ["SB_MCP_CACHE_STUDIO"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is True
        assert is_caching_enabled(server_name="data") is False
        assert is_caching_enabled(server_name="playbook") is False
        assert is_caching_enabled(server_name="studio") is True

    def test_all_servers_enabled(self):
        for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
            os.environ[f"SB_MCP_CACHE_{suffix}"] = "true"
        reset_cache_config()
        for name in ("config", "data", "playbook", "studio"):
            assert is_caching_enabled(server_name=name) is True

    def test_unknown_server_returns_false(self):
        reset_cache_config()
        assert is_caching_enabled(server_name="unknown_server") is False

    def test_case_insensitive_server_name(self):
        os.environ["SB_MCP_CACHE_CONFIG"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="CONFIG") is True
        assert is_caching_enabled(server_name="Config") is True
        assert is_caching_enabled(server_name="config") is True


class TestEnvVarParsing:
    """Test that various env var values are correctly interpreted."""

    def setup_method(self):
        reset_cache_config()
        _clean_env()

    def teardown_method(self):
        reset_cache_config()
        _clean_env()

    def test_truthy_values(self):
        for val in ("true", "1", "yes", "on", "TRUE", "True", "YES", "On"):
            os.environ["SB_MCP_CACHE_DATA"] = val
            reset_cache_config()
            assert is_caching_enabled(server_name="data") is True, f"Expected True for '{val}'"

    def test_falsy_values(self):
        for val in ("false", "0", "no", "off", "", "random"):
            os.environ["SB_MCP_CACHE_DATA"] = val
            reset_cache_config()
            assert is_caching_enabled(server_name="data") is False, f"Expected False for '{val}'"

    def test_whitespace_trimmed(self):
        os.environ["SB_MCP_CACHE_DATA"] = "  true  "
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is True


class TestResetCacheConfig:
    """Test that reset_cache_config clears all cached state."""

    def setup_method(self):
        reset_cache_config()
        _clean_env()

    def teardown_method(self):
        reset_cache_config()
        _clean_env()

    def test_reset_clears_per_server_cache(self):
        os.environ["SB_MCP_CACHE_DATA"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is True
        # Change env and reset
        os.environ["SB_MCP_CACHE_DATA"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is False

    def test_reset_allows_reeval_after_removing_env(self):
        os.environ["SB_MCP_CACHE_CONFIG"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is True
        # Remove override, config should fall back to False
        os.environ.pop("SB_MCP_CACHE_CONFIG")
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is False
