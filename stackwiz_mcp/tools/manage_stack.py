"""
Manage Stack Tool - Performs operations on existing stacks
"""

from typing import Dict, Any
from ..utils.logging import get_logger
from ..models.stack_models import (
    StackOperationParams, 
    StackLogsParams,
    StackOperation
)
from ..tools.stack_operations import (
    start_stack,
    stop_stack,
    restart_stack,
    remove_stack,
    get_stack_logs
)

logger = get_logger(__name__)


class ManageStackTool:
    """Tool for managing existing Docker stacks"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        
        @mcp.tool()
        async def manage_stack(
            stack_name: str,
            action: str,
            follow_logs: bool = False,
            tail_lines: int = 100
        ) -> Dict[str, Any]:
            """
            Perform operations on existing stacks
            
            Args:
                stack_name: Name of the stack
                action: Operation to perform (start, stop, restart, remove, logs)
                follow_logs: Follow log output (for logs action)
                tail_lines: Number of log lines to show
                
            Returns:
                Operation result
            """
            server_state.increment_operations()
            
            try:
                # Normalize action to lowercase
                action_lower = action.lower()
                
                # Validate action
                valid_actions = [op.value for op in StackOperation]
                if action_lower not in valid_actions:
                    return {
                        "success": False,
                        "message": f"Invalid action '{action}'. Valid actions are: {', '.join(valid_actions)}",
                        "error": "Invalid action"
                    }
                
                # Log the operation
                logger.info(f"Performing {action_lower} on stack {stack_name}")
                
                # Handle different actions
                if action_lower == StackOperation.START.value:
                    params = StackOperationParams(name=stack_name)
                    result = start_stack(params)
                    
                elif action_lower == StackOperation.STOP.value:
                    params = StackOperationParams(name=stack_name)
                    result = stop_stack(params)
                    
                elif action_lower == StackOperation.RESTART.value:
                    params = StackOperationParams(name=stack_name)
                    result = restart_stack(params)
                    
                elif action_lower == StackOperation.REMOVE.value:
                    # For remove, we'll use force=False by default
                    # Users should be explicit about removing volumes
                    params = StackOperationParams(name=stack_name, force=False)
                    result = remove_stack(params)
                    
                elif action_lower == StackOperation.LOGS.value:
                    params = StackLogsParams(
                        name=stack_name,
                        lines=tail_lines,
                        follow=follow_logs
                    )
                    result = get_stack_logs(params)
                
                else:
                    # This shouldn't happen due to validation above, but just in case
                    return {
                        "success": False,
                        "message": f"Action '{action}' not implemented",
                        "error": "Not implemented"
                    }
                
                # Convert result to dictionary for MCP response
                response = {
                    "success": result.success,
                    "message": result.message,
                    "action": action_lower,
                    "stack_name": stack_name
                }
                
                # Add error if present
                if result.error:
                    response["error"] = result.error
                
                # Add details if present
                if result.details:
                    response["details"] = result.details
                
                # Log result
                if result.success:
                    logger.info(f"Successfully performed {action_lower} on stack {stack_name}")
                else:
                    logger.error(f"Failed to perform {action_lower} on stack {stack_name}: {result.error}")
                
                return response
                
            except Exception as e:
                logger.error(f"Error performing {action} on stack {stack_name}: {str(e)}")
                return {
                    "success": False,
                    "message": f"Error performing {action} on stack {stack_name}",
                    "error": str(e),
                    "action": action,
                    "stack_name": stack_name
                }