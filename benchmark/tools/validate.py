#!/usr/bin/env python3
"""Validate every Steph Speak Bench case against data/v1/schema.json, standard library only.

    python3 benchmark/tools/validate.py

Implements the JSON Schema subset the case schema uses: type, enum, const, pattern,
minLength, minimum, maximum, minItems, items, required, properties,
additionalProperties, allOf, if/then.

SPDX-License-Identifier: MIT
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list,
         "object": dict, "null": type(None)}


def type_ok(value, name: str) -> bool:
    if name in ("integer", "number") and isinstance(value, bool):
        return False
    return isinstance(value, TYPES[name])


def validate(value, schema: dict, path: str = "$") -> list:
    errors = []
    if "type" in schema:
        names = schema["type"] if isinstance(schema["type"], list) else [schema["type"]]
        if not any(type_ok(value, n) for n in names):
            return [f"{path}: expected {'/'.join(names)}, got {type(value).__name__}"]
    if "enum" in schema and value not in schema["enum"]:
        errors.append(f"{path}: {value!r} not in {schema['enum']}")
    if "const" in schema and value != schema["const"]:
        errors.append(f"{path}: {value!r} != {schema['const']!r}")
    if isinstance(value, str):
        if len(value) < schema.get("minLength", 0):
            errors.append(f"{path}: shorter than {schema['minLength']}")
        if "pattern" in schema and not re.search(schema["pattern"], value):
            errors.append(f"{path}: does not match {schema['pattern']}")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            errors.append(f"{path}: below {schema['minimum']}")
        if "maximum" in schema and value > schema["maximum"]:
            errors.append(f"{path}: above {schema['maximum']}")
    if isinstance(value, list):
        if len(value) < schema.get("minItems", 0):
            errors.append(f"{path}: fewer than {schema['minItems']} items")
        if "items" in schema:
            for i, item in enumerate(value):
                errors += validate(item, schema["items"], f"{path}[{i}]")
    if isinstance(value, dict):
        for key in schema.get("required", []):
            if key not in value:
                errors.append(f"{path}: missing required property '{key}'")
        props = schema.get("properties", {})
        for key, item in value.items():
            if key in props:
                errors += validate(item, props[key], f"{path}.{key}")
            elif schema.get("additionalProperties") is False:
                errors.append(f"{path}: unexpected property '{key}'")
    for sub in schema.get("allOf", []):
        if "if" in sub:
            if not validate(value, sub["if"], path):
                errors += validate(value, sub.get("then", {}), path)
        else:
            errors += validate(value, sub, path)
    return errors


def main() -> int:
    data = Path(__file__).resolve().parents[1] / "data" / "v1"
    schema = json.loads((data / "schema.json").read_text(encoding="utf-8"))
    bad = 0
    for path in sorted(data.glob("*/*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for err in validate(json.loads(line), schema):
                bad += 1
                print(f"{path.relative_to(data)}:{n}: {err}")
    print("valid" if not bad else f"{bad} error(s)")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
