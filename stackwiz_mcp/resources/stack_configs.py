"""
Stack Configurations Resource - Provides access to stack configs
"""

import os
from typing import Dict, Any, List
from ..utils.logging import get_logger
from ..utils.stack_utils import (
    list_stacks,
    get_stack_path,
    get_docker_compose_file,
    read_env_file,
    get_container_status,
    get_stack_status as get_status,
    get_stack_info,
    stack_exists
)

logger = get_logger(__name__)


class StackConfigsResource:
    """Resource for accessing stack configurations"""
    
    @staticmethod
    def register(mcp):
        """Register the resource with the MCP server"""
        
        @mcp.resource("stack://list")
        async def list_stack_configs() -> Dict[str, Any]:
            """List all stack configurations"""
            try:
                # Get all stacks (exclude system stacks by default)
                stacks = list_stacks(include_system=False)
                
                # Build detailed stack information
                stack_configs = []
                for stack_name in stacks:
                    try:
                        info = get_stack_info(stack_name)
                        stack_configs.append({
                            "name": stack_name,
                            "status": info.get("status", "unknown"),
                            "domain": info.get("domain"),
                            "image": info.get("image"),
                            "type": info.get("stack_type", "generic"),
                            "has_env": info.get("has_env", False),
                            "has_compose": info.get("has_compose", False),
                            "container_count": len(info.get("containers", []))
                        })
                    except Exception as e:
                        logger.error(f"Error getting info for stack {stack_name}: {e}")
                        stack_configs.append({
                            "name": stack_name,
                            "status": "error",
                            "error": str(e)
                        })
                
                return {
                    "stacks": stack_configs,
                    "count": len(stack_configs)
                }
                
            except Exception as e:
                logger.error(f"Error listing stack configs: {e}")
                return {
                    "stacks": [],
                    "count": 0,
                    "error": str(e)
                }
        
        @mcp.resource("stack://{name}/compose")
        async def get_stack_compose(name: str) -> str:
            """Get Docker Compose file for a stack"""
            try:
                # Validate stack exists
                if not stack_exists(name):
                    return f"# Error: Stack '{name}' not found\n"
                
                # Get the compose file path
                stack_path = get_stack_path(name)
                compose_file = get_docker_compose_file(stack_path)
                
                if not compose_file:
                    return f"# Error: No docker-compose file found for stack '{name}'\n"
                
                # Read and return the compose file content
                with open(compose_file, 'r') as f:
                    content = f.read()
                
                return content
                
            except Exception as e:
                logger.error(f"Error reading compose file for stack {name}: {e}")
                return f"# Error reading compose file: {str(e)}\n"
        
        @mcp.resource("stack://{name}/env")
        async def get_stack_env(name: str) -> Dict[str, str]:
            """Get environment variables for a stack"""
            try:
                # Validate stack exists
                if not stack_exists(name):
                    return {
                        "_error": f"Stack '{name}' not found"
                    }
                
                # Read environment variables
                stack_path = get_stack_path(name)
                env_vars = read_env_file(stack_path)
                
                # Add metadata
                env_vars["_stack_name"] = name
                env_vars["_stack_path"] = stack_path
                
                # Check if .env file exists
                env_file = os.path.join(stack_path, ".env")
                if not os.path.exists(env_file):
                    env_vars["_note"] = "No .env file found for this stack"
                
                return env_vars
                
            except Exception as e:
                logger.error(f"Error reading env file for stack {name}: {e}")
                return {
                    "_error": str(e)
                }
        
        @mcp.resource("stack://{name}/status")
        async def get_stack_status(name: str) -> Dict[str, Any]:
            """Get current status of a stack"""
            try:
                # Validate stack exists
                if not stack_exists(name):
                    return {
                        "name": name,
                        "status": "not_found",
                        "error": f"Stack '{name}' not found"
                    }
                
                # Get comprehensive stack information
                info = get_stack_info(name)
                
                # Build detailed status response
                status_info = {
                    "name": name,
                    "status": info.get("status", "unknown"),
                    "path": info.get("path"),
                    "type": info.get("stack_type", "generic"),
                    "domain": info.get("domain"),
                    "image": info.get("image"),
                    "port": info.get("port"),
                    "containers": []
                }
                
                # Add container details
                for container in info.get("containers", []):
                    status_info["containers"].append({
                        "name": container.get("Name", ""),
                        "service": container.get("Service", ""),
                        "state": container.get("State", ""),
                        "status": container.get("Status", ""),
                        "health": container.get("Health", ""),
                        "id": container.get("ID", "")[:12] if container.get("ID") else "",
                        "image": container.get("Image", ""),
                        "created": container.get("CreatedAt", ""),
                        "started": container.get("StartedAt", ""),
                        "ports": container.get("Ports", "")
                    })
                
                # Add summary
                status_info["summary"] = {
                    "total_containers": len(status_info["containers"]),
                    "running": len([c for c in status_info["containers"] if c["state"].lower() in ["running", "up"]]),
                    "stopped": len([c for c in status_info["containers"] if c["state"].lower() in ["exited", "stopped"]]),
                    "error": len([c for c in status_info["containers"] if c["state"].lower() not in ["running", "up", "exited", "stopped", "created"]])
                }
                
                return status_info
                
            except Exception as e:
                logger.error(f"Error getting status for stack {name}: {e}")
                return {
                    "name": name,
                    "status": "error",
                    "error": str(e)
                }