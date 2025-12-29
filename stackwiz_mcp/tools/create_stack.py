"""
Create Stack Tool - Creates new Docker service stacks
"""

import asyncio
from typing import Dict, Any
from datetime import datetime
from ..models.stack_models import StackConfig, OperationResult
from ..utils.logging import get_logger

logger = get_logger(__name__)


class CreateStackTool:
    """Tool for creating new Docker service stacks"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        logger.info("[TRACE] CreateStackTool.register() called")
        logger.info(f"[TRACE] MCP instance: {mcp}")
        logger.info(f"[TRACE] MCP type: {type(mcp)}")
        
        @mcp.tool()
        async def create_stack(
            name: str,
            type: str = "generic",
            image: str = None,
            port: int = None,
            domain: str = None,
            create_dns: bool = False,
            auto_start: bool = False,
            environment: Dict[str, str] = None
        ) -> Dict[str, Any]:
            """
            Create a new Docker service stack
            
            Args:
                name: Stack name (lowercase, alphanumeric with hyphens)
                type: Stack type (generic or pocketbase)
                image: Docker image (required for generic)
                port: Container port (required for generic)
                domain: Custom domain (defaults to {name}.rbnk.uk)
                create_dns: Create DNS record
                auto_start: Start stack after creation
                environment: Environment variables
                
            Returns:
                Operation result with stack details
            """
            server_state.increment_operations()
            logger.info(f"[DEBUG] create_stack called with name={name}, type={type}")
            
            # TEMPORARY TEST - Check if function is being called
            test_file = f"/tmp/test-create-stack-{name}.txt"
            with open(test_file, "w") as f:
                f.write(f"create_stack called at {datetime.now()} with name={name}")
            
            try:
                # Create stack config
                config = StackConfig(
                    name=name,
                    type=type,
                    image=image,
                    port=port,
                    domain=domain,
                    create_dns=create_dns,
                    auto_start=auto_start,
                    environment=environment or {}
                )
                
                # Validate input based on stack type
                if config.type == "generic":
                    if not config.image:
                        return {
                            "success": False,
                            "error": "Image is required for generic stack type"
                        }
                    if not config.port:
                        return {
                            "success": False,
                            "error": "Port is required for generic stack type"
                        }
                
                # Import stack utilities
                from ..utils.stack_utils import (
                    get_stack_path, stack_exists, render_template,
                    fix_permissions, run_docker_compose, slugify
                )
                import os
                import random
                import string
                
                # Generate secure encryption key for pocketbase
                def generate_encryption_key():
                    return ''.join(random.choices(string.ascii_letters + string.digits, k=32))
                
                # Sanitize stack name
                sanitized_name = slugify(config.name)
                if sanitized_name != config.name:
                    logger.warning(f"Stack name sanitized from '{config.name}' to '{sanitized_name}'")
                
                # Check if stack already exists
                stack_path = get_stack_path(sanitized_name)
                if stack_exists(sanitized_name):
                    return {
                        "success": False,
                        "error": f"Stack '{sanitized_name}' already exists"
                    }
                
                # Create stack directory structure
                try:
                    logger.info(f"[DEBUG] Creating directory: {stack_path}")
                    os.makedirs(stack_path, mode=0o750)
                    os.makedirs(os.path.join(stack_path, "data"), mode=0o750)
                    os.makedirs(os.path.join(stack_path, "config"), mode=0o750)
                    
                    # Additional directories for pocketbase
                    if config.type == "pocketbase":
                        os.makedirs(os.path.join(stack_path, "pb_data"), mode=0o750)
                        os.makedirs(os.path.join(stack_path, "pb_public"), mode=0o750)
                        os.makedirs(os.path.join(stack_path, "pb_migrations"), mode=0o750)
                        os.makedirs(os.path.join(stack_path, "pb_hooks"), mode=0o750)
                except Exception as e:
                    logger.error(f"Failed to create directories: {e}")
                    return {
                        "success": False,
                        "error": f"Failed to create stack directories: {str(e)}"
                    }
                
                # Set up token substitutions
                domain = config.domain or f"{sanitized_name}.rbnk.uk"
                service_name = config.service_name or sanitized_name
                
                substitutions = {
                    "APP_NAME": sanitized_name,
                    "SERVICE_NAME": service_name,
                    "APP_DOMAIN": domain,
                    "TRAEFIK_NETWORK": config.network,
                    "TRAEFIK_CERTRESOLVER": config.certresolver,
                    "TRAEFIK_ENTRYPOINT": config.entrypoint,
                }
                
                # Add type-specific substitutions
                if config.type == "generic":
                    substitutions.update({
                        "APP_IMAGE": config.image,
                        "APP_PORT": str(config.port)
                    })
                elif config.type == "pocketbase":
                    # Generate secure encryption key
                    encryption_key = generate_encryption_key()
                    
                # Select and render templates based on type
                template_dir = "/srv/dockerdata/_templates"
                
                if config.type == "generic":
                    # Render env file
                    render_template(
                        os.path.join(template_dir, "env-template"),
                        os.path.join(stack_path, ".env"),
                        substitutions
                    )
                    
                    # Render docker-compose.yml
                    render_template(
                        os.path.join(template_dir, "stack-template.yml"),
                        os.path.join(stack_path, "docker-compose.yml"),
                        substitutions
                    )
                    
                elif config.type == "pocketbase":
                    # Create .env file with encryption key
                    env_path = os.path.join(stack_path, ".env")
                    with open(os.path.join(template_dir, "pocketbase-env-template"), 'r') as f:
                        env_content = f.read()
                    
                    # Replace the placeholder encryption key
                    env_content = env_content.replace(
                        "PB_ENCRYPTION_KEY=CHANGE_THIS_TO_32_CHAR_RANDOM_KEY",
                        f"PB_ENCRYPTION_KEY={encryption_key}"
                    )
                    
                    # Add custom environment variables
                    if config.environment:
                        env_content += "\n# Custom environment variables\n"
                        for key, value in config.environment.items():
                            env_content += f"{key}={value}\n"
                    
                    with open(env_path, 'w') as f:
                        f.write(env_content)
                    
                    # Render docker-compose.yml
                    render_template(
                        os.path.join(template_dir, "pocketbase-template.yml"),
                        os.path.join(stack_path, "docker-compose.yml"),
                        substitutions
                    )
                    
                    # Copy README if exists
                    readme_src = os.path.join(template_dir, "README-pocketbase.md")
                    if os.path.exists(readme_src):
                        import shutil
                        shutil.copy2(readme_src, os.path.join(stack_path, "README.md"))
                
                else:
                    # Unknown stack type
                    return {
                        "success": False,
                        "error": f"Unknown stack type: {config.type}"
                    }
                
                # Add any additional environment variables from config
                if config.type == "generic" and config.environment:
                    env_path = os.path.join(stack_path, ".env")
                    with open(env_path, 'a') as f:
                        f.write("\n# Custom environment variables\n")
                        for key, value in config.environment.items():
                            f.write(f"{key}={value}\n")
                
                # Fix permissions on all created files
                fix_permissions(stack_path)
                for root, dirs, files in os.walk(stack_path):
                    for d in dirs:
                        fix_permissions(os.path.join(root, d))
                    for f in files:
                        fix_permissions(os.path.join(root, f))
                
                logger.info(f"Stack '{sanitized_name}' created successfully at {stack_path}")
                
                # Create DNS record if requested
                dns_created = False
                if config.create_dns:
                    logger.info(f"Creating DNS record for {domain}")
                    dns_script = "/srv/dockerdata/_scripts/cloudflare-dns-create.sh"
                    
                    if os.path.exists(dns_script):
                        # Extract subdomain from full domain
                        subdomain = domain.replace(".rbnk.uk", "") if domain.endswith(".rbnk.uk") else sanitized_name
                        
                        from ..utils.stack_utils import run_command
                        success, stdout, stderr = run_command([dns_script, subdomain])
                        
                        if success:
                            logger.info(f"DNS record created for {domain}")
                            dns_created = True
                        else:
                            logger.warning(f"Failed to create DNS record: {stderr}")
                    else:
                        logger.warning(f"DNS creation script not found: {dns_script}")
                
                # Start the stack if requested
                started = False
                if config.auto_start:
                    logger.info(f"Starting stack '{sanitized_name}'")
                    success, stdout, stderr = run_docker_compose(stack_path, ["up", "-d"])
                    
                    if success:
                        logger.info(f"Stack '{sanitized_name}' started successfully")
                        started = True
                    else:
                        logger.warning(f"Failed to start stack: {stderr}")
                
                # Prepare success response
                result = {
                    "success": True,
                    "message": f"Stack '{sanitized_name}' created successfully",
                    "stack": {
                        "name": sanitized_name,
                        "type": config.type,
                        "domain": domain,
                        "path": stack_path,
                        "status": "running" if started else "created",
                        "dns_created": dns_created,
                        "auto_started": started
                    }
                }
                
                # Add type-specific details
                if config.type == "generic":
                    result["stack"].update({
                        "image": config.image,
                        "port": config.port
                    })
                elif config.type == "pocketbase":
                    result["stack"].update({
                        "admin_url": f"https://{domain}/_/",
                        "api_url": f"https://{domain}/api/",
                        "encryption_key": encryption_key  # Include for user reference
                    })
                
                return result
                
            except Exception as e:
                logger.error(f"Failed to create stack: {e}")
                return {
                    "success": False,
                    "error": str(e)
                }
        
        # Log after function definition
        logger.info(f"[TRACE] create_stack function defined: {create_stack}")
        logger.info(f"[TRACE] Function type: {type(create_stack)}")
        logger.info(f"[TRACE] Is coroutine function: {asyncio.iscoroutinefunction(create_stack)}")
        
        # Try to check if tool was registered
        import inspect
        logger.info(f"[TRACE] MCP instance attributes: {dir(mcp)}")
        
        # Return the function for testing
        return create_stack