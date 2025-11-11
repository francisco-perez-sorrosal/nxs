"""Utility functions for reasoning system."""

from pathlib import Path
from string import Template
from typing import Any

from nxs.logger import get_logger

logger = get_logger("reasoning.utils")


def load_prompt(prompt_name: str) -> str:
    """Load a prompt template from the prompts directory.

    Args:
        prompt_name: Relative path from prompts/ directory
                    e.g., "reasoning/complexity_analysis.txt"

    Returns:
        Prompt template as string

    Raises:
        FileNotFoundError: If prompt file doesn't exist
    """
    # Resolve path relative to package
    prompts_dir = Path(__file__).parent.parent.parent / "prompts"
    prompt_path = prompts_dir / prompt_name

    if not prompt_path.exists():
        raise FileNotFoundError(
            f"Prompt template not found: {prompt_path}\n"
            f"Expected at: {prompt_path.absolute()}"
        )

    logger.debug(f"Loading prompt template: {prompt_name}")
    return prompt_path.read_text(encoding="utf-8")


def format_prompt(template: str, **kwargs: Any) -> str:
    """Format a prompt template with variables.

    Uses Python's string.Template for safe substitution.

    Args:
        template: Prompt template string with ${variable} placeholders
        **kwargs: Variable values for substitution

    Returns:
        Formatted prompt string

    Raises:
        KeyError: If required variable is missing
    """
    try:
        return Template(template).substitute(**kwargs)
    except KeyError as e:
        missing_var = str(e).strip("'")
        available = list(kwargs.keys())
        raise KeyError(
            f"Missing required variable '{missing_var}' in prompt template. "
            f"Available variables: {available}"
        ) from e

