"""MCP server entry placeholder.

Tools, Streamable HTTP, and the resource-server role are implemented in a
later work package. This module exists so the package has a stable console
script and ``python -m deepege_connector`` entry point.
"""

from __future__ import annotations


def main() -> None:
    raise SystemExit(
        "The Deepege MCP server is not implemented yet. "
        "This package currently provides shared models, configuration, "
        "and a mock Open API service for local development "
        "(see: python -m tests.mock_core)."
    )


if __name__ == "__main__":
    main()
