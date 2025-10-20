"""Logging configuration for the Nexus project using loguru."""

import sys
from pathlib import Path
from loguru import logger
from typing import Optional


def setup_logger(
    log_file: str = "nexus.log",
    log_level: str = "INFO",
    rotation: str = "10 MB",
    retention: str = "7 days",
    compression: str = "zip",
    console_output: bool = False
) -> None:
    """
    Configure loguru logger with file and console output.
    
    Args:
        log_file: Path to the log file
        log_level: Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        rotation: Log rotation size
        retention: How long to keep old logs
        compression: Compression format for old logs
        console_output: Whether to output to console
    """
    # Remove default handler
    logger.remove()
    
    # Console output with colors
    if console_output:
        logger.add(
            sys.stderr,
            level=log_level,
            format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            colorize=True
        )
    
    # File output
    logger.add(
        log_file,
        level=log_level,
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
        rotation=rotation,
        retention=retention,
        compression=compression,
        encoding="utf-8"
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
import os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
log_file_path = os.path.join(project_root, "nexus.log")
setup_logger(log_file_path)
