"""
Helpers for working with prompt schemas in autocomplete flows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable, Iterator

from nxs.tui.services.prompt_service import PromptService


@dataclass(slots=True)
class ArgumentDescriptor:
    """Structured representation of a prompt argument."""

    name: str
    default: Any | None
    required: bool
    description: str


def _validate_default(default: Any | None) -> Any | None:
    if default is None:
        return None

    default_str = str(default)
    if "Undefined" in default_str or "PydanticUndefined" in default_str:
        return None
    if "class" in default_str.lower() and "<" in default_str:
        return None
    return default


def _iter_dict_schema(schema: dict) -> Iterator[ArgumentDescriptor]:
    properties = schema.get("properties", {})
    required_args = set(schema.get("required", []))

    for arg_name, arg_spec in properties.items():
        default = None
        description = ""

        if isinstance(arg_spec, dict):
            default = arg_spec.get("default")
            description = arg_spec.get("description", "")
        else:
            default = getattr(arg_spec, "default", None) if hasattr(arg_spec, "default") else None
            description = getattr(arg_spec, "description", "") if hasattr(arg_spec, "description") else ""

        yield ArgumentDescriptor(
            name=arg_name,
            default=_validate_default(default),
            required=arg_name in required_args,
            description=description,
        )


def _iter_list_schema(schema: list) -> Iterator[ArgumentDescriptor]:
    required_set = set()
    for arg in schema:
        if isinstance(arg, dict):
            if arg.get("name") and arg.get("required", False):
                required_set.add(arg["name"])
        elif hasattr(arg, "name") and getattr(arg, "required", False):
            required_set.add(arg.name)

    for arg in schema:
        name = None
        default = None
        description = ""

        if isinstance(arg, dict):
            name = arg.get("name")
            default = arg.get("default")
            description = arg.get("description", "")
        elif hasattr(arg, "name"):
            name = arg.name
            description = getattr(arg, "description", "") if hasattr(arg, "description") else ""
            default = _extract_default_from_object(arg)

        if not name:
            continue

        yield ArgumentDescriptor(
            name=name,
            default=_validate_default(default),
            required=name in required_set,
            description=description,
        )


def _extract_default_from_object(obj: Any) -> Any | None:
    for attr in ("default", "default_value"):
        if hasattr(obj, attr):
            try:
                return getattr(obj, attr)
            except Exception:
                return None

    for method in ("model_dump", "dict"):
        if hasattr(obj, method):
            try:
                dumped = getattr(obj, method)(exclude_unset=False, exclude_none=False)
                if isinstance(dumped, dict):
                    return dumped.get("default")
            except Exception:
                return None

    if hasattr(obj, "__dict__"):
        return obj.__dict__.get("default")

    return None


def iterate_arguments(schema: Any) -> Iterable[ArgumentDescriptor]:
    if isinstance(schema, dict):
        return tuple(_iter_dict_schema(schema))
    if isinstance(schema, list):
        return tuple(_iter_list_schema(schema))
    if hasattr(schema, "properties") or hasattr(schema, "required"):
        properties = getattr(schema, "properties", {})
        required = getattr(schema, "required", [])
        if isinstance(properties, dict):
            return tuple(_iter_dict_schema({"properties": properties, "required": required}))
    return ()


def get_command_arguments_with_defaults(
    prompt_service: PromptService, command_name: str
) -> str | None:
    schema_tuple = prompt_service.get_cached_schema(command_name)
    if schema_tuple is None:
        return None

    prompt, _ = schema_tuple
    if not hasattr(prompt, "arguments") or not prompt.arguments:
        return None

    descriptors = iterate_arguments(prompt.arguments)
    parts: list[str] = []
    for descriptor in descriptors:
        if descriptor.default is not None:
            parts.append(f"{descriptor.name}={descriptor.default}")
        elif descriptor.required:
            parts.append(f"{descriptor.name}*")
        else:
            parts.append(f"{descriptor.name}?")

    if parts:
        return ", ".join(parts)
    return None


def expand_command_with_arguments(
    prompt_service: PromptService, command_name: str
) -> str:
    schema_tuple = prompt_service.get_cached_schema(command_name)
    if schema_tuple is None:
        return command_name

    prompt, _ = schema_tuple
    if not hasattr(prompt, "arguments") or not prompt.arguments:
        return command_name

    descriptors = iterate_arguments(prompt.arguments)
    parts: list[str] = []
    for descriptor in descriptors:
        if descriptor.default is not None:
            parts.append(f"{descriptor.name}={descriptor.default}")
        elif descriptor.required:
            parts.append(f"{descriptor.name}=<required>")

    if parts:
        return f"{command_name} {' '.join(parts)}"

    return command_name

