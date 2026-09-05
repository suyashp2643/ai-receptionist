import pytest
from app.config import Settings
from app.integrations.field_mapping import (
    FieldMapping,
    FieldMappingError,
    apply_field_mapping,
    preview_field_mapping,
    validate_field_mapping,
)


def _settings(**overrides) -> Settings:
    defaults = {"integration_max_mapping_bytes": 8192, "integration_max_mapping_depth": 4}
    defaults.update(overrides)
    return Settings(**defaults)


class TestApplyFieldMapping:
    def test_identity_mapping_is_a_no_op(self):
        data = {"a": 1, "b": 2}
        assert apply_field_mapping(data, FieldMapping()) == data

    def test_rename_moves_the_value_to_the_new_key(self):
        result = apply_field_mapping({"old": "value"}, FieldMapping(rename={"old": "new"}))
        assert result == {"new": "value"}

    def test_rename_of_a_missing_key_is_a_no_op(self):
        result = apply_field_mapping({"a": 1}, FieldMapping(rename={"missing": "new"}))
        assert result == {"a": 1}

    def test_include_drops_everything_else(self):
        result = apply_field_mapping({"a": 1, "b": 2, "c": 3}, FieldMapping(include=("a", "c")))
        assert result == {"a": 1, "c": 3}

    def test_omit_drops_only_named_keys(self):
        result = apply_field_mapping({"a": 1, "b": 2}, FieldMapping(omit=("b",)))
        assert result == {"a": 1}

    def test_defaults_fill_in_missing_keys_only(self):
        result = apply_field_mapping({"a": 1}, FieldMapping(defaults={"a": 999, "b": 2}))
        assert result == {"a": 1, "b": 2}

    def test_order_is_rename_then_include_then_omit_then_defaults(self):
        mapping = FieldMapping(rename={"old": "kept"}, include=("kept",), omit=(), defaults={"extra": "x"})
        result = apply_field_mapping({"old": "v", "dropped": "y"}, mapping)
        assert result == {"kept": "v", "extra": "x"}

    def test_does_not_mutate_the_input(self):
        data = {"a": 1}
        apply_field_mapping(data, FieldMapping(rename={"a": "b"}))
        assert data == {"a": 1}


class TestValidateFieldMapping:
    def test_empty_mapping_is_the_identity(self):
        assert validate_field_mapping(None, settings=_settings()) == FieldMapping()
        assert validate_field_mapping({}, settings=_settings()) == FieldMapping()

    def test_unknown_top_level_key_is_rejected(self):
        with pytest.raises(FieldMappingError, match="unrecognized keys"):
            validate_field_mapping({"transform_code": "eval(x)"}, settings=_settings())

    def test_rename_must_be_string_to_string(self):
        with pytest.raises(FieldMappingError):
            validate_field_mapping({"rename": {"a": 5}}, settings=_settings())

    def test_include_must_be_a_list_of_strings(self):
        with pytest.raises(FieldMappingError):
            validate_field_mapping({"include": "not-a-list"}, settings=_settings())

    def test_omit_must_be_a_list_of_strings(self):
        with pytest.raises(FieldMappingError):
            validate_field_mapping({"omit": [1, 2]}, settings=_settings())

    def test_defaults_must_be_an_object(self):
        with pytest.raises(FieldMappingError):
            validate_field_mapping({"defaults": "not-an-object"}, settings=_settings())

    def test_oversized_mapping_is_rejected(self):
        huge = {"defaults": {"blob": "x" * 100}}
        with pytest.raises(FieldMappingError, match="bytes"):
            validate_field_mapping(huge, settings=_settings(integration_max_mapping_bytes=50))

    def test_too_deeply_nested_defaults_are_rejected(self):
        nested = {"defaults": {"a": {"b": {"c": {"d": {"e": "too deep"}}}}}}
        with pytest.raises(FieldMappingError, match="nest"):
            validate_field_mapping(nested, settings=_settings(integration_max_mapping_depth=2))

    def test_valid_mapping_round_trips(self):
        raw = {"rename": {"old": "new"}, "include": ["new", "b"], "omit": ["b"], "defaults": {"c": 1}}
        mapping = validate_field_mapping(raw, settings=_settings())
        assert mapping.rename == {"old": "new"}
        assert mapping.include == ("new", "b")
        assert mapping.omit == ("b",)
        assert mapping.defaults == {"c": 1}


class TestPreview:
    def test_preview_applies_the_mapping_to_sample_data(self):
        result = preview_field_mapping(
            {"phone": "555-1234", "internal_id": "abc"},
            {"rename": {"phone": "phone_number"}, "omit": ["internal_id"]},
            settings=_settings(),
        )
        assert result == {"phone_number": "555-1234"}
