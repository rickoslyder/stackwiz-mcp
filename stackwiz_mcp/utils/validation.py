"""
Validation utilities for StackWiz MCP Server
"""

import re
from typing import Optional, Tuple


def validate_stack_name(name: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a stack name
    
    Args:
        name: Stack name to validate
        
    Returns:
        Tuple of (valid, error_message)
    """
    if not name:
        return False, "Stack name cannot be empty"
    
    if len(name) < 3:
        return False, "Stack name must be at least 3 characters"
    
    if len(name) > 50:
        return False, "Stack name must be less than 50 characters"
    
    if not re.match(r"^[a-z0-9-]+$", name):
        return False, "Stack name must contain only lowercase letters, numbers, and hyphens"
    
    if name.startswith("-") or name.endswith("-"):
        return False, "Stack name cannot start or end with a hyphen"
    
    if "--" in name:
        return False, "Stack name cannot contain consecutive hyphens"
    
    return True, None


def validate_domain(domain: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a domain name
    
    Args:
        domain: Domain to validate
        
    Returns:
        Tuple of (valid, error_message)
    """
    if not domain:
        return False, "Domain cannot be empty"
    
    # Basic domain validation
    domain_regex = re.compile(
        r"^(?:[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?$"
    )
    
    if not domain_regex.match(domain):
        return False, "Invalid domain format"
    
    if len(domain) > 253:
        return False, "Domain name too long"
    
    return True, None


def validate_port(port: int) -> Tuple[bool, Optional[str]]:
    """
    Validate a port number
    
    Args:
        port: Port number to validate
        
    Returns:
        Tuple of (valid, error_message)
    """
    if port is None:
        return False, "Port cannot be None"
    
    if not isinstance(port, int):
        return False, "Port must be an integer"
    
    if port < 1 or port > 65535:
        return False, "Port must be between 1 and 65535"
    
    # Check for commonly reserved ports
    reserved_ports = [22, 53, 80, 443]
    if port in reserved_ports:
        return False, f"Port {port} is reserved for system use"
    
    return True, None


def validate_docker_image(image: str) -> Tuple[bool, Optional[str]]:
    """
    Validate a Docker image name
    
    Args:
        image: Docker image name to validate
        
    Returns:
        Tuple of (valid, error_message)
    """
    if not image:
        return False, "Docker image cannot be empty"
    
    # Basic image name validation
    # Format: [registry/]namespace/name[:tag]
    image_regex = re.compile(
        r"^(?:(?:[a-zA-Z0-9](?:[a-zA-Z0-9-_]*[a-zA-Z0-9])?\.)*[a-zA-Z0-9](?:[a-zA-Z0-9-_]*[a-zA-Z0-9])?(?::[0-9]+)?/)?"
        r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"
        r"(?::[a-zA-Z0-9_][a-zA-Z0-9._-]{0,127})?$"
    )
    
    if not image_regex.match(image):
        return False, "Invalid Docker image format"
    
    return True, None


def validate_environment_key(key: str) -> Tuple[bool, Optional[str]]:
    """
    Validate an environment variable key
    
    Args:
        key: Environment variable key to validate
        
    Returns:
        Tuple of (valid, error_message)
    """
    if not key:
        return False, "Environment variable key cannot be empty"
    
    if not re.match(r"^[A-Z_][A-Z0-9_]*$", key):
        return False, "Environment variable keys must be uppercase letters, numbers, and underscores, starting with a letter or underscore"
    
    return True, None