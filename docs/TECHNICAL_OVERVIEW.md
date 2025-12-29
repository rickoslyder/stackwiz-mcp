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

## Multi-Host / LXC Deployment

When deploying StackWiz on a separate host (LXC container, VM, or different server), you need to understand the network topology and configure accordingly.

### Network Architecture Options

#### Option 1: Standalone Mode (No Traefik Integration)

If your LXC doesn't have Traefik, modify templates to expose ports directly:

```yaml
# Custom template without Traefik
services:
  myapp:
    image: nginx:alpine
    container_name: myapp
    ports:
      - "8080:80"  # Direct port exposure
    # No traefik labels needed
    # No external network needed

networks:
  default:
    driver: bridge
```

**Environment setup:**
```bash
# Create a simple bridge network instead
docker network create stackwiz_default

# Set environment
export STACKWIZ_DOCKER_NETWORK=stackwiz_default
```

#### Option 2: Remote Traefik Integration

If Traefik runs on a different host (e.g., main infrastructure server), you have two options:

**A. Use Traefik's Docker Socket Proxy (Recommended for security)**
```
+-------------------+          +-------------------+
|   LXC Container   |          |   Main Server     |
|                   |          |                   |
|  StackWiz MCP     |   API    |   Traefik         |
|  Docker Engine    | -------> |   (socket proxy)  |
|  Services         |          |   SSL Termination |
+-------------------+          +-------------------+
```

**B. Direct Docker Network Connection (Same network segment)**
If both hosts can share a Docker network (overlay network with Swarm, or same bridge):
```bash
# On LXC: Join the remote Traefik network
docker network create --driver overlay traefik_proxy
# Or connect to existing
docker network connect traefik_proxy container_name
```

#### Option 3: Port Forwarding with Local Traefik

Run a local Traefik instance on the LXC that proxies to services:

```bash
# Install Traefik on LXC
mkdir -p /home/user/traefik
cat > /home/user/traefik/docker-compose.yml << 'EOF'
services:
  traefik:
    image: traefik:v2.10
    container_name: traefik
    command:
      - "--api.insecure=true"
      - "--providers.docker=true"
      - "--providers.docker.exposedbydefault=false"
      - "--entrypoints.web.address=:80"
      - "--entrypoints.websecure.address=:443"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge=true"
      - "--certificatesresolvers.letsencrypt.acme.httpchallenge.entrypoint=web"
      - "--certificatesresolvers.letsencrypt.acme.email=your@email.com"
      - "--certificatesresolvers.letsencrypt.acme.storage=/letsencrypt/acme.json"
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock:ro
      - ./letsencrypt:/letsencrypt
    networks:
      - traefik_proxy

networks:
  traefik_proxy:
    external: true
EOF

docker network create traefik_proxy
docker compose up -d
```

### Port Forwarding (Proxmox/Hypervisor to LXC)

If your LXC is behind NAT (common in Proxmox), you need port forwarding for external access.

#### Method 1: IPTables Rules (Temporary)

On the **Proxmox host** (or hypervisor):

```bash
# Variables
LXC_IP="10.0.0.100"        # Your LXC's internal IP
EXTERNAL_PORT="8443"        # Port exposed externally
INTERNAL_PORT="443"         # Port inside LXC

# Forward HTTPS traffic
iptables -t nat -A PREROUTING -p tcp --dport $EXTERNAL_PORT -j DNAT --to-destination $LXC_IP:$INTERNAL_PORT
iptables -A FORWARD -p tcp -d $LXC_IP --dport $INTERNAL_PORT -j ACCEPT

# Enable masquerading for return traffic
iptables -t nat -A POSTROUTING -j MASQUERADE

# Verify
iptables -t nat -L PREROUTING -n -v
```

#### Method 2: Persistent Configuration (Recommended)

Add to `/etc/network/interfaces` on Proxmox host:

```bash
auto vmbr0
iface vmbr0 inet static
    address 192.168.1.10/24
    gateway 192.168.1.1
    bridge-ports eno1
    bridge-stp off
    bridge-fd 0

    # Port forwarding to LXC
    # HTTP
    post-up   iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to 10.0.0.100:80
    post-down iptables -t nat -D PREROUTING -i vmbr0 -p tcp --dport 80 -j DNAT --to 10.0.0.100:80

    # HTTPS
    post-up   iptables -t nat -A PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to 10.0.0.100:443
    post-down iptables -t nat -D PREROUTING -i vmbr0 -p tcp --dport 443 -j DNAT --to 10.0.0.100:443

    # Allow forwarded traffic
    post-up   iptables -A FORWARD -p tcp -d 10.0.0.100 -j ACCEPT
    post-down iptables -D FORWARD -p tcp -d 10.0.0.100 -j ACCEPT
```

Then apply: `systemctl restart networking`

#### Method 3: Using Non-Standard Ports

If ports 80/443 are used by main host, use alternative ports:

```bash
# Forward external 8080 -> LXC 80
iptables -t nat -A PREROUTING -p tcp --dport 8080 -j DNAT --to-destination 10.0.0.100:80

# Forward external 8443 -> LXC 443
iptables -t nat -A PREROUTING -p tcp --dport 8443 -j DNAT --to-destination 10.0.0.100:443
```

### DNS Considerations for Multi-Host

When StackWiz runs on a different host, DNS records need special consideration:

#### Problem: Auto-IP Detection Returns Wrong IP

The `create_dns_record` tool with `value="AUTO"` detects the **LXC's public IP**, which might be:
- The hypervisor's IP (if NAT'd)
- An internal IP (if private network)
- Wrong for your routing setup

#### Solutions:

**1. Specify IP Explicitly:**
```python
# Instead of AUTO, provide the correct IP
create_dns_record(
    subdomain="myapp",
    type="A",
    value="203.0.113.50",  # Your actual public IP
    proxied=True
)
```

**2. Set Default in Environment:**
```bash
# Force a specific IP for all DNS records
export STACKWIZ_PUBLIC_IP="203.0.113.50"
```

**3. Point to Main Infrastructure:**
If main server handles routing, point DNS there:
```bash
# Create CNAME to main server instead of A record
cloudflare-dns create CNAME myapp main.yourdomain.com
```

**4. Use Cloudflare Tunnel (Zero Trust):**
Bypass port forwarding entirely with Cloudflare Tunnel:
```bash
# On LXC, install cloudflared
docker run -d --name cloudflared \
  --network traefik_proxy \
  cloudflare/cloudflared:latest \
  tunnel --no-autoupdate run --token YOUR_TUNNEL_TOKEN
```

### Complete LXC Setup Example

Here's a full example for deploying StackWiz on an LXC container:

```bash
#!/bin/bash
# lxc-stackwiz-setup.sh

# === Configuration ===
STACK_DIR="/home/user/stacks"
TEMPLATES_DIR="$STACK_DIR/_templates"
CF_TOKEN="your-cloudflare-token"
PUBLIC_IP="203.0.113.50"  # Your actual public IP for DNS

# === Install Dependencies ===
apt update && apt install -y python3-pip docker.io docker-compose-plugin

# === Setup Docker ===
systemctl enable docker
systemctl start docker
usermod -aG docker $USER

# === Create Directory Structure ===
mkdir -p "$TEMPLATES_DIR"
mkdir -p "$STACK_DIR/traefik"

# === Install StackWiz MCP ===
pip install git+https://github.com/rickoslyder/stackwiz-mcp.git

# === Download Templates ===
cd "$TEMPLATES_DIR"
curl -O https://raw.githubusercontent.com/rickoslyder/stackwiz-mcp/main/templates/stack-template.yml
curl -O https://raw.githubusercontent.com/rickoslyder/stackwiz-mcp/main/templates/pocketbase-template.yml
curl -O https://raw.githubusercontent.com/rickoslyder/stackwiz-mcp/main/templates/env-template
curl -O https://raw.githubusercontent.com/rickoslyder/stackwiz-mcp/main/templates/pocketbase-env-template

# === Create Docker Network ===
docker network create traefik_proxy

# === Setup Local Traefik (if not using main server's Traefik) ===
# Uncomment if needed:
# mkdir -p $STACK_DIR/traefik/letsencrypt
# ... (traefik docker-compose setup)

# === Configure Environment ===
cat > /etc/profile.d/stackwiz.sh << EOF
export STACKWIZ_BASE_DIR="$STACK_DIR"
export STACKWIZ_TEMPLATES_DIR="$TEMPLATES_DIR"
export STACKWIZ_DEFAULT_USER="$USER"
export STACKWIZ_DEFAULT_GROUP="docker"
export STACKWIZ_CF_API_TOKEN="$CF_TOKEN"
export STACKWIZ_PUBLIC_IP="$PUBLIC_IP"
EOF

source /etc/profile.d/stackwiz.sh

# === Configure MCP for Claude Code ===
mkdir -p ~/.mcp
cat > ~/.mcp.json << EOF
{
  "mcpServers": {
    "stackwiz": {
      "command": "stackwiz-mcp",
      "env": {
        "STACKWIZ_BASE_DIR": "$STACK_DIR",
        "STACKWIZ_TEMPLATES_DIR": "$TEMPLATES_DIR",
        "STACKWIZ_CF_API_TOKEN": "$CF_TOKEN",
        "STACKWIZ_DEFAULT_USER": "$USER"
      }
    }
  }
}
EOF

# === Verify Installation ===
echo "Testing StackWiz MCP..."
python -m stackwiz_mcp --help

echo "
=== Setup Complete ===

StackWiz MCP is installed and configured.

Next steps:
1. If using Proxmox: Configure port forwarding (see TECHNICAL_OVERVIEW.md)
2. Test creating a stack: stackwiz-mcp (then use via Claude)
3. Verify DNS records point to: $PUBLIC_IP

Templates location: $TEMPLATES_DIR
Stacks location: $STACK_DIR
MCP config: ~/.mcp.json
"
```

### Troubleshooting Multi-Host Issues

#### Service Created But Not Accessible

1. **Check port forwarding:**
   ```bash
   # On hypervisor
   iptables -t nat -L PREROUTING -n -v | grep DNAT
   ```

2. **Check LXC firewall:**
   ```bash
   # On LXC
   iptables -L INPUT -n
   ufw status  # if using ufw
   ```

3. **Test connectivity chain:**
   ```bash
   # From external
   curl -v https://yourdomain.com

   # From hypervisor to LXC
   curl -v http://10.0.0.100:80

   # From LXC to container
   docker exec traefik wget -qO- http://container_name:port
   ```

#### DNS Record Created With Wrong IP

```bash
# Check what IP AUTO detected
curl -s https://api.ipify.org

# If wrong, update the record manually
cloudflare-dns update myapp $CORRECT_IP

# Or delete and recreate
cloudflare-dns delete myapp
cloudflare-dns create A myapp $CORRECT_IP
```

#### Container Network Issues

```bash
# Verify container is on correct network
docker inspect container_name | grep -A 10 Networks

# Manually connect if needed
docker network connect traefik_proxy container_name

# Check network connectivity
docker run --rm --network traefik_proxy alpine ping -c 2 container_name
```

---

## Support

- **Repository**: https://github.com/rickoslyder/stackwiz-mcp
- **Gitea Mirror**: https://gitea.rbnk.uk/admin/stackwiz-mcp
