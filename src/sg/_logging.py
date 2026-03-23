"""Logging configuration for Search Gateway."""

import logging
import os
import sys
from pathlib import Path


def setup_logging(log_level: str | None = None, log_file: str | None = None) -> None:
    """Configure logging for the application.

    Args:
        log_level: Log level (DEBUG, INFO, WARNING, ERROR). Defaults to INFO.
                   Can be overridden by SG_LOG_LEVEL environment variable.
        log_file: Optional log file path. If not provided, logs to console only.
                  Can be set via SG_LOG_FILE environment variable.
    """
    # Determine log level
    level_str = os.getenv("SG_LOG_LEVEL", log_level or "INFO").upper()
    level = getattr(logging, level_str, logging.INFO)

    # Determine log file
    log_file = os.getenv("SG_LOG_FILE", log_file)

    # Create formatters
    detailed_formatter = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # Configure root logger
    root_logger = logging.getLogger()
    root_logger.setLevel(level)

    # Remove existing handlers
    root_logger.handlers.clear()

    # Console handler (always add)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)
    console_handler.setFormatter(detailed_formatter)
    root_logger.addHandler(console_handler)

    # File handler (optional)
    if log_file:
        log_path = Path(log_file).expanduser()
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.FileHandler(log_path)
        file_handler.setLevel(level)
        file_handler.setFormatter(detailed_formatter)
        root_logger.addHandler(file_handler)

    # Suppress noisy third-party loggers
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("httpcore").setLevel(logging.WARNING)
    logging.getLogger("uvicorn").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.error").setLevel(logging.ERROR)
    logging.getLogger("uvicorn.access").setLevel(logging.ERROR)
