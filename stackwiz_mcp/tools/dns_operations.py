"""
DNS Operations Tools - Manages DNS records
"""

from typing import Dict, Any, List
import os
import requests
from ..utils.logging import get_logger
from ..models.stack_models import DnsRecord, DnsRecordType
from ..utils.stack_utils import BASE_DIR

logger = get_logger(__name__)


class DNSManager:
    """Manage DNS records via Cloudflare API."""
    
    def __init__(self):
        self.domain = "rbnk.uk"
        self.api_token = self._get_api_token()
        self.api_base = "https://api.cloudflare.com/client/v4"
        
    def _get_api_token(self) -> str:
        """Get Cloudflare API token from environment or Traefik config."""
        # Try environment variable first
        token = os.environ.get("CF_API_TOKEN", "")
        
        if not token:
            # Try to read from Traefik env file
            traefik_env = os.path.join(BASE_DIR, "traefik", ".env")
            if os.path.exists(traefik_env):
                try:
                    with open(traefik_env, 'r') as f:
                        for line in f:
                            if line.startswith("CF_API_TOKEN=") or line.startswith("CF_DNS_API_TOKEN="):
                                token = line.split("=", 1)[1].strip().strip('"\'')
                                break
                except Exception:
                    pass
        
        return token if token else None
    
    def _get_public_ip(self) -> str:
        """Get the server's public IP address."""
        ip_services = [
            "https://ipv4.icanhazip.com",
            "https://api.ipify.org",
            "https://ifconfig.me/ip"
        ]
        
        for service in ip_services:
            try:
                response = requests.get(service, timeout=5)
                if response.status_code == 200:
                    return response.text.strip()
            except Exception:
                continue
        
        return None
    
    def _get_zone_id(self) -> str:
        """Get Cloudflare zone ID for the domain."""
        if not self.api_token:
            return None
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(
                f"{self.api_base}/zones?name={self.domain}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get("success") and data.get("result"):
                    return data["result"][0]["id"]
        except Exception:
            pass
        
        return None


class CreateDnsRecordTool:
    """Tool for creating DNS records"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        
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
            
            try:
                # Validate record type
                try:
                    record_type = DnsRecordType(type)
                except ValueError:
                    return {
                        "success": False,
                        "message": f"Invalid record type: {type}",
                        "error": f"Valid types are: {', '.join([t.value for t in DnsRecordType])}"
                    }
                
                # Initialize DNS manager
                dns_manager = DNSManager()
                
                if not dns_manager.api_token:
                    return {
                        "success": False,
                        "message": "Cloudflare API token not configured",
                        "error": "Missing CF_API_TOKEN in environment or Traefik .env file"
                    }
                
                # Get zone ID
                zone_id = dns_manager._get_zone_id()
                if not zone_id:
                    return {
                        "success": False,
                        "message": "Failed to get Cloudflare zone ID",
                        "error": "Unable to access zone for rbnk.uk"
                    }
                
                # Handle AUTO value for A records
                target = value
                if record_type == DnsRecordType.A and value == "AUTO":
                    target = dns_manager._get_public_ip()
                    if not target:
                        return {
                            "success": False,
                            "message": "Failed to auto-detect public IP",
                            "error": "Could not determine server's public IP address"
                        }
                
                # Prepare API request
                headers = {
                    "Authorization": f"Bearer {dns_manager.api_token}",
                    "Content-Type": "application/json"
                }
                
                data = {
                    "type": record_type.value,
                    "name": f"{subdomain}.{dns_manager.domain}",
                    "content": target,
                    "ttl": 1,  # Auto TTL
                    "proxied": proxied and record_type.value in ["A", "AAAA", "CNAME"]
                }
                
                # Add priority for MX records
                if record_type == DnsRecordType.MX and priority is not None:
                    data["priority"] = priority
                
                # Create the record
                response = requests.post(
                    f"{dns_manager.api_base}/zones/{zone_id}/dns_records",
                    headers=headers,
                    json=data,
                    timeout=10
                )
                
                result = response.json()
                
                if result.get("success"):
                    record_data = result.get("result", {})
                    return {
                        "success": True,
                        "message": f"DNS record created successfully",
                        "details": {
                            "subdomain": subdomain,
                            "full_domain": f"{subdomain}.{dns_manager.domain}",
                            "type": record_type.value,
                            "target": target,
                            "proxied": proxied,
                            "record_id": record_data.get("id")
                        }
                    }
                else:
                    errors = result.get("errors", [])
                    error_msg = errors[0]["message"] if errors else "Unknown error"
                    return {
                        "success": False,
                        "message": f"Failed to create DNS record: {error_msg}",
                        "error": error_msg
                    }
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"DNS API request error: {str(e)}")
                return {
                    "success": False,
                    "message": f"DNS API request failed: {str(e)}",
                    "error": str(e)
                }
            except Exception as e:
                logger.error(f"DNS creation error: {str(e)}")
                return {
                    "success": False,
                    "message": f"Failed to create DNS record: {str(e)}",
                    "error": str(e)
                }


class ListDnsRecordsTool:
    """Tool for listing DNS records"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        
        @mcp.tool()
        async def list_dns_records(
            filter: str = None
        ) -> List[Dict[str, Any]]:
            """
            List DNS records
            
            Args:
                filter: Filter records by name
                
            Returns:
                List of DNS records
            """
            server_state.increment_operations()
            
            try:
                dns_manager = DNSManager()
                
                # Check if API token is configured
                if not dns_manager.api_token:
                    return [{
                        "error": "Cloudflare API token not configured",
                        "message": "Please configure CF_API_TOKEN in environment or Traefik .env file"
                    }]
                
                # Get zone ID
                zone_id = dns_manager._get_zone_id()
                if not zone_id:
                    return [{
                        "error": "Failed to get Cloudflare zone ID",
                        "message": "Unable to access Cloudflare zone for rbnk.uk"
                    }]
                
                # Fetch DNS records
                headers = {
                    "Authorization": f"Bearer {dns_manager.api_token}",
                    "Content-Type": "application/json"
                }
                
                response = requests.get(
                    f"{dns_manager.api_base}/zones/{zone_id}/dns_records?per_page=100",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success"):
                        records = data.get("result", [])
                        
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
                        
                        return formatted_records
                    else:
                        return [{
                            "error": "API request failed",
                            "message": "Cloudflare API returned an error"
                        }]
                else:
                    return [{
                        "error": f"HTTP {response.status_code}",
                        "message": f"API request failed with status {response.status_code}"
                    }]
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"DNS API request error: {str(e)}")
                return [{
                    "error": "API request failed",
                    "message": f"Failed to connect to Cloudflare API: {str(e)}"
                }]
            except Exception as e:
                logger.error(f"DNS listing error: {str(e)}")
                return [{
                    "error": str(e),
                    "message": f"Failed to list DNS records: {str(e)}"
                }]


class UpdateDnsProxyTool:
    """Tool for updating DNS proxy status"""
    
    @staticmethod
    def register(mcp, server_state):
        """Register the tool with the MCP server"""
        
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
            
            try:
                dns_manager = DNSManager()
                
                if not dns_manager.api_token:
                    return {
                        "success": False,
                        "message": "Cloudflare API token not configured",
                        "error": "Missing CF_API_TOKEN in environment or Traefik .env file"
                    }
                
                zone_id = dns_manager._get_zone_id()
                if not zone_id:
                    return {
                        "success": False,
                        "message": "Failed to get Cloudflare zone ID",
                        "error": "Unable to access zone for rbnk.uk"
                    }
                
                # Find the record
                headers = {
                    "Authorization": f"Bearer {dns_manager.api_token}",
                    "Content-Type": "application/json"
                }
                
                full_domain = f"{subdomain}.{dns_manager.domain}"
                response = requests.get(
                    f"{dns_manager.api_base}/zones/{zone_id}/dns_records?name={full_domain}",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code != 200:
                    return {
                        "success": False,
                        "message": f"Failed to fetch DNS records: HTTP {response.status_code}",
                        "error": f"API request failed with status {response.status_code}"
                    }
                
                data = response.json()
                if not data.get("success") or not data.get("result"):
                    return {
                        "success": False,
                        "message": f"No DNS record found for {full_domain}",
                        "error": "Record not found"
                    }
                
                records = data.get("result", [])
                
                # Find the first proxyable record (A, AAAA, or CNAME)
                target_record = None
                for record in records:
                    if record["type"] in ["A", "AAAA", "CNAME"]:
                        target_record = record
                        break
                
                if not target_record:
                    return {
                        "success": False,
                        "message": f"No proxyable record found for {full_domain}",
                        "error": "Only A, AAAA, and CNAME records can be proxied"
                    }
                
                # Update the proxy status
                update_data = {
                    "proxied": enable
                }
                
                update_response = requests.patch(
                    f"{dns_manager.api_base}/zones/{zone_id}/dns_records/{target_record['id']}",
                    headers=headers,
                    json=update_data,
                    timeout=10
                )
                
                result = update_response.json()
                
                if result.get("success"):
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
                    errors = result.get("errors", [])
                    error_msg = errors[0]["message"] if errors else "Unknown error"
                    return {
                        "success": False,
                        "message": f"Failed to update proxy status: {error_msg}",
                        "error": error_msg
                    }
                    
            except requests.exceptions.RequestException as e:
                logger.error(f"DNS API request error: {str(e)}")
                return {
                    "success": False,
                    "message": f"DNS API request failed: {str(e)}",
                    "error": str(e)
                }
            except Exception as e:
                logger.error(f"DNS proxy update error: {str(e)}")
                return {
                    "success": False,
                    "message": f"Failed to update DNS proxy: {str(e)}",
                    "error": str(e)
                }