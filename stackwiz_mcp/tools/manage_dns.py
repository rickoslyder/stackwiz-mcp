"""
DNS record creation and management for stacks.

This tool provides functionality to:
- Create DNS A records for new services
- Auto-detect public IP address
- Integrate with Cloudflare via API
- Support for various record types
"""

import os
import subprocess
import json
import requests
from typing import Dict, Any, Optional

from ..models.stack_models import DnsRecord, OperationResult
from ..utils.stack_utils import BASE_DIR


class DNSManager:
    """Manage DNS records via Cloudflare API."""
    
    def __init__(self):
        self.domain = "rbnk.uk"
        self.api_token = self._get_api_token()
        self.api_base = "https://api.cloudflare.com/client/v4"
        
    def _get_api_token(self) -> Optional[str]:
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
    
    def _get_public_ip(self) -> Optional[str]:
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
    
    def _get_zone_id(self) -> Optional[str]:
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
    
    def check_record_exists(self, subdomain: str, record_type: str = "A") -> bool:
        """Check if a DNS record already exists."""
        zone_id = self._get_zone_id()
        if not zone_id:
            return False
        
        full_domain = f"{subdomain}.{self.domain}"
        
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        try:
            response = requests.get(
                f"{self.api_base}/zones/{zone_id}/dns_records?type={record_type}&name={full_domain}",
                headers=headers,
                timeout=10
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("result_info", {}).get("count", 0) > 0
        except Exception:
            pass
        
        return False
    
    def create_record(self, params: DnsRecord) -> Dict[str, Any]:
        """Create a DNS record."""
        if not self.api_token:
            return {
                "success": False,
                "message": "Cloudflare API token not configured",
                "error": "Missing CF_API_TOKEN"
            }
        
        zone_id = self._get_zone_id()
        if not zone_id:
            return {
                "success": False,
                "message": "Failed to get Cloudflare zone ID",
                "error": "Zone lookup failed"
            }
        
        # Handle AUTO value for A records
        target = params.value
        if params.type == "A" and target == "AUTO":
            target = self._get_public_ip()
            if not target:
                return {
                    "success": False,
                    "message": "Failed to auto-detect public IP",
                    "error": "IP detection failed"
                }
        
        # Check if record already exists
        if self.check_record_exists(params.subdomain, params.type.value):
            return {
                "success": True,
                "message": f"DNS record already exists for {params.subdomain}.{self.domain}",
                "details": {
                    "subdomain": params.subdomain,
                    "full_domain": f"{params.subdomain}.{self.domain}",
                    "type": params.type.value,
                    "already_exists": True
                }
            }
        
        # Create the record
        headers = {
            "Authorization": f"Bearer {self.api_token}",
            "Content-Type": "application/json"
        }
        
        data = {
            "type": params.type.value,
            "name": f"{params.subdomain}.{self.domain}",
            "content": target,
            "ttl": 1,  # Auto TTL
            "proxied": params.proxied and params.type.value in ["A", "AAAA", "CNAME"]
        }
        
        try:
            response = requests.post(
                f"{self.api_base}/zones/{zone_id}/dns_records",
                headers=headers,
                json=data,
                timeout=10
            )
            
            result = response.json()
            
            if result.get("success"):
                return {
                    "success": True,
                    "message": f"DNS record created successfully",
                    "details": {
                        "subdomain": params.subdomain,
                        "full_domain": f"{params.subdomain}.{self.domain}",
                        "type": params.type.value,
                        "target": target,
                        "proxied": params.proxied,
                        "record_id": result.get("result", {}).get("id")
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
                
        except Exception as e:
            return {
                "success": False,
                "message": f"DNS API error: {str(e)}",
                "error": str(e)
            }


def create_dns_record(params: DnsRecord) -> OperationResult:
    """
    Create a DNS record for a stack.
    
    Args:
        params: DNS record parameters
        
    Returns:
        OperationResult
    """
    # First try using the API
    dns_manager = DNSManager()
    result = dns_manager.create_record(params)
    
    if result["success"]:
        return OperationResult(
            success=True,
            operation="create_dns_record",
            stack_name=params.subdomain,
            message=result["message"]
        )
    
    # If API failed due to missing token, try the shell script
    if "CF_API_TOKEN" in result.get("error", ""):
        script_result = create_dns_via_script(params)
        return script_result
    
    # Otherwise return the API error
    return OperationResult(
        success=False,
        operation="create_dns_record",
        stack_name=params.subdomain,
        message=result["message"],
        error=result.get("error", "Unknown error")
    )


def create_dns_via_script(params: DnsRecord) -> OperationResult:
    """
    Fallback to shell script for DNS creation.
    
    Args:
        params: DNS record parameters
        
    Returns:
        OperationResult
    """
    script_path = os.path.join(BASE_DIR, "_scripts", "cloudflare-dns-create.sh")
    
    if not os.path.exists(script_path):
        return OperationResult(
            success=False,
            operation="create_dns_record",
            stack_name=params.subdomain,
            message="DNS creation script not found",
            error="Missing cloudflare-dns-create.sh"
        )
    
    # Only supports A records via script
    if params.type != "A":
        return OperationResult(
            success=False,
            operation="create_dns_record",
            stack_name=params.subdomain,
            message="Shell script only supports A records",
            error="Unsupported record type for script"
        )
    
    try:
        cmd = [script_path, params.subdomain]
        if params.value != "AUTO":
            cmd.extend(["A", params.value])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            return OperationResult(
                success=True,
                operation="create_dns_record",
                stack_name=params.subdomain,
                message=f"DNS record created via script",
                output=result.stdout
            )
        else:
            return OperationResult(
                success=False,
                operation="create_dns_record",
                stack_name=params.subdomain,
                message="DNS creation script failed",
                error=result.stderr or result.stdout
            )
            
    except Exception as e:
        return OperationResult(
            success=False,
            operation="create_dns_record",
            stack_name=params.subdomain,
            message=f"Script execution error: {str(e)}",
            error=str(e)
        )


def list_dns_records() -> OperationResult:
    """
    List all DNS records for the domain.
    
    Returns:
        OperationResult with DNS records in output
    """
    dns_manager = DNSManager()
    
    if not dns_manager.api_token:
        return OperationResult(
            success=False,
            operation="list_dns_records",
            stack_name="dns",
            message="Cloudflare API token not configured",
            error="Missing CF_API_TOKEN"
        )
    
    zone_id = dns_manager._get_zone_id()
    if not zone_id:
        return OperationResult(
            success=False,
            operation="list_dns_records",
            stack_name="dns",
            message="Failed to get Cloudflare zone ID",
            error="Zone lookup failed"
        )
    
    headers = {
        "Authorization": f"Bearer {dns_manager.api_token}",
        "Content-Type": "application/json"
    }
    
    try:
        response = requests.get(
            f"{dns_manager.api_base}/zones/{zone_id}/dns_records?per_page=100",
            headers=headers,
            timeout=10
        )
        
        if response.status_code == 200:
            data = response.json()
            if data.get("success"):
                records = data.get("result", [])
                
                # Filter and format records
                formatted_records = []
                for record in records:
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
                
                return OperationResult(
                    success=True,
                    operation="list_dns_records",
                    stack_name="dns",
                    message=f"Found {len(formatted_records)} DNS records",
                    output=f"Domain: {dns_manager.domain}\nTotal records: {len(formatted_records)}"
                )
            else:
                return OperationResult(
                    success=False,
                    operation="list_dns_records",
                    stack_name="dns",
                    message="Failed to list DNS records",
                    error="API returned error"
                )
        else:
            return OperationResult(
                success=False,
                operation="list_dns_records",
                stack_name="dns",
                message=f"API request failed with status {response.status_code}",
                error=f"HTTP {response.status_code}"
            )
            
    except Exception as e:
        return OperationResult(
            success=False,
            operation="list_dns_records",
            stack_name="dns",
            message=f"Failed to list DNS records: {str(e)}",
            error=str(e)
        )


def update_dns_proxy(subdomain: str, enabled: bool) -> OperationResult:
    """
    Update the Cloudflare proxy status for a DNS record.
    
    Args:
        subdomain: The subdomain to update
        enabled: True to enable proxy, False to disable
        
    Returns:
        OperationResult
    """
    dns_manager = DNSManager()
    
    # First try API approach
    if dns_manager.api_token:
        zone_id = dns_manager._get_zone_id()
        if zone_id:
            full_domain = f"{subdomain}.{dns_manager.domain}"
            
            headers = {
                "Authorization": f"Bearer {dns_manager.api_token}",
                "Content-Type": "application/json"
            }
            
            try:
                # Find the record
                response = requests.get(
                    f"{dns_manager.api_base}/zones/{zone_id}/dns_records?name={full_domain}",
                    headers=headers,
                    timeout=10
                )
                
                if response.status_code == 200:
                    data = response.json()
                    if data.get("success") and data.get("result"):
                        records = data.get("result", [])
                        
                        if len(records) == 0:
                            return OperationResult(
                                success=False,
                                operation="update_dns_proxy",
                                stack_name=subdomain,
                                message=f"No DNS record found for {full_domain}",
                                error="Record not found"
                            )
                        
                        # Get the first A, AAAA, or CNAME record
                        target_record = None
                        for record in records:
                            if record["type"] in ["A", "AAAA", "CNAME"]:
                                target_record = record
                                break
                        
                        if not target_record:
                            return OperationResult(
                                success=False,
                                operation="update_dns_proxy",
                                stack_name=subdomain,
                                message="No proxyable record found (A, AAAA, or CNAME)",
                                error="No proxyable record"
                            )
                        
                        # Update the proxy status
                        update_data = {
                            "proxied": enabled
                        }
                        
                        update_response = requests.patch(
                            f"{dns_manager.api_base}/zones/{zone_id}/dns_records/{target_record['id']}",
                            headers=headers,
                            json=update_data,
                            timeout=10
                        )
                        
                        result = update_response.json()
                        
                        if result.get("success"):
                            status = "enabled" if enabled else "disabled"
                            return OperationResult(
                                success=True,
                                operation="update_dns_proxy",
                                stack_name=subdomain,
                                message=f"Cloudflare proxy {status} for {full_domain}"
                            )
                        else:
                            errors = result.get("errors", [])
                            error_msg = errors[0]["message"] if errors else "Unknown error"
                            return OperationResult(
                                success=False,
                                operation="update_dns_proxy",
                                stack_name=subdomain,
                                message=f"Failed to update proxy status: {error_msg}",
                                error=error_msg
                            )
                            
            except Exception as e:
                # Fall through to script method
                pass
    
    # Fallback to shell script
    script_path = os.path.join(BASE_DIR, "_scripts", "cloudflare-dns.sh")
    
    if not os.path.exists(script_path):
        return OperationResult(
            success=False,
            operation="update_dns_proxy",
            stack_name=subdomain,
            message="DNS management script not found",
            error="Missing cloudflare-dns.sh"
        )
    
    try:
        action = "on" if enabled else "off"
        cmd = [script_path, "proxy", subdomain, action]
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode == 0:
            status = "enabled" if enabled else "disabled"
            return OperationResult(
                success=True,
                operation="update_dns_proxy",
                stack_name=subdomain,
                message=f"Cloudflare proxy {status} for {subdomain}.{dns_manager.domain}",
                output=result.stdout
            )
        else:
            return OperationResult(
                success=False,
                operation="update_dns_proxy",
                stack_name=subdomain,
                message="Failed to update proxy status",
                error=result.stderr or result.stdout
            )
            
    except Exception as e:
        return OperationResult(
            success=False,
            operation="update_dns_proxy",
            stack_name=subdomain,
            message=f"Script execution error: {str(e)}",
            error=str(e)
        )

# NOTE: Tool definitions were removed as they are unused.
# The server.py module registers DNS tools directly using @mcp.tool() decorators.
# This module now only provides utility classes and functions for DNS operations.