"""Cost calculator for Anthropic Claude API usage.

This module provides cost calculation based on token usage and current
Anthropic pricing (2025). Supports all Claude 4.x models.

The pricing table is built dynamically by querying the Anthropic API
for available models and mapping them to pricing from the official pricing page.
"""

from typing import Optional

from anthropic import Anthropic

from nxs.logger import get_logger

logger = get_logger(__name__)

# Anthropic Claude 4.x pricing rates (2025) - per million tokens
# Source: https://docs.claude.com/en/docs/about-claude/pricing#model-pricing
# These rates are mapped to model IDs retrieved from the API
PRICING_RATES = {
    # Pricing by model family and version
    "opus-4.1": {"input": 15.0, "output": 75.0},
    "opus-4": {"input": 15.0, "output": 75.0},
    "sonnet-4.5": {"input": 3.0, "output": 15.0},
    "sonnet-4.5-extended": {"input": 6.0, "output": 22.5},  # >200K tokens for 1M context window
    "sonnet-4": {"input": 3.0, "output": 15.0},
    "sonnet-4-extended": {"input": 6.0, "output": 22.5},  # >200K tokens for 1M context window
    "haiku-4.5": {"input": 1.0, "output": 5.0},
    # Fallback for unknown models (use Sonnet 4.5 pricing)
    "default": {"input": 3.0, "output": 15.0},
}


def _build_pricing_table_from_api() -> dict[str, dict[str, float]]:
    """Build pricing table by querying Anthropic API for available models.
    
    Fetches the list of available models from the API, filters for 4.x models,
    and maps them to pricing rates from the official pricing page.
    
    Uses the Anthropic SDK's models.list() method to get available models.
    
    Returns:
        Dictionary mapping model IDs to pricing (input/output rates per million tokens)
    """
    pricing_table: dict[str, dict[str, float]] = {}
    
    try:
        # Initialize Anthropic client
        # The client will automatically use ANTHROPIC_API_KEY from environment
        client = Anthropic()
        
        # Get available models using the SDK's models.list() method
        models_response = client.models.list()
        available_models = models_response.data
        
        logger.debug(f"Retrieved {len(available_models)} models from API")
        
        # Filter for 4.x models and build pricing table
        for model in available_models:
            model_id = model.id
            display_name = model.display_name
            
            # Filter for 4.x models (check both ID and display name)
            # Support format: claude-sonnet-4-5-20250929
            is_4x = (
                "4-5" in model_id or  # New format: claude-haiku-4-5-20251001
                "4-1" in model_id or  # New format: claude-opus-4-1-20250805
                "4.5" in model_id or  # Old format or display name
                "4.1" in model_id or  # Old format or display name
                (model_id.startswith("claude-") and ("-4-" in model_id or "-4-5-" in model_id or "-4-1-" in model_id)) or
                "4.5" in display_name or
                "4.1" in display_name or
                ("4" in display_name and "3" not in display_name.split()[-1] and "3.7" not in display_name if display_name else False)
            )
            
            if not is_4x:
                continue
            
            # Map model ID to pricing based on model family and version
            pricing = _get_pricing_for_model(model_id, display_name)
            if pricing:
                pricing_table[model_id] = pricing
                logger.debug(f"Mapped model {model_id} ({display_name}) to pricing: {pricing}")
        
        logger.info(f"Built pricing table with {len(pricing_table)} 4.x models from API")
        
    except ImportError as e:
        logger.warning(
            f"Required library not available for API call: {e}. "
            "Using fallback static pricing table."
        )
    except Exception as e:
        logger.warning(
            f"Failed to fetch models from API: {e}. "
            "Using fallback static pricing table."
        )
        # Return empty dict - will use static fallback
    
    return pricing_table


def _get_pricing_for_model(model_id: str, display_name: str) -> dict[str, float] | None:
    """Get pricing rates for a model based on its ID and display name.
    
    Args:
        model_id: Model identifier from API (e.g., "claude-sonnet-4-5-20250929")
        display_name: Display name from API (e.g., "Claude Sonnet 4.5")
    
    Returns:
        Dictionary with "input" and "output" rates, or None if not a 4.x model
    """
    model_id_lower = model_id.lower()
    display_name_lower = display_name.lower()
    
    # Determine model family and version
    # Support format: claude-sonnet-4-5-20250929
    if "opus" in model_id_lower or "opus" in display_name_lower:
        if "4.1" in model_id_lower or "4-1" in model_id_lower or "4.1" in display_name_lower:
            return PRICING_RATES["opus-4.1"].copy()
        elif ("4" in model_id_lower and "4.1" not in model_id_lower and "4-1" not in model_id_lower) or \
             ("4" in display_name_lower and "4.1" not in display_name_lower):
            return PRICING_RATES["opus-4"].copy()
    
    elif "sonnet" in model_id_lower or "sonnet" in display_name_lower:
        if "4.5" in model_id_lower or "4-5" in model_id_lower or "4.5" in display_name_lower:
            return PRICING_RATES["sonnet-4.5"].copy()
        elif ("4" in model_id_lower and "4.5" not in model_id_lower and "4-5" not in model_id_lower and "3.7" not in model_id_lower) or \
             ("4" in display_name_lower and "4.5" not in display_name_lower and "3.7" not in display_name_lower):
            return PRICING_RATES["sonnet-4"].copy()
    
    elif "haiku" in model_id_lower or "haiku" in display_name_lower:
        if "4.5" in model_id_lower or "4-5" in model_id_lower or "4.5" in display_name_lower:
            return PRICING_RATES["haiku-4.5"].copy()
    
    return None


def _get_static_pricing_fallback() -> dict[str, dict[str, float]]:
    """Get static pricing table as fallback when API is unavailable.
    
    Returns:
        Dictionary with known 4.x model IDs and their pricing
        Uses actual model IDs from Anthropic API as of 2025
    """
    return {
        # Claude Opus 4.1 (actual API model ID)
        "claude-opus-4-1-20250805": PRICING_RATES["opus-4.1"].copy(),
        # Claude Opus 4 (actual API model ID)
        "claude-opus-4-20250514": PRICING_RATES["opus-4"].copy(),
        # Claude Sonnet 4.5 (actual API model ID)
        "claude-sonnet-4-5-20250929": PRICING_RATES["sonnet-4.5"].copy(),
        "claude-sonnet-4-5-20250929-extended": PRICING_RATES["sonnet-4.5-extended"].copy(),
        # Claude Sonnet 4 (actual API model ID)
        "claude-sonnet-4-20250514": PRICING_RATES["sonnet-4"].copy(),
        "claude-sonnet-4-20250514-extended": PRICING_RATES["sonnet-4-extended"].copy(),
        # Claude Haiku 4.5 (actual API model ID)
        "claude-haiku-4-5-20251001": PRICING_RATES["haiku-4.5"].copy(),
        # Fallback
        "default": PRICING_RATES["default"].copy(),
    }


# Build pricing table dynamically from API, with static fallback
try:
    PRICING = _build_pricing_table_from_api()
    # Add extended context pricing for Sonnet models
    for model_id in list(PRICING.keys()):
        if "sonnet" in model_id.lower() and ("4" in model_id or "4-5" in model_id or "4-1" in model_id):
            extended_id = f"{model_id}-extended"
            if "4.5" in model_id or "4-5" in model_id:
                PRICING[extended_id] = PRICING_RATES["sonnet-4.5-extended"].copy()
            elif "4" in model_id and "4.5" not in model_id and "4-5" not in model_id:
                PRICING[extended_id] = PRICING_RATES["sonnet-4-extended"].copy()
    
    # If API call failed or returned no models, use static fallback
    if not PRICING:
        logger.warning("No models retrieved from API, using static fallback")
        PRICING = _get_static_pricing_fallback()
except Exception as e:
    logger.warning(f"Error building pricing table from API: {e}, using static fallback")
    PRICING = _get_static_pricing_fallback()


class CostCalculator:
    """Calculate costs for Claude API usage based on token counts.

    Uses current Anthropic pricing (2025) from:
    https://claude.com/pricing#api

    Supports Claude 4.x models only:
    - Claude Opus 4.1 and 4: $15/MTok input, $75/MTok output
    - Claude Sonnet 4.5 and 4: $3/MTok input, $15/MTok output (≤200K tokens)
    - Claude Sonnet 4.5 and 4 (extended): $6/MTok input, $22.50/MTok output (>200K tokens)
    - Claude Haiku 4.5: $1/MTok input, $5/MTok output
    - Automatically handles extended context pricing for Sonnet when applicable
    """

    def __init__(self, refresh_models: bool = False):
        """Initialize the cost calculator with current pricing.
        
        Args:
            refresh_models: If True, refresh the pricing table from API on initialization.
                          Default False to use cached pricing table.
        """
        if refresh_models:
            # Refresh pricing table from API
            try:
                api_pricing = _build_pricing_table_from_api()
                if api_pricing:
                    self.pricing = api_pricing.copy()
                    # Add extended context pricing for Sonnet models
                    for model_id in list(self.pricing.keys()):
                        if "sonnet" in model_id.lower() and ("4" in model_id or "4-5" in model_id or "4-1" in model_id):
                            extended_id = f"{model_id}-extended"
                            if "4.5" in model_id or "4-5" in model_id:
                                self.pricing[extended_id] = PRICING_RATES["sonnet-4.5-extended"].copy()
                            elif "4" in model_id and "4.5" not in model_id and "4-5" not in model_id:
                                self.pricing[extended_id] = PRICING_RATES["sonnet-4-extended"].copy()
                    logger.info("Refreshed pricing table from API")
                else:
                    self.pricing = PRICING.copy()
            except Exception as e:
                logger.warning(f"Failed to refresh pricing from API: {e}, using cached pricing")
                self.pricing = PRICING.copy()
        else:
            self.pricing = PRICING.copy()
        
        # Ensure default fallback exists
        if "default" not in self.pricing:
            self.pricing["default"] = PRICING_RATES["default"].copy()
        
        logger.debug(
            f"CostCalculator initialized with {len(self.pricing)} models "
            f"(refresh_models={refresh_models})"
        )

    def get_pricing(self, model: str, extended_context: bool = False) -> dict[str, float]:
        """Get pricing rates for a specific model.

        Args:
            model: Claude model identifier (e.g., "claude-sonnet-4-5-20250929")
            extended_context: Whether extended context pricing applies (>200K tokens)
                Only applies to Sonnet 4 and Sonnet 4.5 with 1M context window

        Returns:
            Dictionary with "input" and "output" rates per million tokens.
            Falls back to default pricing if model not found.
        """
        # Check for extended context pricing first (Sonnet 4/4.5 with >200K tokens)
        if extended_context and "sonnet" in model.lower() and "4" in model:
            extended_key = f"{model}-extended"
            if extended_key in self.pricing:
                return self.pricing[extended_key]

        # Try exact model match
        if model in self.pricing:
            return self.pricing[model]

        # Fallback to default
        logger.warning(
            f"Unknown model '{model}', using default pricing. "
            "Please update PRICING dictionary if this is a new model."
        )
        return self.pricing["default"]

    def calculate_cost(
        self,
        model: str,
        input_tokens: int,
        output_tokens: int,
        extended_context: bool = False,
    ) -> float:
        """Calculate cost for token usage.

        Args:
            model: Claude model identifier
            input_tokens: Number of input tokens
            output_tokens: Number of output tokens
            extended_context: Whether extended context pricing applies (>200K tokens)

        Returns:
            Total cost in USD (float, typically 4-6 decimal places)

        Example:
            >>> calculator = CostCalculator()
            >>> cost = calculator.calculate_cost(
            ...     "claude-3-5-sonnet-20241022",
            ...     input_tokens=1000,
            ...     output_tokens=500
            ... )
            >>> print(f"Cost: ${cost:.6f}")
        """
        pricing = self.get_pricing(model, extended_context)

        # Calculate cost: (tokens / 1_000_000) * rate_per_million
        input_cost = (input_tokens / 1_000_000) * pricing["input"]
        output_cost = (output_tokens / 1_000_000) * pricing["output"]
        total_cost = input_cost + output_cost

        logger.debug(
            f"Cost calculation: model={model}, "
            f"input={input_tokens} tokens (${input_cost:.6f}), "
            f"output={output_tokens} tokens (${output_cost:.6f}), "
            f"total=${total_cost:.6f}"
        )

        return total_cost

    def format_cost(self, cost: float, precision: int = 4) -> str:
        """Format cost as a currency string.

        Args:
            cost: Cost in USD
            precision: Number of decimal places (default 4)

        Returns:
            Formatted string like "$0.0030" or "$1.2345"
        """
        return f"${cost:.{precision}f}"

    def format_token_count(self, tokens: int) -> str:
        """Format token count with comma separators.

        Args:
            tokens: Number of tokens

        Returns:
            Formatted string like "1,234" or "1,234,567"
        """
        return f"{tokens:,}"

