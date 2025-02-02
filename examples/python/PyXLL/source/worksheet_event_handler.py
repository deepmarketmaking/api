import logging
from threading import Timer, Lock
# next_column_letter no longer used
from utils.excel import column_number_to_letter
from pyxll import xl_on_open, xl_on_close, xl_macro, xl_app, schedule_call
from subscription_manager import SubscriptionManager
from store.store import store
import time


# Event handler class for Worksheet events
class WorksheetEventHandler:
    def __init__(self):
        """
        Initialize the event handler.
        Sets up the debounce timer and lock.
        """
        self.debounce_interval = 1.0  # seconds
        self.debounce_timer = None
        self.debounce_lock = Lock()
        logging.info("Initialized WorksheetEventHandler.")

    def OnSelectionChange(self, target):
        """
        Event handler for selection changes in the worksheet.
        """
        try:
            selection = self.Application.Selection
            logging.debug(f"Selection changed to: {selection.GetAddress()}")
        except Exception as e:
            logging.error(f"Error in OnSelectionChange: {e}")

    def OnChange(self, target):
        """
        Event handler for cell changes.
        Triggers subscription updates if changes occur in any of the key input columns:
          - the configured identifier column,
          - side column,
          - quantity column,
          - rfq_label column,
          - ats column.

        Args:
            target (Range): The range of cells that have changed.
        """
        try:
            start_time = time.time()
            logging.info('On sheet change event')

            # Determine which worksheet triggered the event.
            try:
                worksheet = target.Parent
                sheet_name = worksheet.Name
                logging.debug(f"Change detected in worksheet: {sheet_name}")
            except Exception as e:
                logging.error(f"Error determining worksheet from target: {e}")
                return

            # Fetch configuration for the active worksheet.
            config = store.worksheet_configurations.get(sheet_name)
            if not config:
                logging.error(
                    f"No configuration found for worksheet '{sheet_name}'.")
                return

            input_parameters = config.get("input_parameters", {})
            if not input_parameters:
                logging.error(
                    f"No input_parameters defined for worksheet '{sheet_name}'.")
                return

            # Determine the configured identifier column.
            identifier_types = ['figi', 'cusip', 'isin']
            selected_identifier = next(
                (k for k in identifier_types if k in input_parameters and input_parameters[k]), None
            )
            if not selected_identifier:
                logging.error(f"No valid identifier type found in configuration for worksheet '{
                              sheet_name}'.")
                return

            # Retrieve the five columns directly from configuration.
            identifier_column = input_parameters[selected_identifier].strip(
            ).upper()
            side_column = input_parameters["side"].strip().upper()
            quantity_column = input_parameters["quantity"].strip().upper()
            rfq_label_column = input_parameters["rfq_label"].strip().upper()
            ats_column = input_parameters["ats"].strip().upper()

            if not identifier_column:
                logging.error("Identifier column is empty.")
                return

            # Prepare a list of the five input columns to monitor.
            input_columns = [
                identifier_column,
                side_column,
                quantity_column,
                rfq_label_column,
                ats_column
            ]
            logging.debug(f"Monitoring input columns: {input_columns}")

            # Get all unique column letters that have changed.
            changed_columns = set()
            try:
                for row in range(1, target.Rows.Count + 1):
                    for col in range(1, target.Columns.Count + 1):
                        try:
                            cell = target.Cells(row, col)
                            column_index = cell.Column
                            column_letter = column_number_to_letter(
                                column_index).upper()
                            changed_columns.add(column_letter)
                        except Exception as e:
                            logging.error(f"Error processing cell at row {
                                          row}, column {col}: {e}")
            except Exception as e:
                logging.error(f"Error iterating through target range: {e}")
                return

            logging.debug(f"Changed columns: {changed_columns}")

            # Check if any of the changed columns is one of the key input columns.
            if changed_columns.intersection(set(input_columns)):
                logging.info(f"Change detected in monitored columns {
                             input_columns}. Scheduling subscription update.")
                self.schedule_subscription_update()
                elapsed_time = time.time() - start_time
                logging.info(f"OnChange executed in {
                             elapsed_time:.3f} seconds.")
            else:
                logging.debug(
                    "No changes detected in monitored columns. No action taken.")
                elapsed_time = time.time() - start_time
                logging.info(f"OnChange executed in {
                             elapsed_time:.3f} seconds.")

        except Exception as e:
            logging.error(f"Error in OnChange: {e}")

    def schedule_subscription_update(self):
        """
        Schedule the SubscriptionManager.update_subscriptions call with debouncing.
        """
        with self.debounce_lock:
            if self.debounce_timer:
                self.debounce_timer.cancel()
                logging.debug("Debounce timer reset.")
            self.debounce_timer = Timer(
                self.debounce_interval, self.trigger_subscription_update)
            self.debounce_timer.start()
            logging.debug(f"Debounce timer started with interval {
                          self.debounce_interval} seconds.")

    def trigger_subscription_update(self):
        """
        Trigger the SubscriptionManager.update_subscriptions function.
        """
        try:
            logging.info(
                "Debounce interval passed. Triggering SubscriptionManager.update_active_worksheet_subscriptions.")
            schedule_call(
                SubscriptionManager.update_active_worksheet_subscriptions)
        except Exception as e:
            logging.error(
                f"Error triggering SubscriptionManager.update_active_worksheet_subscriptions: {e}")
