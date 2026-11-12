"""Helpers for validating responses against openapi/open-v1.yaml."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from referencing import Registry, Resource
from referencing.jsonschema import DRAFT202012

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_PATH = REPO_ROOT / "openapi" / "open-v1.yaml"


@lru_cache(maxsize=1)
def load_spec() -> dict[str, Any]:
    with SPEC_PATH.open(encoding="utf-8") as handle:
        spec = yaml.safe_load(handle)
    if not isinstance(spec, dict):
        raise TypeError(f"{SPEC_PATH} is not a mapping")
    return spec


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resource = Resource(contents=load_spec(), specification=DRAFT202012)
    return Registry().with_resource("urn:deepege:open-v1", resource)


def validate_schema(schema_name: str, data: Any) -> None:
    """Raise jsonschema.ValidationError if data does not match the named component schema."""
    schema = {"$ref": f"urn:deepege:open-v1#/components/schemas/{schema_name}"}
    validator = Draft202012Validator(schema, registry=_registry(), format_checker=FormatChecker())
    validator.validate(data)


def schema_names() -> list[str]:
    return sorted(load_spec()["components"]["schemas"].keys())
