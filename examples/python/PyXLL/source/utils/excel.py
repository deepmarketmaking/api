# File: excel_utils.py

import logging
from pyxll import xl_app

# Configure module-specific logger
logger = logging.getLogger(__name__)

# Helper function: compute the next column letter.


def next_column_letter(col):
    """
    Given a column letter (e.g. 'A', 'Z', or 'AA'),
    return the next column letter.
    """
    col = col.upper()
    num = 0
    for c in col:
        num = num * 26 + (ord(c) - ord('A') + 1)
    num += 1
    # Convert number back to letter using a similar algorithm.
    result = ""
    while num:
        num, remainder = divmod(num - 1, 26)
        result = chr(65 + remainder) + result
    return result


def column_number_to_letter(n):
    """
    Converts a column number to a letter. E.g., 1 -> 'A', 27 -> 'AA'
    """
    string = ""
    while n > 0:
        n, remainder = divmod(n - 1, 26)
        string = chr(65 + remainder) + string
    return string


def update_excel(inferences):
    """
    Updates Excel by adding data from inferences to columns B and C, row by row.

    Parameters:
    - inferences (list): A list of dictionaries containing inference data.
    """
    try:
        app = xl_app()  # Get the Excel application object
        sheet = app.ActiveSheet  # Get the active sheet

        # Find the last used row in column B
        # -4162 corresponds to xlUp
        last_row = sheet.Cells(sheet.Rows.Count, 'B').End(-4162).Row

        # Start writing from the next row
        start_row = last_row + 1

        # Prepare data for batch writing
        data = []
        for inference in inferences:
            # Extract data from inference; adjust the keys based on your actual data structure
            # Replace 'field1' with actual key for column B
            figi = inference.get('figi', '')
            # Replace 'field2' with actual key for column C
            # quantity = inference.get('quantity', '')
            ytm = inference.get('ytm', [])
            ytmFirstItem = ytm[0]
            data.append([figi, ytmFirstItem])

        # Define the range to write data
        end_row = start_row + len(data) - 1
        range_str = f"B{start_row}:C{end_row}"
        cell_range = sheet.Range(range_str)

        # Assign the data to the range
        cell_range.Value = data

        logger.info(f"Successfully updated Excel with {
                    len(inferences)} inferences.")

    except Exception as e:
        logger.error(f"Error updating Excel: {e}")
        raise  # Re-raise the exception to ensure it's visible if needed
