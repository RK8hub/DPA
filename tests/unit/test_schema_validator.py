from __future__ import annotations

from pathlib import Path

from design_pipeline.validators.schema import validate_instance

MINIMAL = {
    "type": "object",
    "required": ["name", "count"],
    "properties": {
        "name": {"type": "string", "pattern": "^[A-Z]"},
        "count": {"type": "integer"},
        "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1},
        "kind": {"enum": ["a", "b"]},
    },
    "additionalProperties": False,
}


def test_valido():
    instance = {"name": "Button", "count": 2, "tags": ["x"], "kind": "a"}
    assert validate_instance(instance, MINIMAL) == []


def test_falta_requerida_y_tipos():
    errors = validate_instance({"name": "Button", "count": "dos"}, MINIMAL)
    assert any("se esperaba integer" in e for e in errors)


def test_pattern_y_enum():
    errors = validate_instance({"name": "button", "count": 1, "kind": "z"}, MINIMAL)
    assert any("patrón" in e for e in errors)
    assert any("enum" in e for e in errors)


def test_additional_properties():
    errors = validate_instance({"name": "X", "count": 1, "extra": True}, MINIMAL)
    assert any("no permitidas" in e for e in errors)


def test_bool_no_es_integer():
    errors = validate_instance({"name": "X", "count": True}, MINIMAL)
    assert errors


def test_items_y_minitems():
    errors = validate_instance({"name": "X", "count": 1, "tags": []}, MINIMAL)
    assert any("al menos" in e for e in errors)
    errors = validate_instance({"name": "X", "count": 1, "tags": [1]}, MINIMAL)
    assert any("se esperaba string" in e for e in errors)


def test_ref_resoluble():
    schema = {
        "$defs": {"item": {"type": "object", "required": ["id"]}},
        "type": "array",
        "items": {"$ref": "#/$defs/item"},
    }
    assert validate_instance([{"id": 1}], schema) == []
    assert validate_instance([{}], schema)
