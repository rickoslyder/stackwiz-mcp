"""
MCP Resources for StackWiz
"""

from .stack_configs import StackConfigsResource
from .templates import TemplatesResource
from .infrastructure import InfrastructureResource

__all__ = [
    "StackConfigsResource",
    "TemplatesResource",
    "InfrastructureResource"
]