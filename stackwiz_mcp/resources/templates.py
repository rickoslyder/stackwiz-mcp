"""
Templates Resource - Provides access to stack templates
"""

from typing import Dict, Any, List
import os
from pathlib import Path
from ..utils.logging import get_logger

logger = get_logger(__name__)


class TemplatesResource:
    """Resource for accessing stack templates"""
    
    @staticmethod
    def register(mcp):
        """Register the resource with the MCP server"""
        
        templates_dir = Path("/srv/dockerdata/_templates")
        
        @mcp.resource("template://list")
        async def list_templates() -> List[str]:
            """List available templates"""
            try:
                if not templates_dir.exists():
                    logger.error(f"Templates directory not found: {templates_dir}")
                    return []
                
                # List all template files
                templates = []
                for file in templates_dir.iterdir():
                    if file.is_file() and (file.suffix in ['.yml', '.yaml'] or 'template' in file.name):
                        templates.append(file.name)
                
                logger.info(f"Found {len(templates)} template files")
                return sorted(templates)
            except Exception as e:
                logger.error(f"Error listing templates: {e}")
                return []
        
        @mcp.resource("template://generic")
        async def get_generic_template() -> str:
            """Get generic stack template with docker-compose and env files"""
            try:
                # Read docker-compose template
                compose_path = templates_dir / "stack-template.yml"
                env_path = templates_dir / "env-template"
                
                if not compose_path.exists() or not env_path.exists():
                    logger.error("Generic template files not found")
                    return "# Template files not found"
                
                compose_content = compose_path.read_text()
                env_content = env_path.read_text()
                
                # Combine both templates with separators
                return f"""# Generic Stack Template
# This template provides a basic Docker service with Traefik integration

## Docker Compose Template (docker-compose.yml):
{compose_content}

## Environment Template (.env):
{env_content}

## Usage:
# 1. Replace all __PLACEHOLDER__ values with actual values
# 2. Save docker-compose content to docker-compose.yml
# 3. Save environment content to .env
# 4. Run: docker compose up -d
"""
            except Exception as e:
                logger.error(f"Error reading generic template: {e}")
                return f"# Error reading template: {str(e)}"
        
        @mcp.resource("template://pocketbase")
        async def get_pocketbase_template() -> str:
            """Get Pocketbase stack template with docker-compose and env files"""
            try:
                # Read docker-compose template
                compose_path = templates_dir / "pocketbase-template.yml"
                env_path = templates_dir / "pocketbase-env-template"
                
                if not compose_path.exists() or not env_path.exists():
                    logger.error("Pocketbase template files not found")
                    return "# Template files not found"
                
                compose_content = compose_path.read_text()
                env_content = env_path.read_text()
                
                # Combine both templates with separators
                return f"""# Pocketbase Stack Template
# This template provides a complete Pocketbase backend-as-a-service setup

## Docker Compose Template (docker-compose.yml):
{compose_content}

## Environment Template (.env):
{env_content}

## Usage:
# 1. Replace all __PLACEHOLDER__ values with actual values
# 2. Generate PB_ENCRYPTION_KEY with: openssl rand -hex 16
# 3. Save docker-compose content to docker-compose.yml
# 4. Save environment content to .env
# 5. Run: docker compose up -d
# 6. Access admin UI at: http://localhost:8090/_/
"""
            except Exception as e:
                logger.error(f"Error reading pocketbase template: {e}")
                return f"# Error reading template: {str(e)}"
        
        @mcp.resource("template://supabase")
        async def get_supabase_template() -> str:
            """Get Supabase stack template with docker-compose and env files"""
            try:
                # Read docker-compose template
                compose_path = templates_dir / "supabase-template.yml"
                env_path = templates_dir / "supabase-env-template"
                
                if not compose_path.exists() or not env_path.exists():
                    logger.error("Supabase template files not found")
                    return "# Template files not found"
                
                compose_content = compose_path.read_text()
                env_content = env_path.read_text()
                
                # Combine both templates with separators
                return f"""# Supabase Stack Template
# This template provides a complete self-hosted Supabase setup

## Docker Compose Template (docker-compose.yml):
{compose_content}

## Environment Template (supabase.env):
{env_content}

## Usage:
# 1. Replace all __PLACEHOLDER__ values with actual values
# 2. Generate secure passwords and JWT secrets
# 3. Save docker-compose content to docker-compose.yml
# 4. Save environment content to supabase.env
# 5. Create bootstrap-sql directory for initialization scripts
# 6. Run: docker compose up -d
# 7. Access Studio at: https://your-domain/
"""
            except Exception as e:
                logger.error(f"Error reading supabase template: {e}")
                return f"# Error reading template: {str(e)}"