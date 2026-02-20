"""
Tests for cache_config per-server toggle logic.

Covers global toggle, per-server overrides, env var value parsing,
backward compatibility, and reset behavior.
"""

import os

from safebreach_mcp_core.cache_config import is_caching_enabled, reset_cache_config


class TestGlobalToggle:
    """Test global SB_MCP_ENABLE_LOCAL_CACHING behavior."""

    def setup_method(self):
        reset_cache_config()
        os.environ.pop("SB_MCP_ENABLE_LOCAL_CACHING", None)
        for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
            os.environ.pop(f"SB_MCP_CACHE_{suffix}", None)

    def teardown_method(self):
        self.setup_method()

    def test_global_on_enables_all_servers(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        reset_cache_config()
        for name in ("config", "data", "playbook", "studio"):
            assert is_caching_enabled(server_name=name) is True

    def test_global_off_disables_all_servers(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        reset_cache_config()
        for name in ("config", "data", "playbook", "studio"):
            assert is_caching_enabled(server_name=name) is False

    def test_global_unset_disables_all_servers(self):
        reset_cache_config()
        for name in ("config", "data", "playbook", "studio"):
            assert is_caching_enabled(server_name=name) is False

    def test_backward_compat_no_args(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        reset_cache_config()
        assert is_caching_enabled() is True

    def test_backward_compat_no_args_disabled(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        reset_cache_config()
        assert is_caching_enabled() is False


class TestPerServerToggle:
    """Test per-server SB_MCP_CACHE_{SERVER} overrides."""

    def setup_method(self):
        reset_cache_config()
        os.environ.pop("SB_MCP_ENABLE_LOCAL_CACHING", None)
        for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
            os.environ.pop(f"SB_MCP_CACHE_{suffix}", None)

    def teardown_method(self):
        self.setup_method()

    def test_server_specific_on_with_global_off(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        os.environ["SB_MCP_CACHE_DATA"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is True
        assert is_caching_enabled(server_name="config") is False
        assert is_caching_enabled(server_name="playbook") is False
        assert is_caching_enabled(server_name="studio") is False

    def test_server_specific_off_with_global_on(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        os.environ["SB_MCP_CACHE_PLAYBOOK"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="playbook") is False
        assert is_caching_enabled(server_name="config") is True
        assert is_caching_enabled(server_name="data") is True
        assert is_caching_enabled(server_name="studio") is True

    def test_server_specific_takes_precedence(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        os.environ["SB_MCP_CACHE_CONFIG"] = "false"
        os.environ["SB_MCP_CACHE_DATA"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is False
        assert is_caching_enabled(server_name="data") is False
        assert is_caching_enabled(server_name="playbook") is True
        assert is_caching_enabled(server_name="studio") is True

    def test_unknown_server_falls_back_to_global(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="unknown_server") is True

    def test_unknown_server_global_off(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="unknown_server") is False

    def test_multiple_servers_independently_controlled(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        os.environ["SB_MCP_CACHE_CONFIG"] = "true"
        os.environ["SB_MCP_CACHE_STUDIO"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is True
        assert is_caching_enabled(server_name="data") is False
        assert is_caching_enabled(server_name="playbook") is False
        assert is_caching_enabled(server_name="studio") is True


class TestEnvVarParsing:
    """Test that various env var values are correctly interpreted."""

    def setup_method(self):
        reset_cache_config()
        os.environ.pop("SB_MCP_ENABLE_LOCAL_CACHING", None)
        for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
            os.environ.pop(f"SB_MCP_CACHE_{suffix}", None)

    def teardown_method(self):
        self.setup_method()

    def test_truthy_values_global(self):
        for val in ("true", "1", "yes", "on", "TRUE", "True", "YES", "On"):
            os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = val
            reset_cache_config()
            assert is_caching_enabled() is True, f"Expected True for '{val}'"

    def test_falsy_values_global(self):
        for val in ("false", "0", "no", "off", "", "random"):
            os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = val
            reset_cache_config()
            assert is_caching_enabled() is False, f"Expected False for '{val}'"

    def test_truthy_values_per_server(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        for val in ("true", "1", "yes", "on", "TRUE"):
            os.environ["SB_MCP_CACHE_DATA"] = val
            reset_cache_config()
            assert is_caching_enabled(server_name="data") is True, (
                f"Expected True for per-server '{val}'"
            )

    def test_falsy_values_per_server(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        for val in ("false", "0", "no", "off"):
            os.environ["SB_MCP_CACHE_DATA"] = val
            reset_cache_config()
            assert is_caching_enabled(server_name="data") is False, (
                f"Expected False for per-server '{val}'"
            )

    def test_whitespace_trimmed(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "  true  "
        reset_cache_config()
        assert is_caching_enabled() is True


class TestResetCacheConfig:
    """Test that reset_cache_config clears all cached state."""

    def setup_method(self):
        reset_cache_config()
        os.environ.pop("SB_MCP_ENABLE_LOCAL_CACHING", None)
        for suffix in ("CONFIG", "DATA", "PLAYBOOK", "STUDIO"):
            os.environ.pop(f"SB_MCP_CACHE_{suffix}", None)

    def teardown_method(self):
        self.setup_method()

    def test_reset_clears_global_cache(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        reset_cache_config()
        assert is_caching_enabled() is True
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        reset_cache_config()
        assert is_caching_enabled() is False

    def test_reset_clears_per_server_cache(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "false"
        os.environ["SB_MCP_CACHE_DATA"] = "true"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is True
        # Change env and reset
        os.environ["SB_MCP_CACHE_DATA"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="data") is False

    def test_reset_allows_reeval_with_new_env(self):
        os.environ["SB_MCP_ENABLE_LOCAL_CACHING"] = "true"
        os.environ["SB_MCP_CACHE_CONFIG"] = "false"
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is False
        # Remove override, config should fall back to global
        os.environ.pop("SB_MCP_CACHE_CONFIG")
        reset_cache_config()
        assert is_caching_enabled(server_name="config") is True
