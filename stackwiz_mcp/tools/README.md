# Stackwiz MCP Tools

This directory contains the core stack management tools for the Stackwiz MCP server.

## Available Tools

### Stack Creation and Management

#### `create_stack`
Create a new Docker stack with Traefik integration.

**Parameters:**
- `name` (required): Stack name (will be slugified)
- `domain` (required): Full domain name (e.g., myapp.rbnk.uk)
- `stack_type`: "generic" or "pocketbase" (default: "generic")
- `image`: Docker image (required for generic stacks)
- `port`: Internal container port (required for generic stacks)
- `service_name`: Docker service name (defaults to stack name)
- `network`: Traefik network (default: "traefik_proxy")
- `entrypoint`: Traefik entrypoint (default: "websecure")
- `certresolver`: Traefik cert resolver (default: "cf")
- `create_dns`: Auto-create DNS record (default: false)
- `auto_start`: Auto-start stack (default: false)

**Example:**
```python
params = {
    "name": "myapp",
    "domain": "myapp.rbnk.uk",
    "stack_type": "generic",
    "image": "nginx:alpine",
    "port": 80,
    "create_dns": true,
    "auto_start": true
}
```

#### `list_stacks`
List all Docker stacks with optional filtering.

**Parameters:**
- `filter_type`: Filter by "generic" or "pocketbase"
- `filter_status`: Filter by "running", "stopped", "created", or "error"
- `include_system`: Include system stacks (default: false)

#### `get_stack_info`
Get detailed information about a specific stack.

**Parameters:**
- `name` (required): Stack name

### Stack Operations

#### `start_stack`
Start a stopped Docker stack.

**Parameters:**
- `name` (required): Stack name
- `force`: Force operation (default: false)

#### `stop_stack`
Stop a running Docker stack.

**Parameters:**
- `name` (required): Stack name
- `force`: Force operation (default: false)

#### `restart_stack`
Restart a Docker stack.

**Parameters:**
- `name` (required): Stack name
- `force`: Force operation (default: false)

#### `remove_stack`
Remove a Docker stack (use force=true to remove volumes).

**Parameters:**
- `name` (required): Stack name
- `force`: Remove volumes too (default: false)

#### `get_stack_logs`
Get logs from a Docker stack.

**Parameters:**
- `name` (required): Stack name
- `service`: Specific service name
- `lines`: Number of lines (default: 100)
- `follow`: Follow logs (not supported)

### DNS Management

#### `create_dns_record`
Create a DNS record in Cloudflare.

**Parameters:**
- `subdomain` (required): Subdomain without .rbnk.uk
- `record_type`: "A", "AAAA", "CNAME", "TXT", "MX" (default: "A")
- `target`: Target value or "AUTO" for auto-detect IP (default: "AUTO")
- `proxied`: Proxy through Cloudflare (default: true)

#### `list_dns_records`
List all DNS records for the domain.

**Parameters:** None

## Tool Implementation Details

### Error Handling
All tools return a `StackOperationResult` with:
- `success`: Boolean indicating success/failure
- `message`: Human-readable message
- `details`: Optional dict with additional information
- `error`: Optional error message on failure

### Permissions
- Tools run with appropriate permissions using sudo
- File permissions are automatically fixed (750 for dirs, 640 for .env)
- Stack operations respect the DEFAULT_USER setting

### Validation
- Stack names are automatically slugified
- Domain format is validated
- Port ranges are checked (1-65535)
- System stacks are protected from accidental removal

### Template System
- Uses templates from `_templates/` directory
- Falls back to inline templates if files missing
- Supports token substitution for customization
- Separate templates for generic and pocketbase stacks