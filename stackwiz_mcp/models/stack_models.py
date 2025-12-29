"""
Stack-related data models for StackWiz MCP Server
"""

from enum import Enum
from typing import Optional, Dict, Any, List
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict


class StackType(str, Enum):
    """Types of stacks that can be created"""
    GENERIC = "generic"
    POCKETBASE = "pocketbase"


class StackStatus(str, Enum):
    """Stack status values"""
    RUNNING = "running"
    STOPPED = "stopped"
    CREATED = "created"
    ERROR = "error"
    UNKNOWN = "unknown"


class StackOperation(str, Enum):
    """Operations that can be performed on stacks"""
    START = "start"
    STOP = "stop"
    RESTART = "restart"
    REMOVE = "remove"
    LOGS = "logs"


class DnsRecordType(str, Enum):
    """DNS record types"""
    A = "A"
    AAAA = "AAAA"
    CNAME = "CNAME"
    MX = "MX"
    TXT = "TXT"
    SRV = "SRV"
    NS = "NS"


class StackConfig(BaseModel):
    """Configuration for creating a new stack"""
    
    model_config = ConfigDict(use_enum_values=True)
    
    # Basic configuration
    name: str = Field(..., description="Stack name", pattern="^[a-z0-9-]+$")
    type: StackType = Field(default=StackType.GENERIC, description="Stack type")
    
    # Domain configuration
    domain: Optional[str] = Field(None, description="Custom domain (defaults to {name}.rbnk.uk)")
    subdomain: Optional[str] = Field(None, description="Subdomain (defaults to stack name)")
    
    # Generic stack configuration
    image: Optional[str] = Field(None, description="Docker image (required for generic)")
    port: Optional[int] = Field(None, description="Container port (required for generic)", ge=1, le=65535)
    service_name: Optional[str] = Field(None, description="Service name (defaults to stack name)")
    
    # Network configuration
    network: str = Field(default="traefik_proxy", description="Docker network")
    entrypoint: str = Field(default="websecure", description="Traefik entrypoint")
    certresolver: str = Field(default="cf", description="Certificate resolver")
    
    # Options
    create_dns: bool = Field(default=False, description="Create DNS record")
    auto_start: bool = Field(default=False, description="Start stack after creation")
    environment: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    labels: Dict[str, str] = Field(default_factory=dict, description="Additional Docker labels")
    volumes: List[str] = Field(default_factory=list, description="Volume mappings")
    
    # Pocketbase-specific options
    include_frontend: bool = Field(default=False, description="Include frontend stack (Pocketbase only)")
    frontend_port: Optional[int] = Field(default=3000, description="Frontend port", ge=1, le=65535)
    
    @field_validator("name")
    def validate_name(cls, v: str) -> str:
        """Validate stack name"""
        if len(v) < 3:
            raise ValueError("Stack name must be at least 3 characters")
        if len(v) > 50:
            raise ValueError("Stack name must be less than 50 characters")
        if not v.replace("-", "").isalnum():
            raise ValueError("Stack name must contain only letters, numbers, and hyphens")
        return v
    
    @field_validator("image")
    def validate_image_for_generic(cls, v: Optional[str]) -> Optional[str]:
        """Validate image is provided for generic stacks"""
        # Note: In Pydantic V2, cross-field validation should be done in model_validator
        # This validator only checks the image field itself
        return v
    
    @field_validator("port")
    def validate_port_for_generic(cls, v: Optional[int]) -> Optional[int]:
        """Validate port is provided for generic stacks"""
        # Note: In Pydantic V2, cross-field validation should be done in model_validator
        # This validator only checks the port field itself
        return v
    
    @field_validator("domain")
    def validate_domain(cls, v: Optional[str]) -> Optional[str]:
        """Validate domain format"""
        if v and not v.replace("-", "").replace(".", "").isalnum():
            raise ValueError("Invalid domain format")
        return v
    
    @model_validator(mode='after')
    def validate_generic_requirements(self):
        """Validate that generic stacks have required fields"""
        if self.type == StackType.GENERIC:
            if not self.image:
                raise ValueError("Image is required for generic stacks")
            if not self.port:
                raise ValueError("Port is required for generic stacks")
        return self


class StackInfo(BaseModel):
    """Information about an existing stack"""
    
    name: str = Field(..., description="Stack name")
    type: StackType = Field(..., description="Stack type")
    status: StackStatus = Field(..., description="Current status")
    created_at: datetime = Field(..., description="Creation timestamp")
    domain: str = Field(..., description="Stack domain")
    path: str = Field(..., description="Stack directory path")
    
    # Container information
    containers: List[Dict[str, Any]] = Field(default_factory=list, description="Container details")
    
    # Configuration
    config: Dict[str, Any] = Field(default_factory=dict, description="Stack configuration")
    environment: Dict[str, str] = Field(default_factory=dict, description="Environment variables")
    
    # Metrics
    cpu_usage: Optional[float] = Field(None, description="CPU usage percentage")
    memory_usage: Optional[float] = Field(None, description="Memory usage in MB")
    
    @property
    def is_running(self) -> bool:
        """Check if stack is running"""
        return self.status == StackStatus.RUNNING
    
    @property
    def url(self) -> str:
        """Get stack URL"""
        return f"https://{self.domain}"


class DnsRecord(BaseModel):
    """DNS record configuration"""
    
    subdomain: str = Field(..., description="Subdomain")
    type: DnsRecordType = Field(default=DnsRecordType.A, description="Record type")
    value: str = Field(default="AUTO", description="Record value (AUTO for server IP)")
    priority: Optional[int] = Field(None, description="Priority (for MX records)", ge=0, le=65535)
    proxied: bool = Field(default=True, description="Enable Cloudflare proxy")
    ttl: int = Field(default=300, description="TTL in seconds", ge=60)
    
    @field_validator("subdomain")
    def validate_subdomain(cls, v: str) -> str:
        """Validate subdomain format"""
        if not v.replace("-", "").replace("_", "").isalnum():
            raise ValueError("Invalid subdomain format")
        return v.lower()
    
    @field_validator("priority")
    def validate_priority_for_mx(cls, v: Optional[int]) -> Optional[int]:
        """Validate priority is provided for MX records"""
        # Note: In Pydantic V2, cross-field validation should be done in model_validator
        # This validator only checks the priority field itself
        return v
    
    @model_validator(mode='after')
    def validate_mx_requirements(self):
        """Validate that MX records have required fields"""
        if self.type == DnsRecordType.MX and self.priority is None:
            raise ValueError("Priority is required for MX records")
        return self


class ValidationError(BaseModel):
    """Validation error details"""
    
    field: str = Field(..., description="Field name")
    message: str = Field(..., description="Error message")
    suggestion: Optional[str] = Field(None, description="Suggested fix")


class ValidationResult(BaseModel):
    """Result of configuration validation"""
    
    valid: bool = Field(..., description="Whether configuration is valid")
    errors: List[ValidationError] = Field(default_factory=list, description="Validation errors")
    warnings: List[str] = Field(default_factory=list, description="Validation warnings")
    
    # Conflict information
    port_conflicts: List[int] = Field(default_factory=list, description="Conflicting ports")
    domain_conflicts: List[str] = Field(default_factory=list, description="Conflicting domains")
    
    @property
    def has_errors(self) -> bool:
        """Check if there are any errors"""
        return len(self.errors) > 0
    
    @property
    def has_warnings(self) -> bool:
        """Check if there are any warnings"""
        return len(self.warnings) > 0
    
    def add_error(self, field: str, message: str, suggestion: Optional[str] = None):
        """Add a validation error"""
        self.errors.append(ValidationError(
            field=field,
            message=message,
            suggestion=suggestion
        ))
        self.valid = False
    
    def add_warning(self, message: str):
        """Add a validation warning"""
        self.warnings.append(message)


class OperationResult(BaseModel):
    """Result of a stack operation"""
    
    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Result message")
    operation: str = Field(..., description="Operation performed")
    stack_name: str = Field(..., description="Stack name")
    
    # Optional details
    output: Optional[str] = Field(None, description="Command output")
    error: Optional[str] = Field(None, description="Error details")
    duration_seconds: Optional[float] = Field(None, description="Operation duration")
    
    # Post-operation state
    stack_status: Optional[StackStatus] = Field(None, description="Stack status after operation")
    
    @classmethod
    def success_result(cls, operation: str, stack_name: str, message: str, **kwargs) -> "OperationResult":
        """Create a success result"""
        return cls(
            success=True,
            operation=operation,
            stack_name=stack_name,
            message=message,
            **kwargs
        )
    
    @classmethod
    def error_result(cls, operation: str, stack_name: str, error: str, **kwargs) -> "OperationResult":
        """Create an error result"""
        return cls(
            success=False,
            operation=operation,
            stack_name=stack_name,
            message=f"Operation failed: {error}",
            error=error,
            **kwargs
        )


class StackOperationParams(BaseModel):
    """Parameters for stack operations (start, stop, restart, remove)"""
    
    name: str = Field(..., description="Stack name")
    force: bool = Field(default=False, description="Force operation (e.g., remove volumes)")


class StackLogsParams(BaseModel):
    """Parameters for retrieving stack logs"""
    
    name: str = Field(..., description="Stack name")
    lines: int = Field(default=100, description="Number of log lines to retrieve", ge=1, le=10000)
    service: Optional[str] = Field(None, description="Specific service to get logs from")
    follow: bool = Field(default=False, description="Follow log output")


class StackOperationResult(BaseModel):
    """Result of a stack operation"""
    
    success: bool = Field(..., description="Whether operation succeeded")
    message: str = Field(..., description="Result message")
    error: Optional[str] = Field(None, description="Error details if failed")
    details: Optional[Dict[str, Any]] = Field(None, description="Additional operation details")