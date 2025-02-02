import logging
import json
from pyxll import xl_app
from websocket_handler import send_subscribe, send_unsubscribe
from store.store import store
from utils.get_figi import get_figi
# no longer used but kept if needed elsewhere
from utils.excel import next_column_letter

# Configure module-specific logger
logger = logging.getLogger(__name__)

# Allowed sizes for quantity validation
ALLOWED_SIZES = {1000, 10000, 100000, 250250, 500000,
                 1000000, 2000000, 3000000, 4000000, 5000000}

# Allowed side values
ALLOWED_SIDES = {"bid", "offer", "dealer"}

# Allowed rfq_label values (lowercase)
ALLOWED_RFQ_LABELS = {"price", "spread", "ytm"}

# Allowed ats values (uppercase)
ALLOWED_ATS = {"N", "Y"}


def validate_quantity(value):
    """
    Validate that the quantity is one of the allowed sizes.
    Accepts numeric values (possibly as a string) that can be converted to an integer.
    Returns a tuple: (is_valid, numeric_value)
    """
    try:
        numeric_value = float(value)
        if numeric_value.is_integer():
            numeric_value = int(numeric_value)
        return numeric_value in ALLOWED_SIZES, numeric_value
    except (ValueError, TypeError):
        return False, None


def is_valid_config(input_parameters):
    """
    Validate that all required configuration parameters are present.
    Required:
      - One of identifier keys: 'figi', 'cusip', or 'isin' must be set and non-empty.
      - 'side', 'quantity', 'rfq_label', and 'ats' must be present and non-empty.
    Returns a tuple (is_valid, identifier_key) where identifier_key is the selected key.
    """
    identifier_key = None
    for key in ['figi', 'cusip', 'isin']:
        if key in input_parameters and input_parameters[key].strip():
            identifier_key = key
            break
    if not identifier_key:
        return False, None

    for key in ["side", "quantity", "rfq_label", "ats"]:
        if key not in input_parameters or not input_parameters[key].strip():
            return False, identifier_key

    return True, identifier_key


class SubscriptionManager:
    """
    Manages current subscriptions to the WebSocket server.

    Global subscriptions are stored as a dictionary:

        current_subscriptions = {
            (figi, quantity, rfq_label, side, ats): {
                "subscription": <subscription payload>,
                "worksheets": [list of worksheet names using this subscription]
            },
            ...
        }
    """
    current_subscriptions = {}

    @classmethod
    def update_subscriptions_for_sheet(cls, ws):
        """
        Update subscriptions based on the data in the given worksheet (ws).

        This method:
          1. Reads the worksheet configuration from store.worksheet_configurations (using ws.Name).
          2. Extracts the column letters for identifier, side, quantity, rfq_label, and ats.
          3. For each row, validates and converts the values, converts the identifier to FIGI,
             and builds a subscription payload (only one per row).
          4. Merges these new subscriptions with cls.current_subscriptions so that if multiple
             worksheets share a subscription, it is only unsubscribed when none use it.
          5. Sends subscribe and unsubscribe messages as needed.
        """
        try:
            ws_name = ws.Name
            logger.info(f"Updating subscriptions for worksheet: {ws_name}")

            # Get configuration for this worksheet.
            config = store.worksheet_configurations.get(
                ws_name, {"input_parameters": {}})
            input_parameters = config.get("input_parameters", {})

            # Validate configuration.
            valid_config, selected_identifier = is_valid_config(
                input_parameters)
            if not valid_config:
                logger.error(f"Invalid configuration for worksheet '{ws_name}'. "
                             f"Ensure an identifier ('figi', 'cusip', or 'isin') and "
                             f"'side', 'quantity', 'rfq_label', and 'ats' are all provided.")
                return

            # Get the column letters directly from configuration.
            identifier_column = input_parameters[selected_identifier].strip(
            ).upper()
            side_column = input_parameters["side"].strip().upper()
            quantity_column = input_parameters["quantity"].strip().upper()
            rfq_label_column = input_parameters["rfq_label"].strip().upper()
            ats_column = input_parameters["ats"].strip().upper()

            if not identifier_column:
                logger.error("Identifier column is empty in configuration.")
                return

            logger.info(f"Using columns for worksheet '{ws_name}': "
                        f"Identifier: '{identifier_column}', "
                        f"Side: '{side_column}', "
                        f"Quantity: '{quantity_column}', "
                        f"Label: '{rfq_label_column}', "
                        f"ATS: '{ats_column}'.")

            # Assume data rows start at row 2.
            start_row = 2
            used_range = ws.UsedRange
            total_rows = used_range.Rows.Count
            if total_rows < start_row:
                logger.info("No data rows found in the worksheet.")
                return

            # Fetch ranges for each column.
            try:
                identifier_range = ws.Range(f"{identifier_column}{start_row}:{
                                            identifier_column}{total_rows}").Value
                side_range = ws.Range(f"{side_column}{start_row}:{
                                      side_column}{total_rows}").Value
                quantity_range = ws.Range(f"{quantity_column}{start_row}:{
                                          quantity_column}{total_rows}").Value
                rfq_label_range = ws.Range(f"{rfq_label_column}{start_row}:{
                                           rfq_label_column}{total_rows}").Value
                ats_range = ws.Range(f"{ats_column}{start_row}:{
                                     ats_column}{total_rows}").Value
            except Exception as e:
                logger.error(f"Error fetching ranges from Excel: {e}")
                return

            def normalize_range(cell_range):
                if not isinstance(cell_range, (list, tuple)):
                    return [cell_range]
                return [cell[0] if isinstance(cell, (list, tuple)) else cell for cell in cell_range]

            identifier_values = normalize_range(identifier_range)
            side_values = normalize_range(side_range)
            quantity_values = normalize_range(quantity_range)
            rfq_label_values = normalize_range(rfq_label_range)
            ats_values = normalize_range(ats_range)

            # Build new subscriptions for this worksheet.
            new_subscriptions = {}
            for idx in range(len(identifier_values)):
                row = start_row + idx
                identifier = identifier_values[idx]
                side = side_values[idx]
                quantity_raw = quantity_values[idx]
                rfq_label_value = rfq_label_values[idx]
                ats_value = ats_values[idx]

                if not identifier or not isinstance(identifier, str):
                    logger.debug(
                        f"Row {row} skipped due to empty or invalid identifier.")
                    continue
                identifier_upper = identifier.strip().upper()

                if not side or not isinstance(side, str):
                    logger.debug(f"Row {row} skipped due to empty side value.")
                    continue
                side_lower = side.strip().lower()
                if side_lower not in ALLOWED_SIDES:
                    logger.debug(
                        f"Row {row} skipped due to invalid side value: {side}")
                    continue

                valid_qty, quantity = validate_quantity(quantity_raw)
                if not valid_qty or quantity is None:
                    logger.debug(f"Row {row} skipped due to invalid quantity: {
                                 quantity_raw}")
                    continue

                if not rfq_label_value or not isinstance(rfq_label_value, str):
                    logger.debug(
                        f"Row {row} skipped due to empty or invalid label value.")
                    continue
                # Convert rfq_label to lowercase and validate.
                rfq_label_val = rfq_label_value.strip().lower()
                if rfq_label_val not in ALLOWED_RFQ_LABELS:
                    logger.debug(f"Row {row} skipped due to invalid rfq_label value: {
                                 rfq_label_value}")
                    continue

                if not ats_value or not isinstance(ats_value, str):
                    logger.debug(
                        f"Row {row} skipped due to empty or invalid ATS value.")
                    continue
                # Convert ats to uppercase and validate.
                ats_val = ats_value.strip().upper()
                if ats_val not in ALLOWED_ATS:
                    logger.debug(
                        f"Row {row} skipped due to invalid ATS value: {ats_value}")
                    continue

                # Convert identifier to FIGI.
                figi = get_figi(selected_identifier, identifier_upper)
                if not figi:
                    logger.warning(f"Failed to retrieve FIGI for identifier '{
                                   identifier_upper}' in row {row}. Skipping.")
                    continue

                # Create a subscription payload using the row's values.
                subscription_key = (
                    figi, quantity, rfq_label_val, side_lower, ats_val)
                subscription_payload = {
                    "figi": figi,
                    "quantity": quantity,
                    "rfq_label": rfq_label_val,
                    "side": side_lower,
                    "ats_indicator": ats_val,
                    "subscribe": True
                }
                new_subscriptions[subscription_key] = subscription_payload

            logger.info(f"New subscriptions for worksheet '{ws_name}': {
                        json.dumps(list(new_subscriptions.keys()), default=str, indent=4)}")

            # Prepare lists for subscribe and unsubscribe messages.
            subscribe_messages = []
            unsubscribe_messages = []

            # Merge new subscriptions with global subscriptions.
            for sub_key, payload in new_subscriptions.items():
                if sub_key in cls.current_subscriptions:
                    if ws_name not in cls.current_subscriptions[sub_key]["worksheets"]:
                        cls.current_subscriptions[sub_key]["worksheets"].append(
                            ws_name)
                else:
                    cls.current_subscriptions[sub_key] = {
                        "subscription": payload,
                        "worksheets": [ws_name]
                    }
                    subscribe_messages.append(payload)

            # Remove subscriptions no longer used by this worksheet.
            keys_to_remove = []
            for sub_key, info in cls.current_subscriptions.items():
                if ws_name in info["worksheets"] and sub_key not in new_subscriptions:
                    info["worksheets"].remove(ws_name)
                    if not info["worksheets"]:
                        unsubscribe_payload = info["subscription"].copy()
                        unsubscribe_payload.pop("subscribe", None)
                        unsubscribe_payload["unsubscribe"] = True
                        unsubscribe_messages.append(unsubscribe_payload)
                        keys_to_remove.append(sub_key)
            for key in keys_to_remove:
                del cls.current_subscriptions[key]

            # --- New filtering logic: filter based on keys ---
            # Build a set of keys (tuples) for subscribe messages.
            subscribe_keys = set()
            for msg in subscribe_messages:
                key = (msg["figi"], msg["quantity"], msg["rfq_label"],
                       msg["side"], msg["ats_indicator"])
                subscribe_keys.add(key)

            # Filter unsubscribe messages by comparing their keys.
            filtered_unsubscribe_messages = []
            for msg in unsubscribe_messages:
                key = (msg["figi"], msg["quantity"], msg["rfq_label"],
                       msg["side"], msg.get("ats_indicator") or msg.get("ats"))
                if key not in subscribe_keys:
                    filtered_unsubscribe_messages.append(msg)

            if filtered_unsubscribe_messages:
                send_unsubscribe(filtered_unsubscribe_messages)
                logger.info(f"Unsubscribed from {len(
                    filtered_unsubscribe_messages)} subscriptions no longer used by any worksheet.")
            if subscribe_messages:
                send_subscribe(subscribe_messages)
                logger.info(f"Subscribed to {
                            len(subscribe_messages)} new subscriptions.")

        except Exception as e:
            logger.error(f"Error in update_subscriptions_for_sheet for worksheet '{
                         ws.Name}': {e}")

    @classmethod
    def update_active_worksheet_subscriptions(cls):
        """
        Update subscriptions for the currently active worksheet.
        """
        try:
            app = xl_app()
            if app is None:
                logger.error("Excel application not found.")
                return
            workbook = app.ActiveWorkbook
            if workbook is None:
                logger.error("No active workbook found.")
                return
            active_ws = workbook.ActiveSheet
            cls.update_subscriptions_for_sheet(active_ws)
        except Exception as e:
            logger.error(
                f"Error in update_active_worksheet_subscriptions: {e}")

    @classmethod
    def init_subscriptions(cls):
        """
        Called once after Excel opens. Iterates over all worksheets in the configuration
        and updates subscriptions for each, if the worksheet exists.
        """
        try:
            app = xl_app()
            if app is None:
                logger.error("Excel application not found.")
                return
            workbook = app.ActiveWorkbook
            if workbook is None:
                logger.error("No active workbook found.")
                return
            logger.info(
                "Initializing subscriptions for all configured worksheets...")
            # reset current subscriptions on init
            cls.current_subscriptions = {}
            for sheet_name in store.worksheet_configurations.keys():
                try:
                    # Check if the worksheet exists.
                    try:
                        ws = workbook.Sheets(sheet_name)
                    except Exception:
                        logger.warning(
                            f"Worksheet '{sheet_name}' does not exist. Skipping.")
                        continue
                    cls.update_subscriptions_for_sheet(ws)
                except Exception as e:
                    logger.error(f"Error initializing subscriptions for sheet '{
                                 sheet_name}': {e}")
        except Exception as e:
            logger.error(f"Error in init_subscriptions: {e}")

# Example usage:
# After Excel opens, call SubscriptionManager.init_subscriptions()
# When updating the active worksheet, call SubscriptionManager.update_active_worksheet_subscriptions()
