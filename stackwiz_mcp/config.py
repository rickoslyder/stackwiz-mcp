"""
Configuration management for StackWiz MCP Server
"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from enum import Enum
from pydantic import BaseModel, Field, field_validator, model_validator
from pydantic_settings import BaseSettings


class Environment(str, Enum):
    """Deployment environment"""
    DEVELOPMENT = "development"
    PRODUCTION = "production"
    TESTING = "testing"


class AuthConfig(BaseModel):
    """Authentication configuration"""
    enabled: bool = Field(default=False, description="Enable authentication")
    oauth_provider: Optional[str] = Field(default=None, description="OAuth provider URL")
    client_id: Optional[str] = Field(default=None, description="OAuth client ID")
    client_secret: Optional[str] = Field(default=None, description="OAuth client secret")
    allowed_users: list[str] = Field(default_factory=list, description="Allowed user emails")
    
    @model_validator(mode='after')
    def validate_oauth_config(self):
        """Validate OAuth configuration completeness"""
        if self.enabled:
            if not self.oauth_provider:
                raise ValueError("OAuth provider required when auth is enabled")
            if not self.client_id:
                raise ValueError("OAuth client ID required when auth is enabled")
            if not self.client_secret:
                raise ValueError("OAuth client secret required when auth is enabled")
        return self


class DockerConfig(BaseModel):
    """Docker configuration"""
    socket_path: str = Field(default="/var/run/docker.sock", description="Docker socket path")
    timeout: int = Field(default=30, description="Docker operation timeout")
    network_name: str = Field(default="traefik_proxy", description="Default Docker network")


class DnsConfig(BaseModel):
    """DNS configuration"""
    provider: str = Field(default="cloudflare", description="DNS provider")
    zone_name: str = Field(default="rbnk.uk", description="DNS zone name")
    api_token: Optional[str] = Field(default=None, description="DNS API token")
    api_email: Optional[str] = Field(default=None, description="Cloudflare email")
    default_ttl: int = Field(default=300, description="Default DNS TTL")
    proxied: bool = Field(default=True, description="Enable Cloudflare proxy by default")

    @property
    def domain(self) -> str:
        """Alias for zone_name for backwards compatibility"""
        return self.zone_name


class TraefikConfig(BaseModel):
    """Traefik configuration"""
    entrypoint: str = Field(default="websecure", description="Default entrypoint")
    certresolver: str = Field(default="cf", description="Default cert resolver")
    middleware: list[str] = Field(default_factory=list, description="Default middleware")


class LoggingConfig(BaseModel):
    """Logging configuration"""
    level: str = Field(default="INFO", description="Log level")
    format: str = Field(default="json", description="Log format (json or text)")
    file_path: Optional[Path] = Field(default=None, description="Log file path")
    max_size_mb: int = Field(default=100, description="Max log file size in MB")
    backup_count: int = Field(default=5, description="Number of log backups to keep")


class Config(BaseSettings):
    """Main configuration class"""
    
    # Environment
    environment: Environment = Field(
        default=Environment.PRODUCTION,
        description="Deployment environment"
    )
    
    # Paths
    base_dir: Path = Field(
        default=Path("/srv/dockerdata"),
        description="Base directory for Docker data"
    )
    templates_dir: Path = Field(
        default=Path("/srv/dockerdata/_templates"),
        description="Templates directory"
    )
    scripts_dir: Path = Field(
        default=Path("/srv/dockerdata/_scripts"),
        description="Scripts directory"
    )
    
    # Server configuration
    server_name: str = Field(default="stackwiz-mcp", description="Server name")
    server_host: str = Field(default="0.0.0.0", description="Server host")
    server_port: int = Field(default=8000, description="Server port")
    
    # Feature flags
    auto_start_stacks: bool = Field(default=False, description="Auto-start stacks after creation")
    validate_before_create: bool = Field(default=True, description="Validate configs before creation")
    enable_monitoring: bool = Field(default=True, description="Enable monitoring endpoints")
    
    # Sub-configurations
    auth: AuthConfig = Field(default_factory=AuthConfig)
    docker: DockerConfig = Field(default_factory=DockerConfig)
    dns: DnsConfig = Field(default_factory=DnsConfig)
    traefik: TraefikConfig = Field(default_factory=TraefikConfig)
    logging: LoggingConfig = Field(default_factory=LoggingConfig)
    
    # Secrets (loaded from environment via STACKWIZ_ prefix)
    cf_api_token: Optional[str] = Field(default=None, description="Cloudflare API token")
    cf_api_email: Optional[str] = Field(default=None, description="Cloudflare API email")
    
    # Performance
    cache_ttl: int = Field(default=300, description="Cache TTL in seconds")
    max_concurrent_operations: int = Field(default=10, description="Max concurrent operations")
    operation_timeout: int = Field(default=300, description="Operation timeout in seconds")
    
    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "env_prefix": "STACKWIZ_",
        "case_sensitive": False
    }
        
    @field_validator("base_dir", "templates_dir", "scripts_dir")
    def validate_paths(cls, v: Path) -> Path:
        """Ensure paths exist"""
        if not v.exists():
            raise ValueError(f"Path does not exist: {v}")
        return v
    
    @model_validator(mode='after')
    def populate_dns_config(self):
        """Populate DNS config from environment if not set.

        Tries multiple environment variable names for flexibility:
        - CF_API_TOKEN, CF_DNS_API_TOKEN (direct)
        - STACKWIZ_CF_API_TOKEN (with prefix)
        """
        import os

        # Try to get API token from various sources
        if not self.dns.api_token:
            # Priority order for API token
            token_candidates = [
                self.cf_api_token,
                os.environ.get("CF_API_TOKEN"),
                os.environ.get("CF_DNS_API_TOKEN"),
                os.environ.get("CLOUDFLARE_DNS_API_TOKEN"),
            ]
            for token in token_candidates:
                if token:
                    self.dns.api_token = token
                    break

        # Try to get API email from various sources
        if not self.dns.api_email:
            email_candidates = [
                self.cf_api_email,
                os.environ.get("CF_API_EMAIL"),
                os.environ.get("CLOUDFLARE_EMAIL"),
            ]
            for email in email_candidates:
                if email:
                    self.dns.api_email = email
                    break

        return self
    
    @property
    def auth_enabled(self) -> bool:
        """Check if authentication is enabled"""
        return self.auth.enabled
    
    @property
    def is_development(self) -> bool:
        """Check if running in development mode"""
        return self.environment == Environment.DEVELOPMENT
    
    @property
    def is_production(self) -> bool:
        """Check if running in production mode"""
        return self.environment == Environment.PRODUCTION
    
    def get_stack_dir(self, stack_name: str) -> Path:
        """Get directory path for a stack"""
        return self.base_dir / stack_name
    
    def get_compose_file(self, stack_name: str) -> Path:
        """Get docker-compose.yml path for a stack"""
        return self.get_stack_dir(stack_name) / "docker-compose.yml"
    
    def get_env_file(self, stack_name: str) -> Path:
        """Get .env file path for a stack"""
        return self.get_stack_dir(stack_name) / ".env"
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary (with secrets masked)"""
        data = self.dict()
        
        # Mask sensitive values
        if data.get("cf_api_token"):
            data["cf_api_token"] = "***"
        if data.get("cf_api_email"):
            data["cf_api_email"] = "***@***"
        if data.get("auth", {}).get("client_secret"):
            data["auth"]["client_secret"] = "***"
        if data.get("dns", {}).get("api_token"):
            data["dns"]["api_token"] = "***"
            
        return data


# Singleton instance
_config: Optional[Config] = None


def get_config() -> Config:
    """Get configuration singleton"""
    global _config
    if _config is None:
        _config = Config()
    return _config


def reload_config() -> Config:
    """Reload configuration from environment"""
    global _config
    _config = Config()
    return _config