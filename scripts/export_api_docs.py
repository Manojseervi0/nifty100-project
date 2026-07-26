from __future__ import annotations

import copy
import json
import re
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DOCS_DIR = PROJECT_ROOT / "docs"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.api.main import app  # noqa: E402


OPENAPI_OUTPUT = DOCS_DIR / "openapi.json"
POSTMAN_OUTPUT = DOCS_DIR / "nifty100_api.postman_collection.json"

EXPECTED_API_ENDPOINTS = 16
HTTP_METHODS = {
    "get",
    "post",
    "put",
    "patch",
    "delete",
    "options",
    "head",
}

VARIABLE_DEFAULTS = {
    "ticker": "TCS",
    "sector": "Information Technology",
    "group_name": "IT Services",
}

QUERY_EXAMPLES = {
    "sector": "Information Technology",
    "market_cap_category": "Large Cap",
    "search": "TCS",
    "from_year": "2019-03",
    "to_year": "2024-03",
    "year": "Mar 2024",
    "min_roe": "15",
    "max_de": "1",
    "min_fcf": "0",
    "min_rev_cagr_5yr": "10",
    "min_pat_cagr_5yr": "10",
    "max_pe": "30",
}


def _slug_to_title(value: str) -> str:
    """Convert an operation identifier into a readable request title."""

    cleaned = re.sub(r"[_\-]+", " ", value).strip()
    return cleaned.title() or "API Request"


def _convert_nullable_any_of(node: dict[str, Any]) -> dict[str, Any]:
    """Convert JSON Schema nullable anyOf syntax to OpenAPI 3.0 syntax."""

    any_of = node.get("anyOf")

    if not isinstance(any_of, list):
        return node

    non_null = [
        item
        for item in any_of
        if not (isinstance(item, dict) and item.get("type") == "null")
    ]

    has_null = len(non_null) != len(any_of)

    if not has_null:
        return node

    node = dict(node)
    node.pop("anyOf", None)
    node["nullable"] = True

    if len(non_null) == 1 and isinstance(non_null[0], dict):
        replacement = dict(non_null[0])
        replacement.update(node)
        node = replacement
    elif non_null:
        node["anyOf"] = non_null

    return node


def _to_openapi_30(value: Any) -> Any:
    """Recursively convert common OpenAPI 3.1 schema constructs to 3.0."""

    if isinstance(value, list):
        return [_to_openapi_30(item) for item in value]

    if not isinstance(value, dict):
        return value

    node = {
        key: _to_openapi_30(item)
        for key, item in value.items()
        if key not in {"jsonSchemaDialect", "$schema"}
    }

    node = _convert_nullable_any_of(node)

    if "const" in node:
        node["enum"] = [node.pop("const")]

    schema_type = node.get("type")

    if isinstance(schema_type, list) and "null" in schema_type:
        remaining_types = [
            item for item in schema_type if item != "null"
        ]
        node["nullable"] = True

        if len(remaining_types) == 1:
            node["type"] = remaining_types[0]
        elif remaining_types:
            node["type"] = remaining_types
        else:
            node.pop("type", None)

    exclusive_minimum = node.get("exclusiveMinimum")

    if isinstance(exclusive_minimum, (int, float)) and not isinstance(
        exclusive_minimum,
        bool,
    ):
        node["minimum"] = exclusive_minimum
        node["exclusiveMinimum"] = True

    exclusive_maximum = node.get("exclusiveMaximum")

    if isinstance(exclusive_maximum, (int, float)) and not isinstance(
        exclusive_maximum,
        bool,
    ):
        node["maximum"] = exclusive_maximum
        node["exclusiveMaximum"] = True

    return node


def build_openapi_spec() -> dict[str, Any]:
    """Return an OpenAPI 3.0-compatible specification for the FastAPI app."""

    schema = copy.deepcopy(app.openapi())
    schema = _to_openapi_30(schema)
    schema["openapi"] = "3.0.3"

    info = schema.setdefault("info", {})
    info.setdefault("title", "Nifty100 Analytics API")
    info.setdefault("version", "1.0.0")
    info.setdefault(
        "description",
        (
            "REST API for Nifty100 company profiles, financial histories, "
            "screening, sectors, peers, valuation, portfolio statistics, "
            "annual-report links, and PDF tearsheets."
        ),
    )

    schema["servers"] = [
        {
            "url": "http://127.0.0.1:8000",
            "description": "Local development server",
        }
    ]

    return schema


def get_api_operations(
    schema: dict[str, Any],
) -> list[tuple[str, str, dict[str, Any]]]:
    """Return all versioned API operations, excluding the root endpoint."""

    operations: list[tuple[str, str, dict[str, Any]]] = []

    for path, path_item in schema.get("paths", {}).items():
        if not path.startswith("/api/v1/"):
            continue

        if not isinstance(path_item, dict):
            continue

        for method, operation in path_item.items():
            if method.lower() not in HTTP_METHODS:
                continue

            if not isinstance(operation, dict):
                continue

            operations.append((path, method.upper(), operation))

    operations.sort(key=lambda item: (item[0], item[1]))
    return operations


def _path_to_postman(path: str) -> str:
    """Replace OpenAPI path parameters with Postman variables."""

    return re.sub(
        r"\{([^{}]+)\}",
        lambda match: "{{" + match.group(1) + "}}",
        path,
    )


def _parameter_value(parameter: dict[str, Any]) -> str:
    """Choose a readable default value for a Postman parameter."""

    name = str(parameter.get("name", "")).strip()
    schema = parameter.get("schema", {})

    if name in QUERY_EXAMPLES:
        return QUERY_EXAMPLES[name]

    if isinstance(schema, dict):
        if schema.get("example") is not None:
            return str(schema["example"])

        if schema.get("default") is not None:
            return str(schema["default"])

        enum_values = schema.get("enum")

        if isinstance(enum_values, list) and enum_values:
            return str(enum_values[0])

        schema_type = schema.get("type")

        if schema_type in {"integer", "number"}:
            return "1"

        if schema_type == "boolean":
            return "true"

    return "value"


def _request_name(
    method: str,
    path: str,
    operation: dict[str, Any],
) -> str:
    """Build a concise Postman request name."""

    summary = operation.get("summary")

    if isinstance(summary, str) and summary.strip():
        return summary.strip()

    operation_id = operation.get("operationId")

    if isinstance(operation_id, str) and operation_id.strip():
        return _slug_to_title(operation_id)

    return f"{method} {path}"


def _build_request(
    method: str,
    path: str,
    operation: dict[str, Any],
) -> dict[str, Any]:
    """Convert one OpenAPI operation into a Postman request item."""

    postman_path = _path_to_postman(path)
    raw_url = "{{base_url}}" + postman_path

    query_parameters: list[dict[str, Any]] = []

    for parameter in operation.get("parameters", []):
        if not isinstance(parameter, dict):
            continue

        if parameter.get("in") != "query":
            continue

        query_parameters.append(
            {
                "key": str(parameter.get("name", "")),
                "value": _parameter_value(parameter),
                "description": str(parameter.get("description", "") or ""),
                "disabled": True,
            }
        )

    url: dict[str, Any] = {
        "raw": raw_url,
        "host": ["{{base_url}}"],
        "path": [
            segment
            for segment in postman_path.strip("/").split("/")
            if segment
        ],
    }

    if query_parameters:
        url["query"] = query_parameters

    description = operation.get("description") or operation.get("summary") or ""

    return {
        "name": _request_name(method, path, operation),
        "request": {
            "method": method,
            "header": [
                {
                    "key": "Accept",
                    "value": "application/json",
                    "type": "text",
                }
            ],
            "url": url,
            "description": str(description),
        },
        "response": [],
    }


def build_postman_collection(
    schema: dict[str, Any],
) -> dict[str, Any]:
    """Build a Postman Collection v2.1 document from the OpenAPI paths."""

    folders: dict[str, list[dict[str, Any]]] = defaultdict(list)

    for path, method, operation in get_api_operations(schema):
        tags = operation.get("tags", ["Other"])
        tag = str(tags[0]) if tags else "Other"

        folders[tag].append(
            _build_request(method, path, operation)
        )

    folder_order = [
        "Health",
        "Companies",
        "Screener",
        "Sectors",
        "Peers",
        "Valuation",
        "Portfolio",
        "Documents",
    ]

    ordered_tags = [
        tag for tag in folder_order if tag in folders
    ] + sorted(tag for tag in folders if tag not in folder_order)

    collection_items = [
        {
            "name": tag,
            "item": folders[tag],
        }
        for tag in ordered_tags
    ]

    return {
        "info": {
            "_postman_id": "nifty100-analytics-api-v1",
            "name": "Nifty100 Analytics API",
            "description": (
                "Postman collection generated from the FastAPI OpenAPI "
                "specification. Optional query parameters are included but "
                "disabled by default."
            ),
            "schema": (
                "https://schema.getpostman.com/json/"
                "collection/v2.1.0/collection.json"
            ),
        },
        "variable": [
            {
                "key": "base_url",
                "value": "http://127.0.0.1:8000",
                "type": "string",
            },
            *[
                {
                    "key": key,
                    "value": value,
                    "type": "string",
                }
                for key, value in VARIABLE_DEFAULTS.items()
            ],
        ],
        "item": collection_items,
    }


def validate_outputs(
    openapi_schema: dict[str, Any],
    postman_collection: dict[str, Any],
) -> int:
    """Validate endpoint and Postman-request counts before writing files."""

    operations = get_api_operations(openapi_schema)
    operation_count = len(operations)

    postman_request_count = sum(
        len(folder.get("item", []))
        for folder in postman_collection.get("item", [])
    )

    if operation_count != EXPECTED_API_ENDPOINTS:
        discovered = "\n".join(
            f"  {method} {path}"
            for path, method, _ in operations
        )

        raise RuntimeError(
            "\n".join(
                [
                    (
                        f"Expected {EXPECTED_API_ENDPOINTS} API endpoints, "
                        f"but found {operation_count}."
                    ),
                    "Check router imports and include_router() calls in main.py.",
                    "Discovered endpoints:",
                    discovered or "  None",
                ]
            )
        )

    if postman_request_count != operation_count:
        raise RuntimeError(
            (
                "Postman request count does not match OpenAPI operation "
                f"count: {postman_request_count} != {operation_count}"
            )
        )

    return operation_count


def write_json(path: Path, data: dict[str, Any]) -> None:
    """Write formatted UTF-8 JSON to a file."""

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def main() -> None:
    """Export and validate OpenAPI and Postman documentation."""

    DOCS_DIR.mkdir(parents=True, exist_ok=True)

    openapi_schema = build_openapi_spec()
    postman_collection = build_postman_collection(openapi_schema)
    endpoint_count = validate_outputs(
        openapi_schema,
        postman_collection,
    )

    write_json(OPENAPI_OUTPUT, openapi_schema)
    write_json(POSTMAN_OUTPUT, postman_collection)

    print("=" * 68)
    print("NIFTY100 API DOCUMENTATION EXPORT")
    print("=" * 68)
    print(f"API endpoints verified : {endpoint_count}")
    print(f"OpenAPI version        : {openapi_schema['openapi']}")
    print(f"OpenAPI output         : {OPENAPI_OUTPUT.relative_to(PROJECT_ROOT)}")
    print(f"Postman output         : {POSTMAN_OUTPUT.relative_to(PROJECT_ROOT)}")
    print("Status                 : PASS")
    print("=" * 68)


if __name__ == "__main__":
    main()