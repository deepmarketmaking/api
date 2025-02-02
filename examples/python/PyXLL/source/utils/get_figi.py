import logging
import requests
import json
from threading import Lock

# Module-level variables to store the mappings
cusip_to_figi = {}
isin_to_figi = {}
figi_data_loaded = False
figi_lock = Lock()  # To ensure thread-safe loading

# Replace with the actual URL
FIGI_JSON_URL = "https://s3.amazonaws.com/deepmm.public/bond_data.json"


def load_figi_data():
    """
    Loads FIGI data from the specified JSON URL and populates the CUSIP and ISIN to FIGI mappings.
    This function is thread-safe and ensures data is loaded only once.
    """
    global figi_data_loaded
    with figi_lock:
        if figi_data_loaded:
            logging.debug("FIGI data already loaded. Skipping reload.")
            return
        try:
            logging.info(f"Fetching FIGI data from {FIGI_JSON_URL}")
            response = requests.get(FIGI_JSON_URL, timeout=10)
            response.raise_for_status()  # Raise an exception for HTTP errors
            data = response.json()

            if not isinstance(data, list):
                logging.error("FIGI JSON data is not a list of objects.")
                return

            for entry in data:
                figi = entry.get('F')
                cusip = entry.get('C')
                isin = entry.get('I')

                if figi:
                    if cusip:
                        cusip_upper = cusip.upper()
                        cusip_to_figi[cusip_upper] = figi.upper()
                        logging.debug(f"Mapped CUSIP '{
                                      cusip_upper}' to FIGI '{figi.upper()}'")
                    if isin:
                        isin_upper = isin.upper()
                        isin_to_figi[isin_upper] = figi.upper()
                        logging.debug(f"Mapped ISIN '{
                                      isin_upper}' to FIGI '{figi.upper()}'")
            figi_data_loaded = True
            logging.info("FIGI data loaded and mappings created successfully.")
        except requests.exceptions.RequestException as e:
            logging.error(f"Failed to fetch FIGI data: {e}")
        except json.JSONDecodeError as e:
            logging.error(f"Failed to parse FIGI JSON data: {e}")
        except Exception as e:
            logging.error(
                f"An unexpected error occurred while loading FIGI data: {e}")


def cusipToFigi(cusip):
    """
    Converts a CUSIP to FIGI using the pre-loaded mappings.

    Args:
        cusip (str): The CUSIP identifier.

    Returns:
        str: The corresponding FIGI or an empty string if not found.
    """
    if not figi_data_loaded:
        load_figi_data()
    figi = cusip_to_figi.get(cusip.upper(), "")
    if figi:
        logging.debug(f"Converted CUSIP '{cusip.upper()}' to FIGI '{figi}'.")
    else:
        logging.warning(f"No FIGI found for CUSIP '{cusip.upper()}'.")
    return figi


def isinToFigi(isin):
    """
    Converts an ISIN to FIGI using the pre-loaded mappings.

    Args:
        isin (str): The ISIN identifier.

    Returns:
        str: The corresponding FIGI or an empty string if not found.
    """
    if not figi_data_loaded:
        load_figi_data()
    figi = isin_to_figi.get(isin.upper(), "")
    if figi:
        logging.debug(f"Converted ISIN '{isin.upper()}' to FIGI '{figi}'.")
    else:
        logging.warning(f"No FIGI found for ISIN '{isin.upper()}'.")
    return figi


def get_figi(identifier_type, identifier_value):
    """
    Retrieves the FIGI based on the identifier type and value.

    Args:
        identifier_type (str): The type of identifier ('figi', 'cusip', 'isin').
        identifier_value (str): The value of the identifier.

    Returns:
        str: The corresponding FIGI or an empty string if not found or on error.
    """
    if not identifier_value:
        logging.error("Identifier value is empty.")
        return ""

    val_upper = identifier_value.upper()

    if identifier_type == 'figi':
        logging.debug(f"Identifier type is FIGI. Using FIGI: {
                      identifier_value}")
        return val_upper
    elif identifier_type == 'cusip':
        figi = cusipToFigi(val_upper)
        if figi:
            return figi
        else:
            logging.warning(f"Failed to convert CUSIP '{
                            identifier_value}' to FIGI.")
            return ""
    elif identifier_type == 'isin':
        figi = isinToFigi(val_upper)
        if figi:
            return figi
        else:
            logging.warning(f"Failed to convert ISIN '{
                            identifier_value}' to FIGI.")
            return ""
    else:
        logging.error(f"Unknown identifier type: '{
                      identifier_type}'. Cannot retrieve FIGI.")
        return ""
