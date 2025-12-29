# StackWiz MCP - Agent Reference Guide

This is the canonical reference for AI agents using StackWiz MCP to manage Docker infrastructure.

## Quick Reference

### Available Tools

| Tool | Purpose | Example |
|------|---------|---------|
| `create_stack` | Create new Docker service | Create a Redis cache service |
| `list_stacks` | List all stacks | Show running services |
| `manage_stack` | Control services | Start/stop/restart/logs |
| `create_dns_record` | Add DNS record | Point subdomain to server |
| `list_dns_records` | List DNS records | Check existing records |
| `update_dns_proxy` | Toggle CF proxy | Enable/disable orange cloud |
| `delete_dns_record` | Remove DNS record | Clean up old records |
| `validate_stack_config` | Validate config | Check before deploying |
| `health_check` | Server health | Verify StackWiz is working |

---

## Tool Details

### create_stack

Creates a new Docker Compose stack with Traefik integration.

**Parameters:**
- `name` (required): Stack name (lowercase, alphanumeric, hyphens)
- `type`: "generic" or "pocketbase" (default: generic)
- `image`: Docker image (required for generic)
- `port`: Container port (required for generic)
- `domain`: Custom domain (default: {name}.rbnk.uk)
- `environment`: Dict of environment variables
- `create_dns`: Create DNS record (default: false)
- `auto_start`: Start after creation (default: false)

**Example:**
```python
create_stack(
    name="my-api",
    type="generic",
    image="nginx:alpine",
    port=80,
    domain="my-api.rbnk.uk",
    create_dns=True,
    auto_start=True
)
```

**Pocketbase Example:**
```python
create_stack(
    name="my-app",
    type="pocketbase",
    domain="my-app.rbnk.uk",
    create_dns=True,
    auto_start=True
)
```

---

### manage_stack

Control existing stacks.

**Parameters:**
- `stack_name` (required): Name of the stack
- `action` (required): "start", "stop", "restart", "remove", "logs"
- `tail_lines`: Lines of logs to show (default: 100)

**Examples:**
```python
# Start a stack
manage_stack(stack_name="my-api", action="start")

# View logs
manage_stack(stack_name="my-api", action="logs", tail_lines=50)

# Stop and remove
manage_stack(stack_name="my-api", action="stop")
manage_stack(stack_name="my-api", action="remove")
```

---

### list_stacks

List all Docker stacks.

**Parameters:**
- `filter`: Filter by name pattern
- `include_status`: Include container status (default: true)
- `sort_by`: "name", "created", or "status"

**Example:**
```python
list_stacks(filter="api", include_status=True)
```

---

### DNS Tools

#### create_dns_record
```python
create_dns_record(
    subdomain="my-api",      # Creates my-api.rbnk.uk
    type="A",                # A, CNAME, MX, TXT
    value="AUTO",            # AUTO = server IP
    proxied=True             # Cloudflare proxy
)
```

#### update_dns_proxy
```python
update_dns_proxy(subdomain="my-api", enable=False)  # Disable proxy
```

#### delete_dns_record
```python
delete_dns_record(subdomain="my-api")
```

---

## Common Workflows

### Deploy a New Web Service

```python
# 1. Create the stack
create_stack(
    name="my-service",
    image="ghcr.io/user/my-service:latest",
    port=3000,
    environment={"NODE_ENV": "production"},
    create_dns=True,
    auto_start=True
)

# 2. Verify it's running
list_stacks(filter="my-service")

# 3. Check logs if needed
manage_stack(stack_name="my-service", action="logs")
```

### Deploy a Pocketbase App

```python
# Creates both backend (my-app-pb) and configures Pocketbase
create_stack(
    name="my-app",
    type="pocketbase",
    create_dns=True,
    auto_start=True
)
# Access at: https://my-app.rbnk.uk
# Admin UI: https://my-app.rbnk.uk/_/
```

### Update a Service

```python
# Pull new image and restart
manage_stack(stack_name="my-service", action="restart")
```

### Troubleshoot a Service

```python
# Check status
list_stacks(filter="my-service", include_status=True)

# View logs
manage_stack(stack_name="my-service", action="logs", tail_lines=200)

# Restart if needed
manage_stack(stack_name="my-service", action="restart")
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `STACKWIZ_BASE_DIR` | Yes | - | Where stacks are created |
| `STACKWIZ_CF_API_TOKEN` | For DNS | - | Cloudflare API token |
| `STACKWIZ_DEFAULT_DOMAIN` | No | rbnk.uk | Default domain |
| `STACKWIZ_DOCKER_NETWORK` | No | traefik_proxy | Docker network |
| `DOCKER_HOST` | No | unix:///var/run/docker.sock | Docker socket |

### MCP Configuration

```json
{
  "mcpServers": {
    "stackwiz": {
      "command": "stackwiz-mcp",
      "env": {
        "STACKWIZ_BASE_DIR": "/srv/dockerdata",
        "STACKWIZ_CF_API_TOKEN": "your-token",
        "STACKWIZ_DEFAULT_DOMAIN": "yourdomain.com"
      }
    }
  }
}
```

---

## Best Practices

1. **Naming**: Use lowercase, hyphenated names (e.g., `my-api`, `user-service`)
2. **DNS**: Always use `create_dns=True` for public services
3. **Proxy**: Keep Cloudflare proxy enabled unless you need WebSockets or have timeouts
4. **Logs**: Check logs after deployment to verify service health
5. **Cleanup**: Remove unused stacks and DNS records to keep infrastructure clean

---

## Error Handling

| Error | Cause | Solution |
|-------|-------|----------|
| "Stack already exists" | Duplicate name | Use different name or remove existing |
| "Port conflict" | Port in use | Choose different port |
| "DNS record exists" | Duplicate subdomain | Delete old record first |
| "Docker socket error" | No Docker access | Check DOCKER_HOST config |
| "Cloudflare API error" | Invalid token | Update CF_API_TOKEN |

---

## Templates

### Generic Stack Template
Creates: `docker-compose.yml` with Traefik labels, health checks, logging

### Pocketbase Template
Creates: Full Pocketbase setup with:
- SQLite database with automatic backups
- Built-in authentication
- REST and realtime APIs
- Admin dashboard
- File storage

---

## Support

- **Repository**: https://gitea.rbnk.uk/admin/stackwiz-mcp
- **GitHub Mirror**: https://github.com/rickoslyder/stackwiz-mcp
