# utils/formatting.py

import logging

logger = logging.getLogger(__name__)


def format_price(value, config):
    """
    Formats the price based on the specified type.

    Args:
        value (float or int): The price value to format.
        config (dict): Configuration object containing the 'type' key.

    Returns:
        str: The formatted price.

    Raises:
        ValueError: If the 'type' in config is invalid or value is not a number.
    """
    price_type = config.get('type')
    if price_type is None:
        logger.error("Configuration object missing 'type' key.")
        raise ValueError("Configuration object must contain a 'type' key.")

    try:
        numeric_value = float(value)
    except (ValueError, TypeError) as e:
        logger.error(f"Invalid value '{value}' for formatting: {e}")
        raise ValueError(f"Value '{value}' must be a number.") from e

    try:
        if price_type.lower() == 'ytm':
            formatted_value = f"{numeric_value:.2f}%"
        elif price_type.lower() == 'spread':
            formatted_value = f"{numeric_value:.1f}"
        elif price_type.lower() == 'price':
            formatted_value = f"${numeric_value:.3f}"
        else:
            logger.error(f"Invalid type '{
                         price_type}' provided for formatting.")
            raise ValueError(f"Invalid type '{
                             price_type}'. Expected 'price', 'ytm', or 'spread'.")
    except Exception as e:
        logger.error(f"Error formatting value '{
                     value}' with type '{price_type}': {e}")
        raise ValueError(f"Error formatting value '{
                         value}' with type '{price_type}'.") from e

    logger.debug(f"Formatted value: {formatted_value} (Type: {price_type})")
    return formatted_value
