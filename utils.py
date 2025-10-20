"""
Utility functions for the Nexus application.
"""

import os
from pathlib import Path
from typing import Optional


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
        with open(prompt_path, 'r', encoding='utf-8') as f:
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
