"""
Utility functions for the Nexus application.
"""

import os
from datetime import datetime
from pathlib import Path


def get_project_root() -> str:
    """
    Get the project root directory (parent of src/nxs).
    
    Returns:
        Absolute path to the project root directory
    """
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def read_prompt(prompt_file: str, prompts_dir: str = "prompts") -> str:
    """
    Read a prompt template from a file.

    Args:
        prompt_file: Name of the prompt file (e.g., "format_document.txt")
        prompts_dir: Directory containing prompt files (default: "prompts")

    Returns:
        The content of the prompt file as a string

    Raises:
        FileNotFoundError: If the prompt file doesn't exist
        IOError: If there's an error reading the file
    """
    # Get the project root directory
    project_root = Path(__file__).parent

    # Construct the full path to the prompt file
    prompt_path = project_root / prompts_dir / prompt_file

    # Check if the file exists
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt file not found: {prompt_path}")

    # Read and return the file content
    try:
        with open(prompt_path, "r", encoding="utf-8") as f:
            return f.read().strip()
    except IOError as e:
        raise IOError(f"Error reading prompt file {prompt_path}: {e}")


def list_prompt_files(prompts_dir: str = "prompts") -> list[str]:
    """
    List all available prompt files in the prompts directory.

    Args:
        prompts_dir: Directory containing prompt files (default: "prompts")

    Returns:
        List of prompt file names
    """
    project_root = Path(__file__).parent
    prompts_path = project_root / prompts_dir

    if not prompts_path.exists():
        return []

    # Return all .txt files in the prompts directory
    return [f.name for f in prompts_path.glob("*.txt")]


def format_time_hhmmss(timestamp: float) -> str:
    """
    Format a Unix timestamp as HH:MM:ss.

    Args:
        timestamp: Unix timestamp (float)

    Returns:
        Formatted string like "14:30:45" or "--:--:--" if timestamp is 0
    """
    if timestamp == 0:
        return "--:--:--"

    dt = datetime.fromtimestamp(timestamp)
    return dt.strftime("%H:%M:%S")


def generate_query_id(query: str) -> str:
    """
    Phase 6: Generate a unique query ID for tracking purposes.

    Uses a hash of the query text to create a deterministic ID.
    This ensures the same query gets the same ID, enabling
    tracker persistence and resume functionality.

    Args:
        query: User query text

    Returns:
        Unique query ID (hex string)
    """
    import hashlib

    # Create deterministic hash from query
    query_hash = hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]
    
    # Include timestamp for uniqueness if needed
    # For now, just use hash - deterministic is better for persistence
    return f"query_{query_hash}"
