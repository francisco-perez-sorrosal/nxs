"""Unit tests for argument parsers."""

import pytest
from nxs.application.parsers.key_value import KeyValueArgumentParser
from nxs.application.parsers.positional import PositionalArgumentParser
from nxs.application.parsers.schema_adapter import SchemaAdapter, SchemaInfo
from nxs.application.parsers.composite import CompositeArgumentParser


class TestKeyValueArgumentParser:
    """Tests for KeyValueArgumentParser."""

    def test_parse_simple_key_value(self):
        """Test parsing simple key=value pairs."""
        parser = KeyValueArgumentParser()
        arg_names = ["style", "format"]
        schema_dict = {}

        result = parser.parse("style=bold", arg_names, schema_dict)
        assert result == {"style": "bold"}

    def test_parse_multiple_key_value(self):
        """Test parsing multiple key=value pairs."""
        parser = KeyValueArgumentParser()
        arg_names = ["style", "format", "color"]
        schema_dict = {}

        result = parser.parse('style=bold format="markdown" color=red', arg_names, schema_dict)
        assert result == {"style": "bold", "format": "markdown", "color": "red"}

    def test_parse_quoted_strings(self):
        """Test parsing quoted strings with spaces."""
        parser = KeyValueArgumentParser()
        arg_names = ["style", "message"]
        schema_dict = {}

        result = parser.parse("style=\"very format\" message='single quotes'", arg_names, schema_dict)
        assert result == {"style": "very format", "message": "single quotes"}

    def test_parse_escaped_quotes(self):
        """Test parsing escaped quotes."""
        parser = KeyValueArgumentParser()
        arg_names = ["message"]
        schema_dict = {}

        result = parser.parse('message="value with \\"quotes\\""', arg_names, schema_dict)
        assert result == {"message": 'value with "quotes"'}

    def test_parse_ignores_invalid_keys(self):
        """Test that invalid keys are ignored."""
        parser = KeyValueArgumentParser()
        arg_names = ["style"]
        schema_dict = {}

        result = parser.parse("style=bold invalid=value", arg_names, schema_dict)
        assert result == {"style": "bold"}
        assert "invalid" not in result

    def test_parse_empty_value(self):
        """Test parsing empty value."""
        parser = KeyValueArgumentParser()
        arg_names = ["style"]
        schema_dict = {}

        result = parser.parse("style=", arg_names, schema_dict)
        assert result == {"style": ""}

    def test_parse_no_equals_sign(self):
        """Test that queries without = return empty dict."""
        parser = KeyValueArgumentParser()
        arg_names = ["style"]
        schema_dict = {}

        result = parser.parse("style bold", arg_names, schema_dict)
        assert result == {}

    def test_parse_key_value_pairs_method(self):
        """Test the internal _parse_key_value_pairs method."""
        parser = KeyValueArgumentParser()

        pairs = parser._parse_key_value_pairs('style="very format" key2=value2')
        assert pairs == [("style", "very format"), ("key2", "value2")]

        pairs = parser._parse_key_value_pairs("style='single quotes'")
        assert pairs == [("style", "single quotes")]


class TestPositionalArgumentParser:
    """Tests for PositionalArgumentParser."""

    def test_parse_positional_arguments(self):
        """Test parsing positional arguments."""
        parser = PositionalArgumentParser()
        arg_names = ["arg1", "arg2", "arg3"]
        schema_dict = {}

        result = parser.parse("value1 value2 value3", arg_names, schema_dict)
        assert result == {"arg1": "value1", "arg2": "value2", "arg3": "value3"}

    def test_parse_fewer_values_than_args(self):
        """Test parsing when fewer values than arguments."""
        parser = PositionalArgumentParser()
        arg_names = ["arg1", "arg2", "arg3"]
        schema_dict = {}

        result = parser.parse("value1 value2", arg_names, schema_dict)
        assert result == {"arg1": "value1", "arg2": "value2"}
        assert "arg3" not in result

    def test_parse_single_resource_reference(self):
        """Test parsing single resource reference with @."""
        parser = PositionalArgumentParser()
        arg_names = ["resource"]
        schema_dict = {}

        result = parser.parse("@resource_id", arg_names, schema_dict)
        assert result == {"resource": "resource_id"}

    def test_parse_resource_with_mcp_prefix(self):
        """Test parsing resource with mcp:// prefix."""
        parser = PositionalArgumentParser()
        arg_names = ["resource"]
        schema_dict = {}

        result = parser.parse("@mcp://server/resource_id", arg_names, schema_dict)
        assert result == {"resource": "resource_id"}

    def test_parse_resource_with_server_colon(self):
        """Test parsing resource with server:resource format."""
        parser = PositionalArgumentParser()
        arg_names = ["resource"]
        schema_dict = {}

        result = parser.parse("@server:resource_id", arg_names, schema_dict)
        assert result == {"resource": "resource_id"}

    def test_parse_multiple_with_resource_references(self):
        """Test parsing multiple arguments with resource references."""
        parser = PositionalArgumentParser()
        arg_names = ["arg1", "arg2"]
        schema_dict = {}

        result = parser.parse("@resource1 @resource2", arg_names, schema_dict)
        assert result == {"arg1": "resource1", "arg2": "resource2"}

    def test_parse_quoted_values(self):
        """Test parsing quoted positional values."""
        parser = PositionalArgumentParser()
        arg_names = ["arg1", "arg2"]
        schema_dict = {}

        result = parser.parse('"value 1" "value 2"', arg_names, schema_dict)
        assert result == {"arg1": "value 1", "arg2": "value 2"}

    def test_extract_resource_id_method(self):
        """Test the internal _extract_resource_id method."""
        parser = PositionalArgumentParser()

        assert parser._extract_resource_id("mcp://server/resource_id") == "resource_id"
        assert parser._extract_resource_id("server:resource_id") == "resource_id"
        assert parser._extract_resource_id("resource_id") == "resource_id"


class TestSchemaAdapter:
    """Tests for SchemaAdapter."""

    def test_normalize_dict_schema(self):
        """Test normalizing dict-based schema."""
        adapter = SchemaAdapter()
        schema = {
            "properties": {
                "style": {"type": "string", "default": "bold"},
                "format": {"type": "string", "description": "Output format"},
            },
            "required": ["style"],
        }

        result = adapter.normalize(schema, "test_command")
        assert result is not None
        assert result.arg_names == ["style", "format"]
        assert result.required_args == ["style"]
        assert "style" in result.schema_dict
        assert "format" in result.schema_dict
        assert result.schema_dict["style"]["default"] == "bold"
        assert result.schema_dict["style"]["required"] is True
        assert result.schema_dict["format"]["required"] is False

    def test_normalize_list_schema(self):
        """Test normalizing list-based schema."""
        adapter = SchemaAdapter()
        schema = [{"name": "style", "required": True, "default": "bold"}, {"name": "format", "required": False}]

        result = adapter.normalize(schema, "test_command")
        assert result is not None
        assert result.arg_names == ["style", "format"]
        assert result.required_args == ["style"]
        assert result.schema_dict["style"]["default"] == "bold"
        assert result.schema_dict["style"]["required"] is True

    def test_normalize_object_schema(self):
        """Test normalizing object-based schema."""
        adapter = SchemaAdapter()

        class MockArg:
            def __init__(self, name, required=False, default=None):
                self.name = name
                self.required = required
                self.default = default

        schema = [MockArg("style", required=True, default="bold"), MockArg("format", required=False)]

        result = adapter.normalize(schema, "test_command")
        assert result is not None
        assert result.arg_names == ["style", "format"]
        assert result.required_args == ["style"]
        assert result.schema_dict["style"]["default"] == "bold"

    def test_normalize_empty_schema(self):
        """Test normalizing empty schema."""
        adapter = SchemaAdapter()

        result = adapter.normalize(None, "test_command")
        assert result is None

        result = adapter.normalize({}, "test_command")
        assert result is None

    def test_normalize_pydantic_undefined_default(self):
        """Test that PydanticUndefined defaults are filtered out."""
        adapter = SchemaAdapter()

        class MockArg:
            def __init__(self, name):
                self.name = name
                self.required = False
                self.default = "PydanticUndefined"

        schema = [MockArg("style")]
        result = adapter.normalize(schema, "test_command")
        assert result is not None
        assert result.schema_dict["style"]["default"] is None


class TestCompositeArgumentParser:
    """Tests for CompositeArgumentParser."""

    def test_parse_key_value_format(self):
        """Test that composite parser uses key-value parser for = format."""
        parser = CompositeArgumentParser()
        arg_names = ["style", "format"]
        schema_dict = {}

        result = parser.parse("style=bold format=markdown", arg_names, schema_dict)
        assert result == {"style": "bold", "format": "markdown"}

    def test_parse_positional_format(self):
        """Test that composite parser uses positional parser for space-separated format."""
        parser = CompositeArgumentParser()
        arg_names = ["arg1", "arg2"]
        schema_dict = {}

        result = parser.parse("value1 value2", arg_names, schema_dict)
        assert result == {"arg1": "value1", "arg2": "value2"}

    def test_normalize_schema(self):
        """Test schema normalization."""
        parser = CompositeArgumentParser()
        schema = {"properties": {"style": {"type": "string", "default": "bold"}}, "required": []}

        result = parser.normalize_schema(schema, "test_command")
        assert result is not None
        assert result.arg_names == ["style"]

    def test_apply_defaults(self):
        """Test applying default values."""
        parser = CompositeArgumentParser()
        args = {"style": "custom"}
        schema_dict = {"style": {"default": "bold"}, "format": {"default": "markdown"}}

        result = parser.apply_defaults(args, schema_dict, "test_command")
        assert result["style"] == "custom"  # Should keep existing value
        assert result["format"] == "markdown"  # Should apply default

    def test_validate_arguments_required(self):
        """Test validation of required arguments."""
        parser = CompositeArgumentParser()
        args = {"style": "bold"}
        required_args = ["style", "format"]
        schema_dict = {"style": {}, "format": {}}

        # Should not raise, just log warning
        parser.validate_arguments(args, required_args, schema_dict, "test_command")

    def test_validate_arguments_invalid(self):
        """Test validation of invalid arguments."""
        parser = CompositeArgumentParser()
        args = {"style": "bold", "invalid": "value"}
        required_args = []
        schema_dict = {"style": {}}

        # Should not raise, just log warning
        parser.validate_arguments(args, required_args, schema_dict, "test_command")


class TestIntegration:
    """Integration tests for the full parsing flow."""

    def test_full_parse_flow_key_value(self):
        """Test full parsing flow with key-value format."""
        parser = CompositeArgumentParser()
        schema = {
            "properties": {"style": {"type": "string", "default": "bold"}, "format": {"type": "string"}},
            "required": ["style"],
        }

        schema_info = parser.normalize_schema(schema, "test_command")
        assert schema_info is not None

        args = parser.parse('style=italic format="markdown"', schema_info.arg_names, schema_info.schema_dict)
        args = parser.apply_defaults(args, schema_info.schema_dict, "test_command")
        parser.validate_arguments(args, schema_info.required_args, schema_info.schema_dict, "test_command")

        assert args == {"style": "italic", "format": "markdown"}

    def test_full_parse_flow_positional(self):
        """Test full parsing flow with positional format."""
        parser = CompositeArgumentParser()
        schema = {
            "properties": {"resource": {"type": "string"}, "format": {"type": "string", "default": "markdown"}},
            "required": ["resource"],
        }

        schema_info = parser.normalize_schema(schema, "test_command")
        assert schema_info is not None

        args = parser.parse("@resource_id", schema_info.arg_names, schema_info.schema_dict)
        args = parser.apply_defaults(args, schema_info.schema_dict, "test_command")
        parser.validate_arguments(args, schema_info.required_args, schema_info.schema_dict, "test_command")

        assert args == {"resource": "resource_id", "format": "markdown"}
