"""
Tests for SafeBreach Config Server tool registration (SAF-32798).

T-13 — verifies the three integration-discovery tools are registered as read-only
public tools with the expected, sibling-consistent input schemas. (get_ti_integrations
was folded into get_installed_integrations via category_filter='ti'.)
"""

import asyncio
from safebreach_mcp_config.config_server import config_server


def _tools():
    return asyncio.run(config_server.mcp.list_tools())


class TestIntegrationToolsRegistration:

    def test_three_registered_read_only(self):
        tools = {t.name: t for t in _tools()}
        for name in ("get_integrations", "get_installed_integrations",
                     "get_installed_integration"):
            assert name in tools, f"{name} not registered"
            assert tools[name].annotations.readOnlyHint is True
            assert tools[name].description  # non-empty public description
        # the TI tool was removed — TI is now category_filter='ti'
        assert "get_ti_integrations" not in tools

    def test_list_tools_schemas_expose_filters(self):
        tools = {t.name: t for t in _tools()}

        gi = tools["get_integrations"].inputSchema["properties"]
        for p in ("console", "page_number", "name_filter", "category_filter",
                  "vendor_filter", "order_by", "order_direction"):
            assert p in gi, f"get_integrations missing param {p}"
        # capability flags were removed in favour of category_filter
        assert "ti_only" not in gi and "vm_only" not in gi

        gii = tools["get_installed_integrations"].inputSchema["properties"]
        for p in ("console", "page_number", "name_filter", "type_filter",
                  "enabled_filter", "category_filter", "order_by", "order_direction"):
            assert p in gii, f"get_installed_integrations missing param {p}"

        gi1 = tools["get_installed_integration"].inputSchema["properties"]
        assert "integration_id" in gi1  # <entity>_id, not bare 'id'
        assert "id" not in gi1
        assert "console" in gi1
