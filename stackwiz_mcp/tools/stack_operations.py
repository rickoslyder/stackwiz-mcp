"""
Stack operations: start, stop, restart, remove, and logs.

This tool provides functionality to:
- Start a stopped stack
- Stop a running stack
- Restart a stack
- Remove a stack (with optional volume removal)
- View stack logs
"""

import os
import shutil
from typing import Dict, Any, Optional

from ..models.stack_models import StackOperationParams, StackLogsParams, StackOperationResult
from ..utils.stack_utils import (
    get_stack_path, stack_exists, run_docker_compose,
    get_stack_status, SYSTEM_STACKS
)


def start_stack(params: StackOperationParams) -> StackOperationResult:
    """
    Start a Docker stack.
    
    Args:
        params: Operation parameters
        
    Returns:
        StackOperationResult
    """
    stack_name = params.name
    
    # Validate stack exists
    if not stack_exists(stack_name):
        return StackOperationResult(
            success=False,
            message=f"Stack '{stack_name}' does not exist",
            error="Stack not found"
        )
    
    # Check current status
    status = get_stack_status(stack_name)
    if status == "running":
        return StackOperationResult(
            success=True,
            message=f"Stack '{stack_name}' is already running",
            details={"status": status}
        )
    
    # Start the stack
    stack_path = get_stack_path(stack_name)
    success, stdout, stderr = run_docker_compose(stack_path, ["up", "-d"])
    
    if success:
        # Get new status
        new_status = get_stack_status(stack_name)
        return StackOperationResult(
            success=True,
            message=f"Stack '{stack_name}' started successfully",
            details={
                "previous_status": status,
                "current_status": new_status,
                "output": stdout
            }
        )
    else:
        return StackOperationResult(
            success=False,
            message=f"Failed to start stack '{stack_name}'",
            error=stderr or "Unknown error",
            details={"output": stdout}
        )


def stop_stack(params: StackOperationParams) -> StackOperationResult:
    """
    Stop a Docker stack.
    
    Args:
        params: Operation parameters
        
    Returns:
        StackOperationResult
    """
    stack_name = params.name
    
    # Validate stack exists
    if not stack_exists(stack_name):
        return StackOperationResult(
            success=False,
            message=f"Stack '{stack_name}' does not exist",
            error="Stack not found"
        )
    
    # Check current status
    status = get_stack_status(stack_name)
    if status == "stopped":
        return StackOperationResult(
            success=True,
            message=f"Stack '{stack_name}' is already stopped",
            details={"status": status}
        )
    
    # Stop the stack
    stack_path = get_stack_path(stack_name)
    success, stdout, stderr = run_docker_compose(stack_path, ["down"])
    
    if success:
        # Get new status
        new_status = get_stack_status(stack_name)
        return StackOperationResult(
            success=True,
            message=f"Stack '{stack_name}' stopped successfully",
            details={
                "previous_status": status,
                "current_status": new_status,
                "output": stdout
            }
        )
    else:
        return StackOperationResult(
            success=False,
            message=f"Failed to stop stack '{stack_name}'",
            error=stderr or "Unknown error",
            details={"output": stdout}
        )


def restart_stack(params: StackOperationParams) -> StackOperationResult:
    """
    Restart a Docker stack.
    
    Args:
        params: Operation parameters
        
    Returns:
        StackOperationResult
    """
    stack_name = params.name
    
    # Validate stack exists
    if not stack_exists(stack_name):
        return StackOperationResult(
            success=False,
            message=f"Stack '{stack_name}' does not exist",
            error="Stack not found"
        )
    
    # Get current status
    status = get_stack_status(stack_name)
    
    # Restart the stack
    stack_path = get_stack_path(stack_name)
    success, stdout, stderr = run_docker_compose(stack_path, ["restart"])
    
    if success:
        # Get new status
        new_status = get_stack_status(stack_name)
        return StackOperationResult(
            success=True,
            message=f"Stack '{stack_name}' restarted successfully",
            details={
                "previous_status": status,
                "current_status": new_status,
                "output": stdout
            }
        )
    else:
        return StackOperationResult(
            success=False,
            message=f"Failed to restart stack '{stack_name}'",
            error=stderr or "Unknown error",
            details={"output": stdout}
        )


def remove_stack(params: StackOperationParams) -> StackOperationResult:
    """
    Remove a Docker stack.
    
    Args:
        params: Operation parameters (force=True will remove volumes)
        
    Returns:
        StackOperationResult
    """
    stack_name = params.name
    
    # Validate stack exists
    if not stack_exists(stack_name):
        return StackOperationResult(
            success=False,
            message=f"Stack '{stack_name}' does not exist",
            error="Stack not found"
        )
    
    # Prevent removal of system stacks
    if stack_name in SYSTEM_STACKS and not params.force:
        return StackOperationResult(
            success=False,
            message=f"Cannot remove system stack '{stack_name}' without force flag",
            error="Protected system stack"
        )
    
    stack_path = get_stack_path(stack_name)
    
    # First, stop the stack if running
    status = get_stack_status(stack_name)
    if status == "running":
        # Stop with volume removal if force is set
        cmd = ["down"]
        if params.force:
            cmd.append("-v")  # Remove volumes
        
        success, stdout, stderr = run_docker_compose(stack_path, cmd)
        if not success:
            return StackOperationResult(
                success=False,
                message=f"Failed to stop stack '{stack_name}' before removal",
                error=stderr or "Unknown error"
            )
    
    # Remove the stack directory
    try:
        shutil.rmtree(stack_path)
        return StackOperationResult(
            success=True,
            message=f"Stack '{stack_name}' removed successfully",
            details={
                "removed_path": stack_path,
                "volumes_removed": params.force
            }
        )
    except Exception as e:
        return StackOperationResult(
            success=False,
            message=f"Failed to remove stack directory",
            error=str(e)
        )


def get_stack_logs(params: StackLogsParams) -> StackOperationResult:
    """
    Get logs from a Docker stack.
    
    Args:
        params: Log parameters
        
    Returns:
        StackOperationResult with logs in details
    """
    stack_name = params.name
    
    # Validate stack exists
    if not stack_exists(stack_name):
        return StackOperationResult(
            success=False,
            message=f"Stack '{stack_name}' does not exist",
            error="Stack not found"
        )
    
    # Build command
    cmd = ["logs", f"--tail={params.lines}"]
    
    if params.service:
        cmd.append(params.service)
    
    # Note: follow is not supported in this context as it would block
    if params.follow:
        return StackOperationResult(
            success=False,
            message="Follow mode is not supported in this context",
            error="Unsupported operation"
        )
    
    # Get logs
    stack_path = get_stack_path(stack_name)
    success, stdout, stderr = run_docker_compose(stack_path, cmd)
    
    if success:
        # Split logs into lines for easier processing
        log_lines = stdout.splitlines()
        
        return StackOperationResult(
            success=True,
            message=f"Retrieved {len(log_lines)} log lines from '{stack_name}'",
            details={
                "logs": stdout,
                "log_lines": log_lines,
                "line_count": len(log_lines),
                "service": params.service,
                "tail": params.lines
            }
        )
    else:
        return StackOperationResult(
            success=False,
            message=f"Failed to get logs from stack '{stack_name}'",
            error=stderr or "Unknown error"
        )


# Tool definitions for the MCP server
start_tool_definition = {
    "name": "start_stack",
    "description": "Start a stopped Docker stack",
    "input_schema": StackOperationParams.model_json_schema(),
    "handler": start_stack
}

stop_tool_definition = {
    "name": "stop_stack",
    "description": "Stop a running Docker stack",
    "input_schema": StackOperationParams.model_json_schema(),
    "handler": stop_stack
}

restart_tool_definition = {
    "name": "restart_stack",
    "description": "Restart a Docker stack",
    "input_schema": StackOperationParams.model_json_schema(),
    "handler": restart_stack
}

remove_tool_definition = {
    "name": "remove_stack",
    "description": "Remove a Docker stack (use force=true to remove volumes)",
    "input_schema": StackOperationParams.model_json_schema(),
    "handler": remove_stack
}

logs_tool_definition = {
    "name": "get_stack_logs",
    "description": "Get logs from a Docker stack",
    "input_schema": StackLogsParams.model_json_schema(),
    "handler": get_stack_logs
}