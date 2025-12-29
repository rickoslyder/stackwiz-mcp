"""
Health check utilities for StackWiz MCP Server
"""

import asyncio
import os
import socket
from pathlib import Path
from typing import Dict, Any, List, Tuple
from datetime import datetime

import aiofiles
import httpx
from docker import DockerClient
from docker.errors import DockerException

from ..config import get_config
from .logging import get_logger

logger = get_logger(__name__)


class HealthCheck:
    """Base class for health checks"""
    
    def __init__(self, name: str, critical: bool = False):
        self.name = name
        self.critical = critical
    
    async def check(self) -> Tuple[bool, str]:
        """
        Perform health check
        
        Returns:
            Tuple of (healthy, message)
        """
        raise NotImplementedError


class DockerHealthCheck(HealthCheck):
    """Check Docker daemon connectivity"""
    
    def __init__(self):
        super().__init__("docker", critical=True)
    
    async def check(self) -> Tuple[bool, str]:
        """Check if Docker daemon is accessible"""
        try:
            config = get_config()
            
            # Run in thread pool to avoid blocking
            loop = asyncio.get_event_loop()
            
            def _check_docker():
                client = DockerClient(base_url=f"unix://{config.docker.socket_path}")
                client.ping()
                client.close()
                return True
            
            await loop.run_in_executor(None, _check_docker)
            return True, "Docker daemon is accessible"
            
        except Exception as e:
            logger.error(f"Docker health check failed: {e}")
            return False, f"Cannot connect to Docker daemon: {str(e)}"


class FileSystemHealthCheck(HealthCheck):
    """Check filesystem access"""
    
    def __init__(self):
        super().__init__("filesystem", critical=True)
    
    async def check(self) -> Tuple[bool, str]:
        """Check if we can read/write to base directory"""
        try:
            config = get_config()
            test_file = config.base_dir / ".health_check"
            
            # Try to write
            async with aiofiles.open(test_file, "w") as f:
                await f.write(f"health_check_{datetime.utcnow().isoformat()}")
            
            # Try to read
            async with aiofiles.open(test_file, "r") as f:
                content = await f.read()
            
            # Clean up
            test_file.unlink(missing_ok=True)
            
            return True, "Filesystem access is working"
            
        except Exception as e:
            logger.error(f"Filesystem health check failed: {e}")
            return False, f"Filesystem access error: {str(e)}"


class DnsHealthCheck(HealthCheck):
    """Check DNS API connectivity"""
    
    def __init__(self):
        super().__init__("dns", critical=False)
    
    async def check(self) -> Tuple[bool, str]:
        """Check if DNS API is accessible"""
        try:
            config = get_config()
            
            if not config.dns.api_token:
                return False, "DNS API token not configured"
            
            # Check Cloudflare API - verify token by listing zones
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"https://api.cloudflare.com/client/v4/zones?name={config.dns.zone_name}",
                    headers={
                        "Authorization": f"Bearer {config.dns.api_token}",
                        "Content-Type": "application/json"
                    },
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    return True, "DNS API is accessible"
                else:
                    return False, f"DNS API returned status {response.status_code}"
                    
        except Exception as e:
            logger.error(f"DNS health check failed: {e}")
            return False, f"Cannot connect to DNS API: {str(e)}"


class NetworkHealthCheck(HealthCheck):
    """Check network connectivity"""
    
    def __init__(self):
        super().__init__("network", critical=False)
    
    async def check(self) -> Tuple[bool, str]:
        """Check if we can resolve DNS and connect to external services"""
        try:
            # Check DNS resolution
            loop = asyncio.get_event_loop()
            
            def _check_dns():
                socket.gethostbyname("cloudflare.com")
                return True
            
            await loop.run_in_executor(None, _check_dns)
            
            # Check external connectivity with a simple HTTPS request
            async with httpx.AsyncClient() as client:
                # Use Cloudflare's CDN endpoint which is always available
                response = await client.get("https://www.cloudflare.com/cdn-cgi/trace", timeout=5.0)
                if response.status_code == 200:
                    return True, "Network connectivity is working"
                else:
                    return False, f"External connectivity test returned status {response.status_code}"
                    
        except Exception as e:
            logger.error(f"Network health check failed: {e}")
            return False, f"Network connectivity error: {str(e)}"


class TraefikHealthCheck(HealthCheck):
    """Check Traefik connectivity"""
    
    def __init__(self):
        super().__init__("traefik", critical=False)
    
    async def check(self) -> Tuple[bool, str]:
        """Check if Traefik is accessible"""
        try:
            # Traefik API is exposed on port 8080 inside the container
            # The correct endpoint for health/ping is /api/rawdata or /ping
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    "http://traefik:8080/ping",
                    timeout=5.0
                )
                
                if response.status_code == 200:
                    return True, "Traefik is accessible"
                else:
                    return False, f"Traefik API returned status {response.status_code}"
                    
        except Exception as e:
            # Traefik might not be accessible from this container
            logger.debug(f"Traefik health check failed: {e}")
            return False, f"Cannot connect to Traefik: {str(e)}"


class HealthChecker:
    """Main health checker that runs all checks"""
    
    def __init__(self):
        self.checks: List[HealthCheck] = [
            DockerHealthCheck(),
            FileSystemHealthCheck(),
            DnsHealthCheck(),
            NetworkHealthCheck(),
            TraefikHealthCheck()
        ]
    
    async def check_all(self) -> Dict[str, Any]:
        """
        Run all health checks
        
        Returns:
            Dictionary with overall health status and individual check results
        """
        results = {}
        all_healthy = True
        critical_healthy = True
        
        # Run checks concurrently
        tasks = []
        for check in self.checks:
            tasks.append(self._run_check(check))
        
        check_results = await asyncio.gather(*tasks, return_exceptions=True)
        
        # Process results
        for check, result in zip(self.checks, check_results):
            if isinstance(result, Exception):
                # Check failed with exception
                results[check.name] = {
                    "healthy": False,
                    "message": f"Check failed: {str(result)}",
                    "critical": check.critical
                }
                all_healthy = False
                if check.critical:
                    critical_healthy = False
            else:
                # Normal result
                healthy, message = result
                results[check.name] = {
                    "healthy": healthy,
                    "message": message,
                    "critical": check.critical
                }
                if not healthy:
                    all_healthy = False
                    if check.critical:
                        critical_healthy = False
        
        return {
            "healthy": critical_healthy,  # Overall health based on critical checks
            "all_healthy": all_healthy,   # All checks including non-critical
            "timestamp": datetime.utcnow().isoformat(),
            "checks": results
        }
    
    async def _run_check(self, check: HealthCheck) -> Tuple[bool, str]:
        """Run a single health check with timeout"""
        try:
            return await asyncio.wait_for(check.check(), timeout=10.0)
        except asyncio.TimeoutError:
            return False, "Health check timed out"
        except Exception as e:
            return False, f"Health check error: {str(e)}"
    
    async def get_readiness(self) -> bool:
        """Check if server is ready to handle requests (critical checks only)"""
        results = await self.check_all()
        return results["healthy"]
    
    async def get_liveness(self) -> bool:
        """Check if server is alive (basic checks)"""
        # Just check if we can respond - actual check logic could be simpler
        return True