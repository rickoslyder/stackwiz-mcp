#!/usr/bin/env python3
"""
StackWiz MCP Server - Main entry point

This module implements the Model Context Protocol server for StackWiz,
enabling AI assistants to create and manage Docker service stacks.
"""

import asyncio
import json
import logging
import os
import sys
import shutil
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from datetime import datetime, timezone
from contextlib import asynccontextmanager

from fastmcp import FastMCP
try:
    from fastmcp.exceptions import McpError
except ImportError:
    # Create a fallback McpError if not available
    class McpError(Exception):
        def __init__(self, message, code=-32603):
            super().__init__(message)
            self.code = code
from pydantic import BaseModel, Field, ConfigDict

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stackwiz_mcp.config import get_config, Config
from stackwiz_mcp.utils.logging import setup_logging, get_logger
from stackwiz_mcp.utils.health import HealthChecker
from stackwiz_mcp.models.stack_models import (
    StackConfig,
    StackType,
    StackOperation,
    DnsRecord,
    ValidationResult
)

# Import tools
from stackwiz_mcp.tools.create_stack import CreateStackTool
from stackwiz_mcp.tools.list_stacks import ListStacksTool
from stackwiz_mcp.tools.manage_stack import ManageStackTool
from stackwiz_mcp.tools.dns_operations import CreateDnsRecordTool, ListDnsRecordsTool, UpdateDnsProxyTool
from stackwiz_mcp.tools.validate_config import ValidateStackConfigTool

# Import resources
from stackwiz_mcp.resources.stack_configs import StackConfigsResource
from stackwiz_mcp.resources.templates import TemplatesResource
from stackwiz_mcp.resources.infrastructure import InfrastructureResource

# Import prompts
from stackwiz_mcp.prompts.deployment_prompts import (
    DeployWebAppPrompt,
    SetupDatabasePrompt,
    CreateApiServicePrompt
)

# Initialize logging
logger = get_logger(__name__)

# Application metadata
APP_NAME = "stackwiz-mcp"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "MCP server for managing Docker service stacks"


class ServerState:
    """Manages server state and session data"""
    
    def __init__(self):
        self.start_time = datetime.now(timezone.utc)
        self.operation_count = 0
        self.active_operations = {}
        self.cache = {}
        self.health_checker = HealthChecker()
    
    def increment_operations(self):
        """Increment operation counter"""
        self.operation_count += 1
    
    def add_active_operation(self, operation_id: str, details: Dict[str, Any]):
        """Track an active operation"""
        self.active_operations[operation_id] = {
            "started_at": datetime.now(timezone.utc),
            "details": details
        }
    
    def remove_active_operation(self, operation_id: str):
        """Remove completed operation"""
        self.active_operations.pop(operation_id, None)
    
    def get_uptime_seconds(self) -> float:
        """Get server uptime in seconds"""
        return (datetime.now(timezone.utc) - self.start_time).total_seconds()


# Global server state
server_state = ServerState()


@asynccontextmanager
async def lifespan(app: FastMCP):
    """Manage server lifecycle"""
    # Startup
    logger.info(f"Starting {APP_NAME} v{APP_VERSION}")
    
    # Initialize configuration
    config = get_config()
    logger.info(f"Base directory: {config.base_dir}")
    logger.info(f"Environment: {config.environment}")
    
    # Run health checks
    health_status = await server_state.health_checker.check_all()
    if not health_status["healthy"]:
        logger.warning("Some health checks failed during startup")
        for check, result in health_status["checks"].items():
            if not result["healthy"]:
                logger.warning(f"  {check}: {result['message']}")
    
    # Initialize tools with configuration
    await initialize_tools(config)
    
    logger.info("Server startup complete")
    
    yield
    
    # Shutdown
    logger.info("Shutting down server...")
    
    # Cleanup any active operations
    if server_state.active_operations:
        logger.warning(f"Cleaning up {len(server_state.active_operations)} active operations")
    
    logger.info("Server shutdown complete")


async def initialize_tools(config: Config):
    """Initialize all tools with configuration"""
    logger.info("[DEBUG] Starting resource and prompt registration")
    # Tools are now registered at module level after mcp instance creation
    # Old tool registration removed - was causing the execution issue
    
    # Register all resources
    StackConfigsResource.register(mcp)
    TemplatesResource.register(mcp)
    InfrastructureResource.register(mcp)
    
    # Register all prompts
    DeployWebAppPrompt.register(mcp)
    SetupDatabasePrompt.register(mcp)
    CreateApiServicePrompt.register(mcp)
    
    # Log registration completion
    logger.info("Resource and prompt registration complete")
    logger.info("Tools are registered at module level")


# Create the FastMCP application
mcp = FastMCP(
    name=APP_NAME,
    version=APP_VERSION,
    instructions=APP_DESCRIPTION,  # Use 'instructions' instead of 'description'
    lifespan=lifespan
)

# Tool implementations will be defined after mcp instance creation

# Import necessary utilities for tool implementations
from .utils.stack_utils import (
    get_stack_path, stack_exists, render_template,
    fix_permissions, run_docker_compose, slugify,
    list_stacks as list_stacks_util,
    get_stack_status, get_stack_info,
    run_command, BASE_DIR
)
from .tools.stack_operations import (
    start_stack, stop_stack, restart_stack,
    remove_stack, get_stack_logs
)
import re
import requests


def get_cloudflare_api_token() -> Optional[str]:
    """
    Get Cloudflare API token from config, environment, or traefik/.env.

    Returns the first available token from:
    1. Config (config.dns.api_token)
    2. Environment variables (CF_API_TOKEN, CF_DNS_API_TOKEN)
    3. Traefik .env file

    Returns:
        API token string or None if not found
    """
    config = get_config()

    # 1. Try config first (already checks env vars via model_validator)
    if config.dns.api_token:
        return config.dns.api_token

    # 2. Try direct environment variables
    token = os.environ.get("CF_API_TOKEN") or os.environ.get("CF_DNS_API_TOKEN")
    if token:
        return token

    # 3. Try to read from Traefik env file as last resort
    # Import dynamically to get runtime value, not import-time constant
    from .utils.stack_utils import _get_base_dir
    traefik_env = os.path.join(_get_base_dir(), "traefik", ".env")
    if os.path.exists(traefik_env):
        try:
            with open(traefik_env, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("CF_API_TOKEN=") or line.startswith("CF_DNS_API_TOKEN="):
                        return line.split("=", 1)[1].strip().strip('"\'')
        except Exception as e:
            logger.warning(f"Failed to read Traefik env file: {e}")

    return None


def get_cloudflare_domain() -> str:
    """Get the configured Cloudflare domain."""
    config = get_config()
    return config.dns.domain  # Uses the property alias


def parse_cloudflare_error(response_json: Dict[str, Any]) -> str:
    """
    Parse Cloudflare API error response and return a user-friendly message.

    The Cloudflare API returns errors in this format:
    {
        "success": false,
        "errors": [{"code": 1004, "message": "DNS Validation Error"}],
        "messages": []
    }

    Args:
        response_json: The JSON response from Cloudflare API

    Returns:
        A formatted error message string
    """
    errors = response_json.get("errors", [])
    if not errors:
        return "Unknown Cloudflare API error"

    # Build comprehensive error message
    error_parts = []
    for error in errors:
        code = error.get("code", "")
        message = error.get("message", "Unknown error")

        # Include error chain if present (nested errors)
        error_chain = error.get("error_chain", [])
        if error_chain:
            chain_msgs = [e.get("message", "") for e in error_chain if e.get("message")]
            if chain_msgs:
                message = f"{message} ({'; '.join(chain_msgs)})"

        if code:
            error_parts.append(f"[{code}] {message}")
        else:
            error_parts.append(message)

    return "; ".join(error_parts)


def cloudflare_api_request(
    method: str,
    url: str,
    headers: Dict[str, str],
    json_data: Optional[Dict[str, Any]] = None,
    max_retries: int = 3,
    base_delay: float = 1.0,
    timeout: int = 10
) -> Tuple[bool, Dict[str, Any]]:
    """
    Make a Cloudflare API request with automatic retry and rate limit handling.

    Implements exponential backoff for:
    - 429 Too Many Requests (rate limiting)
    - 5xx Server Errors (transient errors)
    - Connection/timeout errors

    Args:
        method: HTTP method (GET, POST, PATCH, DELETE)
        url: Full API URL
        headers: Request headers including auth
        json_data: Optional JSON payload for POST/PATCH
        max_retries: Maximum retry attempts (default: 3)
        base_delay: Base delay in seconds for exponential backoff (default: 1.0)
        timeout: Request timeout in seconds (default: 10)

    Returns:
        Tuple of (success: bool, response_data: dict)
        On success: (True, response_json)
        On failure: (False, {"error": error_message, "status_code": code})
    """
    last_error = None

    for attempt in range(max_retries + 1):
        try:
            # Select request method
            if method.upper() == "GET":
                response = requests.get(url, headers=headers, timeout=timeout)
            elif method.upper() == "POST":
                response = requests.post(url, headers=headers, json=json_data, timeout=timeout)
            elif method.upper() == "PATCH":
                response = requests.patch(url, headers=headers, json=json_data, timeout=timeout)
            elif method.upper() == "DELETE":
                response = requests.delete(url, headers=headers, timeout=timeout)
            else:
                return (False, {"error": f"Unsupported HTTP method: {method}"})

            # Handle rate limiting (429)
            if response.status_code == 429:
                # Check Retry-After header
                retry_after = response.headers.get("Retry-After")
                if retry_after:
                    try:
                        wait_time = int(retry_after)
                    except ValueError:
                        wait_time = base_delay * (2 ** attempt)
                else:
                    wait_time = base_delay * (2 ** attempt)

                if attempt < max_retries:
                    logger.warning(
                        f"Cloudflare rate limit hit, waiting {wait_time}s before retry "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    return (False, {
                        "error": "Rate limit exceeded after max retries",
                        "status_code": 429
                    })

            # Handle server errors (5xx) with retry
            if 500 <= response.status_code < 600:
                if attempt < max_retries:
                    wait_time = base_delay * (2 ** attempt)
                    logger.warning(
                        f"Cloudflare server error {response.status_code}, waiting {wait_time}s "
                        f"(attempt {attempt + 1}/{max_retries})"
                    )
                    time.sleep(wait_time)
                    continue
                else:
                    return (False, {
                        "error": f"Server error {response.status_code} after max retries",
                        "status_code": response.status_code
                    })

            # Parse JSON response
            try:
                response_json = response.json()
            except json.JSONDecodeError:
                return (False, {
                    "error": f"Invalid JSON response from Cloudflare API",
                    "status_code": response.status_code
                })

            # Check for API-level success
            if response.status_code in [200, 201] and response_json.get("success"):
                return (True, response_json)

            # Parse error from response
            error_msg = parse_cloudflare_error(response_json)
            return (False, {
                "error": error_msg,
                "status_code": response.status_code,
                "raw_response": response_json
            })

        except requests.exceptions.Timeout:
            last_error = "Request timeout"
            if attempt < max_retries:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(f"Request timeout, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
        except requests.exceptions.ConnectionError as e:
            last_error = f"Connection error: {str(e)}"
            if attempt < max_retries:
                wait_time = base_delay * (2 ** attempt)
                logger.warning(f"Connection error, waiting {wait_time}s (attempt {attempt + 1}/{max_retries})")
                time.sleep(wait_time)
                continue
        except Exception as e:
            last_error = str(e)
            logger.error(f"Unexpected error in Cloudflare API request: {e}")
            break

    return (False, {"error": last_error or "Unknown error after all retries"})


def get_cloudflare_zone_id(api_token: str, domain: str) -> Tuple[bool, str]:
    """
    Get Cloudflare zone ID for a domain with caching.

    Args:
        api_token: Cloudflare API token
        domain: Domain name to look up

    Returns:
        Tuple of (success: bool, zone_id_or_error: str)
    """
    # Check cache first (simple in-memory cache for zone IDs)
    cache_key = f"zone_id_{domain}"
    if cache_key in server_state.cache:
        cached = server_state.cache[cache_key]
        # Cache valid for 5 minutes
        if time.time() - cached["timestamp"] < 300:
            return (True, cached["zone_id"])

    headers = {
        "Authorization": f"Bearer {api_token}",
        "Content-Type": "application/json"
    }

    success, result = cloudflare_api_request(
        "GET",
        f"https://api.cloudflare.com/client/v4/zones?name={domain}",
        headers
    )

    if not success:
        return (False, result.get("error", "Failed to get zone ID"))

    zones = result.get("result", [])
    if not zones:
        return (False, f"No zone found for domain: {domain}")

    zone_id = zones[0]["id"]

    # Cache the zone ID
    server_state.cache[cache_key] = {
        "zone_id": zone_id,
        "timestamp": time.time()
    }

    return (True, zone_id)


# Register tools with proper decorators at module level
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
    logger.info(f"[EXECUTION] create_stack called with name={name}, type={type}")
    
    # Write test file to verify execution
    test_file = f"/tmp/create-stack-{name}-{datetime.now(timezone.utc).timestamp()}.txt"
    with open(test_file, "w") as f:
        f.write(f"create_stack executed at {datetime.now(timezone.utc)} for {name}")
    logger.info(f"[EXECUTION] Test file written: {test_file}")
    
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
                return {"success": False, "error": "Image is required for generic stack type"}
            if not config.port:
                return {"success": False, "error": "Port is required for generic stack type"}
        
        # Generate secure encryption key for pocketbase
        def generate_encryption_key():
            import random
            import string
            return ''.join(random.choices(string.ascii_letters + string.digits, k=32))
        
        # Sanitize stack name
        sanitized_name = slugify(config.name)
        if sanitized_name != config.name:
            logger.warning(f"Stack name sanitized from '{config.name}' to '{sanitized_name}'")
        
        # Check if stack already exists
        stack_path = get_stack_path(sanitized_name)
        if stack_exists(sanitized_name):
            return {"success": False, "error": f"Stack '{sanitized_name}' already exists"}
        
        # Create stack directory structure
        logger.info(f"[EXECUTION] Creating directory: {stack_path}")
        os.makedirs(stack_path, mode=0o750)
        os.makedirs(os.path.join(stack_path, "data"), mode=0o750)
        os.makedirs(os.path.join(stack_path, "config"), mode=0o750)
        
        # Additional directories for pocketbase
        if config.type == "pocketbase":
            os.makedirs(os.path.join(stack_path, "pb_data"), mode=0o750)
            os.makedirs(os.path.join(stack_path, "pb_public"), mode=0o750)
            os.makedirs(os.path.join(stack_path, "pb_migrations"), mode=0o750)
            os.makedirs(os.path.join(stack_path, "pb_hooks"), mode=0o750)
        
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
        encryption_key = None
        if config.type == "generic":
            substitutions.update({
                "APP_IMAGE": config.image,
                "APP_PORT": str(config.port)
            })
        elif config.type == "pocketbase":
            encryption_key = generate_encryption_key()
        
        # Select and render templates based on type
        # Use config-based template directory (respects STACKWIZ_TEMPLATES_DIR)
        from .utils.stack_utils import _get_template_dir
        template_dir = _get_template_dir()
        
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
            return {"success": False, "error": f"Unknown stack type: {config.type}"}
        
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
                "encryption_key": encryption_key
            })
        
        return result
        
    except Exception as e:
        logger.error(f"Failed to create stack: {e}", exc_info=True)
        return {"success": False, "error": str(e)}

@mcp.tool()
async def list_stacks(
    filter: str = None,
    include_status: bool = True,
    sort_by: str = "name"
) -> Dict[str, Any]:
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
    logger.info(f"[EXECUTION] list_stacks called")
    
    try:
        stacks = list_stacks_util()
        
        # Apply filter if provided
        if filter:
            filter_lower = filter.lower()
            stacks = [s for s in stacks if filter_lower in s.lower()]
        
        # Get detailed information for each stack
        stack_info = []
        for stack_name in stacks:
            info = {
                "name": stack_name,
                "path": get_stack_path(stack_name)
            }
            
            if include_status:
                # Get container status (returns a string)
                status = get_stack_status(stack_name)
                info["status"] = status
                
                # Get additional info from docker-compose.yml
                stack_details = get_stack_info(stack_name)
                if stack_details:
                    info.update(stack_details)
            
            stack_info.append(info)
        
        # Sort results
        if sort_by == "name":
            stack_info.sort(key=lambda x: x["name"])
        elif sort_by == "created":
            stack_info.sort(key=lambda x: x.get("created", ""), reverse=True)
        elif sort_by == "status":
            stack_info.sort(key=lambda x: x.get("status", ""))
        
        return {
            "success": True,
            "stacks": stack_info,
            "total": len(stack_info)
        }
        
    except Exception as e:
        logger.error(f"Failed to list stacks: {e}")
        return {"success": False, "error": str(e)}

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
    logger.info(f"[EXECUTION] manage_stack called with stack={stack_name}, action={action}")
    
    try:
        # Check if stack exists
        if not stack_exists(stack_name):
            return {
                "success": False,
                "error": f"Stack '{stack_name}' not found"
            }
        
        # Import the models we need
        from .models.stack_models import StackOperationParams, StackLogsParams
        
        # Perform the requested action
        if action == "start":
            params = StackOperationParams(name=stack_name)
            result = start_stack(params)
        elif action == "stop":
            params = StackOperationParams(name=stack_name)
            result = stop_stack(params)
        elif action == "restart":
            params = StackOperationParams(name=stack_name)
            result = restart_stack(params)
        elif action == "remove":
            params = StackOperationParams(name=stack_name)
            result = remove_stack(params)
        elif action == "logs":
            params = StackLogsParams(name=stack_name, follow=follow_logs, tail=tail_lines)
            result = get_stack_logs(params)
        else:
            return {
                "success": False,
                "error": f"Unknown action: {action}"
            }
        
        return result.model_dump()
        
    except Exception as e:
        logger.error(f"Failed to manage stack: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def create_dns_record(
    subdomain: str,
    type: str = "A",
    value: str = "AUTO",
    priority: int = None,
    proxied: bool = True
) -> Dict[str, Any]:
    """
    Create a DNS record

    Args:
        subdomain: Subdomain name
        type: Record type (A, CNAME, MX, TXT)
        value: Record value (AUTO for server IP)
        priority: Priority for MX records
        proxied: Enable Cloudflare proxy

    Returns:
        Operation result
    """
    server_state.increment_operations()
    logger.info(f"[EXECUTION] create_dns_record called for {subdomain}")

    try:
        # Get Cloudflare API token using centralized helper
        api_token = get_cloudflare_api_token()
        if not api_token:
            logger.error("DNS API token not found in config, environment, or traefik/.env")
            return {
                "success": False,
                "error": "Cloudflare API token not configured"
            }

        # Set up API parameters
        domain = get_cloudflare_domain()
        api_base = "https://api.cloudflare.com/client/v4"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        # Get zone ID using cached helper with retry logic
        zone_success, zone_result = get_cloudflare_zone_id(api_token, domain)
        if not zone_success:
            return {
                "success": False,
                "error": zone_result
            }
        zone_id = zone_result

        # Handle AUTO value for A records
        target = value
        if type == "A" and value == "AUTO":
            # Get public IP
            ip_services = [
                "https://ipv4.icanhazip.com",
                "https://api.ipify.org",
                "https://ifconfig.me/ip"
            ]

            for service in ip_services:
                try:
                    ip_response = requests.get(service, timeout=5)
                    if ip_response.status_code == 200:
                        target = ip_response.text.strip()
                        break
                except:
                    continue

            if target == "AUTO":
                return {
                    "success": False,
                    "error": "Failed to auto-detect public IP"
                }

        # Prepare DNS record data
        data = {
            "type": type,
            "name": f"{subdomain}.{domain}",
            "content": target,
            "ttl": 1,
            "proxied": proxied and type in ["A", "AAAA", "CNAME"]
        }

        if type == "MX" and priority is not None:
            data["priority"] = priority

        # Create the record with retry logic
        logger.info(f"Creating DNS record with data: {data}")
        success, result = cloudflare_api_request(
            "POST",
            f"{api_base}/zones/{zone_id}/dns_records",
            headers,
            json_data=data
        )

        logger.info(f"DNS API response: success={success}, result={result}")

        if success:
            record_data = result.get("result", {})
            return {
                "success": True,
                "message": f"DNS record created for {subdomain}.{domain}",
                "details": {
                    "subdomain": subdomain,
                    "full_domain": f"{subdomain}.{domain}",
                    "type": type,
                    "target": target,
                    "proxied": proxied,
                    "record_id": record_data.get("id")
                }
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Unknown error")
            }

    except Exception as e:
        logger.error(f"Failed to create DNS record: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def list_dns_records(
    filter: str = None
) -> Dict[str, Any]:
    """
    List DNS records

    Args:
        filter: Filter records by name

    Returns:
        List of DNS records
    """
    server_state.increment_operations()
    logger.info(f"[EXECUTION] list_dns_records called")

    try:
        # Get Cloudflare API token using centralized helper
        api_token = get_cloudflare_api_token()
        if not api_token:
            logger.error("DNS API token not found in config, environment, or traefik/.env")
            return {
                "success": False,
                "error": "Cloudflare API token not configured",
                "records": []
            }

        # Set up API parameters
        domain = get_cloudflare_domain()
        api_base = "https://api.cloudflare.com/client/v4"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        # Get zone ID using cached helper with retry logic
        zone_success, zone_result = get_cloudflare_zone_id(api_token, domain)
        if not zone_success:
            return {
                "success": False,
                "error": zone_result,
                "records": []
            }
        zone_id = zone_result

        # Fetch DNS records with retry logic
        success, result = cloudflare_api_request(
            "GET",
            f"{api_base}/zones/{zone_id}/dns_records?per_page=100",
            headers
        )

        if success:
            records = result.get("result", [])

            # Format records
            formatted_records = []
            for record in records:
                # Apply filter if provided
                if filter and filter.lower() not in record["name"].lower():
                    continue

                formatted_records.append({
                    "id": record["id"],
                    "type": record["type"],
                    "name": record["name"],
                    "content": record["content"],
                    "proxied": record.get("proxied", False),
                    "ttl": record.get("ttl", "Auto"),
                    "created_on": record.get("created_on"),
                    "modified_on": record.get("modified_on")
                })

            # Sort by name
            formatted_records.sort(key=lambda r: r["name"])

            return {
                "success": True,
                "records": formatted_records,
                "total": len(formatted_records)
            }
        else:
            return {
                "success": False,
                "error": result.get("error", "Failed to list DNS records"),
                "records": []
            }

    except Exception as e:
        logger.error(f"Failed to list DNS records: {e}")
        return {"success": False, "error": str(e), "records": []}

@mcp.tool()
async def update_dns_proxy(
    subdomain: str,
    enable: bool
) -> Dict[str, Any]:
    """
    Enable or disable Cloudflare proxy for a DNS record

    Args:
        subdomain: Subdomain name
        enable: True to enable proxy, False to disable

    Returns:
        Operation result
    """
    server_state.increment_operations()
    logger.info(f"[EXECUTION] update_dns_proxy called for {subdomain}, enable={enable}")

    try:
        # Get Cloudflare API token using centralized helper
        api_token = get_cloudflare_api_token()
        if not api_token:
            logger.error("DNS API token not found in config, environment, or traefik/.env")
            return {
                "success": False,
                "error": "Cloudflare API token not configured"
            }

        # Set up API parameters
        domain = get_cloudflare_domain()
        api_base = "https://api.cloudflare.com/client/v4"
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        # Get zone ID using cached helper with retry logic
        zone_success, zone_result = get_cloudflare_zone_id(api_token, domain)
        if not zone_success:
            return {
                "success": False,
                "error": zone_result
            }
        zone_id = zone_result

        # Find the record with retry logic
        full_domain = f"{subdomain}.{domain}"
        success, result = cloudflare_api_request(
            "GET",
            f"{api_base}/zones/{zone_id}/dns_records?name={full_domain}",
            headers
        )

        if not success:
            return {
                "success": False,
                "error": result.get("error", f"Failed to fetch DNS records for {full_domain}")
            }

        records = result.get("result", [])
        if not records:
            return {
                "success": False,
                "error": f"No DNS record found for {full_domain}"
            }

        # Find the first proxyable record (A, AAAA, or CNAME)
        target_record = None
        for record in records:
            if record["type"] in ["A", "AAAA", "CNAME"]:
                target_record = record
                break

        if not target_record:
            return {
                "success": False,
                "error": f"No proxyable record found for {full_domain} (only A, AAAA, and CNAME records can be proxied)"
            }

        # Update the proxy status with retry logic
        update_data = {"proxied": enable}

        logger.info(f"Updating DNS proxy for record ID {target_record['id']}")
        update_success, update_result = cloudflare_api_request(
            "PATCH",
            f"{api_base}/zones/{zone_id}/dns_records/{target_record['id']}",
            headers,
            json_data=update_data
        )

        if update_success:
            status = "enabled" if enable else "disabled"
            return {
                "success": True,
                "message": f"Cloudflare proxy {status} for {full_domain}",
                "details": {
                    "subdomain": subdomain,
                    "full_domain": full_domain,
                    "type": target_record["type"],
                    "proxied": enable,
                    "record_id": target_record["id"]
                }
            }
        else:
            return {
                "success": False,
                "error": update_result.get("error", "Unknown error")
            }

    except Exception as e:
        logger.error(f"Failed to update DNS proxy: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def delete_dns_record(
    subdomain: str
) -> Dict[str, Any]:
    """
    Delete a DNS record

    Args:
        subdomain: Subdomain name to delete

    Returns:
        Operation result
    """
    server_state.increment_operations()
    logger.info(f"[EXECUTION] delete_dns_record called for {subdomain}")

    try:
        # Get Cloudflare API token using centralized helper
        api_token = get_cloudflare_api_token()
        if not api_token:
            logger.error("DNS API token not found in config, environment, or traefik/.env")
            return {
                "success": False,
                "error": "Cloudflare API token not configured"
            }

        # Get domain from config
        domain = get_cloudflare_domain()

        # Cloudflare API base
        api_base = "https://api.cloudflare.com/client/v4"

        # Headers for API requests
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json"
        }

        # Get zone ID using cached helper with retry logic
        zone_success, zone_result = get_cloudflare_zone_id(api_token, domain)
        if not zone_success:
            return {
                "success": False,
                "error": zone_result
            }
        zone_id = zone_result
        logger.info(f"Found zone ID: {zone_id}")

        # Search for the record with retry logic
        full_domain = f"{subdomain}.{domain}"
        logger.info(f"Searching for DNS record: {full_domain}")

        success, result = cloudflare_api_request(
            "GET",
            f"{api_base}/zones/{zone_id}/dns_records?name={full_domain}",
            headers
        )

        if not success:
            return {
                "success": False,
                "error": result.get("error", f"Failed to search for DNS record")
            }

        records = result.get("result", [])
        if not records:
            return {
                "success": False,
                "error": f"No DNS record found for {full_domain}"
            }

        # Delete all matching records with retry logic
        deleted_count = 0
        failed_records = []
        for record in records:
            record_id = record["id"]
            logger.info(f"Deleting DNS record ID: {record_id}")

            del_success, del_result = cloudflare_api_request(
                "DELETE",
                f"{api_base}/zones/{zone_id}/dns_records/{record_id}",
                headers
            )

            if del_success:
                deleted_count += 1
                logger.info(f"Successfully deleted record {record_id}")
            else:
                failed_records.append({
                    "id": record_id,
                    "error": del_result.get("error", "Unknown error")
                })
                logger.error(f"Failed to delete record {record_id}: {del_result.get('error')}")

        if deleted_count > 0:
            response = {
                "success": True,
                "message": f"Deleted {deleted_count} DNS record(s) for {full_domain}",
                "details": {
                    "subdomain": subdomain,
                    "full_domain": full_domain,
                    "records_deleted": deleted_count
                }
            }
            if failed_records:
                response["details"]["failed_records"] = failed_records
            return response
        else:
            return {
                "success": False,
                "error": f"Failed to delete any DNS records: {failed_records[0]['error'] if failed_records else 'Unknown error'}"
            }

    except Exception as e:
        logger.error(f"Failed to delete DNS record: {e}")
        return {"success": False, "error": str(e)}

@mcp.tool()
async def validate_stack_config(
    config: Dict[str, Any],
    check_conflicts: bool = True
) -> Dict[str, Any]:
    """
    Validate a stack configuration
    
    Args:
        config: Stack configuration to validate
        check_conflicts: Check for port/domain conflicts
        
    Returns:
        Validation result
    """
    server_state.increment_operations()
    logger.info(f"[EXECUTION] validate_stack_config called")
    
    try:
        valid = True
        errors = []
        warnings = []
        port_conflicts = []
        domain_conflicts = []
        
        # 1. Check required fields
        if not config.get("name"):
            errors.append({
                "field": "name",
                "message": "Stack name is required"
            })
            valid = False
        
        # Get stack type (default to generic)
        stack_type = config.get("type", "generic").lower()
        
        # 2. Validate stack name format if provided
        if config.get("name"):
            name = config["name"]
            
            # Check length
            if len(name) < 3:
                errors.append({
                    "field": "name",
                    "message": "Stack name must be at least 3 characters long"
                })
                valid = False
            elif len(name) > 50:
                errors.append({
                    "field": "name",
                    "message": "Stack name must be less than 50 characters long"
                })
                valid = False
            
            # Check format (lowercase alphanumeric + dashes)
            if not re.match(r'^[a-z0-9-]+$', name):
                errors.append({
                    "field": "name",
                    "message": "Stack name must contain only lowercase letters, numbers, and hyphens",
                    "suggestion": f"Try: {slugify(name)}"
                })
                valid = False
            
            # Check if starts/ends with hyphen
            if name.startswith('-') or name.endswith('-'):
                errors.append({
                    "field": "name",
                    "message": "Stack name cannot start or end with a hyphen"
                })
                valid = False
        
        # 3. Check required fields based on stack type
        if stack_type == "generic":
            # Generic stacks require image and port
            if not config.get("image"):
                errors.append({
                    "field": "image",
                    "message": "Docker image is required for generic stacks"
                })
                valid = False
            
            if not config.get("port"):
                errors.append({
                    "field": "port",
                    "message": "Container port is required for generic stacks"
                })
                valid = False
        elif stack_type == "pocketbase":
            # Pocketbase stacks don't require image/port
            pass
        else:
            warnings.append(f"Unknown stack type '{stack_type}', treating as generic")
        
        # 4. Validate port number if provided
        if config.get("port"):
            try:
                port = int(config["port"])
                if port < 1 or port > 65535:
                    errors.append({
                        "field": "port",
                        "message": f"Port number must be between 1 and 65535 (got {port})"
                    })
                    valid = False
            except (ValueError, TypeError):
                errors.append({
                    "field": "port",
                    "message": f"Port must be a valid integer (got {config['port']})"
                })
                valid = False
        
        # 5. Validate domain format if provided
        if config.get("domain"):
            domain = config["domain"]
            # Basic domain validation (allows subdomains and TLDs)
            domain_pattern = r'^([a-zA-Z0-9-]+\.)*[a-zA-Z0-9-]+\.[a-zA-Z]{2,}$'
            if not re.match(domain_pattern, domain):
                errors.append({
                    "field": "domain",
                    "message": f"Invalid domain format: {domain}",
                    "suggestion": "Use format like: example.com or sub.example.com"
                })
                valid = False
        
        # 6. Check for conflicts if requested and name is valid
        if check_conflicts and config.get("name") and not any(e["field"] == "name" for e in errors):
            name = config["name"]
            
            # Check if stack already exists
            if stack_exists(name):
                errors.append({
                    "field": "name",
                    "message": f"Stack '{name}' already exists",
                    "suggestion": "Choose a different name or remove the existing stack first"
                })
                valid = False
            
            # Check domain conflicts
            if config.get("domain"):
                domain = config["domain"]
                # Simple check - would need to implement full domain conflict checking
                domain_conflicts.append(domain)
            else:
                # Check default domain
                default_domain = f"{name}.rbnk.uk"
                # Simple check - would need to implement full domain conflict checking
            
            # Check port conflicts for generic stacks
            if stack_type == "generic" and config.get("port"):
                try:
                    port = int(config["port"])
                    # Simple check - would need to implement full port conflict checking
                    if port in [80, 443, 22]:
                        port_conflicts.append(port)
                        warnings.append(f"Port {port} is commonly used by system services")
                except:
                    pass
        
        # Add warnings for best practices
        if valid:
            # Warn about common ports
            if config.get("port"):
                try:
                    port = int(config["port"])
                    if port < 1024:
                        warnings.append(
                            f"Port {port} is a privileged port. Consider using a port above 1024"
                        )
                    if port in [80, 443, 22, 21, 25, 3306, 5432, 6379, 27017]:
                        warnings.append(
                            f"Port {port} is commonly used by system services. "
                            "Make sure it's not already in use"
                        )
                except:
                    pass
            
            # Warn about image tags
            if config.get("image") and ':' not in config["image"]:
                warnings.append(
                    f"Docker image '{config['image']}' doesn't specify a tag. "
                    "Consider using a specific version tag instead of 'latest'"
                )
        
        return {
            "valid": valid,
            "errors": errors,
            "warnings": warnings,
            "port_conflicts": port_conflicts,
            "domain_conflicts": domain_conflicts
        }
        
    except Exception as e:
        logger.error(f"Failed to validate config: {e}")
        return {
            "valid": False,
            "errors": [{"field": "general", "message": str(e)}],
            "warnings": [],
            "port_conflicts": [],
            "domain_conflicts": []
        }

# Error handler function (FastMCP handles errors internally)
# This is kept for reference but not used as a decorator
async def handle_error(error: Exception) -> Dict[str, Any]:
    """Global error handler"""
    logger.error(f"Unhandled error: {error}", exc_info=True)
    
    if isinstance(error, McpError):
        return {
            "error": {
                "code": error.code,
                "message": str(error),
                "data": getattr(error, "data", None)
            }
        }
    
    return {
        "error": {
            "code": -32603,
            "message": "Internal server error",
            "data": {
                "type": type(error).__name__,
                "message": str(error)
            }
        }
    }


# Health check endpoint
@mcp.tool()
async def health_check() -> Dict[str, Any]:
    """
    Check server health and connectivity
    
    Returns system health status including Docker, DNS, and filesystem checks.
    """
    server_state.increment_operations()
    
    health_status = await server_state.health_checker.check_all()
    
    return {
        "status": "healthy" if health_status["healthy"] else "unhealthy",
        "uptime_seconds": server_state.get_uptime_seconds(),
        "operation_count": server_state.operation_count,
        "active_operations": len(server_state.active_operations),
        "checks": health_status["checks"],
        "timestamp": datetime.now(timezone.utc).isoformat()
    }


# Server info endpoint
@mcp.tool()
async def server_info() -> Dict[str, Any]:
    """
    Get server information and capabilities
    
    Returns server version, available tools, and configuration details.
    """
    config = get_config()
    
    return {
        "name": APP_NAME,
        "version": APP_VERSION,
        "description": APP_DESCRIPTION,
        "environment": config.environment,
        "base_directory": str(config.base_dir),
        "capabilities": {
            "transports": ["stdio", "http"],
            "authentication": config.auth_enabled,
            "features": [
                "stack_management",
                "dns_management",
                "template_support",
                "validation",
                "monitoring"
            ]
        },
        "uptime_seconds": server_state.get_uptime_seconds(),
        "operation_count": server_state.operation_count
    }


# Tool registration moved to initialize_tools() function

# Resource and prompt registration moved to initialize_tools() function


# HTTP-specific endpoints (when running with HTTP transport)
if os.getenv("MCP_TRANSPORT", "stdio") == "http":
    from fastapi import FastAPI, Request, Response
    from fastapi.middleware.cors import CORSMiddleware
    from fastapi.responses import JSONResponse
    
    # Get the underlying FastAPI app
    app = mcp.http_app
    
    # Add CORS middleware for browser-based clients
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],  # Configure appropriately for production
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    
    @app.get("/health")
    async def http_health_check():
        """HTTP health check endpoint"""
        result = await health_check()
        return JSONResponse(content=result)
    
    @app.get("/info")
    async def http_server_info():
        """HTTP server info endpoint"""
        result = await server_info()
        return JSONResponse(content=result)
    
    @app.get("/metrics")
    async def http_metrics():
        """Prometheus-compatible metrics endpoint"""
        metrics = []
        
        # Basic metrics
        metrics.append(f"# HELP stackwiz_uptime_seconds Server uptime in seconds")
        metrics.append(f"# TYPE stackwiz_uptime_seconds counter")
        metrics.append(f"stackwiz_uptime_seconds {server_state.get_uptime_seconds()}")
        
        metrics.append(f"# HELP stackwiz_operations_total Total number of operations")
        metrics.append(f"# TYPE stackwiz_operations_total counter")
        metrics.append(f"stackwiz_operations_total {server_state.operation_count}")
        
        metrics.append(f"# HELP stackwiz_active_operations Current active operations")
        metrics.append(f"# TYPE stackwiz_active_operations gauge")
        metrics.append(f"stackwiz_active_operations {len(server_state.active_operations)}")
        
        # Health check metrics
        health_status = await server_state.health_checker.check_all()
        for check_name, check_result in health_status["checks"].items():
            metrics.append(f"# HELP stackwiz_health_{check_name} Health check status")
            metrics.append(f"# TYPE stackwiz_health_{check_name} gauge")
            value = 1 if check_result["healthy"] else 0
            metrics.append(f"stackwiz_health_{check_name} {value}")
        
        return Response(content="\n".join(metrics), media_type="text/plain")


def run_stdio():
    """Run the server in stdio mode"""
    logger.info("Starting in stdio mode")
    
    # Run the FastMCP server in stdio mode
    mcp.run()


def run_http(host: str = "0.0.0.0", port: int = 8000):
    """Run the server in HTTP mode"""
    logger.info(f"Starting in HTTP mode on {host}:{port}")
    
    # Update FastMCP settings for HTTP mode
    mcp.settings.host = host
    mcp.settings.port = port
    
    # Run in HTTP mode
    mcp.run()


def main():
    """Main entry point"""
    # Setup logging
    setup_logging()
    
    # Get transport mode from environment
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    
    if transport == "stdio":
        run_stdio()
    elif transport == "http":
        host = os.getenv("MCP_HTTP_HOST", "0.0.0.0")
        port = int(os.getenv("MCP_HTTP_PORT", "8000"))
        run_http(host, port)
    else:
        logger.error(f"Unknown transport mode: {transport}")
        sys.exit(1)


if __name__ == "__main__":
    main()