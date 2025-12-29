"""
List Stacks Tool - Lists existing Docker stacks
"""

from typing import Dict, Any, List
from ..utils.logging import get_logger
from ..utils.stack_utils import list_stacks as get_stack_list, get_stack_info

logger = get_logger(__name__)


class ListStacksTool:
    """Tool for listing existing Docker stacks"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        
        @mcp.tool()
        async def list_stacks(
            filter: str = None,
            include_status: bool = True,
            sort_by: str = "name"
        ) -> List[Dict[str, Any]]:
            """
            List all existing Docker stacks
            
            Args:
                filter: Filter stacks by name
                include_status: Include container status
                sort_by: Sort by name, created, or status
                
            Returns:
                List of stack information
            """
            server_state.increment_operations()
            
            try:
                # Get all stacks (excluding system stacks by default)
                stack_names = get_stack_list(include_system=False)
                
                # Get detailed info for each stack
                stacks_info = []
                for stack_name in stack_names:
                    # Apply filter if provided
                    if filter and filter.lower() not in stack_name.lower():
                        continue
                    
                    # Get stack info
                    stack_info = get_stack_info(stack_name)
                    
                    # Build result object
                    result = {
                        "name": stack_info["name"],
                        "path": stack_info["path"],
                        "status": stack_info["status"],
                        "stack_type": stack_info["stack_type"],
                        "domain": stack_info["domain"],
                        "image": stack_info["image"],
                        "port": stack_info["port"],
                        "has_env": stack_info["has_env"],
                        "has_compose": stack_info["has_compose"]
                    }
                    
                    # Add creation time if available
                    if "created_at" in stack_info:
                        result["created_at"] = stack_info["created_at"]
                    
                    # Include container status if requested
                    if include_status:
                        result["containers"] = []
                        for container in stack_info["containers"]:
                            container_info = {
                                "name": container.get("Name", ""),
                                "service": container.get("Service", ""),
                                "state": container.get("State", ""),
                                "status": container.get("Status", ""),
                                "image": container.get("Image", "")
                            }
                            
                            # Add health status if available
                            if "Health" in container:
                                container_info["health"] = container["Health"]
                                
                            result["containers"].append(container_info)
                    
                    stacks_info.append(result)
                
                # Sort results based on sort_by parameter
                if sort_by == "created":
                    # Sort by creation time (newest first)
                    stacks_info.sort(
                        key=lambda x: float(x.get("created_at", "0")),
                        reverse=True
                    )
                elif sort_by == "status":
                    # Sort by status (running first, then stopped, created, error)
                    status_order = {"running": 0, "stopped": 1, "created": 2, "error": 3}
                    stacks_info.sort(
                        key=lambda x: (status_order.get(x["status"], 4), x["name"])
                    )
                else:  # Default to name
                    stacks_info.sort(key=lambda x: x["name"])
                
                logger.info(f"Listed {len(stacks_info)} stacks (filter: {filter}, sort: {sort_by})")
                return stacks_info
                
            except Exception as e:
                logger.error(f"Error listing stacks: {str(e)}")
                raise