#!/usr/bin/env python3
"""
StackWiz MCP Server - Alternative implementation using standard MCP protocol

This implements the MCP server without relying on FastMCP which may not be available.
"""

import asyncio
import json
import logging
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union
from datetime import datetime
import signal

from pydantic import BaseModel, Field

# Add the parent directory to the Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from stackwiz_mcp.config import get_config, Config
from stackwiz_mcp.utils.logging import setup_logging, get_logger
from stackwiz_mcp.utils.health import HealthChecker

# Initialize logging
logger = get_logger(__name__)

# Application metadata
APP_NAME = "stackwiz-mcp"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = "MCP server for managing Docker service stacks"


class MCPRequest(BaseModel):
    """MCP JSON-RPC request"""
    jsonrpc: str = "2.0"
    method: str
    params: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None


class MCPResponse(BaseModel):
    """MCP JSON-RPC response"""
    jsonrpc: str = "2.0"
    result: Optional[Any] = None
    error: Optional[Dict[str, Any]] = None
    id: Optional[Union[str, int]] = None


class MCPError:
    """Standard MCP error codes"""
    PARSE_ERROR = -32700
    INVALID_REQUEST = -32600
    METHOD_NOT_FOUND = -32601
    INVALID_PARAMS = -32602
    INTERNAL_ERROR = -32603


class StackWizMCPServer:
    """Main MCP server implementation"""
    
    def __init__(self):
        self.config = get_config()
        self.health_checker = HealthChecker()
        self.start_time = datetime.utcnow()
        self.operation_count = 0
        
        # Initialize methods
        self.methods = {
            # MCP standard methods
            "initialize": self.handle_initialize,
            "initialized": self.handle_initialized,
            "shutdown": self.handle_shutdown,
            "list_tools": self.handle_list_tools,
            "call_tool": self.handle_call_tool,
            "list_resources": self.handle_list_resources,
            "read_resource": self.handle_read_resource,
            "list_prompts": self.handle_list_prompts,
            "get_prompt": self.handle_get_prompt,
            
            # Server methods
            "health_check": self.handle_health_check,
            "server_info": self.handle_server_info,
        }
        
        # Tool definitions
        self.tools = {
            "create_stack": {
                "name": "create_stack",
                "description": "Create a new Docker service stack",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Stack name"},
                        "type": {"type": "string", "enum": ["generic", "pocketbase"]},
                        "image": {"type": "string", "description": "Docker image"},
                        "port": {"type": "integer", "description": "Container port"},
                        "domain": {"type": "string", "description": "Custom domain"},
                        "create_dns": {"type": "boolean", "description": "Create DNS record"},
                        "auto_start": {"type": "boolean", "description": "Start after creation"},
                        "environment": {"type": "object", "description": "Environment variables"}
                    },
                    "required": ["name"]
                }
            },
            "list_stacks": {
                "name": "list_stacks",
                "description": "List all existing Docker stacks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "filter": {"type": "string", "description": "Filter by name"},
                        "include_status": {"type": "boolean", "description": "Include status"},
                        "sort_by": {"type": "string", "enum": ["name", "created", "status"]}
                    }
                }
            },
            "manage_stack": {
                "name": "manage_stack",
                "description": "Perform operations on existing stacks",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "stack_name": {"type": "string", "description": "Stack name"},
                        "action": {"type": "string", "enum": ["start", "stop", "restart", "remove", "logs"]},
                        "follow_logs": {"type": "boolean", "description": "Follow logs"},
                        "tail_lines": {"type": "integer", "description": "Log lines to show"}
                    },
                    "required": ["stack_name", "action"]
                }
            },
            "create_dns_record": {
                "name": "create_dns_record",
                "description": "Create a DNS record",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "subdomain": {"type": "string", "description": "Subdomain"},
                        "type": {"type": "string", "enum": ["A", "CNAME", "MX", "TXT"]},
                        "value": {"type": "string", "description": "Record value"},
                        "priority": {"type": "integer", "description": "MX priority"},
                        "proxied": {"type": "boolean", "description": "Enable proxy"}
                    },
                    "required": ["subdomain"]
                }
            },
            "validate_stack_config": {
                "name": "validate_stack_config",
                "description": "Validate a stack configuration",
                "inputSchema": {
                    "type": "object",
                    "properties": {
                        "config": {"type": "object", "description": "Stack configuration"},
                        "check_conflicts": {"type": "boolean", "description": "Check conflicts"}
                    },
                    "required": ["config"]
                }
            }
        }
        
        # Resource definitions
        self.resources = {
            "stack://list": {
                "uri": "stack://list",
                "name": "Stack List",
                "description": "List all stacks",
                "mimeType": "application/json"
            },
            "template://list": {
                "uri": "template://list",
                "name": "Template List",
                "description": "List available templates",
                "mimeType": "application/json"
            },
            "infra://networks": {
                "uri": "infra://networks",
                "name": "Docker Networks",
                "description": "Available Docker networks",
                "mimeType": "application/json"
            }
        }
        
        # Prompt definitions
        self.prompts = {
            "deploy-web-app": {
                "name": "deploy-web-app",
                "description": "Interactive prompt for deploying web applications",
                "arguments": []
            },
            "setup-database": {
                "name": "setup-database",
                "description": "Guided database deployment with best practices",
                "arguments": []
            },
            "create-api-service": {
                "name": "create-api-service",
                "description": "API service deployment with monitoring",
                "arguments": []
            }
        }
    
    async def handle_request(self, request: MCPRequest) -> MCPResponse:
        """Handle incoming MCP request"""
        self.operation_count += 1
        
        try:
            method = self.methods.get(request.method)
            if not method:
                return MCPResponse(
                    id=request.id,
                    error={
                        "code": MCPError.METHOD_NOT_FOUND,
                        "message": f"Method not found: {request.method}"
                    }
                )
            
            result = await method(request.params or {})
            return MCPResponse(id=request.id, result=result)
            
        except Exception as e:
            logger.error(f"Error handling request: {e}", exc_info=True)
            return MCPResponse(
                id=request.id,
                error={
                    "code": MCPError.INTERNAL_ERROR,
                    "message": str(e)
                }
            )
    
    async def handle_initialize(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle initialize request"""
        logger.info("Initializing MCP server")
        
        return {
            "protocolVersion": "0.1.0",
            "capabilities": {
                "tools": True,
                "resources": True,
                "prompts": True,
                "logging": True
            },
            "serverInfo": {
                "name": APP_NAME,
                "version": APP_VERSION,
                "description": APP_DESCRIPTION
            }
        }
    
    async def handle_initialized(self, params: Dict[str, Any]) -> None:
        """Handle initialized notification"""
        logger.info("MCP server initialized")
        return None
    
    async def handle_shutdown(self, params: Dict[str, Any]) -> None:
        """Handle shutdown request"""
        logger.info("Shutting down MCP server")
        return None
    
    async def handle_list_tools(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available tools"""
        return {
            "tools": list(self.tools.values())
        }
    
    async def handle_call_tool(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Call a tool"""
        tool_name = params.get("name")
        tool_params = params.get("arguments", {})
        
        if tool_name not in self.tools:
            raise ValueError(f"Unknown tool: {tool_name}")
        
        # This file is not used - the actual implementation is in server.py
        raise NotImplementedError(f"Tool {tool_name} should be implemented in server.py")
    
    async def handle_list_resources(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available resources"""
        return {
            "resources": list(self.resources.values())
        }
    
    async def handle_read_resource(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Read a resource"""
        uri = params.get("uri")
        
        if uri not in self.resources:
            raise ValueError(f"Unknown resource: {uri}")
        
        # TODO: Implement actual resource reading
        logger.info(f"Reading resource: {uri}")
        
        # Mock responses
        if uri == "stack://list":
            return {"contents": json.dumps({"stacks": []})}
        elif uri == "template://list":
            return {"contents": json.dumps({"templates": ["generic", "pocketbase"]})}
        elif uri == "infra://networks":
            return {"contents": json.dumps({"networks": ["traefik_proxy", "supabase_default"]})}
        else:
            return {"contents": json.dumps({"data": f"Resource {uri}"})}
    
    async def handle_list_prompts(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """List available prompts"""
        return {
            "prompts": list(self.prompts.values())
        }
    
    async def handle_get_prompt(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Get a prompt"""
        name = params.get("name")
        
        if name not in self.prompts:
            raise ValueError(f"Unknown prompt: {name}")
        
        # TODO: Return actual prompt content
        if name == "deploy-web-app":
            content = """I'll help you deploy a web application. Please provide:
1. Application name
2. Application type (static, Node.js, Python, etc.)
3. Domain preference
4. Database requirements
5. Environment variables needed"""
        else:
            content = f"Prompt content for {name}"
        
        return {
            "description": self.prompts[name]["description"],
            "messages": [
                {
                    "role": "assistant",
                    "content": content
                }
            ]
        }
    
    async def handle_health_check(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle health check"""
        health_status = await self.health_checker.check_all()
        
        return {
            "status": "healthy" if health_status["healthy"] else "unhealthy",
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            "operation_count": self.operation_count,
            "checks": health_status["checks"]
        }
    
    async def handle_server_info(self, params: Dict[str, Any]) -> Dict[str, Any]:
        """Handle server info request"""
        return {
            "name": APP_NAME,
            "version": APP_VERSION,
            "description": APP_DESCRIPTION,
            "environment": self.config.environment.value,
            "base_directory": str(self.config.base_dir),
            "uptime_seconds": (datetime.utcnow() - self.start_time).total_seconds(),
            "operation_count": self.operation_count
        }
    
    async def run_stdio(self):
        """Run server in stdio mode"""
        logger.info("Starting StackWiz MCP server in stdio mode")
        
        reader = asyncio.StreamReader()
        protocol = asyncio.StreamReaderProtocol(reader)
        await asyncio.get_event_loop().connect_read_pipe(lambda: protocol, sys.stdin)
        
        writer = sys.stdout
        
        try:
            while True:
                # Read line from stdin
                line = await reader.readline()
                if not line:
                    break
                
                try:
                    # Parse JSON-RPC request
                    data = json.loads(line.decode().strip())
                    request = MCPRequest(**data)
                    
                    # Handle request
                    response = await self.handle_request(request)
                    
                    # Write response
                    response_json = response.model_dump_json(exclude_none=True)
                    writer.write(response_json + "\n")
                    writer.flush()
                    
                except json.JSONDecodeError as e:
                    # Parse error
                    error_response = MCPResponse(
                        error={
                            "code": MCPError.PARSE_ERROR,
                            "message": f"Parse error: {e}"
                        }
                    )
                    writer.write(error_response.model_dump_json() + "\n")
                    writer.flush()
                
                except Exception as e:
                    logger.error(f"Error processing request: {e}", exc_info=True)
                    
        except KeyboardInterrupt:
            logger.info("Received interrupt signal")
        finally:
            logger.info("Shutting down server")


async def main():
    """Main entry point"""
    setup_logging()
    
    server = StackWizMCPServer()
    
    # Handle shutdown signals
    def signal_handler(signum, frame):
        logger.info(f"Received signal {signum}")
        asyncio.create_task(server.handle_shutdown({}))
        sys.exit(0)
    
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)
    
    # Run server
    transport = os.getenv("MCP_TRANSPORT", "stdio").lower()
    
    if transport == "stdio":
        await server.run_stdio()
    else:
        logger.error(f"Unsupported transport: {transport}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())