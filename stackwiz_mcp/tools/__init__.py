"""
Stackwiz MCP Tools - Docker stack management tools.

This module exports all available tools for the MCP server.
"""

# Import tool classes
from .create_stack import CreateStackTool
from .list_stacks import ListStacksTool
from .manage_stack import ManageStackTool
from .dns_operations import CreateDnsRecordTool, ListDnsRecordsTool, UpdateDnsProxyTool
from .validate_config import ValidateStackConfigTool

# Export all tool classes
__all__ = [
    "CreateStackTool",
    "ListStacksTool",
    "ManageStackTool",
    "CreateDnsRecordTool",
    "ListDnsRecordsTool",
    "UpdateDnsProxyTool",
    "ValidateStackConfigTool"
]

# Tool registry for easy access
TOOLS = {
    "CreateStackTool": CreateStackTool,
    "ListStacksTool": ListStacksTool,
    "ManageStackTool": ManageStackTool,
    "CreateDnsRecordTool": CreateDnsRecordTool,
    "ListDnsRecordsTool": ListDnsRecordsTool,
    "UpdateDnsProxyTool": UpdateDnsProxyTool,
    "ValidateStackConfigTool": ValidateStackConfigTool
}