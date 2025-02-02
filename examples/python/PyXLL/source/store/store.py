from pyxll import xl_macro, xl_app, schedule_call
import tkinter as tk
from tkinter import messagebox
import json
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)


class Store:
    # Name of the custom document property to use.
    CONFIG_PROPERTY = "DeepMMConfig"

    def __init__(self):
        self.worksheet_configurations = {}

    def load_configurations_from_docproperty(cls):
        """Load worksheet configurations from the custom document property."""
        xl = xl_app()
        wb = xl.ActiveWorkbook

        try:
            # Access the custom document properties
            props = wb.CustomDocumentProperties
            try:
                config_json = props(cls.CONFIG_PROPERTY).Value
                logging.info(f"Configurations loaded from custom document property '{
                    cls.CONFIG_PROPERTY}'.")
            except Exception:
                # Property doesn't exist; use an empty configuration
                config_json = "{}"
                logging.info(f"Custom document property '{
                    cls.CONFIG_PROPERTY}' not found. Using empty configuration.")

            # Parse JSON
            cls.worksheet_configurations = json.loads(config_json)
        except Exception as e:
            cls.worksheet_configurations = {}
            logging.error(
                f"Error loading configurations from custom document property: {e}")
            messagebox.showerror("Configuration Error",
                                 f"An error occurred while loading configurations: {e}")

    def save_configurations_to_docproperty(cls):
        """Save all worksheet configurations as JSON into a custom document property."""
        xl = xl_app()
        wb = xl.ActiveWorkbook
        try:
            config_json = json.dumps(cls.worksheet_configurations, indent=4)
            props = wb.CustomDocumentProperties

            try:
                # Try to update the property if it already exists.
                props(cls.CONFIG_PROPERTY).Value = config_json
                logging.info(f"Updated custom document property '{
                    cls.CONFIG_PROPERTY}'.")
            except Exception:
                # If it doesn't exist, add it using positional arguments.
                props.Add(cls.CONFIG_PROPERTY, False, 4, config_json)
                logging.info(f"Created custom document property '{
                    cls.CONFIG_PROPERTY}'.")

            # Explicitly save the workbook so the changes persist.
            # wb.Save()
        except Exception as e:
            logging.error(
                f"Error saving configurations to custom document property: {e}")
            messagebox.showerror("Configuration Error",
                                 f"An error occurred while saving configurations: {e}")

    def get_worksheet_config_or_default(cls):
        """Get the configuration for the current active worksheet."""
        xl = xl_app()
        workbook = xl.ActiveWorkbook
        active_worksheet = workbook.ActiveSheet.Name
        # Default configuration for a worksheet is an empty input_parameters dictionary
        config = cls.worksheet_configurations.get(
            active_worksheet, {"input_parameters": {}})
        return config

    def clear_current_active_worksheet_config(cls):
        try:
            xl = xl_app()
            wb = xl.ActiveWorkbook
            active_sheet = wb.ActiveSheet
            sheet_name = active_sheet.Name

            if sheet_name not in store.worksheet_configurations:
                messagebox.showinfo(
                    "Configuration", "No configuration to clear for this worksheet.")
                return

            # Ask for confirmation
            if not messagebox.askyesno("Clear Configuration",
                                       f"Are you sure you want to clear the configuration for worksheet '{sheet_name}'?"):
                return

            # Remove the configuration from the store
            del store.worksheet_configurations[sheet_name]
            logging.info(f"Configuration for '{
                         sheet_name}' cleared from the in-memory store.")

            # Save the updated configuration back to the custom document property.
            cls.save_configurations_to_docproperty()

            messagebox.showinfo(
                "Configuration", "Configuration cleared successfully.")

        except Exception as e:
            logging.error(f"Error clearing configuration: {e}")
            messagebox.showerror(
                "Configuration Error", f"An error occurred while clearing configuration: {e}")


store = Store()
