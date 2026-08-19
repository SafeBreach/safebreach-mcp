"""
Tests for SafeBreach Playbook Server

This module tests the FastMCP server implementation for playbook operations.
"""

import pytest
from unittest.mock import Mock, patch, MagicMock
from safebreach_mcp_playbook.playbook_server import SafeBreachPlaybookServer, parse_external_config


class TestSafeBreachPlaybookServer:
    """Test the SafeBreachPlaybookServer class."""
    
    def test_server_initialization(self):
        """Test server initialization."""
        server = SafeBreachPlaybookServer()
        
        # Check that server was initialized correctly
        assert hasattr(server, 'mcp')
        assert server.mcp is not None
        
        # Check that tools were registered
        # We can't easily test tool registration without more complex mocking,
        # but we can at least verify the server was created
        assert isinstance(server, SafeBreachPlaybookServer)
    
    def test_server_has_mcp_attribute(self):
        """Test that server has the mcp attribute properly initialized."""
        server = SafeBreachPlaybookServer()
        assert hasattr(server, 'mcp')
        assert server.mcp is not None


class TestExposedTagTools:
    """Guard the tag surface the playbook server advertises.

    Tag mutation is unsupported backend-side, so the write tools must not be registered.
    The read-only tag tools must stay registered.
    """

    WITHDRAWN_WRITE_TOOLS = [
        "add_playbook_attack_tag",
        "remove_playbook_attack_tag",
        "rename_playbook_attack_tag",
        "bulk_add_playbook_attack_tags",
        "bulk_remove_playbook_attack_tags",
        "bulk_rename_playbook_attack_tag",
    ]

    EXPECTED_TOOLS = [
        "get_playbook_attacks",
        "get_playbook_attack_details",
        "get_playbook_attacks_by_tags",
        "get_playbook_attack_tags",
    ]

    def _registered_tool_names(self):
        return set(SafeBreachPlaybookServer().mcp._tool_manager._tools.keys())

    @pytest.mark.parametrize("tool_name", WITHDRAWN_WRITE_TOOLS)
    def test_tag_write_tool_not_registered(self, tool_name):
        """No tag write tool is advertised to MCP clients."""
        assert tool_name not in self._registered_tool_names()

    @pytest.mark.parametrize("tool_name", EXPECTED_TOOLS)
    def test_expected_tool_registered(self, tool_name):
        """The read-only tools, including both tag read tools, stay advertised."""
        assert tool_name in self._registered_tool_names()


class TestParseExternalConfig:
    """Test the parse_external_config function."""
    
    @patch.dict('os.environ', {}, clear=True)
    def test_parse_external_config_default(self):
        """Test parsing external config with default values."""
        result = parse_external_config('playbook')
        assert result is False
    
    @patch.dict('os.environ', {'SAFEBREACH_MCP_ALLOW_EXTERNAL': 'true'}, clear=True)
    def test_parse_external_config_global_flag(self):
        """Test parsing external config with global flag."""
        result = parse_external_config('playbook')
        assert result is True
    
    @patch.dict('os.environ', {'SAFEBREACH_MCP_PLAYBOOK_EXTERNAL': 'true'}, clear=True)
    def test_parse_external_config_server_specific(self):
        """Test parsing external config with server-specific flag."""
        result = parse_external_config('playbook')
        assert result is True
    
    @patch.dict('os.environ', {
        'SAFEBREACH_MCP_ALLOW_EXTERNAL': 'false',
        'SAFEBREACH_MCP_PLAYBOOK_EXTERNAL': 'true'
    }, clear=True)
    def test_parse_external_config_server_overrides_global(self):
        """Test that server-specific flag works even when global is false."""
        result = parse_external_config('playbook')
        assert result is True
    
    @patch.dict('os.environ', {'SAFEBREACH_MCP_PLAYBOOK_EXTERNAL': 'false'}, clear=True)
    def test_parse_external_config_explicit_false(self):
        """Test parsing external config with explicit false."""
        result = parse_external_config('playbook')
        assert result is False

def _tool_fn(name):
    """Reach the registered tool's underlying callable — the only way to test its formatting."""
    return SafeBreachPlaybookServer().mcp._tool_manager._tools[name].fn


def _fake_result(attacks, total, page=0, pages=1, applied=None, **extra):
    result = {
        'attacks_in_page': attacks,
        'total_attacks': total,
        'page_number': page,
        'total_pages': pages,
        'applied_filters': applied if applied is not None else {'test_type': 'validate'},
    }
    result.update(extra)
    return result


def _attack(attack_id, name, is_propagate=False):
    return {
        'id': attack_id,
        'name': name,
        'description': f'description of {name}',
        'modifiedDate': '2024-10-07T07:28:05.000Z',
        'publishedDate': '2019-05-29T15:18:44.000Z',
        'is_propagate': is_propagate,
    }


class TestPlaybookAttacksPresentation:
    """T-20 through T-23 — the first tests of this layer's rendered output."""

    MIXED = [_attack(101, 'validate one'), _attack(201, 'propagate one', True)]

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    def test_all_scope_renders_split_header(self, mock_sb):
        """T-20: the customer sees which catalogs the total spans."""
        mock_sb.return_value = _fake_result(
            self.MIXED, total=153, applied={'test_type': 'all'},
            validate_count=108, propagate_count=45
        )

        output = _tool_fn('get_playbook_attacks')(console='c', test_type='all')

        assert '153' in output
        assert '108' in output
        assert '45' in output
        assert 'Validate' in output
        assert 'Propagate' in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    def test_propagate_rows_are_marked(self, mock_sb):
        """T-21: the customer can tell which listed attacks they cannot open in the Playbook."""
        mock_sb.return_value = _fake_result(
            self.MIXED, total=2, applied={'test_type': 'all'},
            validate_count=1, propagate_count=1
        )

        output = _tool_fn('get_playbook_attacks')(console='c', test_type='all')

        validate_block, propagate_block = output.split('### propagate one')[0], output.split('### propagate one')[1]
        assert 'not reachable from the Playbook' in propagate_block
        assert 'not reachable from the Playbook' not in validate_block

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    @pytest.mark.parametrize('scope', ['validate', 'propagate'])
    def test_non_all_scope_keeps_single_total_header(self, mock_sb, scope):
        """T-22: the header change is confined to 'all' — the majority path is untouched."""
        mock_sb.return_value = _fake_result(
            [_attack(101, 'only one')], total=1, applied={'test_type': scope}
        )

        output = _tool_fn('get_playbook_attacks')(console='c', test_type=scope)

        assert '**Total attacks matching filters: 1**' in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    @pytest.mark.parametrize('counts', [
        {},
        {'validate_count': None, 'propagate_count': None},
        {'validate_count': 'x', 'propagate_count': 'y'},
    ])
    def test_missing_counts_fall_back_to_single_total(self, mock_sb, counts):
        """T-23: a cosmetic gap must not become a total tool failure."""
        mock_sb.return_value = _fake_result(
            self.MIXED, total=2, applied={'test_type': 'all'}, **counts
        )

        output = _tool_fn('get_playbook_attacks')(console='c', test_type='all')

        assert '**Total attacks matching filters: 2**' in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    def test_test_type_is_forwarded(self, mock_sb):
        """T-14 (server side): the tool passes the scope through rather than dropping it."""
        mock_sb.return_value = _fake_result([], total=0)

        _tool_fn('get_playbook_attacks')(console='c', test_type='propagate')

        assert mock_sb.call_args.kwargs['test_type'] == 'propagate'

    def test_tool_description_documents_scope(self):
        """T-34 (partial): the agent learns the vocabulary and the default from the description."""
        description = SafeBreachPlaybookServer().mcp._tool_manager._tools['get_playbook_attacks'].description

        assert 'test_type' in description
        for value in ('validate', 'propagate', 'all'):
            assert value in description
        assert 'ALM' in description
        assert 'Playbook' in description


class TestAttackDetailsPropagateMarker:
    """T-28, T-29 — reachability marker on get_playbook_attack_details."""

    @staticmethod
    def _details(is_propagate):
        return {
            'id': 9001,
            'name': 'Kerberoasting via SPN enumeration',
            'description': 'Request service tickets for accounts with SPNs',
            'modifiedDate': '2024-10-07T07:28:05.000Z',
            'publishedDate': '2019-05-29T15:18:44.000Z',
            'is_propagate': is_propagate,
        }

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attack_details')
    def test_propagate_attack_marked_unreachable(self, mock_sb):
        """T-28: a customer handed a Propagate id is told why they cannot find it."""
        mock_sb.return_value = self._details(True)

        output = _tool_fn('get_playbook_attack_details')(attack_id=9001, console='c')

        assert 'not reachable from the Playbook' in output
        assert 'Propagate' in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attack_details')
    def test_validate_attack_output_unchanged(self, mock_sb):
        """T-29: the marker is additive — ordinary attacks render exactly as before."""
        mock_sb.return_value = self._details(False)

        output = _tool_fn('get_playbook_attack_details')(attack_id=9001, console='c')

        assert 'not reachable from the Playbook' not in output
        assert 'Propagate' not in output
        assert '## Kerberoasting via SPN enumeration (ID: 9001)' in output
        assert '**Modified Date:** 2024-10-07T07:28:05.000Z' in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attack_details')
    def test_marker_absent_when_flag_missing(self, mock_sb):
        """T-29 (cont.): a payload without the flag must not raise or mark."""
        details = self._details(False)
        del details['is_propagate']
        mock_sb.return_value = details

        output = _tool_fn('get_playbook_attack_details')(attack_id=9001, console='c')

        assert 'not reachable from the Playbook' not in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attack_details')
    def test_details_takes_no_scope_param(self, mock_sb):
        """T-28 (cont.): scope is deliberately absent here - the caller named a specific id."""
        import inspect
        params = inspect.signature(_tool_fn('get_playbook_attack_details')).parameters
        assert 'test_type' not in params


class TestNullDescriptionRendering:
    """Regression guard for the two TypeError crashes the strict review confirmed.

    Pre-existing on main, but in the exact render blocks SAF-34553 edits, so fixed here.
    transform_reduced_playbook_attack always SETS the description key, so a missing API
    description arrives as None rather than triggering dict.get's default.
    """

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    def test_listing_survives_null_description(self, mock_sb):
        """A null description must not crash the listing render."""
        attack = _attack(1027, 'no description attack')
        attack['description'] = None
        mock_sb.return_value = _fake_result([attack], total=1)

        output = _tool_fn('get_playbook_attacks')(console='c')

        assert 'No description available' in output
        assert 'Error getting playbook attacks' not in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    def test_listing_truncates_long_description(self, mock_sb):
        """Truncation behaviour is preserved for an over-long description."""
        attack = _attack(1027, 'long description attack')
        attack['description'] = 'x' * 250
        mock_sb.return_value = _fake_result([attack], total=1)

        output = _tool_fn('get_playbook_attacks')(console='c')

        assert 'x' * 200 + '...' in output
        assert 'x' * 201 not in output.replace('x' * 200 + '...', '')

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attacks')
    def test_listing_keeps_short_description_verbatim(self, mock_sb):
        """A short description is rendered without an ellipsis."""
        attack = _attack(1027, 'short description attack')
        attack['description'] = 'brief'
        mock_sb.return_value = _fake_result([attack], total=1)

        output = _tool_fn('get_playbook_attacks')(console='c')

        assert '**Description:** brief' in output

    @patch('safebreach_mcp_playbook.playbook_server.sb_get_playbook_attack_details')
    def test_details_survives_null_description(self, mock_sb):
        """A null description must not crash the details render via "\n".join."""
        mock_sb.return_value = {
            'id': 9001,
            'name': 'no description attack',
            'description': None,
            'modifiedDate': '2024-10-07',
            'publishedDate': '2019-05-29',
            'is_propagate': False,
        }

        output = _tool_fn('get_playbook_attack_details')(attack_id=9001, console='c')

        assert 'No description available' in output
        assert 'Error getting playbook attack details' not in output
