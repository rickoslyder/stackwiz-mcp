"""
Deployment Prompts - Interactive prompts for common deployment tasks
"""

from typing import Dict, Any
from ..utils.logging import get_logger

logger = get_logger(__name__)


class DeployWebAppPrompt:
    """Interactive prompt for deploying web applications"""
    
    @staticmethod
    def register(mcp):
        """Register the prompt with the MCP server"""
        
        @mcp.prompt("deploy-web-app")
        async def deploy_web_app_prompt() -> str:
            """Interactive prompt for deploying a web application"""
            return """I'll help you deploy a web application. Please provide:

1. **Application Name**: What should we call this application?
2. **Application Type**: Is this a static site, Node.js app, Python app, or something else?
3. **Domain**: Do you want a custom domain or use the default {name}.rbnk.uk?
4. **Database**: Does this app need a database? (PostgreSQL, MySQL, MongoDB, etc.)
5. **Environment Variables**: Any environment variables needed?
6. **SSL**: Should we enable HTTPS? (recommended)
7. **Monitoring**: Do you want to set up monitoring and alerts?

Based on your answers, I'll create the appropriate stack configuration and deploy it.
"""


class SetupDatabasePrompt:
    """Interactive prompt for setting up databases"""
    
    @staticmethod
    def register(mcp):
        """Register the prompt with the MCP server"""
        
        @mcp.prompt("setup-database")
        async def setup_database_prompt() -> str:
            """Guided database deployment with best practices"""
            return """Let's set up a database with best practices. I need to know:

1. **Database Type**: PostgreSQL, MySQL, MongoDB, Redis, or other?
2. **Purpose**: What will this database be used for?
3. **Size**: Expected data size and growth rate?
4. **Backup Strategy**: How often should we backup? Where to store backups?
5. **Access Control**: Who needs access? From where?
6. **Performance**: Any specific performance requirements?
7. **High Availability**: Do you need replication or clustering?

I'll configure the database with security best practices, automated backups, and monitoring.
"""


class CreateApiServicePrompt:
    """Interactive prompt for creating API services"""
    
    @staticmethod
    def register(mcp):
        """Register the prompt with the MCP server"""
        
        @mcp.prompt("create-api-service")
        async def create_api_service_prompt() -> str:
            """API service deployment with monitoring"""
            return """I'll help you deploy an API service with proper monitoring. Please provide:

1. **API Name**: What's the name of your API service?
2. **Technology**: What framework/language? (Express, FastAPI, Spring Boot, etc.)
3. **Authentication**: What auth method? (JWT, OAuth, API Keys, etc.)
4. **Rate Limiting**: Do you need rate limiting? What limits?
5. **Documentation**: Should we set up API documentation? (Swagger/OpenAPI)
6. **Monitoring**: What metrics are important? (response time, error rate, etc.)
7. **Scaling**: Expected request volume? Need auto-scaling?

I'll set up the API with proper security, monitoring dashboards, and alerting.
"""