"""
MCP Prompts for StackWiz
"""

from .deployment_prompts import (
    DeployWebAppPrompt,
    SetupDatabasePrompt,
    CreateApiServicePrompt
)

__all__ = [
    "DeployWebAppPrompt",
    "SetupDatabasePrompt",
    "CreateApiServicePrompt"
]