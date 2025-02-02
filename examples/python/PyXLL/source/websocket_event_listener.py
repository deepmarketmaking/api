import logging
import time
from datetime import datetime
from threading import Timer

from pyxll import xl_app, schedule_call
from websocket_handler import websocket_client
from utils.get_figi import get_figi
from store.store import store

# Optional: import formatting helper if needed.
from utils.formatting import format_price  # optional

# Global dictionary to store the latest inference data keyed by unique key.
LATEST_INFERENCES = {}

# Global variable for the debouncing timer.
excel_update_timer = None
DEBOUNCE_INTERVAL = 2.0  # seconds


def index_to_col(index):
    """
    Convert a zero-based column index to an Excel column letter.
    """
    col = ""
    index += 1  # convert to 1-based indexing
    while index > 0:
        index, remainder = divmod(index - 1, 26)
        col = chr(65 + remainder) + col
    return col


def col_to_index(col_letter):
    """
    Convert an Excel column letter to a zero-based index.
    """
    col_letter = col_letter.upper()
    index = 0
    for c in col_letter:
        if 'A' <= c <= 'Z':
            index = index * 26 + (ord(c) - ord('A') + 1)
        else:
            raise ValueError(f"Invalid column letter: {col_letter}")
    return index - 1  # zero-based


def next_column_letter(col):
    """
    Helper to compute the next column letter.
    """
    col = col.upper()
    num = 0
    for c in col:
        num = num * 26 + (ord(c) - ord('A') + 1)
    num += 1
    result = ""
    while num:
        num, remainder = divmod(num - 1, 26)
        result = chr(65 + remainder) + result
    return result


def schedule_excel_update():
    """
    Schedule the debounced Excel update if not already scheduled.
    """
    global excel_update_timer
    if excel_update_timer is not None:
        return
    excel_update_timer = Timer(DEBOUNCE_INTERVAL, lambda: schedule_call(
        update_excel_from_inferences_all))
    excel_update_timer.start()
    logging.info(f"Scheduled Excel update in {DEBOUNCE_INTERVAL} seconds.")


def batch_update(ws, rows_to_update, fixed_min_col, fixed_max_col, start_row, total_rows, index_to_col):
    """
    Perform a single update of the entire output region.
    The output region spans from row 'start_row' to 'total_rows' and columns fixed_min_col to fixed_max_col.
    For each row in that range, if there is an update in rows_to_update, use those values;
    otherwise, fill the row with empty strings.
    """
    num_cols = fixed_max_col - fixed_min_col + 1
    num_rows = total_rows - start_row + 1
    # Build a 2D list (list of lists) for the block update.
    block = [["" for _ in range(num_cols)] for _ in range(num_rows)]
    # For each updated row, place the updated values in the proper position.
    for row in rows_to_update:
        # Calculate the index into block (0-based relative to start_row)
        idx = row - start_row
        # For each column in the fixed region, update if provided; otherwise leave empty.
        for col in range(fixed_min_col, fixed_max_col + 1):
            block[idx][col - fixed_min_col] = rows_to_update[row].get(col, "")
    # Determine the address of the block.
    start_cell = f"{index_to_col(fixed_min_col)}{start_row}"
    end_cell = f"{index_to_col(fixed_max_col)}{total_rows}"
    try:
        ws.Range(f"{start_cell}:{end_cell}").Value = block
        logging.info(f"Batch updated region {start_cell}:{
                     end_cell} in sheet '{ws.Name}'.")
    except Exception as e:
        logging.error(f"Error in batch updating region {start_cell}:{
                      end_cell} in sheet '{ws.Name}': {e}")


def update_excel_for_sheet(ws, config):
    """
    Update the given worksheet (ws) using its configuration.
    """
    try:
        ws_name = ws.Name
        logging.info(f"Updating sheet: {ws_name}")
        input_parameters = config.get("input_parameters", {})
        if not input_parameters:
            logging.error(f"No input_parameters defined for sheet '{
                          ws_name}'. Skipping.")
            return

        # Determine the configured identifier column.
        identifier_types = ['figi', 'cusip', 'isin']
        selected_identifier = next(
            (k for k in identifier_types if k in input_parameters and input_parameters[k]), None)
        if not selected_identifier:
            logging.error(f"No valid identifier type for sheet '{
                          ws_name}'. Skipping.")
            return
        identifier_column = input_parameters[selected_identifier].strip(
        ).upper()
        if not identifier_column:
            logging.error(f"Identifier column empty for sheet '{
                          ws_name}'. Skipping.")
            return

        # Retrieve the remaining input columns directly from configuration.
        side_column = input_parameters["side"].strip().upper()
        quantity_column = input_parameters["quantity"].strip().upper()
        rfq_label_column = input_parameters["rfq_label"].strip().upper()
        ats_column = input_parameters["ats"].strip().upper()

        logging.info(f"Sheet '{ws_name}': Identifier: {identifier_column}, Side: {side_column}, "
                     f"Quantity: {quantity_column}, RFQ Label: {rfq_label_column}, ATS: {ats_column}")

        # The output region now starts one column after the ATS column.
        # (Add extra spacing by calling next_column_letter twice.)
        output_start_column = next_column_letter(
            next_column_letter(ats_column))
        logging.info(f"Output region for sheet '{
                     ws_name}' starts at column {output_start_column}")

        # Define fixed region dimensions for the single inference group.
        group_width = 20   # 1 column for date + 19 for array values.
        output_start_idx = col_to_index(output_start_column)
        fixed_min_col = output_start_idx
        fixed_max_col = output_start_idx + group_width - 1

        # Write header in row 1 with an offset of +1.
        header_offset = 1
        header_cell = ws.Cells(1, output_start_idx + header_offset)
        header_cell.Value = "Inference"
        header_cell.ColumnWidth = 15
        # Write subheaders for the following 19 columns (e.g. percentage markers)
        for j in range(19):
            ws.Cells(1, output_start_idx + header_offset +
                     1 + j).Value = f"{(j+1)*5}%"

        # Build mapping from worksheet keys to row numbers.
        start_row = 2
        try:
            used_range = ws.UsedRange
            total_rows_sheet = used_range.Rows.Count
        except Exception as e:
            logging.error(f"Error accessing UsedRange for sheet '{
                          ws_name}': {e}")
            return
        if total_rows_sheet < start_row:
            logging.info(f"No data rows found in sheet '{ws_name}'.")
            return

        try:
            id_range = ws.Range(f"{identifier_column}{start_row}:{
                                identifier_column}{total_rows_sheet}").Value
            side_range = ws.Range(f"{side_column}{start_row}:{
                                  side_column}{total_rows_sheet}").Value
            qty_range = ws.Range(f"{quantity_column}{start_row}:{
                                 quantity_column}{total_rows_sheet}").Value
            rfq_range = ws.Range(f"{rfq_label_column}{start_row}:{
                                 rfq_label_column}{total_rows_sheet}").Value
            ats_range = ws.Range(f"{ats_column}{start_row}:{
                                 ats_column}{total_rows_sheet}").Value
        except Exception as e:
            logging.error(f"Error reading key ranges for sheet '{
                          ws_name}': {e}")
            return

        def normalize(cell_range):
            if not isinstance(cell_range, (list, tuple)):
                return [cell_range]
            return [cell[0] if isinstance(cell, (list, tuple)) else cell for cell in cell_range]

        id_values = normalize(id_range)
        side_values = normalize(side_range)
        qty_values = normalize(qty_range)
        rfq_values = normalize(rfq_range)
        ats_values = normalize(ats_range)

        sheet_key_to_rows = {}
        for idx in range(len(id_values)):
            row_num = start_row + idx
            ident = id_values[idx]
            side_val = side_values[idx]
            qty_val = qty_values[idx]
            rfq_val = rfq_values[idx]
            ats_val = ats_values[idx]
            if not ident or not side_val or not qty_val or not rfq_val or not ats_val:
                continue
            ident_str = str(ident).strip().upper()
            # If identifier is not already FIGI, convert it.
            if selected_identifier != 'figi':
                figi_val = get_figi(selected_identifier, ident_str)
                if not figi_val:
                    continue
                figi_val = figi_val.upper()
            else:
                figi_val = ident_str
            side_str = str(side_val).strip().lower()
            try:
                qty_int = int(qty_val)
            except Exception:
                continue
            # expected to be one of price|spread|ytm
            rfq_str = str(rfq_val).strip().lower()
            ats_str = str(ats_val).strip().upper()    # expected to be N or Y
            unique_key = f"{figi_val}_{side_str}_{qty_int}_{rfq_str}_{ats_str}"
            sheet_key_to_rows.setdefault(unique_key, []).append(row_num)

        # Build updates for each row in one dictionary.
        rows_to_update = {}
        for unique_key, rows in sheet_key_to_rows.items():
            if unique_key not in LATEST_INFERENCES:
                continue
            inf_data = LATEST_INFERENCES[unique_key]
            # Use the inference type from the key (4th part).
            try:
                key_parts = unique_key.split("_")
                inf_type = key_parts[3]  # e.g., "price", "spread", or "ytm"
            except Exception:
                continue
            if inf_data.get(inf_type) is None:
                continue
            # Extract side from the unique key (second part)
            side_from_key = key_parts[1]
            for row in rows:
                if row not in rows_to_update:
                    rows_to_update[row] = {}
                # Write the date (if present) in the first column of the output region.
                date_val = ""
                if inf_data[inf_type].get("date"):
                    try:
                        dt = datetime.fromisoformat(
                            inf_data[inf_type]["date"].replace("Z", "+00:00"))
                        date_val = dt.strftime("%Y-%m-%d %H:%M:%S")
                    except Exception as e:
                        logging.warning(f"Error parsing date for key {
                                        unique_key}: {e}")
                rows_to_update[row][output_start_idx] = date_val
                # Write array values in columns (output_start_idx+1) to (output_start_idx+19).
                arr = inf_data[inf_type].get(inf_type, [])
                if not isinstance(arr, list):
                    arr = []
                # NEW LOGIC: Reverse the array if conditions are met.
                if (inf_type == "price" and side_from_key == "offer") or (inf_type != "price" and side_from_key == "bid"):
                    arr = list(reversed(arr))
                for j in range(19):
                    target_val = arr[j] if j < len(arr) else ""
                    if target_val != "":
                        target_val = format_price(
                            target_val, {'type': inf_type})
                    rows_to_update[row][output_start_idx + 1 + j] = target_val

        # Perform a single batch update of the entire fixed output region.
        schedule_call(lambda: batch_update(ws, rows_to_update, fixed_min_col,
                      fixed_max_col, start_row, total_rows_sheet, index_to_col))
        logging.info(f"Sheet '{ws_name}' updated with inference data.")
    except Exception as e:
        logging.error(f"Error in update_excel_for_sheet for sheet '{
                      ws.Name}': {e}")


def update_excel_from_inferences_all():
    """
    Update Excel for all worksheets for which a configuration is saved.
    """
    global excel_update_timer
    start_time = time.time()
    try:
        logging.info(
            "Updating Excel with stored inference data on all configured sheets...")
        xl = xl_app()
        if xl is None:
            logging.error("Excel application not found.")
            return
        workbook = xl.ActiveWorkbook
        if workbook is None:
            logging.error("No active workbook found.")
            return

        for sheet_name, config in store.worksheet_configurations.items():
            try:
                ws = workbook.Sheets(sheet_name)
                update_excel_for_sheet(ws, config)
            except Exception as e:
                logging.error(f"Error updating subscriptions for sheet '{
                              sheet_name}': {e}")

        elapsed_time = time.time() - start_time
        logging.info(f"update_excel_from_inferences_all executed in {
                     elapsed_time:.3f} seconds.")
    except Exception as e:
        logging.error(f"Error in update_excel_from_inferences_all: {e}")
    finally:
        global excel_update_timer
        excel_update_timer = None


def handle_received_message(message):
    """
    When an inference message is received, store its data in LATEST_INFERENCES
    (keyed by unique key) and schedule a debounced Excel update for all configured worksheets.
    """
    try:
        logging.info(
            "Received inference message; storing data for later update.")
        if 'inference' not in message:
            logging.error("Message does not contain 'inference' key.")
            return
        inference_items_raw = message['inference']
        if not isinstance(inference_items_raw, list):
            logging.error("'inference' should be a list.")
            return

        for inf in inference_items_raw:
            figi_inf = str(inf.get("figi", "")).strip().upper()
            if not figi_inf:
                logging.warning("Inference item missing FIGI. Skipping.")
                continue
            side_inf = str(inf.get("side", "")).strip().lower()
            qty_inf = inf.get("quantity", None)
            if not side_inf or qty_inf is None:
                logging.warning(
                    "Inference item missing side or quantity. Skipping.")
                continue
            try:
                qty_inf = int(qty_inf)
            except Exception as e:
                logging.warning(
                    "Inference item quantity is not an integer. Skipping.")
                continue

            # Determine the inference type based on which candidate field is present.
            inference_type = None
            for candidate in ["price", "spread", "ytm"]:
                if candidate in inf and isinstance(inf[candidate], list) and inf[candidate]:
                    inference_type = candidate
                    break
            if not inference_type:
                logging.warning(
                    "Inference item has no valid inference array. Skipping.")
                continue

            ats_inf = str(inf.get("ats_indicator", "")).strip().upper()
            if ats_inf not in {"N", "Y"}:
                logging.warning(
                    "Inference item has invalid ATS value. Skipping.")
                continue

            # Build the unique key using the detected inference_type.
            unique_key = f"{figi_inf}_{side_inf}_{
                qty_inf}_{inference_type}_{ats_inf}"
            if unique_key not in LATEST_INFERENCES:
                LATEST_INFERENCES[unique_key] = {
                    "price": None, "spread": None, "ytm": None}
            LATEST_INFERENCES[unique_key][inference_type] = inf

        schedule_excel_update()
    except Exception as e:
        logging.error(f"Error in handle_received_message: {e}")


# Subscribe to WebSocket messages.
websocket_client.subscribe(handle_received_message)
