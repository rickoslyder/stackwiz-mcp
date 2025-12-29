"""
Logging configuration for StackWiz MCP Server
"""

import logging
import logging.handlers
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
try:
    # New import path (pythonjsonlogger >= 3.0)
    from pythonjsonlogger.json import JsonFormatter as BaseJsonFormatter
except ImportError:
    # Fallback to old import path
    from pythonjsonlogger import jsonlogger
    BaseJsonFormatter = jsonlogger.JsonFormatter

from ..config import get_config


class ContextFilter(logging.Filter):
    """Add context information to log records"""
    
    def filter(self, record: logging.LogRecord) -> bool:
        """Add custom fields to log record"""
        record.server_name = "stackwiz-mcp"
        record.environment = get_config().environment.value
        record.timestamp = datetime.utcnow().isoformat()
        return True


class CustomJsonFormatter(BaseJsonFormatter):
    """Custom JSON formatter with additional fields"""
    
    def add_fields(self, log_record: Dict[str, Any], record: logging.LogRecord, message_dict: Dict[str, Any]):
        """Add custom fields to JSON log"""
        super().add_fields(log_record, record, message_dict)
        
        # Add standard fields
        log_record["level"] = record.levelname
        log_record["logger"] = record.name
        log_record["timestamp"] = getattr(record, "timestamp", datetime.utcnow().isoformat())
        log_record["server_name"] = getattr(record, "server_name", "stackwiz-mcp")
        log_record["environment"] = getattr(record, "environment", "unknown")
        
        # Add exception info if present
        if record.exc_info:
            log_record["exception"] = self.formatException(record.exc_info)
        
        # Add extra fields
        for key, value in record.__dict__.items():
            if key not in log_record and not key.startswith("_"):
                log_record[key] = value


def setup_logging(log_level: Optional[str] = None) -> None:
    """
    Configure logging for the application
    
    Args:
        log_level: Override log level from config
    """
    config = get_config()
    
    # Determine log level
    level = log_level or config.logging.level
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    
    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    
    # Remove existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Create formatter based on config
    if config.logging.format == "json":
        formatter = CustomJsonFormatter(
            "%(timestamp)s %(level)s %(name)s %(message)s",
            timestamp=True
        )
    else:
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
    
    # Console handler - MUST use stderr for MCP servers (stdout is for JSON-RPC)
    console_handler = logging.StreamHandler(sys.stderr)
    console_handler.setFormatter(formatter)
    console_handler.addFilter(ContextFilter())
    root_logger.addHandler(console_handler)
    
    # File handler if configured
    if config.logging.file_path:
        file_path = Path(config.logging.file_path)
        file_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.handlers.RotatingFileHandler(
            filename=str(file_path),
            maxBytes=config.logging.max_size_mb * 1024 * 1024,
            backupCount=config.logging.backup_count,
            encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        file_handler.addFilter(ContextFilter())
        root_logger.addHandler(file_handler)
    
    # Set levels for specific loggers
    logging.getLogger("docker").setLevel(logging.WARNING)
    logging.getLogger("urllib3").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)
    
    # More verbose logging in development
    if config.is_development:
        logging.getLogger("stackwiz_mcp").setLevel(logging.DEBUG)
    
    # Log startup message
    logger = logging.getLogger(__name__)
    logger.info(
        "Logging configured",
        extra={
            "log_level": level,
            "log_format": config.logging.format,
            "file_logging": bool(config.logging.file_path)
        }
    )


def get_logger(name: str) -> logging.Logger:
    """
    Get a logger instance
    
    Args:
        name: Logger name (usually __name__)
        
    Returns:
        Configured logger instance
    """
    return logging.getLogger(name)


class LogContext:
    """Context manager for adding temporary log context"""
    
    def __init__(self, logger: logging.Logger, **kwargs):
        self.logger = logger
        self.context = kwargs
        self.old_factory = None
    
    def __enter__(self):
        """Enter context and add fields"""
        old_factory = logging.getLogRecordFactory()
        
        def record_factory(*args, **kwargs):
            record = old_factory(*args, **kwargs)
            for key, value in self.context.items():
                setattr(record, key, value)
            return record
        
        logging.setLogRecordFactory(record_factory)
        self.old_factory = old_factory
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Exit context and restore factory"""
        if self.old_factory:
            logging.setLogRecordFactory(self.old_factory)


def log_operation(operation_type: str, operation_id: str):
    """
    Decorator to log operation execution
    
    Args:
        operation_type: Type of operation
        operation_id: Unique operation ID
    """
    def decorator(func):
        async def async_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            
            with LogContext(logger, operation_type=operation_type, operation_id=operation_id):
                logger.info(f"Starting {operation_type}", extra={"args": args, "kwargs": kwargs})
                
                try:
                    result = await func(*args, **kwargs)
                    logger.info(f"Completed {operation_type}", extra={"result": result})
                    return result
                except Exception as e:
                    logger.error(f"Failed {operation_type}", exc_info=True, extra={"error": str(e)})
                    raise
        
        def sync_wrapper(*args, **kwargs):
            logger = get_logger(func.__module__)
            
            with LogContext(logger, operation_type=operation_type, operation_id=operation_id):
                logger.info(f"Starting {operation_type}", extra={"args": args, "kwargs": kwargs})
                
                try:
                    result = func(*args, **kwargs)
                    logger.info(f"Completed {operation_type}", extra={"result": result})
                    return result
                except Exception as e:
                    logger.error(f"Failed {operation_type}", exc_info=True, extra={"error": str(e)})
                    raise
        
        # Return appropriate wrapper based on function type
        import asyncio
        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        else:
            return sync_wrapper
    
    return decorator