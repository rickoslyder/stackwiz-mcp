# CLAUDE.md - StackWiz MCP Agent Instructions

This file provides guidance to Claude Code when using StackWiz MCP for infrastructure management.

## What is StackWiz?

StackWiz is an MCP (Model Context Protocol) server that enables you to:
- Create and manage Docker service stacks
- Handle Cloudflare DNS records
- Deploy services with automatic Traefik routing and SSL

## Quick Start

When you have access to StackWiz MCP tools, you can create infrastructure directly:

```
User: "Create a Redis cache service"

You should:
1. Use create_stack with appropriate parameters
2. Verify with list_stacks
3. Report the service URL to user
```

## Available Tools

### Stack Management
- `create_stack` - Create new Docker services
- `list_stacks` - List existing stacks
- `manage_stack` - Start/stop/restart/remove/logs

### DNS Management
- `create_dns_record` - Create DNS records
- `list_dns_records` - List DNS records
- `update_dns_proxy` - Toggle Cloudflare proxy
- `delete_dns_record` - Delete DNS records

### Utilities
- `validate_stack_config` - Validate before deploying
- `health_check` - Check StackWiz health

## Common Patterns

### Deploy a Generic Service
```python
create_stack(
    name="service-name",
    image="image:tag",
    port=8080,
    create_dns=True,
    auto_start=True
)
```

### Deploy Pocketbase (Full Backend)
```python
create_stack(
    name="app-name",
    type="pocketbase",
    create_dns=True,
    auto_start=True
)
```

### Check Service Health
```python
list_stacks(filter="service-name", include_status=True)
manage_stack(stack_name="service-name", action="logs", tail_lines=50)
```

## Important Notes

1. **Stack names**: Use lowercase, alphanumeric with hyphens only
2. **Domains**: Default to `{name}.{STACKWIZ_DEFAULT_DOMAIN}`
3. **DNS**: Use `create_dns=True` for public services
4. **Proxy**: Cloudflare proxy is enabled by default (disable for WebSocket issues)
5. **Logs**: Always check logs after deployment

## Canonical Documentation

For detailed reference, see: `docs/AGENT_REFERENCE.md`

This includes:
- Complete tool parameter documentation
- Common workflow examples
- Error handling guide
- Configuration reference
- Best practices
