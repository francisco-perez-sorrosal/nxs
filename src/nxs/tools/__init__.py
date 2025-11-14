"""Local tool functions for NXS application.

This package contains Python functions that can be exposed as tools
to Claude via the LocalToolProvider.

To add a new tool:
1. Create a module with your function(s)
2. Add type hints to all parameters
3. Write a comprehensive docstring with Args: section
4. Import and register with LocalToolProvider in main.py
"""

from nxs.tools.weather import get_weather

__all__ = ["get_weather"]
