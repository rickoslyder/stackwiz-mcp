# StackWiz MCP: Complete Technical Architecture

This document provides a comprehensive technical overview of how StackWiz MCP works, including the architecture, data flow, and configuration requirements for deployment in any environment (LXC, Docker, bare metal).

## Executive Summary

StackWiz exists in **two forms** that share the same conceptual model but have different implementations:

1. **CLI Script** (`/srv/dockerdata/_templates/stackwiz`) - Interactive bash wizard for humans
2. **MCP Server** (`stackwiz-mcp` package) - API-driven tool for AI agents

Both create Docker Compose stacks with Traefik integration.

---

## Architecture Overview

```
+---------------------------------------------------------------------+
|                        StackWiz MCP Server                          |
|  +-------------+  +--------------+  +-----------------------------+ |
|  | FastMCP     |  | Tool Layer   |  | Utilities                   | |
|  | Framework   |--| - create     |--| - stack_utils.py            | |
|  |             |  | - manage     |  | - compose execution         | |
|  |             |  | - dns ops    |  | - template rendering        | |
|  +-------------+  +--------------+  +-----------------------------+ |
+---------------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------------+
|                      Required Infrastructure                         |
|  +--------------+  +--------------+  +----------------------------+ |
|  | Docker       |  | Traefik      |  | Cloudflare                 | |
|  | Socket       |  | Proxy        |  | DNS API                    | |
|  | /var/run/    |  | Network:     |  | Token from:                | |
|  | docker.sock  |  | traefik_proxy|  | - STACKWIZ_CF_API_TOKEN    | |
|  |              |  |              |  | - CF_DNS_API_TOKEN         | |
|  |              |  |              |  | - traefik/.env fallback    | |
|  +--------------+  +--------------+  +----------------------------+ |
+---------------------------------------------------------------------+
                              |
                              v
+---------------------------------------------------------------------+
|                       File System Layout                             |
|  $STACKWIZ_BASE_DIR/                                                 |
|  +-- _templates/          <- Template files (REQUIRED)              |
|  |   +-- stack-template.yml                                         |
|  |   +-- pocketbase-template.yml                                    |
|  |   +-- env-template                                               |
|  |   +-- pocketbase-env-template                                    |
|  +-- traefik/.env         <- Optional: fallback for CF_DNS_API_TOKEN|
|  +-- {stack-name}/        <- Created stacks go here                 |
|      +-- docker-compose.yml                                         |
|      +-- .env                                                       |
+---------------------------------------------------------------------+
```

---

## Environment Variables

All paths and settings are now configurable via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `STACKWIZ_BASE_DIR` | `/srv/dockerdata` | Where stacks are created |
| `STACKWIZ_TEMPLATES_DIR` | `{base_dir}/_templates` | Where templates live |
| `STACKWIZ_SCRIPTS_DIR` | `{base_dir}/_scripts` | Where helper scripts live |
| `STACKWIZ_DEFAULT_USER` | Current user | User for file ownership |
| `STACKWIZ_DEFAULT_GROUP` | `docker` | Group for file ownership |
| `STACKWIZ_CF_API_TOKEN` | None | Cloudflare API token |
| `STACKWIZ_DEFAULT_DOMAIN` | `rbnk.uk` | Default domain suffix |
| `STACKWIZ_DOCKER_NETWORK` | `traefik_proxy` | Docker network name |

### Token Discovery Chain

The Cloudflare API token is discovered in this order:

1. `config.dns.api_token` (from config object)
2. `STACKWIZ_CF_API_TOKEN` environment variable
3. `CF_DNS_API_TOKEN` environment variable
4. `CF_API_TOKEN` environment variable
5. Read from `{base_dir}/traefik/.env` file

---

## The Stack Creation Flow

### Step 1: Tool Invocation

```python
@mcp.tool()
async def create_stack(
    name: str,
    type: str = "generic",
    image: str = None,
    port: int = None,
    domain: str = None,
    create_dns: bool = False,
    auto_start: bool = False,
    environment: dict = None,
) -> dict:
```

### Step 2: Validation

```python
# Validate name (lowercase, alphanumeric, hyphens only)
if not re.match(r'^[a-z0-9][a-z0-9-]*[a-z0-9]$|^[a-z0-9]$', name):
    raise ValueError("Invalid stack name")

# Check if stack already exists
stack_dir = settings.base_dir / name
if stack_dir.exists():
    raise ValueError(f"Stack {name} already exists")
```

### Step 3: Template Selection & Rendering

Templates use token substitution:
- `__APP_NAME__` -> stack name
- `__APP_DOMAIN__` -> full domain (e.g., `myapp.rbnk.uk`)
- `__APP_IMAGE__` -> Docker image
- `__APP_PORT__` -> Container port
- `__TRAEFIK_NETWORK__` -> Docker network (default: `traefik_proxy`)
- `__TRAEFIK_ENTRYPOINT__` -> Traefik entrypoint (default: `websecure`)
- `__TRAEFIK_CERTRESOLVER__` -> Cert resolver (default: `cf`)

### Step 4: Directory & File Creation

```python
# Create stack directory
stack_dir.mkdir(parents=True, exist_ok=True)

# Write docker-compose.yml
compose_file = stack_dir / "docker-compose.yml"
compose_file.write_text(rendered_content)

# Write .env file
env_file = stack_dir / ".env"
env_file.write_text(rendered_env)

# Fix permissions (uses STACKWIZ_DEFAULT_USER/GROUP)
fix_permissions(stack_dir)
```

### Step 5: DNS Creation (Optional)

```python
if create_dns:
    await create_dns_record(
        subdomain=name,
        type="A",
        value="AUTO",    # Auto-detects server IP
        proxied=True     # Cloudflare proxy enabled
    )
```

### Step 6: Auto-Start (Optional)

```python
if auto_start:
    result = subprocess.run(
        ["docker", "compose", "-f", str(compose_file), "up", "-d"],
        cwd=str(stack_dir)
    )
```

---

## Deployment Options

### Option A: pip Install (Simplest)

```bash
pip install git+https://github.com/rickoslyder/stackwiz-mcp.git

# Set environment
export STACKWIZ_BASE_DIR=/path/to/stacks
export STACKWIZ_CF_API_TOKEN=your-token

# Create required directories
mkdir -p $STACKWIZ_BASE_DIR/_templates
cp templates/* $STACKWIZ_BASE_DIR/_templates/

# Create Docker network
docker network create traefik_proxy

# Run
stackwiz-mcp
```

### Option B: Docker Container

```json
{
  "mcpServers": {
    "stackwiz": {
      "command": "docker",
      "args": [
        "run", "--rm", "--interactive",
        "--volume", "/var/run/docker.sock:/var/run/docker.sock",
        "--volume", "/your/path:/srv/dockerdata",
        "--env", "STACKWIZ_BASE_DIR=/srv/dockerdata",
        "--env", "CF_DNS_API_TOKEN=your-token",
        "stackwiz-mcp:latest"
      ]
    }
  }
}
```

This works because:
1. Inside the container, paths are `/srv/dockerdata`
2. Volume mount maps your actual path to the expected path
3. Docker socket gives container control over host Docker

### Option C: Direct Python Execution

```bash
# Clone the repo
git clone https://github.com/rickoslyder/stackwiz-mcp.git
cd stackwiz-mcp

# Install dependencies
pip install -e .

# Configure
export STACKWIZ_BASE_DIR=/home/user/stacks
export STACKWIZ_TEMPLATES_DIR=/home/user/stacks/templates
export STACKWIZ_DEFAULT_USER=$USER
export STACKWIZ_CF_API_TOKEN=your-token

# Run
python -m stackwiz_mcp
```

---

## LXC/External Deployment Checklist

### Prerequisites

1. **Docker installed and accessible**
   ```bash
   docker ps  # Should work without sudo, or run MCP as root
   ```

2. **Docker network exists**
   ```bash
   docker network create traefik_proxy
   # Or customize: export STACKWIZ_DOCKER_NETWORK=mynetwork
   ```

3. **Templates directory with files**
   ```bash
   mkdir -p /path/to/stacks/_templates
   # Copy these files:
   # - stack-template.yml
   # - pocketbase-template.yml
   # - env-template
   # - pocketbase-env-template
   ```

4. **Cloudflare token (if using DNS)**
   ```bash
   export STACKWIZ_CF_API_TOKEN=your-token
   ```

### Verification Steps

```bash
# 1. Check templates exist
ls -la $STACKWIZ_TEMPLATES_DIR/

# 2. Check Docker network exists
docker network ls | grep ${STACKWIZ_DOCKER_NETWORK:-traefik_proxy}

# 3. Check Docker socket permissions
ls -la /var/run/docker.sock

# 4. Test MCP server starts
python -m stackwiz_mcp
# Should start without errors

# 5. Test health check (if HTTP mode)
curl http://localhost:8000/health
```

---

## Template Reference

### Generic Stack Template (`stack-template.yml`)

```yaml
services:
  __SERVICE_NAME__:
    image: __APP_IMAGE__
    container_name: __APP_NAME__
    restart: unless-stopped
    env_file:
      - .env
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.__APP_NAME__.rule=Host(`__APP_DOMAIN__`)"
      - "traefik.http.routers.__APP_NAME__.entrypoints=__TRAEFIK_ENTRYPOINT__"
      - "traefik.http.routers.__APP_NAME__.tls.certresolver=__TRAEFIK_CERTRESOLVER__"
      - "traefik.http.services.__APP_NAME__.loadbalancer.server.port=__APP_PORT__"

networks:
  default:
    name: __TRAEFIK_NETWORK__
    external: true
```

### Pocketbase Template (`pocketbase-template.yml`)

```yaml
services:
  pocketbase:
    image: ghcr.io/muchobien/pocketbase:latest
    container_name: __APP_NAME__
    restart: unless-stopped
    volumes:
      - ./pb_data:/pb_data
      - ./pb_public:/pb_public
      - ./pb_migrations:/pb_migrations
      - ./pb_hooks:/pb_hooks
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.__APP_NAME__.rule=Host(`__APP_DOMAIN__`)"
      - "traefik.http.routers.__APP_NAME__.entrypoints=websecure"
      - "traefik.http.routers.__APP_NAME__.tls.certresolver=cf"
      - "traefik.http.services.__APP_NAME__.loadbalancer.server.port=8090"
    healthcheck:
      test: ["CMD", "wget", "--spider", "http://localhost:8090/api/health"]
      interval: 30s
      timeout: 10s
      retries: 3

networks:
  default:
    name: traefik_proxy
    external: true
```

---

## Common Issues & Solutions

### "Path does not exist" Warning

**Cause**: Templates or base directory not set up.

**Fix**:
```bash
export STACKWIZ_BASE_DIR=/your/path
mkdir -p $STACKWIZ_BASE_DIR/_templates
# Copy template files
```

### "Network traefik_proxy declared as external, but could not be found"

**Cause**: Docker network doesn't exist.

**Fix**:
```bash
docker network create traefik_proxy
# Or set custom network:
export STACKWIZ_DOCKER_NETWORK=your-network
```

### "Cloudflare API token not configured"

**Cause**: No token found in any of the discovery locations.

**Fix**:
```bash
export STACKWIZ_CF_API_TOKEN=your-token
# Or
export CF_DNS_API_TOKEN=your-token
```

### Permission errors on stack creation

**Cause**: Wrong user/group configured.

**Fix**:
```bash
export STACKWIZ_DEFAULT_USER=$USER
export STACKWIZ_DEFAULT_GROUP=$(id -gn)
```

---

## DNS Operations Deep Dive

### Zone ID Caching

```python
_cf_zone_cache: dict[str, tuple[str, float]] = {}
ZONE_CACHE_TTL = 300  # 5 minutes

async def _get_zone_id(domain: str) -> str:
    # Check cache first, then query Cloudflare API
```

### Rate Limit Handling

```python
async def _cf_request_with_retry(method, url, **kwargs):
    max_retries = 3
    for attempt in range(max_retries):
        response = await client.request(method, url, **kwargs)
        if response.status_code == 429:  # Rate limited
            retry_after = int(response.headers.get("Retry-After", 60))
            await asyncio.sleep(retry_after)
            continue
        return response
```

### Auto IP Detection

```python
async def _get_server_ip() -> str:
    """Get server's public IP for A records"""
    ip_services = [
        "https://ipv4.icanhazip.com",
        "https://api.ipify.org",
        "https://ifconfig.me/ip"
    ]
    for service in ip_services:
        response = await client.get(service)
        if response.status_code == 200:
            return response.text.strip()
```

---

## MCP Configuration Examples

### Claude Desktop (`claude_desktop_config.json`)

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

### Claude Code (`.mcp.json`)

```json
{
  "mcpServers": {
    "stackwiz": {
      "command": "python",
      "args": ["-m", "stackwiz_mcp"],
      "env": {
        "STACKWIZ_BASE_DIR": "/path/to/stacks",
        "STACKWIZ_CF_API_TOKEN": "your-token"
      }
    }
  }
}
```

---

## Support

- **Repository**: https://github.com/rickoslyder/stackwiz-mcp
- **Gitea Mirror**: https://gitea.rbnk.uk/admin/stackwiz-mcp
