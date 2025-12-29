# StackWiz MCP Server

Transform your Docker infrastructure management with an AI-powered Model Context Protocol (MCP) server. StackWiz MCP enables AI assistants like Claude to create, manage, and deploy containerized services in your infrastructure programmatically.

## 📖 Documentation

| Document | Purpose |
|----------|---------|
| [CLAUDE.md](CLAUDE.md) | Quick reference for Claude Code agents |
| [docs/AGENT_REFERENCE.md](docs/AGENT_REFERENCE.md) | **Canonical documentation** - complete tool reference |
| [INSTALL.md](INSTALL.md) | Installation guide for standalone deployment |

**For AI Agents**: Start with `CLAUDE.md`, refer to `docs/AGENT_REFERENCE.md` for detailed tool parameters.

## 🚀 Quick Start

### Installation

```bash
# Install from Git (recommended)
pip install git+https://gitea.rbnk.uk/admin/stackwiz-mcp.git
# Or from GitHub:
pip install git+https://github.com/rickoslyder/stackwiz-mcp.git

# Or clone and install locally
git clone https://gitea.rbnk.uk/admin/stackwiz-mcp.git
cd stackwiz-mcp
pip install -e .
```

### Claude Desktop Integration

Add to your Claude Desktop configuration (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "stackwiz": {
      "command": "python",
      "args": ["-m", "stackwiz_mcp"],
      "env": {
        "STACKWIZ_BASE_DIR": "/srv/dockerdata",
        "STACKWIZ_LOG_LEVEL": "INFO"
      }
    }
  }
}
```

### Basic Usage

Once configured, you can ask Claude to:

- "Create a new Grafana monitoring service"
- "Deploy a Pocketbase backend for my todo app"
- "List all running Docker stacks"
- "Create a PostgreSQL database with automatic backups"
- "Set up a Ghost blog with custom domain"

## 🎯 Features

### Stack Management
- **Create Stacks**: Deploy any Docker container with automatic Traefik integration
- **Pocketbase Support**: Specialized support for Pocketbase backends
- **List & Monitor**: View all stacks with real-time status
- **Lifecycle Control**: Start, stop, restart, and remove stacks
- **Log Access**: Retrieve container logs for debugging

### DNS Automation
- **Cloudflare Integration**: Full DNS record management (create, list, update, delete)
- **Multiple Record Types**: A, AAAA, CNAME, TXT, MX support
- **Smart Defaults**: Auto-detect server IP for A records
- **Proxy Control**: Toggle Cloudflare proxy (orange/gray cloud) per record
- **Rate Limit Handling**: Automatic retry with exponential backoff
- **Zone ID Caching**: Efficient API usage with 5-minute cache

### Infrastructure Integration
- **Traefik Ready**: Automatic SSL/TLS with Let's Encrypt
- **Network Management**: Proper Docker network configuration
- **Permission Handling**: Secure file permissions (750/640)
- **Template System**: Consistent stack structure

## 📚 Available Tools

### `create_stack`
Creates a new Docker service stack.

**Parameters:**
- `name` (required): Stack identifier (lowercase, alphanumeric + hyphens)
- `type`: "generic" or "pocketbase"
- `domain`: Full domain for the service
- `image`: Docker image (required for generic)
- `port`: Container port (required for generic)
- `create_dns`: Auto-create DNS record
- `auto_start`: Start immediately after creation
- `environment`: Additional environment variables

### `list_stacks`
Lists all Docker stacks in the infrastructure.

**Parameters:**
- `filter`: Filter stacks by name
- `include_status`: Include container status
- `sort_by`: Sort by name, created, or status

### `manage_stack`
Performs operations on existing stacks.

**Parameters:**
- `stack_name` (required): Target stack
- `action`: start, stop, restart, remove, logs
- `options`: Additional options (follow_logs, tail_lines)

### `create_dns_record`
Creates DNS records in Cloudflare with automatic retry and rate limit handling.

**Parameters:**
- `subdomain` (required): Subdomain to create
- `type`: Record type (A, CNAME, MX, TXT)
- `value`: Record value (AUTO for server IP)
- `proxied`: Enable Cloudflare proxy

### `list_dns_records`
Lists DNS records from Cloudflare.

**Parameters:**
- `filter`: Filter records by name (partial match)

### `update_dns_proxy`
Toggles Cloudflare proxy for a DNS record.

**Parameters:**
- `subdomain` (required): Target subdomain
- `enable` (required): true for proxied, false for DNS-only

### `delete_dns_record`
Deletes DNS records from Cloudflare.

**Parameters:**
- `subdomain` (required): Subdomain to delete

### `validate_stack_config`
Validates configuration before creation.

**Parameters:**
- `config` (required): Stack configuration object
- `check_conflicts`: Check for port/domain conflicts

## 🗂️ Resources

The MCP server provides read access to:

- **Stack Configurations**: `stack://list`, `stack://{name}/compose`
- **Templates**: `template://generic`, `template://pocketbase`
- **Infrastructure Info**: `infra://networks`, `infra://domains`

## 💡 Prompts

Interactive deployment guides:

- `deploy-web-app`: Step-by-step web application deployment
- `setup-database`: Database deployment with best practices
- `create-api-service`: API service with monitoring

## 🏗️ Architecture

```
stackwiz-mcp/
├── stackwiz_mcp/          # Main package
│   ├── server.py          # FastMCP server (preferred)
│   ├── mcp_server.py      # Standard MCP implementation
│   ├── config.py          # Configuration management
│   ├── tools/             # MCP tool implementations
│   ├── resources/         # Resource providers
│   ├── prompts/          # Interactive prompts
│   ├── models/           # Pydantic models
│   └── utils/            # Utilities
├── tests/                # Test suite
├── docs/                 # Documentation
└── examples/             # Usage examples
```

## 🧪 Testing

```bash
# Run the test suite
./run_tests.sh

# Manual testing
python test_server.py

# Run specific tests
pytest tests/test_mcp_server.py -v
```

## 🐳 Docker Deployment

```bash
# Build and run with Docker
docker compose up -d

# View logs
docker compose logs -f

# Stop the server
docker compose down
```

## ⚙️ Configuration

### Environment Variables

- `STACKWIZ_BASE_DIR`: Base directory for stacks (default: `/srv/dockerdata`)
- `STACKWIZ_LOG_LEVEL`: Logging level (DEBUG, INFO, WARNING, ERROR)
- `STACKWIZ_ENV`: Environment (development, production)
- `DOCKER_HOST`: Docker daemon socket
- `CF_API_EMAIL`: Cloudflare email
- `CF_DNS_API_TOKEN`: Cloudflare API token
- `DEFAULT_USER`: File owner (default: current user)
- `DEFAULT_GROUP`: File group (default: docker)

### Configuration File

Create `config.json` for persistent settings:

```json
{
  "docker": {
    "network": "traefik_proxy",
    "compose_timeout": 30
  },
  "dns": {
    "default_ttl": 300,
    "proxied": true
  },
  "traefik": {
    "entrypoint": "websecure",
    "certresolver": "cf"
  }
}
```

## 🔒 Security

- **Input Validation**: All inputs validated with Pydantic
- **Command Injection Protection**: Safe command execution
- **Path Traversal Prevention**: Restricted to base directory
- **Secrets Management**: Environment variables never logged
- **Permission Management**: Proper Unix permissions

## 🤝 Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests for new functionality
5. Run the test suite
6. Submit a pull request

## 📝 License

MIT License - See LICENSE file for details.

## 🙏 Acknowledgments

- Built on the [Model Context Protocol](https://modelcontextprotocol.io) specification
- Uses [FastMCP](https://github.com/jlowin/fastmcp) framework
- Inspired by the original stackwiz shell script

## 🐛 Troubleshooting

### Server won't start
- Check Python version (3.8+ required)
- Verify dependencies: `pip install -r requirements.txt`
- Check permissions on base directory

### Tools not working
- Ensure Docker daemon is running
- Verify user is in docker group
- Check `DOCKER_HOST` environment variable

### DNS creation fails
- Verify Cloudflare API credentials (CF_API_TOKEN or CF_DNS_API_TOKEN)
- Check domain is managed by Cloudflare
- Ensure API token has DNS edit permissions
- Rate limits are handled automatically with retries
- See logs for detailed error messages

### DNS proxy toggle fails
- Only A, AAAA, and CNAME records can be proxied
- MX and TXT records cannot be proxied (Cloudflare limitation)

### Logs location
- Server logs: `~/.cache/stackwiz-mcp/logs/`
- Stack logs: `docker compose -f {stack}/docker-compose.yml logs`

## 📞 Support

- GitHub Issues: Report bugs and feature requests
- Documentation: See `/docs` directory
- Examples: Check `/examples` for usage patterns