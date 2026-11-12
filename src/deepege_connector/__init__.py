"""Deepege connector: MCP server for the Deepege Open API.

Tool implementations will be added in a later work package. This package
currently ships shared models, configuration, and a server entry placeholder.
"""

from deepege_connector.models import ErrorCode, JobStatus, Principal

__version__ = "0.1.0"

__all__ = ["ErrorCode", "JobStatus", "Principal", "__version__"]
