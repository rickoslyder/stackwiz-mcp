"""
Utility functions for stack management operations.

Environment Variables (all optional with sensible defaults):
    STACKWIZ_BASE_DIR: Base directory for stacks (default: /srv/dockerdata)
    STACKWIZ_TEMPLATES_DIR: Templates directory (default: {base_dir}/_templates)
    STACKWIZ_DEFAULT_USER: Default user for file ownership (default: current user or 'root')
    STACKWIZ_DEFAULT_GROUP: Default group for file ownership (default: 'docker')
"""

import os
import subprocess
import json
import re
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any
import stat
import logging
import pwd
import grp

logger = logging.getLogger(__name__)


def _get_current_user() -> str:
    """Get current username, with fallback to 'root'."""
    try:
        return pwd.getpwuid(os.getuid()).pw_name
    except (KeyError, AttributeError):
        return "root"


def _get_base_dir() -> str:
    """Get base directory from environment or default."""
    return os.environ.get("STACKWIZ_BASE_DIR", "/srv/dockerdata")


def _get_template_dir() -> str:
    """Get template directory from environment or default."""
    explicit = os.environ.get("STACKWIZ_TEMPLATES_DIR")
    if explicit:
        return explicit
    return os.path.join(_get_base_dir(), "_templates")


def _get_default_user() -> str:
    """Get default user from environment or current user."""
    return os.environ.get("STACKWIZ_DEFAULT_USER", _get_current_user())


def _get_default_group() -> str:
    """Get default group from environment or 'docker'."""
    return os.environ.get("STACKWIZ_DEFAULT_GROUP", "docker")


# Dynamic properties that read from environment at runtime
# These are functions, but we provide module-level constants for backwards compatibility
# that are evaluated at import time (for code that imports BASE_DIR directly)
BASE_DIR = _get_base_dir()
TEMPLATE_DIR = _get_template_dir()
DEFAULT_USER = _get_default_user()
DEFAULT_GROUP = _get_default_group()

# System stacks that should not be managed by users
SYSTEM_STACKS = {
    "traefik", "monitoring", "supabase", "adguard", 
    "_backup", "_scripts", "_templates", "docs"
}


def slugify(name: str) -> str:
    """Convert string to valid stack name (lowercase alphanumeric + dashes)."""
    return re.sub(r'[^a-z0-9]+', '-', name.lower()).strip('-')


def get_stack_path(stack_name: str) -> str:
    """Get the full path for a stack."""
    return os.path.join(_get_base_dir(), stack_name)


def stack_exists(stack_name: str) -> bool:
    """Check if a stack directory exists."""
    return os.path.exists(get_stack_path(stack_name))


def get_docker_compose_file(stack_path: str) -> Optional[str]:
    """Find the docker-compose file in a stack directory."""
    for filename in ['docker-compose.yml', 'docker-compose.yaml', 'compose.yml', 'compose.yaml']:
        filepath = os.path.join(stack_path, filename)
        if os.path.exists(filepath):
            return filepath
    return None


def run_command(cmd: List[str], cwd: Optional[str] = None, capture_output: bool = True, timeout: int = 120) -> Tuple[bool, str, str]:
    """
    Run a command and return success, stdout, stderr.
    
    Args:
        cmd: Command to run as list of strings
        cwd: Working directory (optional)
        capture_output: Whether to capture stdout/stderr (default: True)
        timeout: Timeout in seconds (default: 120)
        
    Returns:
        Tuple of (success: bool, stdout: str, stderr: str)
        - success: True if command returned 0, False otherwise
        - stdout: Captured standard output (empty if capture_output=False)
        - stderr: Captured standard error or error message
        
    Note:
        If the command exceeds the timeout, returns (False, "", "Command timed out...")
    """
    try:
        result = subprocess.run(
            cmd,
            cwd=cwd,
            capture_output=capture_output,
            text=True,
            check=False,
            timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired as e:
        return False, "", f"Command timed out after {timeout} seconds: {' '.join(cmd)}"
    except Exception as e:
        return False, "", str(e)


def run_docker_compose(stack_path: str, command: List[str], sudo_user: Optional[str] = None) -> Tuple[bool, str, str]:
    """
    Run a docker compose command for a stack.
    
    Args:
        stack_path: Path to the stack directory containing docker-compose file
        command: Docker compose subcommand and arguments (e.g., ["up", "-d"])
        sudo_user: User to run command as when running as root (default: DEFAULT_USER)
                  Ignored when running in container environments
    
    Returns:
        Tuple of (success: bool, stdout: str, stderr: str) from run_command
    
    Note:
        - Automatically detects docker compose v2 vs v1 and uses appropriate command
        - Container detection: Skips sudo when running inside Docker container
          (detected via /.dockerenv file or MCP_TRANSPORT=stdio environment variable)
        - Only uses sudo when: running as root (euid=0), not in container, and sudo_user specified
    """
    compose_file = get_docker_compose_file(stack_path)
    if not compose_file:
        return False, "", "No docker-compose file found"
    
    # Try to use docker compose (v2), fall back to docker-compose (v1)
    if os.path.exists("/usr/local/bin/docker-compose") or os.path.exists("/usr/bin/docker-compose"):
        cmd = ["docker-compose", "-f", compose_file] + command
    else:
        cmd = ["docker", "compose", "-f", compose_file] + command
    
    # Skip sudo in container environments (MCP runs in Docker)
    # Check if we're in a container by looking for /.dockerenv
    in_container = os.path.exists("/.dockerenv") or os.environ.get("MCP_TRANSPORT") == "stdio"

    # Use default user if not specified
    if sudo_user is None:
        sudo_user = _get_default_user()

    # If sudo_user is specified and we're not in a container, run as that user
    if sudo_user and os.geteuid() == 0 and not in_container:  # Running as root, not in container
        cmd = ["sudo", "-u", sudo_user] + cmd
    
    return run_command(cmd, cwd=stack_path)


def get_container_status(stack_name: str) -> List[Dict[str, Any]]:
    """
    Get status of containers in a stack.
    """
    stack_path = get_stack_path(stack_name)
    compose_file = get_docker_compose_file(stack_path)
    
    if not compose_file:
        return []
    
    # Get container info using docker compose ps
    success, stdout, _ = run_docker_compose(stack_path, ["ps", "--format", "json"])
    
    if not success or not stdout.strip():
        return []
    
    try:
        # Docker compose ps --format json returns one JSON object per line
        containers = []
        for line in stdout.strip().split('\n'):
            if line:
                containers.append(json.loads(line))
        return containers
    except json.JSONDecodeError:
        return []


def get_stack_status(stack_name: str) -> str:
    """
    Determine the overall status of a stack.
    Returns: "running", "stopped", "created", "error"
    """
    containers = get_container_status(stack_name)
    
    if not containers:
        # No containers found, check if stack exists
        if stack_exists(stack_name):
            return "created"
        return "error"
    
    # Check container states
    running = 0
    stopped = 0
    error = 0
    
    for container in containers:
        state = container.get("State", "").lower()
        if state in ["running", "up"]:
            running += 1
        elif state in ["exited", "stopped", "created"]:
            stopped += 1
        else:
            error += 1
    
    if error > 0:
        return "error"
    elif running > 0 and stopped == 0:
        return "running"
    elif stopped > 0 and running == 0:
        return "stopped"
    else:
        return "created"


def read_env_file(stack_path: str) -> Dict[str, str]:
    """
    Read environment variables from .env file.
    """
    env_file = os.path.join(stack_path, ".env")
    env_vars = {}
    
    if not os.path.exists(env_file):
        return env_vars
    
    try:
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    # Remove quotes if present
                    value = value.strip('"\'')
                    env_vars[key.strip()] = value
    except Exception:
        pass
    
    return env_vars


def fix_permissions(path: str, user: str = None, group: str = None):
    """
    Fix permissions on a directory or file.
    
    Args:
        path: Path to file or directory
        user: Owner username (default: DEFAULT_USER)
        group: Owner group (default: DEFAULT_GROUP)
        
    Note:
        Automatically skips permission changes when running in container environments
        to avoid permission errors. Container detection uses /.dockerenv file or
        MCP_TRANSPORT=stdio environment variable.
    """
    try:
        # Skip permission fixing in container environments
        in_container = os.path.exists("/.dockerenv") or os.environ.get("MCP_TRANSPORT") == "stdio"
        if in_container:
            logger.debug("Running in container, skipping permission changes")
            return

        # Use defaults from environment if not specified
        if user is None:
            user = _get_default_user()
        if group is None:
            group = _get_default_group()

        # Get uid and gid
        uid = pwd.getpwnam(user).pw_uid
        gid = grp.getgrnam(group).gr_gid
        
        # Change ownership
        os.chown(path, uid, gid)
        
        # Set permissions
        if os.path.isdir(path):
            os.chmod(path, 0o750)
            
            # Fix .env file if it exists
            env_file = os.path.join(path, ".env")
            if os.path.exists(env_file):
                os.chown(env_file, uid, gid)
                os.chmod(env_file, 0o640)
            
            # Fix yml files
            for filename in os.listdir(path):
                if filename.endswith(('.yml', '.yaml')):
                    filepath = os.path.join(path, filename)
                    os.chown(filepath, uid, gid)
                    os.chmod(filepath, 0o644)
        else:
            # Single file
            if path.endswith('.env'):
                os.chmod(path, 0o640)
            else:
                os.chmod(path, 0o644)
                
    except Exception as e:
        # Silently continue if we can't fix permissions
        pass


def render_template(template_path: str, output_path: str, substitutions: Dict[str, str]):
    """
    Render a template file with token substitutions.
    """
    # Read template
    if os.path.exists(template_path):
        with open(template_path, 'r') as f:
            content = f.read()
    else:
        # Use fallback templates based on filename
        content = get_fallback_template(os.path.basename(template_path))
    
    # Apply substitutions
    for token, value in substitutions.items():
        # Escape special characters for template replacement
        escaped_value = value.replace('&', '\\&')
        content = content.replace(f"__{token}__", escaped_value)
    
    # Write output
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, 'w') as f:
        f.write(content)


def get_fallback_template(template_name: str) -> str:
    """
    Get fallback template content when template file doesn't exist.
    """
    if template_name == "env-template":
        return """APP_NAME=__APP_NAME__
APP_IMAGE=__APP_IMAGE__
APP_PORT=__APP_PORT__
APP_DOMAIN=__APP_DOMAIN__
TRAEFIK_NETWORK=__TRAEFIK_NETWORK__
TRAEFIK_CERTRESOLVER=__TRAEFIK_CERTRESOLVER__
TRAEFIK_ENTRYPOINT=__TRAEFIK_ENTRYPOINT__

# provider/API keys below (edit as needed)
# OPENAI_API_KEY=
# ANTHROPIC_API_KEY=
# GEMINI_API_KEY=
# GROQ_API_KEY=

STACKWIZ_GENERATED=1
"""
    
    elif template_name == "stack-template.yml":
        return """services:
  __SERVICE_NAME__:
    image: __APP_IMAGE__
    container_name: __APP_NAME__
    restart: unless-stopped
    env_file:
      - ./.env
    volumes:
      - ./data:/data
      - ./config:/config
    networks:
      - default
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.__APP_NAME__-http.rule=Host(`__APP_DOMAIN__`)"
      - "traefik.http.routers.__APP_NAME__-http.entrypoints=web"
      - "traefik.http.routers.__APP_NAME__-http.middlewares=redirect-to-https@file"
      - "traefik.http.routers.__APP_NAME__.rule=Host(`__APP_DOMAIN__`)"
      - "traefik.http.routers.__APP_NAME__.entrypoints=__TRAEFIK_ENTRYPOINT__"
      - "traefik.http.routers.__APP_NAME__.tls.certresolver=__TRAEFIK_CERTRESOLVER__"
      - "traefik.http.services.__APP_NAME__.loadbalancer.server.port=__APP_PORT__"
networks:
  default:
    external: true
    name: __TRAEFIK_NETWORK__
"""
    
    elif template_name == "config-template.yml":
        return "# application configuration stub - edit as required\n"
    
    else:
        return ""


def list_stacks(include_system: bool = False) -> List[str]:
    """
    List all stack directories.
    """
    stacks = []
    base_dir = _get_base_dir()

    try:
        for item in os.listdir(base_dir):
            item_path = os.path.join(base_dir, item)
            
            # Skip non-directories
            if not os.path.isdir(item_path):
                continue
            
            # Skip hidden directories
            if item.startswith('.'):
                continue
            
            # Skip system stacks unless requested
            if not include_system and item in SYSTEM_STACKS:
                continue
            
            # Check if it looks like a stack (has docker-compose file)
            if get_docker_compose_file(item_path):
                stacks.append(item)
    
    except Exception:
        pass
    
    return sorted(stacks)


def get_stack_info(stack_name: str) -> Dict[str, Any]:
    """
    Get detailed information about a stack.
    """
    stack_path = get_stack_path(stack_name)
    
    info = {
        "name": stack_name,
        "path": stack_path,
        "exists": os.path.exists(stack_path),
        "has_env": os.path.exists(os.path.join(stack_path, ".env")),
        "has_compose": get_docker_compose_file(stack_path) is not None,
        "status": "error",
        "containers": [],
        "env_vars": {},
        "stack_type": None,
        "domain": None,
        "image": None,
        "port": None
    }
    
    if not info["exists"]:
        return info
    
    # Get status and containers
    info["status"] = get_stack_status(stack_name)
    info["containers"] = get_container_status(stack_name)
    
    # Read env vars
    env_vars = read_env_file(stack_path)
    info["env_vars"] = env_vars
    
    # Extract common values from env
    info["domain"] = env_vars.get("APP_DOMAIN")
    info["image"] = env_vars.get("APP_IMAGE")
    
    # Try to parse port
    try:
        port_str = env_vars.get("APP_PORT", "")
        if port_str:
            info["port"] = int(port_str)
    except ValueError:
        pass
    
    # Determine stack type
    if env_vars.get("STACKWIZ_STACK_TYPE") == "pocketbase":
        info["stack_type"] = "pocketbase"
    elif info["image"] and "pocketbase" in info["image"].lower():
        info["stack_type"] = "pocketbase"
    else:
        info["stack_type"] = "generic"
    
    # Get creation time
    try:
        stat_info = os.stat(stack_path)
        info["created_at"] = str(stat_info.st_ctime)
    except Exception:
        pass
    
    return info