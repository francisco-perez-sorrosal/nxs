"""Logging configuration for the Nexus project using loguru."""

import os
import sys
from loguru import logger
from typing import Optional

from nxs.utils import get_project_root

# Store the configured log file path to ensure consistency
_log_file_path: Optional[str] = None


def setup_logger(
    log_file: Optional[str] = None,
    log_level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
    compression: str = "zip",
    console_output: bool = False,
) -> None:
    """
    Configure loguru logger with file and console output.

    Args:
        log_file: Path to the log file (if None, uses the previously configured path or default)
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        rotation: Log rotation size
        retention: How long to keep old logs
        compression: Compression format for old logs
        console_output: Whether to output to console
    """
    global _log_file_path
    
    # Determine the log file path
    if log_file is None:
        # Use previously configured path or default to project root
        if _log_file_path is None:
            _log_file_path = os.path.join(get_project_root(), "nexus.log")
        log_file = _log_file_path
    else:
        # Ensure the path is absolute
        if not os.path.isabs(log_file):
            log_file = os.path.join(get_project_root(), log_file)
        _log_file_path = log_file
    
    # Remove default handler
    logger.remove()

    # Console output with colors
    if console_output:
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True,
        )

    # File output
    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8",
    )


def get_logger(name: Optional[str] = None):
    """
    Get a configured logger instance.

    Args:
        name: Optional name for the logger

    Returns:
        Logger instance
    """
    if name:
        return logger.bind(name=name)
    return logger


# Default logger configuration - ensure it creates nexus.log in project root
setup_logger()
