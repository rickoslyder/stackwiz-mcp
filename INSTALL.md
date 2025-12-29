# StackWiz MCP Installation Guide

## Quick Install (pip from Git)

```bash
pip install git+https://gitea.rbnk.uk/admin/stackwiz-mcp.git
```

## Requirements

- Python 3.10+
- Docker (with socket access)
- Cloudflare API token (for DNS management)

## Configuration

Create a `.env` file or set environment variables:

```bash
# Required: Where to create stacks
STACKWIZ_BASE_DIR=/srv/dockerdata

# Required for DNS management
STACKWIZ_CF_API_TOKEN=your-cloudflare-api-token
STACKWIZ_CF_ZONE_ID=your-zone-id  # Optional, auto-detected from domain

# Docker socket (defaults to /var/run/docker.sock)
DOCKER_HOST=unix:///var/run/docker.sock

# Optional: Default domain for services
STACKWIZ_DEFAULT_DOMAIN=yourdomain.com

# Optional: Default Docker network
STACKWIZ_DOCKER_NETWORK=traefik_proxy
```

## Usage with Claude Code

Add to your `.mcp.json`:

```json
{
  "mcpServers": {
    "stackwiz": {
      "command": "stackwiz-mcp",
      "env": {
        "STACKWIZ_BASE_DIR": "/path/to/stacks",
        "STACKWIZ_CF_API_TOKEN": "your-token"
      }
    }
  }
}
```

## Usage as HTTP Server (Remote Access)

```bash
# Start HTTP server
stackwiz-mcp --http --host 0.0.0.0 --port 8080

# Connect from remote Claude Code
# .mcp.json:
{
  "mcpServers": {
    "stackwiz": {
      "type": "sse",
      "url": "http://your-server:8080/sse"
    }
  }
}
```

## Available Tools

- `create_stack` - Create new Docker service stacks
- `list_stacks` - List existing stacks
- `manage_stack` - Start/stop/restart/remove stacks
- `create_dns_record` - Create Cloudflare DNS records
- `list_dns_records` - List DNS records
- `update_dns_proxy` - Toggle Cloudflare proxy
- `delete_dns_record` - Delete DNS records
- `validate_stack_config` - Validate configurations
- `health_check` - Check server health

## Templates

Templates are included in the package for:
- Generic Docker services
- Pocketbase applications

Custom templates can be added to `STACKWIZ_TEMPLATES_DIR`.
