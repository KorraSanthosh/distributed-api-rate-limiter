import logging
import os
import sys
from logging.handlers import RotatingFileHandler
from datetime import datetime, timezone
import json

from app.core.config import settings


class StructuredJSONFormatter(logging.Formatter):
    """Formats log records as structured JSON strings for production parsing."""

    def format(self, record: logging.LogRecord) -> str:
        # Construct the base JSON log payload
        log_payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "func_name": record.funcName,
            "line_number": record.lineno,
        }

        # Dynamically inject context-specific HTTP keys if present
        context_keys = [
            "request_id",
            "client_ip",
            "method",
            "endpoint",
            "status_code",
            "latency_ms",
            "allowed",
            "error_detail",
        ]
        for key in context_keys:
            if hasattr(record, key):
                log_payload[key] = getattr(record, key)

        # Include exception tracebacks if present
        if record.exc_info:
            log_payload["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_payload)


class ConsoleDevelopmentFormatter(logging.Formatter):
    """Formats log records in a highly readable way for terminal output in development."""

    # ANSI terminal color escape codes
    COLORS = {
        "DEBUG": "\033[36m",    # Cyan
        "INFO": "\033[32m",     # Green
        "WARNING": "\033[33m",  # Yellow
        "ERROR": "\033[31m",    # Red
        "CRITICAL": "\033[41m\033[37m",  # Red background, white text
        "RESET": "\033[0m",
    }

    def format(self, record: logging.LogRecord) -> str:
        timestamp = datetime.fromtimestamp(record.created, tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        level_color = self.COLORS.get(record.levelname, self.RESET)
        reset = self.RESET
        
        # Base readable string
        log_msg = (
            f"[{timestamp}] {level_color}{record.levelname:<8}{reset} "
            f"[{record.name}:{record.lineno}] {record.getMessage()}"
        )

        # Append structured context if present (useful in development debugging)
        context = []
        for attr in ["request_id", "client_ip", "method", "endpoint", "status_code", "latency_ms", "allowed"]:
            if hasattr(record, attr):
                context.append(f"{attr}={getattr(record, attr)}")
        
        if context:
            log_msg += f" | {', '.join(context)}"

        # Format exception if any
        if record.exc_info:
            log_msg += f"\n{self.formatException(record.exc_info)}"

        return log_msg

    @property
    def RESET(self) -> str:
        return self.COLORS["RESET"]


def setup_logging() -> logging.Logger:
    """Configures structured logging for the application.

    Logs to:
    - Console (stdout/stderr): JSON in production, human-readable color logs in dev.
    - File (Rotating Handler): Always JSON format for production ingestion.
    """
    root_logger = logging.getLogger()
    
    # Remove existing handlers to avoid duplicate logs
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)

    # Set base logging level
    log_level = getattr(logging, settings.LOG_LEVEL.upper(), logging.INFO)
    root_logger.setLevel(log_level)

    # Ensure log directory exists for the rotating file handler
    log_dir = os.path.dirname(settings.LOG_FILE_PATH)
    if log_dir:
        os.makedirs(log_dir, exist_ok=True)

    # 1. Console Handler Setup
    console_handler = logging.StreamHandler(sys.stdout)
    if settings.ENV == "dev":
        console_handler.setFormatter(ConsoleDevelopmentFormatter())
    else:
        console_handler.setFormatter(StructuredJSONFormatter())
    console_handler.setLevel(log_level)
    root_logger.addHandler(console_handler)

    # 2. Rotating File Handler Setup
    try:
        file_handler = RotatingFileHandler(
            filename=settings.LOG_FILE_PATH,
            maxBytes=settings.LOG_MAX_BYTES,
            backupCount=settings.LOG_BACKUP_COUNT,
            encoding="utf-8",
        )
        file_handler.setFormatter(StructuredJSONFormatter())
        file_handler.setLevel(log_level)
        root_logger.addHandler(file_handler)
    except Exception as e:
        # Fallback if writing to log file fails (e.g. permission error inside Docker)
        print(f"WARNING: Failed to configure log file handler: {e}", file=sys.stderr)

    # Silence verbose third-party loggers
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.error").setLevel(logging.INFO)
    
    logger = logging.getLogger("app")
    logger.info(f"Logging initialized in environment: {settings.ENV}")
    return logger


# Instantiate logger
logger = setup_logging()
