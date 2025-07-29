"""
Tests for SafeBreach Playbook Types

This module tests the data transformation functions for playbook operations.
"""

import pytest
from safebreach_mcp_playbook.playbook_types import (
    get_reduced_playbook_attack_mapping,
    get_full_playbook_attack_mapping,
    transform_reduced_playbook_attack,
    transform_full_playbook_attack,
    filter_attacks_by_criteria,
    paginate_attacks,
    _transform_tags
)


# Test fixtures
@pytest.fixture
def sample_attack_raw():
    """Sample attack data in raw SafeBreach API format."""
    return {
        "id": 1027,
        "name": "DNS queries of malicious URLs",
        "description": "**Goal**\n\n1. Verify whether the target simulator can resolve the IP address of the known malicious domain.",
        "modifiedDate": "2024-10-07T07:28:05.000Z",
        "publishedDate": "2019-05-29T15:18:44.000Z",
        "metadata": {
            "fix_suggestions": [
                {
                    "title": "Harden Intrusion Prevention System (IPS) security configuration",
                    "content": "Ensure that the network Intrusion Prevention System (IPS) is deployed on the network"
                }
            ]
        },
        "tags": [
            {
                "id": 1,
                "name": "category",
                "values": [
                    {"id": 1, "value": "network", "displayName": "Network"},
                    {"id": 2, "value": "dns", "displayName": "DNS"}
                ]
            }
        ],
        "content": {
            "params": [
                {
                    "id": 1,
                    "name": "port",
                    "type": "PORT",
                    "displayName": "Port",
                    "description": "The port to use in the protocol",
                    "values": [{"id": 1, "value": "53", "displayValue": "53"}]
                }
            ]
        }
    }


@pytest.fixture
def sample_attacks_list():
    """Sample list of attacks for filtering tests."""
    return [
        {
            "id": 1027,
            "name": "DNS queries of malicious URLs",
            "description": "Verify whether the target simulator can resolve IP addresses of malicious domains.",
            "modifiedDate": "2024-10-07T07:28:05.000Z",
            "publishedDate": "2019-05-29T15:18:44.000Z"
        },
        {
            "id": 2048,
            "name": "File transfer via HTTP",
            "description": "Test file transfer capabilities over HTTP protocol.",
            "modifiedDate": "2024-01-15T10:30:00.000Z",
            "publishedDate": "2020-03-10T12:00:00.000Z"
        },
        {
            "id": 3141,
            "name": "SSH brute force attack",
            "description": "Attempt to gain unauthorized access via SSH brute force.",
            "modifiedDate": "2023-12-01T14:22:00.000Z",
            "publishedDate": "2018-11-05T09:15:30.000Z"
        }
    ]


class TestTagsTransformation:
    """Test tags transformation functionality."""
    
    def test_transform_tags_complex_structure(self):
        """Test transformation of complex SafeBreach tags structure."""
        complex_tags = [
            {
                "id": 14,
                "name": "sector",
                "values": [
                    {
                        "id": 1,
                        "sort": 1,
                        "value": "Banking",
                        "displayName": "Banking"
                    },
                    {
                        "id": 2,
                        "sort": 2,
                        "value": "Education", 
                        "displayName": "Education"
                    }
                ]
            },
            {
                "id": 4,
                "name": "approach",
                "values": [
                    {
                        "id": 1,
                        "sort": 1,
                        "value": "direct",
                        "displayName": "Direct Attack"
                    }
                ]
            }
        ]
        
        result = _transform_tags(complex_tags)
        
        expected = ["sector:Banking", "sector:Education", "approach:Direct Attack"]
        assert result == expected
    
    def test_transform_tags_empty_or_none(self):
        """Test transformation of empty or None tags."""
        assert _transform_tags(None) == []
        assert _transform_tags([]) == []
        assert _transform_tags("not a list") == []
    
    def test_transform_tags_malformed_data(self):
        """Test transformation with malformed tag data."""
        malformed_tags = [
            {
                "id": 14,
                "name": "sector",
                "values": [
                    {
                        "id": 1,
                        # Missing value and displayName
                    }
                ]
            },
            {
                # Missing name
                "id": 4,
                "values": [
                    {
                        "id": 1,
                        "value": "test"
                    }
                ]
            },
            "not a dict"
        ]
        
        result = _transform_tags(malformed_tags)
        
        # Should handle malformed data gracefully
        # The string "not a dict" gets treated as simple format
        expected = ["sector:unknown", "unknown:test", "not a dict"]
        assert result == expected
    
    def test_transform_tags_string_values(self):
        """Test transformation when values is a string instead of list."""
        string_tags = [
            {
                "id": 1,
                "name": "category",
                "values": "single_value"
            }
        ]
        
        result = _transform_tags(string_tags)
        assert result == ["category:single_value"]
    
    def test_transform_tags_simple_format(self):
        """Test transformation with simple string format (backward compatibility)."""
        simple_tags = ["network", "dns", "malicious"]
        
        result = _transform_tags(simple_tags)
        assert result == ["network", "dns", "malicious"]
    
    def test_transform_tags_mixed_format(self):
        """Test transformation with mixed simple and complex formats."""
        mixed_tags = [
            "simple_tag",
            {
                "id": 1,
                "name": "complex",
                "values": [
                    {"id": 1, "value": "value1", "displayName": "Value 1"}
                ]
            }
        ]
        
        result = _transform_tags(mixed_tags)
        assert result == ["simple_tag", "complex:Value 1"]


class TestMappingFunctions:
    """Test mapping functions for field transformations."""
    
    def test_get_reduced_playbook_attack_mapping(self):
        """Test reduced attack mapping structure."""
        mapping = get_reduced_playbook_attack_mapping()
        
        expected_fields = ['name', 'id', 'description', 'modifiedDate', 'publishedDate']
        assert set(mapping.keys()) == set(expected_fields)
        
        # Verify all mappings point to expected source fields
        assert mapping['name'] == 'name'
        assert mapping['id'] == 'id'
        assert mapping['description'] == 'description'
        assert mapping['modifiedDate'] == 'modifiedDate'
        assert mapping['publishedDate'] == 'publishedDate'
    
    def test_get_full_playbook_attack_mapping(self):
        """Test full attack mapping structure."""
        mapping = get_full_playbook_attack_mapping()
        
        # Should include all reduced fields plus additional ones
        reduced_fields = ['name', 'id', 'description', 'modifiedDate', 'publishedDate']
        additional_fields = ['fix_suggestions', 'tags', 'params']
        expected_fields = reduced_fields + additional_fields
        
        assert set(mapping.keys()) == set(expected_fields)
        
        # Verify additional field mappings
        assert mapping['fix_suggestions'] == 'metadata.fix_suggestions'
        assert mapping['tags'] == 'tags'
        assert mapping['params'] == 'content.params'


class TestTransformationFunctions:
    """Test data transformation functions."""
    
    def test_transform_reduced_playbook_attack(self, sample_attack_raw):
        """Test transformation to reduced format."""
        result = transform_reduced_playbook_attack(sample_attack_raw)
        
        # Verify all required fields are present
        expected_fields = ['name', 'id', 'description', 'modifiedDate', 'publishedDate']
        assert set(result.keys()) == set(expected_fields)
        
        # Verify field values
        assert result['id'] == 1027
        assert result['name'] == "DNS queries of malicious URLs"
        assert result['description'] == sample_attack_raw['description']
        assert result['modifiedDate'] == "2024-10-07T07:28:05.000Z"
        assert result['publishedDate'] == "2019-05-29T15:18:44.000Z"
    
    def test_transform_reduced_with_missing_fields(self):
        """Test transformation with missing fields."""
        incomplete_data = {
            "id": 123,
            "name": "Test Attack"
            # Missing other fields
        }
        
        result = transform_reduced_playbook_attack(incomplete_data)
        
        # Should still have all expected keys, with None for missing values
        expected_fields = ['name', 'id', 'description', 'modifiedDate', 'publishedDate']
        assert set(result.keys()) == set(expected_fields)
        assert result['id'] == 123
        assert result['name'] == "Test Attack"
        assert result['description'] is None
        assert result['modifiedDate'] is None
        assert result['publishedDate'] is None
    
    def test_transform_full_playbook_attack_default(self, sample_attack_raw):
        """Test transformation to full format with default verbosity."""
        result = transform_full_playbook_attack(sample_attack_raw)
        
        # Should include all reduced fields plus all optional fields (default behavior)
        expected_fields = ['name', 'id', 'description', 'modifiedDate', 'publishedDate', 
                          'fix_suggestions', 'tags', 'params']
        assert set(result.keys()) == set(expected_fields)
        
        # Verify basic fields
        assert result['id'] == 1027
        assert result['name'] == "DNS queries of malicious URLs"
        
        # Verify optional fields are included by default
        assert result['fix_suggestions'] == sample_attack_raw['metadata']['fix_suggestions']
        assert result['tags'] == ["category:Network", "category:DNS"]  # Transformed tags format
        assert result['params'] == sample_attack_raw['content']['params']
    
    def test_transform_full_playbook_attack_selective_verbosity(self, sample_attack_raw):
        """Test transformation with selective verbosity options."""
        result = transform_full_playbook_attack(
            sample_attack_raw,
            include_fix_suggestions=True,
            include_tags=False,
            include_parameters=False
        )
        
        # Should include basic fields and only fix_suggestions
        assert 'id' in result
        assert 'name' in result
        assert 'fix_suggestions' in result
        assert result['fix_suggestions'] == sample_attack_raw['metadata']['fix_suggestions']
        
        # Tags and params should not be included
        assert 'tags' not in result or result['tags'] is None
        assert 'params' not in result or result['params'] is None
    
    def test_transform_full_with_nested_missing_data(self):
        """Test transformation when nested data is missing."""
        incomplete_data = {
            "id": 123,
            "name": "Test Attack",
            "description": "Test description",
            "modifiedDate": "2024-01-01T00:00:00.000Z",
            "publishedDate": "2024-01-01T00:00:00.000Z"
            # Missing metadata and content
        }
        
        result = transform_full_playbook_attack(
            incomplete_data,
            include_fix_suggestions=True,
            include_tags=True,
            include_parameters=True
        )
        
        # Should handle missing nested fields gracefully
        assert result['fix_suggestions'] is None
        assert result['tags'] == []  # _transform_tags returns empty list for missing tags
        assert result['params'] is None


class TestFilteringFunctions:
    """Test attack filtering functionality."""
    
    def test_filter_by_name(self, sample_attacks_list):
        """Test filtering by name."""
        result = filter_attacks_by_criteria(sample_attacks_list, name_filter="DNS")
        
        assert len(result) == 1
        assert result[0]['name'] == "DNS queries of malicious URLs"
    
    def test_filter_by_name_case_insensitive(self, sample_attacks_list):
        """Test name filtering is case insensitive."""
        result = filter_attacks_by_criteria(sample_attacks_list, name_filter="dns")
        
        assert len(result) == 1
        assert result[0]['name'] == "DNS queries of malicious URLs"
    
    def test_filter_by_description(self, sample_attacks_list):
        """Test filtering by description."""
        result = filter_attacks_by_criteria(sample_attacks_list, description_filter="HTTP")
        
        assert len(result) == 1
        assert result[0]['name'] == "File transfer via HTTP"
    
    def test_filter_by_description_case_insensitive(self, sample_attacks_list):
        """Test description filtering is case insensitive."""
        result = filter_attacks_by_criteria(sample_attacks_list, description_filter="http")
        
        assert len(result) == 1
        assert result[0]['name'] == "File transfer via HTTP"
    
    def test_filter_by_id_range(self, sample_attacks_list):
        """Test filtering by ID range."""
        # Test minimum ID
        result = filter_attacks_by_criteria(sample_attacks_list, id_min=2000)
        assert len(result) == 2  # IDs 2048 and 3141
        assert all(attack['id'] >= 2000 for attack in result)
        
        # Test maximum ID
        result = filter_attacks_by_criteria(sample_attacks_list, id_max=2500)
        assert len(result) == 2  # IDs 1027 and 2048
        assert all(attack['id'] <= 2500 for attack in result)
        
        # Test both min and max
        result = filter_attacks_by_criteria(sample_attacks_list, id_min=2000, id_max=2500)
        assert len(result) == 1  # Only ID 2048
        assert result[0]['id'] == 2048
    
    def test_filter_by_modified_date_range(self, sample_attacks_list):
        """Test filtering by modified date range."""
        # Filter for 2024 dates
        result = filter_attacks_by_criteria(
            sample_attacks_list,
            modified_date_start="2024-01-01T00:00:00.000Z",
            modified_date_end="2024-12-31T23:59:59.999Z"
        )
        
        assert len(result) == 2  # DNS and HTTP attacks
        assert all("2024" in attack['modifiedDate'] for attack in result)
    
    def test_filter_by_published_date_range(self, sample_attacks_list):
        """Test filtering by published date range."""
        # Filter for dates from 2019-2020
        result = filter_attacks_by_criteria(
            sample_attacks_list,
            published_date_start="2019-01-01T00:00:00.000Z",
            published_date_end="2020-12-31T23:59:59.999Z"
        )
        
        assert len(result) == 2  # DNS and HTTP attacks
        published_years = [attack['publishedDate'][:4] for attack in result]
        assert "2019" in published_years
        assert "2020" in published_years
    
    def test_filter_combined_criteria(self, sample_attacks_list):
        """Test filtering with multiple criteria."""
        result = filter_attacks_by_criteria(
            sample_attacks_list,
            name_filter="transfer",
            id_min=2000,
            modified_date_start="2024-01-01T00:00:00.000Z"
        )
        
        # Should only return the HTTP transfer attack
        assert len(result) == 1
        assert result[0]['name'] == "File transfer via HTTP"
        assert result[0]['id'] == 2048
    
    def test_filter_no_matches(self, sample_attacks_list):
        """Test filtering with no matches."""
        result = filter_attacks_by_criteria(sample_attacks_list, name_filter="NonExistent")
        assert len(result) == 0
    
    def test_filter_with_none_values(self, sample_attacks_list):
        """Test filtering handles None values gracefully."""
        # Add attack with None values
        attacks_with_none = sample_attacks_list + [{
            "id": None,
            "name": None,
            "description": None,
            "modifiedDate": None,
            "publishedDate": None
        }]
        
        # Filtering should not crash and should exclude None values appropriately
        result = filter_attacks_by_criteria(attacks_with_none, name_filter="DNS")
        assert len(result) == 1
        assert result[0]['name'] == "DNS queries of malicious URLs"


class TestPaginationFunction:
    """Test pagination functionality."""
    
    def test_paginate_basic(self, sample_attacks_list):
        """Test basic pagination."""
        result = paginate_attacks(sample_attacks_list, page_number=0, page_size=2)
        
        assert result['page_number'] == 0
        assert result['total_pages'] == 2  # 3 attacks / 2 per page = 2 pages
        assert result['total_attacks'] == 3
        assert len(result['attacks_in_page']) == 2
        assert result['attacks_in_page'][0]['id'] == 1027
        assert result['attacks_in_page'][1]['id'] == 2048
        assert result['hint_to_agent'] is not None
    
    def test_paginate_second_page(self, sample_attacks_list):
        """Test pagination second page."""
        result = paginate_attacks(sample_attacks_list, page_number=1, page_size=2)
        
        assert result['page_number'] == 1
        assert result['total_pages'] == 2
        assert len(result['attacks_in_page']) == 1  # Last page has only 1 item
        assert result['attacks_in_page'][0]['id'] == 3141
        assert result['hint_to_agent'] is None  # No more pages
    
    def test_paginate_empty_list(self):
        """Test pagination with empty list."""
        result = paginate_attacks([], page_number=0, page_size=10)
        
        assert result['page_number'] == 0
        assert result['total_pages'] == 0
        assert result['total_attacks'] == 0
        assert len(result['attacks_in_page']) == 0
    
    def test_paginate_single_page(self, sample_attacks_list):
        """Test pagination when all items fit on one page."""
        result = paginate_attacks(sample_attacks_list, page_number=0, page_size=10)
        
        assert result['page_number'] == 0
        assert result['total_pages'] == 1
        assert result['total_attacks'] == 3
        assert len(result['attacks_in_page']) == 3
        assert result['hint_to_agent'] is None
    
    def test_paginate_invalid_page_number(self, sample_attacks_list):
        """Test pagination with invalid page number."""
        result = paginate_attacks(sample_attacks_list, page_number=10, page_size=2)
        
        assert 'error' in result
        assert 'Invalid page_number 10' in result['error']
        assert result['page_number'] == 10
        assert result['total_pages'] == 2
        assert result['total_attacks'] == 3
        assert len(result['attacks_in_page']) == 0
    
    def test_paginate_negative_page_number(self, sample_attacks_list):
        """Test pagination with negative page number."""
        result = paginate_attacks(sample_attacks_list, page_number=-1, page_size=2)
        
        assert 'error' in result
        assert 'Invalid page_number -1' in result['error']
        assert len(result['attacks_in_page']) == 0
    
    def test_paginate_large_dataset(self):
        """Test pagination with larger dataset."""
        # Create 25 attacks
        large_dataset = []
        for i in range(25):
            large_dataset.append({
                "id": i + 1,
                "name": f"Attack {i + 1}",
                "description": f"Description {i + 1}",
                "modifiedDate": "2024-01-01T00:00:00.000Z",
                "publishedDate": "2024-01-01T00:00:00.000Z"
            })
        
        # Test various pages
        result = paginate_attacks(large_dataset, page_number=0, page_size=10)
        assert result['total_pages'] == 3
        assert len(result['attacks_in_page']) == 10
        
        result = paginate_attacks(large_dataset, page_number=2, page_size=10)
        assert len(result['attacks_in_page']) == 5  # Last page