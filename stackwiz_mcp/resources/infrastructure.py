"""
Infrastructure Resource - Provides infrastructure information
"""

import json
import os
import re
from typing import Dict, Any, List
from ..utils.logging import get_logger
from ..utils.stack_utils import run_command, list_stacks, get_stack_path, read_env_file

logger = get_logger(__name__)


class InfrastructureResource:
    """Resource for accessing infrastructure information"""
    
    @staticmethod
    def register(mcp):
        """Register the resource with the MCP server"""
        
        @mcp.resource("infra://networks")
        async def list_networks() -> List[str]:
            """List available Docker networks"""
            try:
                # Run docker network ls command
                success, stdout, stderr = run_command(
                    ["docker", "network", "ls", "--format", "{{.Name}}"]
                )
                
                if not success:
                    logger.error(f"Failed to list Docker networks: {stderr}")
                    return ["traefik_proxy", "supabase_default"]  # Fallback
                
                # Parse network names from output
                networks = []
                for line in stdout.strip().split('\n'):
                    if line and not line in ["bridge", "host", "none"]:  # Skip default networks
                        networks.append(line)
                
                return sorted(networks) if networks else ["traefik_proxy", "supabase_default"]
                
            except Exception as e:
                logger.error(f"Error listing networks: {str(e)}")
                return ["traefik_proxy", "supabase_default"]  # Fallback
        
        @mcp.resource("infra://domains")
        async def list_domains() -> List[str]:
            """List configured domains by scanning .env files"""
            try:
                domains = set()
                
                # Get all stacks (including system stacks)
                stacks = list_stacks(include_system=True)
                
                for stack_name in stacks:
                    stack_path = get_stack_path(stack_name)
                    env_vars = read_env_file(stack_path)
                    
                    # Look for domain-related environment variables
                    for key, value in env_vars.items():
                        if any(domain_key in key.upper() for domain_key in ["DOMAIN", "HOST", "URL"]):
                            # Extract domain from value
                            # Handle URLs like https://example.com or just example.com
                            domain_match = re.search(r'(?:https?://)?([a-zA-Z0-9.-]+\.[a-zA-Z]{2,})', value)
                            if domain_match:
                                domain = domain_match.group(1)
                                domains.add(domain)
                                
                                # Also add the base domain if it's a subdomain
                                parts = domain.split('.')
                                if len(parts) > 2:
                                    base_domain = '.'.join(parts[-2:])
                                    domains.add(base_domain)
                
                # Add known base domain
                domains.add("rbnk.uk")
                
                return sorted(list(domains))
                
            except Exception as e:
                logger.error(f"Error listing domains: {str(e)}")
                return ["rbnk.uk"]  # Fallback
        
        @mcp.resource("infra://ports")
        async def get_port_usage() -> Dict[int, str]:
            """Get port usage map by scanning running containers"""
            try:
                port_map = {}
                
                # Get container port mappings using docker ps
                success, stdout, stderr = run_command([
                    "docker", "ps", "--format", 
                    "table {{.Names}}\t{{.Ports}}"
                ])
                
                if not success:
                    logger.error(f"Failed to get container ports: {stderr}")
                    return {80: "traefik", 443: "traefik", 5432: "postgresql"}  # Fallback
                
                # Parse the output
                lines = stdout.strip().split('\n')
                if len(lines) > 1:  # Skip header
                    for line in lines[1:]:
                        if '\t' in line:
                            container_name, ports_str = line.split('\t', 1)
                            
                            # Parse port mappings like "0.0.0.0:80->80/tcp, 443/tcp"
                            port_patterns = [
                                r'0\.0\.0\.0:(\d+)->',  # Host port mapping
                                r':::(\d+)->',           # IPv6 port mapping
                                r'^(\d+)/tcp',           # Container port only
                                r'^(\d+)/udp'            # UDP port
                            ]
                            
                            for pattern in port_patterns:
                                matches = re.findall(pattern, ports_str)
                                for port_str in matches:
                                    try:
                                        port = int(port_str)
                                        # Store the service name (remove stack prefix if present)
                                        service_name = container_name.split('-')[-1] if '-' in container_name else container_name
                                        port_map[port] = service_name
                                    except ValueError:
                                        continue
                
                # Add common known ports if not found
                if 80 not in port_map:
                    port_map[80] = "traefik"
                if 443 not in port_map:
                    port_map[443] = "traefik"
                
                # Sort by port number for consistent output
                return dict(sorted(port_map.items()))
                
            except Exception as e:
                logger.error(f"Error getting port usage: {str(e)}")
                return {80: "traefik", 443: "traefik", 5432: "postgresql"}  # Fallback