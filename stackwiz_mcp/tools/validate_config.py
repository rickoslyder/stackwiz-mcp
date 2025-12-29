"""
Validate Config Tool - Validates stack configurations
"""

import re
from typing import Dict, Any, Optional
from ..models.stack_models import ValidationResult, StackType
from ..utils.logging import get_logger
from ..utils.stack_utils import (
    stack_exists, 
    list_stacks, 
    get_stack_info,
    slugify
)

logger = get_logger(__name__)


class ValidateStackConfigTool:
    """Tool for validating stack configurations"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        
        @mcp.tool()
        async def validate_stack_config(
            config: Dict[str, Any],
            check_conflicts: bool = True
        ) -> Dict[str, Any]:
            """
            Validate a stack configuration before creation
            
            Args:
                config: Stack configuration to validate
                check_conflicts: Check for port/domain conflicts
                
            Returns:
                Validation result
            """
            server_state.increment_operations()
            
            result = ValidationResult(valid=True)
            
            # 1. Check required fields
            if not config.get("name"):
                result.add_error("name", "Stack name is required")
            
            # Get stack type (default to generic)
            stack_type = config.get("type", "generic").lower()
            
            # 2. Validate stack name format if provided
            if config.get("name"):
                name = config["name"]
                
                # Check length
                if len(name) < 3:
                    result.add_error("name", "Stack name must be at least 3 characters long")
                elif len(name) > 50:
                    result.add_error("name", "Stack name must be less than 50 characters long")
                
                # Check format (lowercase alphanumeric + dashes)
                if not re.match(r'^[a-z0-9-]+$', name):
                    result.add_error(
                        "name", 
                        "Stack name must contain only lowercase letters, numbers, and hyphens",
                        suggestion=f"Try: {slugify(name)}"
                    )
                
                # Check if starts/ends with hyphen
                if name.startswith('-') or name.endswith('-'):
                    result.add_error("name", "Stack name cannot start or end with a hyphen")
            
            # 3. Check required fields based on stack type
            if stack_type == "generic":
                # Generic stacks require image and port
                if not config.get("image"):
                    result.add_error("image", "Docker image is required for generic stacks")
                
                if not config.get("port"):
                    result.add_error("port", "Container port is required for generic stacks")
            elif stack_type == "pocketbase":
                # Pocketbase stacks don't require image/port
                pass
            else:
                result.add_warning(f"Unknown stack type '{stack_type}', treating as generic")
            
            # 4. Validate port number if provided
            if config.get("port"):
                try:
                    port = int(config["port"])
                    if port < 1 or port > 65535:
                        result.add_error(
                            "port", 
                            f"Port number must be between 1 and 65535 (got {port})"
                        )
                except (ValueError, TypeError):
                    result.add_error(
                        "port", 
                        f"Port must be a valid integer (got {config['port']})"
                    )
            
            # 5. Validate domain format if provided
            if config.get("domain"):
                domain = config["domain"]
                # Basic domain validation (allows subdomains and TLDs)
                domain_pattern = r'^([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'
                if not re.match(domain_pattern, domain):
                    result.add_error(
                        "domain",
                        f"Invalid domain format: {domain}",
                        suggestion="Use format like: example.com or sub.example.com"
                    )
            
            # 6. Check for conflicts if requested and name is valid
            if check_conflicts and config.get("name") and not result.has_errors:
                name = config["name"]
                
                # Check if stack already exists
                if stack_exists(name):
                    result.add_error(
                        "name",
                        f"Stack '{name}' already exists",
                        suggestion="Choose a different name or remove the existing stack first"
                    )
                
                # Check domain conflicts
                if config.get("domain"):
                    domain = config["domain"]
                    if await _check_domain_conflict(domain, name):
                        result.add_error(
                            "domain",
                            f"Domain '{domain}' is already in use by another stack"
                        )
                        result.domain_conflicts.append(domain)
                else:
                    # Check default domain (name.rbnk.uk)
                    default_domain = f"{name}.rbnk.uk"
                    if await _check_domain_conflict(default_domain, name):
                        result.add_error(
                            "domain",
                            f"Default domain '{default_domain}' is already in use",
                            suggestion="Specify a custom domain with the 'domain' parameter"
                        )
                        result.domain_conflicts.append(default_domain)
                
                # Check port conflicts for generic stacks
                if stack_type == "generic" and config.get("port"):
                    try:
                        port = int(config["port"])
                        conflicting_stack = await _check_port_conflict(port, name)
                        if conflicting_stack:
                            result.add_error(
                                "port",
                                f"Port {port} is already in use by stack '{conflicting_stack}'",
                                suggestion="Choose a different port or stop the conflicting service"
                            )
                            result.port_conflicts.append(port)
                    except (ValueError, TypeError):
                        pass  # Already validated above
            
            # Add warnings for best practices
            if result.valid:
                # Warn about common ports
                if config.get("port"):
                    try:
                        port = int(config["port"])
                        if port < 1024:
                            result.add_warning(
                                f"Port {port} is a privileged port. Consider using a port above 1024"
                            )
                        if port in [80, 443, 22, 21, 25, 3306, 5432, 6379, 27017]:
                            result.add_warning(
                                f"Port {port} is commonly used by system services. "
                                "Make sure it's not already in use"
                            )
                    except:
                        pass
                
                # Warn about image tags
                if config.get("image") and ':' not in config["image"]:
                    result.add_warning(
                        f"Docker image '{config['image']}' doesn't specify a tag. "
                        "Consider using a specific version tag instead of 'latest'"
                    )
            
            return {
                "valid": result.valid,
                "errors": [e.dict() for e in result.errors],
                "warnings": result.warnings,
                "port_conflicts": result.port_conflicts,
                "domain_conflicts": result.domain_conflicts
            }


async def _check_domain_conflict(domain: str, current_stack: str) -> bool:
    """Check if a domain is already in use by another stack"""
    try:
        # Get all stacks
        stacks = list_stacks(include_system=False)
        
        for stack_name in stacks:
            if stack_name == current_stack:
                continue
            
            # Get stack info
            info = get_stack_info(stack_name)
            stack_domain = info.get("domain")
            
            if stack_domain and stack_domain == domain:
                return True
        
        return False
    except Exception as e:
        logger.warning(f"Error checking domain conflicts: {e}")
        return False


async def _check_port_conflict(port: int, current_stack: str) -> Optional[str]:
    """Check if a port is already in use by another stack. Returns conflicting stack name or None."""
    try:
        # Get all stacks
        stacks = list_stacks(include_system=False)
        
        for stack_name in stacks:
            if stack_name == current_stack:
                continue
            
            # Get stack info
            info = get_stack_info(stack_name)
            
            # Check if stack is running
            if info.get("status") != "running":
                continue
            
            # Check port from env vars
            stack_port = info.get("port")
            if stack_port and stack_port == port:
                return stack_name
            
            # Also check for common port mappings in containers
            for container in info.get("containers", []):
                # Check published ports
                ports = container.get("Ports", "")
                if ports and f":{port}->" in ports:
                    return stack_name
        
        return None
    except Exception as e:
        logger.warning(f"Error checking port conflicts: {e}")
        return None