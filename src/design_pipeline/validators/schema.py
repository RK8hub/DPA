"""Validador de esquemas JSON (subconjunto) sin dependencias externas.

Implementa el subconjunto de JSON Schema que usa este proyecto: ``type``,
``enum``, ``required``, ``properties``, ``items``, ``additionalProperties``,
``minItems``, ``pattern`` y ``$ref`` a esquemas cargados por nombre. Es
suficiente para validar los manifiestos del pipeline y evita la dependencia
``jsonschema``; los esquemas publicados en ``schemas/`` siguen siendo JSON
Schema estándar para consumo externo.
"""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_TYPE_MAP = {
    "object": dict,
    "array": list,
    "string": str,
    "integer": int,
    "number": (int, float),
    "boolean": bool,
    "null": type(None),
}


def _type_ok(value: Any, expected: str) -> bool:
    python_type = _TYPE_MAP.get(expected)
    if python_type is None:  # pragma: no cover - esquemas propios no usan otros tipos
        return True
    if expected == "integer" and isinstance(value, bool):
        return False  # bool no es integer en JSON Schema
    if expected == "number" and isinstance(value, bool):
        return False
    return isinstance(value, python_type)


def validate_instance(
    instance: Any, schema: dict[str, Any], path: str = "$", root: dict[str, Any] | None = None
) -> list[str]:
    """Valida ``instance`` contra ``schema``. Devuelve lista de errores (vacía si es válido)."""
    root = root if root is not None else schema
    errors: list[str] = []

    if "$ref" in schema:
        ref = schema["$ref"]
        match = re.fullmatch(r"#/(.+)", ref)
        if not match:
            return [f"{path}: $ref no soportado ({ref})"]
        target: Any = root
        for part in match.group(1).split("/"):
            if not isinstance(target, dict) or part not in target:
                return [f"{path}: $ref irresoluble ({ref})"]
            target = target[part]
        return validate_instance(instance, target, path, root)

    expected = schema.get("type")
    if expected is not None:
        types = expected if isinstance(expected, list) else [expected]
        if not any(_type_ok(instance, t) for t in types):
            errors.append(f"{path}: se esperaba {expected}, llegó {type(instance).__name__}")
            return errors  # sin tipo correcto no tiene sentido seguir

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(f"{path}: valor {instance!r} fuera del enum {schema['enum']}")

    if "pattern" in schema and isinstance(instance, str):
        if not re.search(schema["pattern"], instance):
            errors.append(f"{path}: {instance!r} no cumple el patrón {schema['pattern']!r}")

    if isinstance(instance, dict):
        for required in schema.get("required", []):
            if required not in instance:
                errors.append(f"{path}: falta la clave requerida '{required}'")
        properties = schema.get("properties", {})
        for key, subschema in properties.items():
            if key in instance:
                errors.extend(validate_instance(instance[key], subschema, f"{path}.{key}", root))
        if schema.get("additionalProperties") is False:
            extras = [key for key in instance if key not in properties]
            if extras:
                errors.append(f"{path}: claves no permitidas: {extras}")

    if isinstance(instance, list):
        if "minItems" in schema and len(instance) < schema["minItems"]:
            errors.append(f"{path}: se esperaban al menos {schema['minItems']} items")
        item_schema = schema.get("items")
        if item_schema:
            for index, item in enumerate(instance):
                errors.extend(validate_instance(item, item_schema, f"{path}[{index}]", root))

    return errors


def load_schema(schemas_dir: Path, name: str) -> dict[str, Any]:
    path = schemas_dir / name
    if not path.exists():
        raise FileNotFoundError(f"No existe el esquema: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def package_schemas_dir() -> Path:
    from importlib import resources

    return Path(resources.files("design_pipeline").joinpath("data/schemas").as_posix())


def validate_against(schemas_dir: Path, schema_name: str, instance: Any) -> list[str]:
    schema = load_schema(schemas_dir, schema_name)
    return validate_instance(instance, schema)
